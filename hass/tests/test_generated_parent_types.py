"""H01: a non-directory intermediate parent of any selected output is refused before any write.

Temp roots per test; the checkout is only read.
Run: python3 -B -m unittest hass.tests.test_generated_parent_types -v
"""

import errno
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import sitegen
from hass.tests.test_content import IsolatedRepo
from hass.tests.test_generated_io import _run
from hass.tests.test_generated_links import FILES, SITE, _tree

FIRST, LATER = SITE + "producers.json", SITE + "hike/index.html"
TWO = {FIRST: FILES[FIRST], LATER: FILES[LATER]}
OLD = b'{"old": true}\n'
BLOCK = b"not a folder\n"


class GeneratedParentTypeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hass-h01-parents-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "root"
        (self.root / SITE).mkdir(parents=True)
        self.first = self.root / FIRST
        self.first.write_bytes(OLD)
        os.utime(self.first, ns=(1_000_000_000, 1_000_000_000))

    def assertRefusedUntouched(self, files=TWO, only=None):
        with mock.patch("tempfile.mkstemp") as mk:
            with self.assertRaises(NotADirectoryError) as ctx:
                sitegen.write_files(files, self.root, only=only)
        self.assertEqual((ctx.exception.errno, ctx.exception.strerror),
                         (errno.ENOTDIR, "generated folder is not a directory"))
        mk.assert_not_called()
        self.assertEqual(self.first.read_bytes(), OLD)
        self.assertEqual(self.first.stat().st_mtime_ns, 1_000_000_000)
        self.assertEqual(list(self.root.rglob(".*.tmp")), [])

    def test_later_regular_parent_refuses_before_first_write(self):
        blocker = self.root / SITE / "hike"
        blocker.write_bytes(BLOCK)
        self.assertRefusedUntouched()
        self.assertEqual(blocker.read_bytes(), BLOCK)

    def test_later_fifo_and_socket_parent_are_not_opened(self):
        blocker = self.root / SITE / "hike"
        kinds = []
        if hasattr(os, "mkfifo"):
            kinds.append("fifo")
        if hasattr(socket, "AF_UNIX"):
            kinds.append("socket")
        if not kinds:
            self.skipTest("no FIFO/socket support")
        for kind in kinds:
            with self.subTest(kind=kind):
                sock = None
                try:
                    if kind == "fifo":
                        os.mkfifo(blocker)
                    else:
                        sock = socket.socket(socket.AF_UNIX)
                        cwd = os.getcwd()
                        os.chdir(blocker.parent)  # relative bind keeps the path under the AF_UNIX limit
                        try:
                            sock.bind(blocker.name)
                        finally:
                            os.chdir(cwd)
                    self.assertRefusedUntouched()
                finally:
                    if sock:
                        sock.close()
                    if os.path.lexists(blocker):
                        os.unlink(blocker)

    def test_out_cli_blocked_hike_parent_leaves_tree_unchanged(self):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        (self.root / SITE / "hike").write_bytes(BLOCK)
        before = _tree(self.root)
        mtime = self.first.stat().st_mtime_ns
        code, out, err = _run(sitegen.main, "--out", str(self.root), "--repo", str(repo.root))
        self.assertEqual((code, out, err), (2, "", "sitegen: io error: NotADirectoryError\n"))
        self.assertEqual(_tree(self.root), before)
        self.assertEqual(self.first.stat().st_mtime_ns, mtime)

    def test_only_ignores_blocked_unselected_parent(self):
        blocker = self.root / SITE / "hike"
        blocker.write_bytes(BLOCK)
        self.assertEqual(sitegen.write_files(TWO, self.root, only=[FIRST]), [FIRST])
        with self.assertRaises(NotADirectoryError):
            sitegen.write_files(TWO, self.root, only=[LATER])
        self.assertEqual(blocker.read_bytes(), BLOCK)

    def test_missing_parents_and_linked_root_still_work(self):
        self.assertEqual(sitegen.write_files(TWO, self.root), [FIRST, LATER])
        self.assertEqual((self.root / LATER).read_bytes(), FILES[LATER])
        link = self.root.parent / "rootlink"
        link.symlink_to(self.root, target_is_directory=True)
        files = {SITE + "deep/er/page.html": b"x\n"}
        self.assertEqual(sitegen.write_files(files, link), list(files))
        self.assertEqual((self.root / SITE / "deep/er/page.html").read_bytes(), b"x\n")

    def test_symlink_parent_check_still_first(self):
        (self.root.parent / "elsewhere").mkdir()
        (self.root / SITE / "hike").symlink_to(self.root.parent / "elsewhere", target_is_directory=True)
        with self.assertRaises(OSError) as ctx:
            sitegen.write_files(TWO, self.root)
        self.assertEqual(ctx.exception.errno, errno.ELOOP)


if __name__ == "__main__":
    unittest.main()
