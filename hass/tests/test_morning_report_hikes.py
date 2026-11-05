"""AV1322-06 tests: the morning report lists scheduled hikes starting today or tomorrow (Pacific) with confirmed guests
from a read-only --guests RSVP database; unset or unreadable says "guest count unavailable", never 0.

Temporary content dirs and a temporary synthetic RSVP sqlite only. Run:
python3 -m unittest hass.tests.test_morning_report_hikes -v
"""

import contextlib
import io
import json
import os
import sqlite3
import time
import unittest

from hass import morning_report
from hass.tests import test_morning_report as base  # module import: the AVB-23 tests are not collected twice

LAST, product, UNAV = base.LAST, base.product, "guest count unavailable"
SENTINEL = "Zebulon Quillfeather"  # placeholder guest name that must never reach the output


def hike(eid, starts, status="scheduled", capacity=None, title=None):
    return {"id": eid, "title": title or eid.title(), "startsAt": starts, "status": status, "rsvpEnabled": True,
            **({} if capacity is None else {"capacity": capacity})}


class MorningReportHikesTests(unittest.TestCase):
    setUp, content, run_report, report = (base.MorningReportTests.setUp, base.MorningReportTests.content,
                                          base.MorningReportTests.run_report, base.MorningReportTests.report)

    def hikes(self, *events, products=(), raw=None):
        self.content(list(products) or [product("Figs", "yes")], checked_days_ago=1)
        doc = {"schemaVersion": 1, "events": list(events) if raw is None else raw}
        (self.dir / "community.json").write_text(json.dumps(doc), encoding="utf-8")

    def rsvp_db(self, rows):
        path = self.dir / "rsvps.sqlite3"
        with contextlib.closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE rsvps (event_id TEXT, name TEXT, email TEXT, party_size INTEGER)")
            db.executemany("INSERT INTO rsvps VALUES (?, ?, 'guest@example.invalid', ?)",
                           [(eid, SENTINEL, n) for eid, n in rows])
        return str(path)

    def hikes_line(self, *args):
        lines = self.report(*args).split("\n")
        self.assertEqual(lines[-1], LAST)
        return lines[-2]

    def test_counts_with_and_without_capacity_and_zero_when_db_readable(self):  # 1
        self.hikes(hike("ridge", "2026-11-03T09:00:00-08:00", capacity=12), hike("creek", "2026-11-03T10:30:00-08:00"),
                   hike("sunset", "2026-11-02T18:00:00-08:00", capacity=12))
        db = self.rsvp_db([("ridge", 3), ("ridge", 4), ("creek", 7), ("other", 9)])
        self.assertEqual(self.hikes_line("--guests", db), "Hikes: Monday 6:00 pm Sunset (0 of 12 confirmed); "
                         "Tuesday 9:00 am Ridge (7 of 12 confirmed); Tuesday 10:30 am Creek (7 confirmed)")
        out = self.report("--guests", db, "--json")
        self.assertNotIn(SENTINEL, out)
        self.assertNotIn("example.invalid", out)
        self.assertEqual(json.loads(out)["hikes"], [
            {"id": "sunset", "title": "Sunset", "day": "2026-11-02", "time": "18:00", "confirmed": 0, "capacity": 12},
            {"id": "ridge", "title": "Ridge", "day": "2026-11-03", "time": "09:00", "confirmed": 7, "capacity": 12},
            {"id": "creek", "title": "Creek", "day": "2026-11-03", "time": "10:30", "confirmed": 7, "capacity": None}])

    def test_unset_or_unreadable_guests_say_unavailable_never_zero(self):  # 2
        self.hikes(hike("ridge", "2026-11-03T09:00:00-08:00", capacity=12))
        want = f"Hikes: Tuesday 9:00 am Ridge ({UNAV})"
        self.assertEqual(self.hikes_line(), want)
        self.assertIsNone(json.loads(self.report("--json"))["hikes"][0]["confirmed"])
        (not_sqlite := self.dir / "notes.txt").write_text("not a database " * 40)
        no_table = self.dir / "empty.sqlite3"
        with contextlib.closing(sqlite3.connect(no_table)) as db, db:
            db.execute("CREATE TABLE other (x INTEGER)")
        null_seats = self.rsvp_db([("ridge", None)])
        for path in (self.dir / "missing.sqlite3", not_sqlite, self.dir, no_table, null_seats, ""):
            with self.subTest(path=str(path)[-14:]):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = morning_report.main(["--today", "2026-11-02", "--guests", str(path)], content_dir=self.dir, out=out)
                self.assertEqual((code, out.getvalue().split("\n")[-3]), (0, want))
                self.assertNotIn(str(self.dir), out.getvalue() + err.getvalue())
                self.assertIsNone(json.loads(self.report("--json", "--guests", str(path)))["hikes"][0]["confirmed"])
                self.assertNotIn("(0 of 12", out.getvalue())
        self.assertFalse((self.dir / "missing.sqlite3").exists())  # mode=ro never creates it

    def test_cancelled_completed_and_other_days_not_listed(self):  # 3
        self.hikes()
        plain, plain_json = self.report(), self.report("--json")
        self.hikes(hike("gone", "2026-11-03T09:00:00-08:00", status="cancelled"),
                   hike("done", "2026-11-02T08:00:00-08:00", status="completed"),
                   hike("later", "2026-11-04T09:00:00-08:00"), hike("past", "2026-11-01T09:00:00-08:00"),
                   hike("draft", "2026-11-03T09:00:00-08:00", status="draft"))
        db = self.rsvp_db([("gone", 4), ("later", 2)])
        self.assertEqual((self.report(), self.report("--guests", db)), (plain, plain))  # byte-identical, no Hikes line
        self.assertEqual(self.report("--json"), plain_json)
        self.assertNotIn("hikes", json.loads(plain_json))

    def test_pacific_day_boundaries_and_dst_change(self):  # 4
        self.hikes(hike("late", "2026-11-03T07:30:00Z"), hike("tomorrow", "2026-11-03T17:00:00Z"),
                   hike("noon", "2026-11-03T12:00:00-08:00"), hike("night", "2026-11-04T07:30:00Z"),
                   hike("third", "2026-11-04T08:00:00Z"), hike("early", "2026-11-03T00:05:00-08:00"))
        self.assertEqual(self.hikes_line(), f"Hikes: Monday 11:30 pm Late ({UNAV}); Tuesday 12:05 am Early ({UNAV}); "
                         f"Tuesday 9:00 am Tomorrow ({UNAV}); Tuesday 12:00 pm Noon ({UNAV}); "
                         f"Tuesday 11:30 pm Night ({UNAV})")
        self.hikes(hike("eve", "2026-11-01T06:30:00Z"), hike("pdt", "2026-11-01T08:30:00Z"),
                   hike("pst", "2026-11-01T09:30:00Z"), hike("morning", "2026-11-01T17:00:00Z"))
        line = self.run_report("--today", "2026-11-01").split("\n")[-2]
        self.assertEqual(line, f"Hikes: Sunday 1:30 am Pdt ({UNAV}); Sunday 1:30 am Pst ({UNAV}); "
                         f"Sunday 9:00 am Morning ({UNAV})")  # Oct 31 23:30 PDT is yesterday

    def test_ten_long_titled_hikes_stay_within_limit(self):  # 5
        titles = [f"Hike {i:02d} " + "y" * 72 for i in range(10)]
        names = [f"Product {i:02d} " + "x" * 66 for i in range(12)]
        self.hikes(*[hike(f"h{i}", f"2026-11-03T{8 + i:02d}:00:00-08:00", capacity=12, title=t)
                     for i, t in enumerate(titles)],
                   products=[product(n, "limited") for n in names] + [product(n + "s", "no") for n in names])
        text = self.report("--guests", self.rsvp_db([("h1", 2)]))
        self.assertLessEqual(len(text), 1200)
        self.assertEqual(text.split("\n")[-1], LAST)
        self.assertTrue(text.split("\n")[-2].startswith("Hikes: Tuesday 8:00 am Hike 00"), text)
        self.assertIn("…", text.split("\n")[-2])
        self.hikes(*[hike(f"h{i}", f"2026-11-03T{8 + i:02d}:00:00-08:00", title=t) for i, t in enumerate(titles)])
        self.assertEqual(self.hikes_line().count("…"), 10)  # titles are cut before any hike is dropped
        self.assertEqual(self.hikes_line().count(UNAV), 10)

    def test_unparseable_start_is_skipped(self):  # 6
        good = hike("ridge", "2026-11-03T09:00:00-08:00")
        bad = [hike("x", "x"), hike("none", None), hike("num", 20261103), {"id": "nostart", "status": "scheduled"},
               "not an event", None]
        self.hikes(*bad, good)
        self.assertEqual(self.hikes_line(), f"Hikes: Tuesday 9:00 am Ridge ({UNAV})")
        self.assertEqual([h["id"] for h in json.loads(self.report("--json"))["hikes"]], ["ridge"])
        self.hikes(raw="not a list")
        self.assertNotIn("Hikes", self.report())

    def tree_bytes(self):
        return {p.name: p.read_bytes() for p in sorted(self.dir.iterdir()) if p.is_file()}

    def test_naive_hike_start_is_skipped_in_text_and_json(self):  # 7
        self.hikes(hike("naive", "2026-11-03T01:00:00"), hike("dateonly", "2026-11-03"),
                   hike("naivez", "2026-11-02T18:00:00.5"), hike("ridge", "2026-11-03T09:00:00-08:00"))
        before = self.tree_bytes()
        self.assertEqual(self.hikes_line(), f"Hikes: Tuesday 9:00 am Ridge ({UNAV})")
        self.assertEqual([(h["id"], h["confirmed"]) for h in json.loads(self.report("--json"))["hikes"]], [("ridge", None)])
        self.assertEqual(self.tree_bytes(), before)
        self.hikes(hike("naive", "2026-11-03T01:00:00"), hike("dateonly", "2026-11-03"))
        self.assertEqual(self.report("--guests", self.rsvp_db([("naive", 3)])).split("\n")[-2:],
                         ["Available 1 · Limited 0 · Sold out 0 · Not confirmed 0", LAST])

    def test_report_is_host_timezone_independent(self):  # 8
        self.hikes(hike("naive", "2026-11-03T01:00:00"), hike("dateonly", "2026-11-03"),
                   hike("late", "2026-11-03T07:30:00Z"), hike("near", "2026-11-02T23:59:00-08:00"),
                   hike("ridge", "2026-11-03T09:00:00-08:00"))
        old, seen = os.environ.get("TZ"), []
        try:
            for zone in ("UTC", "America/Los_Angeles", "Asia/Tokyo"):
                os.environ["TZ"] = zone
                time.tzset()
                seen.append((self.report(), self.report("--json")))
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(seen[0], seen[2])
        self.assertEqual([h["id"] for h in json.loads(seen[0][1])["hikes"]], ["late", "near", "ridge"])
        self.assertEqual(os.environ.get("TZ"), old)

    def test_explicit_offsets_still_convert_to_pacific(self):  # 9
        for start in ("2026-11-03T17:00:00Z", "2026-11-03T17:00:00+00:00", "2026-11-03T09:00:00-08:00",
                      "2026-11-03T18:00:00+01:00"):
            with self.subTest(start=start):
                self.hikes(hike("ridge", start, title="Ridge"))
                self.assertEqual(json.loads(self.report("--json"))["hikes"][0]["day"], "2026-11-03")
                self.assertEqual(self.hikes_line(), f"Hikes: Tuesday 9:00 am Ridge ({UNAV})")
        # a zone named elsewhere in the event never makes a naive start aware
        self.hikes(dict(hike("naive", "2026-11-03T09:00:00"), timezone="America/Los_Angeles", utcOffset="-08:00"))
        self.assertNotIn("Hikes", self.report())

    def test_all_zone_less_starts_leave_shelf_report_unchanged(self):  # 10
        self.hikes()
        plain, plain_json = self.report(), self.report("--json")
        self.hikes(hike("naive", "2026-11-03T01:00:00"), hike("dateonly", "2026-11-02"))
        db = self.rsvp_db([("naive", 2)])
        before = self.tree_bytes()
        self.assertEqual((self.report(), self.report("--guests", db), self.report("--json")), (plain, plain, plain_json))
        self.assertNotIn("hikes", json.loads(self.report("--json")))
        self.assertEqual(self.tree_bytes(), before)  # content and the RSVP database are not written

    def test_out_of_range_start_is_skipped_without_traceback(self):  # 11
        self.hikes(hike("ancient", "0001-01-01T00:00:00+00:00"), hike("far", "9999-12-31T23:59:59-08:00"),
                   hike("ridge", "2026-11-03T09:00:00-08:00"))
        self.assertEqual(self.hikes_line(), f"Hikes: Tuesday 9:00 am Ridge ({UNAV})")
        self.assertEqual([h["id"] for h in json.loads(self.report("--json"))["hikes"]], ["ridge"])


if __name__ == "__main__":
    unittest.main()
