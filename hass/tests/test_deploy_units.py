"""HASS-SVC-1: the systemd user unit templates in deploy/hass parse and keep the house rules (fixtures only, no systemd)."""
import configparser
import unittest
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "deploy" / "hass"
RUNTIME = "%h/.local/share/hass/runtime/hass/"
SERVICES = ("hass-receiver", "hass-worker", "hass-health", "hass-backup", "hass-clover-sync", "hass-clover-report")


def parse(name):
    cp = configparser.ConfigParser(interpolation=None, strict=True)
    cp.optionxform = str
    cp.read_string((DIR / name).read_text("utf-8"))
    return cp


class UnitTest(unittest.TestCase):
    def test_every_unit_parses_and_is_in_this_list(self):
        names = sorted(p.name for p in DIR.iterdir())
        self.assertEqual(names, sorted([f"{s}.service" for s in SERVICES] + ["hass-health.timer", "hass-backup.timer", "hass-clover-sync.timer", "hass-clover-report.timer"]))
        for name in names: self.assertTrue(parse(name).sections(), name)

    def test_services_run_from_the_runtime_worktree_with_the_house_rules(self):
        for svc in SERVICES:
            service = parse(f"{svc}.service")["Service"]
            self.assertEqual(service["UMask"], "0077", svc)
            self.assertEqual(service["NoNewPrivileges"], "true", svc)
            self.assertEqual(service["PrivateTmp"], "true", svc)
            exec_ = service["ExecStart"].split()
            self.assertEqual(exec_[:2], ["/usr/bin/python3", "-B"], svc)
            self.assertTrue(exec_[2].startswith(RUNTIME), svc)  # never the writer worktree or ~/repos
            self.assertNotIn("0.0.0.0", service["ExecStart"], svc)
            self.assertFalse([k for k in service if k.startswith("Environment")], svc)  # no secret in the unit

    def test_receiver_and_worker_restart_and_install(self):
        for svc, sub in (("hass-receiver", "serve"), ("hass-worker", "work")):
            cp = parse(f"{svc}.service")
            self.assertEqual((cp["Service"]["Restart"], cp["Service"]["RestartSec"]), ("on-failure", "5"))
            self.assertEqual(cp["Install"]["WantedBy"], "default.target")
            self.assertIn(f"host.py {sub} --host %h/.local/state/hass/host/host.json", cp["Service"]["ExecStart"])

    def test_receiver_and_worker_have_a_start_limit_in_unit_section(self):
        for svc in ("hass-receiver", "hass-worker"):
            cp = parse(f"{svc}.service")
            self.assertEqual((int(cp["Unit"]["StartLimitIntervalSec"]), int(cp["Unit"]["StartLimitBurst"])), (300, 5), svc)
            self.assertNotIn("StartLimitIntervalSec", cp["Service"], svc)
            self.assertNotIn("StartLimitBurst", cp["Service"], svc)

    def test_timers_and_oneshots_unchanged(self):
        for svc in ("hass-health", "hass-backup"):
            text = (DIR / f"{svc}.service").read_text("utf-8")
            self.assertNotIn("StartLimit", text, svc)

    def test_health_command_and_timers(self):
        exec_ = parse("hass-health.service")["Service"]["ExecStart"]
        for want in ("--alert-log %h/agent-work/modes/ALERTS.log", "--host-dir %h/.local/state/hass/host",
                     "--seen %h/.local/state/hass/health.seen", "--writer", "--model http://127.0.0.1:11434"):
            self.assertIn(want, exec_)
        self.assertEqual(parse("hass-health.service")["Service"]["SuccessExitStatus"], "1")
        self.assertEqual(parse("hass-health.timer")["Timer"]["OnCalendar"], "*:0/5")
        backup = parse("hass-backup.timer")["Timer"]
        self.assertEqual((backup["OnCalendar"], backup["Persistent"]), ("*-*-* 03:30 America/Los_Angeles", "true"))
        self.assertIn("statebackup.py create --state", parse("hass-backup.service")["Service"]["ExecStart"])
        for timer in ("hass-health", "hass-backup"): self.assertEqual(parse(f"{timer}.timer")["Install"]["WantedBy"], "timers.target")

    def test_clover_sync_is_a_read_only_15_minute_oneshot(self):
        """HASS-CLOVER-2: a template only (the operator installs it after review); the token is never in the unit."""
        service = parse("hass-clover-sync.service")["Service"]
        self.assertEqual(service["Type"], "oneshot")
        self.assertEqual(service["ExecStart"], "/usr/bin/python3 -B %h/.local/share/hass/runtime/hass/clover/cli.py sync "
                                               "--host %h/.local/state/hass/host/host.json")
        self.assertEqual(service["SuccessExitStatus"], "1")
        text = (DIR / "hass-clover-sync.service").read_text("utf-8") + (DIR / "hass-clover-sync.timer").read_text("utf-8")
        for word in ("token", "Bearer", "Authorization", "--force", "StartLimit"):
            self.assertNotIn(word, text)
        timer = parse("hass-clover-sync.timer")
        self.assertEqual((timer["Timer"]["OnCalendar"], timer["Timer"]["Persistent"]), ("*:0/15", "true"))
        self.assertEqual(timer["Install"]["WantedBy"], "timers.target")


    def test_clover_reports_are_daily_cache_only(self):
        svc = parse("hass-clover-report.service")["Service"]
        self.assertEqual(svc["Type"], "oneshot")
        self.assertEqual(svc["ExecStart"], "/usr/bin/python3 -B %h/.local/share/hass/runtime/hass/clover/cli.py report --all "
                                         "--host %h/.local/state/hass/host/host.json")
        timer = parse("hass-clover-report.timer")
        self.assertEqual(timer["Timer"]["OnCalendar"], "*-*-* 06:00 America/Los_Angeles")
        self.assertEqual(timer["Timer"]["Persistent"], "true")
        self.assertEqual(timer["Install"]["WantedBy"], "timers.target")


if __name__ == "__main__":
    unittest.main()
