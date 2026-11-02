"""AV1537-11 (H19 x H06): hass/health.py reports applied changes whose preview check failed (unverified, count only).

Temp 0700 state dirs, draft rows inserted into a fixture conversation DB (conversation.SCHEMA), a fixed clock."""
import contextlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path

from hass import conversation, health
from hass.tests import test_health as base
from hass.tests.test_status_pause import FailingPreviewer
from hass.tests.test_undo import FakePreviewer, H06TestCase

NOW, SECRET = base.NOW, "SECRET-SENTINEL"
COLS = ("code", "state", "reason", "checked_at", "ops_json", "summary", "sender", "chat", "created_at",
        "screenshot")


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat(timespec="seconds")


class HealthUnverifiedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": base.SETTINGS}))
        self.path = self.state / "conversation.sqlite3"

    def draft(self, state, reason, checked_at, code="ab12", summary="placeholder change", screenshot=None):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(conversation.SCHEMA)
            db.execute(f"INSERT INTO drafts({', '.join(COLS)}) VALUES ({', '.join('?' * len(COLS))})",
                       (code, state, reason, checked_at, "[]", summary, "owner@example.invalid",
                        "chat@example.invalid", ago(0), screenshot))

    def failed(self, hours, error="x", **kw):
        when = hours if isinstance(hours, str) else ago(hours)
        self.draft("applied", f"not verified: {error}", when, **kw)

    def run_raw(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state), *extra], now=NOW)
        [line] = out.getvalue().splitlines()
        return code, line

    def run_health(self, *extra):
        code, line = self.run_raw(*extra)
        return code, json.loads(line)["problems"]

    def unverified(self, n):
        return [{"check": "unverified", "detail": str(n)}]

    def test_one_failed_check_an_hour_ago(self):
        self.failed(1)
        self.assertEqual(self.run_health(), (1, self.unverified(1)))

    def test_window_default_and_flag(self):
        self.failed(73)
        self.assertEqual(self.run_health(), (0, []))
        self.assertEqual(self.run_health("--unverified-hours", "100"), (1, self.unverified(1)))
        self.assertEqual(health.check(str(self.state), now=NOW, unverified_hours=100)[0], self.unverified(1))
        self.assertEqual(health.check(str(self.state), now=NOW)[0], [])

    def test_window_edge_is_inside(self):
        self.failed(72)
        self.assertEqual(self.run_health(), (1, self.unverified(1)))
        self.assertEqual(self.run_health("--unverified-hours", "71"), (0, []))

    def test_verified_unchecked_and_other_rows_not_counted(self):
        self.draft("verified", None, ago(1), code="v1", screenshot="v1.png")
        self.draft("applied", None, None, code="n1")  # no previewer: never checked
        self.draft("applied", "not verified: x", None, code="n2")  # reason without a check time
        self.draft("reverted", "undone by cd34", ago(1), code="r1", screenshot="r1.png")  # a checked change undone
        self.draft("reverted", "undone by cd35", None, code="r2")  # no previewer: never checked, then undone
        self.draft("rejected", "not verified: x", ago(1), code="j1")
        self.draft("applied", "verified elsewhere: not verified: x", ago(1), code="w1")  # wording is not a prefix
        self.assertEqual(self.run_health(), (0, []))
        self.failed(1, code="f1")
        self.failed(2, code="f2")
        self.assertEqual(self.run_health(), (1, self.unverified(2)))

    def test_failed_change_later_undone_counts_until_the_window_passes(self):
        self.draft("reverted", "undone by cd34", ago(72), code="r1")  # _outcome rewrote the reason; no screenshot
        self.assertEqual(self.run_health(), (1, self.unverified(1)))
        self.assertEqual(self.run_health("--unverified-hours", "71"), (0, []))

    def test_unreadable_checked_at_counts(self):
        self.failed("garbage", code="g1")
        self.failed("2026-01-01T00:00:00", code="g2")  # zone-less, even though long ago
        self.assertEqual(self.run_health(), (1, self.unverified(2)))

    def test_drafts_without_checked_at_column_skipped(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE drafts(row_id INTEGER PRIMARY KEY, code TEXT, state TEXT, reason TEXT,"
                       " created_at TEXT)")
            db.execute("INSERT INTO drafts(code, state, reason, created_at) VALUES ('h5', 'applied', ?, ?)",
                       ("not verified: x", ago(0)))
        self.assertEqual(self.run_health(), (0, []))

    def test_no_drafts_table(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE other(x)")
        self.assertEqual(self.run_health(), (0, []))

    def test_zero_or_negative_hours_refused(self):
        self.failed(1)
        for bad in ("0", "-1"):
            out = io.StringIO()
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out), \
                    self.assertRaises(SystemExit) as exc:
                health.main(["--state", str(self.state), "--unverified-hours", bad], now=NOW)
            self.assertEqual((exc.exception.code, out.getvalue()), (2, ""))

    def test_output_names_no_code_summary_or_error(self):
        self.failed(1, code="ee99", summary=f"{SECRET}-summary", error=f"{SECRET}-error")
        code, line = self.run_raw()
        self.assertEqual(code, 1)
        self.assertEqual([s for s in (SECRET, "ee99", "not verified", "example.invalid") if s in line], [])
        self.assertEqual(json.loads(line)["problems"], self.unverified(1))

    def test_read_only(self):
        self.failed(1)
        before = {p.name: p.read_bytes() for p in self.state.iterdir()}
        self.run_health()
        self.assertEqual({p.name: p.read_bytes() for p in self.state.iterdir()}, before)


class UndoAfterPreviewTest(H06TestCase):
    """A real conversation: preview check, then undo (history.revert) applied and checked."""

    def unverified(self, hours):
        problems = health.check(str(self.repo.state), now=self.now + timedelta(hours=hours))[0]
        return [p for p in problems if p["check"] == "unverified"]

    def apply_then_undo(self, previewer):
        self.previewer = previewer
        self.conv = self.open()
        done = self.apply("desc")
        self.previewer = FakePreviewer()  # the undo itself passes its check
        self.conv = self.open()
        self.assertEqual(self.say(f"undo {done['code']}"), "proposed")
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        orig, undo = self.drafts()
        self.assertIn('"history.revert"', undo["ops_json"])
        self.assertEqual((orig["state"], orig["reason"], undo["state"]),
                         ("reverted", f"undone by {undo['code']}", "verified"))
        return done

    def test_failed_preview_then_undo_still_counts_inside_the_window(self):
        done = self.apply_then_undo(FailingPreviewer())
        self.assertEqual((done["state"], done["reason"]),
                         ("applied", "not verified: products photo-product-001: simulated check failure"))
        self.assertEqual(self.unverified(1), [{"check": "unverified", "detail": "1"}])
        self.assertEqual(self.unverified(72), [{"check": "unverified", "detail": "1"}])
        self.assertEqual(self.unverified(73), [])

    def test_passed_preview_then_undo_not_counted(self):
        self.apply_then_undo(FakePreviewer())
        self.assertEqual(self.unverified(1), [])


if __name__ == "__main__":
    unittest.main()
