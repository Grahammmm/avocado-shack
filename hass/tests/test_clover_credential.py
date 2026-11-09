"""HASS-CLOVER-1: the token file check and the Token wrapper. Only a FAKE token made up for these tests is ever used.
Run: python3 -B -m unittest hass.tests.test_clover_credential
"""
import copy
import os
import pickle
import shutil
import stat
import tempfile
import traceback
import unittest
from unittest import mock

from hass.clover import credential
from hass.clover.credential import CredentialError, Token, load_token, redact

FAKE_TOKEN = "FAKE-TOKEN-FOR-TESTS-ONLY-0001"


def exc_text(exc):
    """Everything a log line or a crash report could print about an exception."""
    return "\n".join([str(exc), repr(exc), repr(exc.args), "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))])


class TokenFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="clover-cred-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.chmod(self.dir, 0o700)
        self.path = os.path.join(self.dir, "clover.token")

    def write(self, data=FAKE_TOKEN, mode=0o600):
        if os.path.lexists(self.path):
            os.unlink(self.path)
        with open(self.path, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode())
        os.chmod(self.path, mode)

    def refused(self, reason, **kw):
        with self.assertRaises(CredentialError) as ctx:
            load_token(self.path, **kw)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_mode_600_owned_by_the_user_loads(self):
        self.write()
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(load_token(self.path).authorization(), "Bearer " + FAKE_TOKEN)

    def test_trailing_newline_is_dropped(self):
        for tail in ("\n", "\r\n"):
            with self.subTest(tail=repr(tail)):
                self.write(FAKE_TOKEN + tail)
                self.assertEqual(load_token(self.path).authorization(), "Bearer " + FAKE_TOKEN)

    def test_any_mode_other_than_600_is_refused(self):
        for mode in (0o644, 0o640, 0o660, 0o666, 0o604, 0o400, 0o700, 0o601):
            with self.subTest(mode=oct(mode)):
                self.write(mode=mode)
                self.refused("mode")

    def test_another_owner_is_refused(self):
        self.write()
        real = os.fstat

        def other_owner(fd):
            st = real(fd)
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid + 1, st.st_gid, st.st_size,
                                   int(st.st_atime), int(st.st_mtime), int(st.st_ctime)))
        with mock.patch.object(credential.os, "fstat", other_owner):
            self.refused("owner")

    def test_a_folder_that_is_not_private_is_refused(self):
        self.write()
        for mode in (0o770, 0o750 | 0o002, 0o777, 0o720):
            with self.subTest(mode=oct(mode)):
                os.chmod(self.dir, mode)
                self.refused("folder")
        os.chmod(self.dir, 0o700)
        self.refused("folder", uid=os.getuid() + 1)

    def test_a_symlink_a_directory_and_a_missing_file_are_refused(self):
        self.write()
        link = os.path.join(self.dir, "link")
        os.symlink(self.path, link)
        with self.assertRaises(CredentialError) as ctx:
            load_token(link)
        self.assertEqual(ctx.exception.reason, "unreadable")
        sub = os.path.join(self.dir, "sub")
        os.mkdir(sub, 0o600)
        with self.assertRaises(CredentialError) as ctx:
            load_token(sub)
        self.assertEqual(ctx.exception.reason, "not-regular")
        os.unlink(self.path)
        self.refused("unreadable")

    def test_size_and_format(self):
        self.write("")
        self.refused("size")
        self.write("A" * 600)
        self.refused("size")
        for bad in ("two words here", "tab\tinside-token", "ünïcode-token-value", "short", "x" * 300, "a b\nsecond"):
            with self.subTest(bad=bad[:12]):
                self.write(bad)
                self.refused("format")

    def test_no_error_carries_the_token_the_file_bytes_or_the_path(self):
        marker = "SECRET-MARKER-not-a-token but with spaces"
        cases = [(lambda: self.write(marker), "format"), (lambda: self.write(FAKE_TOKEN, 0o644), "mode"), (lambda: os.unlink(self.path), "unreadable")]
        for setup, reason in cases:
            setup()
            exc = self.refused(reason)
            text = exc_text(exc)
            for secret in (marker, FAKE_TOKEN, self.dir, self.path, "clover.token", "Errno"):
                self.assertNotIn(secret, text)
            self.assertIsNone(exc.__cause__)
            self.assertTrue(exc.__suppress_context__ or exc.__context__ is None)

    def test_every_reason_has_a_fixed_phrase(self):
        self.assertEqual(set(credential.REASONS), {"unreadable", "not-regular", "owner", "mode", "folder", "size", "format"})


class TokenObjectTests(unittest.TestCase):
    def setUp(self):
        self.token = Token(FAKE_TOKEN)

    def test_it_never_prints(self):
        for text in (repr(self.token), str(self.token), f"{self.token}", "%s" % self.token, "%r" % self.token, format(self.token, ">40"),
                     repr([self.token]), repr({"k": self.token}), str((self.token,))):
            self.assertNotIn(FAKE_TOKEN, text)
        self.assertEqual(repr(self.token), "Token(<redacted>)")

    def test_it_cannot_be_pickled_copied_or_inspected(self):
        for fn in (lambda: pickle.dumps(self.token), lambda: copy.copy(self.token), lambda: copy.deepcopy(self.token), lambda: vars(self.token)):
            with self.assertRaises(TypeError):
                fn()
        with self.assertRaises(AttributeError):
            self.token._value = "other"
        with self.assertRaises(AttributeError):
            self.token.extra = 1

    def test_redact_removes_the_token_and_any_bearer_string(self):
        text = f"failed with {FAKE_TOKEN} and header Authorization: Bearer abc.def-123 end"
        out = self.token.redact(text)
        self.assertNotIn(FAKE_TOKEN, out)
        self.assertNotIn("abc.def-123", out)
        self.assertIn("[redacted]", out)
        self.assertNotIn("abc.def-123", redact("Bearer abc.def-123"))


if __name__ == "__main__":
    unittest.main()
