"""RF0540-12 tests (H06): a scheduled-hike preview target refuses a before snapshot that is neither a dict nor None.

Wrong-typed (truthy or falsey) snapshots give ``{"kind": "unreadable"}`` from ``preview.target_for`` instead of raising
or being read as an empty record; ``Previewer.capture`` then reuses its fixed refusal before any copy or server.
Pure and synthetic: no browser, no network, no server. Run: python3 -m unittest hass.tests.test_preview_event_before -v
"""

import copy
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import preview

UNREADABLE = {"kind": "unreadable"}
REFUSED = {"ok": False, "png": None, "checks": {}, "error": "preview target unreadable"}
SCHEDULED = {"title": "Synthetic loop", "status": "scheduled"}
BAD_BEFORE = ("damaged", ["meetTime"], 5, True, ("meetTime",), {"meetTime"}, 1.5, b"x",
              [], "", 0, False, ())


def _record(before="absent", **after):
    record = {"collection": "events", "key": "synthetic-hike", "after": {**SCHEDULED, **after}}
    if before != "absent":
        record["before"] = before
    return record


def _target(**extra):
    return {"kind": "event", "title": "Synthetic loop", "status": "scheduled", "id": "synthetic-hike", "recap": "",
            "startsAt": None, "meetingPoint": "", "capacity": None, "rsvpEnabled": False, "changed": {}, **extra}


class MalformedBeforeTests(unittest.TestCase):
    def test_scheduled_truthy_wrong_before_is_unreadable(self):
        for before in ("damaged", ["meetTime"], 5, True, ("meetTime",), {"meetTime"}):
            for after in ({}, {"meetTime": "8:30 AM"}, {"meetTime": "", "meetingAddress": None}):
                with self.subTest(before=before, after=after):
                    record = _record(before, **after)
                    snapshot = copy.deepcopy(record)
                    self.assertEqual(preview.target_for(record), UNREADABLE)
                    self.assertEqual(record, snapshot)

    def test_scheduled_falsey_wrong_before_is_not_empty_snapshot(self):
        for before in ([], "", 0, False, ()):
            with self.subTest(before=before):
                self.assertEqual(preview.target_for(_record(before)), UNREADABLE)
                self.assertEqual(preview.target_for(_record(before, meetTime="8:30 AM")), UNREADABLE)

    def test_missing_none_and_empty_dict_before_preserve_exact_target(self):
        cases = [({}, _target()),
                 ({"meetTime": "8:30 AM", "walkTime": "  "}, _target(changed={"meetTime": "8:30 AM"}))]
        for after, expected in cases:
            for before in ("absent", None, {}):
                with self.subTest(after=after, before=before):
                    got = preview.target_for(_record(before, **after))
                    self.assertEqual(json.dumps(got), json.dumps(expected))

    def test_valid_before_preserves_changed_cleared_and_order(self):
        before = {"meetTime": "8:00 AM", "meetingAddress": "Old lot", "returnTime": "noon", "walkTime": "2 h"}
        record = _record(before, meetTime="8:30 AM", meetingAddress="", returnTime="noon", capacity=12,
                         rsvpEnabled=True, meetingPoint="Trailhead", startsAt="2026-12-01T08:00")
        snapshot = copy.deepcopy(record)
        expected = _target(startsAt="2026-12-01T08:00", meetingPoint="Trailhead", capacity=12, rsvpEnabled=True,
                           changed={"meetTime": "8:30 AM"}, cleared=["meetingAddress", "walkTime"])
        self.assertEqual(json.dumps(preview.target_for(record)), json.dumps(expected))
        self.assertEqual(record, snapshot)
        probe = _record({"meetTime": "8:00 AM", "meetingAddress": "Old lot"}, meetTime="8:30 AM")
        self.assertEqual(json.dumps(preview.target_for(probe)),
                         json.dumps(_target(changed={"meetTime": "8:30 AM"}, cleared=["meetingAddress"])))

    def test_other_status_and_collection_before_behavior_is_unchanged(self):
        for status in ("completed", "cancelled", None):
            with self.subTest(status=status):
                after = {"title": "Synthetic loop", "recap": ""} | ({} if status is None else {"status": status})
                got = preview.target_for({"collection": "events", "key": "synthetic-hike", "before": "damaged",
                                          "after": after})
                self.assertEqual(got, {"kind": "event", "title": "Synthetic loop", "status": status,
                                       "id": "synthetic-hike", "recap": ""})
        route = {"collection": "routeIdeas", "key": "r-1", "before": "damaged", "after": {"title": "Coast walk"}}
        self.assertEqual(preview.target_for(route), {"kind": "route", "id": "r-1", "title": "Coast walk", "hidden": False})
        maker = {"collection": "makers", "key": "m-1", "before": ["x"], "after": {"name": "Farm", "place": "Cayucos"}}
        self.assertEqual(preview.target_for(maker)["kind"], "maker")
        product = {"collection": "products", "key": "p-1", "before": 5, "after": {"name": "A", "status": "hidden"}}
        self.assertEqual(preview.target_for(product)["kind"], "product")
        self.assertEqual(preview.target_for({"collection": "store", "before": "damaged", "after": {}}), UNREADABLE)

    def test_bad_scheduled_before_capture_refuses_before_any_side_effect(self):
        fail = mock.Mock(side_effect=AssertionError("must not be called"))
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / "shots" / "x.png"
            with mock.patch.object(preview.subprocess, "Popen", fail), \
                    mock.patch.object(preview.subprocess, "run", fail), \
                    mock.patch.object(preview.shutil, "copyfile", fail), \
                    mock.patch.object(preview.tempfile, "TemporaryDirectory", fail), \
                    mock.patch.object(socket, "socket", fail):
                for before in BAD_BEFORE:
                    target = preview.target_for(_record(before, meetTime="8:30 AM"))
                    for viewports in (("phone",), preview.VIEWPORTS, ("bogus",)):
                        with self.subTest(before=before, viewports=viewports):
                            result = preview.Previewer(raw, env={}, viewports=viewports).capture({}, target, out)
                            self.assertEqual(result, REFUSED)
            fail.assert_not_called()
            self.assertFalse(out.parent.exists())


if __name__ == "__main__":
    unittest.main()
