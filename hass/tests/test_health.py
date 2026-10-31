"""H19 tests: hass/health.py read-only state health check with change-only notify.

Temp 0700 state dirs, temp SQLite stores built from the conversation schema with placeholder rows, an injected clock.
Never the real private state. Run: python3 -m unittest discover -s hass/tests -t . -v
"""
import contextlib, io, json, os, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

    def test_backups(self):
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


if __name__ == "__main__":
    unittest.main()
