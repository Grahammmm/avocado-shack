"""Offline tests for the loopback-isolation decision in scripts/hass/mac_setup_check.sh.

Fake lsof/curl executables live in a temp dir. Only the isolation lines are asserted: other
checks in the script are macOS-specific and fail on Linux, so this is NOT a whole-script pass.
"""
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hass" / "mac_setup_check.sh"
HEADER = "COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
ISOLATION = re.compile(r"loopback only|beyond loopback|verify loopback-only")
CANARY = "canaryproc"


def row(name, proc=CANARY, user="canaryuser"):
    return f"{proc} 4242 {user} 20u IPv4 0x1 0t0 TCP {name} (LISTEN)\n"


class IsolationTests(unittest.TestCase):
    def run_check(self, listing, rc=0):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "out.txt").write_text(listing)
            for name, body in (
                ("lsof", f'#!/bin/sh\ncat "{tmp}/out.txt"\nexit {rc}\n'),
                ("curl", "#!/bin/sh\nprintf 200\n"),
            ):
                f = tmp / "bin" / name
                f.parent.mkdir(exist_ok=True)
                f.write_text(body)
                f.chmod(f.stat().st_mode | stat.S_IXUSR)
            env = dict(os.environ, HOME=str(tmp), BB_PORT="1234",
                       PATH=f"{tmp / 'bin'}:{os.environ['PATH']}")
            p = subprocess.run(["bash", str(SCRIPT)], env=env, cwd=tmp, text=True,
                               capture_output=True, timeout=60)
            lines = [l for l in p.stdout.splitlines() if ISOLATION.search(l)]
            self.assertEqual(len(lines), 1, p.stdout)
            self.assertNotIn("Traceback", p.stdout + p.stderr)
            return lines[0], p.stdout + p.stderr

    def assert_unknown(self, listing, rc=0):
        line, _ = self.run_check(listing, rc)
        self.assertTrue(line.startswith("FAIL"), line)
        self.assertIn("cannot see a listener", line)

    def test_header_only_cannot_certify_isolation(self):
        self.assert_unknown(HEADER)

    def test_failed_acquisition_with_loopback_row_is_unknown(self):
        self.assert_unknown(HEADER + row("127.0.0.1:1234"), rc=1)

    def test_empty_or_malformed_listing_is_unknown(self):
        good = row("127.0.0.1:1234")
        for listing in (
            "",
            good,  # missing header
            "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE\n" + good,  # no NAME column
            HEADER + "garbage line\n",
            HEADER + row("127.0.0.1"),  # no port delimiter
            HEADER + good + "short row\n",  # good row must not mask a bad one
            HEADER + good.replace("(LISTEN)", "(ESTABLISHED)"),
        ):
            with self.subTest(listing=listing):
                self.assert_unknown(listing)

    def test_supported_loopback_rows_remain_pass(self):
        names = ("127.0.0.1:1234", "[::1]:1234", "localhost:1234")
        combos = [(n,) for n in names] + [names]
        for combo in combos:
            with self.subTest(combo=combo):
                line, _ = self.run_check(HEADER + "".join(row(n) for n in combo))
                self.assertEqual(line, "PASS  port 1234 is loopback only (as the runbook wants)")

    def test_one_nonloopback_row_prevents_pass(self):
        for bad in ("*:1234", "10.0.0.5:1234", "[::]:1234"):
            for order in (0, 1):
                rows = [row("127.0.0.1:1234"), row(bad)]
                if order:
                    rows.reverse()
                with self.subTest(bad=bad, order=order):
                    line, _ = self.run_check(HEADER + "".join(rows))
                    self.assertTrue(line.startswith("FAIL"), line)
                    self.assertIn("beyond loopback", line)

    def test_diagnostics_do_not_echo_listener_data(self):
        listings = [
            (HEADER + row("203.0.113.9:1234"), 0),
            (HEADER + row("127.0.0.1:1234"), 1),
            (HEADER + row("203.0.113.9"), 0),
        ]
        for listing, rc in listings:
            with self.subTest(rc=rc):
                _, everything = self.run_check(listing, rc)
                for canary in ("203.0.113.9", CANARY, "canaryuser", "4242"):
                    self.assertNotIn(canary, everything)


if __name__ == "__main__":
    unittest.main()
