"""AV0022-11 tests: a hike or route draft that adds an access or safety term the owner did not say asks, never drafts.

Pure draft dicts like test_claims_grades, plus one conversation case on the production registry.
Run: python3 -m unittest hass.tests.test_claims_access -v
"""

import unittest

from hass import claims, conversation, voice
from hass.tests.test_claims import MAKERS, edit
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_hike_ops import HIKE, HIKE_ID

POST = "post the Cass Hill hike Saturday 9am"
NOTE = "Dogs welcome, no permit needed"


class AccessTermTests(unittest.TestCase):
    def hits(self, before, after, owner="", **kw):
        kw.setdefault("collection", "events")
        kw.setdefault("field", "accessNote")
        return [term for _w, term in claims.unstated(edit(before, after, **kw), owner, MAKERS)]

    def test_unsaid_note_names_both_terms_in_the_question(self):
        hits = claims.unstated(edit(None, NOTE, collection="events", key="h1", field="accessNote"), POST, MAKERS)
        self.assertEqual(hits, [("events h1 accessNote", "dogs welcome"), ("events h1 accessNote", "no permit needed")])
        q = claims.question(hits)
        self.assertIn('You didn\'t say "dogs welcome" and "no permit needed" in your message. Are they true?', voice.plain(q))

    def test_longest_term_only_and_owner_words_clear_each(self):
        self.assertEqual(self.hits(None, NOTE, "dogs welcome on this one"), ["no permit needed"])
        self.assertEqual(self.hits(None, NOTE, "dogs welcome, no permit needed"), [])
        self.assertEqual(self.hits(None, "No permit needed", "no permit needed"), [])
        self.assertEqual(self.hits(None, "No permit needed", "no permit"), ["no permit needed"])  # shorter is not it
        self.assertEqual(self.hits(None, "No permit", "no permit needed"), [])
        self.assertEqual(self.hits(None, "No permit"), ["no permit"])
        self.assertEqual(self.hits(None, NOTE, "not dogs welcome. no permit needed"), ["dogs welcome"])  # negated

    def test_hyphen_space_case_and_typographic_forms_match(self):
        for after in ("Dog-Friendly", "dog friendly", "DOG\u2011FRIENDLY", "Dog  Friendly"):
            with self.subTest(after=after):
                self.assertEqual(self.hits(None, after), ["dog friendly"])
                self.assertEqual(self.hits(None, after, "it is dog-friendly"), [])
        self.assertEqual(self.hits(None, "WHEELCHAIR ACCESSIBLE"), ["wheelchair accessible"])

    def test_whole_words_only(self):
        for after in ("wheelchair accessibility", "restroomsy", "Not open to the publicity", "free parkings"):
            with self.subTest(after=after):
                self.assertEqual(self.hits(None, after), [])

    def test_counts_compare_with_the_text_before(self):
        self.assertEqual(self.hits("Free parking.", "Free parking. Bring water."), [])
        self.assertEqual(self.hits("Free parking.", "Free parking, free-parking."), ["free parking"])
        self.assertEqual(self.hits("Free parking.", "Bring water."), [])  # removing is not adding
        self.assertEqual(self.hits("No permit needed.", "No permit needed, no permit."), ["no permit"])

    def test_only_events_and_route_ideas_are_gated(self):
        self.assertEqual(self.hits("", "dog friendly treats", collection="products", field="description"), [])
        self.assertEqual(self.hits("", "Organic and dog friendly", collection="products", field="description"),
                         ["organic"])
        self.assertEqual(self.hits("", "restrooms", collection="makers", field="story"), [])
        self.assertEqual(self.hits("", "restrooms", collection="events", field="description"), ["restrooms"])

    def test_route_idea_terrain_hits_and_a_revert_does_not(self):
        kw = {"collection": "routeIdeas", "field": "terrain", "key": "idea-cass-hill"}
        self.assertEqual(self.hits("Dirt trail", "Dirt trail, wheelchair accessible", **kw), ["wheelchair accessible"])
        self.assertEqual(self.hits("Dirt trail", "Dirt trail, wheelchair accessible", "wheelchair accessible", **kw), [])
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(self.hits("Dirt trail", "Dirt trail, wheelchair accessible", ops=revert, **kw), [])


class AccessConversationTests(ConversationTestCase):
    """The production registry and the writer worktree's content, as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def hike(self):
        self.interp.mapping[POST] = _ops(("hike.create", HIKE))
        self.assertEqual(self.say(POST), "proposed")
        self.say("yes")
        self.replies()
        self.assertEqual(self.drafts()[-1]["state"], "applied")

    def test_update_adding_unsaid_access_terms_asks_and_writes_no_row(self):
        self.hike()
        rows, commits = self.drafts(), self.commits()
        text = "tell people about the hike"
        self.interp.mapping[text] = _ops(("hike.update", {"id": HIKE_ID, "accessNote": NOTE}))
        self.assertEqual(self.say(text), "claim-question")
        [reply] = self.replies()
        self.assertIn('"dogs welcome" and "no permit needed" in your message. Are they true?', reply)
        self.assertEqual((self.drafts(), self.commits()), (rows, commits))

    def test_route_edit_adding_unsaid_terrain_claim_asks(self):
        text = "describe the terrain of Cass Hill"
        self.interp.mapping[text] = _ops(("route.edit", {"id": "idea-cass-hill", "terrain": "Dirt, wheelchair accessible"}))
        rows = self.drafts()
        self.assertEqual(self.say(text), "claim-question")
        self.assertIn('"wheelchair accessible" in your message. Is that true?', self.replies()[0])
        self.assertEqual(self.drafts(), rows)

    def test_owner_words_still_propose(self):
        self.hike()
        text = "accessNote: Dogs welcome, no permit needed"
        self.interp.mapping[text] = _ops(("hike.update", {"id": HIKE_ID, "accessNote": NOTE}))
        self.assertEqual(self.say(text), "proposed")


if __name__ == "__main__":
    unittest.main()
