"""RF1925-12: a trail that is hidden is a named refusal ("restore it first"), never a route id a hike can link to.

Run: python3 -B -m unittest hass.tests.test_skill_hidden_route -v
"""
import copy
import dataclasses
import json
import types
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from hass import voice
from hass.skills import dispatch, hikes, kinds
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import SATURDAY, SkillCase, registry_of

PST = timezone(timedelta(hours=-8))
CLOSED = {"id": "idea-closed-loop", "title": "Closed Loop", "status": "hidden"}
OPEN = {"id": "idea-open-loop", "title": "Open Loop", "status": "idea"}
LEGACY = {"id": "idea-old-trail", "title": "Old Trail"}  # no status at all: older fixtures keep working
REPLY = "Closed Loop is hidden. Do you want me to bring it back first?"


def content(*routes):
    return SimpleNamespace(community={"routeIdeas": copy.deepcopy(list(routes)), "events": []})


class ResolverTests(unittest.TestCase):
    def test_hidden_route_is_a_named_refusal_not_a_value(self):
        c = content(CLOSED, OPEN)
        before = copy.deepcopy(c.community)
        for query in ("Closed Loop", "closed loop", "CLOSED  LOOP!", "closed"):
            with self.subTest(query=query):
                r = kinds.route_ref(c, query)
                self.assertEqual((r.status, r.value, r.ids, r.candidates), ("hidden", None, (), ()))
                self.assertEqual(r.reply, REPLY)
                self.assertNotIn("idea-closed-loop", r.reply)
                self.assertEqual(voice.check(r.reply), [])
        self.assertEqual(c.community, before)  # the resolver reads, never edits

    def test_accent_folded_title_is_named_as_written(self):
        r = kinds.route_ref(content({"id": "idea-pena", "title": "Peña Loop", "status": "hidden"}), "PENA loop")
        self.assertEqual((r.status, r.value), ("hidden", None))
        self.assertEqual(r.reply, "Peña Loop is hidden. Do you want me to bring it back first?")

    def test_visible_and_legacy_status_routes_preserve_resolution(self):
        c = content(CLOSED, OPEN, LEGACY)
        for query, want in (("Open Loop", "idea-open-loop"), ("old trail", "idea-old-trail")):
            with self.subTest(query=query):
                r = kinds.route_ref(c, query)
                self.assertEqual((r.status, r.value, r.reply), ("one", want, ""))
        for query, reply in (("Nowhere", "I don't know a trail called that. What is it called?"), ("", "Which trail do you mean?"),
                             ("osed", "I don't know a trail called that. What is it called?")):
            with self.subTest(query=query):
                r = kinds.route_ref(c, query)
                self.assertEqual((r.status, r.value, r.reply), ("none", None, reply))

    def test_mixed_hidden_visible_matches_never_invent_uniqueness(self):
        c = content(CLOSED, OPEN)
        r = kinds.route_ref(c, "Loop")
        self.assertEqual((r.status, r.value, r.ids, r.candidates),
                         ("several", None, ("idea-closed-loop", "idea-open-loop"), ("Closed Loop", "Open Loop")))
        self.assertEqual(r.reply, "Which trail do you mean: Closed Loop or Open Loop?")
        two_hidden = content(CLOSED, {**CLOSED, "id": "idea-closed-ridge", "title": "Closed Ridge"})
        r = kinds.route_ref(two_hidden, "closed")
        self.assertEqual((r.status, r.value, r.candidates), ("several", None, ("Closed Loop", "Closed Ridge")))
        many = content(*({**CLOSED, "id": f"idea-h{n}", "title": f"Hidden Walk {n}"} for n in range(kinds.MAX_CANDIDATES + 2)))
        r = kinds.route_ref(many, "hidden walk")
        self.assertEqual((r.status, len(r.ids)), ("several", kinds.MAX_CANDIDATES))
        # a fresh, unique title is still refused
        self.assertEqual(kinds.route_ref(c, "closed loop").status, "hidden")


class ValidateTests(unittest.TestCase):
    TEXT = "add the Harbor Walk hike on 2026-11-14 at 9:00, meet at the gate, link it to Closed Loop"

    def ctx(self, *routes):
        return types.SimpleNamespace(today="2026-11-08", now=datetime(2026, 11, 8, 9, 0, tzinfo=PST), texts=[self.TEXT],
                                     content=content(*routes), aliases={})

    def slots(self, trail):
        return {"title": "Harbor Walk", "day": "2026-11-14", "clock": "09:00", "meeting_point": "the gate", "trail": trail}

    def test_validate_marks_hidden_trail_refused_without_keeping_id(self):
        out = dispatch.validate(hikes.ADD, {}, self.slots("Closed Loop"), [self.TEXT], self.ctx(CLOSED, OPEN))
        self.assertEqual((out.refused, out.refused_status, out.problem, out.problem_slot), (REPLY, "hidden", REPLY, "trail"))
        self.assertNotIn("trail", out.slots)
        self.assertEqual(out.slots["title"], "Harbor Walk")  # every other valid value is still kept
        self.assertNotIn("idea-closed-loop", json.dumps(out.slots))

    def test_validate_keeps_a_visible_trail_id(self):
        out = dispatch.validate(hikes.ADD, {}, self.slots("Open Loop"), [self.TEXT], self.ctx(CLOSED, OPEN))
        self.assertEqual((out.refused, out.problem), (None, None))
        self.assertEqual(out.slots["trail"], "idea-open-loop")


class ProductionDispatchTests(SkillCase):
    """The real hike.add declaration through the real Conversation, dispatcher and Editor, with a spy on its plan."""
    SKILLS = (hikes.ADD,)
    TEXT = "add the Harbor Walk hike Saturday at 9am, meet at the gate, link it to the trail"

    def setUp(self):
        super().setUp()
        self.plans = []

        def spy(slots, ctx):
            self.plans.append(dict(slots))
            return hikes.plan_add(slots, ctx)

        self.registry = registry_of(dataclasses.replace(hikes.ADD, plan=spy))
        self.conv = self.open()

    def seed(self, hide):
        path = self.repo.wt / "hass/content/community.json"
        community = json.loads(path.read_text())
        for route in community["routeIdeas"]:
            route["status"] = "hidden" if route["id"] in hide else "idea"
        path.write_text(json.dumps(community) + "\n")
        git(self.repo.wt, "add", "hass/content/community.json")
        git(self.repo.wt, "commit", "-q", "-s", "-m", "synthetic hidden route")
        self.base = self.count()

    def slots(self, trail):
        return {"title": "Harbor Walk", "day": SATURDAY, "clock": "09:00", "meeting_point": "the gate", "trail": trail}

    def test_production_hike_add_stops_before_plan_for_hidden_route(self):
        self.seed({"idea-cass-hill"})
        for n, reply in enumerate(({"skill": "hike.add", "slots": self.slots("Cass Hill")},
                                   {"calls": [{"skill": "hike.add", "slots": self.slots("cass hill")}]})):
            with self.subTest(shape=("single", "calls")[n]):
                text = f"{self.TEXT} {n}"
                self.script(text, {**reply, "revises": None})
                self.assertNotEqual(self.say(text), "proposed")
                said = "\n".join(self.replies())
                self.assertIn("Cass Hill is hidden. Do you want me to bring it back first?", said)
                self.assertNotIn("idea-cass-hill", said)
                self.assertEqual(self.plans, [])  # the plan was never called
                self.assertEqual(self.drafts(), [])
                self.nothing_written()
                self.say("never mind")

    def test_visible_route_control_proposes_link_without_mutation(self):
        self.seed({"idea-cass-hill"})
        self.script(self.TEXT, {"skill": "hike.add", "slots": self.slots("Point Buchon"), "revises": None})
        self.assertEqual(self.say(self.TEXT), "proposed")
        self.assertEqual(len(self.plans), 1)
        [draft] = self.drafts()
        ops = json.loads(draft["ops_json"])
        self.assertEqual([op["op"] for op in ops], ["hike.create"])
        self.assertEqual(ops[0]["args"]["trailId"], "idea-point-buchon")
        self.nothing_written()  # still only a proposal until the owner says yes
        routes = json.loads((self.repo.wt / "hass/content/community.json").read_text())["routeIdeas"]
        self.assertEqual({r["id"]: r["status"] for r in routes}["idea-cass-hill"], "hidden")  # nothing restored


if __name__ == "__main__":
    unittest.main()
