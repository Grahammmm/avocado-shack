"""RF2030-5 tests: a claim term added in a list-of-text field (store hours lines) asks, never drafts.

Frozen rule: a field whose new value is a list of strings is checked as the newline-joined text of its items (the old
value joined the same way when it is a list of strings, else ""); count rule, owner check and `where` are unchanged.
Lists holding a non-string item, and dict values, are skipped. Run: python3 -m unittest hass.tests.test_claims_lists -v
"""

import unittest

from hass import claims, conversation
from hass.tests.test_claims import MAKERS, P1
from hass.tests.test_conversation import ConversationTestCase, _ops

HOURS = ["Mon–Sat 9–6", "Local honey Saturdays"]
SET_HOURS = [{"op": "store.set_hours", "args": {}}]


def hours(before, after, ops=None):
    return {"ops": ops or SET_HOURS, "records": [{"collection": "store", "key": "store",
                                                 "before": {"name": "Shack", "hours": before},
                                                 "after": {"name": "Shack", "hours": after}}]}


class ListFieldTests(unittest.TestCase):
    def hits(self, before, after, owner="", ops=None):
        return claims.unstated(hours(before, after, ops), owner, MAKERS)

    def test_added_line_with_unsaid_term_is_a_hit_on_the_hours_field(self):
        self.assertEqual(self.hits(["Mon–Sat 9–6"], HOURS, "add a Saturday honey line"),
                         [("store store hours", "local")])
        self.assertEqual(self.hits(None, HOURS, "add a Saturday honey line"), [("store store hours", "local")])

    def test_owner_words_say_it(self):
        self.assertEqual(self.hits(["Mon–Sat 9–6"], HOURS, "add a line: Local honey Saturdays"), [])

    def test_negated_owner_word_is_still_a_hit(self):
        self.assertEqual(self.hits(["Mon–Sat 9–6"], HOURS, "add the honey line, it is not local"),
                         [("store store hours", "local")])

    def test_reordered_lines_add_nothing(self):
        self.assertEqual(self.hits(HOURS, list(reversed(HOURS))), [])

    def test_second_local_line_counts_unless_said(self):
        more = HOURS + ["Local eggs Sundays"]
        self.assertEqual(self.hits(HOURS, more, "add a Sunday eggs line"), [("store store hours", "local")])
        self.assertEqual(self.hits(HOURS, more, "add: Local eggs Sundays"), [])
        self.assertEqual(self.hits(more, HOURS, ""), [])  # removing a claim line is not adding one

    def test_old_value_that_is_not_a_text_list_counts_as_empty(self):
        for old in ("Local honey Saturdays", ["Local honey Saturdays", 3], {"x": "Local"}):
            with self.subTest(old=old):
                self.assertEqual(self.hits(old, HOURS), [("store store hours", "local")])

    def test_list_with_a_non_string_item_and_dict_values_are_skipped(self):
        for new in (["Organic honey", 7], ["Organic honey", None], ["Organic", ["nested organic"]],
                    {"line": "Organic honey"}):
            with self.subTest(new=new):
                self.assertEqual(self.hits([], new), [])

    def test_several_terms_and_terms_in_two_lines(self):
        self.assertEqual([t for _w, t in self.hits([], ["Organic, vegan bakes", "Certified kosher deli"])],
                         ["organic", "certified", "vegan", "kosher"])

    def test_pure_revert_still_skips_and_mixed_revert_checks(self):
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(self.hits(["Mon–Sat 9–6"], HOURS, ops=revert), [])
        self.assertEqual(self.hits(["Mon–Sat 9–6"], HOURS, ops=revert + SET_HOURS), [("store store hours", "local")])

    def test_hike_clear_adds_nothing_but_a_description_change_is_checked(self):
        ops = [{"op": "hike.update", "args": {"id": "h1", "clear": ["description"]}}]
        cleared = {"ops": ops, "records": [{"collection": "events", "key": "h1",
                                            "before": {"title": "Walk", "description": "Local trail"},
                                            "after": {"title": "Walk"}}]}
        self.assertEqual(claims.unstated(cleared, "clear the description", MAKERS), [])
        changed = {"ops": ops, "records": [{"collection": "events", "key": "h1", "before": {"description": "A trail"},
                                            "after": {"description": "Organic orchard trail"}}]}
        self.assertEqual(claims.unstated(changed, "new description", MAKERS), [("events h1 description", "organic")])


class ListConversationTests(ConversationTestCase):
    """The production registry and the writer worktree's store record, as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def set_hours(self, text, lines):
        self.interp.mapping[text] = _ops(("store.set_hours", {"hours": lines}))
        return self.say(text)

    def approve(self, text, lines):
        self.assertEqual(self.set_hours(text, lines), "proposed")
        self.replies()
        self.say("yes")
        self.replies()
        self.assertEqual(self.drafts()[-1]["state"], "applied")
        return self.drafts()[-1]

    def test_unsaid_organic_line_asks_and_writes_no_row(self):
        text = "add a Saturday honey line to the hours"
        self.assertEqual(self.set_hours(text, ["Mon–Sat 9–6", "Organic honey Saturdays"]), "claim-question")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I did not draft that: "), reply)
        self.assertIn('"organic" in store store hours is not in your message', reply)
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_owner_words_propose(self):
        self.assertEqual(self.set_hours("hours: Mon–Sat 9–6, then Organic honey Saturdays",
                                        ["Mon–Sat 9–6", "Organic honey Saturdays"]), "proposed")

    def test_undo_restoring_an_organic_line_is_proposed(self):
        self.approve("hours: Organic honey Saturdays", ["Mon–Sat 9–6", "Organic honey Saturdays"])
        plain = self.approve("hours: Mon–Sat 9–6 only", ["Mon–Sat 9–6"])
        self.assertEqual(self.say(f"undo {plain['code']}"), "proposed")  # AV0007-02: command undo, not interpreter
        self.assertIn("Organic honey Saturdays", self.replies()[0])

    def test_a_product_text_change_is_still_checked(self):
        self.interp.mapping["fix p1"] = _ops(("product.edit", {"id": P1, "description": "Local Hass avocados"}))
        self.assertEqual(self.say("fix p1"), "claim-question")


if __name__ == "__main__":
    unittest.main()
