"""RF1920-8 (H15): `memory.py history` prints only text cells. A key, kind, date or (with --values) value that a damaged
conversation.sqlite3 holds as a BLOB or number reads "unreadable": one JSON report, exit 0, never a TypeError traceback.
Run: python3 -B -m unittest hass.tests.test_memory_history_cells -v
"""

import contextlib, io, json, sqlite3, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import memory
from hass.content_model import REPO_ROOT
from hass.tests.test_memory import Clock

U = "unreadable"
DAY = "2026-11-03T17:0{}:00+00:00"


class HistoryCellTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.db = self.state / "conversation.sqlite3"
        mem = memory.Memory(str(self.state), Clock())
        mem.remember("tone", "short", "preference", "operator:n")  # 17:01, superseded 17:03
        mem.remember("k", "Saturday", "fact", "owner-stated:p")  # 17:02, active
        mem.correct("tone", "warm", "operator:n")  # 17:04, active
        mem.close()

    def damage(self, *updates):
        """Copy the rows into an untyped table (as a damaged restore may leave it), so a number stays a number."""
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.execute("ALTER TABLE memory RENAME TO memory_old")
            db.execute("CREATE TABLE memory(id INTEGER PRIMARY KEY, key, value, kind, source, approved_change, "
                       "created_at, superseded_at, forgotten_at)")
            db.execute("INSERT INTO memory SELECT * FROM memory_old")
            for sql in updates: db.execute(sql)

    def history(self, *args):
        before, out = self.db.read_bytes(), io.StringIO()
        with contextlib.redirect_stdout(out): code = memory.main(["history", "--state", str(self.state), *args])
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertEqual(self.db.read_bytes(), before)  # read-only
        return code, json.loads(out.getvalue()), out.getvalue()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "memory.py"), "history", "--state",
                               str(self.state), *args], capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)

    def test_blob_or_number_key_and_kind_read_unreadable(self):
        self.damage("UPDATE memory SET key = X'6b' WHERE key = 'k'", "UPDATE memory SET kind = 1.5 WHERE id = 1",
                    "INSERT INTO memory(key, value, kind, source, created_at) VALUES (7, 'v', NULL, 'operator:n', "
                    "'2026-11-03T17:05:00+00:00')")
        run = self.cli()
        self.assertEqual((run.returncode, run.stderr), (0, ""))  # was: TypeError traceback, exit 1
        doc = json.loads(run.stdout)
        self.assertEqual([(r["key"], r["kind"]) for r in doc["rows"]],
                         [("tone", U), (U, "fact"), ("tone", "preference"), (U, U)])
        self.assertEqual({k: doc[k] for k in ("result", "keys", "active", "superseded", "forgotten")},
                         {"result": "ok", "keys": 2, "active": 3, "superseded": 1, "forgotten": 0})
        self.assertEqual(self.history()[:2], (0, doc))

    def test_number_and_blob_dates_read_unreadable_and_still_count(self):
        self.damage("UPDATE memory SET created_at = 17, superseded_at = X'00' WHERE key = 'k'",
                    "UPDATE memory SET forgotten_at = 3.5 WHERE id = 3")
        code, doc, raw = self.history()
        self.assertEqual(code, 0)
        self.assertEqual([r["key"] for r in doc["rows"]], ["k", "tone", "tone"])  # SQLite sorts a number first
        self.assertEqual([[r[f] for f in memory.AUDIT[2:]] for r in doc["rows"]],
                         [[U, U, None], [DAY.format(1), DAY.format(3), None], [DAY.format(4), None, U]])
        self.assertEqual({k: doc[k] for k in ("keys", "active", "superseded", "forgotten")},
                         {"keys": 2, "active": 0, "superseded": 2, "forgotten": 1})  # an unreadable date counts as set

    def test_values_blob_or_number_value_and_inactive_row_never_shows_a_value(self):
        self.damage("UPDATE memory SET value = X'deadbeef' WHERE key = 'k'",
                    "UPDATE memory SET value = 42 WHERE id = 3", "UPDATE memory SET value = X'00' WHERE id = 1")
        code, doc, raw = self.history("--values")
        self.assertEqual(code, 0)
        self.assertEqual([(r["key"], r["active"], r.get("value", "-")) for r in doc["rows"]],
                         [("tone", False, "-"), ("k", True, U), ("tone", True, U)])
        code, doc, raw = self.history()
        self.assertEqual((code, '"value"' in raw), (0, False))

    def test_key_filter_ignores_a_bad_row_of_another_key(self):
        _, _, clean = self.history("--key", "tone", "--values")
        self.damage("UPDATE memory SET key = X'6b', value = X'00', created_at = 9 WHERE key = 'k'")
        code, doc, raw = self.history("--key", "tone", "--values")
        self.assertEqual((code, raw), (0, clean))
        self.assertEqual([r["value"] for r in doc["rows"] if r["active"]], ["warm"])

    def test_normal_db_output_is_unchanged(self):
        def row(key, kind, created, superseded, src, active, value=None):
            sup = "null" if superseded is None else f'"{DAY.format(superseded)}"'
            val = "" if value is None else f', "value": "{value}"'
            return (f'{{"key": "{key}", "kind": "{kind}", "created_at": "{DAY.format(created)}", "superseded_at": '
                    f'{sup}, "forgotten_at": null, "source_kind": "{src}", "active": {active}{val}}}')
        tail = ', "keys": 2, "active": 2, "superseded": 1, "forgotten": 0}\n'
        for args, vals in (((), (None, None)), (("--values",), ("Saturday", "warm"))):
            with self.subTest(args=args):
                want = ('{"result": "ok", "rows": [' + ", ".join((
                    row("tone", "preference", 1, 3, "operator", "false"),
                    row("k", "fact", 2, None, "owner-stated", "true", vals[0]),
                    row("tone", "preference", 4, None, "operator", "true", vals[1]))) + "]" + tail)
                self.assertEqual(self.history(*args)[:3:2], (0, want))


if __name__ == "__main__":
    unittest.main()
