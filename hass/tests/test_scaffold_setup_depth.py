"""RF1911-10: excessively nested --setup JSON is the fixed setup refusal, before any write."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hass.skills import scaffold

SETUP_REFUSAL = "--setup is a JSON list of"
BASE = ("new", "sample.x", "--op", "product.hide", "--label", "hide it")


def run(setup, root, *extra):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = scaffold.main([*BASE, "--setup", setup, "--root", root, *extra])
    return code, out.getvalue(), err.getvalue()


def files(root):
    return sorted(str(p) for p in Path(root).rglob("*"))


class SetupDepth(unittest.TestCase):
    def refused(self, setup):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run(setup, tmp)
            self.assertEqual(code, 2, err)
            self.assertEqual(out, "")
            self.assertIn(SETUP_REFUSAL, err)
            self.assertNotIn("Traceback", err)
            self.assertNotIn("Recursion", err)
            self.assertEqual(files(tmp), [])

    def test_deep_setup_is_fixed_exit_two_before_io(self):
        n = 100_000
        self.refused("[" * n + "]" * n)

    def test_deep_nested_setup_argument_is_also_refused(self):
        n = 100_000
        self.refused('[{"op": "product.hide", "args": ' + "[" * n + "]" * n + "}]")

    def test_empty_and_valid_shallow_setup_dry_run_controls(self):
        shallow = '[{"op": "product.hide", "args": {"id": "x"}}]'
        for setup in ("[]", shallow):
            with self.subTest(setup=setup), tempfile.TemporaryDirectory() as tmp:
                code, _out, err = run(setup, tmp, "--dry-run")
                self.assertEqual(code, 0, err)
                self.assertEqual(files(tmp), [])
        with tempfile.TemporaryDirectory() as tmp:
            code, _out, err = run("[not json", tmp, "--dry-run")
            self.assertEqual(code, 2)
            self.assertEqual(files(tmp), [])


if __name__ == "__main__":
    unittest.main()
