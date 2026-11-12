"""RF1530-17 tests: hass/retention.py refuses a state/media/backups dir that sits below a symlink, before any read.

The report already refuses a root that IS a link; the same static lstat walk now covers every supplied component, in
spelling order (so bridge/../real is refused at bridge, never resolved to accept it). Real synthetic trees under a temp
dir; SQLite/scandir/sidecar seams are tripwires proving refusal precedes every content read. Static check only: no
claim about concurrent replacement. Run: python3 -B -m unittest hass.tests.test_retention_root_ancestors -v
"""
import contextlib, hashlib, io, json, os, shutil, sqlite3, stat, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import conversation, inbox, retention

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
DAYS, OLD = 30, NOW - timedelta(days=31)
SHA = "ab" + "1" * 62
CANARY = "private-canary-xyz"
ERR = "retention: unsafe: {} must be an existing dir, not a symlink\n"
ROOTS = (("--state", "state dir"), ("--media", "media root"), ("--backups", "backups dir"))


def snapshot(root) -> dict:
    """Every path under root -> (type+mode, sha256 of regular bytes); lstat only, so any change, add or removal shows."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for name in (*dirs, *files):
            path = os.path.join(dirpath, name)
            mode = os.lstat(path).st_mode
            out[path] = (mode, hashlib.sha256(Path(path).read_bytes()).hexdigest() if stat.S_ISREG(mode) else None)
    return out


class RootAncestorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.real = self.tmp / "real"
        self.deep = self.real / "a" / "b"
        self.state, self.media, self.backups = (self.deep / n for n in ("state", "media", "backups"))
        for d in (self.state, self.media, self.backups, self.deep / "x"): d.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(self.state / "inbox.sqlite3")) as db, db:
            db.executescript(inbox.SCHEMA)
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            db.executescript(conversation.SCHEMA)
            db.execute("INSERT INTO messages VALUES (?, 'command', ?)", (CANARY, OLD.isoformat()))
        folder = self.media / "originals" / SHA[:2]
        folder.mkdir(parents=True)
        (folder / f"{SHA}.jpg").write_bytes(b"j" * 9)
        (folder / f"{SHA}.json").write_text(json.dumps({"received_at": OLD.isoformat()}))
        (backup := self.backups / "hass-state-20200101T000000Z").mkdir()
        (backup / retention.MANIFEST).write_text("{}")
        os.symlink(self.real, self.tmp / "bridge")  # bridge/a/b/state is a real leaf below a linked ancestor
        os.symlink(self.deep, self.tmp / "hop")
        os.symlink(self.tmp / "nowhere", self.tmp / "dangling")

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = retention.main(["report", "--now", NOW.isoformat(), "--days", str(DAYS), *args])
        return code, out.getvalue(), err.getvalue()

    def tripwires(self):
        stack = contextlib.ExitStack()
        boom = AssertionError("content read before admission finished")
        guarded = mock.Mock(side_effect=boom)

        class GuardedOS:  # retention's own view of os: everything real except the directory scan
            scandir = guarded
            def __getattr__(self, name): return getattr(os, name)

        self.reads = [stack.enter_context(mock.patch.object(retention.sqlite3, "connect", side_effect=boom)),
                      stack.enter_context(mock.patch.object(retention, "os", GuardedOS())),
                      stack.enter_context(mock.patch.object(retention, "_sidecar_time", side_effect=boom)),
                      stack.enter_context(mock.patch.object(retention, "_rows", side_effect=boom))]
        self.reads[1] = guarded
        self.addCleanup(stack.close)
        self.stack = stack

    def all_args(self, base):
        return {flag: str(base / leaf) for flag, leaf in (("--state", "state"), ("--media", "media"),
                                                         ("--backups", "backups"))}

    def refuse(self, flag, what, spelled, *, others=None):
        """CLI exit 2, stdout empty, the fixed neutral stderr; direct report() raises Unsafe with the same message."""
        args = {**self.all_args(self.deep), **(others or {}), flag: str(spelled)}
        argv = [x for pair in args.items() for x in pair]
        before = snapshot(self.tmp)
        with self.subTest(root=what, spelled=str(spelled).replace(str(self.tmp), "T")):
            self.assertEqual(self.cli(*argv), (2, "", ERR.format(what)))
            keyword = {"--state": "state", "--media": "media", "--backups": "backups"}
            direct = {keyword[f]: p for f, p in args.items()}
            with self.assertRaises(retention.Unsafe) as ctx:
                retention.report(days=DAYS, now=NOW, **direct)
            self.assertEqual(str(ctx.exception), ERR.format(what)[len("retention: unsafe: "):-1])
            self.assertEqual(snapshot(self.tmp), before)

    def test_each_root_rejects_linked_ancestor_before_reads(self):
        self.tripwires()
        for flag, what in ROOTS:
            leaf = flag[2:]
            for spelled in (self.tmp / "bridge" / "a" / "b" / leaf,  # several levels below the link
                            self.tmp / "hop" / leaf,  # one level below a link to the parent
                            self.tmp / "bridge" / "a" / "b" / leaf / "."):  # trailing dot is harmless, not an escape
                self.refuse(flag, what, spelled)
        for read in self.reads: read.assert_not_called()

    def test_link_before_parent_cancellation_is_rejected(self):
        self.tripwires()
        for flag, what in ROOTS:
            leaf = flag[2:]
            self.refuse(flag, what, self.tmp / "bridge" / ".." / "real" / "a" / "b" / leaf)  # safe once normalized
            self.refuse(flag, what, self.tmp / "hop" / ".." / "b" / leaf)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.tmp)
        for flag, what in ROOTS:
            leaf = flag[2:]
            self.refuse(flag, what, Path("bridge") / ".." / "real" / "a" / "b" / leaf)
            self.refuse(flag, what, Path("bridge") / "a" / "b" / leaf)  # relative, linked ancestor
        for read in self.reads: read.assert_not_called()

    def test_real_dot_parent_and_relative_roots_keep_exact_report(self):
        direct = self.cli(*(x for pair in self.all_args(self.deep).items() for x in pair))
        self.assertEqual(direct[0], 0, direct)
        doc = json.loads(direct[1])
        self.assertEqual((doc["messages"]["rows"], doc["media"]["originals"], doc["backups"]["complete"]), (1, 1, 1))
        self.assertEqual(doc["media"]["bytes"], 9)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.tmp)
        spellings = (lambda leaf: str(self.deep / "." / leaf),
                     lambda leaf: str(self.deep / "x" / ".." / leaf),
                     lambda leaf: f"real/a/b/{leaf}", lambda leaf: f"real/a/../a/b/{leaf}",
                     lambda leaf: f"./real/a/b/{leaf}", lambda leaf: f"real/a/b/{leaf}/")
        for spell in spellings:
            argv = [x for flag, leaf in (("--state", "state"), ("--media", "media"), ("--backups", "backups"))
                    for x in (flag, spell(leaf))]
            self.assertEqual(self.cli(*argv), direct, argv)
        only_state = self.cli("--state", "real/a/b/state")  # omitted optional roots stay null
        self.assertEqual((only_state[0], json.loads(only_state[1])["media"], json.loads(only_state[1])["backups"]),
                         (0, None, None))

    def test_direct_dangling_and_non_directory_components_are_unsafe(self):
        self.tripwires()
        (self.tmp / "file").write_text(CANARY)
        for flag, what in ROOTS:
            leaf = flag[2:]
            for spelled in (self.tmp / "bridge",  # the direct link keeps being refused
                            self.tmp / "dangling", self.tmp / "dangling" / leaf,
                            self.tmp / "file", self.tmp / "file" / leaf,  # file in the middle
                            self.deep / "missing" / leaf, self.deep / "missing",
                            self.deep / leaf / "originals" / "nope"):
                self.refuse(flag, what, spelled)
        for read in self.reads: read.assert_not_called()
        code, out, err = self.cli("--state", str(self.tmp / "file" / "state"))
        for text in (str(self.tmp), CANARY, "nowhere", "bridge"): self.assertNotIn(text, out + err)

    def test_unsafe_optional_precedes_all_database_opens(self):
        empty = self.tmp / "emptystate"  # a safe state dir whose databases are missing
        empty.mkdir()
        self.tripwires()
        before = snapshot(self.tmp)
        for flag, what in ROOTS[1:]:
            argv = ["--state", str(empty), flag, str(self.tmp / "bridge" / "a" / "b" / flag[2:])]
            self.assertEqual(self.cli(*argv), (2, "", ERR.format(what)))
        for read in self.reads: read.assert_not_called()
        self.assertEqual(snapshot(self.tmp), before)
        self.stack.close()  # tripwires off: safe roots with missing databases
        code, out, _ = self.cli("--state", str(empty), "--media", str(self.media), "--backups", str(self.backups))
        doc = json.loads(out)  # safe roots with missing databases keep the ordinary unavailable outcome
        self.assertEqual((code, doc["inbox"], doc["messages"]), (1, "unavailable", "unavailable"))
        self.assertEqual(doc["media"]["originals"], 1)
        self.assertEqual(snapshot(self.tmp), before)  # mode=ro created no store

    def test_no_writes_and_existing_leaf_guards_survive(self):
        before = snapshot(self.tmp)
        self.assertEqual(self.cli("--state", str(self.state))[0], 0)
        self.assertEqual(snapshot(self.tmp), before)
        # cutoff usage error keeps precedence over a linked root
        code, out, err = self.cli("--state", str(self.tmp / "bridge" / "a" / "b" / "state"), "--now", "0001-01-02T00:00:00+00:00",
                                  "--days", "36500")
        self.assertEqual((code, out, "--days reaches" in err), (2, "", True), err)
        # database leaf guards run after the roots and keep their own diagnostic
        db = self.state / "inbox.sqlite3"
        db.rename(self.tmp / "aside.sqlite3")
        os.symlink(self.tmp / "aside.sqlite3", db)
        self.tripwires()
        self.assertEqual(self.cli("--state", str(self.state)),
                         (2, "", "retention: unsafe: inbox.sqlite3 must be a regular file, not a symlink\n"))
        db.unlink()
        db.mkdir()
        self.assertEqual(self.cli("--state", str(self.state))[0], 2)
        for read in self.reads: read.assert_not_called()
        db.rmdir()
        (self.tmp / "aside.sqlite3").rename(db)
        self.assertEqual(snapshot(self.tmp), before)


if __name__ == "__main__":
    unittest.main()
