"""RF2320-11 tests: receive() refuses a str/bytes envelope over 64 KiB before json.loads (fixtures only, nothing sent).
Run: python3 -B -m unittest hass.tests.test_receiver_size"""

import json, unittest  # noqa: E401
from unittest import mock

from hass import receiver
from hass.tests.test_receiver import NOW, SECRET, ReceiverTestCase

CAP = receiver.MAX_ENVELOPE_BYTES
NONCE = "ab" * 16


class SizeTests(ReceiverTestCase):
    def sized(self, target, nonce=NONCE):
        """The owner's new message, sealed, with its body text padded so the JSON envelope is exactly `target` bytes."""
        def build(pad):
            ev = self.event_from("new-message")
            ev["data"]["text"] = ev["data"]["text"] + " " + "x" * pad
            return receiver.forward(ev, SECRET, nonce=nonce, now=NOW)
        raw = build(target - len(build(0).encode("utf-8")))
        self.assertEqual(len(raw.encode("utf-8")), target)
        return raw

    def nothing_kept(self):
        self.assertEqual((self.inbound_rows(), self.drafts(), self.reply.calls), ([], [], []))
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 0)

    def assert_size(self, raw):
        with mock.patch.object(json, "loads", side_effect=AssertionError("parsed")) as loads:
            out = self.rx.receive(raw, secret=SECRET, now=NOW)
        self.assertEqual(loads.call_count, 0)
        self.assertEqual(out, {"result": "rejected", "draft_id": None, "disposition": None,
                               "reason": "the envelope is larger than 64 KB, so it was not read"})
        self.nothing_kept()

    def assert_shape(self, raw):
        out = self.rx.receive(raw, secret=SECRET, now=NOW)
        self.assertEqual((out["result"], out["reason"]), ("rejected", receiver.REJECTED["shape"]))
        self.nothing_kept()

    def test_cap_and_reason(self):
        self.assertEqual(CAP, 65536)
        self.assertEqual(receiver.REJECTED["size"], "the envelope is larger than 64 KB, so it was not read")

    def test_valid_sealed_envelope_one_byte_over_is_rejected_as_str_bytes_and_bytearray(self):
        raw = self.sized(CAP + 1)
        for form in (raw, raw.encode("utf-8"), bytearray(raw.encode("utf-8"))):
            self.assert_size(form)

    def test_the_same_message_at_exactly_the_cap_is_handled_as_today(self):
        out = self.rx.receive(self.sized(CAP), secret=SECRET, now=NOW)  # parsed and queued as today
        self.assertEqual((out["result"], out["disposition"]), ("handled", "too-long"))
        self.assertEqual([r["state"] for r in self.inbound_rows()], ["done"])
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 1)

    def test_exactly_the_cap_as_bytes_is_not_rejected_for_size(self):
        out = self.rx.receive(self.sized(CAP).encode("utf-8"), secret=SECRET, now=NOW)
        self.assertEqual((out["result"], out["disposition"]), ("handled", "too-long"))

    def test_oversized_garbage_gets_the_size_reason_not_shape(self):
        self.assert_size("x" * (CAP + 1))
        self.assert_size(b"\xff" * (CAP + 1))
        self.assert_shape("x" * CAP)  # at the cap it is parsed, and fails as before

    def test_str_is_measured_in_utf8_bytes_not_characters(self):
        self.assert_shape("é" * 30000)  # 60,000 bytes: passes the size check, then not an envelope
        self.assert_size("é" * 40000)  # 80,000 bytes although len(str) is 40,000
        self.assert_size("é" * (CAP // 2) + "x")  # 65,537 bytes, 32,769 characters
        self.assert_shape("é" * (CAP // 2))  # exactly 65,536 bytes

    def test_lone_surrogate_does_not_raise_in_the_size_check(self):
        self.assert_shape("\ud800")  # under the cap: still the shape rejection
        self.assert_shape('{"v": 1, "x": "\ud800"}')
        self.assert_size("\ud800" * 30000)  # 90,000 bytes under surrogatepass: size, no exception

    def test_a_size_rejection_does_not_consume_the_nonce(self):
        self.assert_size(self.sized(CAP + 1, nonce=NONCE))
        out = self.rx.receive(self.seal_with(NONCE), secret=SECRET, now=NOW)
        self.assertEqual(out["result"], "drafted")
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 1)
        again = self.rx.receive(self.sized(CAP + 1, nonce=NONCE), secret=SECRET, now=NOW + 1)
        self.assertEqual(again["reason"], receiver.REJECTED["size"])  # still unread, not a replay
        self.assertEqual(len(self.drafts()), 1)

    def seal_with(self, nonce):
        return receiver.forward(self.event_from("new-message"), SECRET, nonce=nonce, now=NOW)

    def test_a_dict_is_not_measured(self):
        env = json.loads(self.sized(CAP + 1))
        out = self.rx.receive(env, secret=SECRET, now=NOW)
        self.assertEqual((out["result"], out["disposition"]), ("handled", "too-long"))


if __name__ == "__main__":
    unittest.main()
