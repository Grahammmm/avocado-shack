import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass.clover import journal as jmod
from hass.clover.cache import CacheUnsafe


class JournalLockOpenTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        self.j = jmod.Journal(self.state, SimpleNamespace(environment="sandbox", merchant_id="FAKEMERCH0001"))
        self.lock = self.j.path.with_suffix(".lock")

    def _swap_after_preflight(self, swap):
        real = jmod._private_file

        def hook(path, create):
            out = real(path, create)
            if path == self.lock:
                swap(self.lock)
            return out
        return mock.patch.object(jmod, "_private_file", hook)

    def _refused(self, swap):
        with self._swap_after_preflight(swap), mock.patch.object(jmod.sqlite3, "connect") as conn, \
                mock.patch.object(jmod.fcntl, "flock") as flock:
            with self.assertRaises(CacheUnsafe):
                with self.j.locked():
                    self.fail("yielded")
        conn.assert_not_called()
        flock.assert_not_called()

    def test_symlink_swap_between_preflight_and_open_is_refused(self):
        other = self.root / "other"
        other.write_bytes(b"external")
        other.chmod(0o600)

        def swap(lock):
            lock.unlink()
            lock.symlink_to(other)
        self._refused(swap)
        self.assertEqual(other.read_bytes(), b"external")
        self.assertEqual(other.stat().st_mode & 0o777, 0o600)

    def test_reopened_descriptor_metadata_is_validated(self):
        def swap(lock):
            lock.unlink()
            lock.write_bytes(b"")
            lock.chmod(0o640)
        self._refused(swap)
        self.assertEqual(self.lock.stat().st_mode & 0o777, 0o640)

    def test_regular_private_lock_preserves_journal_identity(self):
        with self.j.locked() as db:
            db.execute("INSERT INTO changes(code) VALUES('c1')")
            ident = db.execute("SELECT v FROM meta WHERE k='identity'").fetchone()[0]
        with self.assertRaises(RuntimeError):
            with self.j.locked() as db:
                self.assertEqual(db.execute("SELECT v FROM meta WHERE k='identity'").fetchone()[0], ident)
                self.assertEqual(db.execute("SELECT count(*) FROM changes").fetchone()[0], 1)
                raise RuntimeError("body")
        with self.j.locked():
            pass

    def test_descriptor_closes_on_validation_and_body_errors(self):
        opened = []
        real_open = os.open

        def op(path, *a, **k):
            fd = real_open(path, *a, **k)
            if str(path).endswith(".lock"):
                opened.append(fd)
            return fd

        def swap(lock):
            lock.unlink()
            lock.write_bytes(b"")
            lock.chmod(0o640)
        with mock.patch.object(jmod.os, "open", op):
            with self.assertRaises(RuntimeError):
                with self.j.locked():
                    raise RuntimeError("body")
            with self._swap_after_preflight(swap):
                with self.assertRaises(CacheUnsafe):
                    with self.j.locked():
                        pass
        self.assertGreaterEqual(len(opened), 2)
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)
        self.lock.chmod(0o600)
        with self.j.locked():
            pass


if __name__ == "__main__":
    unittest.main()
