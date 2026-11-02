"""H01: sitegen/migration_check name I/O errors (exit 2) and never replace a symlinked target.

Every case runs on a throwaway repo copy; the checkout is only read.
Run: python3 -m unittest hass.tests.test_generated_io -v
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hass import migration_check, sitegen
from hass.tests.test_content import IsolatedRepo

SITE = "storefront-mockup/"


def _run(fn, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(list(args))
    return code, out.getvalue(), err.getvalue()


class GeneratedIoTests(unittest.TestCase):
    def setUp(self):
        self.repo = IsolatedRepo()
        self.addCleanup(self.repo.cleanup)
        self.root = self.repo.root

    def sitegen(self, *args):
        return _run(sitegen.main, *args, "--repo", str(self.root))

    def migration(self):
        return _run(migration_check.main, "--repo", str(self.root))

    def assertIoError(self, result, tool, exc_name):
        code, out, err = result
        self.assertEqual(code, 2, out + err)
        self.assertEqual(err, f"{tool}: io error: {exc_name}\n")  # one line: no traceback, path or bytes
        self.assertEqual(out, "")
        self.assertNotIn(str(self.root), err)

    def test_clean_copy_passes_both_tools(self):
        code, out, err = self.sitegen("--check")
        self.assertEqual((code, err), (0, ""), out)
        self.assertTrue(out.startswith("ok: 6 generated files match hass/content"), out)
        code, out, err = self.migration()
        self.assertEqual((code, err), (0, ""), out)
        self.assertTrue(out.endswith("migration check passed\n"), out)

    def test_missing_template_is_named_io_error(self):
        (self.root / "hass" / "templates" / "hike" / "index.html").unlink()
        for mode in ("--check", "--write"):
            with self.subTest(mode=mode):
                self.assertIoError(self.sitegen(mode), "sitegen", "FileNotFoundError")
        self.assertIoError(self.migration(), "migration_check", "FileNotFoundError")

    def test_corrupt_held_list_is_named_io_error(self):
        (self.root / SITE / "held-products.json").write_text("{bad", encoding="utf-8")
        self.assertIoError(self.migration(), "migration_check", "JSONDecodeError")

    def test_missing_held_list_or_baseline_is_named_io_error(self):
        for rel in (SITE + "held-products.json", "hass/content/migration-baseline.json"):
            with self.subTest(rel=rel):
                self.repo.cleanup()
                self.setUp()
                (self.root / rel).unlink()
                self.assertIoError(self.migration(), "migration_check", "FileNotFoundError")

    def test_corrupt_baseline_is_named_io_error(self):
        (self.root / "hass" / "content" / "migration-baseline.json").write_text("{bad", encoding="utf-8")
        self.assertIoError(self.migration(), "migration_check", "JSONDecodeError")

    def test_non_utf8_template_is_named_io_error(self):
        (self.root / "hass" / "templates" / "index.html").write_bytes(b'{"name": "\xff\xfe"}\n')
        self.assertIoError(self.sitegen("--check"), "sitegen", "UnicodeDecodeError")
        self.assertIoError(self.migration(), "migration_check", "UnicodeDecodeError")

    def test_non_utf8_content_is_content_invalid_naming_the_file(self):
        (self.root / "hass" / "content" / "store.json").write_bytes(b'{"name": "\xff\xfe"}\n')
        self.assertEqual(self.sitegen("--check"), (2, "", "content invalid:\n  store.json: not UTF-8 text\n"))
        self.assertEqual(
            self.migration(),
            (1, "MIGRATION CHECK FAILED:\n  content invalid: store.json: not UTF-8 text\n", ""),
        )

    def test_invalid_content_json_still_reported_as_content_invalid(self):
        (self.root / "hass" / "content" / "store.json").write_text("{bad", encoding="utf-8")
        code, out, err = self.sitegen("--check")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("content invalid:\n"), err)
        self.assertNotIn("io error", err)

    def test_symlinked_generated_target_is_never_replaced(self):
        with tempfile.TemporaryDirectory(prefix="hass-h01-outside-") as outside_dir:
            outside = Path(outside_dir) / "outside.json"
            outside.write_bytes(b"outside bytes\n")
            for rel in ("producers.json", "hike/index.html"):
                self.repo.cleanup()
                self.setUp()
                link = self.root / SITE / rel
                link.unlink()
                link.symlink_to(outside)
                with self.subTest(rel=rel):
                    self.assertIoError(self.sitegen("--write"), "sitegen", "OSError")
                    self.assertTrue(link.is_symlink())
                    self.assertEqual(outside.read_bytes(), b"outside bytes\n")
                    self.assertEqual(sorted(Path(outside_dir).iterdir()), [outside])  # no stray temp file

    def test_symlinked_target_in_out_dir_is_never_replaced(self):
        with tempfile.TemporaryDirectory(prefix="hass-h01-out-") as out_dir:
            outside = Path(out_dir) / "outside.js"
            outside.write_bytes(b"outside bytes\n")
            (Path(out_dir) / SITE).mkdir()
            link = Path(out_dir) / SITE / "producers.js"
            link.symlink_to(outside)
            code, out, err = _run(sitegen.main, "--out", out_dir, "--repo", str(self.root))
            self.assertEqual((code, err), (2, "sitegen: io error: OSError\n"), out)
            self.assertNotIn(out_dir, err)
            self.assertTrue(link.is_symlink())
            self.assertEqual(outside.read_bytes(), b"outside bytes\n")

    def test_real_difference_still_exits_1(self):
        (self.root / SITE / "producers.json").write_text("{}", encoding="utf-8")
        code, out, err = self.sitegen("--check")
        self.assertEqual((code, err), (1, ""), out)
        self.assertEqual(out, "generated files out of date (run python3 hass/sitegen.py --write):\n"
                              "  storefront-mockup/producers.json\n")
        code, out, err = self.migration()
        self.assertEqual((code, err), (1, ""), out)
        self.assertIn("MIGRATION CHECK FAILED:", out)

    def assertOnlySymlinkListed(self, rel, outside_dir):  # RF0050-1: --check agrees with --write on symlinks
        code, out, err = self.sitegen("--check")
        self.assertEqual((code, err), (1, ""), out)
        self.assertEqual(out, f"generated files out of date (run python3 hass/sitegen.py --write):\n  {SITE}{rel} (symlink)\n")
        self.assertNotIn(outside_dir, out)

    def test_symlinked_file_with_same_bytes_is_out_of_date_and_never_read(self):
        with tempfile.TemporaryDirectory(prefix="hass-h01-same-") as outside_dir:
            link, outside = self.root / SITE / "producers.json", Path(outside_dir) / "producers.json"
            data = link.read_bytes()
            link.rename(outside)
            link.symlink_to(outside)
            outside.chmod(0)  # a read would raise PermissionError (exit 2) instead of listing the path
            self.assertOnlySymlinkListed("producers.json", outside_dir)
            self.assertIoError(self.sitegen("--write"), "sitegen", "OSError")
            outside.chmod(0o600)
            self.assertEqual((link.is_symlink(), outside.read_bytes(), list(Path(outside_dir).iterdir())),
                             (True, data, [outside]))

    def test_symlinked_folder_with_same_bytes_is_out_of_date(self):
        with tempfile.TemporaryDirectory(prefix="hass-h01-dir-") as outside_dir:
            folder, outside = self.root / SITE / "hike", Path(outside_dir) / "hike" / "index.html"
            data = (folder / "index.html").read_bytes()
            folder.rename(outside.parent)
            folder.symlink_to(outside.parent, target_is_directory=True)
            self.assertOnlySymlinkListed("hike/index.html", outside_dir)
            self.assertIoError(self.sitegen("--write"), "sitegen", "OSError")
            self.assertEqual((folder.is_symlink(), outside.read_bytes(), list(outside.parent.iterdir())),
                             (True, data, [outside]))

    def test_dangling_symlink_is_out_of_date_without_exception(self):
        link = self.root / SITE / "community.json"
        link.unlink()
        link.symlink_to(self.root / "missing.json")
        self.assertOnlySymlinkListed("community.json", str(self.root))

    def test_symlinked_repo_root_still_passes(self):
        with tempfile.TemporaryDirectory(prefix="hass-h01-root-") as link_dir:
            link = Path(link_dir) / "repo"
            link.symlink_to(self.root, target_is_directory=True)
            code, out, err = _run(sitegen.main, "--check", "--repo", str(link))
            self.assertEqual((code, err, out[:32]), (0, "", "ok: 6 generated files match hass"), out)
            rel = SITE + "producers.json"  # the walk excludes the root link itself
            self.assertEqual(sitegen.diff_paths({rel: (self.root / rel).read_bytes()}, link), [])
