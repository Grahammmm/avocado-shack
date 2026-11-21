"""Fixture-only CLI contract for the saved retention report comparison."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/retention_report_diff.py"


class RetentionReportDiffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.before = self.root / "before" / "saved.txt"
        self.after = self.root / "after" / "saved.txt"
        for path in (self.before, self.after):
            path.parent.mkdir()
            self.save(path)

    def save(self, path, **fields):
        report = {"days": 30, "deletes": 0, **fields}
        path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, timeout=10,
        )

    def compare(self):
        return self.invoke("--before", str(self.before), "--after", str(self.after))

    def assert_result(self, result, code, *lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stderr, "")
        last = "PASS retention_report_diff" if code == 0 else "FAIL retention_report_diff"
        self.assertEqual(result.stdout, "\n".join((*lines, last, "")))

    def test_c1_full_pass(self):
        # Reading the first line, treating nulls as failures, or projecting metadata breaks this.
        self.save(self.before, cutoff="2000-01-01T00:00:00+00:00",
                  backups=None, media={"bytes": 4}, webOrphans=1,
                  messages={"rows": 2, "oldest": "2000-01-01"})
        self.save(self.after, cutoff="2000-01-02T00:00:00+00:00",
                  backups={"complete": 1}, media=None, webOrphans=2,
                  messages={"rows": 3, "oldest": "2000-01-02"})
        self.before.write_bytes(b'{"days":1,"deletes":1}\nfixture preamble\n'
                                + self.before.read_bytes() + b" \t\n\n")
        self.assert_result(self.compare(), 0, "note absent before backups",
                           "note absent after media", "oldest messages 2000-01-01 2000-01-02",
                           "delta messages.rows 2 3")

    def test_c2_1_no_file(self):
        # A directory is not a report even though it exists.
        missing = self.root / "missing"
        directory = self.after.parent
        self.assert_result(self.invoke("--before", str(missing), "--after", str(self.after)),
                           1, "FAIL no-file before")
        self.assert_result(self.invoke("--before", str(self.before), "--after", str(directory)),
                           1, "FAIL no-file after")

    def test_c2_2_bad_report(self):
        # JSON arrays, booleans, floats, and a usable penultimate line must not pass.
        for raw in (b"", b"not json", b"[]", b'{"days":30}', b'{"days":true,"deletes":0}',
                    b'{"days":30,"deletes":false}', b'{"days":30,"deletes":0.0}',
                    b'{"days":30,"deletes":0}\nnot json\n', b"\xff"):
            with self.subTest(raw=raw):
                self.before.write_bytes(raw)
                self.assert_result(self.compare(), 1, "FAIL bad-report before")
        self.save(self.before)
        self.after.write_bytes(b'null\n')
        self.assert_result(self.compare(), 1, "FAIL bad-report after")

    def test_c2_3_days_mismatch(self):
        # Comparing counts under different windows is a finding, even with no deletes.
        self.save(self.after, days=31)
        self.assert_result(self.compare(), 1, "FAIL days-mismatch")

    def test_c2_4_deletes_nonzero(self):
        # Checking only the after report or only positive values misses a finding.
        self.save(self.before, deletes=2)
        self.save(self.after, deletes=-1)
        self.assert_result(self.compare(), 1, "FAIL deletes-nonzero before",
                           "FAIL deletes-nonzero after")

    def test_c2_5_unavailable(self):
        # The sentinel is a per-side finding even if the other side reports the class.
        self.save(self.before, inbox="unavailable", messages="unavailable")
        self.save(self.after, inbox={"done": 0}, messages="unavailable")
        self.assert_result(self.compare(), 1, "FAIL unavailable before inbox",
                           "FAIL unavailable before messages", "FAIL unavailable after messages")

    def test_c3_usage_exit_2(self):
        # Usage errors must not be translated into findings or print a status line.
        before = ("--before", str(self.before))
        both = (*before, "--after", str(self.after))
        for args in (before, (*both, "--unexpected"), (*before, "--after")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last stdout line for usage errors.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Detect even rewriting the same bytes, or creating an artifact in either directory.
        paths = (self.before, self.after)
        snapshot = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
        self.assert_result(self.compare(), 0)
        self.assertEqual(snapshot, [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths])
        for path in paths:
            self.assertEqual(set(path.parent.iterdir()), {path})

    def test_c5_no_private_values(self):
        # Dumping either report, echoing parse errors or leaking extra argv would disclose canaries.
        private = dict(text="fixture-text-canary", chat="fixture-chat-canary",
                       sender="fixture-sender-canary", uid="fixture-id-canary",
                       digest="fixture-digest-canary")
        for path in (self.before, self.after):
            self.save(path, messages={"rows": 1, "oldest": "2000-01-01", **private})
        passed = self.compare()
        self.assert_result(passed, 0, "oldest messages 2000-01-01 2000-01-01",
                           "delta messages.rows 1 1")
        self.after.write_text(f"not JSON: {private}", encoding="utf-8")
        failed = self.compare()
        self.assert_result(failed, 1, "FAIL bad-report after")
        missing = self.root / "missing"
        no_file = self.invoke("--before", str(missing), "--after", str(self.before))
        self.assert_result(no_file, 1, "FAIL no-file before")
        usage = self.invoke("--before", str(self.before), "--after", str(self.after),
                            "--unexpected", str(missing))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (passed, failed, no_file, usage):
            for canary in (*private.values(), str(self.before), str(self.after), str(missing)):
                self.assertNotIn(canary, result.stdout)
                self.assertNotIn(canary, result.stderr)

    def test_c6_deterministic(self):
        # Insertion-order iteration at either level changes the bytes for equivalent reports.
        self.save(self.before, screenshots={"files": 0, "bytes": 0},
                  messages={"rows": 0, "oldest": None})
        self.save(self.after, screenshots={"files": 1, "bytes": 8},
                  messages={"rows": 1, "oldest": "2000-01-01"})
        first = self.compare()
        self.save(self.before, messages={"oldest": None, "rows": 0},
                  screenshots={"bytes": 0, "files": 0})
        self.save(self.after, messages={"oldest": "2000-01-01", "rows": 1},
                  screenshots={"bytes": 8, "files": 1})
        second = self.compare()
        expected = ("oldest messages null 2000-01-01", "delta messages.rows 0 1",
                    "delta screenshots.bytes 0 8", "delta screenshots.files 0 1")
        for result in (first, second):
            self.assert_result(result, 0, *expected)
        self.assertEqual(first.stdout, second.stdout)


if __name__ == "__main__":
    unittest.main()
