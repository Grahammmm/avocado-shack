"""RF0910-4 tests: receive() reads envelope text strictly. A repeated JSON key (any depth) or a NaN/Infinity constant is
the shape rejection, before the MAC, with the nonce untouched (fixtures only, nothing sent).
Run: python3 -B -m unittest hass.tests.test_receiver_strict_json"""

import json, unittest  # noqa: E401

from hass import receiver
from hass.tests.test_receiver import NOW, SECRET, ReceiverTestCase

NONCE = "cd" * 16
SHAPE = receiver.REJECTED["shape"]


class StrictJsonTests(ReceiverTestCase):
    def clean(self, nonce=NONCE):
        return receiver.forward(self.event_from("new-message"), SECRET, nonce=nonce, now=NOW)

    def edit(self, raw, old, new):
        self.assertEqual(raw.count(old), 1, old)
        return raw.replace(old, new, 1)

    def two_bodies(self, nonce=NONCE):
        """A decoy body first, then the validly MAC'd one: a last-key-wins parser would accept it."""
        raw = self.clean(nonce)
        decoy = dict(json.loads(raw)["body"], text="decoy: delete everything")
        return self.edit(raw, '{"body": ', '{"body": ' + json.dumps(decoy, sort_keys=True) + ', "body": ')

    def assert_shape(self, raw, nonce=NONCE):
        out = self.rx.receive(raw, secret=SECRET, now=NOW)
        self.assertEqual(out, {"result": "rejected", "draft_id": None, "disposition": None, "reason": SHAPE})
        self.assertEqual((self.inbound_rows(), self.drafts(), self.reply.calls), ([], [], []))
        self.assertNotIn(nonce, self.inbox.seen())
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 0)

    def assert_drafted(self, raw):
        out = self.rx.receive(raw, secret=SECRET, now=NOW)
        self.assertEqual(out, {"result": "drafted", "draft_id": self.drafts()[0]["code"], "disposition": "proposed",
                               "reason": "a draft waits for the owner's approval; nothing was applied"})
        self.assertIn(NONCE, self.inbox.seen())

    def test_valid_sealed_text_is_drafted_as_on_main(self):
        self.assert_drafted(self.clean())

    def test_a_second_body_key_is_shape_even_though_the_last_one_is_validly_sealed(self):
        raw = self.two_bodies()
        self.assertEqual(json.loads(raw)["body"]["text"], json.loads(self.clean())["body"]["text"])  # last one wins
        self.assert_shape(raw)

    def test_a_repeated_key_inside_body_is_shape(self):
        self.assert_shape(self.edit(self.clean(), '"text": ', '"text": "decoy", "text": '))

    def test_a_repeated_top_level_key_with_the_same_value_is_still_shape(self):
        raw = self.clean()
        self.assertTrue(raw.endswith('"v": 1}'))
        self.assert_shape('{"v": 1, ' + raw[1:])
        self.assert_shape(self.edit(raw, '"nonce": ', f'"nonce": "{NONCE}", "nonce": '))

    def test_nan_and_infinity_anywhere_are_shape_never_version_mac_or_stale(self):
        raw = self.clean()
        for const in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(const=const):
                self.assert_shape(self.edit(raw, f'"ts": {NOW}', f'"ts": {const}'))
                self.assert_shape(self.edit(raw, '"v": 1', f'"v": {const}'))  # main: the version reason
                self.assert_shape(self.edit(raw, '"attachments": 0', f'"attachments": {const}'))
                self.assert_shape(self.edit(raw, '{"body": ', f'{{"x": [{const}], "body": '))

    def test_bytes_and_bytearray_with_a_repeated_key_are_the_same_rejection(self):
        raw = self.two_bodies().encode("utf-8")
        self.assert_shape(raw)
        self.assert_shape(bytearray(raw))
        self.assert_shape(self.edit(self.clean(), '"v": 1', '"v": NaN').encode("utf-8"))

    def test_a_dict_built_in_python_takes_the_unchanged_path(self):
        self.assert_drafted(json.loads(self.clean()))

    def test_a_rejected_duplicate_does_not_consume_the_nonce(self):
        self.assert_shape(self.two_bodies())
        self.assert_drafted(self.clean())  # same nonce, now accepted
        self.assertEqual(len(self.drafts()), 1)
        again = self.rx.receive(self.two_bodies(), secret=SECRET, now=NOW + 1)
        self.assertEqual(again["reason"], SHAPE)  # still unread, not a replay
        self.assertEqual(len(self.drafts()), 1)


if __name__ == "__main__":
    unittest.main()
