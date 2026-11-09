"""HASS-HIKE-LOOKUP-1 tests: the offline hike-lookup prototype (hass/hike_lookup.py).

No live network: the recorded answers in hass/tests/fixtures/hike_lookup/ stand in for OpenStreetMap and USGS (recorded
2026-11-09 with scripts/hike_lookup_manual.py), and every test blocks sockets. Design: docs/hass/HIKE-LOOKUP.md.
Run: python3 -m unittest hass.tests.test_hike_lookup -v
"""

import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import claims, hike_lookup as hl, voice
from hass.content_model import TEXT_LIMITS, _text
from hass.ops.routes import _route_add
from hass.tests.test_hike_ops import HikeTestCase

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures" / "hike_lookup"
TODAY = date(2026, 11, 9)
RECORDED = date(2026, 11, 9)


def fixture(slug):
    return hl.FixtureTransport(FIX / f"{slug}.json")


def said(result):
    return voice.plain(result.reply)


class Spy:
    """Wraps a transport and keeps every request that would have gone out."""

    def __init__(self, inner):
        self.inner, self.sent = inner, []

    def get(self, service, request):
        self.sent.append((service, request))
        return self.inner.get(service, request)


class NoNetwork(unittest.TestCase):
    def setUp(self):
        def refuse(*_a, **_k):
            raise AssertionError("a test tried to use the network")
        for target in ("socket.socket.connect", "socket.create_connection", "socket.getaddrinfo"):
            patcher = mock.patch(target, refuse)
            patcher.start()
            self.addCleanup(patcher.stop)


# -- the five required cases, replayed from recorded answers ------------------------------------------------------------


class RecordedCases(NoNetwork):
    def test_every_fixture_is_labelled_and_was_recorded_live(self):
        names = {p.stem: json.loads(p.read_text("utf-8"))["meta"] for p in FIX.glob("*.json")}
        for required in ("bishop_peak", "cerro_san_luis", "point_buchon", "bluff_trail", "no_match"):
            self.assertIn(required, names)
        for slug, meta in names.items():
            self.assertEqual(meta["provenance"], "recorded live", slug)
            self.assertEqual(meta["recorded"], RECORDED.isoformat(), slug)

    def test_bishop_peak_one_trail_out_and_back_to_the_summit(self):
        spy = Spy(fixture("bishop_peak"))
        result = hl.lookup("Bishop Peak", spy, today=TODAY)
        self.assertEqual((result.status, result.total, len(result.candidates)), ("one", 1, 1))
        c = result.candidates[0]
        self.assertEqual((c.name, c.miles, c.gain_ft, c.shape, c.basis), ("Bishop Peak Trail", 2.4, 740, "out-and-back", "summit end"))
        self.assertEqual((c.source, c.retrieved, c.place, c.osm), (hl.SOURCE_NAME, RECORDED, "San Luis Obispo County", ("way/175094087",)))
        self.assertEqual(said(result), 'Did you mean Bishop Peak Trail in San Luis Obispo County, about 2.4 miles out and back on the map, '
                                       'with about 740 feet of climbing? Reply yes to use it, or no and tell me more.')
        self.assertEqual([s for s, _r in spy.sent], ["overpass", "nominatim_reverse", "elevation"])  # three requests, no more

    def test_distance_comes_from_the_route_line_and_rounds_to_a_tenth(self):
        result = hl.lookup("Bishop Peak", fixture("bishop_peak"), today=TODAY)
        c = result.candidates[0]
        one_way = c.record["one_way_m"]
        self.assertAlmostEqual(one_way, 1944.9, places=1)  # haversine sum of the 188 recorded points
        self.assertEqual(c.miles, round(2 * one_way / hl.M_PER_MILE, 1))
        self.assertEqual(f"{c.miles:.1f}", "2.4")

    def test_cerro_san_luis_two_named_pieces_are_chained(self):
        result = hl.lookup("Cerro San Luis", fixture("cerro_san_luis"), today=TODAY)
        c = result.candidates[0]
        self.assertEqual(result.status, "one")
        self.assertEqual((c.name, c.miles, c.gain_ft, c.shape), ("Cerro San Luis", 2.6, 680, "out-and-back"))
        self.assertEqual(set(c.osm), {"way/186338280", "way/464173192"})  # Fire Road + Connector Trail, joined at one point
        self.assertEqual(c.record["bridge_m"], 0)  # joined by a shared point, no guessed gap
        self.assertIn("Did you mean Cerro San Luis in San Luis Obispo County, about 2.6 miles out and back", said(result))

    def test_point_buchon_is_not_sure_and_gives_no_number(self):
        result = hl.lookup("Point Buchon", fixture("point_buchon"), today=TODAY)
        self.assertEqual((result.status, len(result.candidates)), ("unsure", 1))
        c = result.candidates[0]
        self.assertEqual((c.miles, c.gain_ft, c.shape, c.sure), (None, None, "", False))
        self.assertEqual(c.unsure, "the trail has a loop with extra trail attached")
        text = said(result)
        self.assertIn("I'm not sure", text)
        self.assertIn("I won't guess", text)
        self.assertNotRegex(text, r"\d")  # no distance, no climb
        with self.assertRaises(ValueError):
            hl.route_add_args(c)  # never turned into a route idea

    def test_valencia_peak_branches_are_not_sure_too(self):
        result = hl.lookup("Valencia Peak", fixture("valencia_peak"), today=TODAY)
        self.assertEqual((result.status, result.candidates[0].shape), ("unsure", ""))
        self.assertEqual(result.candidates[0].record["bridge_m"], 25.9)  # the one same-name gap is counted, not hidden

    def test_ambiguous_name_offers_three_and_asks_which(self):
        result = hl.lookup("Bluff Trail", fixture("bluff_trail"), today=TODAY)
        self.assertEqual((result.status, result.total, len(result.candidates)), ("several", 3, 3))
        self.assertEqual([c.place for c in result.candidates], ["Cambria", "Pismo Beach", "San Luis Obispo County"])
        self.assertEqual([c.sure for c in result.candidates], [True, True, False])  # a known distance comes before an unknown one
        text = said(result)
        self.assertTrue(text.startswith("I found 3 that fit. Which one do you mean? 1. Bluff trail near Cambria, about 0.9 miles one way on the map"))
        self.assertIn("2. Shell Beach Bluff Trail near Pismo Beach", text)
        self.assertIn("3. Bluff Trail in San Luis Obispo County, and I'm not sure of its distance", text)
        self.assertTrue(text.endswith("Reply 1, 2 or 3, or no if it isn't one of these."))
        self.assertEqual(result.candidates[0].shape, "point-to-point")  # an open line with no summit is one way, never assumed out and back
        self.assertIn("from the lower end", text)

    def test_never_more_than_the_offer_limit(self):
        result = hl.lookup("Bluff Trail", fixture("bluff_trail"), today=TODAY, max_offer=2)
        self.assertEqual((result.total, len(result.candidates)), (3, 2))
        self.assertIn("There are more than 2 that fit; tell me more of the name if none is right.", said(result))
        self.assertTrue(said(result).count("Reply 1 or 2"))

    def test_no_match_says_so_and_invents_nothing(self):
        spy = Spy(fixture("no_match"))
        result = hl.lookup("Mount Doom Trail", spy, today=TODAY)
        self.assertEqual((result.status, result.candidates, result.total), ("none", (), 0))
        self.assertEqual(said(result), "I couldn't find a trail called Mount Doom Trail on the map. I won't guess. "
                                       "Could you say it another way, or tell me the park or trailhead it is near?")
        self.assertEqual([s for s, _r in spy.sent], ["overpass", "nominatim_search"])  # county first, then California

    def test_outside_the_county_a_peak_with_no_mapped_trail_is_a_place_not_a_hike(self):
        spy = Spy(fixture("mission_peak"))
        result = hl.lookup("Mission Peak", spy, today=TODAY)
        self.assertEqual((result.status, result.candidates), ("place_only", ()))
        self.assertEqual(said(result), "I found a place called Mission Peak on the map, but no trail to it, so I can't give you a distance. "
                                       "Do you know how far it is?")
        self.assertEqual([s for s, _r in spy.sent], ["overpass", "nominatim_search"])  # county first, then California
        # the California search also returned a street called Mission Peak: a street is never offered as a trail
        body = json.loads((FIX / "mission_peak.json").read_text("utf-8"))["responses"]
        hits = next(v["body"] for k, v in body.items() if k.startswith("nominatim_search"))
        self.assertIn("residential", [h["type"] for h in hits])

    def test_every_reply_passes_the_voice_rules(self):
        for slug, name in (("bishop_peak", "Bishop Peak"), ("cerro_san_luis", "Cerro San Luis"), ("point_buchon", "Point Buchon"),
                           ("valencia_peak", "Valencia Peak"), ("bluff_trail", "Bluff Trail"), ("no_match", "Mount Doom Trail"),
                           ("mission_peak", "Mission Peak")):
            with self.subTest(slug):
                result = hl.lookup(name, fixture(slug), today=TODAY)
                self.assertEqual(voice.check(result.reply), [], voice.plain(result.reply))


# -- matching ---------------------------------------------------------------------------------------------------------------


class Matching(NoNetwork):
    def test_spoken_and_typed_names_become_the_same_words(self):
        self.assertEqual(hl.name_tokens("the Bishop Peak trail"), ["bishop", "peak"])
        self.assertEqual(hl.name_tokens("Mt. Tam hike"), ["mount", "tam"])
        self.assertEqual(hl.name_tokens("Pt Buchon"), ["point", "buchon"])
        self.assertEqual(hl.name_tokens("Montaña de Oro"), ["montana", "de", "oro"])
        self.assertEqual(hl.name_tokens("Bishop's Peak"), ["bishops", "peak"])

    def test_typos_still_match_but_other_names_do_not(self):
        tokens = hl.name_tokens("Bishup Peek")
        self.assertGreaterEqual(hl.name_score(tokens, "Bishop Peak Trail"), hl.MATCH_MIN)
        self.assertLess(hl.name_score(tokens, "Cerro San Luis"), hl.MATCH_MIN)
        self.assertEqual(hl.name_score(["bishop", "peak"], "Bishop Peak"), 1.0)
        self.assertLess(hl.name_score(["mist"], "Pacific Mist Court"), 0.9)  # extra words that are not trail words rank lower

    def test_search_pattern_is_loose_but_the_county_box_comes_first(self):
        self.assertEqual(hl.name_regex(["bishop", "peak"]), "bish.*peak")
        query = hl.overpass_query(["bishop", "peak"])
        self.assertIn("(34.9,-121.45,35.8,-119.4)", query)
        self.assertIn('way["highway"~"^(path|footway|track|bridleway|steps)$"]', query)  # trails, never streets
        self.assertEqual(hl.nominatim_search_request("Mission Peak")["bounded"], 1)

    def test_existing_route_ideas_are_used_before_any_lookup(self):
        ideas = json.loads((ROOT / "hass/content/community.json").read_text("utf-8"))["routeIdeas"]
        spy = Spy(fixture("no_match"))  # would fail with "missing" if it were asked anything
        result = hl.lookup("Point Buchon trail", spy, today=TODAY, route_ideas=ideas)
        self.assertEqual((result.status, result.idea_id, spy.sent), ("known", "idea-point-buchon", []))
        self.assertIn("You already have a route idea called Point Buchon, 6.6 miles.", said(result))
        self.assertEqual(voice.check(result.reply), [])
        self.assertIsNone(hl.known_route_idea("Bishop Peak", ideas))
        hidden = [dict(i, status="hidden") for i in ideas]
        self.assertIsNone(hl.known_route_idea("Point Buchon", hidden))

    def test_too_short_a_name_asks_for_one(self):
        spy = Spy(fixture("no_match"))
        result = hl.lookup("hike", spy, today=TODAY)
        self.assertEqual((result.status, spy.sent), ("none", []))
        self.assertEqual(said(result), "Which hike do you mean? Tell me its name, like Bishop Peak.")


# -- route chaining on made-up geometry ----------------------------------------------------------------------------------------


def line(points):
    return [{"lat": lat, "lon": lon} for lat, lon in points]


def way(ident, name, points, **tags):
    return {"type": "way", "id": ident, "tags": {"name": name, "highway": "path", **tags}, "geometry": line(points)}


def ring(lat=35.30, lon=-120.70, r=0.004, n=48):
    pts = [(lat + r * math.sin(2 * math.pi * k / n), lon + r * math.cos(2 * math.pi * k / n) / math.cos(math.radians(lat))) for k in range(n)]
    return pts + [pts[0]]


def straight(lat=35.30, lon=-120.70, metres=1500, n=31):
    d = metres / 111195 / (n - 1)
    return [(lat + d * k, lon) for k in range(n)]


class Synthetic:
    """Made-up map answers for the chaining rules (no recorded data involved)."""

    def __init__(self, elements, rise_per_sample=5.0):
        self.elements, self.rise, self.sent = elements, rise_per_sample, []

    def get(self, service, request):
        self.sent.append((service, request))
        if service == "overpass":
            return hl.Response({"elements": self.elements}, TODAY)
        if service == "nominatim_reverse":
            return hl.Response({"address": {"town": "Testville"}}, TODAY)
        if service == "elevation":
            pts = request["points"]
            return hl.Response({"samples": [{"locationId": i, "value": str(100 + self.rise * i)} for i in range(len(pts))]}, TODAY)
        raise hl.TransportError("missing", service)


class Chaining(NoNetwork):
    def run_one(self, elements, name="Test Trail Loop"):
        return hl.lookup(name, Synthetic(elements), today=TODAY)

    def test_haversine_one_degree_of_latitude(self):
        self.assertAlmostEqual(hl.haversine((35, -120), (36, -120)), 111195, delta=5)

    def test_closed_ring_is_a_loop_and_counts_once(self):
        pts = ring()
        result = self.run_one([way(1, "Test Trail Loop", pts)])
        c = result.candidates[0]
        circumference = sum(hl.haversine(a, b) for a, b in zip(pts, pts[1:]))
        self.assertEqual((c.shape, result.status), ("loop", "one"))
        self.assertEqual(c.miles, round(circumference / hl.M_PER_MILE, 1))
        self.assertIn("a loop on the map", said(result))

    def test_a_loop_in_two_pieces_still_closes(self):
        pts = ring()
        result = self.run_one([way(1, "Test Trail Loop", pts[:25]), way(2, "Test Trail Loop", pts[24:])])
        self.assertEqual(result.candidates[0].shape, "loop")

    def test_open_line_without_a_summit_is_one_way(self):
        result = self.run_one([way(1, "Creek Walk", straight())], "Creek Walk")
        c = result.candidates[0]
        self.assertEqual((c.shape, c.miles), ("point-to-point", 0.9))  # 1.5 km one way
        self.assertEqual(c.basis, "open line, no destination marked")

    def test_a_peak_name_or_a_summit_point_means_out_and_back_and_doubles_the_distance(self):
        by_name = self.run_one([way(1, "Hill Peak Trail", straight())], "Hill Peak")
        self.assertEqual((by_name.candidates[0].shape, by_name.candidates[0].miles, by_name.candidates[0].basis), ("out-and-back", 1.9, "destination name"))
        pts = straight()
        summit = {"type": "node", "id": 9, "lat": pts[-1][0] + 0.0004, "lon": pts[-1][1], "tags": {"name": "Creek Walk", "natural": "peak"}}
        by_node = self.run_one([way(1, "Creek Walk", pts), summit], "Creek Walk")
        self.assertEqual((by_node.candidates[0].shape, by_node.candidates[0].basis), ("out-and-back", "summit end"))

    def test_pieces_with_a_shared_point_chain_even_with_different_names(self):
        a, b = straight(), straight(lat=straight()[-1][0])
        result = self.run_one([way(1, "Test Trail Fire Road", a), way(2, "Test Trail Connector Trail", b)], "Test Trail")
        c = result.candidates[0]
        self.assertEqual((c.name, c.shape), ("Test Trail", "point-to-point"))
        self.assertEqual(c.miles, 1.9)

    def test_a_small_gap_between_same_name_pieces_is_bridged_and_counted_a_big_one_is_not(self):
        a = straight(metres=1500)
        near = straight(lat=a[-1][0] + 40 / 111195, metres=1500)  # 40 m gap: same trail
        far = straight(lat=a[-1][0] + 600 / 111195, metres=1500)  # 600 m gap: not one route
        joined = self.run_one([way(1, "Ridge Trail", a), way(2, "Ridge Trail", near)], "Ridge Trail").candidates[0]
        self.assertEqual(joined.record["bridge_m"], 40.0)
        self.assertEqual(joined.miles, 1.9)
        apart = hl.lookup("Ridge Trail", Synthetic([way(1, "Ridge Trail", a), way(2, "Ridge Trail", far)]), today=TODAY)
        self.assertEqual((apart.status, apart.total), ("several", 2))  # two separate trails: ask which

    def test_gaps_over_the_share_limit_say_not_sure(self):
        a = straight(metres=1000)
        b = straight(lat=a[-1][0] + 190 / 111195, metres=1000)  # 190 m gap is 8.7% of the 2.2 km: over the 8% limit
        c = self.run_one([way(1, "Gap Trail", a), way(2, "Gap Trail", b)], "Gap Trail").candidates[0]
        self.assertEqual(c.unsure, "the pieces do not join up")

    def test_a_small_spur_is_left_out_a_big_branch_is_not_sure(self):
        main = straight(metres=2000, n=41)
        spur = [main[20], (main[20][0], main[20][1] + 0.0010)]  # ~90 m side path
        c = self.run_one([way(1, "Spine Trail", main), way(2, "Spine Trail", spur)], "Spine Trail").candidates[0]
        self.assertTrue(c.sure)
        self.assertAlmostEqual(c.record["spur_m"], 92, delta=5)
        big = [main[20], (main[20][0], main[20][1] + 0.012)]  # ~1.1 km branch
        c = self.run_one([way(1, "Spine Trail", main), way(2, "Spine Trail", big)], "Spine Trail").candidates[0]
        self.assertEqual((c.sure, c.unsure), (False, "the trail branches in several places"))

    def test_a_loop_with_a_tail_is_not_sure(self):
        pts = ring()
        tail = [pts[0], (pts[0][0] + 0.004, pts[0][1])]
        c = self.run_one([way(1, "Lolly Trail", pts), way(2, "Lolly Trail", tail)], "Lolly Trail").candidates[0]
        self.assertEqual(c.unsure, "the trail has a loop with extra trail attached")

    def test_a_relation_is_one_trail_from_its_member_ways(self):
        a, b = straight(), straight(lat=straight()[-1][0])
        rel = {"type": "relation", "id": 7, "tags": {"name": "Ridge Route", "route": "hiking"},
               "members": [{"type": "way", "ref": 1, "geometry": line(a)}, {"type": "way", "ref": 2, "geometry": line(b)}]}
        c = self.run_one([rel], "Ridge Route").candidates[0]
        self.assertEqual((c.osm, c.shape, c.miles), (("relation/7",), "point-to-point", 1.9))
        self.assertEqual(hl.source_url(c), "https://www.openstreetmap.org/relation/7")

    def test_a_very_short_line_is_not_offered(self):
        c = self.run_one([way(1, "Tiny Trail", straight(metres=200, n=5))], "Tiny Trail").candidates[0]
        self.assertEqual(c.unsure, "the map only has a very short piece of it")


class Climbing(NoNetwork):
    def test_samples_are_even_capped_and_include_both_ends(self):
        path = straight(metres=1500)
        pts = hl.sample_points(path)
        self.assertEqual((pts[0], pts[-1]), (path[0], (round(path[-1][0], 6), path[-1][1])))
        self.assertEqual(len(pts), 31)  # 50 m apart
        self.assertEqual(len(hl.sample_points(straight(metres=30000, n=301))), hl.MAX_SAMPLES)  # long routes: wider spacing, same request size

    def test_gain_by_shape(self):
        up = [100.0 + 5 * i for i in range(10)]  # steady 45 m climb
        self.assertEqual(hl.elevation_gain_ft(up, "point-to-point"), 150)  # 45 m = 147.6 ft, nearest 10
        self.assertEqual(hl.elevation_gain_ft(up[::-1], "point-to-point"), 150)  # walked from the lower end
        self.assertEqual(hl.elevation_gain_ft(up, "out-and-back"), 150)  # up on the way out, nothing more on the way back
        self.assertEqual(hl.elevation_gain_ft(up + up[::-1], "out-and-back"), 300)  # up and over and back: both legs climb
        self.assertEqual(hl.elevation_gain_ft([100, 100, 110, 100, 100], "loop"), 0)  # single-sample spikes are filtered out

    def test_unreadable_elevation_is_none_and_the_sentence_says_so(self):
        self.assertIsNone(hl.elevations_from({"samples": [{"locationId": 0, "value": "NoData"}]}, 1))
        self.assertIsNone(hl.elevations_from({"oops": 1}, 1))
        self.assertIsNone(hl.elevations_from({"samples": [{"locationId": 0, "value": "5"}]}, 2))

        class NoElevation(Synthetic):
            def get(self, service, request):
                if service == "elevation":
                    raise hl.TransportError("slow")
                return super().get(service, request)

        result = hl.lookup("Creek Walk", NoElevation([way(1, "Creek Walk", straight())]), today=TODAY)
        c = result.candidates[0]
        self.assertEqual((c.sure, c.gain_ft), (True, None))
        self.assertIn("with no climbing figure I trust", said(result))
        self.assertEqual(hl.route_add_args(c)["elevation"], "To be confirmed")  # never a made-up number


# -- failure behaviour ---------------------------------------------------------------------------------------------------------


class Down:
    def __init__(self, kind):
        self.kind = kind

    def get(self, service, request):
        raise hl.TransportError(self.kind)


class Stale:
    def __init__(self, inner, day):
        self.inner, self.day = inner, day

    def get(self, service, request):
        r = self.inner.get(service, request)
        return hl.Response(r.body, self.day, stale=True)


class Failures(NoNetwork):
    def test_each_failure_has_a_plain_reply_and_changes_nothing(self):
        expected = {"network": "I can't reach the map right now", "slow": "The map is slow to answer right now",
                    "busy": "The map asked me to wait a bit", "budget": "I've looked up a lot of trails today",
                    "bad": "The map gave me an answer I can't read", "missing": "I can't reach the map right now"}
        for kind, start in expected.items():
            with self.subTest(kind):
                result = hl.lookup("Bishop Peak", Down(kind), today=TODAY)
                self.assertEqual((result.status, result.failure, result.candidates), ("unavailable", kind, ()))
                self.assertTrue(said(result).startswith(start), said(result))
                self.assertIn("Nothing was changed.", said(result))
                self.assertEqual(voice.check(result.reply), [])

    def test_a_late_failure_after_the_search_still_answers_plainly(self):
        class DiesAfterSearch(Spy):
            def get(self, service, request):
                if service == "elevation":
                    raise hl.TransportError("network")
                return super().get(service, request)

        result = hl.lookup("Bishop Peak", DiesAfterSearch(fixture("bishop_peak")), today=TODAY)
        self.assertEqual((result.status, result.candidates[0].gain_ft), ("one", None))  # distance is known, climb is not: say so
        self.assertIn("no climbing figure I trust", said(result))

    def test_a_saved_copy_is_used_and_said_to_be_old(self):
        old = date(2026, 9, 1)
        result = hl.lookup("Bishop Peak", Stale(fixture("bishop_peak"), old), today=TODAY)
        c = result.candidates[0]
        self.assertEqual((result.status, result.stale, c.stale, c.retrieved), ("one", True, True, old))
        self.assertIn("This is from a saved copy from Sep 1, and I couldn't check it again today.", said(result))
        self.assertEqual(voice.check(result.reply), [])

    def test_a_closure_in_the_map_data_is_repeated_and_not_ignored(self):
        data = json.loads((FIX / "bishop_peak.json").read_text("utf-8"))
        for rec in data["responses"].values():
            for el in (rec["body"].get("elements") or []) if isinstance(rec["body"], dict) else []:
                if el["type"] == "way":
                    el["tags"]["note"] = "Trail closed for <b>storm</b> repair\u200b until spring"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "closed.json"
            path.write_text(json.dumps(data), "utf-8")
            result = hl.lookup("Bishop Peak", hl.FixtureTransport(path), today=TODAY)
        c = result.candidates[0]
        self.assertEqual(c.notes, ("Trail closed for storm repair until spring",))  # markup and the invisible character are gone
        self.assertIn('The map notes say Trail closed for storm repair until spring. Please check with the park before we plan anything.', said(result))
        self.assertTrue(c.sure)  # the numbers stay; the warning travels with them
        self.assertEqual(voice.check(result.reply), [])


# -- the polite client: cache, spacing, limits, log -------------------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.t, self.slept = 1000.0, []
        self.now_dt = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

    def sleep(self, s):
        self.slept.append(s)
        self.t += s

    def monotonic(self):
        self.t += 0.01
        return self.t

    def now(self):
        return self.now_dt


class Raw:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, service, request):
        self.calls.append((service, request))
        if self.fail:
            raise hl.TransportError(self.fail)
        return {"answer": len(self.calls)}


class PoliteClient(NoNetwork):
    def make(self, raw=None, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clock, self.log = Clock(), []
        self.raw = raw or Raw()
        t = hl.CachedTransport(self.raw, Path(tmp.name) / "saved", now=self.clock.now, sleep=self.clock.sleep, clock=self.clock.monotonic,
                               log=self.log.append, **kw)
        t.begin_lookup()
        return t

    def test_a_fresh_saved_answer_means_no_request(self):
        t = self.make()
        first = t.get("overpass", {"query": "q"})
        again = t.get("overpass", {"query": "q"})
        self.assertEqual((len(self.raw.calls), first.body, again.body, again.stale), (1, again.body, {"answer": 1}, False))
        self.assertEqual([r["outcome"] for r in self.log], ["fetched", "saved"])

    def test_an_answer_older_than_its_lifetime_is_fetched_again(self):
        t = self.make()
        t.get("overpass", {"query": "q"})
        self.clock.now_dt += timedelta(days=hl.LIFETIME_DAYS["overpass"] + 1)
        r = t.get("overpass", {"query": "q"})
        self.assertEqual((len(self.raw.calls), r.body, r.stale), (2, {"answer": 2}, False))

    def test_requests_to_one_service_are_spaced(self):
        t = self.make()
        t.get("nominatim_reverse", {"lat": 1, "lon": 2})
        t.get("nominatim_reverse", {"lat": 3, "lon": 4})
        self.assertTrue(self.clock.slept and self.clock.slept[0] >= hl.MIN_INTERVAL_S["nominatim_reverse"] - 0.1, self.clock.slept)

    def test_a_failed_refresh_returns_the_old_copy_marked_stale_and_with_no_copy_raises(self):
        t = self.make()
        t.get("elevation", {"points": [[1, 2]]})
        self.clock.now_dt += timedelta(days=hl.LIFETIME_DAYS["elevation"] + 5)
        self.raw.fail = "slow"
        r = t.get("elevation", {"points": [[1, 2]]})
        self.assertEqual((r.stale, r.retrieved, r.body), (True, date(2026, 11, 9), {"answer": 1}))
        with self.assertRaises(hl.TransportError) as ctx:
            t.get("elevation", {"points": [[9, 9]]})
        self.assertEqual(ctx.exception.kind, "slow")

    def test_limits_per_lookup_and_per_day(self):
        t = self.make(per_lookup=2)
        t.get("overpass", {"query": "a"})
        t.get("elevation", {"points": [[1, 1]]})
        with self.assertRaises(hl.TransportError) as ctx:
            t.get("elevation", {"points": [[2, 2]]})
        self.assertEqual(ctx.exception.kind, "budget")
        self.assertEqual(len(self.raw.calls), 2)
        t.begin_lookup()  # the next lookup starts its own count
        t.get("elevation", {"points": [[2, 2]]})
        day = self.make(per_day=1)
        day.get("overpass", {"query": "a"})
        day.begin_lookup()
        with self.assertRaises(hl.TransportError):
            day.get("overpass", {"query": "b"})
        self.assertEqual(hl.MAX_PER_LOOKUP, 8)
        self.assertEqual(hl.MAX_PER_DAY, 60)

    def test_the_log_has_keys_and_outcomes_never_text(self):
        t = self.make()
        t.get("overpass", {"query": "SECRET-LOOKING-TEXT"})
        t.get("overpass", {"query": "SECRET-LOOKING-TEXT"})
        for row in self.log:
            self.assertEqual(set(row), {"at", "service", "key", "outcome", "seconds"})
        self.assertNotIn("SECRET", json.dumps(self.log))

    def test_the_saved_folder_is_private(self):
        t = self.make()
        t.get("overpass", {"query": "q"})
        self.assertEqual(t.folder.stat().st_mode & 0o777, 0o700)


# -- Hass rules: public text, claims, route ideas versus events ---------------------------------------------------------------------


def sure_candidate(**kw):
    base = dict(name="Bishop Peak Trail", miles=2.4, gain_ft=740, shape="out-and-back", source=hl.SOURCE_NAME, retrieved=RECORDED,
                place="San Luis Obispo", osm=("way/175094087",))
    return hl.Candidate(**{**base, **kw})


class HassRules(NoNetwork):
    def test_public_text_has_no_markup_or_invisible_characters(self):
        dirty = "<script>Bishop</script>\u200b Peak\u202e {{x}}\n$5\tTrail"
        clean = hl.clean_public(dirty)
        self.assertEqual(clean, "Bishop Peak x 5 Trail")
        for bad in ("<", ">", "{{", "}}", "$", "\u200b", "\u202e", "\n", "\t"):
            self.assertNotIn(bad, clean)
        self.assertEqual(len(hl.clean_public("x" * 500)), 120)

    def test_route_idea_arguments_pass_the_existing_validators(self):
        args = hl.route_add_args(sure_candidate())
        self.assertEqual((args["distance"], args["elevation"], args["routeType"], args["elevationLabel"]),
                         ("2.4 miles", "About 740 ft", "Out & back", "Elevation gain"))
        self.assertEqual(args["sourceName"], "OpenStreetMap contributors and USGS 3DEP, retrieved Nov 9, 2026")  # source name + date
        self.assertEqual(args["sourceUrl"], "https://www.openstreetmap.org/way/175094087")
        problems = []
        for field, limit in TEXT_LIMITS["routeIdea"].items():
            _text(problems, field, args[field], limit=limit)
        self.assertEqual(problems, [])
        content = SimpleNamespace(community={"events": [], "routeIdeas": []})
        touched = _route_add(content, args, None)  # the real op
        record = content.community["routeIdeas"][0]
        self.assertEqual((record["id"], record["status"], record["rsvpEnabled"]), (hl.route_id("Bishop Peak Trail"), "idea", False))
        self.assertEqual(touched[0].key, "idea-bishop-peak-trail")

    def test_only_measured_numbers_appear_everything_else_says_to_be_confirmed(self):
        args = hl.route_add_args(sure_candidate())
        for field in ("character", "difficulty", "duration", "terrain"):
            self.assertEqual(args[field], "To be confirmed")
        self.assertEqual(args["description"], "About 2.4 miles, out and back. Michael will share the details soon.")
        self.assertEqual(hl.route_add_args(sure_candidate(shape="loop", gain_ft=None))["elevation"], "To be confirmed")

    def test_the_claims_gate_still_judges_the_text_the_map_supplied(self):
        def hits(candidate):
            args = hl.route_add_args(candidate)
            draft = {"ops": [{"op": "route.add", "args": args}],
                     "records": [{"collection": "routeIdeas", "key": hl.route_id(args["title"]), "before": None, "after": args}]}
            return claims.unstated(draft, "Add a hike on Bishop Peak", {}, {})
        self.assertEqual(hits(sure_candidate()), [])
        organic = hits(sure_candidate(name="Organic Farm Trail"))
        self.assertTrue(organic and organic[0][1] == "organic", organic)  # a claim word from the map is asked about, not published

    def test_route_id_matches_the_one_route_add_makes(self):
        for title in ("Bishop Peak Trail", "Montaña de Oro Bluff Trail", "Cerro San Luis"):
            content = SimpleNamespace(community={"events": [], "routeIdeas": []})
            _route_add(content, hl.route_add_args(sure_candidate(name=title)), None)
            self.assertEqual(content.community["routeIdeas"][0]["id"], hl.route_id(title), title)
        content = SimpleNamespace(community={"events": [], "routeIdeas": [{"id": "idea-bishop-peak-trail", "title": "Other"}]})
        _route_add(content, hl.route_add_args(sure_candidate()), None)
        self.assertEqual(content.community["routeIdeas"][-1]["id"], hl.route_id("Bishop Peak Trail", ["idea-bishop-peak-trail"]))

    def test_a_looked_up_route_is_a_route_idea_until_mike_gives_day_time_and_place(self):
        c = sure_candidate()
        self.assertEqual([o["op"] for o in hl.plan_ops(c)], ["route.add"])  # no hike op by itself
        for missing in ({}, {"date": "2026-12-05"}, {"date": "2026-12-05", "time": "09:00"}, {"date": "", "time": "09:00", "meetingPoint": "Lot"},
                        {"date": "2026-12-05", "time": "09:00", "meetingPoint": "   "}):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                hl.plan_ops(c, missing)
        ops = hl.plan_ops(c, {"date": "2026-12-05", "time": "09:00", "meetingPoint": "Highland trailhead"})
        self.assertEqual([o["op"] for o in ops], ["route.add", "hike.create"])
        self.assertEqual(ops[1]["args"]["trailId"], "idea-bishop-peak-trail")
        self.assertIs(ops[1]["args"]["rsvpEnabled"], False)  # sign-up stays off unless Mike says otherwise
        self.assertNotIn("capacity", ops[1]["args"])

    def test_an_unsure_candidate_never_reaches_the_ops(self):
        with self.assertRaises(ValueError):
            hl.plan_ops(sure_candidate(miles=None, shape="", unsure="the trail branches in several places"))


class WithTheEditor(HikeTestCase):
    """The plan goes through the real editor: prepare and apply, exactly like every other change."""

    def test_route_idea_only_adds_no_hike(self):
        repo = self.repo()
        before_events = repo.community()["events"]
        ops = hl.plan_ops(sure_candidate())
        draft = repo.run(*[(o["op"], o["args"]) for o in ops])
        community = repo.community()
        idea = next(i for i in community["routeIdeas"] if i["id"] == "idea-bishop-peak-trail")
        self.assertEqual((idea["status"], idea["rsvpEnabled"], idea["distance"]), ("idea", False, "2.4 miles"))
        self.assertEqual(community["events"], before_events)  # still no real event
        self.assertTrue(draft["change_id"].startswith("chg-"))  # the usual change record; applying needed the usual approval path

    def test_with_confirmed_details_one_request_makes_the_route_idea_and_the_hike(self):
        repo = self.repo()
        ops = hl.plan_ops(sure_candidate(), {"date": "2026-12-05", "time": "09:00", "meetingPoint": "Highland trailhead"})
        repo.run(*[(o["op"], o["args"]) for o in ops])
        event = next(e for e in repo.community()["events"] if e["trailId"] == "idea-bishop-peak-trail")
        self.assertEqual((event["startsAt"], event["timezone"], event["meetingPoint"], event["rsvpEnabled"], event["status"]),
                         ("2026-12-05T09:00:00-08:00", "America/Los_Angeles", "Highland trailhead", False, "scheduled"))

    def test_the_live_policy_keeps_route_ideas_private_to_a_human_release(self):
        from hass import live_policy
        self.assertEqual(live_policy.PRIVATE["route.add"], "is trail details")
        self.assertNotIn("route.add", live_policy.LIVE)


# -- privacy and the manual script -------------------------------------------------------------------------------------------------------


class Privacy(NoNetwork):
    def test_only_the_hike_name_goes_out(self):
        spy = Spy(fixture("bishop_peak"))
        hl.lookup("Bishop Peak", spy, today=TODAY)
        services = [s for s, _r in spy.sent]
        self.assertEqual(services, ["overpass", "nominatim_reverse", "elevation"])
        self.assertEqual(spy.sent[0][1], {"query": hl.overpass_query(["bishop", "peak"])})
        self.assertEqual(set(spy.sent[1][1]), {"lat", "lon", "zoom"})  # public coordinates of the trail
        self.assertEqual(set(spy.sent[2][1]), {"points"})
        flat = json.dumps(spy.sent)
        for private in ("Mike", "mike", "@", "Saturday", "meetingPoint", "chat", "owner"):
            self.assertNotIn(private, flat)

    def test_digits_in_a_name_never_leave_and_the_name_is_capped(self):
        out = hl.outbound_names("Bishop Peak call 805 555 0100 mike@example.com 93401 and then some more words please")
        text = json.dumps(out)
        for private in ("805", "555", "0100", "93401", "example"):
            self.assertNotIn(private, text)
        self.assertLessEqual(len(hl.name_tokens("one two three four five six seven eight nine ten")[:hl.MAX_NAME_WORDS]), hl.MAX_NAME_WORDS)

    def test_the_module_has_no_network_code(self):
        source = (ROOT / "hass/hike_lookup.py").read_text("utf-8")
        for word in ("import urllib", "import socket", "import http", "import requests", "import ssl", "subprocess", "os.environ"):
            self.assertNotIn(word, source)

    def test_the_manual_script_refuses_to_run_in_ci(self):
        env = {**os.environ, "CI": "true"}
        run = subprocess.run([sys.executable, str(ROOT / "scripts/hike_lookup_manual.py"), "--contact", "nobody", "Bishop Peak"],
                             env=env, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("must not run in CI", run.stderr + run.stdout)

    def test_the_manual_script_is_named_as_live_and_has_no_built_in_contact(self):
        text = (ROOT / "scripts/hike_lookup_manual.py").read_text("utf-8")
        self.assertIn("MAKES LIVE NETWORK CALLS. NEVER RUN BY THE TESTS OR BY CI.", text.splitlines()[1] + text.splitlines()[0] + text.splitlines()[2])
        self.assertIn('required=True, help="an address', text)
        self.assertNotIn("@", text.split("def main")[0].replace("ADDRESS", ""))  # no address baked in


if __name__ == "__main__":
    unittest.main()
