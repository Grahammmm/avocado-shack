"""RF1511-13: photo_polish_hermes.py reports malformed provider shapes as one redacted JSON line, no traceback."""
import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from hass import photo_polish_hermes as runner


class RunnerShapes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        self.src, self.out = os.path.join(d, "in.jpg"), os.path.join(d, "out.jpg")
        self.prompt, self.cache = os.path.join(d, "p.txt"), os.path.join(d, "cache.png")
        with open(self.prompt, "w") as fh:
            fh.write("polish")
        self._reset()
        self.addCleanup(self._restore)
        self._state = (os.getcwd(), list(sys.path), os.environ.get("OPENAI_IMAGE_MODEL"),
                       getattr(sys, "_hermes_pin_default_home", None), sys.modules.get("hermes_bootstrap"))

    def _restore(self):
        cwd, path, env, flag, boot = self._state
        os.chdir(cwd)
        sys.path[:] = path
        if env is None:
            os.environ.pop("OPENAI_IMAGE_MODEL", None)
        else:
            os.environ["OPENAI_IMAGE_MODEL"] = env
        if flag is None:
            if hasattr(sys, "_hermes_pin_default_home"):
                del sys._hermes_pin_default_home
        else:
            sys._hermes_pin_default_home = flag
        if boot is None:
            sys.modules.pop("hermes_bootstrap", None)
        else:
            sys.modules["hermes_bootstrap"] = boot

    def _reset(self):
        with open(self.out, "wb") as fh:
            fh.write(b"untouched")
        with open(self.cache, "wb") as fh:
            fh.write(b"synthetic image")

    def run_runner(self, result, argv_model="openai-codex:tier", argv=None):
        provider = types.SimpleNamespace(generate=lambda *a, **k: result)
        module = types.SimpleNamespace(OpenAICodexImageGenProvider=lambda: provider)
        out, err = io.StringIO(), io.StringIO()
        args = argv or ["r", self.tmp.name, argv_model, self.src, self.out, self.prompt]
        if argv is None:
            args = ["r", self.tmp.name, argv_model, self.src, self.out, self.prompt]
            args = [args[0], args[1], args[2], *args[3:]]
        with mock.patch.dict(sys.modules, {"hermes_bootstrap": types.ModuleType("hermes_bootstrap")}), \
                mock.patch.object(importlib, "import_module", return_value=module), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = runner.main(args)
        return status, out.getvalue(), err.getvalue()

    def read(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def good(self, **kw):
        res = {"success": True, "modality": "image", "image": self.cache, "model": "m", "provider": "p",
               "extra": {"pixel_size": "1024x1024", "imagegen_request_id": "r1"}}
        res.update(kw)
        return res

    def assert_failed(self, result, code="failed"):
        status, out, err = self.run_runner(result)
        self.assertEqual(status, 1)
        self.assertEqual(out.splitlines(), [json.dumps({"code": code, "ok": False})])
        self.assertEqual(err, "")

    def test_unhashable_error_type_is_redacted_failed(self):
        for kind in ([], ["secret"], {"a": "secret"}, None, 7, "unknown"):
            with self.subTest(kind=kind):
                self.assert_failed({"success": False, "error_type": kind})
                self.assertEqual(self.read(self.out), b"untouched")

    def test_invalid_extra_is_refused_before_output_mutation(self):
        for extra in (["x"], [], "text", "", 5, 0, False, True):
            with self.subTest(extra=extra), mock.patch.object(runner.shutil, "copyfile") as cp, \
                    mock.patch.object(runner.os, "unlink") as un:
                self._reset()
                self.assert_failed(self.good(extra=extra))
                cp.assert_not_called()
                un.assert_not_called()
                self.assertEqual(self.read(self.out), b"untouched")
                self.assertTrue(os.path.exists(self.cache))

    def test_valid_metadata_success_copies_and_removes_cache(self):
        status, out, err = self.run_runner(self.good())
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out), {"model": "m", "ok": True, "pixel_size": "1024x1024", "provider": "p",
                                           "request": "r1"})
        self.assertEqual(err, "")
        self.assertEqual(self.read(self.out), b"synthetic image")
        self.assertFalse(os.path.exists(self.cache))
        for extra in ({"extra": None}, {"extra": {}}):
            self._reset()
            status, out, _ = self.run_runner(self.good(**extra))
            self.assertEqual(status, 0)
            data = json.loads(out)
            self.assertEqual((data["pixel_size"], data["request"]), (None, None))
        res = self.good()
        del res["extra"]
        self._reset()
        self.assertEqual(self.run_runner(res)[0], 0)

    def test_known_errors_and_edit_only_controls(self):
        for kind, code in runner.CODES.items():
            self.assert_failed({"success": False, "error_type": kind}, code)
        self.assert_failed("not a dict")
        self._reset()
        self.assert_failed(self.good(modality="text"), "not-edit")
        self.assertEqual(self.read(self.out), b"untouched")
        self.assertTrue(os.path.exists(self.cache))
        status, out, err = self.run_runner(self.good(), argv=["r"])
        self.assertEqual((status, out, err), (2, json.dumps({"code": "usage", "ok": False}) + "\n", ""))
        status, out, err = self.run_runner(self.good(), argv_model="other:x")
        self.assertEqual((status, out, err), (2, json.dumps({"code": "route", "ok": False}) + "\n", ""))
        self.assert_failed(self.good(image="/nonexistent/none.png"), "io")

    def test_runner_tests_restore_process_state(self):
        cwd, path = os.getcwd(), list(sys.path)
        self.run_runner(self.good())
        self.assertEqual(os.environ.get("OPENAI_IMAGE_MODEL"), "tier")
        self._restore()
        self.assertEqual((os.getcwd(), sys.path), (cwd, path))
        self.assertNotEqual(os.environ.get("OPENAI_IMAGE_MODEL"), "tier")
        self.assertNotIn("hermes_bootstrap", sys.modules)


if __name__ == "__main__":
    unittest.main()
