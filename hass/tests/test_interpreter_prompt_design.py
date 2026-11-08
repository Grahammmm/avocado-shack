"""AV1102-08 (H24/H05) tests: a design request (layout, colours, fonts, new section or page) is answered `unsupported`.

The interpreter prompt carries one rule built from DESIGN_UNSUPPORTED; the conversation passes the model's `unsupported`
text to the owner as written (no draft, one counted call) and content edits are proposed as before. No model call.
Run: python3 -B -m unittest hass.tests.test_interpreter_prompt_design -v
"""

import json
import re
import unittest

from hass import conversation
from hass.interpreter_prompt import DESIGN_UNSUPPORTED, PROMPT_MAX_BYTES, RULES, build
from hass.tests.test_conversation import SETTINGS, ConversationTestCase
from hass.tests.test_interpreter_prompt import FIXTURE, TEST_REGISTRY, tiny_content

DESIGN = {"unsupported": DESIGN_UNSUPPORTED}
REQUESTS = ("make the header green", "use a bigger font", "add a new Gift Cards page", "move the hours above the intro")


def _rules(prompt):
    block = prompt.split("Rules:\n", 1)[1].split("\n\nOperations", 1)[0]
    return block.splitlines()


class PromptRuleTests(unittest.TestCase):
    def test_rule_precedes_notes_once_and_its_reply_is_json(self):
        prompt = build(TEST_REGISTRY, tiny_content())
        rules = _rules(prompt)
        design = [line for line in rules if "design change" in line]
        self.assertEqual(len(design), 1)
        self.assertEqual(rules[-4], design[0])  # before the notes, voice and aliases rules
        self.assertIn("product.set_photo", rules[-7])
        self.assertIn('"missing" list', rules[-6])
        self.assertIn("hike.repeat", rules[-5])
        self.assertIn('"notes"', rules[-3])
        self.assertIn("Mike", rules[-2])
        self.assertIn('"aliases"', rules[-1])
        self.assertEqual(prompt.count(DESIGN_UNSUPPORTED), 1)
        found = re.search(r"\{\"unsupported\": \"[^\"]*\"\}", design[0])
        self.assertEqual(json.loads(found.group(0)), DESIGN)
        for words in ("layout", "colours", "fonts", "page structure", "new section or page", "words, hours, photos, hikes"):
            self.assertIn(words, design[0])

    def test_rule_matches_the_snapshot_and_stays_small(self):
        prompt = build(TEST_REGISTRY, tiny_content())
        self.assertEqual(prompt, FIXTURE.read_text("utf-8"))
        without = prompt.replace("- " + RULES[-4] + "\n", "", 1)
        self.assertNotEqual(without, prompt)
        self.assertNotIn(DESIGN_UNSUPPORTED, without)
        self.assertEqual(len(RULES), 29)  # Original prompt rule count; changes beyond wording need review.
        self.assertLess(len(RULES[-4].encode("utf-8")), 300)
        self.assertLess(len(prompt.encode("utf-8")), PROMPT_MAX_BYTES)

    def test_empty_catalog_and_store_still_build(self):
        empty = tiny_content(products=[], makers={})
        prompt = build(TEST_REGISTRY, empty)
        self.assertEqual(prompt.count(DESIGN_UNSUPPORTED), 1)
        self.assertLess(len(prompt.encode("utf-8")), PROMPT_MAX_BYTES)


class DesignConversationTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "interpreterDailyCap": 5})
        mapping = {text: dict(DESIGN) for text in REQUESTS}
        mapping["change the intro to 'Fresh every Saturday'"] = {
            "ops": [{"op": "store.set_intro", "args": {"text": "Fresh every Saturday"}}], "revises": None}
        self.interp = conversation.FixtureInterpreter({**self.interp.mapping, **mapping})
        self.editor = conversation.Editor(self.repo.state)  # production ops registry: store.set_intro exists
        self.conv = self.open()

    def calls(self):
        return self.conv.db.execute("SELECT COALESCE(SUM(calls), 0) FROM usage").fetchone()[0] \
            if self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'usage'").fetchone() else 0

    def test_design_requests_get_the_fixed_reply_and_no_draft(self):
        for number, text in enumerate(REQUESTS, 1):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "unsupported")
                self.assertEqual(self.replies(), [DESIGN_UNSUPPORTED])
                self.assertEqual((len(self.drafts()), self.commits(), self.calls()), (0, 0, number))

    def test_a_design_reply_does_not_block_a_later_content_edit(self):
        self.assertEqual(self.say("make the header green"), "unsupported")
        self.assertEqual(self.replies(), [DESIGN_UNSUPPORTED])
        self.assertEqual(self.say("change the intro to 'Fresh every Saturday'"), "proposed")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Here's the change I'd make:\n"), reply)
        [draft] = self.drafts()
        self.assertEqual(draft["state"], "proposed")
        self.assertEqual(json.loads(draft["ops_json"])[0]["op"], "store.set_intro")
        self.assertEqual((self.commits(), self.calls()), (0, 2))

    def test_content_edit_is_proposed_as_before_and_applies_on_yes(self):
        self.assertEqual(self.say("change the intro to 'Fresh every Saturday'"), "proposed")
        self.replies()
        self.assertEqual(self.say("yes"), "approved")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Saved: "), reply)
        self.assertEqual(self.commits(), 1)

    def test_a_design_reply_leaves_a_pending_draft_alone(self):
        self.assertEqual(self.say("change the intro to 'Fresh every Saturday'"), "proposed")
        self.replies()
        self.assertEqual(self.say("use a bigger font"), "unsupported")
        self.assertEqual(self.replies(), [DESIGN_UNSUPPORTED])
        [draft] = self.drafts()
        self.assertEqual(draft["state"], "proposed")  # the pending draft is neither cancelled nor replaced


if __name__ == "__main__":
    unittest.main()
