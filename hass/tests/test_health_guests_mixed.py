"""RF1230-25 (H19): with guestCountsDb unset, one malformed hike in community.json never hides a readable upcoming
RSVP hike. Each event is judged on its own: any readable upcoming RSVP hike gives problem `unset`, any unreadable
event adds info `hikes unreadable` (once). Fixed details only, never a path, title or time.

Temp 0700 state dir, a plain temp worktree holding only hass/content/community.json, a temp RSVP sqlite, a fixed
clock (builders copied from test_health_guests). Never the real state, worktree or community database.
Run: python3 -m unittest hass.tests.test_health_guests_mixed -v
"""
import contextlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path

from hass import health
from hass.tests.test_health import NOW, SETTINGS

UNSET = {"check": "guest-counts", "detail": "unset"}
HIKES_INFO = {"check": "guest-counts", "detail": "hikes unreadable"}
BAD_TIME = {"id": "bad", "title": "Bad Hike", "status": "scheduled", "rsvpEnabled": True, "startsAt": "not a time"}


def event(eid, days, rsvp=True, status="scheduled"):
    return {"id": eid, "title": eid, "status": status, "rsvpEnabled": rsvp,
            "startsAt": (NOW + timedelta(days=days)).isoformat(timespec="seconds")}


def bad(**fields):  # a scheduled RSVP event whose start time cannot be read
    return dict(BAD_TIME, **fields)


class HealthGuestsMixedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.wt = self.tmp / "state", self.tmp / "wt"
        self.state.mkdir(mode=0o700)
        (self.wt / "hass" / "content").mkdir(parents=True)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.wt), "settings": SETTINGS}))

    def events(self, *events, raw=None):
        path = self.wt / "hass" / "content" / "community.json"
        path.write_text(raw if raw is not None else json.dumps({"events": list(events)}))

    def check(self, *events, raw=None):  # -> (exit code, guest-counts problems, count of the hikes info)
        self.events(*events, raw=raw)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state)], now=NOW)
        [line] = out.getvalue().splitlines()
        for text in (str(self.tmp), "Bad Hike", "not a time", "2027-01-01"):
            self.assertNotIn(text, line)  # fixed details only: no path, title or time
        doc = json.loads(line)
        return code, [p for p in doc["problems"] if p["check"] == "guest-counts"], doc["info"].count(HIKES_INFO)

    def test_bad_time_never_hides_an_upcoming_rsvp_hike_in_either_order(self):  # edge 1
        for broken in (bad(), bad(startsAt="2027-01-01T09:00:00"), bad(startsAt=5), bad(startsAt=None),
                       {k: v for k, v in BAD_TIME.items() if k != "startsAt"}):
            for order in ((broken, event("h1", 3)), (event("h1", 3), broken)):
                with self.subTest(broken=broken.get("startsAt", "missing"), first=order[0]["id"]):
                    self.assertEqual(self.check(*order), (1, [UNSET], 1))

    def test_non_dict_entry_never_hides_an_upcoming_rsvp_hike(self):  # edge 2
        for entry in ("hike", None, 5, ["x"]):
            for order in ((entry, event("h1", 3)), (event("h1", 3), entry)):
                with self.subTest(entry=entry, order=[type(e).__name__ for e in order]):
                    self.assertEqual(self.check(*order), (1, [UNSET], 1))

    def test_several_bad_events_add_the_info_once(self):  # duplicate unreadable rows: one info entry
        self.assertEqual(self.check(bad(), "hike", event("h1", 3), None, bad(startsAt="")), (1, [UNSET], 1))
        self.assertEqual(self.check(bad(), "hike", None), (0, [], 1))

    def test_bad_event_alone_is_info_only(self):  # edge 3: test 6 unchanged
        for broken in (bad(startsAt="2027-01-01T09:00:00"), bad(), "hike"):
            with self.subTest(broken=broken):
                self.assertEqual(self.check(broken), (0, [], 1))

    def test_bad_time_is_never_read_unless_scheduled_with_rsvp(self):  # edge 3: no time read, so neither
        for broken in (bad(status="cancelled"), bad(status="completed"), bad(rsvpEnabled=False), bad(rsvpEnabled=None),
                       {k: v for k, v in bad(status="cancelled").items() if k != "startsAt"}):
            with self.subTest(status=broken["status"], rsvp=broken["rsvpEnabled"]):
                self.assertEqual(self.check(broken), (0, [], 0))
                self.assertEqual(self.check(broken, event("h1", 3)), (1, [UNSET], 0))

    def test_past_rsvp_hike_with_bad_event_is_info_only(self):  # edge 4
        for order in ((event("past", -1), bad()), (bad(), event("past", -1)), (event("now", 0), "hike")):
            with self.subTest(first=str(order[0])[:20]):
                self.assertEqual(self.check(*order), (0, [], 1))

    def test_events_not_a_list_is_info_only(self):  # edge 5: dict, text, missing or null events
        for raw in ('{"events": {"h1": ' + json.dumps(event("h1", 3)) + "}}", '{"events": "h1"}', '{"other": []}',
                    '{"events": null}'):
            with self.subTest(raw=raw[:24]):
                self.assertEqual(self.check(raw=raw), (0, [], 1))

    def test_set_and_readable_db_never_reads_events(self):  # edge 5: guestCountsDb set, the events are not read
        with contextlib.closing(sqlite3.connect(rsvp := self.tmp / "rsvps.sqlite3")) as db, db:
            db.execute("CREATE TABLE rsvps (event_id TEXT, name TEXT, email TEXT, party_size INTEGER)")
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.wt), "settings": dict(
            SETTINGS, guestCountsDb=str(rsvp))}))
        for events in ((bad(), event("h1", 3)), ("hike",)):
            with self.subTest(n=len(events)):
                self.assertEqual(self.check(*events), (0, [], 0))
        self.assertEqual(self.check(raw="{"), (0, [], 0))


if __name__ == "__main__":
    unittest.main()
