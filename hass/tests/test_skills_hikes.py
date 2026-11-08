"""SKILLS-HIKES-1 tests: the six hike skills, their rules, the D8 line, the post-hike announcement and the live boundary.

The case rows (hass/tests/fixtures/skills/hikes/*.jsonl) are run by the generic runners test_skills_plans and test_skills_cases
(the real Conversation, Editor, sitegen and claims on a scratch worktree, undo to the start state). This module adds what a
row cannot show: the declaration of each skill, every rule on its own, the three live texts and the E2E-HIKE-1 text being
fixtures, guest warnings and the guest-count refusal with a real RSVP file, the editor-level apply of a recap, the live
policy class each skill declares, the announcement draft, the dispatcher hand-off, and the kit's new `seed`.
Run: python3 -B -m unittest hass.tests.test_skills_hikes -v
"""
import json
import sys
import types
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from hass import live_policy, voice
from hass.content_model import REPO_ROOT
from hass.ops import load_registry
from hass.skills import hikes, load_skills, skill_lint, testkit
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase, _req

PST = timezone(timedelta(hours=-8))
FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "skills" / "hikes"
NAMES = ("hike.add", "hike.edit", "hike.reschedule", "hike.cancel", "hike.repeat", "hike.recap")
LIVE1 = "add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water"
LIVE2 = "Fiscalini Ranch"
LIVE3 = "create a new hike on Fiscalini Ranch this Saturday at 8am, easy, bring water"
E2E1A_START = "Add a hike: Montaña de Oro Sunrise Walk, Saturday December 5th at 8am."


def ev(id_, title, starts, status="scheduled", **extra):
    return {"id": id_, "title": title, "startsAt": starts, "timezone": "America/Los_Angeles", "status": status,
            "meetingPoint": "the gate", "rsvpEnabled": False, **extra}


CASS = ev("hike-2026-11-21-cass-hill", "Cass Hill", "2026-11-21T09:00:00-08:00")
DONE = ev("hike-2026-10-24-cass-hill", "Cass Hill", "2026-10-24T09:00:00-07:00", "completed", recap="Great morning.")
CALLED = ev("hike-2026-11-15-dune-walk", "Dune Walk", "2026-11-15T10:00:00-08:00", "cancelled")
NOW = datetime(2026, 11, 8, 9, 0, tzinfo=PST)


def ctx(*events, now=NOW, texts=(), today="2026-11-08"):
    return types.SimpleNamespace(today=today, now=now, texts=list(texts), content={"community": {"events": list(events), "routeIdeas": [
        {"id": "idea-fiscalini-bluff", "title": "Fiscalini Ranch Bluff"}]}})


def rows_of(name):
    return testkit.load_rows(FIX / f"{name}.jsonl")


class Declaration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_skills()
        cls.skills = {n: cls.registry.get(n) for n in NAMES}

    def test_the_six_skills_are_in_the_registry_and_lint_clean(self):
        self.assertTrue(all(self.skills.values()))
        self.assertEqual(skill_lint(self.registry, load_registry()), [])

    def test_each_skill_has_ten_example_sentences_with_every_kind(self):
        for name, skill in self.skills.items():
            with self.subTest(name):
                self.assertEqual(len(skill.triggers), 10)
                self.assertTrue({"vague", "typo", "multi"} <= {t.tag for t in skill.triggers})

    def test_only_hike_ops_are_planned_and_the_declarations_match_the_spec(self):
        by = self.skills
        self.assertEqual({n: s.live_class for n, s in by.items()},
                         {"hike.add": "private-only", "hike.edit": "private-only", "hike.reschedule": "chat-live",
                          "hike.cancel": "chat-live", "hike.repeat": "private-only", "hike.recap": "chat-live"})
        for skill in by.values():
            self.assertEqual((skill.approval, skill.preview, skill.undo.mode, skill.version), ("owner-yes", "hike", "revert", 1))
            self.assertTrue(all(f in ("hass/content/community.json", "storefront-mockup/community.json") for f, _ in skill.edits))
        self.assertIn("cancelled", by["hike.add"].undo.residue)  # undo of an add cancels: the hike stays on the page
        self.assertIn("cancelled", by["hike.repeat"].undo.residue)

    def test_every_rule_id_has_a_function_and_every_reply_is_in_plain_words(self):
        for skill in self.skills.values():
            for rule in skill.rules:
                self.assertIn(rule, hikes.RULES)
            for _why, reply in skill.refuse:
                self.assertEqual(voice.check(reply), [], reply)
        for const in ("R_PRICE", "R_PAST_DAY", "R_PAST_TIME", "R_FAR", "R_WHAT_MOVE", "R_SIGNUP_NOT_SAID", "R_SIGNUP_UNCLEAR", "R_SPOTS_NOT_SAID", "R_NO_RECAP_YET"):
            self.assertEqual(voice.check(getattr(hikes, const)), [], const)

    def test_slot_asks_are_one_short_question_and_the_ops_get_their_own_argument_names(self):
        for skill in self.skills.values():
            for slot in skill.slots:
                self.assertEqual(slot.name, slot.name.lower())
                if slot.required:
                    self.assertTrue(slot.ask.endswith("?") and len(slot.ask.split()) <= 14, slot.ask)
        plan = hikes.plan_add({"title": "T", "day": "2026-11-14", "clock": "08:00", "meeting_point": "the gate", "access_note": "No dogs"}, ctx())
        self.assertEqual(plan[0]["args"]["meetingPoint"], "the gate")
        self.assertEqual(plan[0]["args"]["accessNote"], "No dogs")


class Fixtures(unittest.TestCase):
    def test_every_skill_has_a_cases_file_that_meets_the_bar(self):
        registry = load_skills()
        for name in NAMES:
            skill = registry.get(name)
            rows = rows_of(name)
            with self.subTest(name):
                self.assertEqual(str(skill.cases), f"hass/tests/fixtures/skills/hikes/{name}.jsonl")
                self.assertGreaterEqual(len(rows), 10)
                self.assertGreaterEqual(sum(1 for r in rows if r.get("kind") == "refuse"), 2)
                # the kit undoes every approved draft row: at least one must run through approve and undo
                self.assertGreaterEqual(sum(1 for r in rows if not r.get("plan") and r["expect"].get("diff") and r.get("approve") is not False), 1)
                self.assertTrue(all(r.get("version", 1) == skill.version for r in rows))

    def test_the_three_live_texts_and_the_e2e_text_are_fixtures(self):
        texts = {t for r in rows_of("hike.add") if not r.get("plan") for t in r["texts"]}
        self.assertTrue({LIVE1, LIVE2, LIVE3} <= texts)
        self.assertTrue(any(t.startswith(E2E1A_START) for t in texts))
        sequence = next(r for r in rows_of("hike.add") if r["id"] == "live-sequence-ends-in-a-draft")
        self.assertEqual(sequence["texts"], [LIVE1, LIVE2, LIVE3])
        self.assertEqual(sequence["expect"]["dispositions"], ["proposed", "question", "proposed"])  # ends in a draft, not a question

    def test_the_invented_capacity_case_has_a_row_that_must_be_refused_and_one_that_drafts_without_it(self):
        rows = {r["id"]: r for r in rows_of("hike.add")}
        refused = rows["e2e-1a-invented-signup-and-capacity-are-refused"]
        self.assertEqual(refused["replies"][0]["slots"]["capacity"], 10)  # what the model invented on 2026-11-08
        self.assertEqual(refused["expect"]["disposition"], "unsupported")
        clean = rows["e2e-1a-clean-draft-has-no-invented-fields"]["expect"]
        self.assertNotIn("capacity", clean["diff"][0]["after"])
        self.assertIs(clean["diff"][0]["after"]["rsvpEnabled"], False)

    def test_every_recorded_row_changes_the_hike_its_words_name_on_the_day_they_name(self):
        """Review round 2: a row must not advertise a successful change to another hike or day than the one the owner asked about."""
        import difflib
        import re
        unnamed = {"hike.recap": {"complete-with-his-words"}}  # "recap: 12 people, great morning" names no hike (the spec sentence); the seed holds exactly one candidate
        weekdays = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        checked = 0
        for name in NAMES:
            for row in rows_of(name):
                if row.get("plan"):
                    continue
                seeded = {e["id"]: e for e in ((row.get("seed") or {}).get("community") or {}).get("events", [])}
                words = re.findall(r"[a-z]+", " ".join(row["texts"]).lower())
                for reply in row["replies"]:
                    for call in ([reply] + reply.get("calls", [])):
                        slots = call.get("slots") or {}
                        event = seeded.get(slots.get("hike"))
                        with self.subTest(f"{name} {row['id']}"):
                            if slots.get("hike"):
                                self.assertIsNotNone(event, "the row changes a hike that is not in its seed")
                                if row["id"] not in unnamed.get(name, ()):
                                    title = [w for w in re.findall(r"[a-z]+", event["title"].lower()) if len(w) > 3]
                                    near = any(difflib.SequenceMatcher(None, t, w).ratio() >= 0.8 for t in title for w in words)
                                    dated = re.search(r"\b(%s)[a-z]*\s+(\d{1,2})\b" % "|".join(months), " ".join(row["texts"]).lower())
                                    start = datetime.fromisoformat(event["startsAt"])
                                    on_day = bool(dated) and (months[dated.group(1)], int(dated.group(2))) == (start.month, start.day)
                                    self.assertTrue(near or on_day, f"the words {row['texts']} do not name the hike {event['title']!r} ({event['startsAt'][:10]})")
                                    checked += 1
                            if slots.get("day"):
                                said = [weekdays[w] for w in words if w in weekdays]
                                if said:
                                    self.assertIn(date.fromisoformat(slots["day"]).weekday(), said, f"{slots['day']} is not the weekday he said")
        self.assertGreater(checked, 30)

    def test_the_rows_say_which_hike_each_text_is_about(self):
        by = {r["id"]: r for r in rows_of("hike.cancel")}
        row = by["no-note"]
        self.assertIn("Morro Rock", row["texts"][0])
        self.assertEqual(row["replies"][0]["slots"]["hike"], "hike-2026-12-05-morro-rock-beach-stroll")
        self.assertEqual(row["expect"]["preview"]["title"], "Morro Rock Beach Stroll")
        self.assertNotIn("weekend", " ".join(t for r in rows_of("hike.cancel") for t in r.get("texts", [])))  # the kit's clock is a Sunday: "this weekend" names nothing fixed
        recap = {r["id"]: r for r in rows_of("hike.recap")}["refuse-not-started-yet"]
        self.assertEqual(recap["replies"][0]["slots"]["hike"], "hike-2026-12-19-cass-hill")

    def test_every_skill_has_its_own_plan_rows_too(self):
        for name in NAMES:
            plan_rows = [r for r in rows_of(name) if r.get("plan")]
            self.assertGreaterEqual(len(plan_rows), 4, name)  # level 2 (the generic runner runs them)


class Defaults(unittest.TestCase):
    def test_sign_up_is_off_and_says_so(self):
        out = hikes.plan_add({"title": "T", "day": "2026-11-14", "clock": "08:00", "meeting_point": "the gate"}, ctx())
        self.assertIs(out[0]["args"]["rsvpEnabled"], False)
        self.assertNotIn("capacity", out[0]["args"])
        phrases = hikes.SET_PHRASES["hike.add"]({"title": "T", "day": "2026-11-14", "clock": "08:00", "meeting_point": "the gate"}, ctx())
        self.assertEqual(hikes.set_line(phrases), "I set: sign-up off.")
        named = hikes.SET_PHRASES["hike.add"]({"day": "2026-11-14", "clock": "08:00", "meeting_point": "Mill Creek trailhead"}, ctx())
        self.assertEqual(named[0], "sign-up off")  # sign-up first: the line starts with the D8 words
        self.assertEqual(voice.check(hikes.set_line(named)), [])
        self.assertEqual(hikes.SET_PHRASES["hike.add"]({"title": "T", "signup": True}, ctx()), [])  # he said it: nothing was chosen for him
        self.assertEqual(hikes.SET_PHRASES["hike.add"]({"title": "T", "signup": False}, ctx()), [])
        self.assertIsNone(hikes.set_line([]))
        self.assertEqual(hikes.set_line(["sign-up off", "sign-up off"]), "I set: sign-up off.")  # two hikes in one message: said once

    def test_the_owner_reply_of_a_real_draft_carries_the_line_through_the_kit(self):
        """End to end on the scratch world: the real Conversation proposal text, with the line put there by the kit's stand-in
        dispatcher from hikes.SET_PHRASES (the same hand-off the real dispatcher is asked to make)."""
        text = "Add Cass Hill hike December 12 at 8am, meet at Cass Hill gate"
        slots = {"title": "Cass Hill hike", "day": "2026-12-12", "clock": "08:00", "meeting_point": "Cass Hill gate"}
        skills = {s.name: s for s in testkit.registry_skills()}
        seen = {}
        for label, said, given in (("ordinary", text, slots), ("sign-up said", text + ", sign-up on, 15 spots", {**slots, "signup": True, "capacity": 15}),
                                   ("sign-up said off", text + ", sign-up off", {**slots, "signup": False})):
            sc = testkit.Scratch({said: {"skill": "hike.add", "slots": given}}, skills)
            try:
                disposition, out = sc.say(said)
            finally:
                sc.close()
            self.assertEqual(disposition, "proposed", label)
            seen[label] = out[0]
        self.assertTrue(seen["ordinary"].startswith("I set: sign-up off.\n"), seen["ordinary"])
        self.assertIn("whether guests can sign up: no", seen["ordinary"])
        self.assertNotIn("I set:", seen["sign-up said"])
        self.assertNotIn("I set:", seen["sign-up said off"])

    def test_spots_are_written_only_with_sign_up_and_only_as_given(self):
        base = {"title": "T", "day": "2026-11-14", "clock": "08:00", "meeting_point": "the gate"}
        self.assertNotIn("capacity", hikes.plan_add({**base, "capacity": 12}, ctx())[0]["args"])  # E2E-HIKE-1: never invented
        self.assertNotIn("noCapacityLimit", hikes.plan_add({**base, "no_limit": True}, ctx())[0]["args"])
        on = hikes.plan_add({**base, "signup": True, "capacity": 12}, ctx())[0]["args"]
        self.assertEqual((on["rsvpEnabled"], on["capacity"]), (True, 12))
        self.assertEqual(hikes.plan_add({**base, "signup": True}, ctx())[0]["args"],
                         {"title": "T", "date": "2026-11-14", "time": "08:00", "meetingPoint": "the gate", "rsvpEnabled": True})  # the editor asks how many

    def test_facts_are_kept_exactly_as_written_and_never_filled_in(self):
        args = hikes.plan_add({"title": "T", "day": "2026-11-14", "clock": "08:00", "meeting_point": "the gate", "difficulty": "Easy-ish ",
                               "bring": "water"}, ctx())[0]["args"]
        self.assertEqual((args["difficulty"], args["bring"]), ("Easy-ish", "water"))
        for absent in ("distance", "duration", "accessNote", "description", "trailId", "capacity"):
            self.assertNotIn(absent, args)

    def test_the_title_comes_from_the_place_when_he_named_no_title(self):
        for meeting, title in (("Mill Creek trailhead", "Mill Creek hike"), ("the Cass Hill gate", "Cass Hill hike"), ("Fiscalini Ranch", "Fiscalini Ranch hike"),
                               ("Cayucos Pier", "Cayucos Pier hike"), ("Spooners Cove parking lot", "Spooners Cove hike")):
            self.assertEqual(hikes.place_title({"meeting_point": meeting}, ctx()), title)
        self.assertIsNone(hikes.place_title({"meeting_point": "the gate"}, ctx()))  # a place with no name: ask
        self.assertIsNone(hikes.place_title({}, ctx()))
        self.assertEqual(hikes.place_title({"meeting_point": "x", "trail": "idea-fiscalini-bluff"}, ctx()), "Fiscalini Ranch Bluff hike")
        self.assertIsNone(hikes.place_title({"meeting_point": "y" * 90}, ctx()))
        self.assertIn("place_title", hikes.DERIVERS)


class Rules(unittest.TestCase):
    def hit(self, rule, slots, c=None, texts=()):
        return hikes.RULES[rule](slots, texts, c or ctx(CASS, DONE, CALLED))

    def test_a_start_in_the_past_or_too_far_away(self):
        self.assertIn("already passed", self.hit("hike-in-future", {"day": "2026-11-07", "clock": "09:00"})[0])
        self.assertIn("already passed", hikes.R_PAST_DAY)
        self.assertEqual(self.hit("hike-in-future", {"day": "2026-11-08", "clock": "08:00"})[0], hikes.R_PAST_TIME)  # today, 9:00 now
        self.assertIsNone(self.hit("hike-in-future", {"day": "2026-11-08", "clock": "10:00"}))
        self.assertEqual(self.hit("hike-in-future", {"day": "2028-01-01", "clock": "10:00"})[0], hikes.R_FAR)
        self.assertIsNone(self.hit("hike-in-future", {"day": "2026-12-01", "clock": "10:00"}))
        self.assertIsNone(self.hit("hike-in-future", {"hike": CASS["id"]}))  # nothing is being moved: nothing to check
        self.assertEqual(self.hit("hike-in-future", {"hike": CASS["id"], "clock": "07:00", "day": "2026-11-08"})[0], hikes.R_PAST_TIME)
        self.assertIsNone(hikes.RULES["hike-in-future"]({"day": "2026-11-07"}, (), types.SimpleNamespace()))  # no clock known: no verdict

    def test_a_twin_has_the_same_day_and_title_and_is_scheduled(self):
        reply = self.hit("hike-twin", {"title": "cass  HILL", "day": "2026-11-21"})[0]
        self.assertIn("already a hike called", reply)
        self.assertEqual(voice.check(reply), [])
        self.assertIsNone(self.hit("hike-twin", {"title": "Cass Hill", "day": "2026-11-22"}))
        self.assertIsNone(self.hit("hike-twin", {"title": "Dune Walk", "day": "2026-11-15"}))  # cancelled: not a twin
        self.assertIn("already a hike called", self.hit("hike-repeat-twin", {"hike": DONE["id"], "day": "2026-11-21"})[0])
        self.assertIsNone(self.hit("hike-repeat-twin", {"hike": DONE["id"], "day": "2026-11-29"}))

    def test_only_a_scheduled_hike_can_be_changed_moved_or_cancelled_once(self):
        self.assertIsNone(self.hit("hike-scheduled", {"hike": CASS["id"]}))
        self.assertIn("is cancelled", self.hit("hike-scheduled", {"hike": CALLED["id"]})[0])
        self.assertIn("has already happened", self.hit("hike-scheduled", {"hike": DONE["id"]})[0])
        self.assertIn("is already cancelled", self.hit("hike-cancel-state", {"hike": CALLED["id"]})[0])
        self.assertIn("has already happened", self.hit("hike-cancel-state", {"hike": DONE["id"]})[0])
        self.assertIsNone(self.hit("hike-cancel-state", {"hike": CASS["id"]}))
        for rule in ("hike-scheduled", "hike-cancel-state"):
            self.assertEqual(voice.check(self.hit(rule, {"hike": CALLED["id"]})[0]), [])

    def test_a_move_to_the_start_it_already_has(self):
        self.assertIn("already starts then", self.hit("hike-already-then", {"hike": CASS["id"], "day": "2026-11-21"})[0])
        self.assertIn("already starts then", self.hit("hike-already-then", {"hike": CASS["id"], "clock": "09:00"})[0])
        self.assertIsNone(self.hit("hike-already-then", {"hike": CASS["id"], "clock": "09:30"}))
        self.assertIsNone(self.hit("hike-already-then", {"hike": CASS["id"]}))

    def test_a_recap_needs_a_hike_that_has_started_and_was_not_cancelled(self):
        self.assertIn("hasn't happened yet", self.hit("hike-recap-state", {"hike": CASS["id"]})[0])
        self.assertIn("was cancelled", self.hit("hike-recap-state", {"hike": CALLED["id"]})[0])
        self.assertIsNone(self.hit("hike-recap-state", {"hike": DONE["id"]}))
        later = ctx(CASS, now=datetime(2026, 11, 21, 12, 0, tzinfo=PST))
        self.assertIsNone(self.hit("hike-recap-state", {"hike": CASS["id"]}, later))

    def test_prices_are_refused_in_any_text(self):
        for value in ("Coffee after, $5", "5 dollars each", "$ 5", "10 bucks", "12 per person"):
            with self.subTest(value):
                self.assertEqual(self.hit("no-price", {"bring": value})[1], "price")
        self.assertIsNone(self.hit("no-price", {"bring": "Water, a hat, 2 liters"}))
        self.assertEqual(voice.check(hikes.R_PRICE), [])

    def test_invented_sign_up_and_spots_are_refused_when_the_owners_words_are_known(self):
        said = [E2E1A_START + " Meet at the Spooners Cove parking lot. It's an easy difficulty."]
        self.assertEqual(self.hit("hike-no-invention", {"signup": True, "capacity": 10}, texts=said)[0], hikes.R_SIGNUP_NOT_SAID)
        self.assertEqual(self.hit("hike-no-invention", {"signup": True, "capacity": 10}, texts=["add a hike, he said sign up please"])[0], hikes.R_SPOTS_NOT_SAID)
        for fine in (["hike Dec 12 10am Cayucos Pier, sign up with 12 spots"], ["rsvps on, twelve spots"], ["let people sign-up, max 12"]):
            self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "capacity": 12}, texts=fine), fine)
        self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "capacity": 10}))  # his words unknown: no verdict
        self.assertIsNone(self.hit("hike-no-invention", {"signup": False}, texts=said))

    def test_sign_up_needs_words_in_the_same_direction(self):
        """Review round 2: the sign-up WORD is not evidence, its direction is."""
        base = "Add Cass Hill hike December 12 at 8am, meet at Cass Hill gate"
        unclear = hikes.R_SIGNUP_UNCLEAR
        for said in (base + ", sign-up off", base + ", no sign-up", base + ", sign up is off", base + ", without sign-up", base + ", don't let people sign up",
                     base + ", no sign-up and no limit", base + ", sign-up on, sign-up off"):
            with self.subTest(said):
                self.assertEqual(self.hit("hike-no-invention", {"signup": True}, texts=[said])[0], unclear)
                self.assertEqual(self.hit("hike-no-invention", {"signup": True, "no_limit": True}, texts=[said])[0], unclear)
        for said in (base + ", sign-up on", base + ", sign up please", base + ", let people sign up", base + ", rsvps on", base + ", sign-up open",
                     base + ", sign up with no limit", base + ", sign-up on, no limit", base + ", turn on sign-up"):
            with self.subTest(said):
                self.assertIsNone(self.hit("hike-no-invention", {"signup": True}, texts=[said]))
                if "no limit" in said:
                    self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "no_limit": True}, texts=[said]))
        # he said on and the slots say off (or say nothing): the default must not quietly win
        self.assertEqual(self.hit("hike-no-invention", {"signup": False}, texts=[base + ", sign-up on"])[0], unclear)
        self.assertEqual(self.hit("hike-no-invention", {}, texts=[base + ", sign-up on"])[0], unclear)
        self.assertIsNone(self.hit("hike-no-invention", {"signup": False}, texts=[base + ", sign-up off"]))
        self.assertIsNone(self.hit("hike-no-invention", {"signup": False}, texts=[base]))  # the default, nothing said
        # a later message corrects an earlier one; one message that says both is asked about
        self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "no_limit": True}, texts=[base + ", sign-up off", "actually turn sign-up on, no limit"]))
        self.assertIsNone(self.hit("hike-no-invention", {"signup": False}, texts=[base + ", sign-up on", "no wait, sign-up off"]))

    def test_a_guest_limit_needs_a_number_he_tied_to_guests(self):
        base = "Add Cass Hill hike December 12 at 8am, meet at Cass Hill gate"
        not_said = hikes.R_SPOTS_NOT_SAID
        for said in (base + ", sign-up on, no limit", base + ", sign up please", base + ", sign-up on, 5 miles", base + ", sign-up on, bring 12 liters",
                     base + " at 10:30, sign-up on", base + ", sign-up on, up to 5 miles"):
            with self.subTest(said):
                self.assertEqual(self.hit("hike-no-invention", {"signup": True, "capacity": 12}, texts=[said])[0], not_said)
        for said, cap in ((base + ", sign-up on, 15 spots", 15), (base + ", sign-up on, max 15", 15), (base + ", sign up, limit of fifteen", 15),
                          (base + ", sign-up on, a dozen spots", 12), ("cap Cass Hill at 3", 3), ("turn on sign-up, 3 more spots", 3)):
            with self.subTest(said):
                self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "capacity": cap}, texts=[said]))
        # a number and "no limit" together, or two different numbers, are asked about; "no limit" needs its own words
        self.assertEqual(self.hit("hike-no-invention", {"signup": True, "capacity": 15, "no_limit": True}, texts=[base + ", sign-up on, 15 spots, no limit"])[0], not_said)
        self.assertEqual(self.hit("hike-no-invention", {"signup": True, "capacity": 15}, texts=[base + ", sign-up on, 15 spots or 20 spots"])[0], not_said)
        self.assertEqual(self.hit("hike-no-invention", {"signup": True, "no_limit": True}, texts=[base + ", sign-up on, 15 spots"])[0:1], (not_said,))
        self.assertEqual(self.hit("hike-no-invention", {"hike": CASS["id"], "no_limit": True}, texts=["make Cass Hill moderate"])[0], not_said)
        self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "no_limit": True}, texts=["Cass Hill sign-up, unlimited"]))

    def test_the_same_rule_guards_an_edit(self):
        edit = {"hike": CASS["id"]}
        self.assertEqual(self.hit("hike-no-invention", {**edit, "signup": True}, texts=["turn off sign-up for Cass Hill"])[0], hikes.R_SIGNUP_UNCLEAR)
        self.assertEqual(self.hit("hike-no-invention", {**edit, "signup": True, "capacity": 12}, texts=["turn on sign-up for Cass Hill on December 12"])[0], hikes.R_SPOTS_NOT_SAID)
        self.assertEqual(self.hit("hike-no-invention", {**edit, "signup": False}, texts=["make Cass Hill moderate"])[0], hikes.R_SIGNUP_UNCLEAR)  # turned off without a word
        self.assertIsNone(self.hit("hike-no-invention", {**edit, "signup": False}, texts=["turn off sign-up for Cass Hill"]))
        self.assertIsNone(self.hit("hike-no-invention", {**edit, "signup": True, "capacity": 15}, texts=["turn on sign-up for Cass Hill, 15 spots"]))
        self.assertIsNone(self.hit("hike-no-invention", {**edit, "capacity": 3}, texts=["cap Cass Hill at 3"]))
        self.assertEqual(self.hit("hike-no-invention", {**edit, "capacity": 3}, texts=["cap Cass Hill at 3, sign-up off"])[0], hikes.R_SIGNUP_UNCLEAR)
        for reply in (hikes.R_SIGNUP_UNCLEAR, hikes.R_SIGNUP_NOT_SAID, hikes.R_SPOTS_NOT_SAID):
            self.assertEqual(voice.check(reply), [], reply)

    def test_negated_sign_up_words_do_not_turn_sign_up_on(self):
        for said in ("hike Dec 12 10am Cayucos Pier, no sign up", "Dec 12 10am hike, don't let people sign up",
                     "hike Saturday 9am, without rsvps", "hike Saturday, sign ups are off", "hike Saturday, people can't sign up",
                     "hike Saturday. Not taking reservations"):
            with self.subTest(said):
                self.assertEqual(self.hit("hike-no-invention", {"signup": True}, texts=[said])[0], hikes.R_SIGNUP_UNCLEAR)
        for said in ("hike Saturday 9am, sign up please", "hike Saturday, people can sign up, no limit",
                     "hike Saturday, no limit on sign ups", "hike Saturday. No parking fee. Let guests sign up"):
            with self.subTest(said):
                self.assertIsNone(self.hit("hike-no-invention", {"signup": True}, texts=[said]))

    def test_a_guest_limit_must_be_the_number_he_gave_for_guests_not_a_date_or_time(self):
        for said in ("sign up please, hike Dec 12 10am", "sign up, hike on the 12th at 10", "sign up, hike 12/12 at 10:30",
                     "sign up, hike 2026-12-12 at 10", "sign up, hike December 12, meet 8am", "sign up, 12 December"):
            with self.subTest(said):
                for cap in (12, 10, 8, 30, 2026):
                    hit = self.hit("hike-no-invention", {"signup": True, "capacity": cap}, texts=[said])
                    self.assertEqual(hit[0] if hit else None, hikes.R_SPOTS_NOT_SAID, (said, cap))
        for said, cap in (("sign up, Dec 12 10am, 12 spots", 12), ("sign up, Dec 12 at 10, max 20", 20), ("sign up, twelve people", 12),
                          ("sign up, up to twenty five", 25), ("sign up with a limit of 8", 8), ("sign up, Dec 12 10am, 10 guests", 10)):
            with self.subTest(said):
                self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "capacity": cap}, texts=[said]))
        self.assertEqual(self.hit("hike-no-invention", {"signup": True, "capacity": 10},
                                  texts=["sign up, Dec 12 10am, 12 spots"])[0], hikes.R_SPOTS_NOT_SAID)

    def test_a_limit_must_be_a_guest_capacity_he_affirmed(self):
        said = "Add a hike Saturday, sign up please, bring only 2 liters of water"
        self.assertEqual(self.hit("hike-no-invention", {"signup": True, "capacity": 2}, texts=[said])[0], hikes.R_SPOTS_NOT_SAID)
        said = "Add a hike Saturday, sign up please, not 12 spots, 20 spots"
        self.assertEqual(self.hit("hike-no-invention", {"signup": True, "capacity": 12}, texts=[said])[0], hikes.R_SPOTS_NOT_SAID)
        self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "capacity": 20}, texts=[said]))
        self.assertIsNone(self.hit("hike-no-invention", {"signup": True, "capacity": 12}, texts=["sign up, no more than 12"]))

    def test_a_limit_word_needs_a_guest_noun_and_a_later_correction_wins(self):
        no = lambda cap, *texts: self.hit("hike-no-invention", {"signup": True, "capacity": cap}, texts=list(texts))
        self.assertEqual(no(2, "sign up please, bring at most 2 apples")[0], hikes.R_SPOTS_NOT_SAID)
        self.assertEqual(no(12, "sign up please, 12 spots", "actually make it 20 spots")[0], hikes.R_SPOTS_NOT_SAID)
        self.assertIsNone(no(20, "sign up please, 12 spots", "actually make it 20 spots"))
        self.assertIsNone(no(12, "sign up please, 12 spots"))
        self.assertIsNone(no(12, "sign up please, max 12"))
        self.assertIsNone(no(12, "sign up please, at most 12 people"))
        self.assertEqual(no(12, "sign up please, 12 spots", "actually not 12 spots; sign up stays on")[0], hikes.R_SPOTS_NOT_SAID)
        self.assertIsNone(no(20, "sign up please, 12 spots", "actually not 12 spots, 20 spots"))

    def test_the_latest_sign_up_instruction_wins(self):
        self.assertEqual(self.hit("hike-no-invention", {"signup": True}, texts=["sign up please", "actually no sign ups"])[0],
                         hikes.R_SIGNUP_UNCLEAR)
        self.assertIsNone(self.hit("hike-no-invention", {"signup": True}, texts=["no sign ups", "actually, sign up please"]))

    def test_a_plan_cannot_draft_what_a_rule_refuses(self):
        for plan, slots, event in ((hikes.plan_add, {"title": "Cass Hill", "day": "2026-11-21", "clock": "09:00", "meeting_point": "x"}, "already a hike called"),
                                   (hikes.plan_edit, {"hike": CALLED["id"], "bring": "hat"}, "cancelled"),
                                   (hikes.plan_reschedule, {"hike": CASS["id"], "day": "2026-11-21", "clock": "09:00"}, "already starts"),
                                   (hikes.plan_cancel, {"hike": CALLED["id"]}, "already cancelled"),
                                   (hikes.plan_repeat, {"hike": CASS["id"], "day": "2026-11-21", "clock": "10:00"}, "already a hike"),
                                   (hikes.plan_recap, {"hike": CASS["id"], "recap": "good"}, "hasn't happened")):
            with self.subTest(event), self.assertRaises(hikes.Refusal) as caught:
                plan(slots, ctx(CASS, CALLED))
            self.assertIn(event, caught.exception.reply)
            self.assertEqual(voice.check(caught.exception.reply), [])

    def test_missing_slots_ask_their_own_question(self):
        with self.assertRaises(hikes.Refusal) as caught:
            hikes.plan_recap({"hike": CASS["id"]}, ctx())
        self.assertEqual(caught.exception.reply, "How did it go?")
        with self.assertRaises(hikes.Refusal) as caught:
            hikes.plan_reschedule({"hike": CASS["id"]}, ctx())
        self.assertEqual(caught.exception.reply, hikes.R_WHAT_MOVE)

    def test_a_cancel_note_is_one_line_in_his_words(self):
        out = hikes.plan_cancel({"hike": CASS["id"], "note": "  rain\n\n tomorrow  "}, ctx(CASS))
        self.assertEqual(out[0]["args"]["note"], "rain tomorrow")
        self.assertNotIn("note", hikes.plan_cancel({"hike": CASS["id"], "note": "  "}, ctx(CASS))[0]["args"])

    def test_a_recap_of_a_done_hike_corrects_it_and_a_started_one_completes_it(self):
        self.assertEqual(hikes.plan_recap({"hike": DONE["id"], "recap": "x"}, ctx(DONE))[0]["op"], "hike.recap")
        self.assertEqual(hikes.plan_recap({"hike": "hike-2026-11-01-p", "recap": "x"}, ctx(ev("hike-2026-11-01-p", "P", "2026-11-01T08:00:00-08:00")))[0]["op"], "hike.complete")


class DispatcherHandOff(unittest.TestCase):
    def test_rules_and_derivers_are_handed_over_without_replacing_the_generic_ones(self):
        stub = types.SimpleNamespace(RULES={"no-price": "theirs"}, DERIVERS={})
        with mock.patch.dict(sys.modules, {"hass.skills.dispatch": stub}):
            self.assertTrue(hikes._register())
        self.assertEqual(stub.RULES["no-price"], "theirs")
        self.assertIs(stub.RULES["hike-twin"], hikes.rule_twin)
        self.assertEqual(set(stub.RULES), {*hikes.RULES})
        self.assertIs(stub.DERIVERS["place_title"], hikes.place_title)

    def test_the_i_set_wording_is_handed_over_only_when_the_dispatcher_has_a_place_for_it(self):
        stub = types.SimpleNamespace(RULES={}, DERIVERS={}, SET_PHRASES={})
        with mock.patch.dict(sys.modules, {"hass.skills.dispatch": stub}):
            self.assertTrue(hikes._register())
        self.assertIs(stub.SET_PHRASES["hike.add"], hikes.add_set_phrases)
        bare = types.SimpleNamespace(RULES={}, DERIVERS={})  # FW-3 as open today: no such place, nothing is invented there
        with mock.patch.dict(sys.modules, {"hass.skills.dispatch": bare}):
            self.assertTrue(hikes._register())
        self.assertFalse(hasattr(bare, "SET_PHRASES"))

    def test_without_the_dispatcher_nothing_happens(self):
        with mock.patch.dict(sys.modules, {"hass.skills.dispatch": None}):
            self.assertFalse(hikes._register())


class AtTheEditor(HikeTestCase):
    """Plans handed to the real editor (the H04 throwaway repo, an injected clock, a real RSVP file of placeholder guests)."""

    def make(self, repo, **extra):
        slots = {"title": "Test hike", "day": "2026-12-05", "clock": "09:00", "meeting_point": "Test trailhead lot", "signup": True, "capacity": 12, **extra}
        ops = hikes.plan_add(slots, types.SimpleNamespace(today="2026-10-30", now=repo.now, texts=[]))
        repo.run(*[(o["op"], o["args"]) for o in ops])

    def ops(self, plan, slots, repo, **kw):
        c = types.SimpleNamespace(today="2026-10-30", now=repo.now, texts=[], content={"community": repo.community()})
        return [(o["op"], o["args"]) for o in plan(slots, c)]

    def test_the_added_hike_matches_the_ops_the_editor_accepts(self):
        repo = self.repo()
        self.make(repo)
        event = repo.event()
        self.assertEqual((event["rsvpEnabled"], event["capacity"], event["status"]), (True, 12, "scheduled"))

    def test_a_move_and_a_cancel_warn_about_guests_and_still_draft(self):
        repo = self.repo()
        self.make(repo)
        repo.make_db([(HIKE_ID, 1), (HIKE_ID, 2)])
        move = repo.prepare(_req(*self.ops(hikes.plan_reschedule, {"hike": HIKE_ID, "clock": "10:30"}, repo)))
        self.assertEqual(move["result"], "ok", move)
        warning = voice.explain_warning(move["draft"]["warnings"][0])
        self.assertIn("3 guests have signed up", warning)
        self.assertIn("nobody is told automatically", warning)
        cancel = repo.prepare(_req(*self.ops(hikes.plan_cancel, {"hike": HIKE_ID, "note": "rain"}, repo)))
        self.assertEqual(cancel["result"], "ok", cancel)
        self.assertIn("3 guests have signed up", voice.explain_warning(cancel["draft"]["warnings"][0]))
        self.assertEqual(repo.apply(cancel["draft"])["result"], "applied")
        self.assertEqual((repo.event()["status"], repo.event()["cancelNote"]), ("cancelled", "rain"))

    def test_a_limit_below_the_guests_who_signed_up_is_refused_and_without_a_count_it_is_refused_too(self):
        repo = self.repo()
        self.make(repo)
        low = self.ops(hikes.plan_edit, {"hike": HIKE_ID, "capacity": 2}, repo)
        repo.make_db([(HIKE_ID, 3)])
        self.assertEqual(repo.prepare(_req(*low))["result"], "refused")
        repo.use_db(str(repo.db.parent / "absent.sqlite3"))  # cannot be read: fail closed, never a smaller number
        self.assertEqual(repo.prepare(_req(*low))["result"], "refused")

    def test_a_hike_that_has_happened_is_completed_with_his_words_then_corrected(self):
        repo = self.repo()
        self.make(repo)
        repo.now = datetime(2026, 12, 6, 12, 0, tzinfo=PST)  # the day after
        repo.run(*self.ops(hikes.plan_recap, {"hike": HIKE_ID, "recap": "12 people, great morning"}, repo))
        self.assertEqual((repo.event()["status"], repo.event()["recap"]), ("completed", "12 people, great morning"))
        repo.run(*self.ops(hikes.plan_recap, {"hike": HIKE_ID, "recap": "11 people, great morning"}, repo))
        self.assertEqual(repo.event()["recap"], "11 people, great morning")

    def test_repeat_copies_the_text_sign_up_and_limit_to_a_new_day(self):
        repo = self.repo()
        self.make(repo, bring="Water")
        repo.run(*self.ops(hikes.plan_repeat, {"hike": HIKE_ID, "day": "2026-12-12", "clock": "08:00"}, repo))
        copy = repo.event("hike-2026-12-12-test-hike")
        self.assertEqual((copy["bring"], copy["rsvpEnabled"], copy["capacity"], copy["status"]), ("Water", True, 12, "scheduled"))

    def test_the_live_class_each_skill_declares_is_what_the_live_policy_says(self):
        repo = self.repo()
        self.make(repo, difficulty="easy")
        def live(plan, slots):
            drafted = repo.prepare(_req(*self.ops(plan, slots, repo)))
            self.assertEqual(drafted["result"], "ok", drafted)
            return live_policy.check(drafted["draft"])
        # chat-live skills draft nothing the boundary protects
        self.assertEqual(live(hikes.plan_reschedule, {"hike": HIKE_ID, "clock": "10:30"}), [])
        self.assertEqual(live(hikes.plan_cancel, {"hike": HIKE_ID, "note": "rain"}), [])
        repo.now = datetime(2026, 12, 6, 12, 0, tzinfo=PST)
        self.assertEqual(live(hikes.plan_recap, {"hike": HIKE_ID, "recap": "great morning"}), [])
        repo.now = datetime(2026, 10, 30, 12, 0, tzinfo=PST)
        # private-only skills carry trail facts: difficulty, distance, the route link
        for plan, slots in ((hikes.plan_edit, {"hike": HIKE_ID, "difficulty": "moderate"}),
                            (hikes.plan_repeat, {"hike": HIKE_ID, "day": "2026-12-12", "clock": "08:00"}),
                            (hikes.plan_add, {"title": "Other hike", "day": "2026-12-12", "clock": "08:00", "meeting_point": "x", "distance": "5 miles"})):
            with self.subTest(plan.__name__):
                self.assertTrue(live(plan, slots))


class Announcement(unittest.TestCase):
    def content(self, *events):
        return types.SimpleNamespace(community={"events": list(events), "routeIdeas": []})

    def test_the_draft_is_the_title_the_day_his_recap_and_the_fixed_tags(self):
        done = ev("hike-2026-11-14-cass", "Cass Hill", "2026-11-14T09:00:00-08:00", "completed", recap="Great morning, 12 people. We saw whales!")
        out = hikes.recap_announcement(self.content(done), done["id"])
        self.assertEqual(out, {"draft": True, "caption": "Cass Hill\nSaturday, November 14\nGreat morning, 12 people. We saw whales!\n\n#AvocadoShack #NorthCoastHikingClub"})

    def test_nothing_is_added_to_his_words(self):
        done = ev("h", "Cass Hill", "2026-11-14T09:00:00-08:00", "completed", recap="Windy.")
        caption = hikes.recap_announcement(self.content(done), "h")["caption"]
        for word in ("thank", "people", "everyone", "http", "@"):
            self.assertNotIn(word, caption.lower())

    def test_it_refuses_in_plain_words(self):
        cases = {
            "no hike": ("nope", "I don't know that hike."),
            "not started": (CASS["id"], "That hike hasn't happened yet."),
            "cancelled": (CALLED["id"], "That hike was cancelled, so there is nothing to post about."),
        }
        for label, (hike_id, reason) in cases.items():
            with self.subTest(label):
                self.assertEqual(hikes.recap_announcement(self.content(CASS, CALLED), hike_id), {"draft": False, "reason": reason})
        bare = ev("b", "Cass Hill", "2026-11-14T09:00:00-08:00", "completed")
        self.assertEqual(hikes.recap_announcement(self.content(bare), "b")["reason"], hikes.R_NO_RECAP_YET)
        tagged = ev("t", "Cass Hill", "2026-11-14T09:00:00-08:00", "completed", recap="Thanks @friends #hiking")
        self.assertFalse(hikes.recap_announcement(self.content(tagged), "t")["draft"])
        self.assertFalse(hikes.recap_announcement(types.SimpleNamespace(community=None), "t")["draft"])
        for reason in ("I don't know that hike.", "That hike hasn't happened yet.", hikes.R_NO_RECAP_YET):
            self.assertEqual(voice.check(reason), [])

    def test_a_long_recap_is_cut_at_a_sentence_end_never_in_the_middle(self):
        sentence = "We walked the whole ridge and saw the coast. "
        done = ev("l", "Cass Hill", "2026-11-14T09:00:00-08:00", "completed", recap=(sentence * 60).strip())
        caption = hikes.recap_announcement(self.content(done), "l")["caption"]
        self.assertLessEqual(len(caption), hikes.MAX_CAPTION)
        body = caption.split("\n")[2]
        self.assertTrue(body.endswith("coast."))
        self.assertEqual(set(body.split(". ")), {"We walked the whole ridge and saw the coast", "We walked the whole ridge and saw the coast."})
        one_long = ev("m", "Cass Hill", "2026-11-14T09:00:00-08:00", "completed", recap="x" * 2150)
        self.assertEqual(hikes.recap_announcement(self.content(one_long), "m")["reason"], "The recap is too long for one post. Could you shorten it?")

    def test_the_command_line_prints_the_draft_or_the_reason(self):
        done = ev("c", "Cass Hill", "2026-11-14T09:00:00-08:00", "completed", recap="Great morning.")
        with mock.patch("hass.content_model.load_content", return_value=self.content(done)), mock.patch("builtins.print") as shown:
            self.assertEqual(hikes._main(["announce", "c"]), 0)
            self.assertIn("Great morning.", shown.call_args[0][0])
            self.assertEqual(hikes._main(["announce", "zzz"]), 1)
            self.assertEqual(shown.call_args[0][0], "I don't know that hike.")


class KitSeed(unittest.TestCase):
    """The kit's `seed` (this card needs hikes that are already on the page; the repository content has none)."""
    row = {"id": "s", "kind": "clean", "version": 1, "texts": ["cancel Cass Hill"],
           "replies": [{"skill": "hike.cancel", "slots": {"hike": CASS["id"]}}],
           "expect": {"skill": "hike.cancel", "disposition": "proposed", "ops": [{"op": "hike.cancel", "args": {"id": CASS["id"]}}],
                      "diff": [{"file": "hass/content/community.json", "path": f"events[{CASS['id']}].status", "before": "scheduled", "after": "cancelled"}],
                      "files": ["hass/content/community.json", "storefront-mockup/community.json"], "preview": {"kind": "event", "title": "Cass Hill"}},
           "seed": {"community": {"events": [CASS]}}}

    def run_row(self, **change):
        skills = {s.name: s for s in testkit.registry_skills()}
        return testkit.run_case_row({**self.row, **change}, skills, skills["hike.cancel"])

    def test_a_seeded_hike_is_the_start_state_of_the_row(self):
        res = self.run_row()
        self.assertEqual(res.problems, [])
        self.assertEqual(res.facts["undo"], "identical")  # undo comes back to the seeded state, not to an empty page

    def test_without_the_seed_the_hike_is_not_there(self):
        row = {k: v for k, v in self.row.items() if k != "seed"}
        skills = {s.name: s for s in testkit.registry_skills()}
        self.assertFalse(testkit.run_case_row(row, skills, skills["hike.cancel"]).ok)

    def test_a_seed_the_content_rules_refuse_is_a_bad_row_and_leaves_nothing_behind(self):
        res = self.run_row(seed={"community": {"events": [{"id": "x"}]}})
        self.assertEqual(res.codes, ["bad-row"])
        self.assertIn("seed could not be applied", res.problems[0][1])

    def test_a_seed_may_only_name_a_content_file(self):
        for seed in ({"../evil": {"a": 1}}, {"community": [1]}, "events"):
            with self.subTest(seed=seed):
                self.assertEqual(self.run_row(seed=seed).codes, ["bad-row"])


if __name__ == "__main__":
    unittest.main()
