"""RF1201-10: item-standard report inputs with decoded surrogate code points are refused (exit 2) before any write."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import itemstd

REPO = Path(__file__).resolve().parents[2]
SENTINEL = '{"sentinel": true}\n'
BAD = ("\\ud800", "\\udbff", "\\udc00", "\\udfff")


def products_text(name="Synthetic", extra=""):
    return '{"schemaVersion": 1, %s"products": [{"id": "p1", "name": "%s", "status": "hidden"}]}' % (extra, name)


def makers_text(name="Synthetic", key="m1", extra=""):
    return '{"schemaVersion": 1, %s"makers": {"%s": {"name": "%s"}}}' % (extra, key, name)


class SurrogateBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "repo"
        (self.root / "hass" / "style").mkdir(parents=True)
        (self.root / "hass" / "content").mkdir()
        (self.root / "reports" / "hass").mkdir(parents=True)
        for rel in ("__init__.py", "voice.py", "itemstd.py", "style/item-standard.json"):
            shutil.copy(REPO / "hass" / rel, self.root / "hass" / rel)
        self.content = self.root / "hass" / "content"
        self.report = self.root / "reports" / "hass" / "catalog-gaps.json"

    def put(self, products=None, makers=None):
        (self.content / "products.json").write_bytes((products or products_text()).encode("ascii"))
        (self.content / "makers.json").write_bytes((makers or makers_text()).encode("ascii"))

    def run_cli(self, *flags):
        proc = subprocess.run([sys.executable, "-B", str(self.root / "hass" / "itemstd.py"), "report",
                               "--content", str(self.content), *flags],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.root)
        return proc


class SurrogateAdmissionTest(SurrogateBase):
    def test_load_refuses_surrogates_in_keys_values_and_metadata(self):
        for bad in BAD:
            cases = [
                ("products.json", "products", list, products_text(f"Syn{bad}")),
                ("products.json", "products", list, products_text(extra='"note": ["a", ["x%s"]], ' % bad)),
                ("products.json", "products", list, products_text(extra='"n%s": 1, ' % bad)),
                ("makers.json", "makers", dict, makers_text(f"Syn{bad}")),
                ("makers.json", "makers", dict, makers_text(key=f"k{bad}")),
                ("makers.json", "makers", dict, makers_text(extra='"note": {"a": ["x%s"]}, ' % bad)),
            ]
            for name, key, kind, text in cases:
                with self.subTest(file=name, bad=bad, text=text):
                    self.put()
                    (self.content / name).write_bytes(text.encode("ascii"))
                    with self.assertRaises(itemstd.ReportError) as got:
                        itemstd._load(self.content / name, key, kind)
                    msg = str(got.exception)
                    self.assertTrue(msg.endswith("JSON contains surrogate text"), msg)
                    self.assertNotIn("Syn", msg)
                    self.assertNotIn(bad, msg)
                    with self.assertRaises(itemstd.ReportError):
                        itemstd.report_for(self.content)

    def test_real_cli_surrogate_input_is_exit_two(self):
        for which in ("products", "makers"):
            for flags in ((), ("--json",), ("--write",), ("--json", "--write")):
                with self.subTest(which=which, flags=flags):
                    self.report.write_text(SENTINEL, encoding="utf-8")
                    if which == "products":
                        self.put(products=products_text("Synthetic\\ud800Canary"))
                    else:
                        self.put(makers=makers_text("Synthetic\\udfffCanary"))
                    proc = self.run_cli(*flags)
                    self.assertEqual(proc.returncode, 2, proc.stderr)
                    self.assertEqual(proc.stdout, "")
                    self.assertEqual(len(proc.stderr.strip().splitlines()), 1, proc.stderr)
                    self.assertTrue(proc.stderr.startswith("itemstd: cannot read "), proc.stderr)
                    self.assertNotIn("Traceback", proc.stderr)
                    self.assertNotIn("UnicodeEncodeError", proc.stderr)
                    self.assertNotIn("Canary", proc.stderr)
                    self.assertEqual(self.report.read_text(encoding="utf-8"), SENTINEL)

    def test_bad_input_never_calls_writer_or_changes_report(self):
        self.put(products=products_text("Synthetic\\ud800"))
        before = {p.name: p.read_bytes() for p in self.content.iterdir()}
        modes = {p.name: p.stat().st_mode for p in self.content.iterdir()}
        out, err = io.StringIO(), io.StringIO()
        for report_exists in (True, False):
            with self.subTest(report_exists=report_exists):
                self.report.unlink(missing_ok=True)
                if report_exists:
                    self.report.write_text(SENTINEL, encoding="utf-8")
                with mock.patch.object(itemstd, "REPORT_PATH", self.report), \
                        mock.patch.object(itemstd, "write_report") as writer, \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = itemstd.main(["report", "--content", str(self.content), "--write"])
                self.assertEqual(code, 2)
                writer.assert_not_called()
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(self.report.exists(), report_exists)
                if report_exists:
                    self.assertEqual(self.report.read_text(encoding="utf-8"), SENTINEL)
                self.assertEqual(sorted(p.name for p in self.report.parent.iterdir()),
                                 ["catalog-gaps.json"] if report_exists else [])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.content.iterdir()})
        self.assertEqual(modes, {p.name: p.stat().st_mode for p in self.content.iterdir()})
        # real subprocess on the copied repo: same boundary, no staging residue
        self.report.unlink(missing_ok=True)
        proc = self.run_cli("--write")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(list(self.report.parent.iterdir()), [])

    def test_valid_unicode_and_literal_escape_controls(self):
        name = "caf\\u00e9 e\\u0301 \\u4e2d\\u6587 \\ud83d\\ude00 \\\\ud800"
        self.put(products=products_text(name), makers=makers_text(name))
        self.report.write_text(SENTINEL, encoding="utf-8")
        proc = self.run_cli("--json", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        want = "caf\u00e9 e\u0301 \u4e2d\u6587 \U0001F600 \\ud800"
        report = json.loads(proc.stdout)
        self.assertEqual(report["products"][0]["name"], want)
        self.assertEqual(self.report.read_text(encoding="utf-8"), proc.stdout)
        self.assertIn("\U0001F600", self.report.read_bytes().decode("utf-8"))

    def test_iterative_walk_and_legacy_envelope_errors(self):
        nest = "[" * 300 + "]" * 300
        self.put(products=products_text(extra='"note": %s, ' % nest))
        value, _ = itemstd._load(self.content / "products.json", "products", list)
        self.assertEqual(len(value), 1)
        # legacy errors keep precedence over the surrogate walk
        (self.content / "products.json").write_bytes(
            b'{"schemaVersion": 2, "products": [], "x": "\\ud800"}')
        with self.assertRaises(itemstd.ReportError) as got:
            itemstd._load(self.content / "products.json", "products", list)
        self.assertIn("expected", str(got.exception))
        (self.content / "products.json").write_bytes(b"[" * 100000)
        with self.assertRaises(itemstd.ReportError) as got:
            itemstd._load(self.content / "products.json", "products", list)
        self.assertIn("too deep", str(got.exception))


if __name__ == "__main__":
    unittest.main()
