"""RF0834-10: hike and trail names match on whole words, so 'Ridge' can never pick 'Bridge Walk'.

Run: python3 -m unittest hass.tests.test_skill_title_boundaries -v
"""
import copy
import json
import unittest
from types import SimpleNamespace

from hass.skills import hikes, kinds
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import SkillCase, skill_reply

RESOLVERS = (("hike", kinds.hike_ref, "events"), ("trail", kinds.route_ref, "routeIdeas"))


def content(key, *titles):
    return SimpleNamespace(community={key: [{"id": f"r{i}", "title": t} for i, t in enumerate(titles)]})


class ResolverTests(unittest.TestCase):
    def test_inner_word_is_not_a_hike_or_route_name(self):
        for label, fn, key in RESOLVERS:
            for titles, query in ((("Bridge Walk",), "ridge"), (("Bridge Walk",), "Ridge Walk"),
                                  (("Creekside Loop",), "creek"), (("Creekside Loop",), "side loop"),
                                  (("Soak Trail",), "oak")):
                with self.subTest(label=label, query=query, titles=titles):
                    c = content(key, *titles)
                    before = copy.deepcopy(c.community)
                    r = fn(c, query)
                    self.assertEqual((r.status, r.value, r.ids), ("none", None, ()))
                    self.assertEqual(r.reply, f"I don't know a {label} called that. What is it called?")
                    self.assertEqual(c.community, before)  # the resolver reads, never edits

    def test_real_word_partial_titles_keep_normalization(self):
        for label, fn, key in RESOLVERS:
            c = content(key, "Peña Ridge Walk", "Bridges of Mill Creek", "Moonstone Beach-Loop")
            for query, want in (("Peña Ridge Walk", "r0"), ("ridge", "r0"), ("PENA RIDGE", "r0"), ("the ridge walk!", "r0"),
                                ("bridge", "r1"), ("Bridges", "r1"), ("bridge of mill", "r1"), ("mill creek", "r1"),
                                ("beach loop", "r2"), ("moonstone, beach", "r2")):
                with self.subTest(label=label, query=query):
                    r = fn(c, query)
                    self.assertEqual((r.status, r.value), ("one", want))
            with self.subTest(label=label, query="walk ridge"):  # word order still counts
                self.assertEqual(fn(c, "walk ridge").status, "none")

    def test_true_matches_and_display_cap_do_not_invent_uniqueness(self):
        for label, fn, key in RESOLVERS:
            with self.subTest(label=label, case="ridge beside bridge"):
                r = fn(content(key, "Bridge Walk", "Ridge Walk"), "Ridge")
                self.assertEqual((r.status, r.value), ("one", "r1"))
                r = fn(content(key, "Bridge Walk", "Ridge Walk"), "ridge walk")
                self.assertEqual((r.status, r.value), ("one", "r1"))
            with self.subTest(label=label, case="two true matches"):
                r = fn(content(key, "Ridge Walk", "Bridge Walk", "Ridge Loop"), "ridge")
                self.assertEqual((r.status, r.value, r.ids, r.candidates), ("several", None, ("r0", "r2"), ("Ridge Walk", "Ridge Loop")))
                self.assertEqual(r.reply, f"Which {label} do you mean: Ridge Walk or Ridge Loop?")
            with self.subTest(label=label, case="more than the cap"):
                titles = [f"Ridge Walk {n}" for n in range(kinds.MAX_CANDIDATES + 2)]
                r = fn(content(key, "Bridge Walk", *titles), "ridge walk")
                self.assertEqual(r.status, "several")
                self.assertEqual(r.ids, tuple(f"r{i}" for i in range(1, kinds.MAX_CANDIDATES + 1)))
                self.assertEqual(r.candidates, tuple(titles[:kinds.MAX_CANDIDATES]))
            for query in ("", "   ", "the of and", "!!"):
                with self.subTest(label=label, query=query):
                    r = fn(content(key, "The Walk"), query)
                    self.assertEqual((r.status, r.reply), ("none", f"Which {label} do you mean?"))


def event(eid, title, day):
    return dict(id=eid, title=title, startsAt=f"{day}T09:00:00-08:00", timezone="America/Los_Angeles", status="scheduled",
                meetingPoint="the gate", rsvpEnabled=False)


BRIDGE = event("hike-2026-11-21-bridge-walk", "Bridge Walk", "2026-11-21")
RIDGE = event("hike-2026-11-22-ridge-walk", "Ridge Walk", "2026-11-22")


class ProductionCancelTests(SkillCase):
    SKILLS = (hikes.CANCEL,)

    def seed(self, *events):
        path = self.repo.wt / "hass/content/community.json"
        community = json.loads(path.read_text())
        community["events"] = list(events)
        path.write_text(json.dumps(community) + "\n")
        git(self.repo.wt, "add", "hass/content/community.json")
        git(self.repo.wt, "commit", "-q", "-s", "-m", "synthetic hikes")
        self.base = self.count()

    def cancel(self, name):
        text = f"cancel the {name} hike"
        self.script(text, skill_reply("hike.cancel", hike=name))
        return self.say(text)

    def drafted_ops(self):
        [draft] = self.drafts()
        return json.loads(draft["ops_json"])

    def test_production_cancel_does_not_propose_the_inner_word_match(self):
        self.seed(BRIDGE)
        self.assertNotEqual(self.cancel("Ridge"), "proposed")
        replies = self.replies()
        self.assertTrue(any("I don't know a hike called that" in r for r in replies), replies)
        self.assertFalse(any("Bridge Walk" in r for r in replies), replies)
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_production_cancel_of_the_named_hike_proposes_only_that_id(self):
        self.seed(BRIDGE)
        self.assertEqual(self.cancel("Bridge"), "proposed")
        self.assertEqual(self.drafted_ops(), [{"op": "hike.cancel", "args": {"id": BRIDGE["id"]}}])
        self.nothing_written()  # still only a proposal until the owner says yes

    def test_production_cancel_of_ridge_beside_bridge_picks_ridge_without_asking(self):
        self.seed(BRIDGE, RIDGE)
        self.assertEqual(self.cancel("Ridge"), "proposed")
        self.assertEqual(self.drafted_ops(), [{"op": "hike.cancel", "args": {"id": RIDGE["id"]}}])
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
