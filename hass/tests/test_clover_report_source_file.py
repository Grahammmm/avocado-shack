"""RF1810-12: report product sources must be regular files; a FIFO must not block."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass.clover import cache, cli, reports
from hass.tests.test_clover_chat import seed
from hass.tests.test_clover_cli import CliCase

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = "hass/content/products.json"
CHILD = ("import sys\nfrom hass.clover import cache, reports\n"
         "try:\n    reports.read_inputs(sys.argv[1], sys.argv[2])\n"
         "except cache.CacheUnsafe as e:\n    print('unsafe', e)\n")


def worktree(root, make):
    wt = Path(root) / "wt"
    (wt / "hass/content").mkdir(parents=True)
    make(wt / PRODUCTS)
    return wt


class SourceFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir(mode=0o700)

    def test_fifo_product_source_refused_without_writer(self):
        wt = worktree(self.tmp.name, os.mkfifo)
        done = subprocess.run([sys.executable, "-B", "-c", CHILD, str(self.state), str(wt)],
                              cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "unsafe products"))

    def test_product_source_symlink_and_directory_refused(self):
        target = Path(self.tmp.name) / "linked.json"
        target.write_text('{"products": ["linked-secret"]}')
        for make in (lambda p: p.symlink_to(target), lambda p: p.mkdir()):
            wt = worktree(tempfile.mkdtemp(dir=self.tmp.name), make)
            with self.assertRaises(cache.CacheUnsafe) as caught:
                reports.read_inputs(self.state, wt)
            self.assertEqual(str(caught.exception), "products")

    def test_regular_product_source_preserves_semantics(self):
        wt = worktree(self.tmp.name, lambda p: p.write_text('{"products": []}', "utf-8"))
        (wt / PRODUCTS).chmod(0o644)
        self.assertEqual(reports.read_inputs(self.state, wt), ({"products": []}, {}))
        (wt / PRODUCTS).write_text("{not json", "utf-8")
        with self.assertRaises(json.JSONDecodeError):
            reports.read_inputs(self.state, wt)
        (wt / PRODUCTS).unlink()
        with self.assertRaises(FileNotFoundError):
            reports.read_inputs(self.state, wt)


class CliSourceTests(CliCase):
    def test_cli_unsafe_source_writes_no_reports(self):
        seed(self.state)
        target = self.root / "real.json"
        target.write_text('{"products": []}')
        wt = worktree(self.root, lambda p: p.symlink_to(target))
        (self.state / "config.json").write_text(json.dumps({"worktree": str(wt)}))
        with mock.patch.object(cli, "_token", side_effect=AssertionError("token")), \
                mock.patch.object(cli, "_client", side_effect=AssertionError("network")):
            code, out, stdout = self.run_cli("report", "mismatch")
        self.assertEqual(code, 1)
        self.assertNotIn("real.json", stdout)
        self.assertFalse((self.state / "clover/reports").exists())


if __name__ == "__main__":
    unittest.main()
