"""AV0222-08 (H05/H06): a proposal shows the store's home notice window and shelf-check day in words, both sides.
Run: python3 -B -m unittest hass.tests.test_proposal_notice_words -v
"""

import unittest

from hass import conversation, voice

EXPIRES = "2026-11-02T17:10:00+00:00"
NOTICE = {"text": "Closed Thanksgiving Day", "until": "2026-11-26"}
NOTICE_WORDS = "Closed Thanksgiving Day - through Thursday, November 26"
FROM_WORDS = "Closed Thanksgiving Day - from Wednesday, November 25 through Thursday, November 26"


def _lines(b, a, field="notice", undo=False):
    rec = {"collection": "store", "key": "store", "before": {field: b}, "after": {field: a}}
    return voice.plain(conversation.proposal_text("ab12", {"records": [rec], "warnings": []}, EXPIRES, undo=undo)).splitlines()[1:-2]


class NoticeWordsTests(unittest.TestCase):
    def test_notice_set_replace_clear_and_reverse_both_sides(self):
        with_from = {"text": "Closed Thanksgiving Day", "from": "2026-11-25", "until": "2026-11-26"}
        self.assertEqual(_lines(None, NOTICE), [f"the shop details, Home notice: from nothing to {NOTICE_WORDS}"])
        self.assertEqual(_lines(NOTICE, None, undo=True), [f"the shop details, Home notice: from {NOTICE_WORDS} to nothing"])
        out = _lines(NOTICE, with_from)
        self.assertIn(NOTICE_WORDS, "\n".join(out))
        self.assertIn(FROM_WORDS, "\n".join(out))
        self.assertNotIn("{", "\n".join(out))

    def test_long_owner_text_keeps_last_day_visible(self):
        text = "x" * 160
        out = "\n".join(_lines({"text": text, "until": "2026-11-26"}, {"text": text, "until": "2026-11-27"}))
        self.assertIn(f"{text} - through Thursday, November 26", out)
        self.assertIn(f"{text} - through Friday, November 27", out)

    def test_shelf_check_dates_use_fixed_english_words(self):
        self.assertEqual(_lines("2026-11-02", "2026-11-03", "selection_checked_on"), ["the shop details, Shelf check: from Monday, November 2 to Tuesday, November 3"])
        self.assertIn("Thursday, February 29", "\n".join(_lines(None, "2024-02-29", "selection_checked_on")))

    def test_invalid_legacy_values_fall_back_without_crashing(self):
        for bad in ("2026-13-01", "20261103", "2026-11-03T10:00:00", 5, {"text": "x"}, {"text": "", "until": "2026-11-26"},
                    {"text": "x", "from": "2026-11-27", "until": "2026-11-26"}, {"text": "x", "until": "2026-11-26", "extra": 1}):
            out = "\n".join(_lines(None, bad, "selection_checked_on" if not isinstance(bad, dict) else "notice"))
            self.assertNotRegex(out, r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), ")
        self.assertIn("from nothing to", "\n".join(_lines(None, "2026-11-03", "selection_checked_on")).replace("Tuesday, November 3", ""))

    def test_other_fields_and_collections_unchanged(self):
        rec = {"collection": "products", "key": "p1", "before": {"name": "2026-11-02"}, "after": {"name": "2026-11-03"}}
        out = voice.plain(conversation.proposal_text("ab12", {"records": [rec], "warnings": []}, EXPIRES))
        self.assertIn("2026-11-03", out)
        self.assertNotIn("Tuesday", out)

    def test_added_store_uses_same_formatter(self):
        rec = {"collection": "store", "key": "store", "before": None, "after": {"notice": NOTICE, "selection_checked_on": "2026-11-03", "phone": "8055550142"}}
        out = voice.plain(conversation.proposal_text("ab12", {"records": [rec], "warnings": []}, EXPIRES))
        self.assertIn(f"  Home notice: {NOTICE_WORDS}", out)
        self.assertIn("  Shelf check: Tuesday, November 3", out)


if __name__ == "__main__":
    unittest.main()
