"""RF1710-4 (H15): `memory.py history` is a read-only audit of owner memory rows: source kind and dates for every row,
a value only for an active row and only with --values; the source detail and approved_change are never printed.
Run: python3 -B -m unittest hass.tests.test_memory_history -v
"""

import contextlib, io, json, os, sqlite3, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import memory
from hass.content_model import REPO_ROOT
from hass.tests.test_memory import Clock

PROVIDER = "provider-sentinel-6620"  # source detail after ':'
CHANGE = "chg-4417aaaa0000"  # approved_change (RF1650-2: a valid id with an applied record in the test's state dir)
OTHER = "chg-00000000c001"  # another applied change, for tests that only need some owner-approved row


class HistoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.db = self.state / "conversation.sqlite3"

    def store(self):
        mem = memory.Memory(str(self.state), Clock())
        self.addCleanup(mem.close)
        return mem

    def applied(self, change_id):
        """Write an applied change record into this test's state dir, so owner-approved:<change_id> is verified."""
        (self.state / "changes").mkdir(mode=0o700, exist_ok=True)
        (self.state / "changes" / f"{change_id}.json").write_text('{"state": "applied"}', "utf-8")

    def history(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = memory.main(["history", "--state", str(self.state), *args])
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        return code, json.loads(out.getvalue()), out.getvalue()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "memory.py"), "history", *map(str, args)],
                              capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)

    def test_remember_correct_correct_forget_keeps_dated_trail_without_values(self):
        mem = self.store()
        self.applied(CHANGE)
        mem.remember("pickup.day", "Saturday", "fact", f"owner-approved:{CHANGE}", approved_change=CHANGE)
        mem.correct("pickup.day", "Sunday", f"owner-stated:{PROVIDER}")
        mem.correct("pickup.day", "Monday", "operator:fixed typo")
        mem.forget("pickup.day")
        code, doc, raw = self.history("--values")
        self.assertEqual(code, 0)
        rows = doc["rows"]
        self.assertEqual([r["source_kind"] for r in rows], ["owner-approved", "owner-stated", "operator"])
        self.assertTrue(rows[0]["created_at"] < rows[0]["superseded_at"] < rows[1]["created_at"]
                        < rows[1]["superseded_at"] < rows[2]["created_at"] < rows[2]["forgotten_at"])
        self.assertEqual([(r["superseded_at"] is None, r["forgotten_at"] is None) for r in rows],
                         [(False, True), (False, True), (True, False)])
        self.assertFalse(any(r["active"] or "value" in r for r in rows))
        self.assertEqual({k: doc[k] for k in ("result", "keys", "active", "superseded", "forgotten")},
                         {"result": "ok", "keys": 1, "active": 0, "superseded": 2, "forgotten": 1})
        for text in (CHANGE, PROVIDER, "fixed typo", "Saturday", "Sunday", "Monday", "approved_change"):
            self.assertNotIn(text, raw)

    def test_value_only_for_active_row_and_only_with_values(self):
        mem = self.store()
        mem.remember("tone", "short replies", "preference", "operator:onboarding")
        mem.correct("tone", "warm replies", "owner-stated:msg-1")  # the superseded text is still stored
        code, doc, raw = self.history("--values")
        self.assertEqual(code, 0)
        self.assertEqual([("value" in r, r["active"]) for r in doc["rows"]], [(False, False), (True, True)])
        self.assertEqual(doc["rows"][1]["value"], "warm replies")
        self.assertNotIn("short replies", raw)
        self.assertEqual(doc["rows"][1]["kind"], "preference")
        code, doc, raw = self.history()
        self.assertEqual(code, 0)
        self.assertNotIn('"value"', raw)
        self.assertNotIn("warm replies", raw)

    def test_key_filter_unknown_key_and_order(self):
        mem = self.store()
        self.applied(OTHER)
        mem.remember("pickup.day", "Saturday", "fact", f"owner-approved:{OTHER}")
        mem.remember("other.key", "x", "fact", "operator:n")
        mem.correct("pickup.day", "Sunday", "operator:n")
        code, doc, _ = self.history()
        self.assertEqual([r["key"] for r in doc["rows"]], ["pickup.day", "other.key", "pickup.day"])  # created order
        self.assertEqual((doc["keys"], doc["active"]), (2, 2))
        code, doc, _ = self.history("--key", "other.key")
        self.assertEqual((code, [r["key"] for r in doc["rows"]], doc["keys"]), (0, ["other.key"], 1))
        code, doc, _ = self.history("--key", "no.such.key")
        self.assertEqual((code, doc["rows"], doc["keys"]), (0, [], 0))

    def test_invalid_key_is_usage(self):
        self.store()
        for key in ("Bad Key", "", "a/b", "x" * 65):
            with self.subTest(key=key):
                code, doc, _ = self.history("--key", key)
                self.assertEqual((code, doc), (2, {"result": "usage", "problem": "invalid key"}))

    def test_hand_inserted_and_out_of_order_rows(self):
        self.store().remember("tone", "short", "preference", "operator:n")
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            for source in ("weird", "owner-approved", "Owner-Approved:x", f"chat-history:owner-stated:{PROVIDER}"):
                db.execute("INSERT INTO memory(key, value, kind, source, created_at) VALUES ('odd', 'v', 'fact', ?, "
                           "'2000-01-01T00:00:00+00:00')", (source,))
        code, doc, raw = self.history()
        self.assertEqual(code, 0)
        self.assertEqual([(r["key"], r["source_kind"]) for r in doc["rows"]],  # created_at first, then id
                         [("odd", "other")] * 4 + [("tone", "operator")])
        self.assertNotIn(PROVIDER, raw)

    def test_missing_file_or_table_is_empty_and_creates_nothing(self):
        self.state.mkdir(mode=0o700)
        run = self.cli("--state", self.state, "--values")
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        self.assertEqual(json.loads(run.stdout)["rows"], [])
        self.assertEqual(list(self.state.iterdir()), [])
        with contextlib.closing(sqlite3.connect(self.db)) as db, db: db.execute("CREATE TABLE other(x)")
        code, doc, _ = self.history()
        self.assertEqual((code, doc["rows"], doc["keys"]), (0, [], 0))

    def test_corrupt_db_unreadable_and_unsafe_state(self):
        self.state.mkdir(mode=0o700)
        self.db.write_bytes(b"not a database at all " * 200)
        run = self.cli("--state", self.state)
        self.assertEqual((run.returncode, json.loads(run.stdout), run.stderr), (1, {"result": "unreadable"}, ""))
        link = self.state.parent / "link"
        link.symlink_to(self.state)
        for state in (link, self.state.parent / "missing", self.db):
            with self.subTest(state=state.name):
                run = self.cli("--state", state, "--key", "Bad Key")
                self.assertEqual((run.returncode, json.loads(run.stdout), run.stderr), (2, {"result": "unsafe"}, ""))

    def test_history_is_read_only(self):
        mem = self.store()
        self.applied(OTHER)
        mem.remember("pickup.day", "Saturday", "fact", f"owner-approved:{OTHER}")
        mem.forget("pickup.day")
        mem.close()
        os.utime(self.db, ns=(1_000_000_000, 1_000_000_000))
        before = (self.db.read_bytes(), self.db.stat().st_mtime_ns, sorted(os.listdir(self.state)))
        for args in ((), ("--values",), ("--key", "pickup.day")):
            self.assertEqual(self.history(*args)[0], 0)
        self.assertEqual((self.db.read_bytes(), self.db.stat().st_mtime_ns, sorted(os.listdir(self.state))), before)


if __name__ == "__main__":
    unittest.main()
