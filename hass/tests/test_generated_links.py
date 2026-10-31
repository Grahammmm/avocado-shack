"""H01: write_files refuses a symlinked folder between root and a generated file (RF1240-9).

Temp roots and an `outside` folder per test; the checkout is only read.
Run: python3 -m unittest hass.tests.test_generated_links -v
"""

import errno
import os
import tempfile
import unittest
from pathlib import Path

from hass import sitegen
from hass.tests.test_content import IsolatedRepo
from hass.tests.test_generated_io import _run

SITE = "storefront-mockup/"
FILES = {SITE + "producers.json": b"{}\n", SITE + "index.html": b"<p>top</p>\n", SITE + "hike/index.html": b"<p>hike</p>\n"}


def _tree(folder):
    """Every entry under folder (links not followed) with file bytes."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(folder):
        for name in dirnames + filenames:
            path = Path(dirpath, name)
            rel = str(path.relative_to(folder))
            found[rel] = os.readlink(path) if path.is_symlink() else (path.read_bytes() if path.is_file() else None)
    return found


class GeneratedLinkTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hass-h01-links-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "root"
        self.outside = Path(tmp.name) / "outside"
        self.root.mkdir()
        self.outside.mkdir()

    def assertRefused(self, files, root=None):
        with self.assertRaises(OSError) as ctx:
            sitegen.write_files(files, root or self.root)
        self.assertEqual(ctx.exception.errno, errno.ELOOP)
        self.assertEqual(ctx.exception.strerror, "generated folder is a symlink")

    def test_linked_site_folder_is_refused_and_nothing_written(self):
        (self.root / SITE).symlink_to(self.outside, target_is_directory=True)
        self.assertRefused(FILES)
        self.assertEqual(_tree(self.outside), {})
        self.assertEqual(_tree(self.root), {"storefront-mockup": str(self.outside)})

    def test_linked_nested_folder_is_refused_before_any_write(self):
        (self.root / SITE).mkdir()
        (self.root / SITE / "hike").symlink_to(self.outside, target_is_directory=True)
        self.assertRefused(FILES)
        self.assertFalse((self.root / SITE / "index.html").exists())  # earlier file checked, not written
        self.assertFalse((self.root / SITE / "producers.json").exists())
        self.assertEqual(_tree(self.outside), {})

    def test_root_itself_may_be_a_link(self):
        link = self.root / "out-link"
        link.symlink_to(self.outside, target_is_directory=True)
        self.assertEqual(sitegen.write_files(FILES, link), list(FILES))
        for rel, data in FILES.items():
            self.assertEqual((self.outside / rel).read_bytes(), data)

    def test_missing_folders_are_created_as_real_folders(self):
        self.assertEqual(sitegen.write_files(FILES, self.root), list(FILES))
        for folder in (self.root / SITE, self.root / SITE / "hike"):
            self.assertTrue(folder.is_dir() and not folder.is_symlink(), folder)
        self.assertEqual((self.root / SITE / "hike" / "index.html").read_bytes(), b"<p>hike</p>\n")

    def test_dangling_folder_link_is_refused(self):
        missing = self.outside / "missing"
        (self.root / SITE).symlink_to(missing, target_is_directory=True)
        self.assertRefused(FILES)
        self.assertFalse(os.path.lexists(missing))
        self.assertEqual(_tree(self.outside), {})

    def test_only_selected_files_are_checked(self):
        (self.root / SITE).mkdir()
        (self.root / SITE / "hike").symlink_to(self.outside, target_is_directory=True)
        self.assertEqual(sitegen.write_files(FILES, self.root, only=[SITE + "index.html"]), [SITE + "index.html"])
        self.assertEqual(_tree(self.outside), {})
        self.assertRefused(FILES, self.root)  # selecting the linked path still refuses

    def test_out_cli_with_linked_subfolder_is_io_error(self):
        (self.root / SITE).mkdir()
        (self.root / SITE / "hike").symlink_to(self.outside, target_is_directory=True)
        code, out, err = _run(sitegen.main, "--out", str(self.root))
        self.assertEqual((code, out, err), (2, "", "sitegen: io error: OSError\n"))
        self.assertEqual(_tree(self.outside), {})
        self.assertFalse((self.root / SITE / "index.html").exists())

    def test_write_cli_with_linked_site_folder_is_io_error(self):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        moved = self.outside / "site"
        os.rename(repo.root / SITE, moved)
        (repo.root / SITE).symlink_to(moved, target_is_directory=True)
        (moved / "producers.json").write_bytes(b"{}")  # a real difference, so --write has work to do
        before = _tree(moved)
        code, out, err = _run(sitegen.main, "--write", "--repo", str(repo.root))
        self.assertEqual((code, out, err), (2, "", "sitegen: io error: OSError\n"))
        self.assertEqual(_tree(moved), before)

    def test_editor_write_into_linked_content_folder_is_refused(self):
        (self.outside / "store.json").write_bytes(b'{"name": "outside"}\n')
        (self.root / "hass").mkdir()
        (self.root / "hass" / "content").symlink_to(self.outside, target_is_directory=True)
        self.assertRefused({"hass/content/store.json": b"{}"})
        self.assertEqual(_tree(self.outside), {"store.json": b'{"name": "outside"}\n'})

    def test_escaping_key_is_refused_and_nothing_written(self):
        for bad in ("../escape.txt", SITE + "../../escape.txt", str(self.outside / "abs.txt"), ""):
            with self.subTest(key=bad):
                with self.assertRaises(ValueError) as ctx:
                    sitegen.write_files({SITE + "index.html": b"x", bad: b"y"}, self.root)
                self.assertEqual(str(ctx.exception), "generated path escapes root")
                self.assertEqual(_tree(self.root), {})
                self.assertEqual(_tree(self.outside), {})
                self.assertFalse(self.root.parent.joinpath("escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
