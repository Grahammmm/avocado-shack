"""Fixture-only coverage of the saved quiescence snapshot CLI."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.hass import install_quiescence


def observations() -> list[dict[str, object]]:
    return [
        dict(unit="hass-health.timer", exit_code=3, stdout="inactive\n", stderr=""),
        dict(unit="hass-receiver.service", exit_code=3, stdout="inactive\n", stderr=""),
        dict(unit="hass-worker.service", exit_code=3, stdout="inactive\n", stderr=""),
        dict(unit="hass-health.service", exit_code=3, stdout="inactive", stderr=""),
    ]


class InstallQuiescenceTests(unittest.TestCase):
    def verdict(self, payload, expected):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            if payload is not None:
                path.write_bytes(payload)
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = install_quiescence.main([str(path)])
            self.assertEqual(code, expected)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(len(stdout.getvalue().splitlines()), 1)
            self.assertTrue(stdout.getvalue().startswith("PASS:" if expected == 0 else "FAIL:"))
            self.assertIn("saved snapshot", stdout.getvalue())
            self.assertNotIn("fixture-marker", stdout.getvalue())

    def check_rows(self, rows, expected=1):
        self.verdict(json.dumps(rows).encode(), expected)

    def test_complete_snapshot_passes_in_any_order(self):
        # Requiring a particular capture order would reject valid evidence.
        self.check_rows(observations(), expected=0)
        self.check_rows(list(reversed(observations())), expected=0)

    def test_inactive_timer_cannot_stand_in_for_health_service(self):
        # A stopped timer can leave its triggered service running.
        rows = observations()
        self.check_rows(rows[:-1])
        rows[-1].update(exit_code=0, stdout="active\n")
        self.check_rows(rows)

    def test_each_observation_requires_literal_inactive_and_exit_three(self):
        # Exit 3 alone can describe failed/transitional states; text alone can
        # mask an absent unit or a command error.
        for changes in (
            {"stdout": "failed\n"}, {"stdout": "activating\n"},
            {"exit_code": 4, "stdout": "unknown\n"}, {"exit_code": 4},
            {"exit_code": 1}, {"exit_code": "3"}, {"exit_code": 3.0},
            {"stdout": " inactive\n"}, {"stdout": "inactive\ninactive\n"},
            {"stderr": "fixture-marker"},
        ):
            with self.subTest(changes=changes):
                rows = observations()
                rows[2].update(changes)
                self.check_rows(rows)

    def test_duplicate_or_unexpected_unit_is_not_evidence(self):
        # Neither a four-row count nor ignoring surplus rows proves uniqueness.
        rows = observations()
        self.check_rows(rows[:-1] + [rows[0]])
        self.check_rows(rows + [rows[0]])
        rows[-1]["unit"] = "other.service"
        self.check_rows(rows)

    def test_ambiguous_or_missing_saved_data_fails_closed(self):
        # Ordinary JSON loading would silently keep the last duplicate key.
        rows = observations()
        good = json.dumps(rows).encode()
        duplicate = good.replace(b'"exit_code": 3', b'"exit_code": 0, "exit_code": 3', 1)
        for payload in (duplicate, good + good, b"fixture-marker", b"\xff", None):
            with self.subTest(payload=payload):
                self.verdict(payload, 1)
        del rows[0]["stderr"]
        self.check_rows(rows)
        rows[0].update(stderr="", other="fixture-marker")
        self.check_rows(rows)
