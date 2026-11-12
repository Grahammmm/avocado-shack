"""RF1801-12: catalog-report envelopes accept only the exact integer schemaVersion 1 (JSON true / 1.0 / 1e0 refused)."""
import contextlib
import hashlib
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
OK_PRODUCTS = '{"schemaVersion": 1, "products": []}'
OK_MAKERS = '{"schemaVersion": 1, "makers": {}}'
# raw JSON text for the version value: decoded Python equality aliases of 1 plus every other wrong shape
BAD_VERSIONS = ("true", "false", "1.0", "1e0", "2", "0", "-1", '"1"', "null", "[1]", "{}")
ENVELOPES = (("products.json", "products", "[]"), ("makers.json", "makers", "{}"))


def envelope(key, body, version):
    """Serialized envelope text; version None = field absent."""
    head = "" if version is None else f'"schemaVersion": {version}, '
    return "{" + head + f'"{key}": {body}' + "}"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class VersionAdmissionTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.content = self.tmp / "content"
        self.content.mkdir()

    def put(self, name, text):
        (self.content / name).write_text(text, encoding="utf-8")

    def check_envelope(self, name, key, empty):
        kind = list if key == "products" else dict
        for version in BAD_VERSIONS + (None,):
            with self.subTest(file=name, version=version):
                self.put("products.json", OK_PRODUCTS)
                self.put("makers.json", OK_MAKERS)
                self.put(name, envelope(key, empty, version))
                with self.assertRaises(itemstd.ReportError) as got:
                    itemstd._load(self.content / name, key, kind)
                self.assertIn('expected {"schemaVersion": 1,', str(got.exception))
                with self.assertRaises(itemstd.ReportError):
                    itemstd.report_for(self.content)
        # exact integer 1 stays accepted, including shallow unknown metadata
        self.put(name, '{"schemaVersion": 1, "note": {"x": 1.0}, "%s": %s}' % (key, empty))
        value, _ = itemstd._load(self.content / name, key, kind)
        self.assertEqual(value, kind())
        # payload-kind check still applies with a valid version
        self.put(name, envelope(key, "{}" if key == "products" else "[]", 1))
        with self.assertRaises(itemstd.ReportError):
            itemstd._load(self.content / name, key, kind)

    def test_products_envelope_requires_exact_integer_version(self):
        self.check_envelope(*ENVELOPES[0])

    def test_makers_envelope_requires_exact_integer_version(self):
        self.check_envelope(*ENVELOPES[1])


class ReportRefusalTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.repo = self.tmp / "repo"
        (self.repo / "hass" / "style").mkdir(parents=True)
        for f in ("__init__.py", "voice.py", "itemstd.py", "style/item-standard.json"):
            shutil.copy(REPO / "hass" / f, self.repo / "hass" / f)
        self.content = self.repo / "hass" / "content"
        self.content.mkdir()
        self.reports = self.repo / "reports" / "hass"
        self.reports.mkdir(parents=True)
        self.target = self.reports / "catalog-gaps.json"
        self.script = self.repo / "hass" / "itemstd.py"
        self.foreign = self.tmp / "elsewhere"
        self.foreign.mkdir()

    def set_inputs(self, products_version, makers_version):
        """Versions are raw JSON text or an int."""
        (self.content / "products.json").write_text(envelope("products", "[]", products_version), encoding="utf-8")
        (self.content / "makers.json").write_text(envelope("makers", "{}", makers_version), encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(self.script), "report", *args], cwd=self.foreign,
                              capture_output=True, text=True, timeout=120)

    def inventory(self):
        return sorted(p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*") if p.is_file())

    def bad_cases(self):
        return (("true", 1), ("1.0", 1), (1, "true"), (1, "1.0"))

    def test_real_cli_bad_version_is_exit_two_without_stdout(self):
        for pv, mv in self.bad_cases():
            self.set_inputs(pv, mv)
            before = (sha(self.content / "products.json"), sha(self.content / "makers.json"))
            for extra in ((), ("--json",)):
                with self.subTest(products=pv, makers=mv, extra=extra):
                    got = self.run_cli(*extra)
                    self.assertEqual(got.returncode, 2, got.stderr)
                    self.assertEqual(got.stdout, "")
                    self.assertIn('expected {"schemaVersion": 1,', got.stderr)
                    self.assertNotIn("Traceback", got.stderr)
            self.assertEqual((sha(self.content / "products.json"), sha(self.content / "makers.json")), before)
        self.assertEqual(list(self.foreign.iterdir()), [])

    def test_write_refuses_before_staging_and_preserves_old_report(self):
        self.target.write_bytes(b"old report\n")
        for pv, mv in self.bad_cases():
            self.set_inputs(pv, mv)
            before = self.inventory()
            for extra in (("--write",), ("--write", "--json")):
                with self.subTest(products=pv, makers=mv, extra=extra):
                    got = self.run_cli(*extra)
                    self.assertEqual((got.returncode, got.stdout), (2, ""), got.stderr)
                    self.assertEqual(self.target.read_bytes(), b"old report\n")
                    self.assertEqual(self.inventory(), before, "no staging file appears")

    def test_write_refusal_happens_before_the_writer_runs(self):
        self.target.write_bytes(b"old report\n")
        for pv, mv in self.bad_cases():
            self.set_inputs(pv, mv)
            with self.subTest(products=pv, makers=mv):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(itemstd, "REPORT_PATH", self.target), \
                        mock.patch.object(itemstd, "write_report") as writer, \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = itemstd.main(["report", "--content", str(self.content), "--write"])
                self.assertEqual((code, out.getvalue()), (2, ""))
                writer.assert_not_called()
                self.assertEqual(self.target.read_bytes(), b"old report\n")

    def test_invalid_version_never_creates_absent_report(self):
        self.assertFalse(self.target.exists())
        for pv, mv in self.bad_cases():
            self.set_inputs(pv, mv)
            with self.subTest(products=pv, makers=mv):
                got = self.run_cli("--write")
                self.assertEqual(got.returncode, 2, got.stderr)
                self.assertEqual(sorted(p.name for p in self.reports.iterdir()), [])
        # an absent reports folder stays absent as well (refusal still wins over any writer setup)
        shutil.rmtree(self.repo / "reports")
        self.set_inputs("true", 1)
        got = self.run_cli("--write")
        self.assertEqual((got.returncode, got.stdout), (2, ""))
        self.assertFalse((self.repo / "reports").exists())

    def test_valid_integer_one_keeps_report_bytes_and_explicit_write(self):
        self.set_inputs(1, 1)
        (self.content / "products.json").write_text(
            '{"schemaVersion": 1, "meta": {"a": 1.0}, "products": []}', encoding="utf-8")
        self.target.write_bytes(b"old report\n")
        inputs = (sha(self.content / "products.json"), sha(self.content / "makers.json"))
        plain = self.run_cli("--json")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(self.target.read_bytes(), b"old report\n", "no write without --write")
        written = self.run_cli("--write", "--json")
        self.assertEqual(written.returncode, 0, written.stderr)
        self.assertEqual(written.stdout, plain.stdout)
        report = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(report, json.loads(plain.stdout))
        self.assertEqual(report["source"]["products_sha256"], inputs[0])
        self.assertEqual(report["source"]["makers_sha256"], inputs[1])
        self.assertEqual(sorted(p.name for p in self.reports.iterdir()), ["catalog-gaps.json"])


if __name__ == "__main__":
    unittest.main()
