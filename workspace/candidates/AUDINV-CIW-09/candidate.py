#!/usr/bin/env python3
"""AUDINV-CIW-09 local checker for hass-suite-cost-20261114.md. Offline, stdlib only, read-only.

  --self-test                          named synthetic checks (local only, not CI-registered)
  --check REPORT.md --sources SRC.json both paths resolve beneath this package root
"""
import argparse, json, os, re, statistics, sys, unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.realpath(__file__))
UNK = "UNKNOWN"


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def resolve(name, root=ROOT):
    """Path beneath root only: no absolute, no traversal, no symlink component."""
    if not isinstance(name, str) or not name or os.path.isabs(name) or ".." in name.replace("\\", "/").split("/"):
        raise ValueError("path escapes package root: %r" % (name,))
    p = root
    for part in name.split("/"):
        p = os.path.join(p, part)
        if os.path.islink(p):
            raise ValueError("symlink in path: %r" % (name,))
    real = os.path.realpath(p)
    if os.path.commonpath([real, root]) != root:
        raise ValueError("path escapes package root: %r" % (name,))
    return real


def _no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate key %r" % k)
        d[k] = v
    return d


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read(), object_pairs_hook=_no_dupes)


def validate(src):
    if not isinstance(src, dict) or src.get("schema_version") != 1:
        raise ValueError("unknown or missing schema_version")
    for k in ("window", "runs", "jobs", "workflow_revisions"):
        if k not in src:
            raise ValueError("missing key " + k)
    ts(src["window"]["start"]); ts(src["window"]["end"])
    seen = set()
    for j in src["jobs"]:
        key = (j["run"], j["attempt"], j["job_id"])
        if key in seen:
            raise ValueError("duplicate job %r" % (key,))
        seen.add(key)
        if j["kind"] not in ("shard", "quick"):
            raise ValueError("bad job kind")
    for r in src["runs"]:
        c = ts(r["created"])
        if not (ts(src["window"]["start"]) <= c < ts(src["window"]["end"])):
            raise ValueError("run %s outside window" % r["run"])
    return src


def dist(xs):
    if not xs:
        return {"n": 0, "min": UNK, "median": UNK, "p90": UNK, "max": UNK}
    s = sorted(xs)
    return {"n": len(s), "min": s[0], "median": statistics.median(s), "p90": s[max(0, -(-len(s) * 9 // 10) - 1)], "max": s[-1]}


def summarize(src):
    """Everything is derived from observed receipts; plan weights / planned counts are never read."""
    validate(src)
    latest = {}
    superseded = 0
    for r in src["runs"]:
        cur = latest.get(r["run"])
        if cur is None or r["attempt"] > cur["attempt"]:
            superseded += cur is not None
            latest[r["run"]] = r
        else:
            superseded += 1
    jobs = [j for j in src["jobs"] if j["run"] in latest and latest[j["run"]]["attempt"] == j["attempt"]]
    revs = src["workflow_revisions"]

    def timeout(j):
        rev = revs.get(latest[j["run"]].get("workflow_rev"), {})
        return rev.get("shard_timeout_s" if j["kind"] == "shard" else "quick_timeout_s")

    def elapsed(j):
        return ts(j["completed"]) - ts(j["started"]) if j.get("started") and j.get("completed") else None

    out: dict = {"runs": len(latest), "superseded_attempt_records_excluded": superseded}
    for kind in ("shard", "quick"):
        kj = [j for j in jobs if j["kind"] == kind]
        out[kind + "_jobs_by_conclusion"] = dict(sorted(__import__("collections").Counter(str(j["conclusion"]) for j in kj).items()))
        ok = [(elapsed(j), timeout(j)) for j in kj if j["conclusion"] == "success" and elapsed(j) is not None]
        out[kind + "_success_elapsed_s"] = dist([e for e, _ in ok])
        hr = [t - e for e, t in ok if t]
        out[kind + "_min_headroom_s"] = min(hr) if hr else UNK
        rat = [e / t for e, t in ok if t and t > 0]
        out[kind + "_max_elapsed_over_timeout"] = round(max(rat), 4) if rat else UNK
        cen = [elapsed(j) for j in kj if j["conclusion"] == "cancelled" and elapsed(j) is not None]
        out[kind + "_censored_cancelled"] = {"n": len([j for j in kj if j["conclusion"] == "cancelled"]), "max_elapsed_s": max(cen) if cen else UNK,
                                              "reached_timeout": any(t and e >= t for e, t in [(elapsed(j), timeout(j)) for j in kj if j["conclusion"] == "cancelled" and elapsed(j) is not None])}
    sh = [j for j in jobs if j["kind"] == "shard" and j["conclusion"] == "success"]
    out["shard_tests_ran"] = dist([j["tests_ran"] for j in sh if j.get("tests_ran") is not None])
    out["shard_success_without_test_count"] = len([j for j in sh if j.get("tests_ran") is None])
    complete = []
    for run, r in latest.items():
        rs = [j for j in jobs if j["run"] == run and j["kind"] == "shard"]
        if rs and len(rs) >= 2 and all(j["conclusion"] == "success" and j.get("tests_ran") is not None and elapsed(j) is not None for j in rs):
            wall = ts(r["last_job_end"]) - ts(r["first_job_start"]) if r.get("last_job_end") and r.get("first_job_start") else None
            complete.append({"created": r["created"], "run": run, "shards": len(rs), "sum_shard_s": sum(elapsed(j) for j in rs), "max_shard_s": max(elapsed(j) for j in rs),
                             "critical_path_s": wall, "tests": sum(j["tests_ran"] for j in rs)})
    complete.sort(key=lambda c: (c["created"], c["run"]))
    out["complete_full_runs"] = len(complete)
    for k in ("sum_shard_s", "max_shard_s", "critical_path_s", "tests"):
        out["per_run_" + k] = dist([c[k] for c in complete if c[k] is not None])
    cohort = [c for c in complete if c["shards"] == 4]
    if len(cohort) >= 20:
        a, b = cohort[:10], cohort[-10:]
        out["growth_within_window"] = {"comparable": True, "basis": "first 10 vs last 10 complete 4-shard runs by creation time, same workflow timeouts; descriptive only, not a trend or cross-day claim",
                                       "first10_median_tests": statistics.median(c["tests"] for c in a), "last10_median_tests": statistics.median(c["tests"] for c in b),
                                       "first10_median_max_shard_s": statistics.median(c["max_shard_s"] for c in a), "last10_median_max_shard_s": statistics.median(c["max_shard_s"] for c in b)}
    else:
        out["growth_within_window"] = {"comparable": False, "value": UNK}
    out["cross_day_or_pre_parallelism_growth"] = UNK
    return out


def render_check(report_text, src):
    """Return list of problems; empty means structurally correct and bound to the sources."""
    errs = []
    m = re.search(r"```json summary\n(.*?)\n```", report_text, re.S)
    if not m:
        return ["no 'json summary' block"]
    try:
        got = json.loads(m.group(1), object_pairs_hook=_no_dupes)
    except ValueError as e:
        return ["summary block invalid: %s" % e]
    want = summarize(src)
    if got != want:
        errs.append("summary block differs from values recomputed from SOURCES.json: " + ", ".join(sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))))
    for h in ("## Observed shard durations", "## Timeout headroom", "## Per-run critical path", "## Growth", "## Unknown / missing"):
        if h not in report_text:
            errs.append("missing section " + h)
    if UNK not in report_text:
        errs.append("report never states UNKNOWN")
    if src["inspected_main"] not in report_text:
        errs.append("report does not cite inspected main")
    return errs


def check(report, sources):
    src = validate(load_json(resolve(sources)))
    with open(resolve(report), encoding="utf-8") as f:
        text = f.read()
    errs = render_check(text, src)
    for e in errs:
        print("FAIL:", e)
    if not errs:
        print("OK: report matches %d runs / %d jobs in %s" % (len(src["runs"]), len(src["jobs"]), sources))
    return 1 if errs else 0


# ---- embedded named self-tests (local only) ----
def _src(jobs, runs=None, revs=None):
    runs = runs or [{"run": 1, "attempt": 1, "created": "2026-11-14T01:00:00Z", "workflow_rev": "a", "first_job_start": "2026-11-14T01:00:00Z", "last_job_end": "2026-11-14T01:20:00Z"}]
    return {"schema_version": 1, "window": {"start": "2026-11-14T00:00:00Z", "end": "2026-11-15T00:00:00Z"}, "runs": runs, "jobs": jobs,
            "workflow_revisions": revs if revs is not None else {"a": {"shard_timeout_s": 1800, "quick_timeout_s": 1200}}}


def _j(i, shard, end, concl="success", ran=100, run=1, attempt=1, start="2026-11-14T01:00:00Z"):
    return {"run": run, "attempt": attempt, "job_id": i, "kind": "shard", "shard": shard, "conclusion": concl, "started": start, "completed": end, "tests_ran": ran}


class Cases(unittest.TestCase):
    def test_observed_walltime_and_sum_of_shards_are_distinct(self):
        s = summarize(_src([_j(1, 0, "2026-11-14T01:10:00Z"), _j(2, 1, "2026-11-14T01:05:00Z")]))
        self.assertEqual(s["per_run_sum_shard_s"]["max"], 900)
        self.assertEqual(s["per_run_max_shard_s"]["max"], 600)
        self.assertEqual(s["per_run_critical_path_s"]["max"], 1200)

    def test_plan_weight_and_planned_count_are_not_actual_receipts(self):
        j = _j(1, 0, "2026-11-14T01:10:00Z", ran=None)
        j.update({"plan_weight": 290, "planned_tests": 500})
        s = summarize(_src([j]))
        self.assertEqual(s["shard_tests_ran"]["n"], 0)
        self.assertEqual(s["shard_tests_ran"]["max"], UNK)
        self.assertEqual(s["shard_success_without_test_count"], 1)
        self.assertEqual(s["complete_full_runs"], 0)

    def test_missing_timeout_count_or_samples_stays_unknown(self):
        s = summarize(_src([], revs={}))
        self.assertEqual(s["shard_success_elapsed_s"]["median"], UNK)
        self.assertEqual(s["growth_within_window"]["value"], UNK)
        s2 = summarize(_src([_j(1, 0, "2026-11-14T01:10:00Z")], revs={}))
        self.assertEqual(s2["shard_min_headroom_s"], UNK)
        self.assertEqual(s2["shard_max_elapsed_over_timeout"], UNK)

    def test_cancelled_timeout_and_retry_attempts_not_double_counted(self):
        runs = [{"run": 1, "attempt": 1, "created": "2026-11-14T01:00:00Z", "workflow_rev": "a"}, {"run": 1, "attempt": 2, "created": "2026-11-14T01:00:00Z", "workflow_rev": "a"}]
        jobs = [_j(1, 0, "2026-11-14T01:01:00Z", "cancelled", None, attempt=1), _j(2, 0, "2026-11-14T01:10:00Z", attempt=2)]
        s = summarize(_src(jobs, runs))
        self.assertEqual(s["shard_success_elapsed_s"]["n"], 1)
        self.assertEqual(s["shard_censored_cancelled"]["n"], 0)
        self.assertEqual(s["superseded_attempt_records_excluded"], 1)
        s = summarize(_src([_j(1, 0, "2026-11-14T01:30:00Z", "cancelled", None)]))
        self.assertEqual(s["shard_success_elapsed_s"]["n"], 0)
        self.assertTrue(s["shard_censored_cancelled"]["reached_timeout"])
        with self.assertRaises(ValueError):
            summarize(_src([_j(1, 0, "2026-11-14T01:10:00Z"), _j(1, 0, "2026-11-14T01:10:00Z")]))

    def test_headroom_seconds_and_percentage_use_exact_workflow_revision(self):
        runs = [{"run": 1, "attempt": 1, "created": "2026-11-14T01:00:00Z", "workflow_rev": "a"}, {"run": 2, "attempt": 1, "created": "2026-11-14T02:00:00Z", "workflow_rev": "b"}]
        revs = {"a": {"shard_timeout_s": 1800}, "b": {"shard_timeout_s": 900}}
        jobs = [_j(1, 0, "2026-11-14T01:10:00Z"), _j(2, 0, "2026-11-14T02:10:00Z", run=2, start="2026-11-14T02:00:00Z")]
        s = summarize(_src(jobs, runs, revs))
        self.assertEqual(s["shard_min_headroom_s"], 300)
        self.assertEqual(s["shard_max_elapsed_over_timeout"], round(600 / 900, 4))

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        opened = []
        real_open = open
        import builtins
        builtins.open = lambda *a, **k: (opened.append(a), real_open(*a, **k))[1]
        try:
            for bad in ("../x.json", "/etc/passwd", "a/../../x"):
                with self.assertRaises(ValueError):
                    resolve(bad)
            self.assertEqual(opened, [], "no file may be opened before the path guard rejects")
            with self.assertRaises(ValueError):
                validate({"schema_version": 2})
            with self.assertRaises(ValueError):
                json.loads('{"a":1,"a":2}', object_pairs_hook=_no_dupes)
            link = os.path.join(ROOT, "_selftest_link")
            os.symlink("/", link)
            try:
                with self.assertRaises(ValueError):
                    resolve("_selftest_link/etc")
            finally:
                os.unlink(link)
        finally:
            builtins.open = real_open
        self.assertEqual([a for a in opened if len(a) > 1 and any(c in str(a[1]) for c in "wa+x")], [])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--check")
    ap.add_argument("--sources")
    a = ap.parse_args(argv)
    if a.self_test:
        r = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases))
        return 0 if r.wasSuccessful() else 1
    if a.check and a.sources:
        try:
            return check(a.check, a.sources)
        except (ValueError, OSError, KeyError) as e:
            print("FAIL:", e)
            return 1
    ap.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
