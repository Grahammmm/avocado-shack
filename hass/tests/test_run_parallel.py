"""Regression coverage for the CI runner's unittest discovery contract."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass.tests import run_parallel


class ParallelDiscoveryTests(unittest.TestCase):
    def test_discovery_matches_unittest(self):
        for relative in ("testother.py", "nested/test_nested.py"):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tests = root / "hass" / "tests"
                tests.mkdir(parents=True)
                for package in (root / "hass", tests, tests / "nested"):
                    package.mkdir(exist_ok=True)
                    (package / "__init__.py").touch()
                source = (
                    "import unittest\n"
                    "class Sample(unittest.TestCase):\n"
                    "    def test_included(self):\n"
                    "        self.fail('discovery sentinel')\n"
                )
                (tests / relative).write_text(source)
                # Keep a conventional module so the old runner can falsely pass.
                (tests / "test_sample.py").write_text(
                    "import unittest\nclass Control(unittest.TestCase):\n"
                    "    def test_control(self): pass\n"
                )
                shutil.copyfile(run_parallel.__file__, tests / "run_parallel.py")
                serial = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", "hass/tests", "-t", ".", "-v"],
                    cwd=root, capture_output=True, text=True,
                )
                parallel = subprocess.run(
                    [sys.executable, "hass/tests/run_parallel.py", "--jobs", "2"],
                    cwd=root, capture_output=True, text=True,
                )
                self.assertEqual(serial.returncode, 1, serial.stdout + serial.stderr)
                self.assertEqual(parallel.returncode, 1, parallel.stdout + parallel.stderr)
                self.assertIn("discovery sentinel", parallel.stdout + parallel.stderr)
                self.assertIn("test_control", parallel.stdout + parallel.stderr)
