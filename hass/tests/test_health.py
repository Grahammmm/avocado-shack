"""H19 tests: hass/health.py read-only state health check with change-only notify.

Temp 0700 state dirs, temp SQLite stores built from the conversation schema with placeholder rows, an injected clock.
Never the real private state. Run: python3 -m unittest discover -s hass/tests -t . -v
"""
import contextlib, io, json, os, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import conversation, health
from hass.content_model import REPO_ROOT

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}


def iso(minutes_ago, seconds=0):
    return (NOW - timedelta(minutes=minutes_ago, seconds=seconds)).isoformat(timespec="seconds")


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        self.settings(SETTINGS)

    def settings(self, settings):
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": settings}))

    def db(self, *rows, paused=None):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            db.executescript(conversation.SCHEMA)
            for table, values in rows:
                cols = ("chat", "text", "attachments", "created_at", "sent_at") if table == "outbox" else \
                    ("code", "state", "ops_json", "summary", "sender", "chat", "created_at")
                db.execute(f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", values)
            if paused:
                db.execute(conversation.CONTROL)
                db.execute("INSERT INTO control VALUES ('paused', '1', ?, 'p1')", (paused,))

    def run_health(self, *extra, state=None, now=NOW):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(state or self.state), *extra], now=now)
        [line] = out.getvalue().splitlines()
        return code, json.loads(line)

    def ids(self, doc):
        return [p["check"] for p in doc["problems"]]

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(self.state.rglob("*"))}

    def test_healthy_fresh_state(self):
        code, doc = self.run_health()
        self.assertEqual((code, doc["ok"], doc["problems"], doc["notify"]), (0, True, [], False))
        self.assertEqual(doc["info"], [{"check": "conversation", "detail": "no conversation yet"}])
        self.assertFalse((self.state / "conversation.sqlite3").exists())

    def test_bad_settings_and_unsafe_state(self):
        self.settings({**SETTINGS, "approvalTtlSeconds": 30})
        code, doc = self.run_health()
        self.assertEqual((code, self.ids(doc), doc["ok"], doc["notify"]), (1, ["settings"], False, True))
        (self.state / "config.json").unlink()
        self.assertEqual(self.ids(self.run_health()[1]), ["settings"])
        os.symlink(self.state, self.tmp / "link")
        code, doc = self.run_health(state=self.tmp / "link")
        self.assertEqual((code, self.ids(doc)), (2, ["state"]))
        self.assertEqual(self.run_health(state=self.tmp / "missing")[0], 2)
        self.assertFalse((self.tmp / "missing").exists())
        os.chmod(self.state, 0o750)
        self.assertEqual(self.run_health()[0], 2)

    def test_stuck_outbox_and_apply_counts_and_read_only(self):
        self.db(("outbox", ("c", "t", "[]", iso(15, 1), None)), ("outbox", ("c", "t", "[]", iso(16), None)),
                ("outbox", ("c", "t", "[]", iso(15), None)), ("outbox", ("c", "t", "[]", iso(90), iso(89))),
                ("drafts", ("a1", "approved", "[]", "s", "o", "c", iso(10, 1))),
                ("drafts", ("a2", "approved", "[]", "s", "o", "c", iso(10))),
                ("drafts", ("a3", "applied", "[]", "s", "o", "c", iso(60))))
        os.chmod(self.state / "conversation.sqlite3", 0o600)
        before = self.snapshot()
        code, doc = self.run_health()
        self.assertEqual(code, 1)
        self.assertEqual(doc["problems"], [{"check": "outbox-stuck", "detail": "2"},
                                           {"check": "apply-stuck", "detail": "1"}])
        self.run_health("--seen", str(self.tmp / "seen"), "--backups", str(self.tmp))
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("writer.lock", os.listdir(self.state))
        self.assertEqual(self.run_health("--outbox-minutes", "17")[1]["problems"],
                         [{"check": "apply-stuck", "detail": "1"}])

    def test_paused_is_info_only(self):
        self.db(paused=iso(5))
        code, doc = self.run_health()
        self.assertEqual((code, doc["ok"]), (0, True))
        self.assertIn({"check": "paused", "detail": iso(5)}, doc["info"])

    def test_corrupt_db(self):
        (self.state / "conversation.sqlite3").write_bytes(b"not a database " * 100)
        code, doc = self.run_health()
        self.assertEqual((code, self.ids(doc)), (1, ["db-integrity"]))

    @mock.patch.object(health.statebackup, "verify", return_value={"result": "ok", "files": 1})  # placeholder {}
    def test_backups(self, _verify):
        backups = self.tmp / "backups"
        backups.mkdir()
        self.assertEqual(self.run_health("--backups", str(backups))[1]["problems"],
                         [{"check": "backup-age", "detail": "no complete backup"}])
        old = backups / (NOW - timedelta(hours=27)).strftime(health.STAMP)
        old.mkdir()
        (old / "MANIFEST.json").write_text("{}")
        (backups / (NOW - timedelta(hours=1)).strftime(health.STAMP)).mkdir()  # newer, no MANIFEST: ignored
        code, doc = self.run_health("--backups", str(backups))
        self.assertEqual((code, doc["problems"][0]["detail"]), (1, "newest complete backup older than 26 h"))
        self.assertEqual(self.run_health("--backups", str(backups), "--backup-hours", "28")[0], 0)
        fresh = backups / (NOW - timedelta(hours=2)).strftime(health.STAMP)
        fresh.mkdir()
        (fresh / "MANIFEST.json").write_text("{}")
        self.assertEqual(self.run_health("--backups", str(backups))[0], 0)
        self.assertEqual(self.run_health("--backups", str(self.tmp / "none"))[1]["problems"][0]["detail"],
                         "backup dir unreadable")

    def test_dedupe_with_seen(self):
        seen = self.tmp / "seen"
        self.settings({**SETTINGS, "approvalTtlSeconds": 30})
        first, second = self.run_health("--seen", str(seen))[1], self.run_health("--seen", str(seen))[1]
        self.assertEqual((first["notify"], second["notify"]), (True, False))
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(seen.stat().st_mode & 0o777, 0o600)
        self.db(("outbox", ("c", "t", "[]", iso(30), None)))  # a changed problem set alerts again
        self.assertEqual([self.run_health("--seen", str(seen))[1]["notify"] for _ in range(2)], [True, False])
        self.settings(SETTINGS)
        os.unlink(self.state / "conversation.sqlite3")
        fixed = [self.run_health("--seen", str(seen)) for _ in range(2)]
        self.assertEqual([(c, d["ok"], d["notify"]) for c, d in fixed], [(0, True, True), (0, True, False)])
        self.assertEqual(sorted(os.listdir(self.tmp)), ["seen", "state"])  # no temp files left behind

    def test_unsafe_seen_paths(self):
        os.symlink(self.tmp / "target", self.tmp / "seenlink")
        for bad in (REPO_ROOT / "hass" / "tests" / "seen-health", self.tmp / "seenlink", self.state / "seen",
                    self.tmp / "nodir" / "seen"):
            code, doc = self.run_health("--seen", str(bad))
            self.assertEqual((code, self.ids(doc)), (2, ["seen"]), bad)
        self.assertFalse((REPO_ROOT / "hass" / "tests" / "seen-health").exists())
        self.assertFalse((self.tmp / "target").exists())
        self.assertEqual(os.listdir(self.state), ["config.json"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            health.main(["--state", str(self.state), "--outbox-minutes", "0"])
        self.assertEqual(exc.exception.code, 2)

    def limit_db(self, usage=None, *messages, cap=2, table=True):  # AV1922-03: synthetic ids only; usage = (day, calls)
        self.settings({**SETTINGS, **({} if cap is None else {"interpreterDailyCap": cap})})
        self.db()
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            if usage is not None:
                db.execute(conversation.USAGE)
                db.execute("INSERT INTO usage VALUES (?, ?)", usage)
            elif not table:
                db.execute("DROP TABLE messages")
            for n, (disposition, at) in enumerate(messages):
                db.execute("INSERT INTO messages VALUES (?, ?, ?)", (f"canary-id-{n}", disposition, at))

    def test_daily_limit_under_cap_and_at_cap_without_refusal(self):
        for calls in (1, 2):
            self.limit_db(("2026-11-02", calls), ("ok", "2026-11-02T16:00:00+00:00"))
            code, doc = self.run_health()
            self.assertEqual((code, doc["ok"], doc["problems"], doc["notify"]), (0, True, [], False))
            self.assertEqual(doc["info"], [{"check": "interpreter", "detail": f"{calls} of 2 today"}])
            os.unlink(self.state / "conversation.sqlite3")

    def test_daily_limit_counts_today_in_pacific_without_private_fields(self):
        self.limit_db(("2026-11-02", 1), ("daily-limit", "2026-11-02T08:00:00+00:00"),  # Pacific midnight: today
                      ("daily-limit", "2026-11-03T07:59:00+00:00"), ("daily-limit", "2026-11-02T00:30:00-08:00"),
                      ("daily-limit", "2026-11-02T07:59:59+00:00"),  # 23:59:59 on Nov 1: yesterday
                      ("daily-limit", "2026-11-03T08:00:00+00:00"),  # Nov 3 midnight: tomorrow
                      ("daily-limit", "2026-11-02T10:00:00"), ("daily-limit", "junk"), ("daily-limit", ""),
                      ("daily-limit", None), ("unsupported", "2026-11-02T10:00:00+00:00"))
        code, doc = self.run_health()
        self.assertEqual((code, doc["ok"], doc["notify"]), (1, False, True))
        self.assertEqual(doc["problems"], [{"check": "daily-limit", "detail": "3 message(s) not read today, cap 2"}])
        self.assertEqual(doc["info"], [{"check": "interpreter", "detail": "1 of 2 today"}])
        self.assertNotIn("canary", json.dumps(doc))

    def test_daily_limit_fall_back_and_spring_forward_days(self):
        self.limit_db(None, ("daily-limit", "2026-11-01T08:30:00+00:00"), ("daily-limit", "2026-11-02T07:59:00+00:00"),
                      ("daily-limit", "2026-11-02T08:00:00+00:00"))  # the 25-hour Nov 1 ends at 08:00 UTC
        for now in (datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc), datetime(2026, 11, 2, 7, 59, tzinfo=timezone.utc)):
            self.assertEqual(self.run_health(now=now)[1]["problems"][0]["detail"], "2 message(s) not read today, cap 2")
        os.unlink(self.state / "conversation.sqlite3")
        self.limit_db(None, ("daily-limit", "2027-03-14T07:59:00+00:00"), ("daily-limit", "2027-03-14T08:00:00+00:00"),
                      ("daily-limit", "2027-03-15T06:59:00+00:00"), ("daily-limit", "2027-03-15T07:00:00+00:00"))
        got = self.run_health(now=datetime(2027, 3, 14, 20, 0, tzinfo=timezone.utc))[1]["problems"][0]["detail"]
        self.assertEqual(got, "2 message(s) not read today, cap 2")  # the 23-hour Mar 14 ends at 07:00 UTC

    def test_daily_limit_missing_tables_and_no_cap(self):
        self.limit_db(None, ("daily-limit", "2026-11-02T10:00:00+00:00"))  # no usage table: 0 calls, refusal still seen
        code, doc = self.run_health()
        self.assertEqual((code, self.ids(doc), doc["info"]), (1, ["daily-limit"], [{"check": "interpreter", "detail": "0 of 2 today"}]))
        os.unlink(self.state / "conversation.sqlite3")
        self.limit_db(("2026-11-01", 2), table=False)  # no messages table, only yesterday's usage
        code, doc = self.run_health()
        self.assertEqual((code, doc["problems"], doc["info"]), (0, [], [{"check": "interpreter", "detail": "0 of 2 today"}]))
        os.unlink(self.state / "conversation.sqlite3")
        self.settings({**SETTINGS, "interpreterDailyCap": 2})  # no database at all
        code, doc = self.run_health()
        self.assertEqual((code, doc["info"]), (0, [{"check": "conversation", "detail": "no conversation yet"},
                                                   {"check": "interpreter", "detail": "0 of 2 today"}]))
        self.assertFalse((self.state / "conversation.sqlite3").exists())
        self.limit_db(("2026-11-02", 2), ("daily-limit", "2026-11-02T10:00:00+00:00"), cap=None)  # history, no cap
        code, doc = self.run_health()
        self.assertEqual((code, doc["problems"], doc["info"]), (0, [], []))

    def test_daily_limit_read_only_and_change_only_notify(self):
        self.limit_db(("2026-11-02", 2), ("daily-limit", "2026-11-02T10:00:00+00:00"))
        os.chmod(self.state / "conversation.sqlite3", 0o600)
        before, seen = self.snapshot(), self.tmp / "seen"
        docs = [self.run_health("--seen", str(seen))[1] for _ in range(2)]
        self.assertEqual([d["notify"] for d in docs], [True, False])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(seen.stat().st_mode & 0o777, 0o600)
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            db.execute("UPDATE usage SET calls = 2 WHERE day = '2026-11-02'")  # a usage-only change is info: silent
            db.execute("INSERT INTO messages VALUES ('canary-id-x', 'daily-limit', '2026-11-02T11:00:00+00:00')")
        changed = self.run_health("--seen", str(seen))[1]
        self.assertEqual((changed["notify"], changed["problems"][0]["detail"]), (True, "2 message(s) not read today, cap 2"))
        self.assertEqual(self.run_health("--seen", str(seen))[1]["notify"], False)
        next_day = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)  # 01:00 on Nov 3 Pacific: cleared once
        code, cleared = self.run_health("--seen", str(seen), now=next_day)
        self.assertEqual((code, cleared["ok"], cleared["notify"], cleared["info"]),
                         (0, True, True, [{"check": "interpreter", "detail": "0 of 2 today"}]))

    def test_daily_limit_unreadable_db_reports_no_usage(self):
        self.settings({**SETTINGS, "interpreterDailyCap": 2})
        (self.state / "conversation.sqlite3").write_bytes(b"not a database " * 100)
        code, doc = self.run_health()
        self.assertEqual((code, self.ids(doc), doc["info"]), (1, ["db-integrity"], []))


if __name__ == "__main__":
    unittest.main()
