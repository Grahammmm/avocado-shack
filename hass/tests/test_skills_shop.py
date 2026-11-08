"""SKILLS-SHOP-1: the shop and page skills (hass/skills/shop.py, hass/skills/pages.py).

The rows themselves (plan golden and case runs through the real Conversation, Editor, sitegen and claims) are run for every
skill by test_skills_plans and test_skills_cases from hass/tests/fixtures/skills/{shop,pages}. This module adds what those
generic runners cannot say: the lint with the case files, every rule id mapped to a named function, the hours rules on
their own, the live class derived from the real live policy, the home photo end to end (set, undo, put back) with a stored
photo, and plain words in every reply the plans can give.
Run: python3 -B -m unittest hass.tests.test_skills_shop -v
"""

import json
import types
import unittest
from datetime import timedelta

from hass import live_policy, voice
from hass.content_model import DEFAULT_HEADLINE, REPO_ROOT, shop_today
from hass.ops import load_registry
from hass.skills import load_skills, pages, shop, skill_lint, testkit
from hass.skills.backlog import REASONS
from hass.tests.test_set_photo import FIXTURES, PhotoRepo, _req

MINE = ("shop.hours", "shop.notice", "shop.contact", "page.home", "page.about", "page.photo")
CHECKS = {"shop.hours": shop.HOURS_CHECKS, "shop.notice": shop.NOTICE_CHECKS, "shop.contact": shop.CONTACT_CHECKS,
          "page.home": pages.HOME_CHECKS, "page.about": pages.ABOUT_CHECKS, "page.photo": pages.PHOTO_CHECKS}
H0 = ["Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday"]
SHA = "a" * 64
GOLDEN = {
    "shop.hours": [{"hours": ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–5pm · Closed Sunday"]}],
    "shop.notice": [{"text": "Closed Thursday", "until": "2026-11-12"}, {"clear": True}],
    "shop.contact": [{"phone": "805 555 0100"}, {"clear": True}, {"street_address": "1023 Example Street", "town": "Morro Bay"}],
    "page.home": [{"headline": ["Fresh from the coast.", "Picked this week."], "intro": "Come by for lunch."}, {"reset": "intro"}],
    "page.about": [{"story": "A market with a person behind it."}, {"reset": True}],
    "page.photo": [{"photo": SHA, "image_alt": "the shop front on a sunny morning"}, {"clear": True}],
}


def mine():
    reg = load_skills()
    return [reg.skills[n] for n in MINE]


def ctx_for(**kw):
    return types.SimpleNamespace(today="2026-11-08", **kw)


class RegistryAndLint(unittest.TestCase):
    def test_the_six_skills_are_in_the_registry_and_the_whole_registry_lints_clean(self):
        reg = load_skills()
        self.assertTrue(set(MINE) <= set(reg.skills))
        self.assertEqual(skill_lint(reg, load_registry()), [])

    def test_my_skills_lint_clean_with_their_case_files_and_golden_plans(self):
        problems = skill_lint(mine(), load_registry(), repo_root=REPO_ROOT, golden=GOLDEN)
        # FW-1's case-file lint wants a row marked `undo`, which the kit's row format (TK-1) does not allow: the kit undoes
        # every row that ends in a draft by itself (test_the_kit_runs_every_row_of_the_six_files). Everything else must be clean.
        self.assertEqual([p for p in problems if "at least 1 undo row" not in p], [])

    def test_every_golden_plan_works_with_no_context_at_all(self):
        for skill in mine():
            for slots in GOLDEN[skill.name]:
                with self.subTest(skill=skill.name, slots=slots):
                    self.assertTrue(skill.plan(dict(slots), None))

    def test_every_rule_id_is_a_named_function(self):
        for skill in mine():
            with self.subTest(skill=skill.name):
                self.assertEqual(set(skill.rules), set(CHECKS[skill.name]))
                for rule, fn in CHECKS[skill.name].items():
                    self.assertTrue(callable(fn) and fn.__doc__, rule)

    def test_the_cases_files_are_where_the_skills_say_and_hold_plan_and_case_rows(self):
        for skill in mine():
            rows = testkit.load_rows(REPO_ROOT / skill.cases)
            with self.subTest(skill=skill.name):
                self.assertGreaterEqual(sum(1 for r in rows if not r.get("plan")), 4)
                self.assertGreaterEqual(sum(1 for r in rows if r.get("plan")), 8)
                self.assertTrue({"refuse"} <= {r.get("kind") for r in rows})

    def test_the_kit_runs_every_row_of_the_six_files(self):
        skills = testkit.registry_skills()
        for skill in mine():
            with self.subTest(skill=skill.name):
                results = testkit.run_file(REPO_ROOT / skill.cases, skills)
                self.assertTrue(results)
                self.assertEqual([(r.id, r.problems) for r in results if not r.ok], [])

    def test_a_group_has_the_skills_the_spec_names_and_nothing_owns_page_faq_twice(self):
        reg = load_skills()
        self.assertEqual({n for n in reg.skills if n.startswith(("shop.", "page."))} - {"page.faq"}, set(MINE))


class HoursRules(unittest.TestCase):
    def test_days_the_owner_names(self):
        said = shop.days_in_text
        self.assertEqual(said("we're open till 7 on fridays now"), {4})
        self.assertEqual(said("Mon to Sat 9 to 5"), {0, 1, 2, 3, 4, 5})
        self.assertEqual(said("Monday-Friday and sunday"), {0, 1, 2, 3, 4, 6})
        self.assertEqual(said("weekdays 8 to 5"), {0, 1, 2, 3, 4})
        self.assertEqual(said("closed weekends"), {5, 6})
        self.assertEqual(said("winter hours every day"), set(range(7)))
        self.assertEqual(said("open 7 days a week"), set(range(7)))
        self.assertEqual(said("fri through mon"), {4, 5, 6, 0})
        self.assertEqual(said("a sunny morning on Main Street"), set())
        self.assertEqual(said("thurs and tues"), {1, 3})

    def test_one_line_of_hours_by_day(self):
        by_day, opaque = shop.hours_by_day(H0)
        self.assertEqual(opaque, [])
        self.assertEqual({d: v for d, v in by_day.items() if d in (4, 5, 6)}, {4: ["9am–6pm"], 5: ["9am–5pm"], 6: ["closed"]})
        by_day, opaque = shop.hours_by_day(["Daily 10am–4pm", "Open late on market nights"])
        self.assertEqual(sorted(by_day), list(range(7)))
        self.assertEqual(opaque, ["Open late on market nights"])
        self.assertEqual(shop.parse_segment("Closed Mon, Tue & Wed"), ({0, 1, 2}, "closed"))
        self.assertIsNone(shop.parse_segment("Come in for lunch"))
        self.assertIsNone(shop.parse_segment("Friday"))

    def test_day_names_in_plain_words(self):
        self.assertEqual(shop.day_names({5}), "Saturday")
        self.assertEqual(shop.day_names({0, 1, 2, 3}), "Monday to Thursday")
        self.assertEqual(shop.day_names({0, 2}), "Monday and Wednesday")
        self.assertEqual(shop.day_names({0, 2, 4}), "Monday, Wednesday and Friday")

    def untouched(self, new, said, store=None):
        ctx = ctx_for(store=store or {"hours": H0}, texts=said)
        return shop.check_hours_untouched({"hours": new}, said, ctx)

    def test_a_day_he_did_not_name_keeps_its_line(self):
        good = ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", H0[1]]
        self.assertIsNone(self.untouched(good, ["open till 7 on fridays"]))
        stop = self.untouched(["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–6pm · Closed Sunday"], ["open till 7 on fridays"])
        self.assertIsNotNone(stop)
        self.assertEqual((stop.kind, stop.reply), ("question", "Do you want Saturday to stay 9am–5pm?"))
        self.assertIsNone(self.untouched(["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–6pm · Closed Sunday"], ["fri till 7 and saturday 9 to 6"]))

    def test_without_his_words_or_the_saved_hours_the_rule_does_not_judge(self):
        new = ["Monday–Friday 9am–7pm"]
        self.assertIsNone(shop.check_hours_untouched({"hours": new}, [], ctx_for(store={"hours": H0})))
        self.assertIsNone(shop.check_hours_untouched({"hours": new}, ["x"], None))
        self.assertIsNone(shop.check_hours_untouched({"hours": new}, ["x"], ctx_for()))

    def test_a_line_that_names_no_day_is_kept_or_asked_about(self):
        store = {"hours": ["Monday–Friday 9am–6pm", "Open late on market nights"]}
        stop = self.untouched(["Monday–Friday 9am–7pm"], ["fridays till 7"], store)
        self.assertIsNotNone(stop)
        self.assertIn("Open late on market nights", stop.reply)
        self.assertIsNone(self.untouched(["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Open late on market nights"], ["fridays till 7"], store))

    def test_the_stop_carries_what_the_dispatcher_needs(self):
        for slots, ctx in (({"hours": []}, None), ({"hours": ["Monday–Sunday 9am–6pm", "Monday–Friday 8am–5pm"]}, None)):
            with self.assertRaises(shop.SkillStop) as caught:
                shop.plan_hours(slots, ctx)
            self.assertEqual(caught.exception.kind, "question")
            self.assertEqual(str(caught.exception), caught.exception.reply)
        with self.assertRaises(shop.SkillStop) as caught:
            shop.plan_hours({"hours": ["Eggs $2 all day"]}, None)
        self.assertEqual((caught.exception.kind, caught.exception.reason), ("refused", "price"))
        self.assertIn(caught.exception.reason, REASONS)

    def test_plans_never_change_what_they_are_given(self):
        slots = {"hours": ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", H0[1]]}
        before = json.loads(json.dumps(slots))
        shop.plan_hours(slots, ctx_for(store={"hours": H0}, texts=["fridays till 7"]))
        self.assertEqual(slots, before)


class NoticeRules(unittest.TestCase):
    def test_today_to_sixty_days_ahead_and_not_a_day_more(self):
        for until, ok in (("2026-11-08", True), ("2027-01-07", True), ("2027-01-08", False), ("2026-11-07", False)):
            with self.subTest(until=until):
                try:
                    shop.plan_notice({"text": "Closed for the winter", "until": until}, ctx_for())
                    self.assertTrue(ok)
                except shop.SkillStop as stop:
                    self.assertFalse(ok)
                    self.assertEqual(stop.kind, "refused" if until > "2026-12" else "question")

    def test_today_may_arrive_as_a_date_a_string_or_a_clock(self):
        from datetime import date, datetime, timezone
        for today in (date(2026, 11, 8), "2026-11-08", datetime(2026, 11, 8, 12, tzinfo=timezone.utc)):
            with self.subTest(today=repr(today)):
                ctx = types.SimpleNamespace(today=today)
                self.assertTrue(shop.plan_notice({"text": "Closed Friday", "until": "2026-11-13"}, ctx))
        ctx = types.SimpleNamespace(now=datetime(2026, 11, 8, 12, tzinfo=timezone.utc))
        self.assertEqual(shop.today_of(ctx), date(2026, 11, 8))

    def test_prices_and_deals_are_refused_and_logged_as_a_price(self):
        for text in ("All produce 20% off", "Eggs $3", "Big sale on Friday", "Half price lemons", "Avocados 2 for a dollar", "Honey per lb today"):
            with self.subTest(text=text):
                with self.assertRaises(shop.SkillStop) as caught:
                    shop.plan_notice({"text": text, "until": "2026-11-20"}, ctx_for())
                self.assertEqual((caught.exception.kind, caught.exception.reason), ("refused", "price"))
        for fine in ("Closed Thursday for deliveries", "Drop off your crates at the side door", "Parking is behind the store", "We turned the heat off"):
            with self.subTest(fine=fine):
                self.assertTrue(shop.plan_notice({"text": fine, "until": "2026-11-20"}, ctx_for()))


class LiveClass(unittest.TestCase):
    """live_class is what live_policy.check says about the golden plans (spec 2.2): contact is private-only, the rest chat-live."""

    @classmethod
    def setUpClass(cls):
        cls.repo = PhotoRepo()
        cls.photo = cls.repo.store((FIXTURES / "pixel.jpg").read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.repo.cleanup()

    def reasons(self, ops):
        out = self.repo.prepare(_req(*[(o["op"], o["args"]) for o in ops]))
        self.assertEqual(out["result"], "ok", out)
        return live_policy.check({"ops": ops, "records": out["draft"]["records"]})

    def golden(self, name):
        until = (shop_today() + timedelta(days=5)).isoformat()
        slots = {"shop.notice": {"text": "Closed Thursday", "until": until},
                 "page.photo": {"photo": self.photo, "image_alt": "the shop front on a sunny morning"}}
        return slots.get(name) or GOLDEN[name][0]

    def test_each_skill_has_the_class_the_policy_gives_its_golden_plan(self):
        for skill in mine():
            ops = skill.plan(self.golden(skill.name), None)
            reasons = self.reasons(ops)
            with self.subTest(skill=skill.name, reasons=reasons):
                self.assertEqual("private-only" if reasons else "chat-live", skill.live_class)

    def test_contact_is_protected_because_of_its_operations(self):
        ops = shop.plan_contact({"phone": "805 555 0123", "street_address": "1023 Example Street"}, None)
        self.assertEqual(self.reasons(ops), ["protected operation: store.set_address", "protected operation: store.set_phone"])

    def test_a_notice_with_a_phone_number_or_a_claim_is_drafted_but_not_for_a_live_release(self):
        until = (shop_today() + timedelta(days=5)).isoformat()
        for text, kind in (("Call 805 555 0100 for orders", "contact"), ("Certified organic produce Friday", "origin/organic")):
            with self.subTest(text=text):
                self.assertIn("protected sentences: " + kind, self.reasons(shop.plan_notice({"text": text, "until": until}, None)))

    def test_undoing_any_of_them_is_never_protected(self):
        self.assertEqual(live_policy.check({"ops": [{"op": "history.revert", "args": {}}], "records": []}), [])


class HomePhotoEndToEnd(unittest.TestCase):
    """The home photo with a real stored photo: set, undo, put the shop's own photo back, undo that (the kit has no photo rows yet)."""

    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.sha = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())

    def store(self):
        return json.loads(self.repo.read("hass/content/store.json"))

    def run_plan(self, skill, slots):
        ops = skill.plan(slots, ctx_for(store=self.store()))
        return self.repo.run(*[(o["op"], o["args"]) for o in ops])

    def test_set_then_undo_keeps_the_file_and_shows_the_shops_own_photo(self):
        start, index = self.store(), self.repo.read("storefront-mockup/index.html")
        change = self.run_plan(pages.PAGE_PHOTO, {"photo": self.sha, "image_alt": "the shop front on a sunny morning"})
        home = self.store()["homeImage"]
        self.assertEqual(home["image"], f"assets/products/photo-{self.sha[:16]}.jpg")
        self.assertEqual(home["imageAlt"], "the shop front on a sunny morning")
        self.repo.run(("history.revert", {"changeId": change["change_id"]}))
        self.assertEqual(self.store(), start)
        self.assertEqual(self.repo.read("storefront-mockup/index.html"), index)
        self.assertTrue((self.repo.wt / "storefront-mockup" / home["image"]).is_file())  # the declared residue: the file stays
        self.assertEqual(self.repo.status(), "")

    def test_put_the_old_photo_back_and_undo_of_that(self):
        self.run_plan(pages.PAGE_PHOTO, {"photo": self.sha, "image_alt": "the shop front on a sunny morning"})
        with_photo = self.store()
        change = self.run_plan(pages.PAGE_PHOTO, {"clear": True})
        self.assertNotIn("homeImage", self.store())
        self.repo.run(("history.revert", {"changeId": change["change_id"]}))
        self.assertEqual(self.store(), with_photo)
        with self.assertRaises(shop.SkillStop):  # no photo of his: nothing to put back
            pages.PAGE_PHOTO.plan({"clear": True}, ctx_for(store={k: v for k, v in with_photo.items() if k != "homeImage"}))

    def test_the_skills_own_refusals_match_what_the_photo_op_refuses(self):
        for alt in ("IMG_1234", "IMG_1234.jpg", "photo", "a", "Screenshot 2026-11-08"):
            with self.subTest(alt=alt):
                with self.assertRaises(shop.SkillStop):
                    pages.PAGE_PHOTO.plan({"photo": self.sha, "image_alt": alt}, None)
                out = self.repo.prepare(_req(("store.set_home_image", {"photo": self.sha, "imageAlt": alt})))
                self.assertEqual(out["result"], "refused")


class PlainWords(unittest.TestCase):
    """Every reply a plan can give, and every fixed refusal a skill declares, follows docs/hass/VOICE.md (hass/voice.py)."""

    def replies(self):
        out = []
        for skill in mine():
            out += [(skill.name + " refuse", reply) for _cond, reply in skill.refuse]
            for row in testkit.load_rows(REPO_ROOT / skill.cases):
                if not row.get("plan") or "expect_error" not in row:
                    continue
                ctx = types.SimpleNamespace(**{"today": "2026-11-08", **(row.get("ctx") or {})})
                with self.assertRaises(shop.SkillStop) as caught:
                    skill.plan(json.loads(json.dumps(row["slots"])), ctx)
                out.append((f"{skill.name} {row['id']}", caught.exception.reply))
        return out

    def test_replies_pass_the_voice_check(self):
        found = self.replies()
        self.assertGreater(len(found), 60)
        for label, reply in found:
            with self.subTest(label):
                self.assertEqual(voice.check(reply), [])
                self.assertEqual(testkit.plain_words_problems(reply), [])

    def test_a_refusal_never_claims_a_change_was_made(self):
        for label, reply in self.replies():
            with self.subTest(label):
                self.assertFalse(voice.claims_success(reply), reply)


class PagesRules(unittest.TestCase):
    def test_reset_writes_the_shipped_words_and_nothing_when_they_are_already_there(self):
        self.assertEqual(pages.plan_home({"reset": "headline"}, ctx_for(store={"headline": ["A", "B C"]})),
                         [{"op": "store.set_headline", "args": {"first": DEFAULT_HEADLINE[0], "second": DEFAULT_HEADLINE[1]}}])
        with self.assertRaises(shop.SkillStop):
            pages.plan_home({"reset": "headline"}, ctx_for(store={}))
        with self.assertRaises(shop.SkillStop):
            pages.plan_home({"reset": "headline"}, ctx_for(store={"headline": list(DEFAULT_HEADLINE)}))

    def test_a_boast_must_be_his_own_word_and_organic_is_left_to_the_claims_gate(self):
        said = ctx_for(store={}, texts=["rewrite it", "we are the best"])
        self.assertTrue(pages.plan_about({"story": "We are the best at finding good food."}, said))
        with self.assertRaises(shop.SkillStop) as caught:
            pages.plan_about({"story": "We are the best at finding good food."}, ctx_for(store={}, texts=["rewrite it"]))
        self.assertEqual(caught.exception.kind, "question")
        self.assertTrue(pages.plan_about({"story": "Organic avocados from our friends nearby."}, ctx_for(store={}, texts=["x"])))  # hass/claims.py asks for that

    def test_the_story_is_one_paragraph_of_at_most_the_limit(self):
        for story in ("First part of the story is here.\n\nSecond part is here.", "x y " * 120):
            with self.subTest(story=story[:20]):
                with self.assertRaises(shop.SkillStop):
                    pages.plan_about({"story": story}, None)


if __name__ == "__main__":
    unittest.main()
