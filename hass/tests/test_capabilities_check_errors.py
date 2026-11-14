"""RF1036-10: capabilities --check classifies unreadable artifacts as stale, never a traceback."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hass import capabilities

CANARY = "private-canary-0d7e"
BAD_BYTES = b"\xff\xfe\x80\n"
JSON_REL, PAGE_REL = str(capabilities.JSON_PATH), str(capabilities.PAGE_PATH)
FRESH = "Capability manifest and owner page match the registry.\n"


def _snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


class CheckErrorTests(unittest.TestCase):
    def setUp(self):
        self.files = capabilities.generated_files()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel, text in self.files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        self.valid = _snapshot(self.root)

    def check(self, fault=None):
        out, err = io.StringIO(), io.StringIO()
        real = Path.read_text
        writes = []

        def fake_read(path, *a, **k):
            if fault and str(path).endswith(tuple(fault)):
                for rel, exc in fault.items():
                    if str(path).endswith(rel):
                        raise exc
            return real(path, *a, **k)

        def spy(name):
            def inner(*a, **k):
                writes.append(name)
                raise AssertionError("--check must not write: " + name)
            return inner

        with patch.object(capabilities, "ROOT", self.root), \
                patch.object(Path, "read_text", fake_read), \
                patch.object(Path, "write_text", spy("write_text")), \
                patch.object(Path, "mkdir", spy("mkdir")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = capabilities.main(["--check"])
        self.assertEqual(writes, [])
        return code, out.getvalue(), err.getvalue()

    def test_invalid_utf8_each_artifact_is_stale_not_a_traceback(self):
        for rel in (JSON_REL, PAGE_REL):
            with self.subTest(rel=rel):
                (self.root / rel).write_bytes(BAD_BYTES)
                before = _snapshot(self.root)
                code, out, err = self.check()
                self.assertEqual((code, out, err), (1, "", "Stale capability files: " + rel + "\n"))
                self.assertEqual(_snapshot(self.root), before)
                self.assertEqual((self.root / rel).read_bytes(), BAD_BYTES)
                (self.root / rel).write_text(self.files[Path(rel)], encoding="utf-8")

    def test_read_permission_and_disappearance_errors_are_stale(self):
        for exc in (PermissionError(13, CANARY), FileNotFoundError(2, CANARY), OSError(5, CANARY)):
            with self.subTest(exc=type(exc).__name__):
                code, out, err = self.check({JSON_REL: exc})
                self.assertEqual((code, out, err), (1, "", "Stale capability files: " + JSON_REL + "\n"))
                self.assertNotIn(CANARY, out + err)
                self.assertEqual(_snapshot(self.root), self.valid)

    def test_both_failed_artifacts_are_reported_once_in_declared_order(self):
        both = ", ".join((JSON_REL, PAGE_REL))
        (self.root / JSON_REL).write_bytes(BAD_BYTES)
        code, out, err = self.check({PAGE_REL: PermissionError(13, CANARY)})
        self.assertEqual((code, out, err), (1, "", "Stale capability files: " + both + "\n"))
        (self.root / JSON_REL).write_text(self.files[capabilities.JSON_PATH], encoding="utf-8")
        (self.root / PAGE_REL).write_bytes(BAD_BYTES)
        code, out, err = self.check({JSON_REL: OSError(5, CANARY)})
        self.assertEqual((code, out, err), (1, "", "Stale capability files: " + both + "\n"))
        self.assertNotIn(CANARY, out + err)

    def test_fresh_missing_and_plain_text_drift_keep_legacy_results(self):
        self.assertEqual(self.check(), (0, FRESH, ""))
        (self.root / PAGE_REL).write_text("stale\n", encoding="utf-8")
        self.assertEqual(self.check(), (1, "", "Stale capability files: " + PAGE_REL + "\n"))
        (self.root / JSON_REL).unlink()
        both = ", ".join((JSON_REL, PAGE_REL))
        self.assertEqual(self.check(), (1, "", "Stale capability files: " + both + "\n"))
        self.assertFalse((self.root / JSON_REL).exists())

    def test_non_io_programming_errors_and_generator_contract_are_not_swallowed(self):
        with self.assertRaises(RuntimeError):
            self.check({JSON_REL: RuntimeError(CANARY)})
        with patch.object(capabilities, "ROOT", self.root), \
                patch.object(capabilities, "generated_files", side_effect=ValueError("bad registry")), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(capabilities.main(["--check"]), 1)
        self.assertEqual(err.getvalue(), "bad registry\n")
        self.assertEqual(_snapshot(self.root), self.valid)


if __name__ == "__main__":
    unittest.main()
