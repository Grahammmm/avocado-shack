"""RF1450-13: send_png refuses wrongly typed name/data through the fixed BridgeError before password access or transport.
Fixtures only: temp private password file and a recording fake transport."""
import os, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import bridge, bridge_attach, relay

CHAT = "iMessage;-;owner@example.invalid"
PNG = relay.PNG_SIG + b"fixture-picture" * 3
NAME = "hass-12-0.png"
CANARY = "canary-value-xyz"


class AttachmentInputTypes(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pw = Path(tmp.name) / "password"
        pw.write_text("synthetic-not-a-real-password")
        os.chmod(pw, 0o600)
        self.sent = []
        self.sender = bridge_attach.BlueBubblesAttachmentSender(
            "http://127.0.0.1:1234", pw, CHAT, lambda url, body, headers, timeout: (self.sent.append((body, timeout)), 200)[1])

    def refused(self, chat, data, name):
        with mock.patch.object(bridge, "_private_file", side_effect=AssertionError("password access")) as pf:
            with self.assertRaises(bridge.BridgeError) as cm:
                self.sender.send_png(chat, data, name)
        pf.assert_not_called()
        e = cm.exception
        self.assertEqual((e.code, e.status, e.args), ("refused", None, ("refused", None, bridge.SEND_PATH)))
        self.assertIsNone(e.__cause__)
        self.assertTrue(e.__suppress_context__ or e.__context__ is None)
        self.assertNotIn(CANARY, repr(e.args))
        self.assertEqual(self.sent, [])

    def test_wrong_name_types_raise_fixed_refusal_without_password_access(self):
        for bad in (None, NAME.encode(), True, 7, [NAME], {NAME: 1}):
            with self.subTest(name=bad):
                self.refused(CHAT, PNG, bad)

    def test_wrong_data_types_raise_fixed_refusal_without_password_access(self):
        for bad in (None, True, 5, 1.5, CANARY, [CANARY], {CANARY: 1}, memoryview(PNG)):
            with self.subTest(data=type(bad).__name__):
                self.refused(CHAT, bad, NAME)

    def test_bytes_and_bytearray_controls_preserve_multipart(self):
        for data in (PNG, bytearray(PNG)):
            with self.subTest(kind=type(data).__name__):
                self.sent.clear()
                before = bytes(data)
                self.sender.send_png(CHAT, data, NAME)
                self.assertEqual(len(self.sent), 1)
                body, timeout = self.sent[0]
                self.assertEqual(timeout, 30)
                self.assertIn(before, body)
                self.assertIn(f'filename="{NAME}"'.encode(), body)
                self.assertEqual(bytes(data), before)

    def test_existing_png_name_size_and_owner_refusals_stay_fixed(self):
        for chat, data, name in ((CHAT, b"GIF89a" + b"x" * 20, NAME), (CHAT, b"", NAME),
                                 (CHAT, PNG + b"x" * relay.MAX_PNG, NAME), (CHAT, PNG, "bad.png"),
                                 ("iMessage;-;other@example.invalid", PNG, NAME)):
            with self.subTest(chat=chat, name=name, size=len(data)):
                self.refused(chat, data, name)
        exact = relay.PNG_SIG + b"x" * (relay.MAX_PNG - len(relay.PNG_SIG))
        self.sender.send_png(CHAT, exact, NAME)
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
