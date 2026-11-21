"""Offline CLI contracts for the private findings ledger."""

from contextlib import ExitStack, redirect_stdout
import csv
import fcntl
import io
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.hass import npp_findings


SCRIPT = Path(npp_findings.__file__).resolve()
WEEK = "2099-W02"
HEADER = "id\tweek\tstage\tclass\tsummary\tcase_id\tcard\tstate\treason\n"


class FindingsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.ledger = self.root / "findings.tsv"

    def command(self, *args):
        return [sys.executable, "-B", str(SCRIPT), "--ledger", str(self.ledger), *args]

    def cli(self, *args, code=0):
        result = subprocess.run(self.command(*args), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, code, (result.stdout, result.stderr))
        return result.stdout.splitlines()

    @staticmethod
    def add_args(week=WEEK, stage="S1", kind="preview-fallback", summary="Preview fell back"):
        return ("add", "--week", week, "--stage", stage, "--class", kind, "--summary", summary)

    def add(self, **kwargs):
        finding, = self.cli(*self.add_args(**kwargs))
        return finding

    def rows(self):
        with self.ledger.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    def test_c1_add_refuses_private(self):
        # A partial redaction rule or TSV field injection must never reach storage.
        self.cli(*self.add_args(summary="Unredacted @ sentinel"), code=1)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.add(summary="Résumé redacted <n> + fallback"), f"F-{WEEK}-1")
        self.assertEqual(self.add(stage="S13"), f"F-{WEEK}-2")
        self.assertEqual(self.add(week="2099-W03"), "F-2099-W03-1")
        self.assertEqual(self.add(), f"F-{WEEK}-3")
        self.assertTrue(self.ledger.read_text(encoding="utf-8").startswith(HEADER))
        self.assertEqual(stat.S_IMODE(self.ledger.stat().st_mode), 0o600)
        self.assertEqual(self.rows()[0], dict(
            id=f"F-{WEEK}-1", week=WEEK, stage="S1", summary="Résumé redacted <n> + fallback",
            case_id="", card="", state="open", reason="", **{"class": "preview-fallback"},
        ))
        original = self.ledger.read_bytes()
        for char in (*"0123456789", "@", "$", "+1", "\u0661", "\u00b2", "\t", "\n", "\r"):
            summary = f"Unredacted{char}sentinel"
            with self.subTest(char=char):
                self.assertEqual(self.cli(*self.add_args(summary=summary), code=1),
                                 ["FAIL summary must be redacted and on one line"])
                self.assertEqual(self.ledger.read_bytes(), original)
        for overrides in ({"week": "2099-W00"}, {"week": "2099-W54"}, {"week": "2099-W2"},
                          {"stage": "S0"}, {"stage": "S14"}, {"kind": "not a slug"}):
            with self.subTest(overrides=overrides):
                self.cli(*self.add_args(**overrides), code=1)
                self.assertEqual(self.ledger.read_bytes(), original)

    def test_c2_close_rules(self):
        # Missing card or ambiguous/invalid evidence must not mutate the finding.
        finding = self.add()
        original = self.ledger.read_bytes()
        for args, code in (([], 2), (["--card", "card-demo"], 2),
                           (["--case", "case-99-fixture.json"], 2),
                           (["--case", "case-99-fixture.json", "--reason", "duplicate",
                             "--card", "card-demo"], 2),
                           (["--case", "./case-99-fixture.json", "--card", "card-demo"], 1),
                           (["--case", "npp-demo", "--card", "card-demo"], 1),
                           (["--reason", "chat note", "--card", "card-demo"], 1),
                           (["--reason", "duplicate", "--card", ""], 1)):
            with self.subTest(args=args):
                self.cli("close", finding, *args, code=code)
                self.assertEqual(self.ledger.read_bytes(), original)
        self.cli("close", f"F-{WEEK}-99", "--reason", "duplicate", "--card", "card-demo", code=1)
        self.assertEqual(self.ledger.read_bytes(), original)
        closures = [("--case", "case-99-fixture.json"), ("--case", "npp-20990101-1"),
                    ("--reason", "fixture-only")]
        for index, (flag, value) in enumerate(closures):
            if index:
                finding = self.add(kind=f"fixture-{index}")
            self.assertEqual(self.cli("close", finding, flag, value, "--card", "card-demo"), [finding])
            row = next(row for row in self.rows() if row["id"] == finding)
            self.assertEqual((row["case_id"], row["card"], row["state"], row["reason"]),
                             (value if flag == "--case" else "", "card-demo", "closed",
                              value if flag == "--reason" else ""))

        original = self.ledger.read_bytes()
        self.cli("close", f"F-{WEEK}-1", "--reason", "overwrite", "--card", "card-demo", code=1)
        self.assertEqual(self.ledger.read_bytes(), original)

    def test_c3_repeat(self):
        # An open match is not a repeat; a closed exact class matches across weeks/stages.
        first = self.add()
        self.add(stage="S2")
        self.assertEqual([row["state"] for row in self.rows()], ["open", "open"])
        self.cli("close", first, "--reason", "fixture-only", "--card", "card-demo")
        repeat = self.add(week="2099-W03", stage="S13")
        self.add(week="2099-W03", kind="preview-fallback-other")
        self.add(week="2099-W03", kind="preview")
        self.add(week="2099-W03", stage="S2")
        self.assertEqual([row["state"] for row in self.rows()],
                         ["closed", "open", "repeat", "open", "open", "repeat"])
        self.cli("close", repeat, "--case", "case-99-fixture.json", "--card", "card-repeat")
        closed_repeat = self.rows()[2]
        self.assertEqual((closed_repeat["state"], closed_repeat["card"], closed_repeat["case_id"]),
                         ("repeat", "card-repeat", "case-99-fixture.json"))
        report = self.cli("report", "--week", "2099-W03")
        self.assertEqual(report[0], "open=4 closed=2 repeat=2")
        self.assertNotIn(repeat, report[1:-1])
        self.cli("close", f"F-{WEEK}-2", "--reason", "fixture-only", "--card", "card-demo")
        self.assertEqual(self.rows()[1]["state"], "closed")  # Not retroactively a repeat.

    def test_c4_report(self):
        # ISO rollover, the exact age boundary, and stale repeat/closed distinctions.
        old = self.add(week="2098-W51")
        self.cli("close", old, "--reason", "fixture-only", "--card", "card-demo")
        repeat = self.add(week="2098-W52")
        newer = self.add(kind="different")
        self.assertEqual(self.cli("report", "--week", "2099-W02"),
                         ["open=2 closed=1 repeat=1", repeat, newer, "PASS npp_findings"])
        self.assertEqual(self.cli("report", "--week", "2099-W03", code=1),
                         ["open=2 closed=1 repeat=1", repeat, newer, "FAIL npp_findings stale"])
        self.cli("close", repeat, "--reason", "fixture-only", "--card", "card-repeat")
        self.assertEqual(self.cli("report", "--week", "2099-W03"),
                         ["open=1 closed=2 repeat=1", newer, "PASS npp_findings"])

    def test_c5_atomic_bad(self):
        # A failed commit must leave complete old bytes, and writers must serialize.
        self.add()
        original = self.ledger.read_bytes()
        entries = set(self.root.iterdir())

        def interrupted_replace(temp, target):
            self.assertEqual(target, self.ledger.resolve())
            self.assertEqual(Path(temp).parent, target.parent)
            self.assertEqual(self.ledger.read_bytes(), original)
            self.assertTrue(Path(temp).read_bytes().startswith(original))
            with (target.parent / f".{target.name}.lock").open("rb") as rival:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raise OSError("simulated replacement failure")

        with patch.object(npp_findings.os, "replace", side_effect=interrupted_replace) as replace:
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(npp_findings.main(["--ledger", str(self.ledger), *self.add_args()]), 1)
            replace.assert_called_once()
        self.assertEqual(output.getvalue().splitlines(), ["FAIL npp_findings ledger I/O"])
        self.assertEqual(self.ledger.read_bytes(), original)
        self.assertEqual(set(self.root.iterdir()), entries)
        old_snapshot = self.enterContext(self.ledger.open("rb"))
        with ExitStack() as stack:
            writers = [stack.enter_context(subprocess.Popen(
                self.command(*self.add_args()), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )) for _ in range(4)]
            results = set()
            for writer in writers:
                stdout, stderr = writer.communicate(timeout=10)
                self.assertEqual(writer.returncode, 0, stderr)
                results.add(stdout.strip())
        self.assertEqual(results, {f"F-{WEEK}-{i}" for i in range(2, 6)})
        self.assertEqual([row["id"] for row in self.rows()], [f"F-{WEEK}-{i}" for i in range(1, 6)])
        self.assertEqual(old_snapshot.read(), original)

        for corrupt, line in ((b"", 1), (b"bad header\n", 1),
                              (original + b"broken\n", 3), (original + b"\xff\n", 3),
                              (original + original.splitlines(keepends=True)[1], 3),
                              (original.replace(b"Preview fell back", b"Not redacted @"), 2),
                              (original.replace(b"\topen\t", b"\tclosed\t"), 2)):
            with self.subTest(line=line, fixture=corrupt):
                self.ledger.write_bytes(corrupt)
                for args in (("report", "--week", WEEK), self.add_args(),
                             ("close", f"F-{WEEK}-1", "--reason", "duplicate", "--card", "card-demo")):
                    self.assertEqual(self.cli(*args, code=1), [f"FAIL bad-ledger {line}"])
                    self.assertEqual(self.ledger.read_bytes(), corrupt)

    def test_c5_refuses_git_worktrees(self):
        # Both ordinary checkout markers and linked-worktree gitfiles are a boundary.
        checkout = self.root / "checkout"
        checkout.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(checkout, target_is_directory=True)
        marker = checkout / ".git"
        marker.mkdir()
        for directory in (checkout, alias):
            self.ledger = directory / "findings.tsv"
            self.assertEqual(self.cli(*self.add_args(), code=1), ["FAIL ledger must be outside Git worktrees"])
        marker.rmdir()
        marker.write_text("gitdir: ../fixture-metadata\n", encoding="utf-8")
        self.assertEqual(self.cli("report", "--week", WEEK, code=1), ["FAIL ledger must be outside Git worktrees"])
        self.assertEqual(list(checkout.iterdir()), [marker])
