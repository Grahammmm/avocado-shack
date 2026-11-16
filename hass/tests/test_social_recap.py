"""SKILLS-SOCIAL-1 part 2 (AV1109-07): a caption from the owner's saved recap of a completed hike (SKILLS-SPEC 3.29).

``social_draft.build_recap`` (pure), ``social_draft.py --recap ID`` and the read-only ``social.recap`` skill. The caption's only
story is the recap he already saved: no head count, tag or account that he did not write. Every case row of
hass/tests/fixtures/skills/social/social.recap.jsonl is replayed through the real Conversation and Dispatcher.
Run: python3 -B -m unittest hass.tests.test_social_recap -v
"""
import contextlib
import io
import json
import types
import unittest
from unittest import mock

from hass import social_draft, voice
from hass.content_model import ContentError
from hass.skills import dispatch, social
from hass.tests.test_conversation import CHAT, T0
from hass.tests.test_skill_dispatch import skill_reply
from hass.tests.test_skills_social import SocialCase, rows

TAGS = "#AvocadoShack #NorthCoastHikingClub"
HEAD = "Here's a post you can copy. I haven't posted anything."
NO_PHOTO = "No photo is attached here."
BLUFF = "We covered six miles of bluff trail. 12 people came out and the weather was perfect!"
SPRING = "Forty people came and it was lovely. Next time: bring water."


def hike(hid, title, recap=None, status="completed", starts="2026-10-31T16:00:00Z", **more):
    event = {"id": hid, "title": title, "startsAt": starts, "timezone": "America/Los_Angeles", "status": status,
             "meetingPoint": "the Shack porch", "trailId": "idea-point-buchon", "capacity": 30, **more}
    return {**event, "recap": recap} if recap is not None else event


EVENTS = [hike("r-ok", "Bluff Walk", BLUFF, starts="2026-11-01T06:30:00Z"),  # 23:30 on Oct 31 in Pacific
          hike("r-short", "Cove Walk", "Foggy start, clear by noon."),
          hike("r-pier", "Pier Walk", "Six miles, 1,200 feet of climbing.\nSaw two owls!"),
          hike("r-none", "Dune Walk"), hike("r-blank", "Reef Walk", "  \n "),
          hike("r-sched", "Ridge Walk", "It will be great.", status="scheduled"),
          hike("r-cancel", "Marsh Walk", "Rained out.", status="cancelled"),
          hike("r-tag", "Porch Walk", "Thanks @trailcrew for the lift."),
          hike("r-spring", "Spring Walk", SPRING),
          hike("r-friends", "Friend Walk", "We walked six miles with friends. We left on Nov 7 at 6 am, mile 6 was steep. Attendance was great.")]


def caption(title, date, recap):
    return f"{title}\n{date}\n{recap}\n\n{TAGS}"


def events(*es):
    return types.SimpleNamespace(community={"events": list(es)})


class EngineTests(unittest.TestCase):
    def test_completed_saved_recap_exact_caption(self):
        content = events(*EVENTS)
        before = json.dumps(content.community, sort_keys=True)
        want = {"draft": True, "caption": caption("Bluff Walk", "Saturday, October 31, 2026 (Pacific)", BLUFF)}
        self.assertEqual(social_draft.build_recap(content, "r-ok"), want)
        self.assertEqual(social_draft.build_recap(content, "r-ok"), want)
        self.assertEqual(social_draft.build_recap(content, "r-pier")["caption"],
                         caption("Pier Walk", "Saturday, October 31, 2026 (Pacific)", "Six miles, 1,200 feet of climbing.\nSaw two owls!"))
        self.assertNotIn("30", want["caption"])  # capacity is not a people count
        self.assertEqual(json.dumps(content.community, sort_keys=True), before)
        self.assertTrue(social_draft.build_recap(events(hike("x", "No dot", "just words")), "x")["caption"].endswith("\njust words\n\n" + TAGS))

    def test_completion_and_recap_required(self):
        content = events(*EVENTS)
        for hid, reason in (("r-sched", "say how it went first"), ("r-cancel", "say how it went first"), ("r-none", "say how it went first"),
                            ("r-blank", "say how it went first"), ("nope", "no such hike"), ("R-OK", "no such hike")):
            with self.subTest(hid):
                self.assertEqual(social_draft.build_recap(content, hid), {"draft": False, "reason": reason})
        for status in (None, "Completed", 3, "done"):
            self.assertEqual(social_draft.build_recap(events(hike("x", "T", "ok.", status=status)), "x")["reason"], "say how it went first")
        past = hike("x", "T", "ok.", status="scheduled", starts="2020-01-01T10:00:00Z")  # past is not completed
        self.assertEqual(social_draft.build_recap(events(past), "x")["reason"], "say how it went first")
        for bad in (events(hike("x", "T", "ok."), "str"), types.SimpleNamespace(community={"events": "x"}), types.SimpleNamespace(community=None)):
            self.assertEqual(social_draft.build_recap(bad, "x"), {"draft": False, "reason": "cannot read content"})
        for bad in (hike("x", "T", 5), hike("x", "T\nU", "ok."), hike("x", "", "ok."), hike("x", "T", "a\x07b"), hike("x", "T", "ok.", starts="2026-11-01T10:00:00"),
                    hike("x", "T", "ok.", starts="soon"), hike("x", "T", "ok.", starts=None)):
            with self.subTest(str(bad)[:60]):
                self.assertEqual(social_draft.build_recap(events(bad), "x"), {"draft": False, "reason": "hike record incomplete"})

    def test_pacific_date_midnight_dst_and_year(self):
        for starts, date in (("2026-11-01T06:59:59Z", "Saturday, October 31, 2026"), ("2026-11-01T07:00:00Z", "Sunday, November 1, 2026"),
                             ("2026-12-02T07:30:00Z", "Tuesday, December 1, 2026"),   # winter: UTC-8
                             ("2026-07-04T06:59:00Z", "Friday, July 3, 2026"),        # summer: UTC-7
                             ("2026-11-01T08:30:00Z", "Sunday, November 1, 2026"), ("2026-11-01T09:30:00Z", "Sunday, November 1, 2026"),  # both 1:30 am
                             ("2026-11-01T02:30:00-07:00", "Sunday, November 1, 2026"), ("2024-02-29T23:00:00-08:00", "Thursday, February 29, 2024")):
            with self.subTest(starts):
                self.assertEqual(social_draft.build_recap(events(hike("x", "T", "ok.", starts=starts)), "x")["caption"].split("\n")[1], date + " (Pacific)")

    def test_trim_longest_sentence_prefix(self):
        fixed = len("T\nSaturday, October 31, 2026 (Pacific)\n") + len("\n\n" + TAGS)
        room = social_draft.MAX_CAPTION - fixed

        def run(recap):
            return social_draft.build_recap(events(hike("x", "T", recap)), "x")
        fits = "a" * (room - 1) + "."
        self.assertEqual(len(run(fits)["caption"]), 2200)
        self.assertTrue(run(fits)["caption"].startswith("T\nSaturday") and fits in run(fits)["caption"])
        two = "First one.  Second one!\nThird one?" + " x" * 1200  # the overlong tail ends with no mark
        got = run(two)["caption"]
        self.assertEqual(got, caption("T", "Saturday, October 31, 2026 (Pacific)", "First one.  Second one!\nThird one?"))
        over = fits + "b"  # one over, no earlier boundary
        self.assertEqual(run(over), {"draft": False, "reason": "caption too long"})
        early = "Start here.  " + "a" * room  # one over, one fitting sentence
        self.assertEqual(run(early)["caption"], caption("T", "Saturday, October 31, 2026 (Pacific)", "Start here."))
        self.assertEqual(run("Hello world " * 300), {"draft": False, "reason": "caption too long"})  # no punctuation
        self.assertEqual(run("One. Two.A" + "z" * room)["caption"].split("\n")[2], "One.")  # ".T" inside a word is not a boundary
        self.assertEqual(run("Ok. " + "\u00e9" * 3000)["caption"].split("\n")[2], "Ok.")  # code points, not bytes
        self.assertEqual(run("a" * (room - 4) + "\U0001F332\U0001F332.")["caption"].count("\U0001F332"), 2)  # two code points still fit
        self.assertNotIn("\u2026", got)
        self.assertEqual(social_draft.build_recap(events(hike("x", "T" * 2300, "Ok.")), "x"), {"draft": False, "reason": "caption too long"})

    def test_tagged_original_tail_is_refused(self):
        room = social_draft.MAX_CAPTION - len("T\nSaturday, October 31, 2026 (Pacific)\n") - len("\n\n" + TAGS)
        tail = "A short start. " + "w" * room + " #lastword"  # the tagged tail would be cut away: refused before any cutting
        for title, recap in (("T", "see #hike"), ("T", "ask @bob"), ("T", "\uFF03fun"), ("T", "x \uFF20bob"), ("T", "\uFE5Ffun"), ("T", "\uFE6Bbob"),
                             ("Meet @the club", "Fine."), ("#Title", "Fine."), ("T", tail)):
            with self.subTest(title + recap[:12]):
                self.assertEqual(social_draft.build_recap(events(hike("x", title, recap)), "x"),
                                 {"draft": False, "reason": "free text has a hashtag or account name"})
        self.assertTrue(social_draft.build_recap(events(hike("x", "T", "We were # 1 and e @ home.")), "x")["draft"])  # a lone mark is no tag, as in the other engines
        self.assertEqual(social_draft.build_recap(events(hike("x", "T", "a\u2028b")), "x")["reason"], "hike record incomplete")


class CliTests(unittest.TestCase):
    def run_cli(self, argv, content=None, error=None):
        out, err = io.StringIO(), io.StringIO()
        loader = mock.Mock(return_value=content, side_effect=error)
        with mock.patch.object(social_draft, "load_content", loader), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = social_draft.main(argv)
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue(), err.getvalue()

    def test_cli_recap_json_and_exclusivity(self):
        content = events(*EVENTS)
        code, out, err = self.run_cli(["--recap", "r-ok"], content)
        self.assertEqual((code, json.loads(out), err), (0, social_draft.build_recap(content, "r-ok"), ""))
        self.assertEqual(self.run_cli(["--recap", "r-ok", "--now", "2030-01-01T00:00:00Z"], content)[:2], (0, out))  # --now changes nothing
        code, out, _err = self.run_cli(["--recap", "r-none"], content)
        self.assertEqual((code, json.loads(out)), (1, {"draft": False, "reason": "say how it went first"}))
        self.assertEqual(json.loads(self.run_cli(["--recap", "zzz"], content)[1])["reason"], "no such hike")
        code, out, err = self.run_cli(["--recap", "r-ok"], error=ContentError("bad"))
        self.assertEqual((code, json.loads(out), err), (1, {"draft": False, "reason": "cannot read content"}, ""))
        for argv in (["--recap"], ["--recap", "r-ok", "--maker", "k"], ["--recap", "r-ok", "--hike", "r-ok"], ["--recap", "r-ok", "p1"], []):
            with self.subTest(argv):
                code, out, err = self.run_cli(argv, content)
                self.assertEqual((code, out), (2, ""))
                self.assertNotIn("Traceback", err)


class RecapCase(SocialCase):
    """The writer repo with completed, unfinished, recap-less and tagged hikes."""

    def setUp(self):
        super().setUp()
        path = self.content_dir / "community.json"
        doc = json.loads(path.read_text("utf-8"))
        doc["events"] = EVENTS
        path.write_text(json.dumps(doc), "utf-8")

    def want(self, title, recap=BLUFF, date="Saturday, October 31, 2026 (Pacific)"):
        return "\n".join([HEAD, caption(title, date, recap), NO_PHOTO])

    def recap(self, text, title, **slots):
        return self.answered(text, skill_reply("social.recap", hike=title, **slots))


class SkillTests(RecapCase):
    def test_declaration(self):
        skill = social.SOCIAL_RECAP
        self.assertEqual((skill.approval, skill.edits, skill.side_effects, skill.live_class, skill.version), ("none", (), ("none",), "read-only", 1))
        self.assertEqual([(s.name, s.kind, s.required) for s in skill.slots], [("hike", "hike_ref", True)])
        self.assertGreaterEqual(len({t.text for t in skill.triggers}), 6)
        self.assertIs(dispatch.READ_ONLY["social.recap"], social.recap_reply)
        self.assertIn("social.recap", dispatch.READ_ONLY_LONG)
        social._register()
        self.assertIs(dispatch.READ_ONLY["social.recap"], social.recap_reply)
        for text in (social.NO_RECAPS, social.ADD_TO_RECAP, social.NO_TAGGING, *social.RECAP_REFUSALS.values()):
            self.assertEqual(voice.check(text), [], text)
        self.assertIn("say how it went first", social.RECAP_REFUSALS["say how it went first"].lower())

    def test_recap_real_dispatch_and_two_captions(self):
        before = self.snapshot()
        self.assertEqual(self.recap("post about how the bluff walk went", "Bluff Walk"), ("answer", [self.want("Bluff Walk")]))
        self.assertEqual(self.recap("recap post for the cove walk", "Cove Walk"),
                         ("answer", [self.want("Cove Walk", "Foggy start, clear by noon.", "Saturday, October 31, 2026 (Pacific)")]))
        self.assertEqual(self.ask("post about how the hike went", skill_reply("social.recap"))[1][0][0], "Which hike should the post be about?")
        self.assertEqual(self.answered("bluff walk", skill_reply("social.recap", hike="Bluff Walk")), ("answer", [self.want("Bluff Walk")]))
        two = {"calls": [{"skill": "social.recap", "slots": {"hike": "Bluff Walk"}}, {"skill": "social.recap", "slots": {"hike": "Spring Walk"}}]}
        self.assertEqual(self.answered("recap captions for the bluff walk and the spring walk", two),
                         ("answer", [self.want("Bluff Walk"), self.want("Spring Walk", SPRING)]))
        bad = {"calls": [{"skill": "social.recap", "slots": {"hike": "Dune Walk"}}, {"skill": "social.recap", "slots": {"hike": "Bluff Walk"}}]}
        self.assertEqual(self.answered("recap captions for the dune walk and the bluff walk", bad),
                         ("answer", [social.RECAP_REFUSALS["say how it went first"], self.want("Bluff Walk")]))
        self.assertIsNone(self.live())
        self.assert_untouched(before)

    def test_unfinished_and_unusable_hikes_say_how_it_went_first(self):
        before = self.snapshot()
        for title in ("Dune Walk", "Reef Walk", "Ridge Walk", "Marsh Walk"):
            with self.subTest(title):
                self.assertEqual(self.recap(f"post about how the {title.lower()} went", title), ("answer", [social.RECAP_REFUSALS["say how it went first"]]))
        self.assertEqual(self.recap("post about the porch walk recap", "Porch Walk"), ("answer", [social.SHARED_REFUSALS["free text has a hashtag or account name"]]))
        self.assert_untouched(before)

    def test_no_completed_recap_at_all(self):
        path = self.content_dir / "community.json"
        doc = json.loads(path.read_text("utf-8"))
        doc["events"] = [e for e in EVENTS if e["id"] in ("r-none", "r-sched")]
        path.write_text(json.dumps(doc), "utf-8")
        self.assertEqual(self.answered("post about how the last hike went", skill_reply("social.recap")), ("refused", [social.NO_RECAPS]))
        self.assertIsNone(self.live())

    def test_requested_attendance_must_already_be_saved(self):
        before = self.snapshot()
        for text in ("post about the bluff walk and say 40 people came", "bluff walk caption, mention forty hikers came",
                     "bluff walk post, add that 30 of us showed up", "caption for the cove walk and say 6 people came"):
            with self.subTest(text):
                self.assertEqual(self.recap(text, "Bluff Walk"), ("refused", [social.ADD_TO_RECAP]))
        for text in ("post the recap and say 40 people came", "add that 40 people came"):  # no hike named: same guidance, no number taken
            self.assertEqual(self.answered(text, skill_reply("social.recap")), ("refused", [social.ADD_TO_RECAP]))
        self.assertEqual(self.recap("bluff walk caption and say 6 miles, 1,200 feet", "Bluff Walk")[0], "answer")  # a mileage is no head count
        self.assertEqual(self.recap("caption for the pier walk, say 6 people came", "Pier Walk"), ("refused", [social.ADD_TO_RECAP]))  # 6 miles is not 6 people
        disposition, said = self.recap("bluff walk caption, say 12 people came", "Bluff Walk")  # already saved: the unchanged caption
        self.assertEqual((disposition, said), ("answer", [self.want("Bluff Walk")]))
        self.assertEqual(self.recap("spring walk caption, say forty people came", "Spring Walk"), ("answer", [self.want("Spring Walk", SPRING)]))
        forged = self.recap("bluff walk caption", "Bluff Walk", recap="We had 99 people", count=99)  # a model-supplied recap or count is not used
        self.assertEqual(forged, ("answer", [self.want("Bluff Walk")]))
        self.assert_untouched(before)

    def test_distances_and_dates_are_not_head_counts(self):
        before = self.snapshot()
        for text in ("friend walk caption, say 6 people came", "friend walk caption, say six friends came", "friend walk caption, say 7 hikers came"):
            with self.subTest(text):  # the saved recap has "six miles with friends", "Nov 7 at 6 am", "mile 6 was steep"
                self.assertEqual(self.recap(text, "Friend Walk"), ("refused", [social.ADD_TO_RECAP]))
        for said, counted in (("We walked six miles with friends.", set()), ("Six miles of friends and 3 hours of fog.", set()),
                              ("We hiked 6 km with hikers", set()), ("On Nov 7 friends joined; mile 6 hikers waited.", set()),
                              ("6 days with kids", set()), ("Attendance was 40 miles", set()),
                              ("40 happy people came", {40}), ("Forty of us came.", {40}), ("Attendance was 40.", {40}),
                              ("On Nov 7, 12 people came and six friends joined.", {12, 6}), ("We walked six miles. 12 people came.", {12})):
            with self.subTest(said):
                self.assertEqual(social._counts(said), counted)
        self.assert_untouched(before)

    def test_compound_attendance_counts_are_complete(self):
        for said, counted in (("Twenty one people came.", {21}), ("twenty-one people came.", {21}), ("THIRTY ONE guests came.", {31}),
                              ("Ninety-nine people came.", {99}), ("Attendance was twenty one.", {21}), ("Turnout was forty-two", {42}),
                              ("Twenty people came.", {20}), ("twenty  one hikers came", {21}), ("Twenty-one people and 12 guests came.", {21, 12})):
            with self.subTest(said):
                self.assertEqual(social._counts(said), counted)

    def test_compound_distance_date_and_money_controls(self):
        for said in ("We walked twenty one miles with friends.", "We walked twenty-one miles with friends.", "On Nov twenty one friends joined.",
                     "Attendance was twenty-one miles", "mile twenty one hikers waited"):
            with self.subTest(said):
                self.assertEqual(social._counts(said), set())

    def _with_recaps(self, **recaps):
        path = self.content_dir / "community.json"
        doc = json.loads(path.read_text("utf-8"))
        doc["events"] = [hike(f"c-{i}", title, text) for i, (title, text) in enumerate(recaps.items())]
        path.write_text(json.dumps(doc), "utf-8")

    def test_digit_and_compound_attendance_equivalence(self):
        self._with_recaps(**{"Bluff Walk": "21 people came.", "Cove Walk": "Twenty-one people came.", "Pier Walk": "Thirty one people came."})
        before = self.snapshot()
        for title, text in (("Bluff Walk", "bluff walk caption, say twenty one people came"), ("Bluff Walk", "bluff walk caption, say twenty-one people came"),
                            ("Cove Walk", "cove walk caption, say 21 people came"), ("Cove Walk", "cove walk caption, say twenty one people came")):
            with self.subTest(text):
                saved = "21 people came." if title == "Bluff Walk" else "Twenty-one people came."
                self.assertEqual(self.recap(text, title), ("answer", [self.want(title, saved)]))
        self.assert_untouched(before)

    def test_distinct_compounds_cannot_share_a_component(self):
        self._with_recaps(**{"Bluff Walk": "Thirty-one people came.", "Cove Walk": "Twenty people came.", "Pier Walk": "Twenty-one people came."})
        before = self.snapshot()
        for title, text in (("Bluff Walk", "bluff walk caption, say twenty-one people came"), ("Bluff Walk", "bluff walk caption, say twenty one people came"),
                            ("Cove Walk", "cove walk caption, say twenty-one people came"), ("Cove Walk", "cove walk caption, say twenty one people came"),
                            ("Pier Walk", "pier walk caption, say twenty people came"), ("Pier Walk", "pier walk caption, say one person came and twenty-one people came"),
                            ("Pier Walk", "pier walk caption, say 1 people came")):
            with self.subTest(text):
                self.assertEqual(self.recap(text, title), ("refused", [social.ADD_TO_RECAP]))
        self.assert_untouched(before)

    def test_hundred_attendance_is_one_complete_count(self):
        for said, counted in (("one hundred people came", {100}), ("Two Hundred people came.", {200}), ("two  hundred and one guests came", {201}),
                              ("two hundred one guests came", {201}), ("two hundred twenty-one people came", {221}),
                              ("two hundred and twenty one people came", {221}), ("nine hundred ninety-nine hikers came", {999}),
                              ("attendance was two hundred", {200}), ("Attendance was two hundred and twenty-one", {221}),
                              ("turnout was nine hundred ninety-nine", {999}), ("two hundred and five of us came", {205}),
                              ("Attendance was two hundred twenty", {220}), ("two hundred eighteen people came", {218}),
                              ("Attendance was two hundred nineteen", {219}), ("two hundred and eighteen people came", {218}),
                              ("a hundred people came", {100}), ("Twenty-one people and 12 guests came.", {21, 12}), ("200 people came", {200})):
            with self.subTest(said):
                self.assertEqual(social._counts(said), counted)

    def test_hundred_equivalence_uses_saved_attendance(self):
        self._with_recaps(**{"Bluff Walk": "200 people came.", "Cove Walk": "Two hundred people came.", "Pier Walk": "2 people came.",
                             "Spring Walk": "Two hundred and twenty-one people came.", "Friend Walk": "21 people came."})
        before = self.snapshot()
        for title, text, saved in (("Bluff Walk", "bluff walk caption, say two hundred people came", "200 people came."),
                                   ("Cove Walk", "cove walk caption, say 200 people came", "Two hundred people came."),
                                   ("Spring Walk", "spring walk caption, say 221 people came", "Two hundred and twenty-one people came.")):
            with self.subTest(text):
                self.assertEqual(self.recap(text, title), ("answer", [self.want(title, saved)]))
        for title, text in (("Pier Walk", "pier walk caption, say two hundred people came"), ("Friend Walk", "friend walk caption, say two hundred and twenty-one people came"),
                            ("Pier Walk", "pier walk caption, say 200 people came"), ("Bluff Walk", "bluff walk caption, say two hundred and one people came"),
                            ("Bluff Walk", "bluff walk caption, say one hundred people came")):
            with self.subTest(text):  # the real dispatcher refuses before any caption
                self.assertEqual(self.recap(text, title), ("refused", [social.ADD_TO_RECAP]))
        self.assert_untouched(before)

    def test_hundred_context_is_not_a_distance_date_or_price(self):
        for said in ("We walked two hundred miles with friends.", "two hundred minutes with kids", "On Nov two hundred friends joined.",
                     "mile two hundred hikers waited", "route two hundred and five guests", "$ two hundred friends", "Attendance was two hundred miles"):
            with self.subTest(said):
                self.assertEqual(social._counts(said), set())

    def test_hundred_remainder_distance_cannot_authorize_attendance(self):
        for number in ("two hundred twenty", "two hundred twenty-one", "two hundred twenty one", "two hundred one",
                       "two hundred and twenty", "two hundred and twenty-one", "two hundred and one"):
            saved = f"Attendance was {number} miles"
            with self.subTest(saved=saved, seam="counts"):
                self.assertEqual(social._counts(saved), set())
            with self.subTest(saved=saved, seam="dispatch"):
                self._with_recaps(**{"Bluff Walk": saved})
                before = self.snapshot()
                self.assertEqual(self.recap("bluff walk caption, say 200 people came", "Bluff Walk"), ("refused", [social.ADD_TO_RECAP]))
                self.assert_untouched(before)

    def test_unsupported_numeric_run_cannot_authorize_by_suffix(self):
        self._with_recaps(**{"Bluff Walk": "2 people came. 100 hikers came.", "Cove Walk": "Two people came."})
        before = self.snapshot()
        for title, text in (("Bluff Walk", "bluff walk caption, say two thousand two people came"), ("Cove Walk", "cove walk caption, say two thousand people came"),
                            ("Bluff Walk", "bluff walk caption, say two hundred hundred people came"), ("Bluff Walk", "bluff walk caption, add attendance was two hundred hundred"),
                            ("Bluff Walk", "bluff walk caption, say two hundred and hundred people came")):
            with self.subTest(text):
                self.assertEqual(self.recap(text, title), ("refused", [social.ADD_TO_RECAP]))
        for said in ("two thousand two people came", "two hundred hundred people came"):
            self.assertEqual(social._counts(said), set())
        self.assert_untouched(before)

    def test_tag_partners_and_publish_are_refused(self):
        before = self.snapshot()
        for text in ("bluff walk caption and tag the partners", "post about the bluff walk with the hashtag #hikingfun", "caption, thank @trailcrew please",
                     "caption for the bluff walk \uFF20bob", "bluff walk caption with \uFF03fun", "bluff walk caption \uFE6Bbob"):
            with self.subTest(text):
                self.assertEqual(self.recap(text, "Bluff Walk"), ("refused", [social.NO_TAGGING]))
        for text in ("post the bluff walk recap now", "send the bluff walk recap to the club"):
            with self.subTest(text):
                self.assertEqual(self.recap(text, "Bluff Walk"), ("refused", [social.NO_POSTING]))
        self.assertEqual(self.recap("post about the tag-along hike, the bluff walk", "Bluff Walk")[0], "answer")
        self.assert_untouched(before)

    def test_other_captions_unchanged(self):
        # the tag and count checks belong to social.recap only; the hike caption still reads the same text
        self.assertEqual(self.answered("caption for the bluff walk and tag everyone", skill_reply("social.hike", hike="Bluff Walk"))[0], "answer")
        self.assertEqual(social.hike_reply({"hike": "r-ok"}, types.SimpleNamespace(content=self.content(), now=T0)),
                         social.HIKE_REFUSALS["hike already happened"])


class CaseRowTests(RecapCase):
    def test_every_recap_case_row_gives_the_recorded_answer(self):
        got = rows("social.recap")
        self.assertGreaterEqual(len(got), 10)
        self.assertGreaterEqual(sum(1 for r in got if r["kind"] == "refuse"), 2)
        for row in got:
            with self.subTest(row["id"]):
                replay = row["note"]["dispatch"]
                self.now = T0
                self.conv.requests.close_live(CHAT, self.now, "closed")
                before = self.snapshot()
                disposition, said = self.answered(row["texts"][0], replay["skill"])
                self.assertEqual(disposition, replay["disposition"])
                self.assertEqual(said, replay["said"])
                answer = "\n\n".join(said)  # the generic kit has no long-caption path: its short wording replay is separate
                self.assertEqual(row["replies"], [{"unsupported": answer.splitlines()[0] if len(answer) > voice.LONG_AFTER else answer}])
                self.assertIn(row["expect"]["reply_contains"], answer)
                self.assertTrue(row["version"] == 1 and "undo" not in row)
                self.assert_untouched(before)


if __name__ == "__main__":
    unittest.main()
