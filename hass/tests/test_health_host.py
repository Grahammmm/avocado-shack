"""HASS-SVC-1 (H19): host health checks (--host-dir) and the --alert-log line. Temp dirs and fixtures only; the real host,
relay, journals and secret are never read."""
import builtins, contextlib, io, json, os, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import health, relay

NOW = datetime(2026, 11, 6, 20, 0, tzinfo=timezone.utc)
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}
A, B = "a" * 40, "b" * 40


def secs(minutes_ago): return int((NOW - timedelta(minutes=minutes_ago)).timestamp())


class HostHealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.host = self.tmp / "state", self.tmp / "host"
        for d in (self.state, self.host): d.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))
        self.secret, self.stop = self.tmp / "envelope.key", self.tmp / "STOP"
        self.write_secret()
        self.write_host()

    # fixtures ---------------------------------------------------------------------------------------------
    def write_secret(self, mode=0o600):
        self.secret.write_text("0" * 64 + "\n")
        self.secret.chmod(mode)

    def write_host(self, mode=0o600):
        cfg = {"state": str(self.state), "secretFile": str(self.secret), "listen": "127.0.0.1:8795", "allowedPeers": [],
               "approvals": "hold", "interpreter": {"url": "http://127.0.0.1:11434", "model": "m"}, "runtimeCommit": A,
               "release": {"stopFile": str(self.stop)}}
        path = self.host / "host.json"
        path.write_text(json.dumps(cfg))
        path.chmod(mode)

    def relay_db(self, rows=(), last_pull=None):
        db = relay.RelayStore(self.host).db
        for created, acked in rows:
            db.execute("INSERT INTO relay(chat, text, pictures, created_at, acked_at) VALUES ('c', 't', 0, ?, ?)", (created, acked))
        if last_pull is not None: db.execute("INSERT OR REPLACE INTO meta VALUES ('last_pull_at', ?)", (str(last_pull),))
        db.close()

    def books(self, *journals, anchor=True):
        (self.host / "releases").mkdir(mode=0o700, exist_ok=True)
        if anchor:
            p = self.host / "publish.json"
            p.write_text(json.dumps({"anchor_site_commit": A, "anchor_build_today": "2026-11-01", "anchor_seq": 0,
                                     "anchor_at": NOW.isoformat()}))
            p.chmod(0o600)
        for n, (state, minutes_ago) in enumerate(journals, 1):
            j = {"change_id": f"chg-{n:012x}", "code": "ab12", "kind": "change", "orig": None, "draft_hash": "h", "writer_before": A,
                 "site_before": A, "today": "2026-11-06", "seq": n, "push_attempts": [], "state": state, "notified": [],
                 "at": (NOW - timedelta(minutes=minutes_ago)).isoformat()}
            if state in ("live", "pushed", "unconfirmed", "unknown"):
                j.update(site_commit=B, push_attempts=[NOW.isoformat()], manifest={}, writer_after=B)
            p = self.host / "releases" / (j["change_id"] + ".json")
            p.write_text(json.dumps(j))
            p.chmod(0o600)

    def run_health(self, *extra, host=True):
        out = io.StringIO()
        argv = ["--state", str(self.state), *(["--host-dir", str(self.host)] if host else []), *extra]
        with contextlib.redirect_stdout(out): code = health.main(argv, now=NOW)
        [line] = out.getvalue().splitlines()
        return code, json.loads(line)

    def problems(self, **kw):
        return {p["check"]: p["detail"] for p in self.run_health(**kw)[1]["problems"]}

    # relay-stuck / mac-silent -----------------------------------------------------------------------------
    def test_healthy_host_and_no_flag_means_no_host_checks(self):
        self.assertEqual(self.problems(), {})
        self.host.joinpath("host.json").unlink()
        self.assertEqual(self.problems(host=False), {})

    def test_relay_stuck_counts_only_old_unacked_rows(self):
        self.relay_db([(secs(20), None), (secs(30), None), (secs(40), secs(39)), (secs(5), None)])
        self.assertEqual(self.problems(), {"relay-stuck": "2"})
        (self.host / "relay.sqlite3").unlink()
        self.relay_db([(secs(5), None)])
        self.assertEqual(self.problems(), {})

    def test_relay_store_symlink_is_refused_not_followed(self):
        real = self.tmp / "real.sqlite3"
        sqlite3.connect(real).close()
        os.symlink(real, self.host / "relay.sqlite3")
        self.assertEqual(self.problems(), {"relay-stuck": "relay store is not a regular file"})

    def test_mac_silent_buckets(self):
        for pulled, want in ((11, "over 10 min"), (37, "over 30 min"), (121, "over 2 h"), (500, "over 2 h")):
            self.relay_db(last_pull=secs(pulled))
            self.assertEqual(self.problems(), {"mac-silent": want}, pulled)
        for pulled in (3, 10):
            self.relay_db(last_pull=secs(pulled))
            self.assertEqual(self.problems(), {}, pulled)

    def test_mac_never_pulled_is_not_silent_and_unreadable_store_is_a_problem(self):
        self.relay_db()
        self.assertEqual(self.problems(), {})
        (self.host / "relay.sqlite3").write_bytes(b"not a database" * 50)
        self.assertEqual(self.problems(), {"relay-stuck": "relay store unreadable"})

    # releases ---------------------------------------------------------------------------------------------
    def test_release_open_reports_the_state_only(self):
        self.books(("live", 500), ("reverted", 500), ("not-applied", 500), ("closed", 500))
        self.assertEqual(self.problems(), {})
        shutil.rmtree(self.host / "releases")
        self.books(("not-published", 1))
        self.assertEqual(self.problems(), {"release-open": "not-published"})

    def test_in_progress_is_open_only_after_15_minutes(self):
        self.books(("intent", 14))
        self.assertEqual(self.problems(), {})
        self.books(("intent", 16))
        self.assertEqual(self.problems(), {"release-open": "intent"})

    def test_live_unconfirmed_counts_unknown_and_unconfirmed(self):
        self.books(("unconfirmed", 5))
        self.assertEqual(self.problems(), {"release-open": "unconfirmed", "live-unconfirmed": "1"})
        self.books(("unknown", 5))
        self.assertEqual(self.problems(), {"release-open": "unknown", "live-unconfirmed": "1"})

    def test_release_books_fail_closed(self):
        self.books(("live", 5), anchor=False)  # journals without publish.json
        self.assertEqual(self.problems(), {"release-books": "release books failed their checks"})
        self.books(("live", 5))
        self.assertEqual(self.problems(), {})
        journal = self.host / "releases" / "chg-000000000001.json"
        journal.chmod(0o644)
        self.assertEqual(list(self.problems()), ["release-books"])
        journal.chmod(0o600)
        journal.rename(self.tmp / "moved.json")
        os.symlink(self.tmp / "moved.json", journal)  # a linked journal is never followed
        self.assertEqual(list(self.problems()), ["release-books"])

    def test_no_books_at_all_is_fine_and_a_linked_releases_dir_is_refused(self):
        self.assertEqual(self.problems(), {})
        (self.host / "publish.json").write_text("{}")
        os.symlink(self.tmp, self.host / "releases")
        self.assertEqual(list(self.problems()), ["release-books"])

    # host-config / STOP -----------------------------------------------------------------------------------
    def test_host_config_mode_and_type_only(self):
        self.write_host(0o644)
        self.assertEqual(self.problems(), {"host-config": "host.json refused"})
        self.write_host()
        self.write_secret(0o644)
        self.assertEqual(self.problems(), {"host-config": "secret file mode"})
        self.secret.unlink()
        os.symlink(self.tmp / "elsewhere", self.secret)
        self.assertEqual(self.problems(), {"host-config": "secret file type"})
        self.secret.unlink()
        self.assertEqual(self.problems(), {"host-config": "secret file missing"})
        self.host.joinpath("host.json").unlink()
        self.assertEqual(self.problems(), {"host-config": "host.json refused"})

    def test_nul_in_secret_or_stop_path_is_a_host_config_problem_not_a_crash(self):
        for key in ("secretFile", "stopFile"):
            self.write_host()
            path = self.host / "host.json"
            cfg = json.loads(path.read_text())
            (cfg if key == "secretFile" else cfg["release"])[key] = "/tmp/a\u0000b"
            path.write_text(json.dumps(cfg))
            path.chmod(0o600)
            self.assertIn("host-config", self.problems(), key) if key == "secretFile" else self.problems()

    def test_secret_file_is_never_opened(self):
        opened, real_open, real_os_open = [], builtins.open, os.open

        def spy(real):
            def inner(path, *a, **kw):
                opened.append(str(path))
                return real(path, *a, **kw)
            return inner
        with mock.patch.object(builtins, "open", spy(real_open)), mock.patch.object(os, "open", spy(real_os_open)):
            self.assertEqual(self.problems(), {})
        self.assertTrue(opened)  # the spy sees other opens
        self.assertNotIn(str(self.secret), opened)

    def test_stop_file_is_info_then_stopped_long(self):
        self.stop.write_text("")
        os.utime(self.stop, (secs(60), secs(60)))
        code, doc = self.run_health()
        self.assertEqual((code, doc["problems"], doc["info"][-1]["check"]), (0, [], "publishing-stopped"))
        os.utime(self.stop, (secs(25 * 60), secs(25 * 60)))
        code, doc = self.run_health()
        self.assertEqual((code, doc["problems"]), (1, [{"check": "stopped-long", "detail": "over 24 h"}]))
        self.assertNotIn("publishing-stopped", [i["check"] for i in doc["info"]])

    # --alert-log ------------------------------------------------------------------------------------------
    def test_alert_line_only_on_change_and_carries_ids_only(self):
        log, seen = self.tmp / "ALERTS.log", self.tmp / "seen"
        self.relay_db([(secs(30), None)], last_pull=secs(300))
        args = ("--seen", str(seen), "--alert-log", str(log))
        self.assertTrue(self.run_health(*args)[1]["notify"])
        self.assertFalse(self.run_health(*args)[1]["notify"])  # same problems: no second line
        [line] = log.read_text().splitlines()
        parts = line.split(" ")
        self.assertEqual((parts[0], parts[1], len(parts[2]), parts[3:]), ("2026-11-06T20:00:00Z", "HASS-HEALTH", 12, ["mac-silent", "relay-stuck"]))
        self.relay_db(last_pull=secs(15))  # a different detail changes the fingerprint
        self.run_health(*args)
        self.assertEqual(len(log.read_text().splitlines()), 2)
        self.assertEqual(oct(log.stat().st_mode & 0o777), "0o600")

    def test_no_line_when_healthy(self):
        log = self.tmp / "ALERTS.log"
        self.run_health("--seen", str(self.tmp / "seen"), "--alert-log", str(log))
        self.assertFalse(log.exists())

    def test_alert_log_path_rules(self):
        real = self.tmp / "real.log"
        real.write_text("")
        link = self.tmp / "link.log"
        os.symlink(real, link)
        for bad in (link, self.state / "ALERTS.log", health.REPO_ROOT / "ALERTS.log", self.tmp / "no-dir" / "x.log", self.tmp):
            code, doc = self.run_health("--alert-log", str(bad))
            self.assertEqual((code, doc["problems"][0]["check"], doc["ok"]), (2, "alert-log", False), bad)
        self.assertEqual(real.read_text(), "")


if __name__ == "__main__":
    unittest.main()
