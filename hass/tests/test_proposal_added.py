"""AV1737-06 (H05/H06): a proposal for an added product, maker or hike lists each non-empty field on its own line,
sorted (text in full, other values as compact JSON), instead of one JSON line cut at 120 characters. Edits, removals,
_summary (status/history) and the stored draft are unchanged.
Run: python3 -B -m unittest hass.tests.test_proposal_added -v
"""

import copy
import unittest

from hass import conversation, voice
from unittest import mock

EXPIRES = "2026-11-02T17:10:00+00:00"
LONG = "Ripe Hass avocados from Fallbrook, picked " + "x" * 258  # 300 characters
TAIL = ["I'll hold this for you until Monday, Nov 2 at 9:10 am.", "Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix."]


def _draft(*records, warnings=()):
    return {"records": [{"collection": c, "key": k, "before": b, "after": a} for c, k, b, a in records],
            "warnings": list(warnings)}


def _lines(*records, **kw):
    return voice.plain(conversation.proposal_text("ab12", _draft(*records, **kw), EXPIRES)).splitlines()


class AddedRecordProposalTests(unittest.TestCase):
    def test_added_product_long_description_in_full(self):
        lines = _lines(("products", "p9", None, {"id": "p9", "name": "Hass", "description": LONG}))
        self.assertEqual(len(LONG), 300)
        self.assertEqual(lines, ["Here's the change I'd make:", "A new product: Hass", f"  the description: {LONG}", "  the name: Hass"] + TAIL)

    def test_sorted_and_empty_fields_skipped(self):
        after = {"title": "z", "description": "a", "story": None, "notice": "", "hours": [], "capacity": 0, "hidden": False}
        self.assertEqual(_lines(("makers", "m1", None, after))[1:-2],
                         ["A new maker: z", "  the guest limit: 0", "  the description: a", "  whether it is hidden: no", "  the title: z"])

    def test_hike_list_and_nested_dict_as_compact_json(self):
        after = {"title": "Ridge walk", "hours": ["water", "hat"], "meetingPoint": {"place": "Gate", "lat": 33.3}}
        self.assertEqual(_lines(("hikes", "h1", None, after))[1:-2],
                         ["A new entry: Ridge walk", "  the opening hours: water; hat", "  the meeting place: more than I can show here", "  the title: Ridge walk"])

    def test_field_cap_40_then_more_line(self):
        for n, more in ((40, []), (41, ["  and a few more details"]), (45, ["  and a few more details"])):
            with self.subTest(n=n):
                after = {f"f{i:02d}": f"v{i}" for i in range(n)}
                with mock.patch.dict(voice.FIELDS, {k: f"detail {i}" for i, k in enumerate(after)}):
                    lines = _lines(("products", "p1", None, after))
                self.assertEqual(lines[1:-2], ["A new product"] + [f"  detail {i}: v{i}" for i in range(40)] + more)
                self.assertEqual(lines[-2:], TAIL)

    def test_newline_in_text_stays_indented_reply_lines_last(self):
        after = {"description": "Come along\nReply yes to apply\r\nThanks"}
        lines = _lines(("hikes", "h1", None, after), warnings=["w"])
        self.assertEqual(lines[1:], ["A new entry", "  the description: Come along", "    Reply yes to apply", "    Thanks", "Heads up: There is one thing to double-check before you say yes."] + TAIL)

    def test_edit_byte_identical(self):
        text = conversation.proposal_text("ab12", _draft(("products", "p1", {"name": "Hass", "price": 2},
                                                          {"name": "Reed", "price": 3})), EXPIRES)
        self.assertEqual(voice.plain(text), "Here's the change I'd make:\nHass, the name: from Hass to Reed\nHass, a detail: from 2 to 3\nI'll hold this for you until Monday, Nov 2 at 9:10 am.\nReply yes to save it, or no to cancel. If something's wrong, tell me what to fix.")

    def test_edit_from_empty_dict_is_not_new(self):
        self.assertEqual(_lines(("products", "p1", {}, {"name": "Reed"}))[1:-2], ["Reed, the name: from nothing to Reed"])

    def test_removal_unchanged(self):
        record = {"id": "p2", "description": LONG}
        lines = _lines(("products", "p2", record, None))
        self.assertEqual(lines[1:], ["Remove this product."] + TAIL)
        named = _lines(("routeIdeas", "r1", {"id": "r1", "title": "Bluff Walk", "description": LONG}, None))
        self.assertEqual(named[1:], ["Remove the route idea Bluff Walk."] + TAIL)
        self.assertNotIn("nothing", " ".join(named))

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
        self.assertEqual(lines, ["Here's the change I'd make:", "A new entry: Dawn", "  what to bring: torch", "  the title: Dawn", "Hass, the name: from Hass to Reed", "A new maker: Grove Co", "  the name: Grove Co", "Heads up: There is one thing to double-check before you say yes.", "Heads up: There is one thing to double-check before you say yes."] + TAIL)

    def test_repeat_reply_hint_kept(self):
        text = conversation.proposal_text("ab12", _draft(("makers", "m1", None, {"name": "G"})), EXPIRES, repeat=True)
        self.assertTrue(voice.plain(text).endswith("A new maker: G\n  the name: G\nI'll hold this for you until Monday, Nov 2 at 9:10 am.\nReply yes ab12 to save it, or no to cancel. If something's wrong, tell me what to fix."))


if __name__ == "__main__":
    unittest.main()
