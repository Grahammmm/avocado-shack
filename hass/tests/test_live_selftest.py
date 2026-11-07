"""HASS-LIVE-AUDIT-1: scripts/hass/live_selftest.sh --synthetic-only (scripts/hass/live_selftest_synth.py) passes on
this checkout; scripts/hass/live_selftest_model.py refuses an unknown case id before any model call; and the full
(live) mode, run against fake git/systemctl/journalctl and fake health/inbox output in a temp dir, FAILs when an
acquisition fails (health crash, git exit 128, journalctl exit 1) instead of reporting clean/healthy/zero, while the
valid controls (clean git, backup-age-only health, an empty successful journal query) still pass or warn.
Run: python3 -B -m unittest hass.tests.test_live_selftest"""

import os, shutil, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "hass"
ENV = {"HASS_PYTHON": sys.executable, "PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
if os.environ.get("TMPDIR"):
    ENV["TMPDIR"] = os.environ["TMPDIR"]  # child temp files stay in the configured scratch dir

# Stand-ins, selected by the PROBE_* variables. The fake interpreter answers for the synthetic helper, health.py and
# inbox.py and hands every other script (the real live_selftest_parse.py) to the real interpreter.
FAKE_PY = f"""#!{sys.executable}
import os, sys
script = sys.argv[2] if len(sys.argv) > 2 else ""
health = os.environ.get("PROBE_HEALTH", "ok")
if script.endswith("live_selftest_synth.py"):
    print('{{"failed": 0, "ran": 6, "synthetic": "pass"}}')
elif script.endswith("health.py"):
    if health == "crash":
        print("Traceback (most recent call last): simulated crash", file=sys.stderr)
        sys.exit(1)
    if health == "backup-age":
        print('{{"ok": false, "problems": [{{"check": "backup-age", "detail": "x"}}], "info": {{}}, "fingerprint": "f"}}')
        sys.exit(1)
    print('{{"ok": true, "problems": [], "info": {{}}, "fingerprint": "f"}}')
elif script.endswith("inbox.py"):
    print('{{"pending": 0, "done": 3, "history": 3, "oldest_pending_minutes": null}}')
else:
    os.execv({sys.executable!r}, [{sys.executable!r}] + sys.argv[1:])
"""
FAKE_GIT = """#!/bin/sh
[ "${PROBE_GIT:-ok}" = fail ] && exit 128
case "$*" in *rev-parse*) echo 0123456789ab ;; esac
exit 0
"""
FAKE_SYSTEMCTL = """#!/bin/sh
case "$*" in
  *is-active*) echo active ;;
  *NRestarts*) echo 0 ;;
  *LastTriggerUSec*)
    case "${PROBE_TIMER:-ok}" in fail) exit 1 ;; never) echo 'n/a' ;; *) echo 'Sat 2026-11-07 14:40:03 PST' ;; esac ;;
  *ExecMainStatus*) echo 0 ;;
esac
"""
FAKE_JOURNALCTL = """#!/bin/sh
case "${PROBE_JOURNAL:-empty}" in fail) exit 1 ;; lines) printf 'a\\nb\\nc\\n' ;; esac
exit 0
"""


FAKE_DU = """#!/bin/sh
case "${PROBE_DU:-ok}" in partial) echo "123	$2"; exit 1 ;; esac
exec /usr/bin/du "$@"
"""
FAKE_DF = """#!/bin/sh
case "${PROBE_DF:-ok}" in partial) printf 'Filesystem 1M-blocks Used Available Capacity Mounted\\nx 10 1 9999 1%% /\\n'; exit 1 ;; esac
exec /usr/bin/df "$@"
"""


class LiveSelftestScript(unittest.TestCase):
    def test_synthetic_only_passes_and_touches_no_live_path(self):
        r = subprocess.run(["bash", str(SCRIPTS / "live_selftest.sh"), "--synthetic-only"], capture_output=True, text=True,
                           timeout=600, env=ENV, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('PASS synthetic {"failed": 0, "ran": 6, "synthetic": "pass"}', r.stdout)
        self.assertRegex(r.stdout, r"HASS-SELFTEST \S+Z pass=1 warn=0 fail=0 skip=0\n$")

    def test_model_helper_refuses_an_unknown_case_without_calling_a_model(self):
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "live_selftest_model.py"), "--url", "http://127.0.0.1:9",
                            "--model", "m", "--ids", "nope"], capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertEqual((r.returncode, r.stdout.strip()), (2, '{"result": "error", "error": "--ids: unknown case id"}'))


class LiveModeAcquisitionFailures(unittest.TestCase):
    """The live checks, isolated: fakes on PATH, a temp state root with a fresh backup, a temp growth file."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hass-selftest-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        bins = self.tmp / "bin"
        bins.mkdir()
        for name, body in (("python", FAKE_PY), ("git", FAKE_GIT), ("systemctl", FAKE_SYSTEMCTL),
                           ("journalctl", FAKE_JOURNALCTL), ("du", FAKE_DU), ("df", FAKE_DF)):
            (bins / name).write_text(body)
            (bins / name).chmod(0o700)
        self.state = self.tmp / "hass"
        (self.state / "backups").mkdir(parents=True)
        (self.state / "backups" / "hass-state-synthetic.tar").write_text("x")
        self.growth = self.tmp / "growth.tsv"
        self.env = dict(ENV, PATH=f"{bins}:/usr/bin:/bin", HASS_PYTHON=str(bins / "python"))

    def run_live(self, **probes):
        r = subprocess.run(["bash", str(SCRIPTS / "live_selftest.sh"), "--state-root", str(self.state),
                            "--growth-file", str(self.growth), "--min-free-mb", "1"],
                           capture_output=True, text=True, timeout=120, env=dict(self.env, **probes), cwd=self.tmp)
        lines = {ln.split(" ", 2)[1]: ln for ln in r.stdout.splitlines() if ln[:5] in ("PASS ", "WARN ", "FAIL ", "SKIP ")}
        return r, lines

    def test_valid_controls_pass(self):
        r, lines = self.run_live()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(lines["runtime"], "PASS runtime checkout 0123456789ab clean")
        self.assertEqual(lines["runtime-after"], "PASS runtime-after still clean")
        self.assertEqual(lines["health"], "PASS health no problems")
        self.assertEqual(lines["inbox"], "PASS inbox pending 0, done 3")
        self.assertRegex(lines["growth"], r"^PASS growth state \d+ KB, free \d+ MB, hass journal 0 lines/24h$")
        self.assertRegex(self.growth.read_text(), r"^\d+ \d+ \d+ 0\n$")
        self.assertRegex(r.stdout, r"pass=11 warn=0 fail=0 skip=1\n$")

    def test_backup_age_only_health_is_a_warning(self):
        r, lines = self.run_live(PROBE_HEALTH="backup-age", PROBE_JOURNAL="lines")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(lines["health"], "WARN health problems: backup-age")
        self.assertIn("hass journal 3 lines/24h", lines["growth"])

    def test_health_crash_fails(self):
        r, lines = self.run_live(PROBE_HEALTH="crash")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(lines["health"].startswith("FAIL health health.py exit 1 without a valid report"), lines["health"])
        self.assertNotIn("Traceback", r.stdout)
        self.assertIn("failed:health", r.stdout)

    def test_git_failure_is_not_clean(self):
        r, lines = self.run_live(PROBE_GIT="fail")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(lines["runtime"], "FAIL runtime cannot read the checkout head (git rev-parse exit 128)")
        self.assertEqual(lines["runtime-after"], "FAIL runtime-after checkout state unknown (git status exit 128)")
        self.assertNotIn("clean", lines["runtime"] + lines["runtime-after"])

    def test_journal_failure_is_not_zero_lines(self):
        self.growth.write_text("1 2 3 4\n")
        r, lines = self.run_live(PROBE_JOURNAL="fail")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(lines["growth"].startswith("FAIL growth "), lines["growth"])
        self.assertIn("hass journal unknown lines/24h", lines["growth"])
        self.assertIn("not measured: hass journal (journalctl exit 1)", lines["growth"])
        self.assertNotIn("journal 0 lines", lines["growth"])
        self.assertEqual(self.growth.read_text(), "1 2 3 4\n")  # the previous baseline is kept

    def test_du_partial_total_with_nonzero_exit_fails_and_keeps_baseline(self):
        self.growth.write_text("1 2 3 4\n")
        r, lines = self.run_live(PROBE_DU="partial")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(lines["growth"].startswith("FAIL growth "), lines["growth"])
        self.assertIn("not measured: state size (du exit 1)", lines["growth"])
        self.assertIn("state unknown KB", lines["growth"])
        self.assertEqual(self.growth.read_text(), "1 2 3 4\n")

    def test_df_partial_output_with_nonzero_exit_fails_and_keeps_baseline(self):
        self.growth.write_text("1 2 3 4\n")
        r, lines = self.run_live(PROBE_DF="partial")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not measured: free disk (df exit 1)", lines["growth"])
        self.assertEqual(self.growth.read_text(), "1 2 3 4\n")

    def test_timer_query_failure_fails_but_never_triggered_timer_only_warns(self):
        r, lines = self.run_live(PROBE_TIMER="fail")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(lines["timer:hass-health"], "FAIL timer:hass-health last trigger query failed (systemctl exit 1)")
        self.assertIn("failed:timer:hass-health,timer:hass-backup", r.stdout)
        r, lines = self.run_live(PROBE_TIMER="never")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(lines["timer:hass-health"], "WARN timer:hass-health active, has not run yet")


if __name__ == "__main__":
    unittest.main()
