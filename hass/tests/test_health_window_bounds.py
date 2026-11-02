"""RF0050-2: health.py refuses a window over 100 years as a usage error (exit 2). Temp state; unittest discover."""
import contextlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import conversation, health, inbox
from hass.tests.test_health import NOW, SETTINGS, iso

MAX_H = health.MAX_WINDOW_HOURS
BOUNDS = {"--outbox-minutes": MAX_H * 60, "--inbox-minutes": MAX_H * 60, "--backup-hours": MAX_H,
          "--inbox-unreadable-hours": MAX_H, "--unverified-hours": MAX_H, "--paused-hours": MAX_H}
BOUND_TEXT = f"minutes must be at most {MAX_H * 60} and hours at most {MAX_H} (100 years)"


class WindowBoundsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.backups, self.seen = self.tmp / "state", self.tmp / "backups", self.tmp / "seen"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            db.executescript(conversation.SCHEMA + conversation.CONTROL + ";")  # outbox: today's overflow path
            db.execute("INSERT INTO outbox(chat, text, attachments, created_at) VALUES ('c', 't', '[]', ?)",
                       (iso(60 * 24 * 365),))  # a year-old unsent reply lies inside a 100-year window
            db.execute("INSERT INTO control VALUES ('paused', '1', ?, 'p1')", (iso(60),))
        with contextlib.closing(sqlite3.connect(self.state / "inbox.sqlite3")) as db, db: db.executescript(inbox.SCHEMA)
        (old := self.backups / (NOW - timedelta(days=365 * 50)).strftime(health.STAMP)).mkdir(parents=True)
        (old / "MANIFEST.json").write_text("{}")
        self.seen.write_text("previous\n")

    def args(self, **over):
        return ["--state", str(self.state), "--backups", str(self.backups), "--seen", str(self.seen),
                *(str(x) for kv in {**BOUNDS, **over}.items() for x in kv)]

    def refused(self, argv):
        snap = lambda: {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.tmp.rglob("*") if p.is_file()}  # noqa
        out, err, before = io.StringIO(), io.StringIO(), snap()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as exc, \
                mock.patch.object(health, "check", side_effect=AssertionError("check ran")) as check:
            health.main(argv, now=NOW)
        self.assertEqual((exc.exception.code, out.getvalue(), check.call_count, snap()), (2, "", 0, before))
        self.assertNotIn("Traceback", err.getvalue())  # state, backups and --seen untouched; no JSON line
        return err.getvalue()

    @mock.patch.object(health.statebackup, "verify", return_value={"result": "ok", "files": 1})  # placeholder {}
    def test_every_flag_at_its_bound_runs_normally(self, _verify):
        with contextlib.redirect_stdout(out := io.StringIO()): code = health.main(self.args(), now=NOW)
        [line] = out.getvalue().splitlines()  # one JSON line
        self.assertEqual((code, json.loads(line)["problems"], json.loads(line)["info"]),
                         (0, [], [{"check": "paused", "detail": iso(60)}]))

    def test_each_flag_over_its_bound_and_huge_values_are_usage_errors(self):
        for flag, bound in BOUNDS.items():
            with self.subTest(flag):
                self.assertIn(BOUND_TEXT, self.refused(self.args(**{flag: bound + 1})))
        for flag, value in (("--outbox-minutes", 9_999_999_999), ("--backup-hours", 20_000_000),
                            ("--paused-hours", 10 ** 20), ("--inbox-minutes", 10 ** 20)):
            with self.subTest(flag, value=value):  # bare argv too: the refusal needs no other flag
                self.assertIn(BOUND_TEXT, self.refused(["--state", str(self.state), flag, str(value)]))

    def test_zero_and_negative_keep_the_old_refusal(self):
        for flag in BOUNDS:
            for value in ("0", "-5"):
                with self.subTest(flag, value=value):
                    err = self.refused(self.args(**{flag: value}))
                    self.assertIn("minutes and hours must be >= 1", err)
                    self.assertNotIn("100 years", err)
