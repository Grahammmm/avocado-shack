"""H06 tests: undo refuses a symlinked or non-directory ``<state>/changes`` parent as '<id> record is unreadable' (RF1040-1).

Throwaway StoreRepo fixtures only. Run: python3 -m unittest hass.tests.test_revert_parent_directory -v
"""

import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass.ops import OpContext
from hass.tests.test_store_ops import NEW_HOURS, REVERT, SET_HOURS, StoreTestCase, _req

STORE = "hass/content/store.json"


class DirectAccessorTests(unittest.TestCase):
    CID = "chg-0123456789ab"

    def ctx(self, state):
        return OpContext(now=None, site_dir=Path("."), settings={}, state_dir=state)

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.state = self.root / "state"
        self.state.mkdir()

    def test_dangling_changes_directory_is_unreadable(self):
        os.symlink(self.root / "nowhere", self.state / "changes")
        with self.assertRaises(OSError):
            self.ctx(self.state).change(self.CID)
        self.assertFalse((self.root / "nowhere").exists())

    def test_non_directory_changes_parent_is_unreadable(self):
        (self.state / "changes").write_text("{}")
        with self.assertRaises(OSError):
            self.ctx(self.state).change(self.CID)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_fifo_changes_parent_is_unreadable_without_opening(self):
        os.mkfifo(self.state / "changes")
        with self.assertRaises(OSError):
            self.ctx(self.state).change(self.CID)

    def test_missing_changes_or_missing_record_is_unknown(self):
        self.assertIsNone(self.ctx(self.state).change(self.CID))
        (self.state / "changes").mkdir()
        self.assertIsNone(self.ctx(self.state).change(self.CID))
        self.assertIsNone(self.ctx(None).change(self.CID))

    def test_malformed_id_and_absent_state_touch_no_filesystem(self):
        with mock.patch("os.lstat", side_effect=AssertionError("touched")):
            self.assertIsNone(self.ctx(self.state).change("../x"))
            self.assertIsNone(self.ctx(None).change(self.CID))

    def test_parent_permission_failure_propagates(self):
        parent = self.state / "changes"
        real = os.lstat

        def lstat(path, *a, **k):
            if os.fspath(path) == os.fspath(parent):
                raise PermissionError(13, "Permission denied")
            return real(path, *a, **k)

        with mock.patch("os.lstat", side_effect=lstat), self.assertRaises(PermissionError):
            self.ctx(self.state).change(self.CID)

    def test_healthy_directory_still_reads(self):
        (self.state / "changes").mkdir()
        (self.state / "changes" / f"{self.CID}.json").write_text('{"a": 1}')
        self.assertEqual(self.ctx(self.state).change(self.CID), {"a": 1})


class UndoParentTests(StoreTestCase):
    def setUp(self):
        self.r = self.repo()
        self.change_id = self.r.run((SET_HOURS, {"hours": NEW_HOURS}))["change_id"]
        self.changes = self.r.state / "changes"
        self.outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.outside)

    def prepare(self):
        return self.r.prepare(_req((REVERT, {"changeId": self.change_id})))

    def assert_refused(self):
        r = self.r
        before = (r.drafts(), r.read(STORE), r.head())
        result = self.prepare()
        self.assertEqual((result["result"], result.get("reason")), ("refused", f"{self.change_id} record is unreadable"),
                         result)
        self.assertEqual((r.drafts(), r.read(STORE), r.head()), before)
        self.assertEqual(r.status(), "")

    def test_linked_changes_directory_is_unreadable(self):
        moved = self.outside / "changes"
        shutil.move(str(self.changes), str(moved))
        os.symlink(moved, self.changes)
        record = moved / f"{self.change_id}.json"
        outside_bytes = record.read_bytes()
        self.assert_refused()
        self.assertEqual(record.read_bytes(), outside_bytes)
        self.assertEqual(stat.S_IFMT(os.lstat(self.changes).st_mode), stat.S_IFLNK)

    def test_dangling_changes_directory_is_unreadable(self):
        shutil.rmtree(self.changes)
        os.symlink(self.outside / "gone", self.changes)
        self.assert_refused()
        self.assertFalse((self.outside / "gone").exists())

    def test_regular_file_changes_parent_is_unreadable(self):
        shutil.rmtree(self.changes)
        self.changes.write_text("not a folder")
        self.assert_refused()

    def test_healthy_undo_and_missing_record_unchanged(self):
        result = self.prepare()
        self.assertEqual(result["result"], "ok", result)
        (self.changes / f"{self.change_id}.json").unlink()
        result = self.prepare()
        self.assertEqual((result["result"], result.get("reason")), ("refused", f"unknown change {self.change_id}"))


if __name__ == "__main__":
    unittest.main()
