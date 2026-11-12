"""RF0600-10: diff_paths reads at most len(expected) + 1 bytes of each regular generated file.

Synthetic temp files only. Run: python3 -B -m unittest hass.tests.test_generated_compare_bounds -q
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import sitegen

REL = "storefront-mockup/generated.txt"


class _Spy:
    """Wrap Path.open to record the size argument of every read on binary handles."""

    def __init__(self):
        self.reads = []
        self.returned = []
        self._real = Path.open

    def __enter__(self):
        spy = self

        def opener(path, mode="r", *a, **k):
            handle = spy._real(path, mode, *a, **k)
            if "b" not in mode:
                return handle
            return _Handle(handle, spy)

        self._patch = mock.patch.object(Path, "open", opener)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()


class _Handle:
    def __init__(self, inner, spy):
        self._inner, self._spy = inner, spy

    def read(self, size=-1):
        self._spy.reads.append(size)
        out = self._inner.read(size)
        self._spy.returned.append(len(out))
        return out

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._inner.close()


class CompareBoundTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hass-rf0600-10-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "root"
        (self.root / "storefront-mockup").mkdir(parents=True)
        self.target = self.root / REL

    def write(self, data):
        self.target.write_bytes(data)

    def test_oversized_actual_read_is_expected_length_plus_one(self):
        expected = b"123456789"
        for actual in (b"x" * (1 << 20), expected + b"y" * (1 << 20)):
            self.write(actual)
            with _Spy() as spy, mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded")):
                self.assertEqual(sitegen.diff_paths({REL: expected}, self.root), [REL])
            self.assertEqual(spy.reads, [10])
            self.assertLessEqual(max(spy.returned), 10)

    def test_exact_short_long_empty_and_binary_contents(self):
        cases = [
            (b"abc", b"abc", False), (b"abc", b"abd", True), (b"abc", b"ab", True), (b"abc", b"abcd", True),
            (b"", b"", False), (b"", b"x", True), (b"x", b"", True),
            (b"\xff\x00\xfe", b"\xff\x00\xfe", False), (b"\xff\x00\xfe", b"\xff\x00\xff", True),
        ]
        for expected, actual, drift in cases:
            self.write(actual)
            files = {REL: expected}
            self.assertEqual(sitegen.diff_paths(files, self.root), [REL] if drift else [], (expected, actual))
            self.assertEqual(files, {REL: expected})

    def test_empty_expected_requests_one_byte(self):
        self.write(b"z" * 5000)
        with _Spy() as spy:
            self.assertEqual(sitegen.diff_paths({REL: b""}, self.root), [REL])
        self.assertEqual(spy.reads, [1])

    def test_growth_at_open_seam_stays_bounded(self):
        self.write(b"abc")
        real = Path.open

        def grow(path, mode="r", *a, **k):
            if "b" in mode:
                with real(path, "ab") as f:
                    f.write(b"z" * (1 << 20))
            return real(path, mode, *a, **k)

        with mock.patch.object(Path, "open", grow):
            self.assertEqual(sitegen.diff_paths({REL: b"abc"}, self.root), [REL])

    def test_link_missing_directory_and_special_file_never_open(self):
        outside = self.tmp / "outside.txt"
        outside.write_bytes(b"abc")
        os.symlink(outside, self.root / "storefront-mockup/link.txt")
        os.symlink(self.tmp / "nowhere", self.root / "storefront-mockup/dangling.txt")
        (self.root / "storefront-mockup/dir.txt").mkdir()
        os.mkfifo(self.root / "storefront-mockup/fifo.txt")
        names = ["link", "dangling", "dir", "fifo", "missing"]
        files = {f"storefront-mockup/{n}.txt": b"abc" for n in names}
        with mock.patch.object(Path, "open", side_effect=AssertionError("opened")):
            self.assertEqual(sitegen.diff_paths(files, self.root), list(files))

    def test_root_link_allowed_and_read_failure_propagates(self):
        self.write(b"abc")
        alias = self.tmp / "alias"
        os.symlink(self.root, alias)
        self.assertEqual(sitegen.diff_paths({REL: b"abc"}, alias), [])
        with mock.patch.object(Path, "open", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                sitegen.diff_paths({REL: b"abc"}, self.root)


if __name__ == "__main__":
    unittest.main()
