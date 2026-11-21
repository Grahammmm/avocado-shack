"""Fixture-only checks of the maker allowlist comparison contract."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_allowlist_diff.py"
SPEC = importlib.util.spec_from_file_location("install_allowlist_diff", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
DIFF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIFF)

MARKER = "synthetic-private-marker"
ENTRY = b'{"a":"synthetic-private-marker","b":true}'
OTHER = b'"synthetic-alternative"'
EMPTY = b'{"allowlist":[]}'


def document(*entries):
    return b'{"allowlist":[' + b','.join(entries) + b']}'


def digest(entry):
    return hashlib.sha256(entry).hexdigest()[:12]


class InstallAllowlistDiffTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        self.file = self.repo / "hass/npp/assets/hass-maker-research/sources.json"
        self.file.parent.mkdir(parents=True)
        self.git("init", "--quiet", "--object-format=sha1")

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
            cwd=self.repo, check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()

    def commit(self, raw):
        if raw is None:
            self.file.unlink(missing_ok=True)
        else:
            self.file.write_bytes(raw)
        self.git("add", "--all")
        self.git("commit", "--quiet", "--allow-empty", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def args(self, old, new, repo=None):
        return ["--repo", str(self.repo if repo is None else repo), "--old", old, "--new", new]

    def assert_output(self, result, stdout, stderr, *lines, reasons=()):
        self.assertEqual(stderr, "")
        for marker in (MARKER, "synthetic-alternative", str(self.repo)):
            self.assertNotIn(marker, stdout + stderr)
        expected = [*lines, *(f"FAIL {reason}" for reason in reasons)]
        expected.append(f"{'FAIL' if reasons else 'PASS'} install_allowlist_diff")
        self.assertEqual(stdout, "\n".join(expected) + "\n")
        self.assertEqual(result, 1 if reasons else 0)

    def check_diff(self, old, new, *lines, reasons=(), repo=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = DIFF.main(self.args(old, new, repo))
        self.assert_output(result, stdout.getvalue(), stderr.getvalue(), *lines, reasons=reasons)

    def test_equal_commits_pass_regardless_of_order_and_worktree(self):
        # Comparing file bytes, list order, unrelated keys, or the dirty tree would fail.
        old = self.commit(document(ENTRY, OTHER, ENTRY))
        new = self.commit(b'{"extra":false, "allowlist":[' + OTHER + b', '
                          b'{"b":true, "a":"synthetic-private-marker"},' + ENTRY + b']}')
        dirty = b"not the committed input"
        self.file.write_bytes(dirty)
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *self.args(old, new)],
                                capture_output=True, text=True, timeout=10)
        self.assert_output(result.returncode, result.stdout, result.stderr,
                           "old_count 3 new_count 3 added 0 removed 0")
        self.assertEqual(self.file.read_bytes(), dirty)

    def test_add_remove_swap_and_duplicate(self):
        # Count-only comparison misses swaps; set comparison misses extra copies.
        old = self.commit(document(ENTRY))
        added = f"added {digest(OTHER)}"
        removed = f"removed {digest(ENTRY)}"
        duplicate = f"added {digest(ENTRY)}"
        for entries, counts, changes in (
            ((ENTRY, OTHER), "1 new_count 2 added 1 removed 0", [added]),
            ((), "1 new_count 0 added 0 removed 1", [removed]),
            ((OTHER,), "1 new_count 1 added 1 removed 1", [added, removed]),
            ((ENTRY, ENTRY, ENTRY), "1 new_count 3 added 2 removed 0", [duplicate, duplicate]),
        ):
            with self.subTest(counts=counts):
                new = self.commit(document(*entries))
                self.check_diff(old, new, f"old_count {counts}", *changes, reasons=("changed",))

    def test_distinct_large_decimal_values_are_changes(self):
        old = self.commit(document(b'{"value":9007199254740992.0}'))
        new = self.commit(document(b'{"value":9007199254740993.0}'))
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = DIFF.main(self.args(old, new))
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(result, 1)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[0], "old_count 1 new_count 1 added 1 removed 1")
        self.assertRegex(lines[1], r"^added [0-9a-f]{12}$")
        self.assertRegex(lines[2], r"^removed [0-9a-f]{12}$")
        self.assertNotEqual(lines[1].split()[1], lines[2].split()[1])
        self.assertEqual(lines[3:], ["FAIL changed", "FAIL install_allowlist_diff"])

    def test_equivalent_decimal_spellings_and_nested_values(self):
        old = self.commit(document(b'{"values":[1.00,9.007199254740993e15,1e400,0.00]}'))
        new = self.commit(document(b'{"values":[1e0,9007199254740993.0,10e399,0e-12]}'))
        self.check_diff(old, new, "old_count 1 new_count 1 added 0 removed 0")

    def test_refuses_bad_sources_and_labels_both_sides(self):
        # Lenient JSON parsing or defaulting missing fields to [] could pass bad inputs.
        good = self.commit(EMPTY)
        for raw, reason in (
            (None, "absent"),
            (b'{"allowlist":["synthetic-private-marker",]}', "bad-json"),
            (b'\xff', "bad-json"),
            (b'[]', "bad-json"),
            (document(b'NaN'), "bad-json"),
            (document(b'Infinity'), "bad-json"),
            (document(b'-Infinity'), "bad-json"),
            (document(b'1e99999999999999999999999999999'), "bad-json"),
            (rb'{"allowlist":[{"synthetic-private-marker":0,"synthetic-private-mark\u0065r":1}]}',
             "duplicate-key"),
            (b'{"allowlist":[],"allowlist":[]}', "duplicate-key"),
            (b'{"allowlist":false}', "not-list"),
            (b'{}', "not-list"),
        ):
            with self.subTest(raw=raw):
                bad = self.commit(raw)
                self.check_diff(bad, good, reasons=(f"{reason} old",))
                self.check_diff(good, bad, reasons=(f"{reason} new",))
        self.check_diff(self.commit(None), self.commit(b'{}'),
                        reasons=("absent old", "not-list new"))

    def test_bad_sha_and_unknown_commit_are_distinct(self):
        # Refs and abbreviated IDs are not full SHAs; a tree SHA is not a commit.
        good = self.commit(EMPTY)
        for invalid in ("HEAD", good[:12], "g" * 40, good + "\n"):
            with self.subTest(invalid=invalid):
                self.check_diff(invalid, good, reasons=("bad-sha",))
        for missing in ("f" * 40, self.git("rev-parse", "HEAD^{tree}")):
            with self.subTest(missing=missing):
                self.check_diff(good, missing, reasons=("unknown-commit",))
        self.check_diff(good, good, repo=self.repo / MARKER,
                        reasons=("unknown-commit", "unknown-commit"))

    def test_missing_argument_preserves_argparse_exit(self):
        # Missing CLI syntax must not be treated as an allowlist finding.
        result = subprocess.run([sys.executable, "-B", str(SCRIPT)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("usage:", result.stderr)
        self.assertNotIn("FAIL", result.stderr)


if __name__ == "__main__":
    unittest.main()
