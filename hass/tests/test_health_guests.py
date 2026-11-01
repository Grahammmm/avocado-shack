"""AV1537-12 (H19): health reports guest-counts when guestCountsDb is set but unreadable, or unset while an upcoming
scheduled hike takes RSVPs. Counts only; never the path, a guest name or an email.

Temp 0700 state dir, a plain temp worktree holding only hass/content/community.json, a temp RSVP sqlite with an
`rsvps` table and placeholder guests, a fixed clock. Never the real state, worktree or community database.
Run: python3 -m unittest hass.tests.test_health_guests -v
"""
import contextlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path

from hass import health
from hass.tests.test_health import NOW, SETTINGS

SENTINEL = "Zebulon Quillfeather"  # placeholder guest name that must never reach stdout
UNREADABLE, UNSET = {"check": "guest-counts", "detail": "unreadable"}, {"check": "guest-counts", "detail": "unset"}
HIKES_INFO = {"check": "guest-counts", "detail": "hikes unreadable"}


def event(eid, days, rsvp=True, status="scheduled"):
    return {"id": eid, "title": eid, "status": status, "rsvpEnabled": rsvp,
            "startsAt": (NOW + timedelta(days=days)).isoformat(timespec="seconds")}


class HealthGuestsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.wt = self.tmp / "state", self.tmp / "wt"
        self.state.mkdir(mode=0o700)
        (self.wt / "hass" / "content").mkdir(parents=True)
        self.rsvp = self.tmp / "rsvps.sqlite3"
        with contextlib.closing(sqlite3.connect(self.rsvp)) as db, db:
            db.execute("CREATE TABLE rsvps (event_id TEXT, name TEXT, email TEXT, party_size INTEGER)")
            db.execute("INSERT INTO rsvps VALUES ('h1', ?, 'guest@example.invalid', 2)", (SENTINEL,))
        self.events()

    def config(self, db=None, **extra):
        settings = dict(SETTINGS, **extra) if db is None else dict(SETTINGS, guestCountsDb=str(db), **extra)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.wt), "settings": settings}))

    def events(self, *events, raw=None):
        path = self.wt / "hass" / "content" / "community.json"
        path.write_text(raw if raw is not None else json.dumps({"events": list(events)}))

    def run_health(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state)], now=NOW)
        [line] = out.getvalue().splitlines()
        for text in (str(self.tmp), SENTINEL, "guest@example.invalid", "rsvps.sqlite3"):
            self.assertNotIn(text, line)  # 2, 8: no path, guest name or email
        return code, json.loads(line)

    def guests(self):
        code, doc = self.run_health()
        return code, [p for p in doc["problems"] if p["check"] == "guest-counts"], doc

    def test_readable_db_is_no_problem(self):  # 1
        self.events(event("h1", 3))
        self.config(self.rsvp)
        code, found, doc = self.guests()
        self.assertEqual((code, doc["ok"], found), (0, True, []))

    def test_set_path_that_does_not_open_is_unreadable(self):  # 2, also with no RSVP hike at all
        self.events(event("h1", 3, rsvp=False))
        (not_sqlite := self.tmp / "notes.txt").write_text("not a database " * 40)
        for path in (self.tmp / "missing.sqlite3", self.tmp, not_sqlite):
            with self.subTest(path=path.name):
                self.config(path)
                code, found, doc = self.guests()
                self.assertEqual((code, doc["ok"], found), (1, False, [UNREADABLE]))
        self.assertFalse((self.tmp / "missing.sqlite3").exists())  # mode=ro never creates it

    def test_set_path_with_no_worktree_is_still_opened(self):  # 2: opened whether or not hikes can be read
        shutil.rmtree(self.wt)
        self.config(self.tmp / "missing.sqlite3")
        self.assertEqual(self.guests()[1], [UNREADABLE])

    def test_non_text_setting_is_unreadable(self):
        for value in (5, True, ["x"], {"p": 1}):
            with self.subTest(value=value):
                self.config(guestCountsDb=value)
                self.assertEqual(self.guests()[1], [UNREADABLE])

    def test_db_without_rsvps_table_is_unreadable(self):  # 3
        with contextlib.closing(sqlite3.connect(other := self.tmp / "other.sqlite3")) as db, db:
            db.execute("CREATE TABLE guests (event_id TEXT, party_size INTEGER)")
        self.config(other)
        self.assertEqual(self.guests()[1], [UNREADABLE])

    def test_unset_with_upcoming_rsvp_hike(self):  # 4
        self.events(event("past", -1), event("h1", 3), event("off", 4, rsvp=False))
        for extra in ({}, {"guestCountsDb": None}, {"guestCountsDb": ""}):
            with self.subTest(extra=extra):
                self.config(**extra)
                code, found, doc = self.guests()
                self.assertEqual((code, doc["ok"], found), (1, False, [UNSET]))
                self.assertNotIn(HIKES_INFO, doc["info"])

    def test_unset_without_upcoming_rsvp_hike_is_no_problem(self):  # 5
        self.config()
        for events in ([], [event("off", 3, rsvp=False)], [event("past", -1), event("off", 3, rsvp=False)],
                       [event("gone", 3, status="cancelled")], [event("done", 3, status="completed")],
                       [event("idea", 3, status="idea")], [event("now", 0)], [event("missing", 3, rsvp=None)]):
            with self.subTest(events=[e["id"] for e in events]):
                self.events(*events)
                code, found, doc = self.guests()
                self.assertEqual((code, doc["ok"], found), (0, True, []))
                self.assertNotIn(HIKES_INFO, doc["info"])

    def test_unset_and_community_unreadable_is_info_only(self):  # 6
        self.config()
        for raw in ("{", "[]", '{"events": {"a": 1}}', '{"other": []}', '{"events": [{"status": "scheduled",'
                    ' "rsvpEnabled": true, "startsAt": "not a time"}]}', '{"events": [{"status": "scheduled",'
                    ' "rsvpEnabled": true, "startsAt": "2027-01-01T09:00:00"}]}', None):
            with self.subTest(raw=raw):
                if raw is None:
                    (self.wt / "hass" / "content" / "community.json").unlink()
                else:
                    self.events(raw=raw)
                code, found, doc = self.guests()
                self.assertEqual((code, doc["ok"], found), (0, True, []))
                self.assertIn(HIKES_INFO, doc["info"])

    def test_unset_and_bad_writer_config_is_info_only(self):  # 6: config.json without a worktree
        (self.state / "config.json").write_text(json.dumps({"settings": SETTINGS}))
        code, found, doc = self.guests()
        self.assertEqual((code, found), (0, []))
        self.assertIn(HIKES_INFO, doc["info"])

    def test_unset_and_no_worktree_dir_adds_nothing(self):  # the `writer` check owns a missing worktree
        shutil.rmtree(self.wt)
        self.config()
        code, found, doc = self.guests()
        self.assertEqual((code, found), (0, []))
        self.assertNotIn(HIKES_INFO, doc["info"])

    def test_settings_error_skips_the_check(self):
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.wt), "settings": {
            "guestCountsDb": str(self.tmp / "missing.sqlite3")}}))
        code, doc = self.run_health()
        self.assertEqual([p["check"] for p in doc["problems"]], ["settings"])
        self.assertNotIn(HIKES_INFO, doc["info"])

    def test_rsvp_db_bytes_and_mtime_unchanged(self):  # 7, 8
        self.events(event("h1", 3))
        self.config(self.rsvp)
        before = (self.rsvp.read_bytes(), self.rsvp.stat().st_mtime_ns)
        files = sorted(p.name for p in self.tmp.iterdir())
        self.assertEqual(self.guests()[1], [])
        self.assertEqual((self.rsvp.read_bytes(), self.rsvp.stat().st_mtime_ns), before)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), files)  # no -journal/-wal left behind


if __name__ == "__main__":
    unittest.main()
