"""RF2150-13: design_preview admits an artifact only with the exact eight-byte PNG signature (format ID only)."""

import os, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import design_preview as dp
from hass.tests.test_design_preview import OK_CHECKS, PNG, FakePreviewer, RepoCase

SIG = b"\x89PNG\r\n\x1a\n"


class SignatureFake(FakePreviewer):
    """Healthy fake whose artifacts carry ``bad`` bytes at the chosen capture call (phone or desktop)."""
    def __init__(self, bad, call=0, desktop=False):
        super().__init__()
        self.bad, self.call, self.desktop = bad, call, desktop

    def capture(self, files, target, out_png):
        index = len(self.calls)
        result = super().capture(files, target, out_png)
        if index == self.call:
            Path(result["desktopPng" if self.desktop else "png"]).write_bytes(self.bad)
        return result


class PrivatePngTests(unittest.TestCase):
    def path(self, data, mode=0o600):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        path = Path(holder.name, "a.png")
        path.write_bytes(data)
        os.chmod(path, mode)
        return path

    def test_empty_text_short_and_corrupt_headers_are_refused(self):
        bad = [b"", b"not a png!", b"\xff\xd8\xff\xe0" + b"\0" * 8, b"\x89png\r\n\x1a\n"]
        bad += [SIG[:n] for n in range(1, 8)]
        bad += [SIG[:i] + b"X" + SIG[i + 1:] + b"\0" * 8 for i in range(8)]
        for data in bad:
            path = self.path(data)
            self.assertIsNone(dp._private_png(str(path), path), data)

    def test_exact_signature_is_admitted_with_bounded_read(self):
        path = self.path(PNG + b"arbitrary tail")
        sizes = []
        real = os.read
        with mock.patch.object(os, "read", lambda fd, n: sizes.append(n) or real(fd, n)):
            self.assertEqual(dp._private_png(str(path), path), str(path))
        self.assertEqual(sizes, [8])

    def test_type_and_mode_admission_preserved_and_fd_closed(self):
        path = self.path(PNG, mode=0o644)
        self.assertIsNone(dp._private_png(str(path), path))
        self.assertIsNone(dp._private_png(None, path))
        self.assertIsNone(dp._private_png(str(path.parent), path.parent))
        link = path.parent / "link.png"
        link.symlink_to(path)
        os.chmod(path, 0o600)
        self.assertIsNone(dp._private_png(str(link), link))
        seen = []
        real = os.open
        with mock.patch.object(os, "open", lambda *a, **k: seen.append(real(*a, **k)) or seen[-1]):
            self.assertEqual(dp._private_png(str(path), path), str(path))
            with mock.patch.object(os, "read", side_effect=OSError("boom")):
                self.assertIsNone(dp._private_png(str(path), path))
        self.assertEqual(len(seen), 2)
        for fd in seen:
            with self.assertRaises(OSError):
                os.fstat(fd)


class RunTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})

    def test_invalid_signature_fails_each_capture_position(self):
        for call in range(4):
            for desktop in (False, True):
                for bad in (b"", b"plain text"):
                    out = self.tmp / f"o{call}{int(desktop)}{len(bad)}"
                    fake = SignatureFake(bad, call, desktop)
                    code, doc = self.run_fake(fake, out=out)
                    self.assertEqual(code, 1)
                    self.assertEqual(doc["result"], "preview-failed")
                    self.assertEqual(len(fake.calls), 4)
                    errors = [c["error"] for c in doc["captures"]]
                    want = "missing desktop png" if desktop else "missing png"
                    self.assertEqual(errors[call], want)
                    self.assertEqual(errors.count(None), 3)
                    bad_path = Path(fake.calls[call][2])
                    if desktop:
                        bad_path = bad_path.with_name(bad_path.stem + "-desktop.png")
                    self.assertEqual(bad_path.read_bytes(), bad)

    def test_false_check_diagnostic_still_wins_over_bad_bytes(self):
        fake = SignatureFake(b"", 0)
        fake.plan = {0: "check-fail"}
        code, doc = self.run_fake(fake)
        self.assertEqual(code, 1)
        self.assertTrue(doc["captures"][0]["error"].startswith("check failed"))


if __name__ == "__main__":
    unittest.main()
