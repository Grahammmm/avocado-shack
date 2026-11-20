"""Fixture-only contract for the saved stdout verdict, not the preflight producer."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.hass.install_preflight_verdict import after_verdict, before_verdict, main


ON = {"npp": True, "houseRender": True, "photo_polish": True}


def report(*, after=False):
    return {
        "status": "READY", "present": ["stage.py"], "missing": [],
        "pins": {"manifest_present": True, "checked": 2, "mismatches": []},
        "allowlist_count": 0,
        "skills": {"present": ["SKILL.md"], "missing": []},
        "acceptance_fail_0": True,
        "switches": {"current": dict(ON) if after else {"npp": False},
                     "proposed": dict(ON), "diff": [] if after else [
                         '- "npp": false', '+ "npp": true', '+ "houseRender": true', '+ "photo_polish": true',
                     ]},
    }


def capture(obj):
    return json.dumps(obj).encode() + b"\nSynthetic human-readable summary\n"


class VerdictTests(unittest.TestCase):
    def test_first_line_and_process_status_are_authoritative(self):
        # A banner or a later READY object must not rescue a bad first line or failed process.
        good = capture(report())
        def check(raw, status: object = 0):
            return before_verdict(raw, status, default_off_confirmed=True)

        self.assertEqual(check(good), "PASS")
        for bad in (b"", b"\n" + good, b"banner\n" + good, b"[]\n" + good, b"\xff\n" + good,
                    good.replace(b'"status":', b'"status":"NOT-READY","status":', 1),
                    good.replace(b'"allowlist_count": 0', b'"allowlist_count": NaN', 1)):
            with self.subTest(bad=bad[:24]):
                self.assertEqual(check(bad), "FAIL: invalid first JSON line")
        for status in (3, None, False):
            with self.subTest(status=status):
                self.assertEqual(check(good, status), "FAIL: preflight exit status")

    def test_ready_headline_does_not_override_readiness_fields(self):
        # A valid-looking headline cannot mask missing, dirty, or wrongly typed evidence.
        cases = (
            ("status", "NOT-READY", "preflight not READY"),
            ("missing", ["stage.py"], "incomplete stages"),
            ("missing", None, "incomplete stages"),
            ("present", [], "incomplete stages"),
            ("skills", {"present": ["SKILL.md"], "missing": ["other.md"]}, "incomplete skills"),
            ("skills", {}, "incomplete skills"),
            ("pins", None, "pins not verified"),
            ("pins", {"manifest_present": 1, "mismatches": [], "checked": 2}, "pins not verified"),
            ("pins", {"manifest_present": True, "mismatches": ["fixture"], "checked": 2}, "pins not verified"),
            ("pins", {"manifest_present": True, "mismatches": [], "checked": 0}, "pins not verified"),
            *(("allowlist_count", value, "invalid allowlist count") for value in (None, False, -1, 1.0, "1")),
            *(("acceptance_fail_0", value, "acceptance not confirmed") for value in (None, False, 1, 1.0, "true")),
        )
        for key, value, reason in cases:
            with self.subTest(field=key, value=value):
                self.assertEqual(before_verdict(capture({**report(), key: value}), 0, default_off_confirmed=True),
                                 f"FAIL: {reason}")
        missing = report()
        del missing["acceptance_fail_0"]
        self.assertEqual(before_verdict(capture(missing), 0, default_off_confirmed=True),
                         "FAIL: acceptance not confirmed")

    def test_before_uses_current_npp_and_requires_independent_evidence(self):
        # Proposed true is normal before switching; missing current NPP is not its own proof.
        for current, confirmed, verdict in (
            ({"npp": False}, True, "PASS"), ({}, True, "PASS"),
            ({"npp": False}, False, "FAIL: default-off not confirmed"),
            ({}, False, "FAIL: default-off not confirmed"),
            ({}, 1, "FAIL: default-off not confirmed"),
            ({"npp": True}, True, "FAIL: NPP already on"),
            ({"npp": None}, True, "FAIL: invalid current switches"),
            ({"npp": 0}, True, "FAIL: invalid current switches"),
            (None, True, "FAIL: invalid current switches"),
        ):
            with self.subTest(current=current, confirmed=confirmed):
                before = report()
                before["switches"]["current"] = current
                self.assertEqual(before_verdict(capture(before), 0, default_off_confirmed=confirmed), verdict)

    def test_after_uses_current_switches_and_requires_explicit_empty_diff(self):
        # An all-true proposal and an empty diff cannot stand in for actual readback.
        before = capture(report())
        for key in ON:
            for value in (False, "absent", 1):
                with self.subTest(key=key, value=value):
                    after = report(after=True)
                    if value == "absent":
                        del after["switches"]["current"][key]
                    else:
                        after["switches"]["current"][key] = value
                    expected = "FAIL: invalid current switches" if type(value) is int else "FAIL: current switches not all on"
                    self.assertEqual(after_verdict(capture(after), 0, before_stdout=before, before_exit_status=0,
                                                   default_off_confirmed=True), expected)
        for diff in (None, "", ["fixture"]):
            with self.subTest(diff=diff):
                after = report(after=True)
                after["switches"]["diff"] = diff
                self.assertEqual(after_verdict(capture(after), 0, before_stdout=before, before_exit_status=0,
                                               default_off_confirmed=True), "FAIL: switch diff not empty")

    def test_after_requires_passing_baseline_and_unchanged_readiness(self):
        # Two READY headlines are insufficient: each capture must pass, with no reported drift.
        before = capture(report())
        after = report(after=True)
        for raw, status, confirmed in ((before, 3, True), (before, 0, False), (capture(after), 0, True),
                                        (capture({**report(), "acceptance_fail_0": None}), 0, True)):
            with self.subTest(status=status, confirmed=confirmed, raw=raw):
                self.assertEqual(after_verdict(capture(after), 0, before_stdout=raw, before_exit_status=status,
                                               default_off_confirmed=confirmed), "FAIL: before report did not pass")
        def check(candidate, status=0):
            return after_verdict(capture(candidate), status, before_stdout=before, before_exit_status=0,
                                 default_off_confirmed=True)

        self.assertEqual(check(after), "PASS")
        self.assertEqual(check(after, 3), "FAIL: preflight exit status")
        self.assertEqual(check({**after, "acceptance_fail_0": None}), "FAIL: acceptance not confirmed")
        for key, value in (("allowlist_count", 1), ("present", ["replacement.py"]),
                           ("skills", {"present": ["other.md"], "missing": []}),
                           ("pins", {"manifest_present": True, "checked": 3, "mismatches": []})):
            with self.subTest(key=key):
                self.assertEqual(check({**after, key: value}), "FAIL: readiness changed")

    def test_cli_reads_saved_first_lines_and_emits_only_fixed_reasons(self):
        # Diagnostics/filenames must not leak and passing fixtures must remain untouched.
        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "before.out"
            after = Path(tmp) / "after.out"
            before.write_bytes(capture(report()) + b"\xfffixture diagnostic")
            after.write_bytes(capture(report(after=True)))
            original = {p: p.read_bytes() for p in (before, after)}
            common = ["--exit-status", "0", "--default-off-confirmed"]
            for args, status, expected in (
                (["before", "--stdout", str(before), *common], 0, "PASS"),
                (["after", "--stdout", str(after), *common, "--before-stdout", str(before),
                  "--before-exit-status", "0"], 0, "PASS"),
                (["before", "--stdout", str(before)], 2, "FAIL: invalid arguments"),
                (["before", "--stdout", str(Path(tmp) / "absent"), *common], 1, "FAIL: could not read saved stdout"),
            ):
                with self.subTest(status=status, expected=expected):
                    out, err = io.StringIO(), io.StringIO()
                    with redirect_stdout(out), redirect_stderr(err):
                        if status == 2:
                            with self.assertRaises(SystemExit) as exc:
                                main(args)
                            self.assertEqual(exc.exception.code, status)
                        else:
                            self.assertEqual(main(args), status)
                    self.assertEqual((out.getvalue(), err.getvalue()),
                                     ("", expected + "\n") if status == 2 else (expected + "\n", ""))
            self.assertEqual({p: p.read_bytes() for p in Path(tmp).iterdir()}, original)
