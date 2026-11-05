"""RF1140-7 (H06/H08): a reply with a preview picture goes out as its text plus one fixed note; the outbox moves on.
No network (fake transport); synthetic fixtures. Run: python3 -m unittest discover -s hass/tests -t . -v"""

import builtins, hashlib, json, os, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import preview
from hass.bridge import PICTURE_NOTE, BlueBubblesSender, BridgeError, normalize
from hass.tests.test_bridge import BASE, OWNER_CHAT, PASSWORD, FakeTransport, event, password_file
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_undo import PNG, H06TestCase

PIC = "/nonexistent/x.png"


class PictureSendTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeTransport()
        self.sender = BlueBubblesSender(BASE, password_file(self), self.fake)

    def test_picture_reply_is_text_newline_note_and_the_path_is_never_sent(self):
        self.sender.send(OWNER_CHAT, "Draft A1 \u2026", [PIC])
        [call] = self.fake.calls
        self.assertEqual(call["body"]["message"], "Draft A1 \u2026\n" + PICTURE_NOTE)
        for part in (call["url"], json.dumps(call["body"]), json.dumps(call["headers"])):
            self.assertNotIn("x.png", part)

    def test_text_reply_is_unchanged(self):
        self.sender.send(OWNER_CHAT, "hi", [])
        self.sender.send(OWNER_CHAT, "hi")
        self.assertEqual([c["body"]["message"] for c in self.fake.calls], ["hi", "hi"])

    def test_http_failure_with_a_picture_names_neither_password_nor_path(self):
        with self.assertRaises(BridgeError) as ctx:
            BlueBubblesSender(BASE, password_file(self), FakeTransport(500)).send(OWNER_CHAT, "Draft", [PIC])
        err = ctx.exception
        self.assertEqual((err.code, err.status), ("http-error", 500))
        for text in (str(err), repr(err), repr(err.args), repr(err.__cause__), repr(err.__context__)):
            self.assertNotIn(PASSWORD, text)
            self.assertNotIn(PIC, text)

    def test_the_attachment_is_never_opened_or_stated(self):
        touched = []

        def guard(real):
            def wrapper(path, *args, **kwargs):
                if PIC in str(path):
                    touched.append(str(path))
                    raise PermissionError("attachment must not be touched")
                return real(path, *args, **kwargs)
            return wrapper
        with mock.patch.object(builtins, "open", guard(builtins.open)), mock.patch.object(os, "stat", guard(os.stat)), \
                mock.patch.object(os, "lstat", guard(os.lstat)), mock.patch.object(os, "open", guard(os.open)):
            self.sender.send(OWNER_CHAT, "Draft", [PIC])
        self.assertEqual((touched, len(self.fake.calls)), ([], 1))


class PictureFlushTests(H06TestCase):
    def make_previewer(self):
        folder = tempfile.TemporaryDirectory(prefix="hass-pic-")
        self.addCleanup(folder.cleanup)
        self.png = png = Path(folder.name) / "p.png"
        preview._write_private(png, PNG)
        return mock.Mock(capture=lambda files, target, out, assets=None: {"ok": True, "png": str(png), "error": None})

    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "ownerChat": OWNER_CHAT})
        self.conv.db.close()
        self.conv = self.open()

    def test_proposals_with_pictures_flush_and_the_png_is_kept(self):
        before, fake = hashlib.sha256(self.png.read_bytes()).hexdigest(), FakeTransport()
        sender = BlueBubblesSender(BASE, password_file(self), fake)
        self.assertEqual(self.conv.handle(normalize(event("new-message"))), "proposed")
        [row] = self.conv.outbox.unsent()
        self.assertEqual(json.loads(row["attachments"]), [str(self.png)])
        self.assertEqual((self.conv.flush(sender), self.conv.outbox.unsent()), (1, []))
        self.say("desc2", chat=OWNER_CHAT)
        rows = self.conv.outbox.unsent()
        self.assertIn([str(self.png)], [json.loads(r["attachments"]) for r in rows])
        self.assertEqual((self.conv.flush(sender), self.conv.outbox.unsent()), (len(rows), []))
        for call, row in zip(fake.calls, [None, *rows], strict=True):
            pic = row is None or json.loads(row["attachments"])
            self.assertEqual(call["body"]["message"].endswith("\n" + PICTURE_NOTE), bool(pic))
        self.assertNotIn(str(self.png), json.dumps(fake.calls))
        self.assertEqual(hashlib.sha256(self.png.read_bytes()).hexdigest(), before)
