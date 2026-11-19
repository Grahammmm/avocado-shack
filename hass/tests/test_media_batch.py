"""AV2152-04 (H12) tests: media.store_originals keeps a batch all or nothing, and removes only what it created.

A temporary media root outside the repository; every photo is built in memory. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_media_batch -v
"""

import errno
import fcntl
import hashlib
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from hass import media
from hass.tests.test_media_web import jpeg, seg

AT = "2026-11-02T18:00:00+00:00"


def origin(moved):
    """The original path of a file the unwind moved aside to .<name>.unwind-<token>."""
    return Path(moved).with_name(Path(moved).name[1:].rsplit(".unwind-", 1)[0])


def pic(i):
    return jpeg(seg(0xFE, f"batch {i}".encode()))


def files(root):
    return sorted(str(Path(d, n).relative_to(root)) for d, _, names in os.walk(root) for n in names)


class StoreOriginalsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"

    def store(self, items):
        return media.store_originals(self.root, items, received_at=AT, source="owner-chat")

    def test_stores_each_photo_in_order_with_sidecar_and_private_modes(self):
        got = self.store([pic(1), pic(2), pic(3)])
        self.assertEqual([g["sha256"] for g in got], [hashlib.sha256(pic(i)).hexdigest() for i in (1, 2, 3)])
        self.assertEqual([g["duplicate"] for g in got], [False] * 3)
        self.assertEqual(len(files(self.root)), 6)
        for g in got: self.assertEqual(stat.S_IMODE(os.stat(g["path"]).st_mode), 0o600)

    def test_a_repeat_inside_the_batch_and_an_earlier_original_are_duplicates(self):
        media.store_original(self.root, pic(1), received_at=AT, source="owner-chat")
        got = self.store([pic(1), pic(2), pic(2)])
        self.assertEqual([g["duplicate"] for g in got], [True, False, True])
        self.assertEqual(len(files(self.root)), 4)

    def test_a_later_corrupt_store_refusal_removes_only_the_new_files(self):
        old = media.store_original(self.root, pic(1), received_at=AT, source="owner-chat")
        bad = hashlib.sha256(pic(3)).hexdigest()
        folder = self.root / "originals" / bad[:2]
        folder.mkdir(parents=True, exist_ok=True)
        os.symlink("/nonexistent", folder / f"{bad}.jpg")  # a symlink where the original belongs: corrupt-store
        before = files(self.root)
        with self.assertRaises(media.BatchRefused) as cm: self.store([pic(1), pic(2), pic(3)])
        self.assertEqual((cm.exception.code, cm.exception.position, cm.exception.reply), ("corrupt-store", 3, media.REPLIES["corrupt-store"]))
        self.assertEqual(files(self.root), before)  # photo 2's original and sidecar are gone again
        self.assertTrue(Path(old["path"]).is_file())
        self.assertTrue(os.path.islink(folder / f"{bad}.jpg"))

    def test_a_write_or_sidecar_fault_removes_the_new_original_and_sidecars_only(self):
        old = media.store_original(self.root, pic(1), received_at=AT, source="owner-chat")
        before = files(self.root)
        real = media._write_new
        writes = []

        def faulty(final, data, created=None):
            writes.append(final.name)
            if len(writes) == 4: raise OSError("disk full")  # photo 2 original, its sidecar, photo 3 original, then photo 3's sidecar
            return real(final, data, created)
        with mock.patch.object(media, "_write_new", faulty), self.assertRaises(media.BatchRefused) as cm:
            self.store([pic(1), pic(2), pic(3)])
        self.assertEqual((cm.exception.code, cm.exception.position), ("corrupt-store", 3))
        self.assertEqual(len(writes), 4)
        self.assertEqual(files(self.root), before)
        self.assertEqual(Path(old["path"]).read_bytes(), pic(1))

    def test_a_missing_sidecar_repaired_by_the_batch_is_removed_but_the_original_stays(self):
        old = media.store_original(self.root, pic(1), received_at=AT, source="owner-chat")
        Path(old["path"]).with_suffix(".json").unlink()
        before = files(self.root)
        with self.assertRaises(media.BatchRefused) as cm: self.store([pic(1), b""])
        self.assertEqual((cm.exception.code, cm.exception.position), ("empty", 2))
        self.assertEqual(files(self.root), before)
        self.assertTrue(Path(old["path"]).is_file())

    def test_a_replaced_file_with_another_inode_is_never_removed(self):
        made = []
        real = media._write_new

        def swap(final, data, created=None):
            real(final, data, created)
            made.append(final)
            if len(made) == 2:  # after photo 1's sidecar: replace its original with a different file, then fail photo 2
                os.unlink(made[0])
                made[0].write_bytes(b"someone else's file")
                raise OSError("fault")
        with mock.patch.object(media, "_write_new", swap), self.assertRaises(media.BatchRefused):
            self.store([pic(1), pic(2)])
        self.assertEqual(made[0].read_bytes(), b"someone else's file")
        self.assertFalse(made[1].exists())

    def fail_second_after(self, hook):
        """Run a two-photo batch whose 2nd photo faults; hook(paths) runs just before the unwind's validation of each file."""
        made = []
        real_write, real_check = media._write_new, media._still_written

        def write(final, data, created=None):
            real_write(final, data, created)
            made.append(final)
            if len(made) == 3: raise OSError("fault")  # photo 1 original + sidecar, then photo 2's original
        with mock.patch.object(media, "_write_new", write), mock.patch.object(media, "_still_written", lambda *a: hook(real_check, *a)):
            with self.assertRaises(media.BatchRefused): self.store([pic(1), pic(2)])
        return made

    def test_the_normal_unwind_removes_its_own_files(self):
        made = self.fail_second_after(lambda real, *a: real(*a))
        self.assertEqual(len(made), 3)
        self.assertEqual(files(self.root), [])

    def test_a_file_replaced_at_the_path_after_validation_survives(self):
        def hook(real, moved, *a):
            ok = real(moved, *a)  # validated and about to be removed; now someone puts another file at the path
            origin(moved).write_bytes(b"late arrival")
            return ok
        made = self.fail_second_after(hook)
        for p in made: self.assertEqual(p.read_bytes(), b"late arrival")  # every validated file was removed; the late file stays
        self.assertEqual([p for p in files(self.root) if ".unwind-" in p], [])

    def test_a_same_inode_rewrite_before_removal_survives(self):
        def hook(real, moved, *a):
            with open(moved, "r+b") as fh: fh.write(b"X")  # same inode, same size, other bytes
            return real(moved, *a)
        made = self.fail_second_after(hook)
        for p in made: self.assertEqual(p.read_bytes()[:1], b"X")  # rewritten files are put back, not removed
        self.assertEqual([p for p in files(self.root) if ".unwind-" in p], [])

    def test_a_mismatch_is_not_put_back_over_a_new_file(self):
        def hook(real, moved, *a):
            with open(moved, "r+b") as fh: fh.write(b"X")
            origin(moved).write_bytes(b"newer")
            return real(moved, *a)
        made = self.fail_second_after(hook)
        for p in made: self.assertEqual(p.read_bytes(), b"newer")  # never clobbered
        self.assertEqual(len([p for p in files(self.root) if ".unwind-" in p]), 3)  # the changed files stay under their moved names

    def test_other_errors_unwind_and_propagate(self):
        with self.assertRaises(ValueError):
            media.store_originals(self.root, [pic(1)], received_at="not a time", source="owner-chat")
        self.assertFalse(self.root.exists())
        real = media.store_original
        calls = []

        def odd(*a, **kw):
            calls.append(1)
            if len(calls) == 2: raise RuntimeError("unexpected")
            return real(*a, **kw)
        with mock.patch.object(media, "store_original", odd), self.assertRaises(RuntimeError): self.store([pic(1), pic(2)])
        self.assertEqual(files(self.root), [])

    def test_iterator_error_reports_restored_and_moved_files(self):
        error = ValueError("iterator failed")

        def items():
            yield pic(1)
            raise error

        def unreadable(moved, *args):
            if origin(moved).suffix == ".jpg":
                origin(moved).write_bytes(b"new arrival")  # only the sidecar can be put back
            raise OSError(errno.EIO, "read error")

        with mock.patch.object(media, "_still_written", unreadable), self.assertRaises(ValueError) as cm:
            self.store(items())
        self.assertIs(cm.exception, error)
        self.assertEqual(str(error), "iterator failed")
        sidecar, = self.root.rglob("*.json")
        moved, = self.root.rglob(".*.jpg.unwind-*")
        self.assertEqual(moved.read_bytes(), pic(1))
        self.assertCountEqual(getattr(error, "__notes__", ()),
                              [f"Batch unwind kept: {path.resolve()}" for path in (sidecar, moved)])  # _open_root resolves the root (symlinked TMPDIR)

    def test_the_many_reply_is_built_from_the_constant(self):
        self.assertEqual(media.MAX_PHOTOS_PER_MESSAGE, 4)
        self.assertEqual(media.REPLIES["many"], "Please send up to 4 photos per message; nothing was saved.")

    # Fix round 2 (dossier D1-D4): the root lock covers single stores too; an unverified candidate is restored, never hidden.

    def test_a_concurrent_single_store_waits_for_a_failing_batch_and_keeps_its_file(self):
        made, got, started = [], [], threading.Event()
        real = media._write_new
        single = threading.Thread(target=lambda: (started.set(), got.append(
            media.store_original(self.root, pic(1), received_at=AT, source="owner-chat"))))

        def write(final, data, created=None):
            real(final, data, created)
            made.append(final)
            if len(made) == 3:  # photo 1 original + sidecar written; the same content arrives as a single store, then photo 2 faults
                single.start()
                started.wait(5)
                single.join(0.5)
                self.assertTrue(single.is_alive())  # blocked on the root lock while the batch still holds it
                raise OSError("fault")
        with mock.patch.object(media, "_write_new", write), self.assertRaises(media.BatchRefused) as cm:
            self.store([pic(1), pic(2)])
        self.assertEqual(cm.exception.kept, ())
        single.join(10)
        self.assertFalse(single.is_alive())
        self.assertEqual(got[0]["duplicate"], False)  # the batch had unwound photo 1 before the single store ran
        self.assertEqual(Path(got[0]["path"]).read_bytes(), pic(1))  # what the single store returned as stored is there
        self.assertTrue(Path(got[0]["path"]).with_suffix(".json").is_file())

    def test_a_symlink_swapped_in_before_the_unwind_ends_at_its_original_path(self):
        made = []
        real = media._write_new
        target = self.tmp / "elsewhere"
        target.write_bytes(b"not in the store")

        def write(final, data, created=None):
            real(final, data, created)
            made.append(final)
            if len(made) == 3:
                os.unlink(made[0])
                os.symlink(target, made[0])  # photo 1's original replaced by a symlink, then photo 2 faults
                raise OSError("fault")
        with mock.patch.object(media, "_write_new", write), self.assertRaises(media.BatchRefused) as cm:
            self.store([pic(1), pic(2)])
        self.assertTrue(os.path.islink(made[0]))
        self.assertEqual(os.readlink(made[0]), str(target))
        self.assertEqual(target.read_bytes(), b"not in the store")
        self.assertEqual(cm.exception.kept, (made[0],))
        self.assertFalse(made[1].exists() or made[2].exists())  # the batch's own files are still removed
        self.assertEqual([p for p in files(self.root) if ".unwind-" in p], [])

    def test_a_validation_error_restores_the_candidate(self):
        def hook(real, moved, *a):
            raise OSError(errno.EIO, "read error")
        made = self.fail_second_after(hook)
        for p, data in zip(made, (pic(1), None, pic(2))):
            self.assertTrue(p.is_file())  # not proven unchanged, so kept at its own path
            if data is not None: self.assertEqual(p.read_bytes(), data)
        self.assertEqual([p for p in files(self.root) if ".unwind-" in p], [])

    def test_an_unverified_candidate_whose_path_is_taken_stays_moved_and_is_reported(self):
        made, real_write = [], media._write_new

        def write(final, data, created=None):
            real_write(final, data, created)
            made.append(final)
            if len(made) == 3: raise OSError("fault")

        def hook(moved, *a):
            origin(moved).write_bytes(b"newer")
            raise OSError(errno.EIO, "read error")
        with mock.patch.object(media, "_write_new", write), mock.patch.object(media, "_still_written", hook):
            with self.assertRaises(media.BatchRefused) as cm: self.store([pic(1), pic(2)])
        for p in made: self.assertEqual(p.read_bytes(), b"newer")  # never clobbered
        self.assertEqual(len(cm.exception.kept), 3)
        for k in cm.exception.kept:
            self.assertIn(".unwind-", k.name)
            self.assertTrue(k.is_file())
        self.assertEqual(sorted(origin(k) for k in cm.exception.kept), sorted(made))

    def test_the_normal_unwind_removes_its_own_files_and_reports_none_kept(self):
        made = []
        real = media._write_new

        def write(final, data, created=None):
            real(final, data, created)
            made.append(final)
            if len(made) == 3: raise OSError("fault")
        with mock.patch.object(media, "_write_new", write), self.assertRaises(media.BatchRefused) as cm:
            self.store([pic(1), pic(2)])
        self.assertEqual((cm.exception.code, cm.exception.position, cm.exception.kept), ("corrupt-store", 2, ()))
        self.assertEqual(files(self.root), [])

    def test_single_stores_and_web_copies_take_the_root_lock(self):
        locks = []
        real = media._lock_root

        def spy(base):
            fd = real(base)
            locks.append(fd)
            return fd
        with mock.patch.object(media, "_lock_root", spy):
            rec = media.store_original(self.root, pic(1), received_at=AT, source="owner-chat")
            media.web_copy(self.root, rec["sha256"])
            self.store([pic(2), pic(3)])  # one lock for the whole batch, none taken again per photo
        self.assertEqual(len(locks), 3)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # every lock was released again
        finally: os.close(fd)


if __name__ == "__main__":
    unittest.main()
