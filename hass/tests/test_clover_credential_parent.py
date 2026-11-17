"""HASS-CLOVER-1: the token read is anchored to the checked folder. Fabricated tokens and private temp folders only.
Run: python3 -B -m unittest hass.tests.test_clover_credential_parent
"""
import errno
import os
import shutil
import stat
import tempfile
import traceback
import unittest
from unittest import mock

from hass.clover import credential
from hass.clover.credential import CredentialError, inspect, load_token

GOOD = "FAKE-GOOD-TOKEN-FOR-TESTS-0001"
EVIL = "FAKE-EVIL-TOKEN-FOR-TESTS-0002"


def put(folder, token, folder_mode=0o700):
    os.makedirs(folder, exist_ok=True)
    os.chmod(folder, folder_mode)
    path = os.path.join(folder, "clover.token")
    with open(path, "w") as fh:
        fh.write(token)
    os.chmod(path, 0o600)
    return path


class ParentAnchorTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="clover-parent-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.chmod(self.root, 0o700)
        self.parent = os.path.join(self.root, "safe")
        self.path = put(self.parent, GOOD)
        self.moved = os.path.join(self.root, "safe.orig")

    def swap_after_lstat(self, substitute):
        """After the first lstat of the checked folder, move it aside and let `substitute()` put something at its name."""
        real, done = os.lstat, []

        def lstat(p, *a, **k):
            st = real(p, *a, **k)
            if p == self.parent and not done:
                done.append(1)
                os.rename(self.parent, self.moved)
                substitute()
            return st
        return mock.patch.object(credential.os, "lstat", lstat)

    def refused(self, reason):
        with self.assertRaises(CredentialError) as ctx:
            load_token(self.path)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_healthy_read_still_works(self):
        self.assertEqual(load_token(self.path).authorization(), "Bearer " + GOOD)

    def test_parent_symlink_swap_after_lstat_is_refused(self):
        evil = os.path.join(self.root, "evil")
        put(evil, EVIL, 0o777)
        with self.swap_after_lstat(lambda: os.symlink(evil, self.parent)):
            self.refused("folder")

    def test_parent_directory_replacement_is_refused(self):
        with self.swap_after_lstat(lambda: put(self.parent, EVIL)):
            self.refused("folder")

    def test_opened_parent_owner_and_write_bits_are_checked(self):
        real = os.fstat

        def tweak(change):
            def fstat(fd):
                st = real(fd)
                if stat.S_ISDIR(st.st_mode):
                    st = os.stat_result(change(st))
                return st
            return fstat
        other = tweak(lambda s: (s.st_mode, s.st_ino, s.st_dev, s.st_nlink, s.st_uid + 1, s.st_gid, s.st_size, 0, 0, 0))
        group = tweak(lambda s: (s.st_mode | 0o020, s.st_ino, s.st_dev, s.st_nlink, s.st_uid, s.st_gid, s.st_size, 0, 0, 0))
        for name, fake in (("owner", other), ("writable", group)):
            with self.subTest(name), mock.patch.object(credential.os, "fstat", fake), \
                    mock.patch.object(credential.os, "read", side_effect=AssertionError("token read")):
                self.refused("folder")

    def test_leaf_open_uses_checked_directory_descriptor(self):
        real, done = os.open, []

        def opener(p, flags, *a, **k):
            if k.get("dir_fd") is not None and not done:
                done.append(1)
                os.rename(self.parent, self.moved)
                put(self.parent, EVIL, 0o777)
            return real(p, flags, *a, **k)
        with mock.patch.object(credential.os, "open", opener):
            token = load_token(self.path)
        self.assertEqual(token.authorization(), "Bearer " + GOOD)

    def test_parent_and_leaf_descriptors_close_on_all_paths(self):
        real_open, real_fstat, real_read = os.open, os.fstat, os.read
        opened = []

        def opener(*a, **k):
            fd = real_open(*a, **k)
            opened.append(fd)
            return fd

        def bad_dir(fd):
            st = real_fstat(fd)
            if stat.S_ISDIR(st.st_mode):
                st = os.stat_result((st.st_mode | 0o020,) + tuple(st)[1:])
            return st

        def bad_read(fd, n):
            raise OSError(errno.EIO, "boom")

        def chmod644():
            os.chmod(self.path, 0o644)
        cases = [("healthy", None, None), ("leaf refusal", chmod644, "mode"), ("folder refusal", bad_dir, "folder"),
                 ("read error", bad_read, "unreadable")]
        for name, tweak, reason in cases:
            opened.clear()
            with self.subTest(name), mock.patch.object(credential.os, "open", opener):
                os.chmod(self.path, 0o600)
                patches = []
                if name == "leaf refusal":
                    tweak()
                elif name == "folder refusal":
                    patches.append(mock.patch.object(credential.os, "fstat", tweak))
                elif name == "read error":
                    patches.append(mock.patch.object(credential.os, "read", bad_read))
                for p in patches:
                    p.start()
                try:
                    if reason:
                        self.refused(reason)
                    else:
                        load_token(self.path)
                finally:
                    for p in patches:
                        p.stop()
                self.assertGreaterEqual(len(opened), 1 if name == "folder refusal" else 2)
                for fd in opened:
                    with self.assertRaises(OSError) as ctx:
                        real_fstat(fd)
                    self.assertEqual(ctx.exception.errno, errno.EBADF)
        with mock.patch.object(credential.os, "open", side_effect=AssertionError("opened")):
            self.assertIsNone(inspect(self.path))

    def test_refusals_do_not_leak_or_chain_paths_or_bytes(self):
        with self.swap_after_lstat(lambda: put(self.parent, EVIL)):
            exc = self.refused("folder")
        text = "\n".join([str(exc), repr(exc), repr(exc.args), "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))])
        for secret in (GOOD, EVIL, self.root, self.path, "clover.token", "Errno"):
            self.assertNotIn(secret, text)
        self.assertIsNone(exc.__cause__)
        self.assertTrue(exc.__suppress_context__ or exc.__context__ is None)


if __name__ == "__main__":
    unittest.main()
