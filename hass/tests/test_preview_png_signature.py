"""RF0240-13 tests: the shared Previewer admits a screenshot only when the capture child wrote the eight PNG signature bytes.

Offline: the server lifecycle, the site copy and the node child are in-process fakes (no socket, subprocess, browser or
model); the capture, byte admission and private-write code are real and write real scratch files. This is signature
identification only, not decoding or integrity checking."""

import contextlib, json, stat, tempfile, unittest  # noqa: E401
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from hass import preview

SIG = b"\x89PNG\r\n\x1a\n"
GOOD = SIG + b"synthetic suffix"
PASS = {"productShown": True, "description": True}
TARGET = {"kind": "product", "id": "p1", "name": "x", "status": "active", "description": "d"}
CANARY = b"CANARY-private-payload"
BAD = ([b"", b"not a png " + CANARY, b"\xff\xd8\xff\xe0" + b"JFIF" + CANARY]
       + [SIG[:n] for n in range(1, 8)]
       + [SIG[:i] + bytes([SIG[i] ^ 1]) + SIG[i + 1:] + b"rest" for i in range(8)])


class FakeServer:
    pid = 4242

    def __init__(self, log):
        self.log = log

    def poll(self):
        return None

    def terminate(self):
        self.log.append("terminate")

    def wait(self, timeout=None):
        self.log.append("wait")


class PngSignatureTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory(prefix="hass-png-sig-")
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        (self.root / "temp").mkdir()
        self.out = self.root / "shots" / "c1.png"
        self.desktop_out = self.root / "shots" / "c1-desktop.png"
        self.server_log, self.runs, self.writes = [], [], []

    def capture(self, plan, viewports=preview.VIEWPORTS, on_checks=None):
        """plan: viewport -> (bytes to write or None, stdout dict or None, exit code)."""
        def fake_run(argv, env, **_kw):
            self.runs.append(env["VIEWPORT"])
            data, stdout, code = plan[env["VIEWPORT"]]
            if data is not None:
                Path(env["OUT"]).write_bytes(data)
            self.last_out = env["OUT"]
            return CompletedProcess(argv, code, json.dumps(stdout) if stdout is not None else "", "child broke" if code else "")

        def spy_write(path, data):
            self.writes.append((Path(path), data))
            return real_write(path, data)

        real_write, real_checks = preview._write_private, preview._checks
        previewer = preview.Previewer(self.root, {"PATH": "", "HOME": str(self.root)}, viewports)
        patches = [mock.patch.object(tempfile, "tempdir", str(self.root / "temp")),
                   mock.patch.object(preview.Previewer, "_copy_site", lambda s, tmp, f, a=None: tmp / "site"),
                   mock.patch.object(preview, "_free_port", lambda: 1),
                   mock.patch.object(preview, "_get_ok", lambda port: True),
                   mock.patch.object(preview.subprocess, "Popen", lambda *a, **k: FakeServer(self.server_log)),
                   mock.patch.object(preview.subprocess, "run", fake_run),
                   mock.patch.object(preview, "_write_private", spy_write)]
        if on_checks:
            patches.append(mock.patch.object(preview, "_checks", lambda out: (on_checks(), real_checks(out))[1]))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            result = previewer.capture({}, TARGET, self.out)
        self.assertEqual(self.server_log, ["terminate", "wait"])  # always finalized
        self.assertEqual(list((self.root / "temp").iterdir()), [])  # temp copy removed
        return result

    def test_bad_phone_png_fails_before_desktop_and_preserves_old_output(self):
        self.out.parent.mkdir(parents=True)
        self.out.write_bytes(b"old phone shot")
        for bad in BAD:
            with self.subTest(bad=bad[:12]):
                self.runs.clear()
                self.writes.clear()
                self.server_log.clear()
                result = self.capture({"phone": (bad, {"checks": PASS}, 0), "desktop": (GOOD, {"checks": PASS}, 0)})
                self.assertEqual(result, {"ok": False, "png": None, "checks": {}, "error": "bad screenshot PNG"})
                self.assertEqual(self.runs, ["phone"])
                self.assertEqual(self.writes, [])
                self.assertEqual(self.out.read_bytes(), b"old phone shot")
                self.assertFalse(self.desktop_out.exists())

    def test_bad_desktop_png_preserves_good_phone_only(self):
        self.desktop_out.parent.mkdir(parents=True)
        self.desktop_out.write_bytes(b"old desktop shot")
        for bad in BAD:
            with self.subTest(bad=bad[:12]):
                self.runs.clear()
                self.writes.clear()
                self.server_log.clear()
                result = self.capture({"phone": (GOOD, {"checks": PASS}, 0), "desktop": (bad, {"checks": PASS}, 0)})
                self.assertEqual(result, {"ok": False, "png": str(self.out), "checks": PASS,
                                          "error": "desktop: bad screenshot PNG", "desktopPng": None})
                self.assertEqual(self.runs, ["phone", "desktop"])
                self.assertEqual(self.out.read_bytes(), GOOD)
                self.assertEqual(self.desktop_out.read_bytes(), b"old desktop shot")

    def test_same_validated_bytes_are_written(self):
        mutated = []
        mutate = lambda: mutated.append(Path(self.last_out).write_bytes(b"changed after admission"))  # noqa: E731
        result = self.capture({"phone": (GOOD, {"checks": PASS}, 0)}, ("phone",), on_checks=mutate)
        self.assertTrue(result["ok"])
        self.assertEqual(mutated, [len(b"changed after admission")])  # the seam really ran after admission
        self.assertEqual(self.writes, [(self.out, GOOD)])
        self.assertEqual(self.out.read_bytes(), GOOD)

    def test_signature_only_control_and_phone_only_shape(self):
        both = self.capture({"phone": (GOOD, {"checks": PASS}, 0), "desktop": (GOOD, {"checks": PASS}, 0)})
        self.assertEqual(both, {"ok": True, "png": str(self.out),
                                "checks": {**PASS, **{f"desktop:{k}": v for k, v in PASS.items()}},
                                "error": None, "desktopPng": str(self.desktop_out)})
        for path in (self.out, self.desktop_out):
            self.assertEqual(path.read_bytes(), GOOD)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.server_log.clear()
        self.desktop_out.unlink()
        self.out.unlink()
        phone = self.capture({"phone": (GOOD, {"checks": PASS}, 0)}, ("phone",))
        self.assertEqual(phone, {"ok": True, "png": str(self.out), "checks": PASS, "error": None})
        self.assertFalse(self.desktop_out.exists())

    def test_valid_png_false_checks_and_malformed_checks_preserve_diagnostics(self):
        failing = {"productShown": False, "description": True}
        result = self.capture({"phone": (GOOD, {"checks": failing}, 0), "desktop": (GOOD, {"checks": PASS}, 0)})
        self.assertEqual(result, {"ok": False, "png": str(self.out), "checks": failing,
                                  "error": "check failed: productShown", "desktopPng": None})
        self.assertEqual(self.runs, ["phone"])
        self.runs.clear()
        self.server_log.clear()
        self.assertEqual(self.capture({"phone": (GOOD, {"checks": "nope"}, 0)}),
                         {"ok": False, "png": None, "checks": {}, "error": "bad checks output"})
        self.runs.clear()
        self.server_log.clear()
        result = self.capture({"phone": (GOOD, {"checks": PASS}, 0), "desktop": (None, None, 3)})
        self.assertEqual((result["ok"], result["png"], result["checks"], result["desktopPng"], result["error"]),
                         (False, str(self.out), PASS, None, "desktop: child broke"))
        self.assertEqual(self.out.read_bytes(), GOOD)

    def test_no_private_payload_diagnostic(self):
        for viewport_plan in ({"phone": (BAD[1], {"checks": PASS}, 0)},
                              {"phone": (GOOD, {"checks": PASS}, 0), "desktop": (BAD[1], {"checks": PASS}, 0)}):
            self.server_log.clear()
            result = self.capture(viewport_plan)
            self.assertNotIn(CANARY.decode(), json.dumps(result))
            self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
