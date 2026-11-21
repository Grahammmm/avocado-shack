"""Exercise the read-only install receipt on synthetic change records."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_change_record.py"
SPEC = importlib.util.spec_from_file_location("pilot_change_record", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)

CHANGE_ID = "chg-0123456789ab"
COMMIT = "0123456789abcdef" + "a" * 24
PRIVATE = "synthetic-private-marker"
SUCCESS = {"state": "installed", "commit": COMMIT, "installed_at": "2000-01-01T00:00:00+00:00", "files": 2}


class PilotChangeRecordTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.changes = self.root / "changes"
        self.changes.mkdir()
        self.record = self.changes / f"{CHANGE_ID}.json"

    def store(self, install):
        self.record.write_text(json.dumps({"private": PRIVATE, "install": install}), encoding="utf-8")

    def check(self, expected, *, status=1, change_id=CHANGE_ID, cli=False):
        args = ["--state", str(self.root), "--change-id", change_id]
        if cli:
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                                    capture_output=True, text=True, timeout=5)
            actual = result.returncode, result.stdout, result.stderr
        else:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = reader.main(args)
            actual = code, stdout.getvalue(), stderr.getvalue()
        self.assertEqual(actual, (status, expected + "\n", ""))

    def test_success_prints_only_short_commit_and_changes_no_files(self):
        # Printing the receipt object or rewriting state would leak or alter private data.
        self.store(SUCCESS)
        before = self.record.read_bytes(), self.record.stat().st_mtime_ns
        self.check("INSTALLED commit 0123456789ab", status=0, cli=True)
        self.assertEqual((self.record.read_bytes(), self.record.stat().st_mtime_ns), before)
        self.assertEqual(set(self.root.rglob("*")), {self.changes, self.record})

    def test_missing_and_absent_result_stay_distinct(self):
        # A top-level applied commit is not evidence that the site was installed.
        self.check("NOT-INSTALLED missing-record")
        self.assertEqual(list(self.changes.iterdir()), [])
        self.record.write_text(json.dumps({"state": "applied", "commit": COMMIT, "private": PRIVATE}),
                               encoding="utf-8")
        self.check("NOT-INSTALLED no-install-result")

    def test_failure_names_omit_details_and_do_not_echo_unknown_reasons(self):
        # Raw reasons contain paths and rollback details; even a bare unknown name is private.
        for name in ("site path is not a regular file", "site file cannot be read",
                     "readback mismatch", "write failed", PRIVATE):
            with self.subTest(name=name):
                reason = f"{name}: {PRIVATE}; rollback failed: {PRIVATE}"
                self.store({"state": "failed", "reason": reason, "failed_at": SUCCESS["installed_at"],
                            "commit": COMMIT})
                expected = name if name != PRIVATE else "no-install-result"
                self.check(f"NOT-INSTALLED {expected}")
        for reason in (None, [], PRIVATE):
            with self.subTest(reason=reason):
                self.store({"state": "failed", "reason": reason})
                self.check("NOT-INSTALLED no-install-result")

    def test_requires_the_stored_success_shape(self):
        # A state string alone, an alternate result envelope, or bool-as-int cannot establish success.
        cases = (None, [], PRIVATE, {"result": "installed", "commit": COMMIT},
                 {"state": "already_installed", "commit": COMMIT},
                 {"state": "installed", "commit": COMMIT},
                 {**SUCCESS, "installed_at": None}, {**SUCCESS, "installed_at": ""},
                 {**SUCCESS, "files": True}, {**SUCCESS, "files": 0}, {**SUCCESS, "files": 1.0},
                 {**SUCCESS, "reason": PRIVATE})
        for result in cases:
            with self.subTest(result=result):
                self.store(result)
                self.check("NOT-INSTALLED no-install-result")

    def test_only_full_lowercase_hex_commit_is_accepted(self):
        # Neither short IDs, uppercase, trailing newline nor a fallback to another field is safe.
        for commit in (COMMIT[:12], COMMIT.upper(), COMMIT + "\n", "a" * 64, "g" * 40, None, 42, PRIVATE):
            with self.subTest(commit=commit):
                self.store({**SUCCESS, "commit": commit})
                self.check("NOT-INSTALLED bad-commit")
        self.store({key: value for key, value in SUCCESS.items() if key != "commit"})
        self.check("NOT-INSTALLED bad-commit")

    def test_invalid_ids_cannot_select_existing_files(self):
        # Seed the would-be target so a missing file cannot hide permissive validation.
        for change_id in ("../" + CHANGE_ID, "chg-0123456789aB", "chg-0123456789a",
                          CHANGE_ID + "c", CHANGE_ID + "\n", CHANGE_ID.removeprefix("chg-")):
            with self.subTest(change_id=change_id):
                (self.changes / f"{change_id}.json").write_text(json.dumps({"install": SUCCESS}),
                                                              encoding="utf-8")
                self.check("NOT-INSTALLED missing-record", change_id=change_id)

    def test_refuses_symlinks_and_wrong_file_types(self):
        # Both links point at valid records; FIFOs must be refused without waiting on a writer.
        self.store(SUCCESS)
        target = self.record.rename(self.root / "target.json")
        self.record.symlink_to(target)
        self.check("NOT-INSTALLED missing-record")
        self.record.unlink()
        os.mkfifo(self.record)
        self.check("NOT-INSTALLED missing-record", cli=True)
        self.record.unlink()
        self.record.mkdir()
        self.check("NOT-INSTALLED missing-record")
        self.record.rmdir()
        actual = self.changes.rename(self.root / "actual")
        target.rename(actual / self.record.name)
        self.changes.symlink_to(actual, target_is_directory=True)
        self.check("NOT-INSTALLED missing-record")
        self.changes.unlink()
        self.check("NOT-INSTALLED missing-record")
        self.changes.touch()
        self.check("NOT-INSTALLED missing-record")

    def test_strict_json_rejects_ambiguous_or_broken_records(self):
        # Permissive JSON would report success despite duplicated keys or non-JSON values.
        good = json.dumps({"install": SUCCESS})[:-1].encode()
        for tail in (b',"install":' + json.dumps(SUCCESS).encode() + b'}',
                     rb',"private":{"synthetic-private-marker":0,"synthetic-private-\u006darker":1}}',
                     b',"private":"synthetic-private-marker\xff"}', b'} synthetic-private-marker',
                     b',"private":NaN}', b',"private":Infinity}', b',"private":-Infinity}', b''):
            with self.subTest(tail=tail):
                self.record.write_bytes(good + tail)
                self.check("NOT-INSTALLED missing-record")
        for document in ([{"install": SUCCESS}], None, PRIVATE, 0, True):
            with self.subTest(document=document):
                self.record.write_text(json.dumps(document), encoding="utf-8")
                self.check("NOT-INSTALLED missing-record")


if __name__ == "__main__":
    unittest.main()
