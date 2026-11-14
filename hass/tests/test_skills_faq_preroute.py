"""RF2345-12: explicit fresh FAQ-page requests are refused and logged by code before any model call (SKILLS-SPEC 3.26)."""
from __future__ import annotations

import unittest
from dataclasses import replace

from hass import voice
from hass.skills import backlog
from hass.skills.backlog import NO_FAQ, PAGE_FAQ, explicit_page_request
from hass.tests.test_conversation import CHAT, SETTINGS, STRANGER
from hass.tests.test_skill_dispatch import HIKE_ADD, SkillCase, registry_of, skill_reply

# Keep the old pre-route contract covered for an explicitly active historical fixture.
# Production PAGE_FAQ is retired; the current registry is exercised by test_front_pages.
PAGE_FAQ = replace(PAGE_FAQ, status="active")

POSITIVE = ("FAQ", "add an FAQ", "Add a FAQ.", "FAQ: what are your hours? Nine to five", "frequently asked questions",
            "please add a frequently asked questions page", "add a questions page!", "  add a   delivery policy page?  ",
            "please FAQ: do you deliver? no", "Please   FAQ: hours? nine", "please FAQ", "please add an FAQ.")
NEGATIVE = ("add to the about text that we're closed Sundays", "intro: FAQ coming soon", "don't add an FAQ", "remove the FAQ",
            '"add an FAQ"', "what is an FAQ?", "add an FAQs", "addanFAQ", "add FAQ and change the hours", "FAQ:", "please FAQ:", "please", "",
            "update the delivery policy notice", "add a page")


class FaqPrerouteCase(SkillCase):
    SKILLS = (HIKE_ADD, PAGE_FAQ)

    def rows(self):
        return [tuple(r) for r in self.conv.db.execute("SELECT id, reason, text FROM backlog ORDER BY id")] \
            if self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'backlog'").fetchone() else []


class ClassifierTests(unittest.TestCase):
    def test_finite_grammar(self):
        for t in POSITIVE:
            self.assertTrue(explicit_page_request(t), t)
        for t in NEGATIVE:
            self.assertFalse(explicit_page_request(t), t)
        for t in (None, 5, b"faq", ["faq"]):
            self.assertFalse(explicit_page_request(t))


class PrerouteTests(FaqPrerouteCase):
    def test_explicit_fresh_forms_log_without_interpreter(self):
        for mode in ("both", "skills-first"):
            for n, text in enumerate(POSITIVE):
                with self.subTest(mode=mode, text=text):
                    self.MODE = mode
                    self.setUp()
                    self.assertEqual(self.say(text), "backlog")
                    [(i, reason, stored)] = self.rows()
                    self.assertEqual((reason, stored), ("unsupported-page", text))
                    self.assertEqual(self.replies(), [f"{NO_FAQ} I can't do that yet. I wrote it down as request #{i}. Nothing on the site changed."])
                    self.assertEqual(self.asked, [])
                    self.nothing_written()
        self.MODE = "both"

    def test_cap_exhaustion_does_not_block_code_only_refusal(self):
        self.set_settings({**SETTINGS, "skills": {"mode": "both"}, "interpreterDailyCap": 1})
        self.conv = self.open()
        self.script("order eggs", {"skill": "none", "summary": "eggs"})
        self.say("order eggs")  # uses the one model call of the day
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(self.say("add an FAQ"), "backlog")
        self.assertEqual([r[1] for r in self.rows()], ["other", "unsupported-page"])
        self.assertEqual(len(self.asked), 1)

    def test_off_mode_keeps_its_route(self):
        self.set_settings({**SETTINGS, "skills": {"mode": "ops-only"}})
        self.conv = self.open()
        self.say("add an FAQ")
        self.assertEqual(self.rows(), [])

    def test_non_matching_goes_to_the_model(self):
        self.script("add to the about text that we're closed Sundays", {"skill": "none", "summary": "x"})
        self.say("add to the about text that we're closed Sundays")
        self.assertEqual(len(self.asked), 1)

    def test_open_request_keeps_its_route(self):
        self.script("add a hike Saturday, Mill Creek trailhead, easy", skill_reply("hike.add", title="Mill", place="Mill Creek", day="2026-11-07", difficulty="easy"))
        self.say("add a hike Saturday, Mill Creek trailhead, easy")
        before = self.live()
        self.assertIsNotNone(before)
        self.script("FAQ", {"skill": "none", "summary": "faq"})
        self.say("FAQ")
        self.assertEqual([r for r in self.rows() if r[1] == "unsupported-page"], [])
        self.assertEqual(self.live()["request_id"], before["request_id"]) if self.live() else None

    def test_duplicate_and_foreign_messages_log_at_most_once(self):
        self.assertEqual(self.say("add an FAQ", pid="dup"), "backlog")
        self.say("add an FAQ", pid="dup")
        self.say("add an FAQ", sender=STRANGER)
        self.say("add an FAQ", from_me=True)
        self.say("add an FAQ", chat="other@g.us")
        self.say("add an FAQ", kind="edit")
        self.assertEqual(len(self.rows()), 1)

    def test_retired_page_faq_does_not_preroute(self):
        self.registry = registry_of(HIKE_ADD)
        self.conv = self.open()
        self.script("add an FAQ", {"skill": "none", "summary": "faq"})
        self.say("add an FAQ")
        self.assertEqual(len(self.asked), 1)

    def test_model_picked_page_faq_is_unchanged(self):
        self.script("put up a page of common questions", skill_reply("page.faq"))
        self.assertEqual(self.say("put up a page of common questions"), "backlog")
        [(i, reason, _t)] = self.rows()
        self.assertEqual(reason, "unsupported-page")
        self.assertEqual(self.say(f"forget backlog.{i}"), "backlog-forgot")
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
