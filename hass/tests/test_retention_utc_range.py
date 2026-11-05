"""RF1110-13 tests: hass/retention.py treats a stored time whose UTC instant is outside year 1..9999 as undated.

Synthetic temp state/media dirs and an injected clock; never the real private state.
Run: python3 -B -m unittest hass.tests.test_retention_utc_range -v
"""
import contextlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

from hass import conversation, inbox, memory, retention
from hass.tests.test_retention import NOW, OLD, NEW, SHA_OLD, SHA_UNDATED, iso, tree

UNDER, OVER = "0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"
OK_EDGE_LOW, OK_EDGE_HIGH = "0001-01-01T14:00:00+14:00", "9999-12-31T09:59:59-14:00"
BAD = (UNDER, OVER)


class UtcRangeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.media = self.tmp / "state", self.tmp / "media"
        for d in (self.state, self.media): d.mkdir(mode=0o700)
        for name, schema in (("inbox.sqlite3", inbox.SCHEMA), ("conversation.sqlite3", conversation.SCHEMA + memory.TABLE)):
            with contextlib.closing(sqlite3.connect(self.state / name)) as db, db: db.executescript(schema)

    def conv(self, sql, *args):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db: db.execute(sql, args)

    def run_cli(self, *extra, state=None, now=iso(NOW)):
        out, err = io.StringIO(), io.StringIO()
        argv = ["report", "--state", str(state or self.state), "--days", "30", "--now", now, *extra]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try: code = retention.main(argv)
            except SystemExit as exc: code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_when_rejects_utc_underflow_and_overflow(self):
        for raw in BAD: self.assertIsNone(retention._when(raw), raw)
        for raw in (None, "", "garbage", "2026-11-02T17:00:00", 5): self.assertIsNone(retention._when(raw))
        for raw in ("2026-11-02T17:00:00+05:30", OK_EDGE_LOW, OK_EDGE_HIGH):
            got = retention._when(raw)
            self.assertEqual(got, datetime.fromisoformat(raw))
            self.assertEqual(got.isoformat(), datetime.fromisoformat(raw).isoformat())

    def test_stored_range_errors_do_not_abort_report(self):
        for bad in BAD:
            with self.subTest(bad=bad):
                for sql in ("DELETE FROM messages", "DELETE FROM outbox", "DELETE FROM drafts",
                            "DELETE FROM approvals", "DELETE FROM memory"): self.conv(sql)
                with contextlib.closing(sqlite3.connect(self.state / "inbox.sqlite3")) as db, db:
                    db.execute("DELETE FROM inbound")
                    for i, t in enumerate((bad, iso(OLD), iso(NEW))):
                        db.execute("INSERT INTO inbound(provider_id, received_at, state, enqueued_at) "
                                   "VALUES (?, ?, 'pending', 'x')", (f"p{i}", t))
                for i, t in enumerate((bad, iso(OLD))):
                    self.conv("INSERT INTO messages(provider_id, disposition, received_at) VALUES (?, 'd', ?)", f"m{i}", t)
                    self.conv("INSERT INTO outbox(chat, text, attachments, created_at) VALUES ('c', 't', '[]', ?)", t)
                    self.conv("INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at) "
                              "VALUES ('c', 'rejected', '[]', 's', 'a', 'c', ?)", t)
                    self.conv("INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, "
                              "approved_at) VALUES ('a', 'c', ?, 'x', 'h', 'b', 'e', ?)", f"a{i}", t)
                    self.conv("INSERT INTO memory(key, value, kind, source, created_at, forgotten_at) "
                              "VALUES ('k', 'v', 'fact', 'operator:x', 'c', ?)", t)
                code, out, err = self.run_cli()
                self.assertEqual((code, err), (0, ""))
                doc = json.loads(out)
                oldest = OLD.date().isoformat()
                self.assertEqual(doc["inbox"], {"done": 0, "history": 0, "pending": 1, "oldest": oldest})
                self.assertEqual(doc["messages"], {"rows": 1, "oldest": oldest})
                self.assertEqual(doc["outbox"], {"sent": 0, "unsent": 1, "oldest": oldest})
                self.assertEqual(doc["drafts"], {"closed": 1, "open": 0})
                self.assertEqual(doc["approvals"], {"rows": 1, "oldest": oldest})
                self.assertEqual(doc["memory"], {"forgotten": 1, "superseded": 0, "oldest": oldest})
                self.assertNotIn("unavailable", out)

    def test_representable_calendar_endpoints_remain_dated(self):
        for raw, count in ((OK_EDGE_LOW, 1), (OK_EDGE_HIGH, 0)):
            with self.subTest(raw=raw):
                self.conv("DELETE FROM messages")
                self.conv("INSERT INTO messages(provider_id, disposition, received_at) VALUES ('m', 'd', ?)", raw)
                doc = json.loads(self.run_cli()[1])
                self.assertEqual(doc["messages"]["rows"], count)
                self.assertEqual(doc["messages"]["oldest"], datetime.fromisoformat(raw).astimezone(timezone.utc).date().isoformat())
        self.conv("DELETE FROM messages")
        self.conv("INSERT INTO messages(provider_id, disposition, received_at) VALUES ('m', 'd', ?)",
                  "2026-10-03T19:00:00+02:00")  # 17:00 UTC, exactly the cutoff: not strictly older
        self.assertEqual(json.loads(self.run_cli()[1])["messages"], {"rows": 0, "oldest": "2026-10-03"})

    def test_bad_sidecar_date_is_undated(self):
        def original(sha, received):
            folder = self.media / "originals" / sha[:2]
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{sha}.jpg").write_bytes(b"j" * 5)
            (folder / f"{sha}.json").write_text(json.dumps({"received_at": received}))
        original(SHA_OLD, iso(OLD))
        for bad, sha in zip(BAD, (SHA_UNDATED, "12" + "4" * 62)): original(sha, bad)
        (self.media / "web" / "12").mkdir(parents=True)
        (self.media / "web" / "12" / ("12" + "4" * 62 + ".jpg")).write_bytes(b"w")
        code, out, err = self.run_cli("--media", str(self.media))
        self.assertEqual((code, err), (0, ""))
        doc = json.loads(out)
        self.assertEqual(doc["media"], {"originals": 1, "bytes": 5, "web": 0, "oldest": OLD.date().isoformat(), "undated": 2})
        self.assertEqual(doc["webOrphans"], 0)

    def test_bad_now_refused_before_paths_open(self):
        for bad in BAD:
            with self.subTest(bad=bad):
                code, out, err = self.run_cli(state=self.tmp / "missing", now=bad)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("--now must be a timezone-aware ISO-8601 time", err)
                self.assertNotIn("Traceback", err)
        far = "9999-12-31T00:00:00+00:00"  # valid extreme UTC value is still accepted (and then fails on the missing store)
        self.assertEqual(self.run_cli(state=self.tmp / "missing", now=far)[0], 2)
        self.assertNotIn("--now must", self.run_cli(state=self.tmp / "missing", now=far)[2])

    def test_bad_stored_time_cli_is_private_and_read_only(self):
        canary = "text-canary-3"
        self.conv("INSERT INTO messages(provider_id, disposition, received_at) VALUES (?, 'd', ?)", canary, UNDER)
        self.conv("INSERT INTO outbox(chat, text, attachments, created_at) VALUES ('chat-canary-2', ?, '[]', ?)", canary, OVER)
        before = tree(self.tmp)
        code, out, err = self.run_cli()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(out.splitlines()), 1)
        doc = json.loads(out)
        self.assertEqual(doc["messages"], {"rows": 0, "oldest": None})
        self.assertEqual(doc["outbox"], {"sent": 0, "unsent": 0, "oldest": None})
        self.assertEqual(doc["deletes"], 0)
        for c in (canary, "chat-canary-2"): self.assertNotIn(c, out)
        self.assertEqual(tree(self.tmp), before)


if __name__ == "__main__":
    unittest.main()
