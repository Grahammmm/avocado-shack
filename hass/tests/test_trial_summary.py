"""AV1104-09 (H18): hass/trial_summary.py counts the owner trial per Pacific day, never contents."""
import contextlib, io, json, os, re, sqlite3, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass import conversation, media, trial_summary as ts  # noqa: E402

CANARY = "CANARY-7f3a91"
SCRIPT = ROOT / "hass" / "trial_summary.py"


def make_state(tmp, messages=(), drafts=(), approvals=(), usage=None, tables=True):
    """A state dir with conversation.sqlite3 from the real SCHEMA; every private column holds the canary."""
    d = Path(tmp)
    db = sqlite3.connect(d / "conversation.sqlite3")
    if tables: db.executescript(conversation.SCHEMA)
    for i, (disp, at) in enumerate(messages):
        db.execute("INSERT INTO messages VALUES (?, ?, ?)", (f"{CANARY}-m{i}", disp, at))
    for i, (state, at) in enumerate(drafts):
        db.execute("INSERT INTO drafts(change_id, code, state, ops_json, summary, sender, chat, created_at) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (f"{CANARY}-c{i}", f"{CANARY}-code", state, "[]", f"{CANARY}-summary",
                                                       f"{CANARY}-sender", f"{CANARY}-chat", at))
    for i, at in enumerate(approvals):
        db.execute("INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, approved_at) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (f"{CANARY}-s", f"{CANARY}-ch", f"{CANARY}-p{i}", f"{CANARY}-c", "h", "b",
                                                      "2099-01-01T00:00:00+00:00", at))
    if usage is not None:
        db.execute(conversation.USAGE)
        db.executemany("INSERT INTO usage VALUES (?, ?)", usage)
    db.commit(); db.close()
    return d


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try: code = ts.main(list(args))
        except SystemExit as e: code = e.code
    return code, out.getvalue(), err.getvalue()


def report(tmp, start="2026-11-01", days=7):
    code, out, _ = run("--state", str(tmp), "--from", start, "--days", str(days), "--json")
    assert code == 0, out
    return json.loads(out)


class TrialSummaryTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(); self.addCleanup(self._t.cleanup); self.tmp = self._t.name

    def test_window_zero_days_and_totals(self):
        make_state(self.tmp, messages=[("approved", "2026-11-01T08:00:00-07:00"), ("approved", "2026-11-03T08:00:00-08:00"),
                                       ("rejected", "2026-11-03T09:00:00-08:00"), ("approved", "2026-10-31T23:59:00-07:00"),
                                       ("approved", "2026-11-08T00:00:00-08:00")])
        r = report(self.tmp)
        self.assertEqual([d["day"] for d in r["daysSummary"]], [f"2026-11-0{n}" for n in range(1, 8)])
        self.assertEqual([d["messages"]["approved"] for d in r["daysSummary"]], [1, 0, 1, 0, 0, 0, 0])
        self.assertEqual(r["totals"]["messages"]["approved"], 2); self.assertEqual(r["totals"]["messages"]["rejected"], 1)
        self.assertEqual(report(self.tmp, "2026-11-03", 1)["totals"]["messages"]["approved"], 1)
        r31 = report(self.tmp, "2026-10-31", 31)
        self.assertEqual(len(r31["daysSummary"]), 31); self.assertEqual(r31["totals"]["messages"]["approved"], 4)
        self.assertEqual(report(self.tmp, "2026-11-01")["days"], 7)

    def test_pacific_midnight_and_both_dst_changes(self):
        # 2026-03-08 spring forward, 2026-11-01 fall back: 08:30Z on 11-01 is 01:30 PDT, 09:30Z is 01:30 PST (both day 11-01)
        times = ["2026-11-01T06:59:59+00:00", "2026-11-01T07:00:00+00:00", "2026-11-01T08:30:00+00:00",
                 "2026-11-01T09:30:00+00:00", "2026-11-02T07:59:59+00:00", "2026-11-02T08:00:00+00:00"]
        make_state(self.tmp, messages=[("approved", t) for t in times])
        got = {d["day"]: d["messages"]["approved"] for d in report(self.tmp, "2026-10-31", 3)["daysSummary"]}
        self.assertEqual(got, {"2026-10-31": 1, "2026-11-01": 4, "2026-11-02": 1})
        got = {d["day"]: d["messages"]["approved"] for d in report(self.tmp, "2026-03-07", 3)["daysSummary"]}
        self.assertEqual(got, {"2026-03-07": 0, "2026-03-08": 0, "2026-03-09": 0})
        d2 = tempfile.mkdtemp(dir=self.tmp)
        make_state(d2, messages=[("approved", "2026-03-08T09:59:59+00:00"), ("approved", "2026-03-08T10:00:00+00:00"),
                                 ("approved", "2026-03-09T06:59:59+00:00"), ("approved", "2026-03-09T07:00:00+00:00")])
        got = [d["messages"]["approved"] for d in report(d2, "2026-03-07", 3)["daysSummary"]]
        self.assertEqual(got, [0, 3, 1])  # 03-08 is a 23 hour day: 01:59 PST, 03:00 PDT and 23:59 PDT

    def test_unknown_times_and_old_time_columns(self):
        make_state(self.tmp, messages=[("approved", None), ("approved", ""), ("approved", "2026-11-02T08:00:00"),
                                       ("approved", "garbage"), ("approved", b"\x00\x01"), ("approved", 5),
                                       ("approved", "2026-01-01T00:00:00+00:00")])
        r = report(self.tmp)
        self.assertEqual(r["unknown"]["messages"]["approved"], 6); self.assertEqual(r["totals"]["messages"]["approved"], 6)
        self.assertNotIn("day", r["unknown"])
        self.assertTrue(all(d["messages"]["approved"] == 0 for d in r["daysSummary"]))
        old = Path(tempfile.mkdtemp(dir=self.tmp))
        db = sqlite3.connect(old / "conversation.sqlite3")
        db.executescript("CREATE TABLE messages(provider_id TEXT, disposition TEXT NOT NULL);"
                         "INSERT INTO messages VALUES ('x', 'rejected');"
                         "CREATE TABLE drafts(state TEXT NOT NULL); INSERT INTO drafts VALUES ('applied');"
                         "CREATE TABLE approvals(id INTEGER); INSERT INTO approvals VALUES (1);")
        db.commit(); db.close()
        r = report(old)
        self.assertEqual((r["unknown"]["messages"]["rejected"], r["unknown"]["drafts"]["applied"], r["unknown"]["approvals"]),
                         (1, 1, 1))
        text = run("--state", str(old), "--from", "2026-11-01")[1]
        self.assertIn("day unknown:", text)

    def test_dispositions_are_exclusive_and_owner_only(self):
        singles = [k for k in ts.MESSAGE_KEYS if k not in ("commands", "photo-refused", "other")]
        cmds = sorted(ts.COMMANDS)
        at = "2026-11-02T10:00:00-08:00"
        rows = ([(k, at) for k in singles] + [(c, at) for c in cmds] + [(f"photo-refused:{s}", at) for s in media.REPLIES]
                + [("photo-refused:" + CANARY, at), (CANARY, at), ("approved\nx", at), (b"x", at)]
                + [(k, None) for k in ts.NOT_OWNER] + [(k, at) for k in ts.NOT_OWNER])
        make_state(self.tmp, messages=rows)
        db = sqlite3.connect(Path(self.tmp) / "conversation.sqlite3")  # a NULL disposition is not storable: NOT NULL
        self.assertRaises(sqlite3.IntegrityError, db.execute, "INSERT INTO messages VALUES ('n', NULL, NULL)"); db.close()
        m = report(self.tmp)["totals"]["messages"]
        for k in singles: self.assertEqual(m[k], 1, k)
        self.assertEqual(m["commands"], len(cmds)); self.assertEqual(m["photo-refused"], len(media.REPLIES))
        self.assertEqual(m["other"], 4)
        eligible = len(singles) + len(cmds) + len(media.REPLIES) + 4
        self.assertEqual(sum(m.values()), eligible)
        self.assertEqual(set(m), set(ts.MESSAGE_KEYS))
        self.assertEqual(ts.PHOTO_REFUSED, frozenset(media.REPLIES))
        self.assertNotIn(CANARY, json.dumps(report(self.tmp)))

    def test_drafts_current_states_not_implied_expiry(self):
        at = "2026-11-02T10:00:00-08:00"
        states = {"applied": "applied", "verified": "checked", "failed": "failed", "reverted": "undone", "expired": "expired",
                  "rejected": "cancelled", "proposed": "waiting", "needs-details": "waiting", "approved": "waiting",
                  CANARY: "other"}
        old = "2000-01-01T00:00:00+00:00"  # long past any expiry, still proposed: remains waiting
        make_state(self.tmp, drafts=[(s, at) for s in states] + [("proposed", old), ("applied", "2026-12-25T00:00:00-08:00")])
        r = report(self.tmp)
        d = r["daysSummary"][1]["drafts"]
        want = {k: 0 for k in ts.DRAFT_KEYS}
        for v in states.values(): want[v] += 1
        self.assertEqual(d, want); self.assertEqual(d["checked"], 1); self.assertEqual(d["applied"], 1)
        self.assertEqual(r["totals"]["drafts"], want)

    def test_approvals_and_usage_are_independent(self):
        make_state(self.tmp, approvals=["2026-11-02T08:00:00-08:00", "2026-11-02T09:00:00-08:00", "2026-11-04T09:00:00-08:00"],
                   usage=[("2026-11-02", 3), ("2026-11-05", 2), ("not-a-day", 4), ("2026-02-30", 1), ("2026-11-3", 9)])
        r = report(self.tmp)
        self.assertEqual([d["approvals"] for d in r["daysSummary"]], [0, 2, 0, 1, 0, 0, 0])
        self.assertEqual([d["interpreterCalls"] for d in r["daysSummary"]], [0, 3, 0, 0, 2, 0, 0])
        self.assertEqual(r["unknown"]["interpreterCalls"], 14)
        self.assertEqual((r["totals"]["approvals"], r["totals"]["interpreterCalls"]), (3, 19))
        self.assertEqual(sum(r["totals"]["messages"].values()), 0)
        none = tempfile.mkdtemp(dir=self.tmp); make_state(none)
        self.assertEqual(report(none)["totals"]["interpreterCalls"], 0)
        for bad in (-1, 1.5, "abc"):
            d = tempfile.mkdtemp(dir=self.tmp); p = make_state(d)
            db = sqlite3.connect(p / "conversation.sqlite3")
            db.execute(conversation.USAGE); db.execute("INSERT INTO usage VALUES ('2026-11-02', ?)", (bad,)); db.commit(); db.close()
            code, out, _ = run("--state", d, "--from", "2026-11-01", "--json")
            self.assertEqual((code, json.loads(out)), (1, {"result": "unreadable"}), bad)

    def test_missing_tables_missing_store_corrupt_and_unsafe_paths(self):
        empty = Path(tempfile.mkdtemp(dir=self.tmp)); make_state(empty, tables=False)
        r = report(empty); self.assertEqual(sum(r["totals"]["messages"].values()), 0)
        for table in ("messages", "drafts", "approvals"):
            d = Path(tempfile.mkdtemp(dir=self.tmp)); make_state(d, messages=[("approved", "2026-11-02T10:00:00-08:00")],
                                                                  drafts=[("applied", "2026-11-02T10:00:00-08:00")],
                                                                  approvals=["2026-11-02T10:00:00-08:00"])
            db = sqlite3.connect(d / "conversation.sqlite3"); db.execute(f"DROP TABLE {table}"); db.commit(); db.close()
            t = report(d)["totals"]
            self.assertEqual(t["messages"]["approved"], 0 if table == "messages" else 1)
            self.assertEqual(t["drafts"]["applied"], 0 if table == "drafts" else 1)
            self.assertEqual(t["approvals"], 0 if table == "approvals" else 1)
        bad = []
        nodb = Path(tempfile.mkdtemp(dir=self.tmp)); bad.append(nodb)
        garbage = Path(tempfile.mkdtemp(dir=self.tmp)); (garbage / "conversation.sqlite3").write_bytes(b"not a database" * 100)
        bad.append(garbage)
        schema = Path(tempfile.mkdtemp(dir=self.tmp)); db = sqlite3.connect(schema / "conversation.sqlite3")
        db.execute("CREATE TABLE messages(provider_id TEXT, something TEXT)"); db.commit(); db.close(); bad.append(schema)
        isdir = Path(tempfile.mkdtemp(dir=self.tmp)); (isdir / "conversation.sqlite3").mkdir(); bad.append(isdir)
        fifo = Path(tempfile.mkdtemp(dir=self.tmp)); os.mkfifo(fifo / "conversation.sqlite3"); bad.append(fifo)
        dangling = Path(tempfile.mkdtemp(dir=self.tmp)); (dangling / "conversation.sqlite3").symlink_to(dangling / "nowhere")
        bad.append(dangling)
        real = Path(tempfile.mkdtemp(dir=self.tmp)); make_state(real)
        link = Path(tempfile.mkdtemp(dir=self.tmp)); (link / "conversation.sqlite3").symlink_to(real / "conversation.sqlite3")
        bad.append(link)
        dirlink = Path(self.tmp) / "dirlink"; dirlink.symlink_to(real); bad.append(dirlink)
        bad.append(Path(self.tmp) / "absent")
        for d in bad:
            code, out, err = run("--state", str(d), "--from", "2026-11-01")
            self.assertEqual((code, out.strip(), err), (1, ts.UNREADABLE_TEXT, ""), str(d))
        self.assertFalse((nodb / "conversation.sqlite3").exists()); self.assertFalse((Path(self.tmp) / "absent").exists())

    def test_read_only_including_live_wal(self):
        d = Path(self.tmp)
        make_state(d)
        writer = sqlite3.connect(d / "conversation.sqlite3"); writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO messages VALUES ('w1', 'approved', '2026-11-02T10:00:00-08:00')"); writer.commit()
        self.assertTrue((d / "conversation.sqlite3-wal").exists())  # committed data sits only in the WAL
        def snap(): return {p.name: p.read_bytes() for p in sorted(d.iterdir()) if not p.name.endswith("-shm")}  # -shm is the reader index
        before = snap()
        self.assertEqual(report(d)["totals"]["messages"]["approved"], 1)
        self.assertEqual(snap(), before)
        seen = []
        orig = ts.sqlite3.connect
        def traced(*a, **k):
            c = orig(*a, **k); c.set_trace_callback(seen.append); return c
        ts.sqlite3.connect = traced
        try: run("--state", str(d), "--from", "2026-11-01")
        finally: ts.sqlite3.connect = orig
        writer.close()
        self.assertTrue(seen)
        for sql in seen:
            self.assertRegex(sql.strip().upper(), r"^(PRAGMA (QUERY_ONLY|TABLE_INFO)|BEGIN|COMMIT|SELECT)", sql)
            self.assertNotRegex(sql.upper(), r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|VACUUM)\b")

    def test_canaries_never_print_in_either_format(self):
        hostile = f"{CANARY}'; DROP TABLE messages;--"
        make_state(self.tmp, messages=[(hostile, f"{CANARY}-time"), ("approved", "2026-11-02T10:00:00-08:00")],
                   drafts=[(hostile, hostile), ("applied", "2026-11-02T10:00:00-08:00")],
                   approvals=["2026-11-02T10:00:00-08:00", hostile], usage=[(hostile, 2), ("2026-11-02", 1)])
        for extra in ((), ("--json",)):
            code, out, err = run("--state", self.tmp, "--from", "2026-11-01", *extra)
            self.assertEqual(code, 0); self.assertNotIn(CANARY, out + err); self.assertEqual(err, "")
        selected = []
        orig = ts.sqlite3.connect
        def traced(*a, **k):
            c = orig(*a, **k); c.set_trace_callback(selected.append); return c
        ts.sqlite3.connect = traced
        try: run("--state", self.tmp, "--from", "2026-11-01")
        finally: ts.sqlite3.connect = orig
        selects = " ".join(s for s in selected if s.upper().startswith("SELECT"))
        for forbidden in ("summary", "code", "sender", "chat", "provider_id", "change_id", "ops_json", "outbox", "text",
                          "draft_hash"):
            self.assertNotRegex(selects, rf"\b{forbidden}\b")
        bad = Path(self.tmp) / "nope" / CANARY
        for extra in ((), ("--json",)):
            code, out, err = run("--state", str(bad), "--from", "2026-11-01", *extra)
            self.assertEqual(code, 1); self.assertNotIn(CANARY, out + err)
        code, out, err = run("--state", self.tmp, "--from", CANARY)
        self.assertEqual(code, 2); self.assertNotIn(CANARY, out + err)

    def test_cli_usage_and_documented_command(self):
        make_state(self.tmp, messages=[("approved", "2026-11-02T10:00:00-08:00"), ("status", None)],
                   drafts=[("verified", "2026-11-02T10:00:00-08:00")])
        for args in ([], ["--state", self.tmp], ["--from", "2026-11-01"], ["--state", self.tmp, "--from", "2026-1-1"],
                     ["--state", self.tmp, "--from", "2026-02-30"], ["--state", self.tmp, "--from", "26-11-01"],
                     *(["--state", self.tmp, "--from", "2026-11-01", "--days", n] for n in ("0", "32", "x", "-1", "1.5", "")),
                     ["--state", self.tmp, "--from", "9999-12-31", "--days", "2"], ["--bogus"]):
            code, out, err = run(*args)
            self.assertEqual(code, 2, args); self.assertEqual(out, "")
        self.assertEqual(run("--help")[0], 0)
        code, out, _ = run("--state", self.tmp, "--from", "2026-11-01", "--json")
        self.assertEqual(out.count("\n"), 1)
        r = json.loads(out)
        self.assertEqual((r["result"], r["from"], r["days"], r["timezone"]), ("ok", "2026-11-01", 7, "America/Los_Angeles"))
        self.assertEqual(set(r), {"result", "from", "days", "timezone", "daysSummary", "unknown", "totals"})
        self.assertEqual(set(r["totals"]), {"messages", "drafts", "approvals", "interpreterCalls"})
        code, text, _ = run("--state", self.tmp, "--from", "2026-11-01")
        lines = text.splitlines()
        self.assertEqual(len(lines), 9)
        self.assertTrue(lines[0].startswith("2026-11-01:") and lines[7].startswith("day unknown:")
                        and lines[8].startswith("totals:"))
        totals = dict(re.findall(r"[\[\s]([^\s\[\]=]+)=(\d+)", lines[8]))
        self.assertEqual(totals["approved"], "1"); self.assertEqual(totals["commands"], "1")
        self.assertEqual(totals["checked"], "1"); self.assertEqual(totals["approvals"], "0")
        self.assertEqual(r["totals"]["messages"]["approved"], 1)
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--state", self.tmp, "--from", "2026-11-01", "--json"],
                              capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual((proc.returncode, json.loads(proc.stdout)), (0, r)); self.assertEqual(proc.stderr, "")
        proc = subprocess.run([sys.executable, "-B", "-m", "hass.trial_summary", "--state", self.tmp, "--from", "2026-11-01",
                               "--json"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual((proc.returncode, json.loads(proc.stdout)), (0, r))
        doc = (ROOT / "docs" / "hass" / "TRIAL.md").read_text()
        section = doc.split("## Reviewing the trial", 1)[1].split("\n## ", 1)[0]
        for needle in ("hass/trial_summary.py --state", "--json", "Pacific", "day unknown", "interpreterDailyCap",
                       "not H18 completion"):
            self.assertIn(needle, section)


class _Cur:
    """Real cursor wrapper for a row query: refuses fetchall/fetchmany, counts rows pulled, may fail late."""
    def __init__(self, cur, log, fail_after=None):
        self._c, self._log, self._fail = cur, log, fail_after

    def fetchall(self): raise AssertionError("fetchall: whole table materialized")
    fetchmany = fetchall

    def __iter__(self):
        for n, row in enumerate(self._c):
            if self._fail is not None and n >= self._fail: raise sqlite3.OperationalError(f"{CANARY} disk I/O error")
            self._log.append(n); yield row
        if self._fail is not None: raise sqlite3.OperationalError(f"{CANARY} disk I/O error")


class _Db:
    def __init__(self, db, log, fail_after): self._d, self._log, self._fail = db, log, fail_after

    def execute(self, sql, *a):
        cur = self._d.execute(sql, *a)
        return _Cur(cur, self._log, self._fail) if sql.startswith("SELECT") and "sqlite_master" not in sql else cur

    def close(self): self._d.close()

    def __setattr__(self, name, v):
        if name in ("_d", "_log", "_fail"): object.__setattr__(self, name, v)
        else: setattr(self._d, name, v)


class StreamingTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(); self.addCleanup(self._t.cleanup); self.tmp = self._t.name

    def patched(self, fail_after=None):
        log, real = [], sqlite3.connect
        patcher = mock.patch.object(ts.sqlite3, "connect", lambda *a, **k: _Db(real(*a, **k), log, fail_after))
        patcher.start(); self.addCleanup(patcher.stop)
        return log

    def test_all_count_tables_iterate_without_fetchall(self):
        make_state(self.tmp, messages=[("approved", "2026-11-01T08:00:00-07:00"), ("commands", "2026-11-02T08:00:00-08:00")],
                   drafts=[("verified", "2026-11-01T08:00:00-07:00")], approvals=["2026-11-01T09:00:00-07:00"],
                   usage=[("2026-11-01", 3), ("2026-11-02", 4)])
        expected = report(self.tmp)
        log = self.patched()
        got = report(self.tmp)
        self.assertEqual(got, expected)
        self.assertEqual(got["totals"]["messages"]["approved"], 1); self.assertEqual(got["totals"]["approvals"], 1)
        self.assertEqual(got["totals"]["interpreterCalls"], 7); self.assertEqual(len(log), 2 + 1 + 1 + 2)

    def test_many_outside_rows_do_not_accumulate(self):
        db = sqlite3.connect(Path(self.tmp) / "conversation.sqlite3"); db.executescript(conversation.SCHEMA)
        db.executemany("INSERT INTO messages VALUES (?, ?, ?)",
                       [(f"m{i}", "approved", "2026-01-01T08:00:00-08:00") for i in range(5000)]
                       + [("in", "approved", "2026-11-01T08:00:00-07:00"), ("u", "approved", None)])
        db.commit(); db.close()
        log = self.patched()
        r = report(self.tmp, "2026-11-01", 1)
        self.assertEqual((r["totals"]["messages"]["approved"], r["unknown"]["messages"]["approved"]), (2, 1))
        self.assertEqual(len(log), 5002)

    def test_streamed_iteration_error_is_unreadable(self):
        make_state(self.tmp, messages=[("approved", "2026-11-01T08:00:00-07:00")] * 3)
        self.patched(fail_after=1)
        for extra in ([], ["--json"]):
            code, out, err = run("--state", self.tmp, "--from", "2026-11-01", *extra)
            self.assertEqual(code, 1); self.assertIn(out, ("Trial summary unavailable.\n", '{"result": "unreadable"}\n'))
            self.assertNotIn(CANARY, out + err)

    def test_streamed_old_and_missing_tables(self):
        db = sqlite3.connect(Path(self.tmp) / "conversation.sqlite3")
        db.execute("CREATE TABLE messages(id, disposition)"); db.execute("INSERT INTO messages VALUES ('a', 'approved')")
        db.execute("CREATE TABLE drafts(state)"); db.execute("INSERT INTO drafts VALUES ('verified')")
        db.commit(); db.close()
        other = tempfile.mkdtemp(dir=self.tmp)
        db = sqlite3.connect(Path(other) / "conversation.sqlite3")
        db.execute("CREATE TABLE drafts(created_at)"); db.commit(); db.close()
        self.patched()
        r = report(self.tmp)
        self.assertEqual((r["unknown"]["messages"]["approved"], r["totals"]["approvals"], r["totals"]["interpreterCalls"]), (1, 0, 0))
        self.assertEqual(sum(r["unknown"]["drafts"].values()), 1)
        self.assertEqual(run("--state", other, "--from", "2026-11-01")[0], 1)

    def test_streamed_usage_late_bad_calls_refuses(self):
        make_state(self.tmp, usage=[("2026-11-01", 3), ("2026-11-02", -1)])
        self.patched()
        code, out, _ = run("--state", self.tmp, "--from", "2026-11-01", "--json")
        self.assertEqual((code, out), (1, '{"result": "unreadable"}\n'))


if __name__ == "__main__":
    unittest.main()
