"""RF1830-11: a JSON integer too large for float conversion in a matching map point is an unreadable answer
(``unavailable`` / ``bad``), not an OverflowError out of lookup. Synthetic malformed-source evidence only."""

from __future__ import annotations

import copy
import json
import math
import unittest
from datetime import date
from unittest import mock

from hass import hike_lookup as hl
from hass.tests import test_hike_lookup as base

TODAY = date(2026, 11, 9)
HUGE = 10 ** 400


def wire(body):
    """A real JSON round trip (no NaN/Infinity extensions): the huge integer is a legal JSON integer token."""
    return json.loads(json.dumps(body, allow_nan=False))


class Recording:
    """Deterministic in-memory transport. ``overpass`` answers come from a list (first stage, then the id query)."""

    def __init__(self, overpass, search=None):
        self.overpass, self.search, self.services = list(overpass), search, []
        self.frozen = copy.deepcopy(self.overpass)

    def get(self, service, request):
        self.services.append(service)
        if service == "overpass":
            return hl.Response(self.overpass.pop(0) if len(self.overpass) > 1 else self.overpass[0], TODAY)
        if service == "nominatim_search":
            return hl.Response(self.search, TODAY)
        if service == "nominatim_reverse":
            return hl.Response({"address": {"town": "Testville"}}, TODAY)
        if service == "elevation":
            pts = request["points"]
            return hl.Response({"samples": [{"locationId": i, "value": str(100 + 5.0 * i)} for i in range(len(pts))]}, TODAY)
        raise hl.TransportError("missing", service)


class NoNetwork(unittest.TestCase):
    def setUp(self):
        def refuse(*_a, **_k):
            raise AssertionError("a test tried to use the network")
        for target in ("socket.socket.connect", "socket.create_connection", "socket.getaddrinfo"):
            patcher = mock.patch(target, refuse)
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_unreadable(self, result, transport=None):
        self.assertEqual((result.status, result.failure, result.candidates, result.total), ("unavailable", "bad", (), 0))
        text = base.said(result)
        self.assertTrue(text.startswith("The map gave me an answer I can't read"), text)
        self.assertIn("Nothing was changed.", text)
        self.assertNotIn("0000000000", text)


def good_way(ident=1, name="Creek Walk"):
    return base.way(ident, name, base.straight())


def corrupt_way(index, key, value, ident=2):
    el = good_way(ident)
    el["geometry"][index][key] = value
    return el


class OverflowAtTheBoundary(NoNetwork):
    def test_huge_json_integer_way_coordinates_return_bad_not_overflow(self):
        last = len(good_way()["geometry"]) - 1
        for value in (HUGE, -HUGE):
            for key in ("lat", "lon"):
                for index in (0, last):
                    with self.subTest(value=value > 0, key=key, index=index):
                        body = wire({"elements": [corrupt_way(index, key, value)]})
                        before = copy.deepcopy(body)
                        t = Recording([body])
                        self.assert_unreadable(hl.lookup("Creek Walk", t, today=TODAY))
                        self.assertEqual(body, before)
                        self.assertEqual(t.services, ["overpass"])

    def test_relation_members_and_summit_points_use_the_same_boundary(self):
        member = {"type": "way", "geometry": base.line(base.straight())}
        bad_member = {"type": "way", "geometry": wire(base.line(base.straight()) + [{"lat": HUGE, "lon": -120.7}])}
        relation = lambda members: {"type": "relation", "id": 5, "tags": {"name": "Creek Walk"}, "members": members}
        summit = {"type": "node", "id": 9, "lat": 35.3, "lon": -HUGE, "tags": {"name": "Creek Walk"}}
        cases = {"relation member": [good_way(), relation([member, bad_member])], "summit node": [good_way(), summit]}
        for label, elements in cases.items():
            with self.subTest(label):
                body = wire({"elements": elements})
                before = copy.deepcopy(body)
                t = Recording([body])
                result = hl.lookup("Creek Walk", t, today=TODAY)
                self.assert_unreadable(result)  # the valid sibling way does not survive as a candidate
                self.assertEqual(body, before)
                self.assertEqual(t.services, ["overpass"])

    def test_earlier_valid_elements_and_points_do_not_escape_whole_answer_refusal(self):
        body = wire({"elements": [good_way(1), corrupt_way(3, "lat", HUGE, ident=2)]})
        before = copy.deepcopy(body)
        t = Recording([body])
        self.assert_unreadable(hl.lookup("Creek Walk", t, today=TODAY))
        self.assertEqual(body, before)
        self.assertEqual(t.services, ["overpass"])  # no reverse-geocode, elevation or other request

    def test_second_stage_bad_geometry_is_not_partially_offered(self):
        hit = {"name": "Creek Walk", "category": "highway", "type": "path", "osm_type": "way", "osm_id": 1}
        t = Recording([{"elements": []}, wire({"elements": [corrupt_way(2, "lon", HUGE, ident=1)]})], search=[hit])
        self.assert_unreadable(hl.lookup("Creek Walk", t, today=TODAY))
        self.assertEqual(t.services, ["overpass", "nominatim_search", "overpass"])


class HealthyValuesAreUnchanged(NoNetwork):
    def test_existing_numeric_admission_and_healthy_values_are_unchanged(self):
        for value in (0, 1, -7, 35, -120, 0.0, -0.5, 35.3, 1e300, 10 ** 300):
            with self.subTest(value=value):
                out = hl._number(value, "x")
                self.assertEqual(out, value)
                self.assertIs(type(out), type(value))
        for value in (True, False, "35.3", None, [1], {"a": 1}, float("inf"), float("-inf"), float("nan"), HUGE, -HUGE):
            with self.subTest(value=repr(value)[:20]):
                with self.assertRaises(hl.TransportError) as caught:
                    hl._number(value, "what")
                self.assertEqual((caught.exception.kind, str(caught.exception)), ("bad", "bad: what"))
                self.assertNotIn("0000000000", str(caught.exception))

    def test_ordinary_coordinates_and_recorded_output_are_unchanged(self):
        t = Recording([wire({"elements": [good_way()]})])
        result = hl.lookup("Creek Walk", t, today=TODAY)
        self.assertEqual((result.status, result.failure, len(result.candidates)), ("one", "", 1))
        self.assertEqual(t.services, ["overpass", "nominatim_reverse", "elevation"])
        recorded = hl.lookup("Bishop Peak", base.fixture("bishop_peak"), today=TODAY)
        self.assertEqual((recorded.status, recorded.total), ("one", 1))
        self.assertEqual((recorded.candidates[0].miles, recorded.candidates[0].gain_ft), (2.4, 740))
        self.assertTrue(math.isfinite(recorded.candidates[0].record["one_way_m"]))


if __name__ == "__main__":
    unittest.main()
