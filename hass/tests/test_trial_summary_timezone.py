"""RF0010-11 (H18/H09): missing America/Los_Angeles timezone data refuses the whole trial summary privately."""
import os, sqlite3, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass import trial_summary as ts  # noqa: E402
from hass.tests import test_trial_summary as base  # noqa: E402  (module only: its TestCase is not re-collected here)

CANARY = "TZCANARY-5c21e0"
JSON_REFUSAL = '{"result": "unreadable"}\n'
TEXT_REFUSAL = "Trial summary unavailable.\n"
AWARE = "2026-11-02T07:30:00+00:00"  # 2026-11-01 23:30 PST: the UTC day would be 11-02


def zone_fails_after(n_ok):
    """A ZoneInfo stand-in: the real zone `n_ok` times, then the real missing-zone error carrying a canary."""
    calls = []

    def fake(key):
        calls.append(key)
        if len(calls) > n_ok: raise ZoneInfoNotFoundError(f"No time zone found with key {key} {CANARY}")
        return ZoneInfo(key)
    return fake, calls


class TrialSummaryTimezoneTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(); self.addCleanup(self._t.cleanup); self.tmp = self._t.name

    def state(self, **rows):
        return base.make_state(tempfile.mkdtemp(dir=self.tmp), **rows)

    def refuses(self, state, fake):
        """Both formats print only the fixed refusal, exit 1, empty stderr, no canary/path/timestamp."""
        for flag, want in (("--json", JSON_REFUSAL), (None, TEXT_REFUSAL)):
            args = ["--state", str(state), "--from", "2026-11-01", *([flag] if flag else [])]
            with mock.patch.object(ts, "ZoneInfo", side_effect=fake):
                code, out, err = base.run(*args)
            self.assertEqual((code, out, err), (1, want, ""))
            for secret in (CANARY, base.CANARY, str(state), AWARE, "Traceback", "2026-11-02"):
                self.assertNotIn(secret, out + err)

    def test_real_cli_without_timezone_resources_is_private_unreadable(self):
        state = self.state(messages=[("approved", "2026-11-02T10:00:00-08:00")])
        empty_zones = tempfile.mkdtemp(dir=self.tmp)
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON") and k != "TZ"}
        env["PYTHONTZPATH"] = empty_zones
        for flag, want in (["--json"], JSON_REFUSAL), ([], TEXT_REFUSAL):
            p = subprocess.run([sys.executable, "-B", "-S", str(base.SCRIPT), "--state", str(state), "--from", "2026-11-01",
                                *flag], capture_output=True, text=True, env=env, cwd=self.tmp, timeout=60)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (1, want, ""))
        env.pop("PYTHONTZPATH")  # control: the same child with the normal zone database counts the message
        p = subprocess.run([sys.executable, "-B", "-S", str(base.SCRIPT), "--state", str(state), "--from", "2026-11-01",
                            "--json"], capture_output=True, text=True, env=env, cwd=self.tmp, timeout=60)
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        self.assertIn('"approved":1', p.stdout)

    def test_missing_zone_in_messages_drafts_and_approvals_refuses_whole_report(self):
        valid = "2026-11-01T10:00:00-07:00"  # converts first, so a late failure cannot leave partial counts
        for rows in ({"messages": [("approved", valid), ("rejected", AWARE)]},
                     {"messages": [("approved", valid)], "drafts": [("applied", AWARE)]},
                     {"drafts": [("applied", valid)], "approvals": [AWARE]}):
            with self.subTest(table=list(rows)[-1]):
                state = self.state(**rows)
                fake, _ = zone_fails_after(1)
                with mock.patch.object(ts, "ZoneInfo", side_effect=fake), self.assertRaises(ts.Unreadable) as cm:
                    ts.summarize(str(state), ts.date(2026, 11, 1), 7)
                self.assertIsNone(cm.exception.__cause__); self.assertTrue(cm.exception.__suppress_context__)
                self.assertEqual(cm.exception.args, ())
                self.refuses(state, zone_fails_after(1)[0])

    def test_timezone_failure_closes_read_connection_and_preserves_store(self):
        state = self.state(messages=[("approved", "2026-11-01T10:00:00-07:00")], approvals=[AWARE])
        store = state / "conversation.sqlite3"
        before = store.read_bytes()
        conns, real_connect = [], sqlite3.connect

        def capture(*a, **k):
            conns.append(c := real_connect(*a, **k)); return c
        fake, _ = zone_fails_after(0)
        with mock.patch.object(ts.sqlite3, "connect", side_effect=capture), mock.patch.object(ts, "ZoneInfo", side_effect=fake):
            with self.assertRaises(ts.Unreadable): ts.summarize(str(state), ts.date(2026, 11, 1), 7)
        self.assertEqual(len(conns), 1)  # no retry or second scan
        with self.assertRaises(sqlite3.ProgrammingError): conns[0].execute("SELECT 1")
        self.assertEqual(store.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in state.iterdir()), ["conversation.sqlite3"])

    def test_missing_zone_never_becomes_unknown_or_utc_success(self):
        state = self.state(messages=[("approved", AWARE)])
        self.refuses(state, zone_fails_after(0)[0])
        r = base.report(state, "2026-11-01", 2)  # the real zone: Pacific 11-01, never unknown or the UTC day
        self.assertEqual([d["messages"]["approved"] for d in r["daysSummary"]], [1, 0])
        self.assertEqual(r["unknown"]["messages"]["approved"], 0)

    def test_unknown_time_usage_only_and_empty_store_do_not_need_zone(self):
        fake, calls = zone_fails_after(0)
        unknown = self.state(messages=[("approved", None), ("rejected", "2026-11-01T10:00:00"), ("proposed", "not-a-time")],
                             drafts=[("applied", "")], approvals=["2026-11-01 10:00"])
        usage = self.state(usage=[("2026-11-01", 3), ("2026-11-02", 2)])
        empty = self.state()
        with mock.patch.object(ts, "ZoneInfo", side_effect=fake):
            r = base.report(unknown)
            self.assertEqual({k: v for k, v in r["unknown"]["messages"].items() if v},
                             {"approved": 1, "rejected": 1, "proposed": 1})
            self.assertEqual((r["unknown"]["drafts"]["applied"], r["unknown"]["approvals"]), (1, 1))
            self.assertEqual(base.report(usage)["totals"]["interpreterCalls"], 5)
            self.assertEqual(base.report(empty)["totals"], ts._blank())
        self.assertEqual(calls, [])

    def test_pacific_dst_and_error_precedence_remain(self):
        state = self.state(messages=[("approved", t) for t in ("2026-11-01T06:59:59+00:00", "2026-11-01T09:30:00+00:00",
                                                                "2026-03-08T10:00:00+00:00", "2026-03-09T06:59:59+00:00")])
        got = {d["day"]: d["messages"]["approved"] for d in base.report(state, "2026-10-31", 2)["daysSummary"]}
        self.assertEqual(got, {"2026-10-31": 1, "2026-11-01": 1})
        got = {d["day"]: d["messages"]["approved"] for d in base.report(state, "2026-03-08", 2)["daysSummary"]}
        self.assertEqual(got, {"2026-03-08": 2, "2026-03-09": 0})
        fake, calls = zone_fails_after(0)
        with mock.patch.object(ts, "ZoneInfo", side_effect=fake):
            code, out, err = base.run("--state", str(state), "--from", "2026-13-01", "--json")
            self.assertEqual((code, out), (2, "")); self.assertTrue(err.startswith("usage: "))
            missing = Path(self.tmp) / "absent"
            self.assertEqual(base.run("--state", str(missing), "--from", "2026-11-01", "--json"), (1, JSON_REFUSAL, ""))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
