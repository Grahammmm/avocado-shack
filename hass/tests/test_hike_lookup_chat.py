"""HIKE-LOOKUP-2: the map lookup in the hike.add chat (docs/hass/HIKE-LOOKUP.md, "HIKE-LOOKUP-2").

Hermetic: the live fetch is replaced by the recorded answers of HIKE-LOOKUP-1 (hass/tests/fixtures/hike_lookup/), sleeping is
patched out, and every test blocks sockets. The production ``hike.add`` skill runs through the real Conversation, dispatcher and
Editor with a scripted interpreter (the model's replies are written out per owner text); nothing is written before the owner's own
``yes <code>``.
Run: python3 -m unittest hass.tests.test_hike_lookup_chat -v
"""
import dataclasses
import fcntl
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import conversation, hike_fetch, hike_lookup as hl, voice
from hass.skills import dispatch, hikes
from hass.tests.test_conversation import CHAT, SETTINGS, T0 as NOW
from hass.tests.test_skill_dispatch import LIVE1, SATURDAY, SkillCase, registry_of, skill_reply

FIX = Path(__file__).resolve().parent / "fixtures" / "hike_lookup"
CONTACT = "mike-shack@example.invalid"
PLAIN_QUESTION = "Where do people meet?"
FOUND = ("Did you mean Bishop Peak Trail in San Luis Obispo County, about 2.4 miles out and back on the map, "
         "with about 740 feet of climbing? Reply yes to use it, or no and tell me more.")
ADD_BISHOP = "add a hike on Bishop Peak Saturday at 9am"
BISHOP = skill_reply("hike.add", title="Bishop Peak hike", day=SATURDAY, clock="09:00")


class FakeFetch:
    """Stands in for ``hike_fetch.LiveFetch``: replays the recorded answers and remembers the contact it was made with."""
    made, requests, fixtures = [], [], ("bishop_peak",)
    fail = None

    def __init__(self, contact):
        FakeFetch.made.append(contact)
        self.transport = hl.FixtureTransport(*(FIX / f"{name}.json" for name in FakeFetch.fixtures))

    def __call__(self, service, request):
        FakeFetch.requests.append(service)
        if FakeFetch.fail:
            raise hl.TransportError(FakeFetch.fail)
        return self.transport.get(service, request).body


class NoNetwork(unittest.TestCase):
    def setUp(self):
        super().setUp()
        FakeFetch.made, FakeFetch.requests, FakeFetch.fixtures, FakeFetch.fail = [], [], ("bishop_peak",), None

        def refuse(*_a, **_k):
            raise AssertionError("a test tried to use the network")
        for target in ("socket.socket.connect", "socket.create_connection", "socket.getaddrinfo"):
            patcher = mock.patch(target, refuse)
            patcher.start()
            self.addCleanup(patcher.stop)


class ChatCase(NoNetwork, SkillCase):
    SKILLS = (hikes.ADD,)
    LOOKUP = {"contact": CONTACT}

    def setUp(self):
        super().setUp()
        for target, new in (("hass.hike_fetch.LiveFetch", FakeFetch), ("time.sleep", lambda s: None)):
            patcher = mock.patch(target, new)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.settings(self.LOOKUP)

    def settings(self, lookup):
        extra = {} if lookup is None else {"hikeLookup": lookup}
        self.set_settings({**SETTINGS, "skills": {"mode": self.MODE}, **extra})
        self.conv = self.open()

    def turn(self, text, reply):
        self.script(text, reply)
        disposition = self.say(text)
        return disposition, self.replies()

    @property
    def folder(self):
        return self.repo.state / "hike_lookup"

    def offers(self):
        return sorted((self.folder / "offers").glob("*.json")) if (self.folder / "offers").exists() else []

    def last_ops(self):
        return json.loads(self.drafts()[-1]["ops_json"])

    def asked_to_meet(self):
        return self.live()["asked_slot"] == "meeting_point"

    def fresh(self):
        """Start over inside one test: the open request is closed and any draft waiting for a yes is cancelled."""
        self.conv.requests.close_live(CHAT, self.now)
        if self.conv._drafts("state IN ('proposed', 'needs-details')"):
            self.say("no")
            self.replies()


class TheOffer(ChatCase):
    def test_a_named_hike_with_no_meeting_place_is_offered_the_map_trail_with_measured_numbers(self):
        disposition, [said] = self.turn(ADD_BISHOP, BISHOP)
        self.assertEqual(disposition, "question")
        self.assertEqual(voice.plain(said), FOUND)
        self.assertEqual(voice.check(said), [])
        self.assertEqual(FakeFetch.made, [CONTACT])  # the operator's contact address, from the setting, is what the client was made with
        self.assertEqual(FakeFetch.requests, ["overpass", "nominatim_reverse", "elevation"])
        self.assertTrue(self.asked_to_meet())
        self.assertEqual(voice.plain(self.live()["question"]), voice.plain(said))
        self.nothing_written()

    def test_yes_then_the_place_gives_the_route_idea_and_the_hike_on_it_and_needs_the_owners_yes_code(self):
        self.turn(ADD_BISHOP, BISHOP)
        disposition, [asked] = self.turn("yes", skill_reply("hike.add"))
        self.assertEqual((disposition, asked), ("question", PLAIN_QUESTION))  # the usual next question, no second lookup
        self.assertEqual(FakeFetch.requests, ["overpass", "nominatim_reverse", "elevation"])
        disposition, [proposal] = self.turn("Highland trailhead", skill_reply("hike.add", meeting_point="Highland trailhead"))
        self.assertEqual(disposition, "proposed")
        route, hike = self.last_ops()
        self.assertEqual([route["op"], hike["op"]], ["route.add", "hike.create"])
        self.assertEqual((route["args"]["title"], route["args"]["distance"], route["args"]["elevation"], route["args"]["routeType"]),
                         ("Bishop Peak Trail", "2.4 miles", "About 740 ft", "Out & back"))
        self.assertEqual(route["args"]["sourceName"], f"{hl.SOURCE_NAME}, retrieved Nov 2, 2026")  # the day the answers were really fetched
        self.assertEqual(route["args"]["sourceUrl"], "https://www.openstreetmap.org/way/175094087")
        self.assertEqual((hike["args"]["title"], hike["args"]["meetingPoint"], hike["args"]["trailId"], hike["args"]["rsvpEnabled"]),
                         ("Bishop Peak hike", "Highland trailhead", "idea-bishop-peak-trail", False))
        self.assertIn("I'll also add a route idea for", voice.plain(proposal))
        self.assertIn("about 2.4 miles out and back on the map", voice.plain(proposal))
        self.assertEqual(voice.check(proposal.splitlines()[0], long_ok=True), [])  # the line beside the draft (the editor's own lines name the link)
        self.nothing_written()
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        community = json.loads((self.repo.wt / "hass/content/community.json").read_text("utf-8"))
        idea = next(r for r in community["routeIdeas"] if r["id"] == "idea-bishop-peak-trail")
        event = next(e for e in community["events"] if e["title"] == "Bishop Peak hike")
        self.assertEqual((idea["status"], idea["rsvpEnabled"], event["trailId"], event["rsvpEnabled"]), ("idea", False, idea["id"], False))

    def test_no_means_the_plain_flow_and_no_route_idea_and_no_second_lookup(self):
        self.turn(ADD_BISHOP, BISHOP)
        disposition, [asked] = self.turn("no", skill_reply("hike.add"))
        self.assertEqual((disposition, asked), ("question", PLAIN_QUESTION))
        self.turn("Highland trailhead", skill_reply("hike.add", meeting_point="Highland trailhead"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["hike.create"])
        self.assertNotIn("trailId", self.last_ops()[0]["args"])
        self.assertEqual(len(FakeFetch.requests), 3)  # only the first lookup's requests

    def test_no_and_more_words_is_a_no_and_so_is_any_answer_that_is_not_a_clear_yes(self):
        for n, answer in enumerate(("no, I mean Cerro San Luis", "hmm not sure", "what about the second one")):
            with self.subTest(answer=answer):
                self.fresh()
                text = f"{ADD_BISHOP} {n}"
                self.turn(text, BISHOP)
                self.assertEqual(self.turn(answer, skill_reply("hike.add"))[1], [PLAIN_QUESTION])
                self.turn("Highland trailhead", skill_reply("hike.add", meeting_point="Highland trailhead"))
                self.assertEqual([op["op"] for op in self.last_ops()], ["hike.create"])

    def test_the_offer_is_asked_once_a_later_turn_does_not_look_the_map_up_again(self):
        self.turn(ADD_BISHOP, BISHOP)
        before = len(FakeFetch.requests)
        self.turn("tell me about it", skill_reply("hike.add"))
        self.turn("Highland trailhead", skill_reply("hike.add", meeting_point="Highland trailhead"))
        self.assertEqual(len(FakeFetch.requests), before)

    def test_the_offer_files_and_the_log_hold_no_owner_text(self):
        self.turn(ADD_BISHOP, BISHOP)
        self.turn("yes", skill_reply("hike.add"))
        files = [p for p in self.folder.rglob("*") if p.is_file()]
        self.assertTrue(files)
        for path in files:
            body = path.read_text("utf-8")
            for private in (ADD_BISHOP, "Saturday at 9am", "Highland"):
                self.assertNotIn(private, body, path.name)
        log = [json.loads(line) for line in (self.folder / "requests.log").read_text("utf-8").splitlines()]
        self.assertEqual(len(log), 3)
        for row in log:
            self.assertEqual(set(row), {"at", "service", "key", "outcome", "seconds"})
            self.assertEqual(row["outcome"], "fetched")
        self.assertEqual(self.folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.folder / "offers").stat().st_mode & 0o777, 0o700)

    def test_only_the_hike_name_is_sent_not_the_day_or_the_place(self):
        sent = []
        original = FakeFetch.__call__

        def spy(fetch, service, request):
            sent.append(json.dumps(request))
            return original(fetch, service, request)

        with mock.patch.object(FakeFetch, "__call__", spy):
            self.turn("add a hike on Bishop Peak Saturday at 9am, call 805 555 0100", BISHOP)
        text = " ".join(sent)
        for private in ("Saturday", "9am", "805", "555", "0100", "call"):
            self.assertNotIn(private, text)


class SeveralTrails(ChatCase):
    ADD_BLUFF = "add a hike on Bluff Trail Saturday at 9am"
    BLUFF = skill_reply("hike.add", title="Bluff Trail hike", day=SATURDAY, clock="09:00")

    def setUp(self):
        super().setUp()
        FakeFetch.fixtures = ("bluff_trail",)

    def test_at_most_three_are_offered_each_with_its_own_numbers_and_a_pick_by_number_adds_that_one(self):
        _, [said] = self.turn(self.ADD_BLUFF, self.BLUFF)
        text = voice.plain(said)
        self.assertTrue(text.startswith("I found 3 that fit. Which one do you mean?"), text)
        self.assertEqual(voice.check(said, long_ok=True), [])
        self.assertIn("Reply 1, 2 or 3", text)
        offered = [c for c in json.loads(self.offers()[0].read_text("utf-8"))["candidates"]]
        self.assertEqual(len(offered), 3)
        self.assertIsNone(next((c["miles"] for c in offered if not c["shape"]), None))  # a trail the map is not sure of has no number
        sure = [i for i, c in enumerate(offered) if c["miles"] is not None]
        self.assertTrue(sure)
        pick = sure[0]
        self.assertEqual(self.turn(str(pick + 1), skill_reply("hike.add"))[1], [PLAIN_QUESTION])
        self.turn("The gate", skill_reply("hike.add", meeting_point="The gate"))
        route, hike = self.last_ops()
        self.assertEqual((route["op"], route["args"]["title"], route["args"]["distance"]),
                         ("route.add", offered[pick]["name"], f"{offered[pick]['miles']:.1f} miles"))
        self.assertEqual(hike["args"]["trailId"], hl.route_id(offered[pick]["name"], ()))

    def test_a_bare_yes_to_several_is_asked_once_more_then_a_number_is_taken(self):
        _, [first] = self.turn(self.ADD_BLUFF, self.BLUFF)
        disposition, [again] = self.turn("yes", skill_reply("hike.add"))
        self.assertEqual((disposition, again), ("question", first))
        self.assertEqual(self.turn("1", skill_reply("hike.add"))[1], [PLAIN_QUESTION])
        self.turn("The gate", skill_reply("hike.add", meeting_point="The gate"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["route.add", "hike.create"])

    def test_a_second_bare_yes_is_not_asked_a_third_time(self):
        self.turn(self.ADD_BLUFF, self.BLUFF)
        self.turn("yes", skill_reply("hike.add"))
        self.assertEqual(self.turn("yes please", skill_reply("hike.add"))[1], [PLAIN_QUESTION])
        self.turn("The gate", skill_reply("hike.add", meeting_point="The gate"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["hike.create"])

    def test_a_number_out_of_range_adds_nothing(self):
        self.turn(self.ADD_BLUFF, self.BLUFF)
        self.assertEqual(self.turn("7", skill_reply("hike.add"))[1], [PLAIN_QUESTION])
        self.turn("The gate", skill_reply("hike.add", meeting_point="The gate"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["hike.create"])

    def test_picking_a_trail_the_map_is_not_sure_of_adds_no_route_idea_and_no_number(self):
        self.turn(self.ADD_BLUFF, self.BLUFF)
        offered = json.loads(self.offers()[0].read_text("utf-8"))["candidates"]
        unsure = next(i for i, c in enumerate(offered) if not c["shape"])
        self.assertEqual(self.turn(str(unsure + 1), skill_reply("hike.add"))[1], [PLAIN_QUESTION])
        self.turn("The gate", skill_reply("hike.add", meeting_point="The gate"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["hike.create"])


class WhenThePlainFlowRuns(ChatCase):
    def plain(self, text=ADD_BISHOP, reply=BISHOP):
        disposition, [said] = self.turn(text, reply)
        self.assertEqual((disposition, said), ("question", PLAIN_QUESTION))
        return said

    def test_no_setting_means_no_lookup_at_all(self):
        self.settings(None)
        self.plain()
        self.assertEqual((FakeFetch.made, FakeFetch.requests, self.offers()), ([], [], []))

    def test_a_bad_contact_setting_stops_the_start_up_and_no_address_is_built_in(self):
        for bad in ("nobody", "two words@example.com", "http://example.com", "x" * 120 + "@example.com", 7, ["a@b.co"], ""):
            with self.subTest(contact=bad):
                with self.assertRaises(conversation.ConfigError):
                    self.settings({"contact": bad})
        with self.assertRaises(conversation.ConfigError):
            self.settings("mike@example.com")
        self.settings({"contact": "https://example.com/contact"})  # a link is as good as an address
        self.assertEqual(conversation.load_settings(self.repo.state)["hikeLookupContact"], "https://example.com/contact")
        self.settings({})  # no contact given: the lookup is off
        self.assertNotIn("hikeLookupContact", conversation.load_settings(self.repo.state))
        self.settings(None)
        self.assertNotIn("hikeLookupContact", conversation.load_settings(self.repo.state))
        self.set_settings({**SETTINGS, "hikeLookup.contact": CONTACT})  # the flat key, like skills.mode
        self.assertEqual(conversation.load_settings(self.repo.state)["hikeLookupContact"], CONTACT)

    def test_a_meeting_place_a_distance_or_a_listed_route_the_owner_gave_means_no_lookup(self):
        cases = {"place": skill_reply("hike.add", title="Bishop Peak hike", day=SATURDAY, clock="09:00", meeting_point="Highland trailhead"),
                 "distance": skill_reply("hike.add", title="Bishop Peak hike", day=SATURDAY, clock="09:00", distance="about 3 miles"),
                 "trail": skill_reply("hike.add", title="Bishop Peak hike", day=SATURDAY, clock="09:00", trail="Cass Hill")}
        for name, reply in cases.items():
            with self.subTest(name):
                self.fresh()
                text = f"add Bishop Peak {name} Saturday 9am about 3 miles Highland trailhead Cass Hill"
                self.turn(text, reply)
                self.assertEqual((FakeFetch.made, FakeFetch.requests), ([], []))

    def test_a_route_idea_hass_already_has_is_never_looked_up(self):
        self.plain("add a hike on Cass Hill Saturday at 9am", skill_reply("hike.add", title="Cass Hill hike", day=SATURDAY, clock="09:00"))
        self.assertEqual(FakeFetch.requests, [])

    def test_a_title_that_is_not_a_place_asks_nothing(self):
        self.plain("add a Saturday morning hike at 9am", skill_reply("hike.add", title="Saturday morning hike", day=SATURDAY, clock="09:00"))
        self.assertEqual((FakeFetch.made, FakeFetch.requests), ([], []))

    def test_several_asks_in_one_message_are_never_looked_up(self):
        text = "add Bishop Peak hike Saturday at 9am and Cerro San Luis hike Sunday at 9am"
        calls = {"calls": [{"skill": "hike.add", "slots": {"title": "Bishop Peak hike", "day": SATURDAY, "clock": "09:00"}},
                           {"skill": "hike.add", "slots": {"title": "Cerro San Luis hike", "day": "2026-11-08", "clock": "09:00"}}],
                 "revises": None}
        self.turn(text, calls)
        self.assertEqual((FakeFetch.made, FakeFetch.requests), ([], []))

    def test_nothing_found_gives_the_plain_question_and_no_second_try(self):
        FakeFetch.fixtures = ("no_match",)
        self.plain("add a hike on Mount Doom Saturday at 9am", skill_reply("hike.add", title="Mount Doom hike", day=SATURDAY, clock="09:00"))
        before = len(FakeFetch.requests)
        self.turn("tell me more", skill_reply("hike.add"))
        self.assertEqual(len(FakeFetch.requests), before)
        self.assertEqual(len(self.offers()), 1)  # the "nothing to offer" note
        self.turn("The gate", skill_reply("hike.add", meeting_point="The gate"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["hike.create"])

    def test_a_trail_the_map_is_not_sure_of_gives_no_number_and_the_plain_question(self):
        FakeFetch.fixtures = ("valencia_peak",)
        said = self.plain("add a hike on Valencia Peak Saturday at 9am", skill_reply("hike.add", title="Valencia Peak hike", day=SATURDAY, clock="09:00"))
        self.assertNotRegex(said, r"\d")

    def test_every_way_the_map_can_fail_leaves_the_hike_flow_whole(self):
        for kind in ("network", "slow", "busy", "bad"):
            with self.subTest(kind=kind):
                self.fresh()
                FakeFetch.fail = kind
                self.plain(f"add a hike on Bishop Peak Saturday at 9am {kind}", BISHOP)
                self.turn("The gate", skill_reply("hike.add", meeting_point="The gate"))
                self.assertEqual([op["op"] for op in self.last_ops()], ["hike.create"])

    def test_a_bug_in_the_lookup_never_stops_the_hike(self):
        with mock.patch.object(hl, "lookup", side_effect=RuntimeError("boom")):
            self.plain()
        self.turn("The gate", skill_reply("hike.add", meeting_point="The gate"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["hike.create"])

    def test_the_day_limit_counts_across_a_restart_and_then_the_plain_flow_runs(self):
        self.folder.mkdir(mode=0o700)
        saved = self.folder / "saved"
        saved.mkdir(mode=0o700)
        (saved / hl.COUNT_FILE).write_text(json.dumps({"counts": {self.now.date().isoformat(): hl.MAX_PER_DAY}}), "utf-8")
        self.plain()
        self.assertEqual(FakeFetch.requests, [])  # over the 60 for today: not one request, and no number said
        self.assertEqual(json.loads((saved / hl.COUNT_FILE).read_text("utf-8"))["counts"], {self.now.date().isoformat(): hl.MAX_PER_DAY})

    def test_a_draft_waiting_for_his_yes_means_no_question_that_a_bare_yes_could_answer(self):
        self.turn(LIVE1, skill_reply("hike.add", title="Mill Creek hike", day=SATURDAY, clock="08:00", meeting_point="Mill Creek trailhead"))
        self.assertEqual(self.live()["state"], "drafted")
        self.conv.requests.close_live(CHAT, self.now)  # the draft keeps waiting for his yes; a new request begins
        self.plain("add a hike on Bishop Peak Sunday at 9am", skill_reply("hike.add", title="Bishop Peak hike", day="2026-11-08", clock="09:00"))
        self.assertEqual((FakeFetch.made, FakeFetch.requests), ([], []))
        self.say("no")  # the bare no still cancels the waiting draft, as it always did
        self.replies()

    def test_with_no_setting_a_bare_yes_is_what_it_always_was(self):
        self.settings(None)
        self.plain()
        self.assertEqual((self.say("yes"), self.replies()), ("no-target", ["Nothing is waiting for your yes."]))

    def test_the_map_is_given_ninety_seconds_in_all_and_a_slow_answer_leaves_the_plain_flow(self):
        now = [0.0]  # the clock moves only when a server takes its time

        def slow_fetch(service, request):
            now[0] += 100.0  # the first answer comes after 100 seconds: more than the 90 for the lookup in all
            return FakeFetch("a@b.co")(service, request)
        cfg = {"contact": CONTACT, "folder": self.folder, "fetch": slow_fetch, "clock": lambda: now[0], "sleep": lambda s: None}
        ctx = SimpleNamespace(hike_lookup=cfg, now=self.now, texts=[ADD_BISHOP], multi_call=False, content=SimpleNamespace(
            community={"routeIdeas": [], "events": []}), today=self.now.date())
        result = hikes._look_up(cfg, "Bishop Peak hike", ctx)
        self.assertEqual(FakeFetch.requests, ["overpass"])  # the trail itself came; its place and climbing were not waited for
        self.assertEqual((result.status, result.candidates[0].place, result.candidates[0].gain_ft), ("one", "", None))
        self.assertIn("no climbing figure I trust", voice.plain(result.reply))

    def test_the_time_left_is_given_to_a_fetch_that_takes_it_and_not_to_one_that_does_not(self):
        seen = []

        class Takes:
            accepts_timeout = True

            def __call__(self, service, request, timeout=None):
                seen.append(timeout)
                return {}
        now = [0.0]
        transport = hl.CachedTransport(Takes(), self.folder / "t1", max_seconds=90.0, clock=lambda: now[0], sleep=lambda s: None)
        transport.begin_lookup()
        now[0] = 25.0
        transport.get("overpass", {"query": "a"})
        self.assertEqual(seen, [65.0])
        now[0] = 90.5  # nothing left: not even started
        with self.assertRaises(hl.TransportError) as caught:
            transport.get("nominatim_reverse", {"lat": 1})
        self.assertEqual((caught.exception.kind, seen), ("slow", [65.0]))
        plain = []
        other = hl.CachedTransport(lambda service, request: plain.append((service, request)) or {}, self.folder / "t2",
                                   max_seconds=90.0, clock=lambda: now[0], sleep=lambda s: None)
        other.begin_lookup()
        other.get("overpass", {"query": "a"})
        self.assertEqual(len(plain), 1)

    def test_the_pause_between_two_requests_cannot_use_up_the_time_and_still_start_one(self):
        now, seen = [0.0], []

        def sleep(seconds):
            now[0] += seconds

        class Takes:
            accepts_timeout = True

            def __call__(self, service, request, timeout=None):
                seen.append(timeout)
                return {}
        transport = hl.CachedTransport(Takes(), self.folder / "t3", max_seconds=90.0, clock=lambda: now[0], sleep=sleep)
        transport.begin_lookup()
        transport.get("overpass", {"query": "a"})
        now[0] = 89.9
        transport.limiter._last["overpass"] = 89.9  # the next one must wait MIN_INTERVAL_S: past the limit
        with self.assertRaises(hl.TransportError) as caught:
            transport.get("overpass", {"query": "b"})
        self.assertEqual((caught.exception.kind, len(seen)), ("slow", 1))

    def test_a_confirmed_trail_with_the_hikes_own_name_is_still_one_route_idea_and_one_hike(self):
        self.turn("add a hike on Bishop Peak Trail Saturday at 9am", skill_reply("hike.add", title="Bishop Peak Trail", day=SATURDAY, clock="09:00"))
        self.turn("yes", skill_reply("hike.add"))
        self.turn("Highland trailhead", skill_reply("hike.add", meeting_point="Highland trailhead"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["route.add", "hike.create"])
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        community = json.loads((self.repo.wt / "hass/content/community.json").read_text("utf-8"))
        self.assertEqual([r["title"] for r in community["routeIdeas"] if r["id"] == "idea-bishop-peak-trail"], ["Bishop Peak Trail"])

    def test_a_yes_to_one_trail_does_not_carry_over_when_the_hike_is_then_corrected_to_a_different_one(self):
        self.turn(ADD_BISHOP, BISHOP)
        self.turn("yes", skill_reply("hike.add"))
        disposition, [proposal] = self.turn("Actually make it Cerro San Luis, meet at Marsh Street trailhead", skill_reply(
            "hike.add", title="Cerro San Luis hike", meeting_point="Marsh Street trailhead"))
        self.assertEqual(disposition, "proposed")
        [hike] = self.last_ops()  # no route idea, no link to Bishop Peak's route
        self.assertEqual((hike["op"], hike["args"]["title"], "trailId" in hike["args"]), ("hike.create", "Cerro San Luis hike", False))
        self.assertNotIn("route idea", voice.plain(proposal))
        self.assertNotIn("2.4 miles", voice.plain(proposal))
        self.assertEqual(FakeFetch.requests, ["overpass", "nominatim_reverse", "elevation"])  # and the map was not asked again

    def test_a_correction_that_keeps_the_hike_named_keeps_the_yes_and_its_route_idea(self):
        self.turn(ADD_BISHOP, BISHOP)
        self.turn("yes", skill_reply("hike.add"))
        self.turn("Actually make it Bishop Peak, meet at the gate",
                  skill_reply("hike.add", title="Bishop Peak", meeting_point="the gate"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["route.add", "hike.create"])

    def test_a_route_idea_that_already_has_the_trails_name_is_linked_and_never_added_twice(self):
        found = hl.candidate_from_json({**hl.candidate_to_json(hl.lookup("Bishop Peak", hl.FixtureTransport(FIX / "bishop_peak.json"),
                                                                         today=date(2026, 11, 9)).candidates[0])})
        hike = {"op": "hike.create", "args": {"title": "Peak day", "date": SATURDAY, "time": "09:00", "meetingPoint": "gate", "rsvpEnabled": False}}
        ctx = lambda *routes: SimpleNamespace(content=SimpleNamespace(community={"routeIdeas": list(routes), "events": []}))  # noqa: E731
        listed = {"id": "idea-bishop-peak-listed", "title": "bishop  PEAK trail", "status": "idea"}
        self.assertEqual(hikes._with_route_idea(found, [hike], ctx(listed)), [{"op": "hike.create", "args": {**hike["args"], "trailId": listed["id"]}}])
        hidden = {**listed, "status": "hidden"}  # a hidden one is not a link target: a new idea is added, under the next free id
        route, linked = hikes._with_route_idea(found, [hike], ctx(hidden, {"id": "idea-bishop-peak-trail", "title": "Other", "status": "idea"}))
        self.assertEqual((route["op"], linked["args"]["trailId"]), ("route.add", "idea-bishop-peak-trail-2"))

    def test_only_a_plain_answer_is_taken_from_the_approval_path(self):
        self.turn(ADD_BISHOP, BISHOP)
        for text, taken in (("yes", True), ("No.", True), ("ok", True), ("1", True), ("yes a1b2", False), ("approve", False), ("cancel", False),
                            ("reject", False), ("no a1b2", False), ("yes please change the title", False), ("7", False), ("hours", False)):
            with self.subTest(text=text):
                self.assertEqual(self.conv.dispatch.takes_answer(text, self.now), taken)
        with mock.patch.object(self.conv, "skills_mode", "ops-only"):
            self.assertEqual(self.say("yes"), "no-target")  # skills off: a yes is only ever an approval
        self.replies()

    def test_an_answer_with_a_code_still_approves_and_cancel_still_cancels(self):
        self.turn(ADD_BISHOP, BISHOP)
        self.assertEqual(self.say("cancel"), "no-target")  # nothing was drafted: the same words as before the lookup existed
        self.replies()
        self.assertIsNone(self.live())  # and cancel dropped the open request


class SavedOffers(ChatCase):
    def test_an_offer_older_than_two_hours_or_not_exactly_ours_is_not_used(self):
        self.turn(ADD_BISHOP, BISHOP)
        [path] = self.offers()
        data = json.loads(path.read_text("utf-8"))
        for broken in ({**data, "v": 2}, {**data, "status": "maybe"}, {**data, "at": "garbage"}, {**data, "candidates": [{"name": 1}]},
                       {**data, "reply": 4}, {**data, "reasks": True}, {**data, "at": "2026-11-02T09:00:00"}):
            with self.subTest(broken=sorted(k for k in broken if broken[k] != data.get(k))):
                path.write_text(json.dumps(broken), "utf-8")
                self.assertIsNone(hikes._read_offer({"folder": self.folder}, [ADD_BISHOP], self.now))
        path.write_text("{not json", "utf-8")
        self.assertIsNone(hikes._read_offer({"folder": self.folder}, [ADD_BISHOP], self.now))
        path.write_text(json.dumps(data), "utf-8")
        self.assertIsNotNone(hikes._read_offer({"folder": self.folder}, [ADD_BISHOP], self.now))
        self.assertIsNone(hikes._read_offer({"folder": self.folder}, [ADD_BISHOP], self.now + timedelta(hours=2, seconds=1)))

    def test_a_damaged_offer_means_the_map_is_asked_again_from_the_saved_answers_with_no_new_request(self):
        self.turn(ADD_BISHOP, BISHOP)
        [path] = self.offers()
        path.write_text("{}", "utf-8")
        before = len(FakeFetch.requests)
        self.turn("yes", skill_reply("hike.add"))  # no readable offer: the plain question
        self.assertEqual(len(FakeFetch.requests), before)

    def test_old_offers_are_erased_when_a_new_one_is_written(self):
        self.turn(ADD_BISHOP, BISHOP)
        [old] = self.offers()
        stale = (self.now - timedelta(hours=25)).timestamp()
        os.utime(old, (stale, stale))
        self.fresh()
        self.turn(f"{ADD_BISHOP} again", BISHOP)
        self.assertNotIn(old, self.offers())
        self.assertEqual(len(self.offers()), 1)

    def test_the_offer_survives_a_restart_of_hass(self):
        self.turn(ADD_BISHOP, BISHOP)
        self.conv = self.open()
        self.turn("yes", skill_reply("hike.add"))
        self.turn("Highland trailhead", skill_reply("hike.add", meeting_point="Highland trailhead"))
        self.assertEqual([op["op"] for op in self.last_ops()], ["route.add", "hike.create"])


class Answers(unittest.TestCase):
    def test_how_short_replies_are_read(self):
        table = [("yes", 1, ("pick", 0)), ("Yes!", 1, ("pick", 0)), ("yeah that's it", 1, ("pick", 0)), ("ok", 1, ("pick", 0)),
                 ("1", 1, ("pick", 0)), ("the first one", 3, ("pick", 0)), ("2", 3, ("pick", 1)), ("number 3", 3, ("pick", 2)),
                 ("third", 3, ("pick", 2)), ("yes", 3, ("yes", None)), ("sure", 2, ("yes", None)),
                 ("4", 3, ("other", None)), ("0", 3, ("other", None)), ("2", 1, ("other", None)), ("22", 3, ("other", None)),
                 ("no", 3, ("no", None)), ("nope", 1, ("no", None)), ("no, the other one", 3, ("no", None)),
                 ("not that one", 2, ("no", None)), ("", 1, ("other", None)), ("yes and also bring lunch for everyone", 1, ("other", None)),
                 ("tell me more", 1, ("other", None)), ("yes sign up with 5 spots", 1, ("other", None)),
                 ("yes a1b2", 1, ("other", None)), ("no a1b2", 3, ("other", None)), ("no 4", 3, ("no", None)), ("yes dead", 1, ("other", None))]
        for text, offered, want in table:
            with self.subTest(text=text, offered=offered):
                self.assertEqual(hl.read_answer(text, offered), want)

    def test_a_candidate_goes_to_json_and_back_unchanged_and_a_damaged_one_is_refused(self):
        result = hl.lookup("Bishop Peak", hl.FixtureTransport(FIX / "bishop_peak.json"), today=date(2026, 11, 9))
        [c] = result.candidates
        back = hl.candidate_from_json(json.loads(json.dumps(hl.candidate_to_json(c))))
        self.assertEqual(back, c)
        self.assertEqual(back.record, c.record)
        data = hl.candidate_to_json(c)
        for field, bad in (("miles", "2.4"), ("miles", float("inf")), ("gain_ft", 7.5), ("gain_ft", True), ("shape", "zigzag"), ("osm", ["way/x"]),
                           ("osm", "way/1"), ("notes", "x"), ("stage", "mars"), ("stale", 1), ("record", []), ("retrieved", "yesterday"),
                           ("name", 5), ("score", "high")):
            with self.subTest(field=field, bad=bad):
                self.assertIsNone(hl.candidate_from_json({**data, field: bad}))
        self.assertIsNone(hl.candidate_from_json({k: v for k, v in data.items() if k != "name"}))
        self.assertIsNone(hl.candidate_from_json([data]))
        # an edited file that adds markup is cleaned again, and a number with no shape is dropped
        dirty = hl.candidate_from_json({**data, "name": "<b>Bishop</b> Peak\u200b", "shape": ""})
        self.assertEqual((dirty.name, dirty.miles, dirty.shape, dirty.sure), ("Bishop Peak", None, "", False))


class DayCountOnDisk(NoNetwork):
    def make(self, folder, raw, **kw):
        self.slept = []
        now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        return hl.CachedTransport(raw, folder, now=lambda: now, sleep=self.slept.append, **kw)

    def counted(self, folder):
        return json.loads((Path(folder) / hl.COUNT_FILE).read_text("utf-8"))["counts"]

    def test_the_count_is_written_before_the_request_and_survives_a_new_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = []

            def raw(service, request):
                seen.append(self.counted(tmp)["2026-11-09"])  # on disk already while the request is being made
                return {"answer": 1}

            first = self.make(tmp, raw, per_day=3)
            first.begin_lookup()
            first.get("overpass", {"query": "a"})
            self.assertEqual(seen, [1])
            second = self.make(tmp, raw, per_day=3)  # Hass restarted
            second.begin_lookup()
            second.get("overpass", {"query": "b"})
            second.get("overpass", {"query": "c"})
            with self.assertRaises(hl.TransportError) as ctx:
                second.get("overpass", {"query": "d"})
            self.assertEqual(ctx.exception.kind, "budget")
            self.assertEqual((self.counted(tmp), seen), ({"2026-11-09": 3}, [1, 2, 3]))
            third = self.make(tmp, raw, per_day=3)
            third.begin_lookup()
            with self.assertRaises(hl.TransportError):
                third.get("overpass", {"query": "e"})  # a new client does not start from zero

    def test_a_saved_answer_costs_nothing_and_a_new_day_starts_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = mock.Mock(return_value={"answer": 1})
            t = self.make(tmp, raw, per_day=1)
            t.begin_lookup()
            t.get("overpass", {"query": "a"})
            t.get("overpass", {"query": "a"})  # saved: no request, no count
            self.assertEqual((raw.call_count, self.counted(tmp)), (1, {"2026-11-09": 1}))
            tomorrow = hl.CachedTransport(raw, tmp, now=lambda: datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc), sleep=lambda s: None, per_day=1)
            tomorrow.begin_lookup()
            tomorrow.get("overpass", {"query": "b"})
            self.assertEqual(self.counted(tmp), {"2026-11-09": 1, "2026-11-10": 1})

    def test_only_the_last_seven_days_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).mkdir(exist_ok=True)
            (Path(tmp) / hl.COUNT_FILE).write_text(json.dumps({"counts": {f"2026-10-{d:02d}": 1 for d in range(1, 21)}}), "utf-8")
            t = self.make(tmp, lambda s, r: {"answer": 1})
            t.begin_lookup()
            t.get("overpass", {"query": "a"})
            self.assertEqual(len(self.counted(tmp)), hl.COUNT_DAYS_KEPT)
            self.assertEqual(self.counted(tmp)["2026-11-09"], 1)

    def test_a_damaged_count_file_fails_closed_for_the_day_is_set_aside_and_heals_tomorrow(self):
        for damage in ("{not json", json.dumps({"counts": {"2026-11-09": -1}}), json.dumps({"counts": {"2026-11-09": True}}),
                       json.dumps({"counts": {"someday": 1}}), json.dumps({"counts": []}), json.dumps([1]), "\u0000"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / hl.COUNT_FILE).write_text(damage, "utf-8")
                raw = mock.Mock(return_value={"answer": 1})
                t = self.make(tmp, raw)
                t.begin_lookup()
                for query in ("a", "b"):  # not just the first call: the damage is written over, so the second call is refused too
                    with self.assertRaises(hl.TransportError) as ctx:
                        t.get("overpass", {"query": query})
                    self.assertEqual(ctx.exception.kind, "budget")
                self.assertEqual(raw.call_count, 0)
                self.assertTrue((Path(tmp) / "day-count.bad").exists())
                tomorrow = hl.CachedTransport(raw, tmp, now=lambda: datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc), sleep=lambda s: None)
                tomorrow.begin_lookup()
                tomorrow.get("overpass", {"query": "c"})
                self.assertEqual(raw.call_count, 1)

    def test_a_count_that_cannot_be_written_means_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = mock.Mock(return_value={"answer": 1})
            t = self.make(Path(tmp) / "saved", raw)
            t.begin_lookup()
            with mock.patch.object(Path, "write_text", side_effect=OSError("disk full")):
                with self.assertRaises(hl.TransportError) as ctx:
                    t.get("overpass", {"query": "a"})
            self.assertEqual((ctx.exception.kind, raw.call_count), ("budget", 0))

    def test_when_over_the_limit_an_older_saved_answer_is_still_given_marked_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = mock.Mock(return_value={"answer": 1})
            t = self.make(tmp, raw, per_day=1)
            t.begin_lookup()
            t.get("elevation", {"points": [[1, 2]]})
            later = hl.CachedTransport(raw, tmp, now=lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc) + timedelta(days=400),
                                       sleep=lambda s: None, per_day=1)
            later.begin_lookup()
            later.get("overpass", {"query": "x"})  # today's one request
            r = later.get("elevation", {"points": [[1, 2]]})
            self.assertEqual((r.stale, r.body, raw.call_count), (True, {"answer": 1}, 2))


class LiveClient(NoNetwork):
    """``hike_fetch.LiveFetch`` with a fake ``urlopen``: no socket is ever opened."""

    class Resp:
        def __init__(self, body, on_read=None):
            self.body, self.on_read = body, on_read

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            if self.on_read:
                self.on_read()
            out, self.body = (self.body, b"") if n < 0 else (self.body[:n], self.body[n:])
            return out

    def fetch(self, body=b"{}", contact=CONTACT, error=None):
        self.opened = []

        def opener(req, timeout=None):
            self.opened.append((req, timeout))
            if error:
                raise error
            return self.Resp(body)

        return hike_fetch.LiveFetch(contact, opener=opener)

    def test_a_request_that_starts_inside_the_ninety_seconds_is_not_let_run_past_them(self):
        now, timeouts = [0.0], []
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)

        def opener(req, timeout=None):  # a server that answers only after 100 seconds, on a clock that counts only what is waited
            timeouts.append(timeout)
            if "overpass" in req.full_url:
                now[0] += 80
                return LiveClient.Resp(b'{"elements": []}')
            now[0] += min(timeout, 100)
            raise TimeoutError()
        cfg = {"contact": CONTACT, "folder": folder, "fetch": hike_fetch.LiveFetch(CONTACT, opener=opener),
               "clock": lambda: now[0], "sleep": lambda s: None}
        ctx = SimpleNamespace(hike_lookup=cfg, now=NOW, texts=[ADD_BISHOP], multi_call=False, content=SimpleNamespace(
            community={"routeIdeas": [], "events": []}), today=NOW.date())
        result = hikes._look_up(cfg, "Bishop Peak hike", ctx)
        self.assertEqual((result.status, result.failure, result.candidates), ("unavailable", "slow", ()))  # nothing offered: the plain flow
        self.assertEqual(timeouts[0], hike_fetch.TIMEOUT_S)  # the first request has the usual limit (90 s left, more than 60)
        self.assertEqual(timeouts[1], 10)  # the second starts at 80 s: it is given the 10 seconds left, not another 60
        self.assertLessEqual(now[0], hikes.LOOKUP_SECONDS)  # the chat was never kept waiting past the 90 seconds
        self.assertEqual(len(timeouts), 2)  # and no third request was started

    def test_a_body_that_trickles_in_is_cut_off_at_the_time_limit(self):
        now = [0.0]

        def tick():  # every read succeeds quickly (no socket timeout) but the clock moves 10 s each time
            now[0] += 10

        client = hike_fetch.LiveFetch(CONTACT, opener=lambda req, timeout=None: LiveClient.Resp(b"x" * 10_000_000, tick),
                                      clock=lambda: now[0])
        with self.assertRaises(hike_fetch.hl.TransportError) as cm:
            client("overpass", {"query": "q"}, timeout=30)
        self.assertEqual(cm.exception.kind if hasattr(cm.exception, "kind") else cm.exception.args[0], "slow")
        self.assertLessEqual(now[0], 40)

    def test_a_read_that_never_returns_is_cut_off_at_the_time_limit(self):
        import threading
        import time as real_time
        release = threading.Event()
        self.addCleanup(release.set)

        class Stuck(LiveClient.Resp):  # one read that stays blocked inside the receive loop (bytes trickling in)
            def read(self, n=-1):
                release.wait(30)
                return b""

        def stuck_headers(req, timeout=None):  # headers that never arrive
            release.wait(30)
            raise TimeoutError()

        for opener in (lambda req, timeout=None: Stuck(b""), stuck_headers):
            with self.subTest(opener=opener):
                client = hike_fetch.LiveFetch(CONTACT, opener=opener)
                started = real_time.monotonic()
                with self.assertRaises(hike_fetch.hl.TransportError) as cm:
                    client("overpass", {"query": "q"}, timeout=0.3)
                self.assertEqual(cm.exception.kind, "slow")
                self.assertLess(real_time.monotonic() - started, 5)

    def test_no_contact_no_client_and_none_is_built_in(self):
        for bad in (None, "", "nobody", "http://insecure.example.com", "a b@example.com"):
            with self.subTest(contact=bad), self.assertRaises(ValueError):
                hike_fetch.LiveFetch(bad)
        source = Path(hike_fetch.__file__).read_text("utf-8")
        self.assertNotIn("@", source.replace("[A-Za-z0-9._%+-]+@", ""))

    def test_the_user_agent_names_the_app_and_the_operators_contact(self):
        client = self.fetch(b'{"elements": []}')
        self.assertEqual(client("overpass", {"query": "q"}), {"elements": []})
        req, timeout = self.opened[0]
        self.assertEqual(req.get_header("User-agent"), f"avocado-shack-hass-hike-lookup/0.1 (contact: {CONTACT})")
        self.assertEqual((req.full_url, timeout), (hike_fetch.ENDPOINTS["overpass"], hike_fetch.TIMEOUT_S))
        self.assertTrue(req.data.startswith(b"data="))

    def test_each_service_goes_to_its_own_https_address_with_only_what_it_needs(self):
        client = self.fetch()
        client("nominatim_search", {"q": "bishop peak", "limit": 10})
        client("nominatim_reverse", {"lat": 35.3, "lon": -120.7, "zoom": 12})
        client("elevation", {"points": [[-120.7, 35.3]]})
        urls = [req.full_url for req, _t in self.opened]
        self.assertTrue(urls[0].startswith(hike_fetch.ENDPOINTS["nominatim_search"] + "?q=bishop+peak"))
        self.assertTrue(urls[1].startswith(hike_fetch.ENDPOINTS["nominatim_reverse"] + "?"))
        self.assertEqual(urls[2], hike_fetch.ENDPOINTS["elevation"])
        self.assertTrue(all(u.startswith("https://") for u in urls))
        self.assertIsNone(self.opened[0][0].data)
        self.assertIn(b"esriGeometryMultipoint", self.opened[2][0].data)

    def test_every_failure_is_one_of_the_documented_kinds(self):
        import http.client
        import urllib.error
        http_error = lambda code: urllib.error.HTTPError("https://x", code, "m", {}, None)  # noqa: E731
        cases = [(http_error(429), "busy"), (http_error(503), "busy"), (http_error(504), "busy"), (http_error(500), "network"),
                 (TimeoutError(), "slow"), (urllib.error.URLError("timed out"), "slow"), (urllib.error.URLError("refused"), "network"),
                 (ConnectionResetError(), "network"), (http.client.IncompleteRead(b"x"), "bad")]
        for error, kind in cases:
            with self.subTest(error=repr(error)):
                with self.assertRaises(hl.TransportError) as ctx:
                    self.fetch(error=error)("overpass", {"query": "q"})
                self.assertEqual(ctx.exception.kind, kind)
        for body in (b"not json", b"\xff\xfe", b"[" * 100000):
            with self.subTest(body=body[:10]):
                with self.assertRaises(hl.TransportError) as ctx:
                    self.fetch(body)("overpass", {"query": "q"})
                self.assertEqual(ctx.exception.kind, "bad")
        with self.assertRaises(hl.TransportError) as ctx:
            self.fetch(b" " * (hike_fetch.MAX_BODY_BYTES + 10))("overpass", {"query": "q"})
        self.assertEqual(ctx.exception.kind, "bad")

    def test_the_real_dispatcher_hands_the_operators_setting_and_the_state_folder_to_the_plan(self):
        ctx = SimpleNamespace(hike_lookup={"contact": CONTACT, "folder": Path("/x")})
        self.assertIsNotNone(hikes._lookup_cfg(ctx))
        for bad in (None, {}, {"contact": "nobody", "folder": "/x"}, {"contact": CONTACT}, {"contact": CONTACT, "folder": 5}):
            self.assertIsNone(hikes._lookup_cfg(SimpleNamespace(hike_lookup=bad)))
        self.assertIsNone(hikes._lookup_cfg(SimpleNamespace()))  # a context from before this card has no setting: off
        self.assertIn("hike_lookup", dispatch.Ctx.__init__.__code__.co_varnames)


class SpacingAndReservation(NoNetwork):
    """Review of PR #810: the spacing between requests to one server holds across lookups (a new transport per chat lookup) and across
    the two Nominatim calls, and the 60-a-day count is a locked check-add-write that two clients of one folder cannot both win."""

    class Clock:
        def __init__(self):
            self.t, self.slept = 1000.0, []

        def sleep(self, s):
            self.slept.append(s)
            self.t += s

        def monotonic(self):
            self.t += 0.01
            return self.t

    NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

    def make(self, folder, raw, clock=None, **kw):
        clock = clock or self.Clock()
        return hl.CachedTransport(raw, folder, now=lambda: self.NOW, sleep=clock.sleep, clock=clock.monotonic, **kw)

    def test_a_new_transport_given_the_shared_limiter_still_waits_for_the_last_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, limiter = self.Clock(), hl.SpacingLimiter()
            raw = mock.Mock(return_value={"answer": 1})
            for query in ("a", "b", "c"):  # three lookups, each with a transport of its own
                t = self.make(tmp, raw, clock, limiter=limiter)
                t.begin_lookup()
                t.get("overpass", {"query": query})
            self.assertEqual(raw.call_count, 3)
            self.assertEqual(len(clock.slept), 2)
            self.assertTrue(all(s >= hl.MIN_INTERVAL_S["overpass"] - 0.1 for s in clock.slept), clock.slept)

    def test_without_a_shared_limiter_each_transport_is_on_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = self.Clock()
            raw = mock.Mock(return_value={"answer": 1})
            for query in ("a", "b"):
                self.make(tmp, raw, clock).get("overpass", {"query": query})
            self.assertEqual(clock.slept, [])  # the default is private: only the chat opts in to sharing

    def test_nominatim_search_then_reverse_is_one_server_and_one_spacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, limiter = self.Clock(), hl.SpacingLimiter()
            raw = mock.Mock(return_value={"answer": 1})
            first, second = self.make(tmp, raw, clock, limiter=limiter), self.make(tmp, raw, clock, limiter=limiter)
            first.get("nominatim_search", {"q": "bishop"})
            second.get("nominatim_reverse", {"lat": 1, "lon": 2})
            self.assertEqual(len(clock.slept), 1)
            self.assertGreaterEqual(clock.slept[0], hl.MIN_INTERVAL_S["nominatim_search"] - 0.1)
            second.get("overpass", {"query": "x"})  # a different server: no wait for Nominatim
            second.get("elevation", {"points": [[1, 2]]})
            self.assertEqual(len(clock.slept), 1)
            self.assertEqual(hl.SERVICE_HOST["nominatim_search"], hl.SERVICE_HOST["nominatim_reverse"])
            self.assertEqual(sorted(hl.SERVICE_HOST), sorted(hl.MIN_INTERVAL_S))

    def test_a_failed_request_still_counts_for_the_spacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, limiter = self.Clock(), hl.SpacingLimiter()
            bad = mock.Mock(side_effect=hl.TransportError("busy"))
            with self.assertRaises(hl.TransportError):
                self.make(tmp, bad, clock, limiter=limiter).get("nominatim_search", {"q": "a"})
            self.make(tmp, mock.Mock(return_value={"answer": 1}), clock, limiter=limiter).get("nominatim_reverse", {"lat": 1, "lon": 2})
            self.assertEqual(len(clock.slept), 1)

    def test_the_chat_gives_every_lookup_the_one_limiter_of_its_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = self.Clock()
            raw = mock.Mock(return_value={"answer": 1})
            cfg = {"contact": CONTACT, "folder": tmp, "fetch": raw, "sleep": clock.sleep, "clock": clock.monotonic}
            ctx = SimpleNamespace(now=self.NOW)
            for query in ("a", "b"):  # what ``_look_up`` does for each chat lookup: a new transport every time
                t = hikes._make_transport(cfg, ctx)
                t.begin_lookup()
                t.get("nominatim_search", {"q": query})
            self.assertEqual(len(clock.slept), 1)
            self.assertGreaterEqual(clock.slept[0], hl.MIN_INTERVAL_S["nominatim_search"] - 0.1)
            self.assertIs(hl.shared_limiter(clock.monotonic), hl.shared_limiter(clock.monotonic))
            self.assertIsNot(hl.shared_limiter(clock.monotonic), hl.shared_limiter(self.Clock().monotonic))

    class Takes:
        """A fetch that takes the time left and remembers it."""
        accepts_timeout = True

        def __init__(self):
            self.seen = []

        def __call__(self, service, request, timeout=None):
            self.seen.append(timeout)
            return {}

    def test_time_spent_reserving_the_request_is_taken_off_what_the_fetch_is_given(self):
        for start, delay, expected in ((80.0, 2.0, [8.0]), (89.0, 2.0, [])):  # 2 s in the day count: 8 s left, or nothing left at 91 s
            with self.subTest(start=start), tempfile.TemporaryDirectory() as tmp:
                now, fetch = [0.0], self.Takes()
                transport = hl.CachedTransport(fetch, tmp, now=lambda: self.NOW, sleep=lambda s: None, clock=lambda: now[0], max_seconds=90.0)
                transport.begin_lookup()
                now[0] = start
                reserve = transport._reserve

                def slow_reserve(today, reserve=reserve):
                    ok = reserve(today)
                    now[0] += delay  # the day-count lock took this long
                    return ok
                transport._reserve = slow_reserve
                if expected:
                    transport.get("overpass", {"query": "a"})
                else:
                    with self.assertRaises(hl.TransportError) as caught:
                        transport.get("overpass", {"query": "a"})
                    self.assertEqual(caught.exception.kind, "slow")
                self.assertEqual(fetch.seen, expected)  # never the 10 s that were left before the reservation

    def test_a_server_busy_with_another_request_cannot_hold_a_lookup_past_its_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            limiter, fetch = hl.SpacingLimiter(), self.Takes()
            entered, release = threading.Event(), threading.Event()

            def other_lookup():  # a request to the same server that is still running
                with limiter.hold("overpass", lambda: 0.0, lambda s: None):
                    entered.set()
                    release.wait(30)
            holder = threading.Thread(target=other_lookup)
            holder.start()
            try:
                self.assertTrue(entered.wait(30))
                transport = hl.CachedTransport(fetch, tmp, now=lambda: self.NOW, sleep=lambda s: None, clock=lambda: 89.8,
                                               max_seconds=90.0, limiter=limiter)
                transport.began = 0.0  # 0.2 s of the lookup are left
                began = time.monotonic()
                with self.assertRaises(hl.TransportError) as caught:
                    transport.get("overpass", {"query": "a"})
                self.assertLess(time.monotonic() - began, 10)  # it waited about 0.2 s, not until the other request was done
                self.assertEqual((caught.exception.kind, fetch.seen), ("slow", []))
            finally:
                release.set()
                holder.join(30)
            self.assertFalse(holder.is_alive())

    def test_a_spacing_wait_that_would_end_past_the_time_is_not_slept(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock, fetch = self.Clock(), self.Takes()
            transport = self.make(tmp, fetch, clock, max_seconds=1.0, limiter=hl.SpacingLimiter())
            transport.begin_lookup()
            transport.get("overpass", {"query": "a"})
            with self.assertRaises(hl.TransportError) as caught:  # the next one must wait MIN_INTERVAL_S, more than the 1 s in all
                transport.get("overpass", {"query": "b"})
            self.assertEqual((caught.exception.kind, len(fetch.seen), clock.slept), ("slow", 1, []))

    def start_all(self, threads):
        for th in threads:
            th.start()
        for th in threads:
            th.join(30)
            self.assertFalse(th.is_alive())

    def test_two_clients_cannot_both_take_the_last_request_of_the_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp).mkdir(exist_ok=True)
            (Path(tmp) / hl.COUNT_FILE).write_text(json.dumps({"counts": {"2026-11-09": hl.MAX_PER_DAY - 1}}), "utf-8")
            barrier, results, fetched = threading.Barrier(2), [], []

            def fetch(service, request):
                fetched.append(request)
                return {"answer": 1}

            def client(query):
                t = self.make(tmp, fetch)
                t.begin_lookup()
                barrier.wait(10)
                try:
                    t.get("overpass", {"query": query})
                    results.append("fetched")
                except hl.TransportError as exc:
                    results.append(exc.kind)

            self.start_all([threading.Thread(target=client, args=(q,)) for q in ("a", "b")])
            self.assertEqual(sorted(results), ["budget", "fetched"])
            self.assertEqual(len(fetched), 1)
            self.assertEqual(json.loads((Path(tmp) / hl.COUNT_FILE).read_text("utf-8"))["counts"], {"2026-11-09": hl.MAX_PER_DAY})

    def test_many_clients_lose_no_increments_and_never_pass_the_day_limit(self):
        for per_day, clients, each in ((60, 8, 5), (10, 8, 5)):
            with self.subTest(per_day=per_day), tempfile.TemporaryDirectory() as tmp:
                barrier, fetched, lock = threading.Barrier(clients), [], threading.Lock()

                def fetch(service, request):
                    with lock:
                        fetched.append(request)
                    return {"answer": 1}

                def client(n):
                    t = self.make(tmp, fetch, per_day=per_day, per_lookup=each)
                    t.begin_lookup()
                    barrier.wait(10)
                    for i in range(each):
                        try:
                            t.get("overpass", {"query": f"{n}-{i}"})
                        except hl.TransportError as exc:
                            self.assertEqual(exc.kind, "budget")

                self.start_all([threading.Thread(target=client, args=(n,)) for n in range(clients)])
                want = min(per_day, clients * each)
                self.assertEqual(len(fetched), want)
                self.assertEqual(json.loads((Path(tmp) / hl.COUNT_FILE).read_text("utf-8"))["counts"], {"2026-11-09": want})
                self.assertEqual([p.name for p in Path(tmp).glob("day-count*.tmp")], [])  # no writer left its temp file behind

    def test_the_count_lock_is_a_real_cross_client_lock_and_a_busy_one_means_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = mock.Mock(return_value={"answer": 1})
            t = self.make(tmp, raw)
            t.begin_lookup()
            fd = os.open(Path(tmp) / hl.COUNT_LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)  # another client is in the middle of writing the count
                with mock.patch.object(hl, "COUNT_LOCK_SECONDS", 0.05), self.assertRaises(hl.TransportError) as ctx:
                    t.get("overpass", {"query": "a"})
                self.assertEqual((ctx.exception.kind, raw.call_count), ("budget", 0))
            finally:
                os.close(fd)
            t.get("overpass", {"query": "a"})  # the lock is gone: the same request goes through and is counted
            self.assertEqual((raw.call_count, t.day_count()), (1, 1))

    def test_no_file_locking_means_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = mock.Mock(return_value={"answer": 1})
            t = self.make(tmp, raw)
            t.begin_lookup()
            with mock.patch.object(hl, "fcntl", None), self.assertRaises(hl.TransportError) as ctx:
                t.get("overpass", {"query": "a"})
            self.assertEqual((ctx.exception.kind, raw.call_count), ("budget", 0))

    def test_the_cached_answer_files_are_written_under_names_no_other_writer_uses(self):
        with tempfile.TemporaryDirectory() as tmp:
            names = set()
            real = hl._unique_tmp
            with mock.patch.object(hl, "_unique_tmp", side_effect=lambda p: names.add(real(p)) or real(p)):
                self.make(tmp, lambda s, r: {"answer": 1}).get("overpass", {"query": "a"})
            self.assertTrue(names and all(str(os.getpid()) in n.name and n.name.endswith(".tmp") for n in names))
            self.assertEqual(len({n.name for n in names}), len(names))


class Declaration(unittest.TestCase):
    def test_the_skill_declaration_and_its_prompt_are_unchanged_by_the_lookup(self):
        names = [s.name for s in hikes.ADD.slots]
        self.assertEqual(names, ["title", "day", "clock", "meeting_point", "signup", "capacity", "no_limit", "trail", "difficulty",
                                 "distance", "duration", "bring", "access_note", "description"])
        self.assertTrue(callable(hikes.question))
        self.assertIsNone(hikes.question("clock", {"title": "Bishop Peak hike"}, SimpleNamespace()))
        self.assertIsNone(hikes.question("meeting_point", {"title": "Bishop Peak hike"}, SimpleNamespace()))  # no setting in the context: off


if __name__ == "__main__":
    unittest.main()
