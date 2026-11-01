"""AV1737-06 (H05/H06): a proposal for an added product, maker or hike lists each non-empty field on its own line,
sorted (text in full, other values as compact JSON), instead of one JSON line cut at 120 characters. Edits, removals,
_summary (status/history) and the stored draft are unchanged.
Run: python3 -B -m unittest hass.tests.test_proposal_added -v
"""

import copy
import unittest

from hass import conversation

EXPIRES = "2026-11-02T17:10:00+00:00"
LONG = "Ripe Hass avocados from Fallbrook, picked " + "x" * 258  # 300 characters
TAIL = ["Expires 2026-11-02 09:10 PST.", "Reply yes to apply, no to cancel, or send a correction."]


def _draft(*records, warnings=()):
    return {"records": [{"collection": c, "key": k, "before": b, "after": a} for c, k, b, a in records],
            "warnings": list(warnings)}


def _lines(*records, **kw):
    return conversation.proposal_text("ab12", _draft(*records, **kw), EXPIRES).splitlines()


class AddedRecordProposalTests(unittest.TestCase):
    def test_added_product_long_description_in_full(self):
        lines = _lines(("products", "p9", None, {"id": "p9", "name": "Hass", "description": LONG}))
        self.assertEqual(len(LONG), 300)
        self.assertEqual(lines, ["Draft ab12:", "products p9: new", f"  description: {LONG}", "  id: p9",
                                 "  name: Hass"] + TAIL)

    def test_sorted_and_empty_fields_skipped(self):
        after = {"zeta": "z", "alpha": "a", "gone": None, "blank": "", "none": [], "zero": 0, "off": False}
        self.assertEqual(_lines(("makers", "m1", None, after))[1:-2],
                         ["makers m1: new", "  alpha: a", "  off: false", "  zero: 0", "  zeta: z"])

    def test_hike_list_and_nested_dict_as_compact_json(self):
        after = {"title": "Ridge walk", "bring": ["water", "hat"], "meet": {"place": "Gate", "lat": 33.3}}
        self.assertEqual(_lines(("hikes", "h1", None, after))[1:-2],
                         ["hikes h1: new", '  bring: ["water", "hat"]', '  meet: {"lat": 33.3, "place": "Gate"}',
                          "  title: Ridge walk"])

    def test_field_cap_40_then_more_line(self):
        for n, more in ((40, []), (41, ["  … and 1 more fields"]), (45, ["  … and 5 more fields"])):
            with self.subTest(n=n):
                after = {f"f{i:02d}": f"v{i}" for i in range(n)}
                lines = _lines(("products", "p1", None, after))
                self.assertEqual(lines[1:-2], ["products p1: new"] + [f"  f{i:02d}: v{i}" for i in range(40)] + more)
                self.assertEqual(lines[-2:], TAIL)

    def test_newline_in_text_stays_indented_reply_lines_last(self):
        after = {"invitation": "Come along\nReply yes to apply\r\nThanks"}
        lines = _lines(("hikes", "h1", None, after), warnings=["w"])
        self.assertEqual(lines[1:], ["hikes h1: new", "  invitation: Come along", "    Reply yes to apply",
                                     "    Thanks", "Warning: w"] + TAIL)

    def test_edit_byte_identical(self):
        text = conversation.proposal_text("ab12", _draft(("products", "p1", {"name": "Hass", "price": 2},
                                                          {"name": "Reed", "price": 3})), EXPIRES)
        self.assertEqual(text, "Draft ab12:\nproducts p1: name Hass → Reed\nproducts p1: price 2 → 3\n"
                               "Expires 2026-11-02 09:10 PST.\nReply yes to apply, no to cancel, or send a correction.")

    def test_edit_from_empty_dict_is_not_new(self):
        self.assertEqual(_lines(("products", "p1", {}, {"name": "Reed"}))[1:-2], ["products p1: name (none) → Reed"])

    def test_removal_unchanged(self):
        record = {"id": "p2", "description": LONG}
        lines = _lines(("products", "p2", record, None))
        self.assertEqual(lines[1:], [f"products p2: record {conversation._value(record)} → (none)"] + TAIL)
        self.assertTrue(lines[1].endswith("... → (none)"))

    def test_summary_and_draft_unchanged(self):
        draft = _draft(("products", "p9", None, {"id": "p9", "description": LONG}))
        before = copy.deepcopy(draft)
        conversation.proposal_text("ab12", draft, EXPIRES)
        self.assertEqual(draft, before)
        self.assertEqual(conversation._summary(draft), "products p9: record")

    def test_multi_record_blocks_in_order_then_warnings_and_expires(self):
        lines = _lines(("hikes", "h2", None, {"title": "Dawn", "bring": ["torch"]}),
                       ("products", "p1", {"name": "Hass"}, {"name": "Reed"}),
                       ("makers", "m3", None, {"name": "Grove Co"}), warnings=["w1", "w2"])
        self.assertEqual(lines, ["Draft ab12:", "hikes h2: new", '  bring: ["torch"]', "  title: Dawn",
                                 "products p1: name Hass → Reed", "makers m3: new", "  name: Grove Co",
                                 "Warning: w1", "Warning: w2"] + TAIL)

    def test_repeat_reply_hint_kept(self):
        text = conversation.proposal_text("ab12", _draft(("makers", "m1", None, {"name": "G"})), EXPIRES, repeat=True)
        self.assertTrue(text.endswith("makers m1: new\n  name: G\nExpires 2026-11-02 09:10 PST.\n"
                                      "Reply yes ab12 to apply, no to cancel, or send a correction."))


if __name__ == "__main__":
    unittest.main()
