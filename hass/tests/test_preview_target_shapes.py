"""RF0550-2 tests (H06): ``preview.target_for`` never raises on a damaged change record; a record, ``after`` value or
read field of the wrong type gives ``{"kind": "unreadable"}``, which ``capture`` refuses before any copy or server.

Pure: no browser, no network, no server. Run: python3 -m unittest hass.tests.test_preview_target_shapes -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import preview

UNREADABLE = {"kind": "unreadable"}
REFUSED = {"ok": False, "png": None, "checks": {}, "error": "preview target unreadable"}
PRODUCT = {"collection": "products", "key": "p-1", "after": {"name": "Avocados", "status": "active", "description": "Ripe."}}
MAKER = {"collection": "makers", "key": "m-1", "after": {"name": "Farm", "place": "Cayucos", "hidden": True}}
STORE = {"collection": "store", "after": {"hours": ["Mon 9-5"], "streetAddress": "5 Example St", "town": "Cayucos"}}
EVENT = {"collection": "events", "key": "h-1", "after": {"title": "Hike", "status": "completed", "recap": "Calm."}}
ROUTE = {"collection": "routeIdeas", "key": "r-1", "after": {"title": "Coast walk", "status": "open", "recap": "x"}}


def _with(record, **after):
    return {**record, "after": {**record["after"], **after}}


class GoodRecordTests(unittest.TestCase):
    def test_good_records_give_the_same_targets_as_before(self):
        cases = [
            (PRODUCT, {"kind": "product", "id": "p-1", "name": "Avocados", "status": "active", "description": "Ripe."}),
            (MAKER, {"kind": "maker", "key": "m-1", "name": "Farm", "place": "Cayucos", "hidden": True}),
            (STORE, {"kind": "store", "hours": ["Mon 9-5"], "streetAddress": "5 Example St", "town": "Cayucos",
                     "headline": [], "story": None}),
            (EVENT, {"kind": "event", "title": "Hike", "status": "completed", "id": "h-1", "recap": "Calm."}),
            (ROUTE, {"kind": "event", "title": "Coast walk", "status": None, "id": "", "recap": ""}),
        ]
        for record, expected in cases:
            with self.subTest(collection=record["collection"]):
                self.assertEqual(json.dumps(preview.target_for(record)), json.dumps(expected))

    def test_none_after_and_empty_hours_keep_todays_targets(self):
        self.assertEqual(preview.target_for({"collection": "products", "key": "p-1", "after": None}),
                         {"kind": "product", "id": "p-1", "name": "", "status": None, "description": None})
        self.assertEqual(preview.target_for(_with(STORE, hours=[])),
                         {"kind": "store", "hours": [], "streetAddress": "5 Example St", "town": "Cayucos", "headline": [], "story": None})
        self.assertEqual(preview.target_for(_with(STORE, hours=None))["hours"], [])
        self.assertEqual(preview.target_for(_with(PRODUCT, name=None, description=None))["name"], None)

    def test_fields_another_kind_reads_are_not_checked(self):
        self.assertEqual(preview.target_for(_with(PRODUCT, hours="Mon", place=3))["kind"], "product")
        self.assertEqual(preview.target_for(_with(ROUTE, status=5, recap=[1]))["title"], "Coast walk")


class DamagedRecordTests(unittest.TestCase):
    def assertUnreadable(self, record):
        self.assertEqual(preview.target_for(record), UNREADABLE)

    def test_record_not_a_dict(self):
        for record in (None, [], "x", 5, ["products"]):
            with self.subTest(record=record):
                self.assertUnreadable(record)

    def test_after_neither_dict_nor_none(self):
        for base in (PRODUCT, MAKER, STORE, EVENT, ROUTE):
            for after in ([], "Honey", 5, ["name"], "", 0, False):
                with self.subTest(collection=base["collection"], after=after):
                    self.assertUnreadable({**base, "after": after})

    def test_store_hours_must_be_a_list_of_text(self):
        for hours in ("Mon 9-5", ["Mon 9-5", 7], [None], ("Mon 9-5",), {"Mon": "9-5"}, ""):
            with self.subTest(hours=hours):
                self.assertUnreadable(_with(STORE, hours=hours))

    def test_read_fields_must_be_text(self):
        cases = [(PRODUCT, "name", 7), (PRODUCT, "status", True), (PRODUCT, "description", ["Ripe."]),
                 (MAKER, "place", {"a": 1}), (MAKER, "name", 3.5), (STORE, "streetAddress", 1),
                 (STORE, "town", ["Cayucos"]), (EVENT, "title", ["t"]), (EVENT, "status", 2),
                 (EVENT, "recap", {"t": 1}), (ROUTE, "title", 9)]
        for record, field, value in cases:
            with self.subTest(collection=record["collection"], field=field):
                self.assertUnreadable(_with(record, **{field: value}))

    def test_key_must_be_text_or_absent(self):
        for base in (PRODUCT, MAKER, STORE, EVENT, ROUTE):
            for key in (12, ["p-1"], {"k": 1}, 0):
                with self.subTest(collection=base["collection"], key=key):
                    self.assertUnreadable({**base, "key": key})

    def test_unhashable_collection_never_raises(self):
        self.assertEqual(preview.target_for({"collection": ["store"], "after": {"title": "T"}})["kind"], "event")
        self.assertUnreadable({"collection": {"a": 1}, "after": {"title": 4}})


class CaptureRefusalTests(unittest.TestCase):
    def test_unreadable_target_is_refused_before_any_copy_or_server(self):
        fail = mock.Mock(side_effect=AssertionError("must not be called"))
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / "shots" / "x.png"
            with mock.patch.object(preview.subprocess, "Popen", fail), \
                    mock.patch.object(preview.subprocess, "run", fail), \
                    mock.patch.object(preview.tempfile, "TemporaryDirectory", fail):
                for target in (UNREADABLE, preview.target_for(None), preview.target_for(_with(STORE, hours="Mon"))):
                    for viewports in (("phone",), preview.VIEWPORTS, ("bogus",)):
                        with self.subTest(target=target, viewports=viewports):
                            result = preview.Previewer(raw, env={}, viewports=viewports).capture({}, target, out)
                            self.assertEqual(result, REFUSED)
            fail.assert_not_called()
            self.assertFalse(out.parent.exists())


if __name__ == "__main__":
    unittest.main()
