"""Fixture-only acceptance tests for the offline revert scan."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_revert_scan.py"
SPEC = importlib.util.spec_from_file_location("install_revert_scan", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)
PRIVATE = "synthetic-private-marker"


class InstallRevertScanTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix=f"{PRIVATE}-")
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ALLOW_PROTOCOL="")
        self.git("init", "-q", "-b", "main", "--template=", "--object-format=sha1")
        self.file = self.repo / "unit a.txt"
        self.file.write_text("before\n", encoding="utf-8")
        self.git("add", "--all")
        self.base = self.commit("Base")

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgSign=false", "-C", str(self.repo), *args],
            check=True, capture_output=True, text=True, env=self.env, timeout=10,
        ).stdout.strip()

    def commit(self, message):
        self.git("commit", "-qm", message, "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def merge_unit(self, unit):
        self.git("switch", "-qc", unit)
        (self.repo / f"unit {unit}.txt").write_text(f"{PRIVATE}\n", encoding="utf-8")
        self.git("add", "--all")
        introduced = self.commit(f"Unit {unit}\n\n{PRIVATE}")
        self.git("switch", "-q", "main")
        self.git("merge", "--no-ff", "-qm", f"Merge {unit}", unit)
        return self.git("rev-parse", "HEAD"), introduced

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = SCAN.main(args)
            except SystemExit as exit_:
                code = exit_.code
        self.assertNotIn(PRIVATE, out.getvalue() + err.getvalue())
        return code, out.getvalue(), err.getvalue()

    def assert_scan(self, code, lines, target, *merges, repo=None):
        args = ["--repo", str(self.repo if repo is None else repo), "--target", target]
        for merge in merges:
            args += ["--merge", merge]
        final = "PASS" if code == 0 else "FAIL"
        expected = "\n".join([*lines, f"{final} install_revert_scan", ""])
        self.assertEqual(self.invoke(args), (code, expected, ""))

    def test_two_clean_merges_use_committed_trees_without_writes(self):
        # Reading the dirty tree would flag a restore; updating Git would change the snapshot.
        first, _ = self.merge_unit("a")
        second, _ = self.merge_unit("b")
        self.file.write_text("before\n", encoding="utf-8")

        def snapshot():
            return {path: path.read_bytes() for path in self.repo.rglob("*") if path.is_file()}

        before = snapshot()
        self.assert_scan(0, [f"OK {first[:12]}", f"OK {second[:12]}"], second, first, second)
        self.assertEqual(snapshot(), before)

    def test_git_merge_revert_reports_both_findings_and_keeps_scanning(self):
        # Git's generated trailer and identical bytes are independent findings.
        first, _ = self.merge_unit("a")
        second, _ = self.merge_unit("b")
        self.git("revert", "--no-edit", "-m", "1", first)
        reverted = self.git("rev-parse", "HEAD")
        self.assert_scan(1, [f"FAIL reverted {first[:12]} by {reverted[:12]}",
                             f"FAIL path-restored {first[:12]} unit a.txt", f"OK {second[:12]}"],
                         reverted, first, second)

    def test_revert_of_introduced_commit_on_merged_side_branch(self):
        # Checking only first-parent history or only direct reverts of M misses this.
        merge, introduced = self.merge_unit("a")
        self.git("switch", "-qc", "later")
        reverted = self.commit(f"This reverts commit {introduced}.\n\n{PRIVATE}")
        self.commit(f"This reverts commit {self.base}.")  # Not in M^1..M.
        self.git("switch", "-q", "main")
        self.git("merge", "--no-ff", "-qm", "Merge later", "later")
        self.assert_scan(1, [f"FAIL reverted {merge[:12]} by {reverted[:12]}"],
                         self.git("rev-parse", "HEAD"), merge)

    def test_quiet_restore_of_edited_file_and_deletion_of_added_file(self):
        # Quiet edits have no trailer; deleting a merge-added path restores absence.
        merge, _ = self.merge_unit("a")
        added, _ = self.merge_unit("b")
        self.file.write_text("before\n", encoding="utf-8")
        self.git("rm", "--", "unit b.txt")
        self.git("add", "--all")
        target = self.commit("Quiet restore")
        self.assert_scan(1, [f"FAIL path-restored {merge[:12]} unit a.txt",
                             f"FAIL path-restored {added[:12]} unit b.txt"], target, merge, added)

    def test_non_merge_commit_is_rejected(self):
        # An ancestor isn't sufficient without at least two parents.
        target, unit = self.merge_unit("a")
        self.assert_scan(1, ["FAIL not-merge"], target, unit)

    def test_merge_not_reachable_from_selected_release_is_rejected(self):
        # An existing merge (even HEAD) doesn't prove reachability from the target.
        merge, _ = self.merge_unit("a")
        self.assert_scan(1, ["FAIL not-ancestor"], self.base, merge)

    def test_missing_or_noncommit_object_is_unknown(self):
        # A syntactically valid ID or an existing blob isn't enough to name a commit.
        merge, _ = self.merge_unit("a")
        for value in ("0" * 40, self.git("rev-parse", "HEAD:unit a.txt")):
            with self.subTest(value=value[:12]):
                self.assert_scan(1, ["FAIL unknown-commit"], merge, value)
                self.assert_scan(1, ["FAIL unknown-commit"], value, merge)

    def test_bad_sha_is_a_redacted_finding_not_usage_error(self):
        # Reject revision expressions and wrong widths before they reach Git.
        merge, _ = self.merge_unit("a")
        for value in (PRIVATE, merge + "^1", merge[:12], "f" * 64):
            self.assert_scan(1, ["FAIL bad-sha"], merge, value)
            self.assert_scan(1, ["FAIL bad-sha"], value, merge)
        self.assert_scan(1, ["FAIL bad-sha", "FAIL unknown-commit"], merge, PRIVATE, "0" * 40)

    def test_unreadable_repo_fails_without_git_diagnostics(self):
        # Git's stderr contains the private checkout path on a failed -C.
        merge, _ = self.merge_unit("a")
        self.assert_scan(1, ["FAIL unknown-commit"], merge, merge, repo=self.repo / "missing")

    def test_promisor_repository_fails_closed_before_object_lookups(self):
        # Some versions of Git try lazy fetches on missing objects in partial clones.
        merge, _ = self.merge_unit("a")
        self.git("config", "remote.fixture.promisor", "true")
        self.assert_scan(1, ["FAIL unknown-commit"], merge, merge)

    def test_usage_errors_stay_argparse_exit_two_and_redact_arguments(self):
        # Missing/extra arguments are CLI usage errors, not scan findings.
        code, out, err = self.invoke(["--repo", str(self.repo), PRIVATE])
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage:", err)
