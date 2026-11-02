"""RF0110-5 tests: a screenshot run whose last stdout line is not ``{"checks": {<str>: <bool>, ...}}`` is a failed run.

Reuses the RF1058-10 viewport setup (fake ``node``, real loopback preview server). The fake here also prints a raw
``stdout`` text from the plan when given, so non-JSON and multi-line output can be tried.
"""

import json, sys  # noqa: E401

from hass.tests import test_preview_viewports as vp
from hass.tests.test_editor import EditorTestCase

RAW_NODE = vp.FAKE_NODE.replace('print(json.dumps({{"checks": plan["checks"]}}))',
                                'print(plan["stdout"] if "stdout" in plan else json.dumps({{"checks": plan["checks"]}}))')
assert RAW_NODE != vp.FAKE_NODE
BAD = {"checks null": {"checks": None}, "checks list": {"checks": []}, "checks empty": {"checks": {}},
       "checks int value": {"checks": {"a": 1}}, "checks string value": {"checks": {"a": "true"}},
       "checks one non-bool": {"checks": {**vp.PASS, "noPosts": None}}, "not JSON": {"stdout": "done"},
       "JSON list line": {"stdout": "[1]"}, "no checks key": {"stdout": "{}"}, "empty stdout": {"stdout": ""},
       "too deep": {"stdout": "[" * 100000 + "]" * 100000}}


class ChecksShapeTests(EditorTestCase):
    capture, assertPrivatePng = vp.ViewportTests.capture, vp.ViewportTests.assertPrivatePng

    def setUp(self):
        vp.ViewportTests.setUp(self)
        (self.tmp / "bin" / "node").write_text(RAW_NODE.format(python=sys.executable, log=str(self.log),
                                                              plan=str(self.plan), png=vp.PNG))

    def fresh(self):
        for leftover in (self.log, self.out, self.desktop_png):
            leftover.unlink(missing_ok=True)

    def test_bad_desktop_checks_keep_the_phone_result(self):
        for label, plan in BAD.items():
            with self.subTest(label):
                self.fresh()
                result, calls, _server = self.capture({"phone": {"checks": vp.PASS}, "desktop": plan})
                self.assertEqual(result, {"ok": False, "png": str(self.out), "checks": vp.PASS,
                                          "error": "desktop: bad checks output", "desktopPng": None})
                self.assertPrivatePng(self.out)
                self.assertFalse(self.desktop_png.exists())
                self.assertEqual([c["viewport"] for c in calls], ["phone", "desktop"])

    def test_bad_phone_checks_are_a_named_failure_and_skip_desktop(self):
        for viewports in (vp.preview.VIEWPORTS, ("phone",)):
            for label, plan in BAD.items():
                with self.subTest(label, viewports=viewports):
                    self.fresh()
                    result, calls, _server = self.capture({"phone": plan, "desktop": {"checks": vp.PASS}}, viewports)
                    self.assertEqual(result, {"ok": False, "png": None, "checks": {}, "error": "bad checks output"})
                    self.assertEqual([c["viewport"] for c in calls], ["phone"])
                    self.assertFalse(self.out.exists() or self.desktop_png.exists())

    def test_only_the_last_line_counts(self):
        line = json.dumps({"checks": vp.PASS})
        result, _calls, _server = self.capture({"phone": {"stdout": "loading\n" + line + "\n\n"},
                                                "desktop": {"stdout": line + "\nnot json"}})
        self.assertEqual(result, {"ok": False, "png": str(self.out), "checks": vp.PASS,
                                  "error": "desktop: bad checks output", "desktopPng": None})
        self.fresh()
        result, _calls, _server = self.capture({"phone": {"stdout": "a\n" + line}, "desktop": {"stdout": "b\n" + line}})
        self.assertEqual((result["ok"], result["error"], result["desktopPng"]), (True, None, str(self.desktop_png)))
        self.assertEqual(result["checks"], {**vp.PASS, **vp.desktop(vp.PASS)})

    def test_exit_zero_without_png_keeps_todays_failure_text(self):
        node = self.tmp / "bin" / "node"
        node.write_text(node.read_text().replace('open(os.environ["OUT"], "wb")', 'open(os.devnull, "wb")'))
        result, calls, _server = self.capture({"phone": {"stdout": "rendered nothing"}, "desktop": {"checks": vp.PASS}})
        self.assertEqual(result, {"ok": False, "png": None, "checks": {}, "error": "rendered nothing"})
        self.assertEqual([c["viewport"] for c in calls], ["phone"])
        self.fresh()
        result, _calls, _server = self.capture({"phone": {"stdout": ""}}, ("phone",))
        self.assertEqual(result["error"], "no output")
