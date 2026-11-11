"""check-image refuses an unreadable picture with one fixed, path-free stderr line and exit 2 (no traceback, no score).
A scored pass/fail keeps its JSON and exit 0/1. Synthetic files only; no network."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HASS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HASS))
import house_style as hs  # noqa: E402

FIXED = "house_style: image could not be checked\n"
RENDERED = HASS.parent / "reports" / "hass" / "newitem-1" / "rendered"


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = hs.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CheckImageRefusal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def assertRefused(self, res, canary):
        code, out, err = res
        self.assertEqual((code, out, err), (2, "", FIXED))
        self.assertNotIn(canary, err)

    def test_missing_image_is_private_exit_two(self):
        p = self.dir / "canary-missing.jpg"
        self.assertRefused(run_main("check-image", str(p)), "canary")
        self.assertFalse(p.exists())

    def test_corrupt_and_empty_images_are_unscorable(self):
        for name, data in (("canary-bad.jpg", b"not a picture"), ("canary-empty.jpg", b"")):
            p = self.dir / name
            p.write_bytes(data)
            self.assertRefused(run_main("check-image", str(p)), "canary")
            self.assertEqual(p.read_bytes(), data)

    def test_directory_and_permission_errors_are_unscorable(self):
        self.assertRefused(run_main("check-image", str(self.dir)), "canary")
        p = self.dir / "canary-denied.jpg"
        p.write_bytes(b"x")
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError(13, "canary secret")):
            self.assertRefused(run_main("check-image", str(p)), "canary")

    def test_pillow_missing_is_fixed_exit_two(self):
        p = self.dir / "canary-a.jpg"
        p.write_bytes(b"x")
        with mock.patch.object(hs, "_pil", side_effect=hs.PillowMissing("canary pip")):
            self.assertRefused(run_main("check-image", str(p)), "canary")
            code, _, _ = run_main("check-text", "A plain jar of avocado honey.")
            self.assertIn(code, (0, 1))

    def test_scored_pass_and_fail_keep_exact_json(self):
        try:
            hs._pil()
        except hs.PillowMissing:
            self.skipTest("Pillow missing")
        for name, want in (("jar-white-sheet.jpg", 0), ("bag-red-cloth.jpg", 1)):
            p = RENDERED / name
            if not p.exists():
                self.skipTest("rendered fixture absent")
            api = hs.check_image(p.read_bytes())
            code, out, err = run_main("check-image", str(p))
            self.assertEqual((code, err), (want, ""))
            self.assertEqual(out, json.dumps(api, indent=1, ensure_ascii=False) + "\n")

    def test_direct_script_from_foreign_cwd(self):
        bad = self.dir / "canary-bad.jpg"
        bad.write_bytes(b"junk")
        for p in (self.dir / "canary-none.jpg", bad):
            r = subprocess.run([sys.executable, "-B", str(HASS / "house_style.py"), "check-image", str(p)],
                               cwd=self.dir, capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (2, "", FIXED))

    def test_unexpected_programmer_errors_not_swallowed(self):
        p = self.dir / "a.jpg"
        p.write_bytes(b"x")
        with mock.patch.object(hs, "check_image", side_effect=ValueError("bug")):
            with self.assertRaises(ValueError):
                run_main("check-image", str(p))


if __name__ == "__main__":
    unittest.main()
