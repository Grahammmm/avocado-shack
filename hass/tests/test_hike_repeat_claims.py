"""AV1937-05 tests: the words and numbers a hike.repeat copies from a real hike count as the owner's, and nothing else does.

Pure drafts like test_claims_numbers, plus conversation cases on the production registry and the writer worktree.
Run: python3 -B -m unittest hass.tests.test_hike_repeat_claims -v
"""

import copy
import json
import unittest
from unittest import mock

from hass import claims, conversation
from hass.tests.test_claims import MAKERS
from hass.tests.test_conversation import ConversationTestCase, _ops

SRC_ID, NEW_ID = "hike-2027-03-06-cerro-alto-loop", "hike-2027-03-13-cerro-alto-loop"
SOURCE_ARGS = {"title": "Cerro Alto loop", "date": "2027-03-06", "time": "09:00", "meetingPoint": "Test trailhead lot",
               "rsvpEnabled": True, "capacity": 12, "description": "Organic trail snacks on a 5 miles loop.",
               "distance": "5 miles", "duration": "About 3 hours", "accessNote": "Dogs allowed on leash; free parking.",
               "trailId": "idea-cass-hill"}
REPEAT = {"id": SRC_ID, "date": "2027-03-13", "time": "09:00"}
SAY = "same Cerro Alto hike again on March 13 at 9"
SOURCE = {"id": SRC_ID, "title": "Cerro Alto loop", "startsAt": "2027-03-06T09:00:00-08:00", "status": "scheduled",
          "timezone": "America/Los_Angeles", "meetingPoint": "Test trailhead lot", "rsvpEnabled": True, "capacity": 12,
          "description": SOURCE_ARGS["description"], "distance": "5 miles", "duration": "About 3 hours",
          "accessNote": SOURCE_ARGS["accessNote"], "trailId": "idea-cass-hill", "recap": "Organic cookies were great."}
SOURCES = {SRC_ID: SOURCE}


def repeat_draft(**after):
    new = {**{k: v for k, v in SOURCE.items() if k != "recap"}, "id": NEW_ID, "startsAt": "2027-03-13T09:00:00-08:00", **after}
    return {"ops": [{"op": "hike.repeat", "args": dict(REPEAT)}],
            "records": [{"collection": "events", "key": NEW_ID, "before": None, "after": new}]}


def hits(draft, owner=SAY, sources=SOURCES):
    return [(w, t) for w, t in claims.unstated(draft, owner, MAKERS, {}, sources)]


class PureCopyTests(unittest.TestCase):
    def test_copied_words_and_numbers_need_no_owner_words(self):
        self.assertEqual(hits(repeat_draft()), [])
        self.assertEqual(hits(repeat_draft(), owner=""), [])

    def test_the_same_draft_without_a_source_asks(self):
        asked = {("events " + NEW_ID + " description", "organic"), ("events " + NEW_ID + " description", "5 miles")}
        for name, sources in (("none", None), ("empty", {}), ("another hike", {"hike-x": SOURCE}), ("not a dict", [SOURCE])):
            with self.subTest(sources=name):
                found = set(hits(repeat_draft(), sources=sources))
                self.assertTrue(asked <= found, found)
        self.assertTrue(claims.unstated(repeat_draft(), SAY, MAKERS))  # sources default to none

    def test_changed_copied_text_is_checked(self):
        found = hits(repeat_draft(description=SOURCE["description"] + " Vegan lunch."))
        self.assertIn(("events %s description" % NEW_ID, "vegan"), found)
        self.assertIn(("events %s description" % NEW_ID, "organic"), found)  # the whole changed value is no longer a copy
        self.assertIn(("events %s distance" % NEW_ID, "6 miles"), hits(repeat_draft(distance="6 miles")))
        self.assertIn(("events %s accessNote" % NEW_ID, "free parking"), hits(repeat_draft(accessNote="Free parking nearby.")))

    def test_only_allowlisted_fields_are_exempt(self):
        self.assertEqual(hits(repeat_draft(recap="Organic cookies were great.")), [("events %s recap" % NEW_ID, "organic")])
        self.assertIn("recap", claims.EVENT_TEXT_FIELDS)
        self.assertNotIn("recap", claims.REPEAT_FIELDS)
        self.assertEqual(claims.REPEAT_FIELDS[0], "title")

    def test_the_record_must_match_the_repeat_op(self):
        base = repeat_draft()
        cases = {
            "other date": lambda d: d["ops"][0]["args"].update(date="2027-03-14"),
            "other time": lambda d: d["ops"][0]["args"].update(time="10:00"),
            "other source": lambda d: d["ops"][0]["args"].update(id="hike-other"),
            "id not a string": lambda d: d["ops"][0]["args"].update(id=["x"]),
            "date missing": lambda d: d["ops"][0]["args"].pop("date"),
            "args not a dict": lambda d: d["ops"][0].update(args="x"),
            "other op name": lambda d: d["ops"][0].update(op="hike.create"),
            "record key": lambda d: d["records"][0].update(key="hike-2027-03-14-cerro-alto-loop"),
            "record not new": lambda d: d["records"][0].update(before={"title": "x"}),
            "record not events": lambda d: d["records"][0].update(collection="routeIdeas"),
            "status": lambda d: d["records"][0]["after"].update(status="completed"),
            "title differs": lambda d: d["records"][0]["after"].update(title="Another loop"),
            "start differs": lambda d: d["records"][0]["after"].update(startsAt="2027-03-13T10:00:00-08:00"),
            "id differs": lambda d: d["records"][0]["after"].update(id="hike-2027-03-13-other"),
        }
        for name, break_it in cases.items():
            with self.subTest(case=name):
                draft = copy.deepcopy(base)
                break_it(draft)
                self.assertTrue(hits(draft), "no exemption was expected")

    def test_a_repeat_exempts_only_its_own_record(self):
        draft = repeat_draft()
        other = copy.deepcopy(draft["records"][0])
        other.update(key="hike-2027-03-20-other-hike")
        other["after"].update(id="hike-2027-03-20-other-hike", title="Other hike", startsAt="2027-03-20T09:00:00-08:00")
        draft["ops"].append({"op": "hike.create", "args": {}})
        draft["records"].append(other)  # a second hike with the same copied words, made by hike.create
        found = hits(draft)
        self.assertTrue(found and all("hike-2027-03-20-other-hike" in where for where, _t in found), found)

    def test_one_repeat_op_exempts_one_record(self):
        draft = repeat_draft()
        draft["records"].append(copy.deepcopy(draft["records"][0]))  # a second new record for the same repeat
        self.assertTrue(hits(draft))
        draft["ops"].append({"op": "hike.repeat", "args": dict(REPEAT)})  # a second repeat op claims it
        self.assertEqual(hits(draft), [])

    def test_a_later_update_of_the_new_hike_is_still_checked(self):
        draft = repeat_draft()
        update = copy.deepcopy(draft["records"][0])
        update["before"] = copy.deepcopy(update["after"])
        update["after"] = {**update["after"], "description": SOURCE["description"] + " Vegan lunch, 9 miles."}
        draft["ops"].append({"op": "hike.update", "args": {}})
        draft["records"].append(update)
        found = [t for _w, t in hits(draft)]
        self.assertEqual(sorted(found), ["9 miles", "vegan"])

    def test_the_same_check_without_a_repeat_op_is_unchanged(self):
        draft = repeat_draft()
        draft["ops"] = [{"op": "hike.create", "args": {}}]
        self.assertIn(("events %s description" % NEW_ID, "organic"), hits(draft))


class RepeatConversationTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()
        made = self.editor.prepare([{"op": "hike.create", "args": SOURCE_ARGS}])
        self.assertEqual(made["result"], "ok", made)
        self.assertEqual(self.editor.apply(made["draft"]["change_id"], made["draft"]["draft_hash"])["result"], "applied")
        self.interp.mapping[SAY] = _ops(("hike.repeat", REPEAT))

    def ask(self, text, *ops):
        self.interp.mapping[text] = _ops(*ops)
        rows = self.drafts()
        return rows, self.say(text)

    def test_copied_claims_and_numbers_are_stated(self):
        rows, result = [], self.say(SAY)
        self.assertEqual(result, "proposed")
        self.assertEqual(self.replies()[0].count("You didn't say"), 0)
        self.assertEqual(self.drafts()[-1]["summary"], "a new hike: Cerro Alto loop")
        self.assertEqual(self.say("yes"), "approved")
        events = {e["id"]: e for e in json.loads((self.repo.wt / "hass/content/community.json").read_text("utf-8"))["events"]}
        self.assertEqual(events[NEW_ID]["description"], SOURCE_ARGS["description"])
        self.assertEqual(events[NEW_ID]["accessNote"], SOURCE_ARGS["accessNote"])

    def test_the_same_words_in_a_plain_create_still_ask(self):
        rows, result = self.ask("add the same loop again", ("hike.create", {**SOURCE_ARGS, "date": "2027-03-13"}))
        self.assertEqual(result, "claim-question")
        self.assertIn("You didn't say", self.replies()[0])
        self.assertEqual(self.drafts(), rows)

    def test_mixed_draft_and_forged_copy_still_checked(self):
        update = ("hike.update", {"id": NEW_ID, "description": "Organic trail snacks on a 9 miles loop."})
        product = ("product.edit", {"id": "photo-product-001", "description": "Organic and creamy."})
        other = ("hike.create", {**SOURCE_ARGS, "title": "Other loop", "date": "2027-03-20", "trailId": "idea-cass-hill"})
        for name, ops, named in (("later update", (("hike.repeat", REPEAT), update), '"9 miles"'),
                                 ("product edit", (("hike.repeat", REPEAT), product), '"organic"'),
                                 ("another hike create", (("hike.repeat", REPEAT), other), '"dogs allowed" and "free parking"'),
                                 ("create first", (other, ("hike.repeat", REPEAT)), '"dogs allowed" and "free parking"')):
            with self.subTest(case=name):
                rows, result = self.ask(f"mixed {name}", *ops)
                self.assertEqual(result, "claim-question")
                self.assertIn(named, self.replies()[0])
                self.assertEqual(self.drafts(), rows)

    def test_missing_or_unreadable_source_fails_closed(self):
        for name, patch in (("none", mock.patch.object(conversation.Conversation, "_sources", return_value=None)),
                            ("empty", mock.patch.object(conversation.Conversation, "_sources", return_value={}))):
            with self.subTest(source=name), patch:
                rows = self.drafts()
                self.assertEqual(self.say(SAY, pid=f"p-{name}"), "claim-question")
                self.assertEqual(self.drafts(), rows)

    def test_sources_read_from_the_worktree_and_none_when_unreadable(self):
        self.assertEqual(self.conv._sources()[SRC_ID]["description"], SOURCE_ARGS["description"])  # type: ignore[index]
        community = self.repo.wt / "hass" / "content" / "community.json"
        for bad in ("{", json.dumps({"events": "x"}), json.dumps({})):
            with self.subTest(bad=bad):
                community.write_text(bad, "utf-8")
                self.assertIsNone(self.conv._sources())

    def test_an_interpreter_flag_exempts_nothing(self):
        rows, result = self.ask("flagged", ("hike.repeat", {**REPEAT, "copied": True}))
        self.assertEqual(result, "question")  # an unknown argument asks; no draft row exists
        self.assertIn("I can't do that kind of change from chat yet, so nothing changed. Say help to see what I can change.", self.replies()[0])
        self.assertEqual(self.drafts(), rows)


if __name__ == "__main__":
    unittest.main()
