"""RF0310-5 (H06) tests: ``history.revert`` refuses a change whose stored ``before`` value is misshaped (a hike without a
text status or a readable start, a non-int capacity, a non-dict value) as ``record is malformed``; it never raises.

Each case applies a real change in a throwaway HikeRepo (temp repo + temp state dir, fixture content and a temp RSVP
database with example.invalid rows only), then edits the stored ``before`` in ``<state>/changes/<id>.json``.
Run: python3 -m unittest hass.tests.test_revert_event_shape -v
"""

import contextlib
import io
import json
from datetime import datetime

from hass import editor
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, HikeTestCase, _req

COMMUNITY, PRODUCTS = "hass/content/community.json", "hass/content/products.json"


class RevertEventShapeTests(HikeTestCase):
    def setUp(self):
        self.r = self.repo()
        self.r.run(("hike.create", HIKE))
        self.r.make_db([(HIKE_ID, 2)])
        self.change_id = self.r.run(("hike.update", {"id": HIKE_ID, "capacity": 20}))["change_id"]
        self.path = self.r.state / "changes" / f"{self.change_id}.json"
        self.record = json.loads(self.path.read_text("utf-8"))
        self.before = self.record["records"][0]["before"]

    def set_before(self, before, path=None, record=None):
        record = record or self.record
        records = [{**record["records"][0], "before": before}] + record["records"][1:]
        (path or self.path).write_text(json.dumps({**record, "records": records}), "utf-8")

    def assert_refused(self, reason, change_id=None):
        """Undo refused with exactly ``reason``; nothing drafted, content, history and the record byte-identical."""
        r, change_id = self.r, change_id or self.change_id
        record = (r.state / "changes" / f"{change_id}.json").read_bytes()
        files = lambda: [(r.wt / rel).read_bytes() for rel in (COMMUNITY, PRODUCTS)]  # noqa: E731
        kept = (r.drafts(), files(), r.head())
        result = r.prepare(_req(("history.revert", {"changeId": change_id})))
        self.assertEqual((result["result"], result.get("reason")), ("refused", reason), result)
        self.assertEqual((r.drafts(), files(), r.head(), r.status()), (*kept, ""))
        self.assertEqual((r.state / "changes" / f"{change_id}.json").read_bytes(), record)

    def test_misshaped_hike_before_is_malformed(self):
        drop = lambda field: {k: v for k, v in self.before.items() if k != field}  # noqa: E731
        cases = {"capacity text": {**self.before, "capacity": "12"}, "capacity null": {**self.before, "capacity": None},
                 "capacity float": {**self.before, "capacity": 12.0}, "capacity bool": {**self.before, "capacity": True},
                 "no status": drop("status"), "status int": {**self.before, "status": 1},
                 "no startsAt": drop("startsAt"), "startsAt int": {**self.before, "startsAt": 20261102},
                 "startsAt words": {**self.before, "startsAt": "next Tuesday"},
                 "startsAt no zone": {**self.before, "startsAt": "2026-12-05T09:00:00"},
                 "before a list": [self.before], "before text": "scheduled", "before a number": 7}
        for name, before in cases.items():
            with self.subTest(name):
                self.set_before(before)
                self.assert_refused(f"{self.change_id} record is malformed")

    def test_shape_wins_over_conflict_and_seats(self):
        self.set_before({**self.before, "capacity": "1"})  # an int 1 would be refused for 2 confirmed guests
        self.assert_refused(f"{self.change_id} record is malformed")
        self.r.run(("hike.update", {"id": HIKE_ID, "title": "Renamed"}))  # later edit: a conflict once well-formed
        self.assert_refused(f"{self.change_id} record is malformed")
        self.set_before(self.before)
        self.assert_refused(f"conflict: events {HIKE_ID} changed after {self.change_id}")

    def test_product_before_a_list_is_malformed(self):
        change = self.r.run(("product.edit", {"id": "photo-product-001", "description": "Buttery."}))
        path = self.r.state / "changes" / f"{change['change_id']}.json"
        record = json.loads(path.read_text("utf-8"))
        self.set_before([record["records"][0]["before"]], path, record)
        self.assert_refused(f"{change['change_id']} record is malformed", change["change_id"])

    def test_valid_before_reverts_and_past_start_keeps_its_reason(self):
        self.r.now = datetime.fromisoformat(self.before["startsAt"])  # the stored, well-formed before is untouched
        self.assert_refused("start is in the past")
        self.r.now = NOW
        self.r.run(("history.revert", {"changeId": self.change_id}))
        self.assertEqual(self.r.event()["capacity"], 12)
        self.assertEqual(self.r.event()["status"], "scheduled")

    def test_created_hike_is_still_cancelled(self):
        created = self.r.run(("hike.create", {**HIKE, "title": "Walk two"}))
        self.assertIsNone(json.loads((self.r.state / "changes" / f"{created['change_id']}.json")
                                     .read_text("utf-8"))["records"][0]["before"])
        self.r.run(("history.revert", {"changeId": created["change_id"]}))
        self.assertEqual(self.r.event("hike-2026-12-05-walk-two")["status"], "cancelled")

    def test_cli_prints_refused_not_io_error(self):
        self.set_before({**self.before, "startsAt": 20261102})
        request = self.r.state.parent / "revert.json"
        request.write_text(json.dumps(_req(("history.revert", {"changeId": self.change_id}))), "utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = editor.main(["prepare", str(request), "--state", str(self.r.state)])
        self.assertEqual(err.getvalue(), "")
        result = json.loads(out.getvalue())
        self.assertEqual((result["result"], result["reason"]), ("refused", f"{self.change_id} record is malformed"))
        self.assertNotIn("io-error", out.getvalue())
        self.assertEqual(self.r.event()["capacity"], 20)
        self.assertNotEqual(code, 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
