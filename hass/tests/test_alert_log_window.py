"""Offline behavioral contracts for the copied Hass alert log reader."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/alert_log_window.py"
SPEC = importlib.util.spec_from_file_location("alert_log_window", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)

SINCE = "2030-04-05T10:00:00Z"
UNTIL = "2030-04-05T11:00:00Z"
PASS = "PASS alert_log_window"
FAIL = "FAIL alert_log_window"


class AlertLogWindowTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.log = self.root / "fixture-alerts.log"

    def invoke(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = READER.main(list(argv))
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def run_window(self, since=SINCE, until=UNTIL):
        return self.invoke("--log", str(self.log), "--since", since, "--until", until)

    def assert_result(self, result, exit_code, summary):
        code, stdout, stderr = result
        self.assertEqual(code, exit_code, stderr)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(lines[-1:], [summary])
        return lines

    def test_c1_full_pass(self):
        # Taking the last physical prior row would miss the newest prior alert.
        self.log.write_bytes(
            b"2030-04-05T09:55:00Z HASS-HEALTH 012345abcdef check-one check-two\n"
            b"synthetic other event\n"
            b"2030-04-05T09:50:00Z HASS-HEALTH 123456abcdef check-three\n"
            b"2030-04-05T11:15:00Z HASS-HEALTH 234567abcdef check-four\n"
        )
        self.assertEqual(self.assert_result(self.run_window(), 0, PASS), [
            "last-before 2030-04-05T09:55:00Z 012345abcdef check-one check-two",
            "note other-lines 1",
            PASS,
        ])

    def test_c2_1_no_log(self):
        # Missing files and directories must not be treated as clean logs.
        for directory in (False, True):
            with self.subTest(directory=directory):
                if directory:
                    self.log.mkdir()
                self.assertEqual(self.assert_result(self.run_window(), 1, FAIL), [
                    "FAIL no-log", FAIL,
                ])

    def test_c2_2_bad_window(self):
        # A naive timestamp or empty/reversed window must not silently pass.
        self.log.write_bytes(b"")
        for since, until in (
            ("not-an-iso-time", UNTIL),
            ("2030-04-05T10:00:00", UNTIL),
            (SINCE, "2030-04-05T11:00:00"),
            (SINCE, "2030-04-05T12:00:00+02:00"),
            (UNTIL, SINCE),
        ):
            with self.subTest(since=since, until=until):
                lines = self.assert_result(self.run_window(since, until), 1, FAIL)
                self.assertEqual([line for line in lines if line.startswith("FAIL ")], [
                    "FAIL bad-window", FAIL,
                ])

    def test_c2_3_bad_line(self):
        # Check all marked rows (even outside the window) and use physical line numbers.
        self.log.write_bytes(
            b"synthetic unmarked line\n"
            b"2030-04-05T09:30:00Z HASS-HEALTH 012345ABCDEF check-one\n"
            b"2030-04-31T10:30:00Z HASS-HEALTH 012345abcdef check-two\n"
            b"2030-04-05T10:30:00Z HASS-HEALTH 012345abcdef\x20\n"
            b"2030-04-05T12:30:00Z HASS-HEALTH 012345abcdef check-three \n"
        )
        self.assertEqual(self.assert_result(self.run_window(), 1, FAIL), [
            "FAIL bad-line 2", "FAIL bad-line 3", "FAIL bad-line 4", "FAIL bad-line 5",
            "last-before none", "note other-lines 1", FAIL,
        ])

    def test_c2_4_alert_in_window(self):
        # Do not stop at the first in-window alert or deduplicate identical rows.
        self.log.write_bytes(
            b"2030-04-05T10:30:00Z HASS-HEALTH 012345abcdef check-one check-two\n" * 2
        )
        self.assertEqual(self.assert_result(self.run_window(), 1, FAIL), [
            "alert 2030-04-05T10:30:00Z 012345abcdef check-one check-two",
            "alert 2030-04-05T10:30:00Z 012345abcdef check-one check-two",
            "last-before none", "note other-lines 0", "FAIL alert-in-window 2", FAIL,
        ])

    def test_c3_usage_exit_2(self):
        # Usage errors must not get the health-finding exit or a stdout verdict.
        required = ("--log", str(self.log), "--since", SINCE, "--until", UNTIL)
        for argv in (required[:-2], required + ("--unknown",), required[:-1]):
            with self.subTest(argv=argv):
                code, stdout, stderr = self.invoke(*argv)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertTrue(stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # Catch rewrites (even of identical bytes) and sidecar files/directories.
        raw = b"synthetic event\r\n\xff\n"
        self.log.write_bytes(raw)
        before = self.log.stat().st_mtime_ns
        self.assert_result(self.run_window(), 0, PASS)
        self.assertEqual(self.log.read_bytes(), raw)
        self.assertEqual(self.log.stat().st_mtime_ns, before)
        self.assertEqual(list(self.root.iterdir()), [self.log])

    def test_c5_no_private_values(self):
        # Neither skipped rows, rejected rows, nor argparse diagnostics may echo input.
        message = "synthetic message canary"
        chat = "synthetic-chat-canary"
        sender = "synthetic-sender-canary"
        identifier = "synthetic-full-id-canary"
        digest = "012345abcdef" + "a" * 52
        path = str(self.log)
        self.log.write_text(
            f"{message} {chat} {sender} {identifier} {path}\n"
            f"{SINCE} HASS-HEALTH {digest} check-one\n"
            f"{SINCE} HASS-HEALTH {digest[:12]} check-one\n",
            encoding="utf-8",
        )
        result = self.run_window()
        self.assertEqual(self.assert_result(result, 1, FAIL), [
            "FAIL bad-line 2", "alert 2030-04-05T10:00:00Z 012345abcdef check-one",
            "last-before none", "note other-lines 1", "FAIL alert-in-window 1", FAIL,
        ])
        usage = self.invoke("--log", path, "--since", SINCE, "--until", UNTIL, path)
        self.assertEqual(usage[:2], (2, ""))
        for value in (message, chat, sender, identifier, digest, path):
            with self.subTest(value=value):
                self.assertNotIn(value, result[1] + result[2])
                self.assertNotIn(value, usage[1] + usage[2])

    def test_c6_window_edges(self):
        # Nonzero offsets make string ordering wrong; compare the represented instants.
        self.log.write_bytes(
            b"2030-04-05T10:00:00Z HASS-HEALTH 012345abcdef check-one\n"
            b"2030-04-05T11:00:00Z HASS-HEALTH 123456abcdef check-two\n"
        )
        lines = self.assert_result(
            self.run_window("2030-04-05T12:00:00+02:00", "2030-04-05T06:00:00-05:00"),
            1, FAIL,
        )
        self.assertEqual(lines, [
            "alert 2030-04-05T10:00:00Z 012345abcdef check-one",
            "last-before none", "note other-lines 0", "FAIL alert-in-window 1", FAIL,
        ])
