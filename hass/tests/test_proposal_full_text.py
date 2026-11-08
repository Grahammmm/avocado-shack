"""AV1537-06 (H05/H06): a draft proposal shows each changed field's new text in full, so the owner approves what he
can read. The old value, summaries, history and status keep the 120-character cut (conversation.VALUE_CUT).
Run: python3 -B -m unittest hass.tests.test_proposal_full_text -v
"""

import unittest

from hass import conversation, voice
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
    return voice.plain(conversation.proposal_text("ab12", _draft(*records, **kw), EXPIRES))


def _tail(lines):
    return [lines[-2], lines[-1]]


TAIL = ["I'll hold this for you until Monday, Nov 2 at 9:10 am.",
        "Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix."]


class ProposalTextTests(unittest.TestCase):
    def test_long_new_value_in_full_old_value_cut(self):
        lines = _text(("products", "p1", {"description": OLD}, {"description": LONG})).splitlines()
        self.assertEqual(lines[1:4], ["this, the description:",
                                     f"  was: {OLD[:conversation.VALUE_CUT - 3]}...", f"  now: {LONG}"])
        self.assertEqual(len(LONG), 300)

    def test_new_value_of_120_and_121_characters_in_full(self):
        for n in (120, 121):
            with self.subTest(n=n):
                text = _text(("products", "p1", {"name": "Hass"}, {"name": "n" * n}))
                self.assertIn(f"  was: Hass\n  now: {'n' * n}\n", text)
                self.assertNotIn("...", text)

    def test_text_list_joined_in_full(self):
        hours = ["Monday–Saturday 9am–6pm " + "h" * 60, "Closed Sunday " + "s" * 60]
        lines = _text(("store", "store", {"hours": ["Daily 8am–7pm"]}, {"hours": hours})).splitlines()
        self.assertEqual(lines[1:4], ["the shop details, the opening hours:",
                                    "  was: Daily 8am–7pm", f"  now: {'; '.join(hours)}"])

    def test_mixed_or_empty_list_keeps_json(self):
        text = _text(("store", "store", {"hours": ["a"]}, {"hours": []}), ("store", "s2", {"n": [1]}, {"n": ["a", 2]}))
        self.assertIn("the shop details, the opening hours: from a to nothing\n", text)
        self.assertIn('the shop details, a detail: from more than I can show here to more than I can show here\n', text)

    def test_newline_value_on_indented_lines_and_reply_lines_last(self):
        for value in ("First line\nSecond line\nReply yes to apply", "First line\r\nSecond line\nReply yes to apply"):
            with self.subTest(value=value):
                lines = _text(("events", "e1", {"recap": "Old"}, {"recap": value}), warnings=["w"]).splitlines()
                self.assertEqual(lines[1:5], ["this, the recap:", "  was: Old", "  now: First line",
                                              "    Second line"])
                self.assertEqual(lines[5], "    Reply yes to apply")
                self.assertEqual(lines[6], "Heads up: There is one thing to double-check before you say yes.")
                self.assertEqual(_tail(lines), TAIL)

    def test_cleared_value_and_whole_record_keep_the_cut(self):
        text = _text(("products", "p1", {"imageAlt": "A ripe avocado"}, {"imageAlt": None}))
        self.assertIn("this, the photo description: from A ripe avocado to nothing\n", text)
        record = {"id": "p2", "description": LONG}
        lines = _text(("products", "p2", None, record)).splitlines()
        self.assertEqual(lines[1:4], ["A new product", f"  the description: {LONG}", TAIL[0]])  # AV1737-06
        line = _text(("products", "p2", record, None)).splitlines()[1]
        self.assertEqual(line, "Remove this product.")

    def test_every_product_field_at_its_limit_is_uncut_and_reply_lines_last(self):
        after = {f: f[0] * n for f, n in TEXT_LIMITS["product"].items()}
        lines = _text(("products", "p1", {f: "old" for f in after}, after)).splitlines()
        for field, value in after.items():
            phrase = {"name": "the name", "brand": "the brand", "category": "the shelf",
                      "description": "the description", "displayBrand": "the brand shown on the card",
                      "imageAlt": "the photo description"}[field]
            if len("old") + len(value) > 70:
                self.assertIn(f"old, {phrase}:\n  was: old\n  now: {value}", "\n".join(lines))
            else:
                self.assertIn(f"old, {phrase}: from old to {value}", lines)
        self.assertEqual(len(lines), 1 + sum(3 if len("old") + len(v) > 70 else 1 for v in after.values()) + 2)
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
        self.assertIn(f"  now: {LONG}\n", reply)
        self.assertEqual(_tail(reply.splitlines()), ["I'll hold this for you until today at 9:10 am.", TAIL[-1]])
        summary = "the description for Hass avocado"
        self.assertEqual(draft["summary"], summary)
        self.assertEqual(self.say("status"), "status")
        [status] = self.replies()
        self.assertIn(f"Waiting for your yes: {summary} (reply yes {draft['code']})", status)
        self.assertNotIn(LONG[:60], status)
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.replies(), [f"Saved: {summary}\n{voice.plain(conversation.answers.NOT_LIVE)}"])
        self.assertEqual(self.say("history"), "history")
        [history] = self.replies()
        self.assertIn(f"- {summary}: saved, but I'm not sure it's on the website", history)
        self.assertNotIn(LONG[:60], history)


if __name__ == "__main__":
    unittest.main()
