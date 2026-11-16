#!/usr/bin/env python3
"""AUDINV-CIW-06 offline checker: full-day avocado queue percentile report.

Local-only. Stdlib only. No network, no gh, no writes. Run:
  candidate.py --self-test
  candidate.py --check avocado-queue-percentiles-20261114.md --sources SOURCES.json
"""
import argparse, datetime as dt, json, math, os, re, sys, unittest

ROOT = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
DAY = ("2026-11-14T00:00:00Z", "2026-11-15T00:00:00Z")
IO_LOG = []  # every open() this module performs, so tests can prove "no I/O"


class Bad(ValueError):
    pass


def ts(v):
    """Parse strict UTC timestamp; raises Bad on malformed."""
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", v):
        raise Bad("malformed timestamp %r" % (v,))
    try:
        return dt.datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise Bad("malformed timestamp %r" % (v,))


def nearest_rank(samples, p):
    """rank = max(1, ceil(p*n)); None for no samples (UNKNOWN, never zero)."""
    if not samples:
        return None
    s = sorted(samples)
    return s[max(1, math.ceil(p * len(s))) - 1]


def summarize(samples):
    if not samples:
        return "UNKNOWN"
    s = sorted(samples)
    return {"n": len(s), "p50": nearest_rank(s, .5), "p90": nearest_rank(s, .9),
            "p95": nearest_rank(s, .95), "min": s[0], "max": s[-1], "samples": s}


def measure(records, pages_expected=None, pages_seen=None):
    """records: dicts run_id, attempt, job_id, event, name, labels, run_created,
    started, conclusion, optional job_created. Returns cohorts + exclusions + coverage."""
    excl, seen, cohorts = [], set(), {}
    lo, hi = ts(DAY[0]), ts(DAY[1])
    for r in records:
        ident = (r.get("run_id"), r.get("attempt"), r.get("job_id"))
        try:
            if None in ident:
                raise Bad("missing identity")
            if ident in seen:
                raise Bad("duplicate identity")
            seen.add(ident)
            rc = ts(r.get("run_created"))
            if not lo <= rc < hi:  # half-open UTC day selected by run created_at
                raise Bad("run created outside day")
            if not r.get("started"):
                raise Bad("incomplete: no start time")
            st = ts(r["started"])
            d_run = (st - rc).total_seconds()
            if d_run < 0:
                raise Bad("negative run-to-start interval")
            d_q = None
            if r.get("job_created") is not None:
                d_q = (st - ts(r["job_created"])).total_seconds()
                if d_q < 0:
                    raise Bad("negative job-created-to-start interval")
        except Bad as e:
            excl.append({"id": list(ident), "reason": str(e)})
            continue
        key = "%s|%s|%s" % ("PR" if r.get("event") == "pull_request" else "main-nightly",
                            r.get("conclusion") or "incomplete", r.get("name"))
        c = cohorts.setdefault(key, {"run_to_start_s": [], "true_queue_s": [], "queue_missing": 0})
        c["run_to_start_s"].append(d_run)
        if d_q is None:
            c["queue_missing"] += 1  # missing is not zero
        else:
            c["true_queue_s"].append(d_q)
    out = {k: {"run_to_start_s": summarize(v["run_to_start_s"]),
               "true_queue_s": summarize(v["true_queue_s"]),
               "queue_missing": v["queue_missing"]} for k, v in sorted(cohorts.items())}
    gap = sorted(set(pages_expected or []) - set(pages_seen or []))
    n_ok = sum(len(v["run_to_start_s"]) for v in cohorts.values())
    if pages_expected is None or gap or n_ok == 0:
        coverage = "INCOMPLETE"
    else:
        coverage = "COMPLETE"
    return {"cohorts": out, "exclusions": excl, "pages_missing": gap, "coverage": coverage}


def _under_root(rel):
    """Resolve rel beneath ROOT; reject traversal, absolute, symlink, protected roots
    BEFORE any open()."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel) or ".." in rel.split("/"):
        raise Bad("path escapes package root: %r" % (rel,))
    p = os.path.join(ROOT, rel)
    cur = ROOT
    for part in rel.split("/"):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise Bad("symlink refused: %r" % (rel,))
    if os.path.commonpath([os.path.realpath(p), ROOT]) != ROOT:
        raise Bad("path escapes package root: %r" % (rel,))
    return p


def _read(rel):
    p = _under_root(rel)
    IO_LOG.append(("open", p))
    with open(p, encoding="utf-8") as f:
        return f.read()


def _json(rel):
    return _parse(_read(rel))


def check_report(report_rel, sources_rel):
    """Validate the report's data block against SOURCES.json. Returns list of problems."""
    src = _json(sources_rel)
    md = _read(report_rel)
    m = re.search(r"```json report-data\n(.*?)\n```", md, re.S)
    if not m:
        return ["no report-data block"]
    try:
        d = _parse(m.group(1))
    except Bad as e:
        return ["report-data: %s" % e]
    bad = []
    ids = sorted(s["id"] for s in src.get("sources", []))
    if sorted(d.get("source_ids", [])) != ids:
        bad.append("source_ids do not match SOURCES.json")
    if list(d.get("window", [])) != list(DAY):
        bad.append("window is not the closed UTC day")
    cov, n = d.get("coverage"), d.get("n_jobs_in_window")
    if cov not in ("COMPLETE", "INCOMPLETE") or not isinstance(n, int) or n < 0:
        bad.append("coverage/n_jobs_in_window invalid")
        return bad
    missing = src.get("missing_coverage")
    if cov == "COMPLETE" and missing:
        bad.append("COMPLETE coverage contradicts missing source coverage")
    if cov == "INCOMPLETE" or missing:
        if d.get("status") != "HOLD":
            bad.append("incomplete coverage must be status HOLD")
        if d.get("queue_improvement_claim") != "NOT_ESTABLISHED":
            bad.append("improvement claimed without full-day coverage")
        if not missing:
            bad.append("SOURCES.json lists no missing coverage for an INCOMPLETE report")
    if n == 0 and (d.get("true_queue_s") != "UNKNOWN" or d.get("run_to_start_s") != "UNKNOWN"):
        bad.append("zero jobs must report UNKNOWN metrics, not numbers")
    if d.get("true_queue_s") not in ("UNKNOWN",) and not d.get("job_created_available"):
        bad.append("true queue percentiles need job-created timestamps")
    return bad


class Tests(unittest.TestCase):
    @staticmethod
    def rec(i, **kw):
        r = {"run_id": 1, "attempt": 1, "job_id": i, "event": "pull_request", "name": "check",
             "conclusion": "success", "run_created": "2026-11-14T10:00:00Z",
             "started": "2026-11-14T10:01:00Z"}
        r.update(kw)
        return r

    def test_nearest_rank_percentiles_for_one_and_even_samples(self):
        self.assertEqual(nearest_rank([7], .95), 7)
        s = [4, 1, 3, 2]
        self.assertEqual((nearest_rank(s, .5), nearest_rank(s, .9), nearest_rank(s, .95)), (2, 4, 4))
        self.assertIsNone(nearest_rank([], .5))
        self.assertEqual(summarize([0, 0])["p50"], 0)  # valid zero wait kept

    def test_true_queue_and_dependency_latency_are_separate(self):
        r = measure([self.rec(1, job_created="2026-11-14T10:00:50Z")])["cohorts"]
        c = next(iter(r.values()))
        self.assertEqual(c["run_to_start_s"]["p50"], 60)
        self.assertEqual(c["true_queue_s"]["p50"], 10)

    def test_missing_job_created_timestamp_does_not_become_zero(self):
        c = next(iter(measure([self.rec(1)])["cohorts"].values()))
        self.assertEqual(c["true_queue_s"], "UNKNOWN")
        self.assertEqual(c["queue_missing"], 1)
        self.assertEqual(c["run_to_start_s"]["n"], 1)

    def test_pagination_gap_cancelled_and_negative_intervals_are_explicit(self):
        m = measure([self.rec(1), self.rec(2, conclusion="cancelled"),
                     self.rec(3, started="2026-11-14T09:00:00Z"),
                     self.rec(4, started="garbage"), self.rec(5, started=None)],
                    pages_expected=[1, 2, 3], pages_seen=[1, 3])
        self.assertEqual(m["pages_missing"], [2])
        self.assertEqual(m["coverage"], "INCOMPLETE")
        self.assertEqual(sorted(k.split("|")[1] for k in m["cohorts"]), ["cancelled", "success"])
        reasons = sorted(e["reason"] for e in m["exclusions"])
        self.assertEqual(len(reasons), 3)
        self.assertIn("negative run-to-start interval", reasons)
        self.assertEqual(measure([self.rec(1)], [1], [1])["coverage"], "COMPLETE")

    def test_utc_day_boundary_and_unique_run_attempt_job_identity(self):
        m = measure([self.rec(1, run_created="2026-11-14T00:00:00Z", started="2026-11-14T00:00:05Z"),
                     self.rec(2, run_created="2026-11-15T00:00:00Z", started="2026-11-15T00:00:05Z"),
                     self.rec(3, run_created="2026-11-13T23:59:59Z", started="2026-11-14T00:00:05Z"),
                     self.rec(1), self.rec(1, attempt=2)])
        n = sum(c["run_to_start_s"]["n"] for c in m["cohorts"].values())
        self.assertEqual(n, 2)  # day start in; next day, previous day out; dup out; attempt 2 in
        self.assertEqual(sorted(e["reason"] for e in m["exclusions"]),
                         ["duplicate identity", "run created outside day", "run created outside day"])

    def test_missing_source_coverage_cannot_be_reported_complete(self):
        fx = _json("fixtures.json")
        complete = dict(fx["base"], coverage="COMPLETE")
        self.assertEqual(_problems(dict(complete, n_jobs_in_window=1), fx["source_ids"], []), [])
        for patch in ({}, {"status": "OK"}, {"queue_improvement_claim": "IMPROVED"},
                      {"status": "OK", "queue_improvement_claim": "IMPROVED"}):
            with self.subTest(patch=patch):
                got = _problems(dict(complete, **patch), fx["source_ids"], ["missing export"])
                self.assertIn("COMPLETE coverage contradicts missing source coverage", got)
                if patch.get("status") == "OK":
                    self.assertIn("incomplete coverage must be status HOLD", got)
                if patch.get("queue_improvement_claim") == "IMPROVED":
                    self.assertIn("improvement claimed without full-day coverage", got)

    def test_report_data_uses_strict_schema_and_duplicate_key_validation(self):
        fx = _json("fixtures.json")
        valid = json.dumps(fx["base"])
        self.assertEqual(_problems(fx["base"], fx["source_ids"], ["gap"]), [])
        cases = [
            (json.dumps(dict(fx["base"], schema_version=2)), "unknown schema_version"),
            (json.dumps({k: v for k, v in fx["base"].items() if k != "schema_version"}),
             "unknown schema_version"),
            ('{"schema_version": 1,' + valid[1:], "duplicate key 'schema_version'"),
            ('{"schema_version": 2,' + valid[1:], "duplicate key 'schema_version'"),
            ('{"status": "OK",' + valid[1:], "duplicate key 'status'"),
            (valid[:-1] + ', "extra": {"n": 1, "n": 2}}', "duplicate key 'n'"),
            ("{bad", "malformed json:"),
        ]
        for text, reason in cases:
            with self.subTest(text=text):
                got = _problems(fx["base"], fx["source_ids"], ["gap"], report_text=text)
                self.assertTrue(any(reason in problem for problem in got), got)

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        del IO_LOG[:]
        for bad in ("../x", "/etc/passwd", "a/../../x", "", None):
            with self.assertRaises(Bad):
                _under_root(bad)
        self.assertEqual(IO_LOG, [])  # refused before any open
        link = os.path.join(ROOT, "_selftest_link.json")
        os.symlink("/etc/hostname", link)
        try:
            with self.assertRaises(Bad):
                _read("_selftest_link.json")
        finally:
            os.unlink(link)
        self.assertEqual(IO_LOG, [])
        for text in ('{"schema_version":1,"schema_version":1}', '{"schema_version":2}', "{bad"):
            self.assertRaises(Bad, _parse, text)
        # deciding negatives from fixtures.json: each fail case must be caught by the checker
        fx = _json("fixtures.json")
        for c in fx["cases"]:
            got = _problems(dict(fx["base"], **c["patch"]), fx["source_ids"], c["missing"])
            self.assertEqual("fail" if got else "ok", c["expected"], c["name"])


def _parse(text):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise Bad("duplicate key %r" % k)
            d[k] = v
        return d
    try:
        d = json.loads(text, object_pairs_hook=pairs)
    except json.JSONDecodeError as e:
        raise Bad("malformed json: %s" % e)
    if not isinstance(d, dict) or d.get("schema_version") != 1:
        raise Bad("unknown schema_version")
    return d


def _problems(d, ids, missing, report_text=None):
    """In-memory variant of check_report's rules for the negative tests."""
    global _read
    saved = _read
    md = "```json report-data\n%s\n```" % (json.dumps(d) if report_text is None else report_text)
    src = json.dumps({"schema_version": 1, "sources": [{"id": i} for i in ids], "missing_coverage": missing})
    _read = lambda rel: md if rel.endswith(".md") else src
    try:
        # the stub bypasses file I/O but not the checker logic
        return check_report("r.md", "s.json")
    finally:
        _read = saved


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--check")
    ap.add_argument("--sources")
    a = ap.parse_args(argv)
    if a.self_test:
        r = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
        return 0 if r.wasSuccessful() else 1
    if a.check and a.sources:
        try:
            bad = check_report(a.check, a.sources)
        except (Bad, OSError) as e:
            bad = [str(e)]
        for b in bad:
            print("FAIL:", b)
        print("check:", "FAIL" if bad else "PASS (structure only; not an acceptance of the evidence)")
        return 1 if bad else 0
    ap.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
