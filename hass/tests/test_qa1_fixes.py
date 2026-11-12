"""HASS-QA-1: owner-test bugs found by the real-interpreter battery (agent-work reports/hass/QA-1.md).
Run: python3 -B -m unittest hass.tests.test_qa1_fixes -v
"""
import unittest

from hass import voice


class NoticeShownInTheDraft(unittest.TestCase):
    def test_a_notice_value_shows_its_words_and_last_day(self):
        # battery nt-set (real GPU interpreter): the draft said "Avocado Shack, the notice: from nothing to more than I can
        # show here", so the owner was asked to approve a notice he could not read
        shown = voice.value_words({"text": "Closed early Friday at 3 for a family event", "until": "2026-11-13"}, "notice")
        self.assertEqual(shown, "Closed early Friday at 3 for a family event (until November 13)")

    def test_a_notice_with_an_unreadable_day_still_shows_its_words(self):
        self.assertEqual(voice.value_words({"text": "Closed Monday", "until": "soon"}), "Closed Monday")

    def test_other_small_records_keep_their_wording(self):
        # a meeting place {place, lat} must not leak a raw coordinate (pinned in test_proposal_added)
        self.assertEqual(voice.value_words({"place": "Gate", "lat": 33.3}), "more than I can show here")
        self.assertEqual(voice.value_words({"a": {"b": 1}}), "more than I can show here")

    def test_an_empty_notice_still_says_so(self):
        self.assertEqual(voice.value_words({"text": " ", "until": "2026-11-13"}), "more than I can show here")


if __name__ == "__main__":
    unittest.main()
