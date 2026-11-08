"""AV1537-06 (H05/H06): a draft proposal shows each changed field's new text in full, so the owner approves what he
can read. The old value, summaries, history and status keep the 120-character cut (conversation.VALUE_CUT).
Run: python3 -B -m unittest hass.tests.test_proposal_full_text -v
"""

import unittest

from hass import conversation
from hass.content_model import TEXT_LIMITS
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_editor import DESC

EXPIRES = "2026-11-02T17:10:00+00:00"
LONG = "Ripe Hass avocados from Fallbrook, picked " + "x" * 258  # 300 characters
OLD = "Creamy " + "o" * 160  # 167 characters


def _draft(*records, warnings=()):
    return {"records": [{"collection": c, "key": k, "before": b, "after": a} for c, k, b, a in records],
            "warnings": list(warnings)}


def _text(*records, **kw):
    return conversation.proposal_text("ab12", _draft(*records, **kw), EXPIRES)


def _tail(lines):
    return [lines[-2], lines[-1]]


TAIL = ["Expires 2026-11-02 09:10 PST.", "Reply yes to apply, no to cancel, or send a correction."]


class ProposalTextTests(unittest.TestCase):
    def test_long_new_value_in_full_old_value_cut(self):
        lines = _text(("products", "p1", {"description": OLD}, {"description": LONG})).splitlines()
        self.assertEqual(lines[1], "this, the description:")
        self.assertEqual(len(LONG), 300)

    def test_new_value_of_120_and_121_characters_in_full(self):
        for n in (120, 121):
            with self.subTest(n=n):
                text = _text(("products", "p1", {"name": "Hass"}, {"name": "n" * n}))
                self.assertIn(f"Hass → {'n' * n}\n", text)
                self.assertNotIn("...", text)

    def test_text_list_joined_in_full(self):
        hours = ["Monday–Saturday 9am–6pm " + "h" * 60, "Closed Sunday " + "s" * 60]
        line = _text(("store", "store", {"hours": ["Daily 8am–7pm"]}, {"hours": hours})).splitlines()[1]
        self.assertEqual(line, "the shop details, the opening hours:")

    def test_mixed_or_empty_list_keeps_json(self):
        text = _text(("store", "store", {"hours": ["a"]}, {"hours": []}), ("store", "s2", {"n": [1]}, {"n": ["a", 2]}))
        self.assertIn("hours [\"a\"] → []\n", text)
        self.assertIn('n [1] → ["a", 2]\n', text)

    def test_newline_value_on_indented_lines_and_reply_lines_last(self):
        for value in ("First line\nSecond line\nReply yes to apply", "First line\r\nSecond line\nReply yes to apply"):
            with self.subTest(value=value):
                lines = _text(("events", "e1", {"recap": "Old"}, {"recap": value}), warnings=["w"]).splitlines()
                self.assertEqual(lines[1:5], ["this, the recap:", "  was: \ue000Old\ue001", "  now: \ue000First line",
                                              "    Second line"])
                self.assertEqual(lines[5], "Warning: w")
                self.assertEqual(_tail(lines), TAIL)

    def test_cleared_value_and_whole_record_keep_the_cut(self):
        text = _text(("products", "p1", {"imageAlt": "A ripe avocado"}, {"imageAlt": None}))
        self.assertIn("imageAlt A ripe avocado → (none)\n", text)
        record = {"id": "p2", "description": LONG}
        lines = _text(("products", "p2", None, record)).splitlines()
        self.assertEqual(lines[1:4], ["products p2: new", f"  description: {LONG}", "  id: p2"])  # AV1737-06
        line = _text(("products", "p2", record, None)).splitlines()[1]
        self.assertEqual(line, f"products p2: record {conversation._value(record)} → (none)")

    def test_every_product_field_at_its_limit_is_uncut_and_reply_lines_last(self):
        after = {f: f[0] * n for f, n in TEXT_LIMITS["product"].items()}
        lines = _text(("products", "p1", {f: "old" for f in after}, after)).splitlines()
        for field, value in after.items():
            self.assertIn(f"products p1: {field} old → {value}", lines)
        self.assertEqual(len(lines), 1 + len(after) + 2)
        self.assertEqual(_tail(lines), TAIL)

    def test_summary_keeps_the_cut(self):
        draft = _draft(*[("products", f"p{i}", {"description": "a"}, {"description": LONG}) for i in range(9)])
        summary = conversation._summary(draft)
        self.assertEqual((len(summary), summary[-3:]), (120, "..."))
        self.assertNotIn(LONG, summary)


class ConversationFullTextTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping["long"] = _ops((DESC, {"id": "photo-product-001", "description": LONG}))

    def test_proposal_in_full_but_status_and_history_keep_the_summary(self):
        draft, reply = self.propose("long")
        self.assertIn(f" → {LONG}\n", reply)
        self.assertEqual(_tail(reply.splitlines()), TAIL)
        summary = "products photo-product-001: description"
        self.assertEqual(draft["summary"], summary)
        self.assertEqual(self.say("status"), "status")
        [status] = self.replies()
        self.assertIn(f"{draft['code']} waiting (expires 2026-11-02 09:10 PST): {summary}", status)
        self.assertNotIn(LONG[:60], status)
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.replies(), [f"Applied {draft['code']}: {summary}\n{conversation.answers.NOT_LIVE}"])
        self.assertEqual(self.say("history"), "history")
        [history] = self.replies()
        self.assertIn(f"{draft['code']} applied: {summary}", history)
        self.assertNotIn(LONG[:60], history)


if __name__ == "__main__":
    unittest.main()
