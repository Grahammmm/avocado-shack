"""RF0421-10 tests: owner text inside voice.quote cannot unbalance the voice guard.

The two reserved marks (OPEN/CLOSE) are dropped from the quoted words, so one quote() call is always one balanced wrapper:
a mark typed by the owner cannot hide later Hass sentences, nor expose his own words. Synthetic values only; nothing is sent.
Run: python3 -B -m unittest hass.tests.test_voice_quote_markers
"""
import unittest

from hass import voice
from hass.tests import test_conversation as tc

OPEN, CLOSE = voice.OPEN, voice.CLOSE
q = voice.quote
BAD = " The server is slow."  # Hass-authored suffix that must always be caught


def _balanced(s):
    return s == "" or (s.count(OPEN) == 1 and s.count(CLOSE) == 1 and s[0] == OPEN and s[-1] == CLOSE)


class QuoteMarkerTests(unittest.TestCase):
    def test_open_marker_cannot_hide_later_assistant_rules(self):
        for name in (OPEN + "Honey", "Ho" + OPEN + "ney", "Honey" + OPEN, OPEN * 3 + "Honey" + OPEN * 2):
            with self.subTest(name=repr(name)):
                self.assertEqual(voice.check("Which " + q(name) + "?" + BAD), ["the word 'server'"])
                self.assertEqual(voice.check("Which " + q(name) + "? Nice \U0001F600"), ["an emoji Mike did not use first"])
                self.assertEqual(voice.check("Which " + q(name) + "? See photo-product-001."), ["an id like photo-product-001"])

    def test_close_marker_does_not_expose_owner_words(self):
        for name in (CLOSE + "Server Rack", "Server" + CLOSE + " Rack", "Server Rack" + CLOSE, CLOSE * 3 + "Server Rack" + CLOSE * 2):
            with self.subTest(name=repr(name)):
                self.assertEqual(voice.check("Which " + q(name) + "?"), [])
                self.assertEqual(voice.check("Which " + q(name) + "?" + BAD), ["the word 'server'"])

    def test_mixed_balanced_and_unbalanced_input_markers(self):
        for value in (OPEN + CLOSE, CLOSE + OPEN, OPEN, CLOSE, OPEN + CLOSE + "x" + CLOSE + OPEN, "x" + CLOSE + OPEN + "y", ""):
            with self.subTest(value=repr(value)):
                out = q(value)
                self.assertTrue(_balanced(out), repr(out))
                self.assertEqual(out == "", voice.plain(value) == "")
                self.assertEqual(voice.plain(out), voice.plain(value))
        self.assertEqual(q(OPEN + CLOSE), "")
        # adjacent quoted values stay isolated
        self.assertEqual(voice.check("A " + q(OPEN + "x") + q("server" + CLOSE) + "." + BAD), ["the word 'server'"])
        self.assertEqual(voice.check("A " + q(OPEN + "x") + q("server" + CLOSE) + "."), [])

    def test_visible_bytes_and_nonmarker_inputs_stay_compatible(self):
        for value in ("Honey", "Caf\u00e9 \U0001F600, \u201cnew\u201d!\nline two", None, 42, "\ue002 other private use", q("already")):
            with self.subTest(value=repr(value)):
                self.assertEqual(voice.plain(q(value)), voice.plain(str(value)))
        self.assertEqual(q("Honey"), OPEN + "Honey" + CLOSE)
        self.assertEqual(q(None), OPEN + "None" + CLOSE)
        self.assertEqual(q(42), OPEN + "42" + CLOSE)
        self.assertEqual(q("\ue002x"), OPEN + "\ue002x" + CLOSE)  # no broad private-use stripping
        self.assertEqual(q(q("twice")), OPEN + "twice" + CLOSE)  # re-quoting gives one wrapper

    def test_guard_enforces_suffix_after_quote(self):
        text = "Which " + q("Honey" + OPEN) + "?" + BAD
        sent, broken = voice.guard(text)
        self.assertEqual((sent, broken), (voice.SAFE_LINE, ["the word 'server'"]))
        sent, broken = voice.guard("Which " + q("Honey" + OPEN + CLOSE) + "?")
        self.assertEqual((sent, broken), ("Which Honey?", []))
        # flags keep their own meaning: emoji_ok allows the emoji, not the banned word
        self.assertEqual(voice.check("Which " + q(OPEN + "x") + "? \U0001F600", emoji_ok=True), [])
        self.assertEqual(voice.check("Which " + q(OPEN + "x") + "? \U0001F600" + BAD, emoji_ok=True), ["the word 'server'"])


class OutboxSuffixEnforcement(tc.ConversationTestCase):
    def test_strict_outbox_raises_on_hass_suffix_after_injected_open(self):
        with self.assertRaises(voice.VoiceError):
            self.conv.outbox.add(tc.CHAT, "Which " + q("Honey" + OPEN) + "?" + BAD)

    def test_nonstrict_outbox_stores_safe_line_and_reason_only_log(self):
        self.conv.outbox.strict = False
        self.conv.outbox.msg_id = "m-quote-markers-1"
        self.conv.outbox.add(tc.CHAT, "Which " + q("Honey" + OPEN) + "?" + BAD)
        [row] = [dict(r) for r in self.conv.db.execute("SELECT text FROM outbox")]
        self.assertEqual(row["text"], voice.SAFE_LINE)
        [logged] = self.conv.log.rows()
        self.assertEqual(logged["kind"], "voice-fallback")
        self.assertNotIn("Honey", str(logged))


if __name__ == "__main__":
    unittest.main()
