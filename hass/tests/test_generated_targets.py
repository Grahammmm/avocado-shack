"""H01: write_files checks every target before replacing any (RF0740-1).

A symlink, folder or FIFO at a later generated path is refused before the first temp file,
so earlier files are never replaced. Temp roots per test; the checkout is only read.
Run: python3 -m unittest hass.tests.test_generated_targets -v
"""

import errno
import os
import tempfile
import unittest
from pathlib import Path

from hass import sitegen
from hass.tests.test_content import IsolatedRepo
from hass.tests.test_generated_io import _run
from hass.tests.test_generated_links import FILES, SITE, _tree

FIRST, LATER = SITE + "producers.json", SITE + "index.html"
TWO = {FIRST: FILES[FIRST], LATER: FILES[LATER]}
OLD = b'{"old": true}\n'


class GeneratedTargetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hass-h01-targets-")
        self.addCleanup(tmp.cleanup)
        self.root, self.outside = Path(tmp.name) / "root", Path(tmp.name) / "outside"
        self.root.mkdir()
        self.outside.mkdir()

    def _first(self):
        (self.root / SITE).mkdir()
        first = self.root / FIRST
        first.write_bytes(OLD)
        os.utime(first, ns=(1_000_000_000, 1_000_000_000))
        return first

    def assertRefused(self, err, msg, files=TWO):
        with self.assertRaises(OSError) as ctx:
            sitegen.write_files(files, self.root)
        self.assertEqual((ctx.exception.errno, ctx.exception.strerror), (err, msg))

    def assertFirstUntouched(self, first):
        self.assertEqual(first.read_bytes(), OLD)
        self.assertEqual(first.stat().st_mtime_ns, 1_000_000_000)
        self.assertEqual(list(self.root.rglob(".*.tmp")) + list(self.outside.rglob(".*.tmp")), [])

    def test_later_symlink_refused_before_first_write(self):
        first = self._first()
        (self.outside / "page.html").write_bytes(b"outside\n")
        (self.root / LATER).symlink_to(self.outside / "page.html")
        self.assertRefused(errno.ELOOP, "generated target is a symlink")
        self.assertFirstUntouched(first)
        self.assertEqual(_tree(self.outside), {"page.html": b"outside\n"})

    def test_later_folder_refused_before_first_write(self):
        first = self._first()
        (self.root / LATER).mkdir()
        (self.root / LATER / "keep.txt").write_bytes(b"keep\n")
        self.assertRefused(errno.EISDIR, "generated target is not a regular file")
        self.assertFirstUntouched(first)
        self.assertEqual(_tree(self.root / LATER), {"keep.txt": b"keep\n"})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on this platform")
    def test_later_fifo_refused_and_never_opened(self):
        first = self._first()
        os.mkfifo(self.root / LATER)
        self.assertRefused(errno.EINVAL, "generated target is not a regular file")  # an open() would hang here
        self.assertFirstUntouched(first)
        self.assertFalse((self.root / LATER).is_file())

    def test_only_checks_and_writes_the_selected_set(self):
        self._first()
        (self.root / LATER).symlink_to(self.outside / "page.html")
        self.assertEqual(sitegen.write_files(TWO, self.root, only=[FIRST]), [FIRST])
        self.assertEqual((self.root / FIRST).read_bytes(), TWO[FIRST])
        self.assertEqual(_tree(self.outside), {})
        self.assertRefused(errno.ELOOP, "generated target is a symlink", {LATER: TWO[LATER]})  # selecting it refuses

    def test_dangling_target_link_refused_before_any_write(self):
        first = self._first()
        (self.root / LATER).symlink_to(self.outside / "missing.html")
        self.assertRefused(errno.ELOOP, "generated target is a symlink")
        self.assertFirstUntouched(first)
        self.assertFalse(os.path.lexists(self.outside / "missing.html"))

    def test_root_link_with_regular_targets_writes_as_before(self):
        link = self.root / "out-link"
        link.symlink_to(self.outside, target_is_directory=True)
        (self.outside / SITE).mkdir()
        (self.outside / FIRST).write_bytes(OLD)
        self.assertEqual(sitegen.write_files(FILES, link), list(FILES))
        for rel, data in FILES.items():
            self.assertEqual((self.outside / rel).read_bytes(), data)

    def test_write_cli_with_later_linked_target_is_io_error(self):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        content = sitegen.load_and_validate(repo.root / "hass" / "content", repo.root / SITE)
        order = list(sitegen.render(content, repo.root / "hass" / "templates"))
        first, later = repo.root / order[0], repo.root / order[-1]
        first.write_bytes(OLD)  # a real difference, so --write would replace it first
        (self.outside / "page").write_bytes(b"outside\n")
        later.unlink()
        later.symlink_to(self.outside / "page")
        code, out, err = _run(sitegen.main, "--write", "--repo", str(repo.root))
        self.assertEqual((code, out, err), (2, "", "sitegen: io error: OSError\n"))
        self.assertEqual(first.read_bytes(), OLD)
        self.assertEqual(_tree(self.outside), {"page": b"outside\n"})


if __name__ == "__main__":
    unittest.main()
