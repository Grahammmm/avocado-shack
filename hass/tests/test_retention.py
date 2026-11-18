"""H21 tests: hass/retention.py read-only retention report (counts older than --days N; deletes nothing).

Temp state, media and backup dirs built from the real schemas with placeholder canary rows and an injected clock.
Never the real private state. Run: python3 -B -m unittest hass.tests.test_retention -v
"""
import contextlib, hashlib, io, json, os, shutil, sqlite3, subprocess, sys, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import conversation, inbox, retention

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
DAYS, CANARIES = 30, ("pid-canary-1", "chat-canary-2", "text-canary-3", "change-canary-4", "sender-canary-5")
OLD, AT, NEW = NOW - timedelta(days=31), NOW - timedelta(days=DAYS), NOW - timedelta(days=1)
SHA_OLD, SHA_NEW, SHA_UNDATED = "ab" + "1" * 62, "cd" + "2" * 62, "ef" + "3" * 62


def iso(dt):
    return dt.isoformat(timespec="microseconds")


def tree(*roots) -> dict:
    """Every path under roots -> sha256 of its bytes (None for a dir), so any new, changed or gone entry shows."""
    out = {}
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            out.update({os.path.join(dirpath, d): None for d in dirs})
            out.update({os.path.join(dirpath, f): hashlib.sha256(Path(dirpath, f).read_bytes()).hexdigest()
                        for f in files})
    return out


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.media, self.backups = self.tmp / "state", self.tmp / "media", self.tmp / "backups"
        for d in (self.state, self.media, self.backups): d.mkdir(mode=0o700)
        with contextlib.closing(sqlite3.connect(self.state / "inbox.sqlite3")) as db, db:
            db.executescript(inbox.SCHEMA)
            for n, (state, when) in enumerate((("done", OLD), ("history", OLD), ("done", AT), ("pending", NEW))):
                db.execute("INSERT INTO inbound VALUES (?, ?, ?, ?, NULL, ?, NULL)",
                           (f"{CANARIES[0]}-{n}", iso(when), CANARIES[2], state, iso(when)))
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            db.executescript(conversation.SCHEMA)
            for n, when in enumerate((iso(OLD), iso(AT), iso(NEW), None, "2026-01-01T00:00:00")):
                db.execute("INSERT INTO messages VALUES (?, 'command', ?)", (f"{CANARIES[0]}-m{n}", when))
            for when, sent in ((OLD, iso(OLD)), (OLD, None), (AT, None), (NEW, None)):
                db.execute("INSERT INTO outbox(chat, text, attachments, created_at, sent_at) VALUES (?, ?, '[]', ?, ?)",
                           (CANARIES[1], CANARIES[2], iso(when), sent))
            for state, when in (("rejected", OLD), ("reverted", OLD), ("proposed", OLD), ("verified", NEW)):
                db.execute("INSERT INTO drafts(change_id, code, state, ops_json, summary, sender, chat, created_at) "
                           "VALUES (?, 'c', ?, '[]', ?, ?, ?, ?)",
                           (CANARIES[3], state, CANARIES[2], CANARIES[4], CANARIES[1], iso(when)))
        (shots := self.state / "screenshots").mkdir()
        for name, when, size in ((f"{CANARIES[3]}-proposal.png", OLD, 7), (f"{CANARIES[3]}-result.png", NEW, 5)):
            (shots / name).write_bytes(b"x" * size)
            os.utime(shots / name, (when.timestamp(), when.timestamp()))

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = retention.main(["report", "--now", iso(NOW), *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def report(self, *extra):
        code, out, _ = self.run_main("--state", str(self.state), "--days", str(DAYS), *extra)
        return code, json.loads(out), out

    def original(self, sha, meta, size):
        folder = self.media / "originals" / sha[:2]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{sha}.jpg").write_bytes(b"j" * size)
        (folder / f"{sha}.json").write_text(json.dumps(meta))

    def test_counts_both_sides_of_cutoff_and_no_ids_or_text(self):
        code, doc, out = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(doc["cutoff"], AT.isoformat())
        self.assertEqual(doc["inbox"], {"done": 1, "history": 1, "pending": 0, "oldest": OLD.date().isoformat()})
        self.assertEqual(doc["messages"], {"rows": 1, "oldest": OLD.date().isoformat()})  # null/zone-less not counted
        self.assertEqual(doc["outbox"], {"sent": 1, "unsent": 1, "oldest": OLD.date().isoformat()})
        self.assertEqual(doc["drafts"], {"closed": 2, "open": 1})
        self.assertEqual(doc["screenshots"], {"files": 1, "bytes": 7})
        self.assertEqual((doc["media"], doc["backups"], doc["deletes"], doc["days"]), (None, None, 0, DAYS))
        for canary in (*CANARIES, ".png", str(self.tmp)): self.assertNotIn(canary, out)

    def test_cli_script_runs_from_its_path(self):
        script = str(Path(retention.__file__))
        proc = subprocess.run([sys.executable, "-B", script, "report", "--state", str(self.state), "--days", str(DAYS),
                               "--now", iso(NOW)], capture_output=True, text=True, timeout=60)
        self.assertEqual((proc.returncode, json.loads(proc.stdout)["inbox"]["done"]), (0, 1), proc.stderr)

    def test_days_must_be_a_whole_number_of_at_least_one(self):
        for args in (["--days", "0"], ["--days", "-1"], ["--days", "x"], ["--days", "1.5"], []):
            code, out, err = self.run_main("--state", str(self.state), *args)
            self.assertEqual((code, out), (2, ""), args)
        code, _, _ = self.run_main("--state", str(self.state), "--days", "1", "--now", "2026-11-02T17:00:00")
        self.assertEqual(code, 2)  # a zone-less --now is refused too (the last --now wins)

    def test_missing_inbox_or_corrupt_conversation_is_unavailable_exit_1(self):
        (self.state / "inbox.sqlite3").rename(self.tmp / "inbox.aside")
        code, doc, _ = self.report()
        self.assertEqual((code, doc["inbox"], doc["outbox"]["unsent"]), (1, "unavailable", 1))
        self.assertFalse((self.state / "inbox.sqlite3").exists())  # mode=ro never creates the missing store
        (self.tmp / "inbox.aside").rename(self.state / "inbox.sqlite3")
        (self.state / "conversation.sqlite3").write_bytes(b"not a database at all, just junk bytes" * 40)
        code, doc, _ = self.report()
        self.assertEqual(code, 1)
        self.assertEqual([doc[k] for k in ("messages", "outbox", "drafts")], ["unavailable"] * 3)
        self.assertEqual((doc["inbox"]["done"], doc["screenshots"]["files"], doc["deletes"]), (1, 1, 0))

    def test_unsafe_paths_exit_2_and_create_nothing(self):
        (self.tmp / "link").symlink_to(self.state)
        (self.tmp / "dblink").mkdir()
        (self.tmp / "dblink" / "conversation.sqlite3").symlink_to(self.state / "conversation.sqlite3")
        (self.tmp / "medialink").symlink_to(self.media)
        cases = (["--state", str(self.tmp / "link")], ["--state", str(self.tmp / "missing")],
                 ["--state", str(self.tmp / "dblink")],
                 ["--state", str(self.state), "--media", str(self.tmp / "medialink")],
                 ["--state", str(self.state), "--backups", str(self.tmp / "missing")])
        before = tree(self.tmp)
        for args in cases:
            code, out, err = self.run_main(*args, "--days", "1")
            self.assertEqual((code, out), (2, ""), args)
            self.assertIn("unsafe", err)
        self.assertEqual(tree(self.tmp), before)
        self.assertFalse((self.tmp / "missing").exists())

    def test_media_originals_web_copies_and_undated_sidecar(self):
        self.original(SHA_OLD, {"received_at": iso(OLD)}, 11)
        self.original(SHA_NEW, {"received_at": iso(NEW)}, 13)
        self.original(SHA_UNDATED, {"kind": "jpeg"}, 17)  # no received_at: never guessed from mtime
        (web := self.media / "web" / SHA_OLD[:2]).mkdir(parents=True)
        (web / f"{SHA_OLD}.jpg").write_bytes(b"w")
        (self.media / "originals" / SHA_OLD[:2] / ".leftover.tmp").write_bytes(b"t")  # not an original
        code, doc, out = self.report("--media", str(self.media))
        self.assertEqual(code, 0)
        self.assertEqual(doc["media"], {"originals": 1, "bytes": 11, "web": 1, "oldest": OLD.date().isoformat(),
                                        "undated": 1})
        self.assertNotIn(SHA_OLD[:16], out)

    def test_backups_complete_incomplete_and_foreign_names(self):
        stamp = "hass-state-%Y%m%dT%H%M%SZ"
        for when, manifest in ((OLD, True), (OLD + timedelta(hours=1), False), (NEW, True)):
            (folder := self.backups / when.strftime(stamp)).mkdir()
            if manifest: (folder / "MANIFEST.json").write_text("{}")
        for foreign in ("hass-state-latest", "notes", "hass-state-20200101T000000Z.tmp",
                        "hass-state-20261301T000000Z", "hass-state-20260230T000000Z"):  # stamp-shaped, no such date
            (self.backups / foreign).mkdir()
        code, doc, _ = self.report("--backups", str(self.backups))
        self.assertEqual(code, 0)
        self.assertEqual(doc["backups"], {"complete": 1, "incomplete": 1, "oldest": OLD.date().isoformat()})

    def test_full_run_writes_nothing(self):
        self.original(SHA_OLD, {"received_at": iso(OLD)}, 3)
        (self.backups / OLD.strftime("hass-state-%Y%m%dT%H%M%SZ")).mkdir()
        before = tree(self.tmp)
        code, doc, _ = self.report("--media", str(self.media), "--backups", str(self.backups))
        self.assertEqual((code, doc["deletes"]), (0, 0))
        self.assertEqual(tree(self.tmp), before)  # no -wal, -shm or -journal either

    def test_module_has_no_delete_or_write_calls(self):
        source = Path(retention.__file__).read_text(encoding="utf-8")
        for name in ("unlink", "rmtree", "os.remove", "rmdir", "write_", "rename", "os.replace", "truncate"):
            self.assertFalse(name in source, name)
        # the only open is the read-only sidecar os.open (RF1920-2); no write, create, truncate or append flag anywhere
        self.assertEqual(source.count("open("), source.count("os.open(path, os.O_RDONLY | "), "an open() other than os.open")
        self.assertEqual(source.count("open("), 1)
        for flag in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND"): self.assertNotIn(flag, source)
        self.assertIn("?mode=ro", source)


if __name__ == "__main__":
    unittest.main()
