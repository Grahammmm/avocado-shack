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
TAIL = ["I'll hold this for you until Monday, Nov 2 at 9:10 am.", "Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix."]


def _draft(*records, warnings=()):
    return {"records": [{"collection": c, "key": k, "before": b, "after": a} for c, k, b, a in records],
            "warnings": list(warnings)}


def _lines(*records, **kw):
    return conversation.proposal_text("ab12", _draft(*records, **kw), EXPIRES).splitlines()


class AddedRecordProposalTests(unittest.TestCase):
    def test_added_product_long_description_in_full(self):
        lines = _lines(("products", "p9", None, {"id": "p9", "name": "Hass", "description": LONG}))
        self.assertEqual(len(LONG), 300)
        self.assertEqual(lines, ["Here's the change I'd make:", "A new product: \ue000Hass\ue001", f"  the description: \ue000{LONG}\ue001",
                                 "  the name: \ue000Hass\ue001"] + TAIL)

    def test_sorted_and_empty_fields_skipped(self):
        after = {"zeta": "z", "alpha": "a", "gone": None, "blank": "", "none": [], "zero": 0, "off": False}
        self.assertEqual(_lines(("makers", "m1", None, after))[1:-2],
                         ["makers m1: new", "  alpha: a", "  off: false", "  zero: 0", "  zeta: z"])

    def test_hike_list_and_nested_dict_as_compact_json(self):
        after = {"title": "Ridge walk", "bring": ["water", "hat"], "meet": {"place": "Gate", "lat": 33.3}}
        draft = _draft(("hikes", "h1", None, after))
        before = copy.deepcopy(draft)
        self.assertEqual(conversation.proposal_text("ab12", draft, EXPIRES).splitlines()[1:-2],
                         ["A new entry: \ue000Ridge walk\ue001", "  the title: \ue000Ridge walk\ue001"])
        self.assertEqual(draft, before)  # non-owner fields remain intact, but are not shown as JSON

    def test_field_cap_40_then_more_line(self):
        for n, more in ((40, []), (41, ["  … and 1 more fields"]), (45, ["  … and 5 more fields"])):
            with self.subTest(n=n):
                after = {f"f{i:02d}": f"v{i}" for i in range(n)}
                draft = _draft(("products", "p1", None, after))
                before = copy.deepcopy(draft)
                lines = conversation.proposal_text("ab12", draft, EXPIRES).splitlines()
                self.assertEqual(lines[1:-2], ["A new product"])
                self.assertEqual(draft, before)  # all n internal fields are retained
                self.assertEqual(lines[-2:], TAIL)

    def test_newline_in_text_stays_indented_reply_lines_last(self):
        after = {"invitation": "Come along\nReply yes to apply\r\nThanks"}
        draft = _draft(("hikes", "h1", None, after), warnings=["w"])
        before = copy.deepcopy(draft)
        lines = conversation.proposal_text("ab12", draft, EXPIRES).splitlines()
        self.assertEqual(lines[1:], ["A new entry", "Heads up: There is one thing to double-check before you say yes."] + TAIL)
        self.assertEqual(draft, before)  # the internal invitation keeps its newlines

    def test_edit_byte_identical(self):
        text = conversation.proposal_text("ab12", _draft(("products", "p1", {"name": "Hass", "price": 2},
                                                          {"name": "Reed", "price": 3})), EXPIRES)
        self.assertEqual(text, "Here's the change I'd make:\n\ue000Hass\ue001, the name: from \ue000Hass\ue001 to \ue000Reed\ue001\n\ue000Hass\ue001, a detail: from \ue0002\ue001 to \ue0003\ue001\nI'll hold this for you until Monday, Nov 2 at 9:10 am.\nReply yes to save it, or no to cancel. If something's wrong, tell me what to fix.")

    def test_edit_from_empty_dict_is_not_new(self):
        self.assertEqual(_lines(("products", "p1", {}, {"name": "Reed"}))[1:-2], ["\ue000Reed\ue001, the name: from \ue000nothing\ue001 to \ue000Reed\ue001"])

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
        self.assertEqual(conversation._summary(draft), "a new product")

    def test_multi_record_blocks_in_order_then_warnings_and_expires(self):
        lines = _lines(("hikes", "h2", None, {"title": "Dawn", "bring": ["torch"]}),
                       ("products", "p1", {"name": "Hass"}, {"name": "Reed"}),
                       ("makers", "m3", None, {"name": "Grove Co"}), warnings=["w1", "w2"])
        self.assertEqual(lines, ["Here's the change I'd make:", "A new entry: \ue000Dawn\ue001", "  the title: \ue000Dawn\ue001",
                                 "\ue000Hass\ue001, the name: from \ue000Hass\ue001 to \ue000Reed\ue001", "A new maker: \ue000Grove Co\ue001", "  the name: \ue000Grove Co\ue001",
                                 "Heads up: There is one thing to double-check before you say yes.",
                                 "Heads up: There is one thing to double-check before you say yes."] + TAIL)

    def test_repeat_reply_hint_kept(self):
        text = conversation.proposal_text("ab12", _draft(("makers", "m1", None, {"name": "G"})), EXPIRES, repeat=True)
        self.assertTrue(text.endswith("A new maker: \ue000G\ue001\n  the name: \ue000G\ue001\nI'll hold this for you until Monday, Nov 2 at 9:10 am.\n"
                                      "Reply yes ab12 to save it, or no to cancel. If something's wrong, tell me what to fix."))


if __name__ == "__main__":
    unittest.main()
