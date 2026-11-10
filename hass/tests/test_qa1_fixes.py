"""HASS-QA-1: owner-test bugs found by the real-interpreter battery (agent-work reports/hass/QA-1.md)."""
import unittest

from hass import voice


class NoticeShownInTheDraft(unittest.TestCase):
    def test_a_notice_value_shows_its_words(self):
        # battery nt-set (real GPU interpreter): the draft said "Avocado Shack, the notice: from nothing to more than I can
        # show here", so the owner was asked to approve a notice he could not read
        shown = voice.value_words({"text": "Closed early Friday at 3 for a family event", "until": "2026-11-13"}, "notice")
        self.assertIn("Closed early Friday at 3 for a family event", shown)
        self.assertNotIn("more than I can show", shown)

    def test_nested_values_still_say_so(self):
        self.assertEqual(voice.value_words({"a": {"b": 1}}), "more than I can show here")

    def test_an_empty_record_still_says_so(self):
        self.assertEqual(voice.value_words({"text": ""}), "more than I can show here")


if __name__ == "__main__":
    unittest.main()
