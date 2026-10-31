"""RF1058-10 tests: the private preview checks phone then desktop width against one loopback preview server.

A fake ``node`` first on the PATH given in ``env`` (no Chromium) records each call (VIEWPORT, PREVIEW_URL, a GET of the
live server), writes a tiny PNG to OUT and prints the checks a per-viewport plan file chooses; the real
community-server.py serves a temp writer repo. The real-Chromium case is skipped unless PLAYWRIGHT_MODULE is set.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import preview
from hass.tests import test_preview
from hass.tests.test_editor import EditorTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
PASS = {"productShown": True, "description": True, "noPageErrors": True, "noPosts": True}
TARGET = {"kind": "product", "id": "photo-product-001", "name": "x", "status": "active", "description": "d"}
FAKE_NODE = """#!{python}
import json, os, sys, urllib.request
url = os.environ["PREVIEW_URL"]
with open({log!r}, "a") as log:
    log.write(json.dumps({{"viewport": os.environ.get("VIEWPORT"), "url": url,
                          "status": urllib.request.urlopen(url + "/", timeout=5).status}}) + "\\n")
plan = json.load(open({plan!r}))[os.environ["VIEWPORT"]]
if plan.get("exit"):
    print("render broke", file=sys.stderr)
    sys.exit(plan["exit"])
open(os.environ["OUT"], "wb").write({png!r})
print(json.dumps({{"checks": plan["checks"]}}))
"""


def desktop(checks):
    return {f"desktop:{name}": passed for name, passed in checks.items()}


class ViewportTests(EditorTestCase):
    def setUp(self):
        self.writer = self.repo()
        holder = tempfile.TemporaryDirectory(prefix="hass-viewports-")
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)
        for name in ("bin", "temp"):
            (self.tmp / name).mkdir()
        self.plan, self.log = self.tmp / "plan.json", self.tmp / "calls.jsonl"
        node = self.tmp / "bin" / "node"
        node.write_text(FAKE_NODE.format(python=sys.executable, log=str(self.log), plan=str(self.plan), png=PNG))
        node.chmod(0o700)
        self.env = {"PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", "HOME": str(self.tmp)}
        self.out, self.desktop_png = (self.tmp / "shots" / n for n in ("c1-proposal.png", "c1-proposal-desktop.png"))

    def capture(self, plan, viewports=preview.VIEWPORTS):
        """Run one capture; check the server is stopped and the temp copy gone; return (result, calls, server)."""
        self.plan.write_text(json.dumps(plan))
        previewer = preview.Previewer(self.writer.wt, self.env, viewports)
        with mock.patch.object(tempfile, "tempdir", str(self.tmp / "temp")):
            result = previewer.capture({}, TARGET, self.out)
        server = previewer.last_server
        if server is not None:
            with self.assertRaises(ProcessLookupError):
                os.kill(server["pid"], 0)
        self.assertEqual(list((self.tmp / "temp").iterdir()), [])
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls, server

    def assertPrivatePng(self, path):
        self.assertEqual(Path(path).read_bytes(), PNG)
        self.assertEqual(stat.S_IMODE(Path(path).stat().st_mode), 0o600)

    def test_both_viewports_pass_against_one_server(self):
        result, calls, server = self.capture({"phone": {"checks": PASS}, "desktop": {"checks": PASS}})
        self.assertEqual(result, {"ok": True, "png": str(self.out), "checks": {**PASS, **desktop(PASS)},
                                  "error": None, "desktopPng": str(self.desktop_png)})
        self.assertPrivatePng(self.out)
        self.assertPrivatePng(self.desktop_png)
        url = f"http://127.0.0.1:{server['port']}"
        self.assertEqual(calls, [{"viewport": "phone", "url": url, "status": 200},
                                 {"viewport": "desktop", "url": url, "status": 200}])

    def test_desktop_check_failure_fails_the_preview(self):
        result, calls, _server = self.capture({"phone": {"checks": PASS},
                                               "desktop": {"checks": {"product-card": False}}})
        self.assertEqual((result["ok"], result["error"], result["png"]),
                         (False, "check failed: desktop:product-card", str(self.out)))
        self.assertEqual(result["checks"], {**PASS, "desktop:product-card": False})
        self.assertPrivatePng(self.out)
        self.assertEqual([c["viewport"] for c in calls], ["phone", "desktop"])

    def test_desktop_check_not_exactly_true_fails(self):
        result, _calls, _server = self.capture({"phone": {"checks": PASS},
                                                "desktop": {"checks": {**PASS, "noPosts": "yes"}}})
        self.assertEqual((result["ok"], result["error"]), (False, "check failed: desktop:noPosts"))

    def test_desktop_process_failure_keeps_the_phone_png(self):
        result, calls, _server = self.capture({"phone": {"checks": PASS}, "desktop": {"exit": 1}})
        self.assertEqual(result, {"ok": False, "png": str(self.out), "checks": PASS,
                                  "error": "desktop: render broke", "desktopPng": None})
        self.assertPrivatePng(self.out)
        self.assertFalse(self.desktop_png.exists())
        self.assertEqual([c["viewport"] for c in calls], ["phone", "desktop"])

    def test_phone_process_failure_skips_desktop(self):
        result, calls, _server = self.capture({"phone": {"exit": 1}, "desktop": {"checks": PASS}})
        self.assertEqual(result, {"ok": False, "png": None, "checks": {}, "error": "render broke"})
        self.assertEqual([c["viewport"] for c in calls], ["phone"])
        self.assertFalse(self.out.exists() or self.desktop_png.exists())

    def test_phone_check_failure_skips_desktop(self):
        result, calls, _server = self.capture({"phone": {"checks": {**PASS, "productShown": False}},
                                               "desktop": {"checks": PASS}})
        self.assertEqual(result, {"ok": False, "png": str(self.out), "checks": {**PASS, "productShown": False},
                                  "error": "check failed: productShown", "desktopPng": None})
        self.assertEqual([c["viewport"] for c in calls], ["phone"])
        self.assertFalse(self.desktop_png.exists())

    def test_phone_only_keeps_todays_result(self):
        result, calls, _server = self.capture({"phone": {"checks": PASS}}, viewports=("phone",))
        self.assertEqual(result, {"ok": True, "png": str(self.out), "checks": PASS, "error": None})
        self.assertEqual([c["viewport"] for c in calls], ["phone"])
        self.assertFalse(self.desktop_png.exists())

    def test_unsupported_viewports_are_refused_without_raising(self):
        for viewports in (("tablet",), ("desktop",), ("desktop", "phone"), ("phone", "phone"), (), "phone"):
            with self.subTest(viewports=viewports):
                result, calls, server = self.capture({}, viewports=viewports)
                self.assertEqual((result["ok"], result["png"], result["checks"], calls, server),
                                 (False, None, {}, [], None))
                self.assertTrue(result["error"].startswith("ValueError: unsupported viewports"), result["error"])
                self.assertLessEqual(len(result["error"]), 200)


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class RealBrowserViewportTests(test_preview.BrowserCase):
    def test_product_edit_passes_phone_and_desktop(self):
        draft, _reply = self.propose("desc")
        result = self.previewer.results[-1]
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        png = Path(result["desktopPng"])
        self.assertEqual(png.name, f"{draft['change_id']}-proposal-desktop.png")
        data = png.read_bytes()
        self.assertEqual((data[:8], int.from_bytes(data[16:20], "big")), (test_preview.PNG_SIGNATURE, 1280))
        self.assertEqual(stat.S_IMODE(png.stat().st_mode), 0o600)
        self.assertEqual(int.from_bytes(Path(result["png"]).read_bytes()[16:20], "big"), 390)

