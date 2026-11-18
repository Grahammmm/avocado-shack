"""AV2152-04 (H12) tests: media.store_originals keeps a batch all or nothing, and removes only what it created.

A temporary media root outside the repository; every photo is built in memory. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_media_batch -v
"""

import hashlib
import os
import stat
import tempfile
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

    def test_the_many_reply_is_built_from_the_constant(self):
        self.assertEqual(media.MAX_PHOTOS_PER_MESSAGE, 4)
        self.assertEqual(media.REPLIES["many"], "Please send up to 4 photos per message; nothing was saved.")


if __name__ == "__main__":
    unittest.main()
