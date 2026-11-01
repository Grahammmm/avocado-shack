"""RF1650-12 (H17/H19): health reports a pause older than --paused-hours (default 24) as problem `paused-long`.

Temp 0700 state dirs and seen folders outside the repo, placeholder rows, an injected clock. Never the real state.
"""
import contextlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import conversation, health

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat(timespec="seconds")


class HealthPausedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))

    def db(self, paused=None, control=True):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            db.executescript(conversation.SCHEMA)
            if control: db.execute(conversation.CONTROL)
            if paused is not None: db.execute("INSERT INTO control VALUES ('paused', '1', ?, 'p1')", (paused,))

    def run_health(self, *extra, now=NOW):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = health.main(["--state", str(self.state), *extra], now=now)
        self.assertEqual(err.getvalue(), "")  # no traceback
        [line] = out.getvalue().splitlines()
        return code, json.loads(line)

    def long(self, doc):
        return [p for p in doc["problems"] if p["check"] == "paused-long"]

    def assert_info_only(self, set_at, *extra):
        code, doc = self.run_health(*extra)
        self.assertEqual((code, doc["ok"], doc["problems"]), (0, True, []))
        self.assertIn({"check": "paused", "detail": set_at}, doc["info"])

    def assert_long(self, set_at, detail, *extra, now=NOW):
        code, doc = self.run_health(*extra, now=now)
        self.assertEqual((code, doc["ok"], self.long(doc)), (1, False, [{"check": "paused-long", "detail": detail}]))
        self.assertIn({"check": "paused", "detail": set_at}, doc["info"])  # the info line is kept
        return doc

    def test_short_pause_is_info_only(self):
        self.db(paused=ago(2))
        self.assert_info_only(ago(2))

    def test_pause_over_default_24_hours_is_a_problem(self):
        self.db(paused=ago(25))
        self.assert_long(ago(25), "over 24 h")

    def test_paused_hours_flag_moves_the_limit(self):
        self.db(paused=ago(25))
        self.assert_info_only(ago(25), "--paused-hours", "48")
        (self.state / "conversation.sqlite3").unlink()
        self.db(paused=ago(49))
        self.assert_long(ago(49), "over 48 h", "--paused-hours", "48")

    def test_exact_boundary_is_not_long(self):  # _older: strictly before the limit
        self.db(paused=ago(24))
        self.assert_info_only(ago(24))

    def test_one_second_past_boundary_is_long(self):
        set_at = (NOW - timedelta(hours=24, seconds=1)).isoformat(timespec="seconds")
        self.db(paused=set_at)
        self.assert_long(set_at, "over 24 h")

    def test_unreadable_time_is_long(self):
        for raw in ("yesterday", "", "2026-11-02T10:00:00"):  # words, empty, zone-less: unreadable (fail closed)
            with self.subTest(raw=raw):
                self.db(paused=raw)
                self.assert_long(raw, "unreadable time")
                (self.state / "conversation.sqlite3").unlink()

    def test_future_time_is_not_long(self):  # a readable time ahead of the clock is a short pause
        self.db(paused=ago(-3))
        self.assert_info_only(ago(-3))

    def test_not_paused_has_neither_line(self):
        for kwargs in ({}, {"control": False}):
            with self.subTest(**kwargs):
                self.db(**kwargs)
                code, doc = self.run_health()
                self.assertEqual((code, doc["problems"]), (0, []))
                self.assertNotIn("paused", {i["check"] for i in doc["info"]})
                (self.state / "conversation.sqlite3").unlink()

    def test_zero_or_bad_paused_hours_is_usage_error(self):
        for value in ("0", "-1", "x"):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(SystemExit) as ctx:
                    health.main(["--state", str(self.state), "--paused-hours", value], now=NOW)
                self.assertEqual((ctx.exception.code, out.getvalue()), (2, ""))

    def test_same_long_pause_notifies_once(self):
        self.db(paused=ago(30))
        folder = self.tmp / "seendir"
        folder.mkdir(mode=0o700)
        seen = ["--seen", str(folder / "fp-health")]
        first = self.assert_long(ago(30), "over 24 h", *seen)
        second = self.assert_long(ago(30), "over 24 h", *seen, now=NOW + timedelta(hours=5))  # later run, same pause
        self.assertEqual((first["notify"], second["notify"]), (True, False))
        self.assertEqual(first["fingerprint"], second["fingerprint"])


if __name__ == "__main__":
    unittest.main()
