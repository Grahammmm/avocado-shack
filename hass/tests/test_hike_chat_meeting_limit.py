"""RF0211-11: a saved route's trailhead is suggested as the meeting place only when it fits a hike's meeting place.

The suggestion is "<route title> trailhead, <town>"; a hike's meetingPoint holds at most 160 characters (code points). A
longer suggestion would only dead-end: his yes reaches the length refusal and nothing is drafted. So it is not offered, and
he is asked where, with the question that has no suggestion. A suggestion that fits (exactly 160 included) is unchanged.
Run: python3 -m unittest hass.tests.test_hike_chat_meeting_limit -v
"""

import copy
import json
import unittest

from hass import content_model, conversation, hike_chat, voice
from hass.tests import test_chat_scenarios as scen  # module alias: its TestCase classes are not collected here
from hass.tests.test_editor import git

TOWN = "Cambria"
NO_SUGGESTION = "Tell me the spot, like a trailhead or a parking lot."


def title_for(total, town=TOWN):
    """A route title whose complete suggestion is ``total`` code points long."""
    rest = total - len(" trailhead") - (len(", " + town) if town else 0)
    return "Fiscalini Ranch " + "r" * (rest - len("Fiscalini Ranch "))


def create(meeting="Fiscalini Ranch", trail="idea-long"):
    args = {"title": "Fiscalini Ranch hike", "date": "2026-11-08", "time": "10:00", "meetingPoint": meeting, "rsvpEnabled": False}
    if trail:
        args["trailId"] = trail
    return {"op": "hike.create", "args": args}


class SuggestionLimitTests(unittest.TestCase):
    def test_complete_candidate_exactly_at_limit_and_one_over(self):
        self.assertEqual(hike_chat.MEETING_LIMIT, content_model.TEXT_LIMITS["event"]["meetingPoint"])
        for town in (TOWN, None):
            with self.subTest(town=town):
                fits, over = title_for(160, town), title_for(161, town)
                want = f"{fits} trailhead" + (f", {town}" if town else "")
                self.assertEqual(len(want), 160)
                self.assertEqual(hike_chat.suggest_meeting({"title": fits, "place": town}), want)
                self.assertIsNone(hike_chat.suggest_meeting({"title": over, "place": town}))
                shaped = hike_chat.shape([create()], {"idea-long": {"title": over, "place": town}})
                self.assertEqual(shaped.ask["kind"], "meet")
                self.assertIsNone(shaped.ask["suggest"])
                self.assertEqual(shaped.ask["question"], hike_chat.meeting_question("Fiscalini Ranch hike", None))
                self.assertNotIn("Reply yes", shaped.ask["question"])
                good = hike_chat.shape([create()], {"idea-long": {"title": fits, "place": town}})
                self.assertEqual((good.ask["suggest"], good.ask["question"]),
                                 (want, hike_chat.meeting_question("Fiscalini Ranch hike", want)))

    def test_non_ascii_uses_code_points_not_utf8_bytes(self):
        title = "Fiscalini Ranch é😀 " + "é" * (160 - len(" trailhead, Cambria") - len("Fiscalini Ranch é😀 "))
        want = f"{title} trailhead, {TOWN}"
        self.assertEqual(len(want), 160)
        self.assertGreater(len(want.encode("utf-8")), 160)
        self.assertEqual(hike_chat.suggest_meeting({"title": f"  {title}  ", "place": f" {TOWN} "}), want)
        self.assertIsNone(hike_chat.suggest_meeting({"title": title + "é", "place": TOWN}))

    def test_long_town_counts_and_no_component_is_silently_dropped(self):
        self.assertIsNone(hike_chat.suggest_meeting({"title": "Cass Hill", "place": "C" * 140}))
        self.assertIsNone(hike_chat.suggest_meeting({"title": title_for(161, None)}))
        for place in (None, "", "   ", 7):
            with self.subTest(place=place):
                self.assertEqual(hike_chat.suggest_meeting({"title": "Cass Hill", "place": place}), "Cass Hill trailhead")
        self.assertEqual(hike_chat.suggest_meeting({"title": "Cass Hill", "place": TOWN}), "Cass Hill trailhead, Cambria")

    def test_ask_retains_call_identity_and_input_values(self):
        routes = {"idea-long": {"title": title_for(161), "place": TOWN}}
        ops = [{"op": "product.set_availability", "args": {"id": "p", "available": "no"}}, create("Cass Hill trailhead", None), create()]
        before = (copy.deepcopy(ops), copy.deepcopy(routes))
        shaped = hike_chat.shape(ops, routes)
        self.assertEqual((ops, routes), before)
        self.assertEqual((shaped.ask["index"], shaped.ask["suggest"]), (2, None))
        self.assertEqual(shaped.ops[1]["args"]["meetingPoint"], "Cass Hill trailhead")
        self.assertEqual(shaped.ops[2]["args"]["meetingPoint"], "Fiscalini Ranch")
        off = hike_chat.shape(ops, routes, live=False)
        self.assertIsNone(off.ask)
        self.assertEqual(off.ops, ops)


class ConversationLimitTests(scen.ScenarioCase):
    """The live conversation with the route idea's title made long in the throwaway writer (one seed commit, before counting)."""

    def seed(self, title):
        path = self.repo.wt / "hass" / "content" / "community.json"
        data = json.loads(path.read_text("utf-8"))
        [route] = [r for r in data["routeIdeas"] if r["id"] == "idea-fiscalini-bluff"]
        route["title"] = title
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
        problems = []
        content_model.validate_community(problems, {k: v for k, v in data.items() if k != "schemaVersion"})
        self.assertEqual(problems, [])  # a valid saved route: only the generated suggestion is too long
        git(self.repo.wt, "commit", "-q", "-am", "seed long route title")
        self.base, self.head = self.count(), self.repo.head()

    def ask(self):
        self.interp.mapping["Fiscalini hike Sunday 10am"] = {"ops": [create("Fiscalini", "idea-fiscalini-bluff")], "revises": None}
        self.assertEqual(self.say("Fiscalini hike Sunday 10am"), "question")
        return [voice.plain(r) for r in self.replies()]

    def test_real_overlong_suggestion_never_invites_impossible_yes(self):
        self.seed(title_for(161))
        self.assertEqual(self.ask(), ["Where should people meet for Fiscalini Ranch hike? " + NO_SUGGESTION])
        self.assertEqual(self.say("yes"), "question")  # a bare yes installs nothing: he is asked where
        self.assertEqual([voice.plain(r) for r in self.replies()], [voice.plain(conversation.MEET_NO)])
        self.assertEqual((self.drafts(), self.commits(), self.repo.head()), ([], 0, self.head))
        place = "The bench at the end of Windsor Blvd"
        self.interp.mapping[place] = {"ops": [create(place, "idea-fiscalini-bluff")], "revises": None}
        self.assertEqual(self.say(place), "proposed")
        self.assertIn(f"the meeting place: {place}", "\n".join(voice.plain(r) for r in self.replies()))
        self.assertEqual([d["state"] for d in self.drafts()], ["proposed"])
        self.assertEqual((self.commits(), self.repo.head()), (0, self.head))  # named approval still needed

    def confirm(self, title):
        want = f"{title} trailhead, {TOWN}"
        self.assertEqual(self.ask(), [voice.plain(hike_chat.meeting_question("Fiscalini Ranch hike", want))])
        self.assertEqual(self.say("yes"), "proposed")
        self.assertIn(f"the meeting place: {want}", "\n".join(voice.plain(r) for r in self.replies()))
        self.assertEqual([d["state"] for d in self.drafts()], ["proposed"])
        self.assertEqual(self.commits(), 0)  # nothing written before his named approval

    def test_real_fitting_suggestion_still_confirms_to_draft(self):
        self.confirm("Fiscalini Ranch")

    def test_real_suggestion_exactly_at_the_limit_confirms_to_draft(self):
        self.seed(title_for(160))
        self.confirm(title_for(160))


if __name__ == "__main__":
    unittest.main()
