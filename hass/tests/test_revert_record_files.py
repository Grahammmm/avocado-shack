"""H06 tests: ``history.revert`` reads its change and draft records only as regular, non-link files (RF1800-1).

A FIFO draft never hangs the undo, and a change record that is a link, FIFO or folder is refused as unreadable;
nothing is drafted, written or committed. Each case uses a throwaway StoreRepo (temp repo + temp state dir, fixture
content only, production ops). Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import os
import shutil
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from hass.tests.test_store_ops import NEW_HOURS, REVERT, SET_HOURS, StoreTestCase, _req

STORE = "hass/content/store.json"


class RevertRecordFileTests(StoreTestCase):
    def setUp(self):
        self.r = self.repo()
        self.store_before = self.r.read(STORE)
        self.change_id = self.r.run((SET_HOURS, {"hours": NEW_HOURS}))["change_id"]
        self.record = self.r.state / "changes" / f"{self.change_id}.json"
        self.draft = self.r.state / "drafts" / f"{self.change_id}.json"
        self.record_bytes = self.record.read_bytes()
        self.draft_bytes = self.draft.read_bytes()

    def _snapshot(self, path):
        """The kind of ``path`` plus its link target or bytes, without ever opening a FIFO."""
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            return "link", os.readlink(path)
        return stat.S_IFMT(mode), path.read_bytes() if stat.S_ISREG(mode) else None

    def _fifo(self, path):
        path.unlink()
        os.mkfifo(path)
        self.addCleanup(self._release, path)

    @staticmethod
    def _release(path):
        """If a reader is still blocked on the FIFO (a failing run), open and close its write end to free it."""
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass

    def revert(self, denied=None):
        """Prepare the undo in a daemon thread (os.lstat of ``denied`` raising PermissionError); > 5 s is a hang."""
        out, real = [], os.lstat

        def lstat(path, *args, **kwargs):
            if denied is not None and os.fspath(path) == os.fspath(denied):
                raise PermissionError(13, "Permission denied")
            return real(path, *args, **kwargs)

        def call():
            with mock.patch("os.lstat", side_effect=lstat):
                out.append(self.r.prepare(_req((REVERT, {"changeId": self.change_id}))))

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        worker.join(5)
        self.assertFalse(worker.is_alive(), "undo hung on a record file")
        return out[0]

    def assert_refused(self, reason, denied=None):
        """Undo is refused with exactly ``reason``; no draft, store bytes, git head or record file changes."""
        r = self.r
        before = (r.drafts(), r.read(STORE), r.head(), self._snapshot(self.record), self._snapshot(self.draft))
        result = self.revert(denied)
        self.assertEqual((result["result"], result.get("reason")), ("refused", reason), result)
        self.assertNotIn("Traceback", json.dumps(result))
        after = (r.drafts(), r.read(STORE), r.head(), self._snapshot(self.record), self._snapshot(self.draft))
        self.assertEqual(after, before)
        self.assertEqual(r.status(), "")
        self.assertEqual(r.store()["hours"], NEW_HOURS)

    def _outside(self, data):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        target = root / "copy.json"
        target.write_bytes(data)
        return target

    # Draft record (<state>/drafts/<id>.json)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_fifo_draft_is_unreadable_without_hanging(self):
        self._fifo(self.draft)
        self.assert_refused(f"{self.change_id} draft is unreadable")

    def test_folder_or_linked_draft_is_unreadable(self):
        target = self._outside(self.draft_bytes)
        for name, make in (("folder", self.draft.mkdir), ("link to a valid draft", lambda: os.symlink(target, self.draft)),
                           ("dangling link", lambda: os.symlink(target.parent / "missing.json", self.draft))):
            with self.subTest(name):
                if self.draft.is_dir() and not self.draft.is_symlink():
                    self.draft.rmdir()
                else:
                    self.draft.unlink()
                make()
                self.assert_refused(f"{self.change_id} draft is unreadable")

    def test_draft_lstat_permission_error_is_unreadable(self):
        self.assert_refused(f"{self.change_id} draft is unreadable", denied=self.draft)

    # Change record (<state>/changes/<id>.json)

    def test_record_linked_to_a_valid_copy_outside_state_is_unreadable(self):
        target = self._outside(self.record_bytes)
        self.record.unlink()
        os.symlink(target, self.record)
        self.assert_refused(f"{self.change_id} record is unreadable")
        self.assertEqual(target.read_bytes(), self.record_bytes)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_fifo_record_is_unreadable_without_hanging(self):
        self._fifo(self.record)
        self.assert_refused(f"{self.change_id} record is unreadable")

    def test_folder_record_is_unreadable(self):
        self.record.unlink()
        self.record.mkdir()
        self.assert_refused(f"{self.change_id} record is unreadable")

    def test_record_lstat_permission_error_is_unreadable(self):
        self.assert_refused(f"{self.change_id} record is unreadable", denied=self.record)

    def test_missing_record_is_unknown_change(self):
        self.record.unlink()
        result = self.revert()
        self.assertEqual((result["result"], result.get("reason")), ("refused", f"unknown change {self.change_id}"))
        self.assertEqual(self.r.store()["hours"], NEW_HOURS)

    # Regressions: healthy files and an absent drafts folder revert as today

    def _assert_reverts(self):
        result = self.revert()
        self.assertEqual(result["result"], "ok", result)
        self.assertEqual(self.r.apply(result["draft"])["result"], "applied")
        self.assertEqual(self.r.store(), json.loads(self.store_before))
        self.assertEqual(json.loads(self.record.read_text("utf-8"))["revertedBy"], result["draft"]["change_id"])

    def test_healthy_record_and_draft_revert_as_today(self):
        self._assert_reverts()

    def test_no_drafts_folder_reverts_as_today(self):
        drafts = self.draft.parent
        os.rename(drafts, drafts.with_name("drafts-moved"))
        self._assert_reverts()


if __name__ == "__main__":
    unittest.main()
