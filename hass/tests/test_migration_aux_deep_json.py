"""RF0010-13: decoder-excessive migration auxiliary JSON is a private exit-2 refusal, not a traceback.

Every case edits a throwaway IsolatedRepo; the checkout is only read.
Run: python3 -B -m unittest hass.tests.test_migration_aux_deep_json -v
"""

import contextlib
import io
import json
import subprocess
import sys
import unittest
from unittest import mock

from hass import migration_check
from hass.content_model import REPO_ROOT
from hass.tests.test_content import IsolatedRepo

FILES = {
    "baseline": "hass/content/migration-baseline.json",
    "held": "storefront-mockup/held-products.json",
    "preview": "storefront-mockup/hiking-preview.json",
}
DEPTH = 10000
ERR = "migration_check: io error: ValueError\n"


def _deep(kind):
    return "[" * DEPTH + "]" * DEPTH if kind == "array" else '{"a":' * DEPTH + "1" + "}" * DEPTH


def _snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode)
            for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


def _main(root):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = migration_check.main(["--repo", str(root)])
    return code, out.getvalue(), err.getvalue()


class DeepAuxJsonTests(unittest.TestCase):
    def _repo(self):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        return repo.root

    def test_each_auxiliary_decoder_rejects_real_deep_arrays_and_objects(self):
        for name, rel in FILES.items():
            for kind in ("array", "object"):
                with self.subTest(file=name, kind=kind):
                    root = self._repo()
                    (root / rel).write_text(_deep(kind), "utf-8")
                    before = _snapshot(root)
                    code, out, err = _main(root)
                    self.assertEqual((code, out, err), (2, "", ERR))
                    self.assertEqual(_snapshot(root), before)
                    proc = subprocess.run([sys.executable, "-B", "hass/migration_check.py", "--repo", str(root)],
                                          cwd=REPO_ROOT, capture_output=True, text=True, timeout=300)
                    self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (2, "", ERR))
                    self.assertNotIn(str(root), proc.stderr)

    def test_deep_baseline_stops_before_content_loading(self):
        root = self._repo()
        (root / FILES["baseline"]).write_text(_deep("array"), "utf-8")
        with mock.patch.object(migration_check, "load_and_validate") as load, \
                mock.patch.object(migration_check, "render") as render:
            self.assertEqual(_main(root), (2, "", ERR))
        load.assert_not_called()
        render.assert_not_called()

    def test_only_decoder_recursion_is_translated(self):
        path = REPO_ROOT / FILES["held"]
        with mock.patch.object(migration_check.json, "loads", side_effect=RecursionError):
            with self.assertRaises(ValueError) as cm:
                migration_check._read_aux_json(path)
        self.assertIsNone(cm.exception.__cause__)
        self.assertTrue(cm.exception.__suppress_context__)
        with mock.patch.object(migration_check, "_held_ids", side_effect=RecursionError):
            with self.assertRaises(RecursionError):
                migration_check.run_checks(REPO_ROOT)

    def test_shape_and_read_failure_channels_preserved(self):
        root = self._repo()
        (root / FILES["baseline"]).write_text("[]", "utf-8")
        (root / FILES["held"]).write_text(_deep("array"), "utf-8")
        code, out, err = _main(root)
        self.assertEqual((code, out, err), (1, "MIGRATION CHECK FAILED:\n  baseline is not an object\n", ""))
        for rel, data in ((FILES["held"], b"\xff"), (FILES["preview"], b"{")):
            with self.subTest(rel=rel):
                root = self._repo()
                (root / rel).write_bytes(data)
                code, out, err = _main(root)
                self.assertEqual((code, out), (2, ""))
                want = "JSONDecodeError" if data == b"{" else "UnicodeDecodeError"
                self.assertEqual(err, f"migration_check: io error: {want}\n")
        root = self._repo()
        (root / FILES["held"]).unlink()
        self.assertEqual(_main(root), (2, "", "migration_check: io error: FileNotFoundError\n"))

    def test_untouched_control_and_absent_preview_pass(self):
        root = self._repo()
        code, out, err = _main(root)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("migration check passed", out)
        (root / FILES["preview"]).unlink()
        code2, out2, err2 = _main(root)
        self.assertEqual((code2, out2, err2), (0, out, ""))
        self.assertEqual(json.loads((root / FILES["held"]).read_text("utf-8")),
                         json.loads((REPO_ROOT / FILES["held"]).read_text("utf-8")))


if __name__ == "__main__":
    unittest.main()
