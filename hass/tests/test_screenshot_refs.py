"""Fixture-only checks of the screenshot reference CLI contract."""

from contextlib import closing, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/screenshot_refs.py"
DB_NAME = "conversation.sqlite3"
PASS = "PASS screenshot_refs"
FAIL = "FAIL screenshot_refs"
# Leave screenshot affinity unspecified so malformed non-string values survive.
SCHEMA = "CREATE TABLE drafts(change_id TEXT, screenshot, summary, chat, sender, draft_hash, code)"


class ScreenshotRefsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "synthetic state #%?"
        self.state.mkdir()
        self.db = self.state / DB_NAME
        self.screenshots = self.state / "screenshots"

    def make_db(self, rows=(), *, path=None, schema=SCHEMA):
        with closing(sqlite3.connect(path or self.db)) as db, db:
            db.execute(schema)
            if rows:
                db.executemany("INSERT INTO drafts(change_id, screenshot) VALUES (?, ?)", rows)

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def run_state(self):
        return self.invoke("--state", str(self.state))

    def assert_status(self, result, code, final):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1:], [final])
        self.assertEqual(result.stderr, "")

    def assert_findings(self, result, *findings):
        self.assert_status(result, 1, FAIL)
        self.assertEqual(
            [line for line in result.stdout.splitlines() if line.startswith("FAIL ")],
            [*(f"FAIL {reason}" for reason in findings), FAIL],
        )

    def test_c1_full_pass(self):
        # Whole-path matching, counting distinct refs, and conflating orphan types
        # would all miscount this valid report; bad refs are notes, not failures.
        self.make_db([
            ("draft-a", "/synthetic/elsewhere/draft-a-proposal.png"),
            ("draft-b", "draft-a-proposal.png"),
            ("draft-c", None), ("draft-d", ""), ("draft-e", 42),
            ("draft-f", b"synthetic-blob"),
        ])
        self.screenshots.mkdir()
        for name in ("draft-a-proposal.png", "draft-c-proposal.png", "orphan-proposal.png", "loose.png"):
            (self.screenshots / name).touch()
        (self.screenshots / "not-a-file.png").mkdir()
        result = self.run_state()
        self.assert_status(result, 0, PASS)
        self.assertEqual(result.stdout.splitlines(), [
            "drafts 6", "refs 2", "files 4", "note bad-ref 3",
            "note proposal-orphans 1", "note other-unreferenced 2", PASS,
        ])

    def test_c2_1_missing_db(self):
        # A normal SQLite connect would create the missing file; keep both findings
        # in check order when neither input is present.
        self.screenshots.mkdir()
        self.assert_findings(self.run_state(), f"missing-db {DB_NAME}")
        self.assertFalse(self.db.exists())
        self.screenshots.rmdir()
        self.assert_findings(self.run_state(), f"missing-db {DB_NAME}", "no-screenshots-dir")

    def test_c2_2_unsafe_db(self):
        # Reject a symlink to a valid store before SQLite sees it, and a directory
        # at the store path without misreporting it as unreadable SQLite.
        self.screenshots.mkdir()
        decoy = self.root / "decoy.sqlite3"
        self.make_db(path=decoy)
        self.db.symlink_to(decoy)
        spec = importlib.util.spec_from_file_location("screenshot_refs", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout = io.StringIO()
        with patch.object(module.sqlite3, "connect", side_effect=AssertionError("unsafe open")):
            with redirect_stdout(stdout):
                self.assertEqual(module.main(["--state", str(self.state)]), 1)
        self.assertEqual(stdout.getvalue().splitlines()[-2:], [f"FAIL unsafe-db {DB_NAME}", FAIL])
        self.assert_findings(self.run_state(), f"unsafe-db {DB_NAME}")
        self.db.unlink()
        self.db.mkdir()
        self.assert_findings(self.run_state(), f"unsafe-db {DB_NAME}")

    def test_c2_3_not_sqlite(self):
        # Opening a non-DB file can appear to succeed; opening a valid DB without
        # the required schema really does. Neither may be mistaken for zero rows.
        self.screenshots.mkdir()
        self.db.write_bytes(b"not a SQLite store")
        self.assert_findings(self.run_state(), f"not-sqlite {DB_NAME}")
        for schema in (
            "CREATE TABLE unrelated(change_id, screenshot)",
            "CREATE TABLE drafts(change_id)",
            "CREATE TABLE drafts(screenshot)",
        ):
            with self.subTest(schema=schema):
                self.db.unlink()
                self.make_db(schema=schema)
                self.assert_findings(self.run_state(), f"not-sqlite {DB_NAME}")

    def test_c2_4_no_screenshots_dir(self):
        # Missing, symlinked, and non-directory entries are not empty inventories.
        self.make_db()
        self.assert_findings(self.run_state(), "no-screenshots-dir")
        decoy = self.root / "decoy-dir"
        decoy.mkdir()
        self.screenshots.symlink_to(decoy, target_is_directory=True)
        self.assert_findings(self.run_state(), "no-screenshots-dir")
        self.screenshots.unlink()
        self.screenshots.touch()
        self.assert_findings(self.run_state(), "no-screenshots-dir")

    def test_c2_5_dangling_screenshot(self):
        # Count rows, not distinct missing names. An existing external path, a
        # directory and a symlink in the inventory do not provide a local file.
        self.screenshots.mkdir()
        outside = self.root / "missing.png"
        outside.touch()
        (self.screenshots / "folder.png").mkdir()
        (self.screenshots / "alias.png").symlink_to(outside)
        (self.screenshots / "found.png").touch()
        self.make_db([
            ("draft-a", "missing.png"), ("draft-b", str(outside)),
            ("draft-c", "folder.png"), ("draft-d", "alias.png"),
            ("draft-e", "found.png"), ("draft-f", None),
        ])
        result = self.run_state()
        self.assert_findings(result, "dangling-screenshot 4")
        self.assertIn("refs 5", result.stdout.splitlines())
        self.assertIn("files 1", result.stdout.splitlines())

    def test_c3_usage_exit_2(self):
        # Usage failures must not be routed through the audit finding/exit path.
        for args in ((), ("--state",), ("--state", str(self.state), "--unknown")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # no last stdout line for C3
                self.assertTrue(result.stderr.startswith("usage: "))

    def snapshot(self):
        snapshot = {}
        for path in (self.root, *self.root.rglob("*")):
            metadata = path.lstat()
            contents = path.read_bytes() if stat.S_ISREG(metadata.st_mode) else None
            snapshot[path.relative_to(self.root)] = (contents, metadata.st_mtime_ns, metadata.st_mode)
        return snapshot

    def test_c4_read_only(self):
        # A mode=ro reader alone can create WAL shared memory. A store with
        # pending WAL data must not produce stale counts or touch the store.
        self.screenshots.mkdir()
        (self.screenshots / "found.png").write_bytes(b"not opened as an image")
        self.make_db([("draft-a", "found.png")])
        before = self.snapshot()
        # Even temporary creation followed by cleanup in the input tree is a write.
        with patch.dict(os.environ, TMPDIR=str(self.screenshots), TEMP=str(self.root.parent)):
            result = self.run_state()
        self.assert_status(result, 0, PASS)
        self.assertIn("drafts 1", result.stdout.splitlines())
        self.assertEqual(self.snapshot(), before)

        with closing(sqlite3.connect(self.db)) as db:
            db.execute("PRAGMA locking_mode=EXCLUSIVE")
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            with db:
                db.execute("INSERT INTO drafts(change_id, screenshot) VALUES ('draft-b', 'found.png')")
            self.assertGreater(self.db.with_name(DB_NAME + "-wal").stat().st_size, 0)
            self.assertFalse(self.db.with_name(DB_NAME + "-shm").exists())
            before = self.snapshot()
            result = self.run_state()
            self.assert_status(result, 0, PASS)
            self.assertEqual(result.stdout.splitlines(), [
                "drafts 2", "refs 2", "files 1", "note bad-ref 0",
                "note proposal-orphans 0", "note other-unreferenced 0", PASS,
            ])
            self.assertEqual(self.snapshot(), before)

        # Closing the fixture writer checkpoints WAL. Inspecting the clean WAL
        # database must still count both rows without recreating any sidecars.
        before = self.snapshot()
        result = self.run_state()
        self.assert_status(result, 0, PASS)
        self.assertIn("drafts 2", result.stdout.splitlines())
        self.assertEqual(self.snapshot(), before)

    def test_a1_uncheckpointed_wal(self):
        # A frozen store ships without SHM. Ignoring WAL misses the committed
        # reference and mislabels its proposal screenshot as an orphan.
        self.screenshots.mkdir()
        (self.screenshots / "draft-wal-proposal.png").touch()
        with tempfile.TemporaryDirectory(dir=self.root) as source:
            store = Path(source) / DB_NAME
            self.make_db([("draft-base", None)], path=store)
            with closing(sqlite3.connect(store)) as writer:
                self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
                writer.execute("PRAGMA wal_autocheckpoint=0")
                with writer:
                    writer.execute("INSERT INTO drafts(change_id, screenshot) VALUES (?, ?)",
                                   ("draft-wal", "draft-wal-proposal.png"))
                wal = store.with_name(DB_NAME + "-wal")
                self.assertGreater(wal.stat().st_size, 0)
                shutil.copyfile(store, self.db)
                shutil.copyfile(wal, self.db.with_name(wal.name))

        self.assertFalse(self.db.with_name(DB_NAME + "-shm").exists())
        before = self.snapshot()
        result = self.run_state()
        self.assert_status(result, 0, PASS)
        self.assertEqual(result.stdout.splitlines(), [
            "drafts 2", "refs 1", "files 1", "note bad-ref 0",
            "note proposal-orphans 0", "note other-unreferenced 0", PASS,
        ])
        self.assertEqual(self.snapshot(), before)

    def test_a1_harmless_journal(self):
        # Presence alone is not corruption, and this sidecar must not be removed.
        self.screenshots.mkdir()
        self.make_db([("draft-base", None)])
        self.db.with_name(DB_NAME + "-journal").touch()
        before = self.snapshot()
        result = self.run_state()
        self.assert_status(result, 0, PASS)
        self.assertEqual(result.stdout.splitlines(), [
            "drafts 1", "refs 0", "files 0", "note bad-ref 0",
            "note proposal-orphans 0", "note other-unreferenced 0", PASS,
        ])
        self.assertEqual(self.snapshot(), before)

    def test_a1_symlinked_sidecar(self):
        # Copying without lstat would follow this link and accept an empty WAL.
        self.screenshots.mkdir()
        self.make_db()
        decoy = self.root / "decoy-wal"
        decoy.touch()
        self.db.with_name(DB_NAME + "-wal").symlink_to(decoy)
        before = self.snapshot()
        self.assert_findings(self.run_state(), f"not-sqlite {DB_NAME}")
        self.assertEqual(self.snapshot(), before)

    def test_c5_no_private_values(self):
        # Row and path diagnostics must stay redacted on success, findings and
        # usage errors, even when argparse would normally echo the raw argument.
        canaries = (
            "canary-change-id", "canary-missing-image.png", "canary-summary-text",
            "canary-chat", "canary-sender", "canary-draft-digest", "canary-code",
        )
        self.screenshots.mkdir()
        self.make_db()
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("INSERT INTO drafts VALUES (?, ?, ?, ?, ?, ?, ?)", canaries)
        orphan = "canary-orphan-proposal.png"
        (self.screenshots / orphan).touch()
        finding = self.run_state()
        self.assert_findings(finding, "dangling-screenshot 1")
        (self.screenshots / canaries[1]).touch()
        passing = self.run_state()
        self.assert_status(passing, 0, PASS)
        usage = self.invoke("--state", str(self.state), str(self.screenshots / orphan))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (finding, passing, usage):
            for canary in (*canaries, orphan, str(self.root), str(self.state), str(self.db)):
                self.assertNotIn(canary, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
