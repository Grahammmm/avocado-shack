"""RF1100-18: retention counts only completed .png regular files as screenshots (synthetic temp files, read-only).

Run: python3 -B -m unittest hass.tests.test_retention_screenshots -v
"""
import contextlib, io, json, os, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import conversation, inbox, retention
from hass.tests.test_retention import tree

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
CUT = NOW - timedelta(days=30)
OLD, NEW = (CUT - timedelta(days=1)).timestamp(), (NOW - timedelta(days=1)).timestamp()


class ShotsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.shots = self.tmp / "shots"
        self.shots.mkdir()

    def put(self, name, size, when=OLD):
        (self.shots / name).write_bytes(b"x" * size)
        os.utime(self.shots / name, (when, when))

    def test_old_png_only_counts_completed_extension(self):
        self.put("real.png", 3)
        for name, size in (("notes.txt", 16), ("a.json", 4), ("noext", 5), ("cap.png.tmp", 7), ("UP.PNG", 9)):
            self.put(name, size)
        self.assertEqual(retention._shots(self.shots, CUT), {"files": 1, "bytes": 3})

    def test_cutoff_is_strict_and_zero_byte_png_counts(self):
        self.put("zero.png", 0)
        self.put("a.png", 4)
        self.put("b.png", 6)
        self.put("equal.png", 8, CUT.timestamp())
        self.put("new.png", 10, NEW)
        self.assertEqual(retention._shots(self.shots, CUT), {"files": 3, "bytes": 10})

    def test_nonregular_entries_and_nested_png_are_ignored(self):
        self.put("target.png", 5)
        outside = self.tmp / "outside.png"
        outside.write_bytes(b"y" * 50)
        os.utime(outside, (OLD, OLD))
        os.symlink(outside, self.shots / "link.png")
        os.symlink(self.tmp / "missing", self.shots / "dangling.png")
        os.mkfifo(self.shots / "fifo.png")
        (self.shots / "dir.png").mkdir()
        (self.shots / "dir.png" / "nested.png").write_bytes(b"z" * 40)
        os.utime(self.shots / "dir.png" / "nested.png", (OLD, OLD))
        self.assertEqual(retention._shots(self.shots, CUT), {"files": 1, "bytes": 5})

    def test_missing_and_symlinked_screenshot_folder_stay_empty(self):
        self.put("a.png", 4)
        link = self.tmp / "link"
        os.symlink(self.shots, link)
        before = tree(self.tmp)
        zero = {"files": 0, "bytes": 0}
        self.assertEqual(retention._shots(self.tmp / "nope", CUT), zero)
        self.assertEqual(retention._shots(link, CUT), zero)
        self.assertEqual(tree(self.tmp), before)


class CliTest(unittest.TestCase):
    def test_cli_report_preserves_schema_privacy_and_tree(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        state = tmp / "state"
        state.mkdir(mode=0o700)
        for name, schema in (("inbox.sqlite3", inbox.SCHEMA), ("conversation.sqlite3", conversation.SCHEMA)):
            with contextlib.closing(sqlite3.connect(state / name)) as db, db:
                db.executescript(schema)
        shots = state / "screenshots"
        shots.mkdir()
        for name, size in (("secretname-a.png", 3), ("secretname-b.png", 4), ("secretname.txt", 20), ("secretname.png.tmp", 9)):
            (shots / name).write_bytes(b"x" * size)
            os.utime(shots / name, (OLD, OLD))
        before = tree(tmp)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = retention.main(["report", "--state", str(state), "--days", "30", "--now", NOW.isoformat()])
        doc = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(doc["screenshots"], {"files": 2, "bytes": 7})
        self.assertEqual(doc["deletes"], 0)
        self.assertNotIn("secretname", out.getvalue() + err.getvalue())
        self.assertNotIn(str(tmp), out.getvalue() + err.getvalue())
        self.assertEqual(tree(tmp), before)


if __name__ == "__main__":
    unittest.main()
