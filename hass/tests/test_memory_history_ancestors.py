"""RF1500-25 (H15): `memory.py history` refuses a state path with a linked or non-directory component before any read.
Static admission only (no TOCTOU/descriptor confinement). Run: python3 -B -m unittest hass.tests.test_memory_history_ancestors -v
"""

import contextlib, io, json, os, sqlite3, tempfile, unittest  # noqa: E401
from unittest import mock
from pathlib import Path

from hass import memory
from hass.tests.test_memory import Clock

CANARY = "ancestor-canary-7731"
REASON = "state path is a link or not a directory"


class AncestorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        self.real = self.root / "real"
        mem = memory.Memory(str(self.real / "state"), Clock())  # creates real/state/conversation.sqlite3
        mem.remember("pickup.day", CANARY, "fact", "operator:n")
        mem.close()
        self.state = self.real / "state"
        self.bridge = self.root / "bridge"
        self.bridge.symlink_to(self.real)

    def main(self, state, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = memory.main(["history", "--state", str(state), *args])
        return code, json.loads(out.getvalue()), out.getvalue()

    def assert_refused(self, state):
        """Direct helper and main both refuse; SQLite is never opened and no value is printed."""
        with mock.patch.object(memory.sqlite3, "connect", side_effect=AssertionError("opened")) as connect:
            with self.assertRaises(memory.UnsafeFile) as ctx: memory.history(state, None, True)
            self.assertEqual(str(ctx.exception), REASON)
            code, doc, raw = self.main(state, "--values")
        connect.assert_not_called()
        outer = Path(state).is_dir() and not Path(state).is_symlink()  # else main's existing outer guard answers, no reason
        self.assertEqual((code, doc), (2, {"result": "unsafe", **({"problem": REASON} if outer else {})}))
        self.assertNotIn(CANARY, raw)

    def test_linked_ancestor_refuses_before_sqlite(self):
        self.assert_refused(self.bridge / "state")

    def test_relative_and_absolute_ancestor_links_refuse(self):
        (self.root / "deep").mkdir()
        (self.root / "deep" / "hop").symlink_to(self.bridge)  # link to a link: multiple depth
        (self.root / "dangling").symlink_to(self.root / "gone")
        (self.root / "file").write_text("x", "utf-8")
        for state in (self.bridge / "state", self.root / "deep" / "hop" / "state", self.root / "dangling" / "state",
                      self.root / "file" / "state"):
            with self.subTest(state=state.relative_to(self.root).as_posix()): self.assert_refused(state)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.root)
        with self.subTest(state="relative"): self.assert_refused("bridge/state")
        with self.subTest(state="relative file"): self.assert_refused("file/state")

    def test_link_before_parent_cancellation_is_not_normalized_away(self):
        (self.real / "other").mkdir()
        for state in (f"{self.bridge}/../real/state", f"{self.bridge}/./../real/state", f"{self.bridge}/other/../state"):
            with self.subTest(state=state[len(str(self.root)):]): self.assert_refused(state)

    def test_real_dot_and_parent_paths_preserve_exact_history(self):
        (self.real / "child").mkdir()
        before = (self.state / "conversation.sqlite3").read_bytes()
        baseline = self.main(self.state, "--values")
        self.assertEqual(baseline[0], 0)
        self.assertEqual([r["value"] for r in baseline[1]["rows"]], [CANARY])
        for state in (f"{self.real}/./state", f"{self.real}/child/../state", f"{self.root}/real/./child/.././state"):
            with self.subTest(state=state[len(str(self.root)):]):
                self.assertEqual(self.main(state, "--values"), baseline)
                self.assertEqual(memory.history(state, None, True), baseline[1])
        self.assertEqual((self.state / "conversation.sqlite3").read_bytes(), before)
        self.assertNotIn(CANARY, self.main(self.state)[2])  # no --values: still no value

    def test_missing_database_does_not_override_unsafe_ancestor(self):
        empty = {"result": "ok", "rows": [], "keys": 0, "active": 0, "superseded": 0, "forgotten": 0}
        (self.real / "bare").mkdir()
        self.assertEqual(memory.history(self.real / "bare"), empty)  # real, missing leaf: empty success
        self.assertEqual(self.main(self.real / "bare")[:2], (0, empty))
        self.assert_refused(self.bridge / "bare")  # linked ancestor, missing leaf: unsafe, not empty
        # existing distinctions are unchanged: no table is empty success, a linked or corrupt database is not
        with contextlib.closing(sqlite3.connect(self.real / "bare" / "conversation.sqlite3")) as db, db: db.execute("CREATE TABLE o(x)")
        self.assertEqual(memory.history(self.real / "bare"), empty)
        (self.real / "linkdb").mkdir()
        (self.real / "linkdb" / "conversation.sqlite3").symlink_to(self.state / "conversation.sqlite3")
        with self.assertRaises(memory.UnsafeFile) as ctx: memory.history(self.real / "linkdb", None, True)
        self.assertEqual(str(ctx.exception), "conversation file is a link or not a regular file")
        (self.real / "bad").mkdir()
        (self.real / "bad" / "conversation.sqlite3").write_bytes(b"not a database " * 200)
        self.assertEqual(self.main(self.real / "bad")[:2], (1, {"result": "unreadable"}))

    def test_snapshot_privacy_and_precedence(self):
        db = self.state / "conversation.sqlite3"
        snap = (db.read_bytes(), db.stat().st_mode, db.stat().st_mtime_ns, sorted(os.listdir(self.state)))
        with mock.patch.object(memory, "Memory", side_effect=AssertionError("constructed")), \
                mock.patch.object(memory.os, "chmod", side_effect=AssertionError("chmod")):
            self.assert_refused(self.bridge / "state")
            code, doc, _ = self.main(self.bridge / "state", "--key", "Bad Key")  # invalid key keeps usage precedence
            self.assertEqual((code, doc), (2, {"result": "usage", "problem": "invalid key"}))
            for state in (self.bridge, self.root / "missing", db):  # direct-state refusal stays fixed and neutral
                self.assertEqual(self.main(state, "--values")[:2], (2, {"result": "unsafe"}))
        self.assertEqual((db.read_bytes(), db.stat().st_mode, db.stat().st_mtime_ns, sorted(os.listdir(self.state))), snap)


if __name__ == "__main__": unittest.main()
