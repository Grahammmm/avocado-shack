"""Contract tests against disposable SQLite fixtures, never live state."""

from contextlib import closing
import importlib.util
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/retention_uncounted_tables.py"
PASS = "PASS retention_uncounted_tables"
FAIL = "FAIL retention_uncounted_tables"
CANARIES = (
    "synthetic-message-text", "synthetic-chat-value", "synthetic-sender-value",
    "synthetic-full-provider-id", "abcd" * 16,
)


class RetentionUncountedTablesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = Path(temp.name).resolve() / "fixture #?%"
        self.state.mkdir()

    def store(self, name, sql):
        with closing(sqlite3.connect(self.state / f"{name}.sqlite3")) as db:
            db.executescript(sql)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              cwd=self.state, capture_output=True, text=True, timeout=10)

    def report(self):
        return self.cli("--state", str(self.state))

    def assert_report(self, result, code, *lines):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stdout, "\n".join((*lines, FAIL if code else PASS)) + "\n")
        self.assertEqual(result.stderr, "")

    def test_c1_full_pass(self):
        # A fixed extras list, a global exclusion set, bad quoting, or counting
        # non-tables (including sqlite_sequence) all break this inventory.
        self.store("conversation", '''
            CREATE TABLE usage (id INTEGER PRIMARY KEY AUTOINCREMENT);
            INSERT INTO usage DEFAULT VALUES;
            INSERT INTO usage DEFAULT VALUES;
            CREATE TABLE "odd""name" (nullable TEXT);
            INSERT INTO "odd""name" VALUES (NULL);
            CREATE TABLE inbound (x);
            CREATE TABLE messages (x);
            CREATE TABLE outbox (x);
            CREATE TABLE drafts (x);
            CREATE TABLE approvals (x);
            CREATE TABLE memory (x);
            CREATE VIEW not_a_table AS SELECT * FROM usage;
            CREATE INDEX usage_index ON usage (id);
        ''')
        self.store("inbox", "CREATE TABLE nonces (x); CREATE TABLE inbound (x); CREATE TABLE outbox (x);")
        self.assert_report(self.report(), 0, 'table conversation.inbound rows 0',
                           'table conversation.odd"name rows 1', 'table conversation.usage rows 2',
                           'table inbox.nonces rows 0', 'table inbox.outbox rows 0')

    def test_c2_findings(self):
        # A fail-fast or unordered loop loses the other store's finding.
        (self.state / "inbox.sqlite3").mkdir()
        self.assert_report(self.report(), 1, "FAIL missing-db conversation.sqlite3", "FAIL unsafe-db inbox.sqlite3")

    def test_c2_1_missing_db(self):
        # A missing store must not be interpreted as an empty database.
        self.store("conversation", "CREATE TABLE usage (x);")
        self.assert_report(self.report(), 1, "table conversation.usage rows 0", "FAIL missing-db inbox.sqlite3")
        self.assertFalse((self.state / "inbox.sqlite3").exists())

    def test_c2_2_unsafe_db(self):
        # stat()/exists() would accept a working symlink or misclassify a dangling one.
        self.store("inbox", "CREATE TABLE inbound (x);")
        self.store("decoy", "CREATE TABLE nonces (x);")
        for kind in ("symlink", "dangling", "directory"):
            with self.subTest(kind=kind):
                case = self.state / kind
                case.mkdir()
                inbox = case / "inbox.sqlite3"
                inbox.write_bytes((self.state / "inbox.sqlite3").read_bytes())
                candidate = case / "conversation.sqlite3"
                if kind == "directory":
                    candidate.mkdir()
                else:
                    candidate.symlink_to(self.state / ("decoy.sqlite3" if kind == "symlink" else "absent"))
                self.assert_report(self.cli("--state", str(case)), 1, "FAIL unsafe-db conversation.sqlite3")

    def test_c2_3_not_sqlite(self):
        # connect() can succeed until the first schema read, so test through the CLI.
        (self.state / "conversation.sqlite3").write_bytes(b"synthetic non-database")
        self.store("inbox", "CREATE TABLE meta (x);")
        self.assert_report(self.report(), 1, "FAIL not-sqlite conversation.sqlite3", "table inbox.meta rows 0")

        # A readable schema does not guarantee all discovered tables are countable.
        (self.state / "conversation.sqlite3").write_bytes(b"")
        self.store("conversation", """
            PRAGMA writable_schema=ON;
            INSERT INTO sqlite_master VALUES ('table', 'usage', 'usage', 0,
                'CREATE VIRTUAL TABLE usage USING synthetic_missing_module');
        """)
        self.assert_report(self.report(), 1, "FAIL not-sqlite conversation.sqlite3", "table inbox.meta rows 0")

    def test_c3_usage_exit_2(self):
        # Usage failures must not enter the store inspection or emit a tool footer.
        for args in ((), ("--state",), ("--state", str(self.state), "--unknown")):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A plain mode=ro read can create WAL sidecars. Directory mtime
        # catches them even if they disappear on close.
        self.store("conversation", "PRAGMA journal_mode=WAL; CREATE TABLE usage (x); INSERT INTO usage VALUES (NULL);")
        self.store("inbox", "CREATE TABLE meta (x);")

        def snapshot():
            return (self.state.stat().st_mtime_ns,
                    {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode) for p in self.state.iterdir()})

        before = snapshot()
        self.assert_report(self.report(), 0, "table conversation.usage rows 1", "table inbox.meta rows 0")
        self.assertEqual(snapshot(), before)

        # A stable copy with committed WAL frames must not return stale counts.
        source = self.state.parent / "wal-source.sqlite3"
        with closing(sqlite3.connect(source)) as db:
            db.executescript("PRAGMA journal_mode=WAL; CREATE TABLE usage (x);"
                             "PRAGMA wal_checkpoint(TRUNCATE); INSERT INTO usage VALUES (NULL);")
            for suffix in ("", "-wal"):
                (self.state / f"conversation.sqlite3{suffix}").write_bytes(Path(str(source) + suffix).read_bytes())
        before = snapshot()
        self.assert_report(self.report(), 1, "FAIL not-sqlite conversation.sqlite3", "table inbox.meta rows 0")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Catch row dumps, SQLite diagnostics and argument errors echoing paths.
        with closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db:
            db.execute("CREATE TABLE message_chats (text, chat, sender, provider_id, digest)")
            db.execute("INSERT INTO message_chats VALUES (?, ?, ?, ?, ?)", CANARIES)
            db.commit()
        self.store("inbox", "CREATE TABLE inbound (x);")
        success = self.report()
        self.assert_report(success, 0, "table conversation.message_chats rows 1")
        (self.state / "inbox.sqlite3").write_bytes(CANARIES[0].encode())
        failure = self.report()
        self.assert_report(failure, 1, "table conversation.message_chats rows 1", "FAIL not-sqlite inbox.sqlite3")
        usage = self.cli("--state", str(self.state), str(self.state))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (success, failure, usage):
            for canary in (*CANARIES, str(self.state.parent), str(self.state)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_counted_set_matches_retention(self):
        # The independent SQL text catches additions and removals in the real report.
        spec = importlib.util.spec_from_file_location("retention_uncounted_tables", SCRIPT)
        assert spec is not None and spec.loader is not None
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        source = (ROOT / "hass/retention.py").read_text(encoding="utf-8")
        from_names = set(re.findall(r"\bFROM ([a-z_][a-z_0-9]*)\b", source)) - {"sqlite_master"}
        self.assertEqual(set().union(*tool.COUNTED.values()), from_names)
        self.store("conversation", "CREATE TABLE messages (x);")
        self.store("inbox", "CREATE TABLE inbound (x);")
        self.assert_report(self.report(), 0)
