"""Messages that are blank once the voice marks are removed are 'empty' (RF0640-12). Synthetic input only."""
import itertools
import unittest

from hass import voice
from hass.tests.test_conversation import CHAT, ConversationTestCase

O, C = voice.OPEN, voice.CLOSE
BLANKS = (" ", " \t\n", "\u00a0", "\u2003 ", "\n\n")
MARKS_ONLY = ("", O, C, O + C, O + O + C + C, O + O, C + C, C + O, O + " " + C, O + "\t" + C + " " + O + C, voice.quote(""))
FLAGS = [dict(zip(("emoji_ok", "long_ok", "ids_ok"), f)) for f in itertools.product((False, True), repeat=3)]


class VisibleEmpty(unittest.TestCase):
    def test_marked_whitespace_is_empty_after_plain(self):
        for blank in BLANKS:
            for text in (blank, voice.quote(blank), O + blank + C, "  " + O + blank + C):
                self.assertEqual(voice.check(text), ["empty"], repr(text))

    def test_marker_only_combinations_are_empty(self):
        for text in MARKS_ONLY:
            self.assertEqual(voice.check(text), ["empty"], repr(text))

    def test_flags_cannot_admit_visibly_empty_messages(self):
        for flags in FLAGS:
            for text in MARKS_ONLY + tuple(voice.quote(b) for b in BLANKS) + (None, True, 0, 5, [], ["x"], {}, {"a": 1}):
                self.assertEqual(voice.check(text, **flags), ["empty"], (flags, text))

    def test_guard_uses_existing_safe_line_for_visible_empty(self):
        for flags in FLAGS:
            for text in MARKS_ONLY + tuple(voice.quote(b) for b in BLANKS):
                self.assertEqual(voice.guard(text, **flags), (voice.SAFE_LINE, ["empty"]), (flags, text))

    def test_nonblank_quoted_words_and_surrounding_prose_stay_unchanged(self):
        for text in (voice.quote("Tomatoes"), voice.quote("Hass") + voice.quote("Fuerte"), "Here you go: " + voice.quote("  ") + " ok",
                     " Done. ", "!", ".", "Added " + voice.quote("product.set_photo") + " for you."):
            self.assertEqual(voice.check(text), [], repr(text))
            self.assertEqual(voice.guard(text), (voice.plain(text), []), repr(text))
        self.assertIn("the word 'interpreter'", voice.check("The interpreter failed."))


class OutboxVisibleEmpty(ConversationTestCase):
    def _rows(self):
        return [dict(r) for r in self.conv.db.execute("SELECT text FROM outbox")]

    def test_strict_outbox_refuses_visible_empty_without_row(self):
        for text in (voice.quote(" \t\n"), O + C):
            with self.assertRaises(voice.VoiceError) as ctx:
                self.conv.outbox.add(CHAT, text)
            self.assertIn("empty", str(ctx.exception))
        self.assertEqual(self._rows(), [])

    def test_nonstrict_outbox_records_one_existing_fallback(self):
        self.conv.outbox.strict = False
        self.conv.outbox.msg_id = "m-voice-empty"
        self.conv.outbox.add(CHAT, voice.quote(" \t\n"))
        self.assertEqual(self._rows(), [{"text": voice.SAFE_LINE}])
        [logged] = self.conv.log.rows()
        self.assertEqual(logged["kind"], "voice-fallback")


if __name__ == "__main__":
    unittest.main()
