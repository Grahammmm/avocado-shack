#!/usr/bin/env python3
"""AUDINV-CIW-10 candidate: offline avocado shard-contention retuning evidence checker.

Local-only, stdlib-only, read-only over its own package root. No network, no live mode, no apply switch.
  --self-test                         run the embedded unittest cases (synthetic fixtures only)
  --check REPORT.md --sources SRC     validate the report against SOURCES.json (paths resolve under package root)
  --render REPORT.md --sources SRC    write the report from SOURCES.json (deterministic)
  --extract CACHE_DIR WORKFLOW OUT    one-shot: build SOURCES.json from the existing ci-metrics cache (read-only)
"""
import hashlib
import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
W0, W1 = "2026-11-14T00:00:00Z", "2026-11-15T00:00:00Z"
MIN_N = 5          # comparable completed runs required in EACH of two widths before any retuning is recommended
SHARD_RE = re.compile(r"^hass shard (\d+)$")
TS_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


class Bad(Exception):
    pass


def ts(s):
    if not isinstance(s, str) or not TS_RE.match(s):
        raise Bad("invalid timestamp %r" % (s,))
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def in_window(s):
    return W0 <= s < W1  # lexical compare is exact for fixed-width UTC stamps


def safe_path(rel, root=ROOT):
    """Resolve rel beneath root; refuse traversal, absolute paths and symlinks before any open."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"):
        raise Bad("path escapes package root: %r" % (rel,))
    p = os.path.join(root, rel)
    cur = root
    for part in rel.split("/"):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise Bad("symlink refused: %r" % (rel,))
    if os.path.commonpath([os.path.realpath(root), os.path.realpath(p)]) != os.path.realpath(root):
        raise Bad("path escapes package root: %r" % (rel,))
    return p


def _nodup(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise Bad("duplicate key %r" % k)
        d[k] = v
    return d


def load_json(rel, root=ROOT):
    with open(safe_path(rel, root), encoding="utf-8") as f:
        d = json.load(f, object_pairs_hook=_nodup)
    if not isinstance(d, dict) or d.get("schema_version") != 1:
        raise Bad("unknown or missing schema_version in %s" % rel)
    return d


def pct(vals, q):
    v = sorted(vals)
    return None if not v else v[min(len(v) - 1, int(q * len(v)))]


def joinable(a, b):
    """Contention and elapsed observations join only for the same head+attempt cohort AND overlapping intervals."""
    if (a["head"], a["run"], a["attempt"]) != (b["head"], b["run"], b["attempt"]):
        return False
    return ts(a["start"]) < ts(b["end"]) and ts(b["start"]) < ts(a["end"])


def derive(src):
    """Pure function of SOURCES.json -> report facts. Configured width is never read as measured concurrency."""
    runs = {}
    for r in src["runs"]:
        if not in_window(r["created"]):
            continue
        k = (r["id"], r["attempt"])
        if k in runs:
            raise Bad("duplicate run %r" % (k,))
        runs[k] = r
    jobs = []
    for j in src["jobs"]:
        if (j["run"], j["attempt"]) in runs:
            jobs.append(j)
    by_run = {}
    for j in jobs:
        m = SHARD_RE.match(j["name"])
        if m and j["conclusion"] in ("success", "failure") and j["started"] and j["completed"]:
            by_run.setdefault((j["run"], j["attempt"]), []).append(j)
    ivs = [(ts(j["started"]), ts(j["completed"])) for j in jobs if j["started"] and j["completed"]]
    rows = []
    for k, shards in sorted(by_run.items()):
        r = runs[k]
        width = len({SHARD_RE.match(j["name"]).group(1) for j in shards})
        peak_own = max(sum(1 for o in shards if ts(o["started"]) <= ts(s["started"]) < ts(o["completed"])) for s in shards)
        cc = [sum(1 for a, b in ivs if a <= ts(s["started"]) < b) - 1 for s in shards]  # other avocado jobs, same instant
        el = [ts(s["completed"]) - ts(s["started"]) for s in shards]
        rows.append({"run": k[0], "attempt": k[1], "head": r["head"], "event": r["event"], "observed_width": width,
                     "measured_own_peak": peak_own, "others_at_start_max": max(cc), "shard_elapsed_max_s": max(el),
                     "shard_elapsed_sum_s": sum(el)})
    widths = {}
    for r in rows:
        widths.setdefault(r["observed_width"], []).append(r["shard_elapsed_max_s"])
    per_width = {str(w): {"n": len(v), "p50_s": pct(v, .5), "p90_s": pct(v, .9)} for w, v in sorted(widths.items())}
    host = src["missing_coverage"]
    missing = sorted(k for k, v in host.items() if isinstance(v, str) and v.startswith("UNKNOWN"))
    return {"window": [W0, W1], "runs_in_window": len(runs), "runs_with_sampled_jobs": len({(j["run"], j["attempt"]) for j in jobs}),
            "full_tier_runs_with_shard_jobs": len(rows), "per_observed_width": per_width, "run_rows": rows,
            "distinct_heads": len({r["head"] for r in rows}), "missing_metrics": missing,
            "verdict": verdict(per_width, missing)}


def verdict(per_width, missing):
    comparable = [w for w, s in per_width.items() if s["n"] >= MIN_N]
    why = []
    if len(per_width) < 2:
        why.append("only one observed width (%s); no comparable contrast" % ",".join(per_width) if per_width else "no shard jobs observed")
    elif len(comparable) < 2:
        why.append("fewer than two widths have n>=%d" % MIN_N)
    if missing:
        why.append("missing metrics (not zero): " + ",".join(missing))
    if why:
        return {"verdict": "HOLD", "recommendation": None, "reasons": why}
    best = min(comparable, key=lambda w: per_width[w]["p50_s"])
    return {"verdict": "RETUNE-CANDIDATE", "recommendation": "width %s showed lowest p50 among comparable widths; confirm confounders" % best, "reasons": []}


# ---- report ---------------------------------------------------------------------------------------------------
FENCE = "```json derived\n"
HEADS = ["## Verdict", "## Window and sources", "## Observed widths and heads", "## Current workflow", "## Missing coverage and confounders"]


def render(src):
    d = derive(src)
    wf = src["workflow"]
    per = d["per_observed_width"]
    L = ["# Avocado shard contention retuning evidence, 2026-11-14 (UTC) — CIW-10", "",
         "## Verdict", "", "**%s** — no retuning is recommended." % d["verdict"]["verdict"] if d["verdict"]["verdict"] == "HOLD"
         else "**%s** — %s" % (d["verdict"]["verdict"], d["verdict"]["recommendation"]), ""]
    L += ["- " + x for x in d["verdict"]["reasons"]] + [""]
    L += ["## Window and sources", "", "Window [%s, %s). #335 (width-two variable/cap) is merged and excluded; this report changes no variable, cap or workflow." % (W0, W1), ""]
    L += ["- `%s` sha256 `%s` (%d bytes), captured %s" % (i["name"], i["sha256"], i["bytes"], i["captured"]) for i in src["inputs"]] + [""]
    L += ["- runs created in window: %d; of those, runs whose jobs were sampled: %d; runs with completed `hass shard N` jobs: %d" %
          (d["runs_in_window"], d["runs_with_sampled_jobs"], d["full_tier_runs_with_shard_jobs"]), ""]
    L += ["## Observed widths and heads", "", "| observed width | runs | p50 slowest-shard s | p90 s |", "|---|---|---|---|"]
    L += ["| %s | %d | %s | %s |" % (w, s["n"], s["p50_s"], s["p90_s"]) for w, s in per.items()] + [""]
    L += ["Distinct heads among those runs: %d. Per-run rows (head, attempt, own-peak concurrency, other sampled avocado jobs running at shard start, "
          "which includes the run's own sibling shards) are in the JSON block below; the 'others' count is a LOWER BOUND, counting only sampled jobs. "
          "Slowest-shard elapsed here is descriptive: the workflow comment expects ~290 s per shard at width 4, the observed p50 is higher, but without runner or host data "
          "that gap cannot be attributed to shard width." % d["distinct_heads"], ""]
    L += ["## Current workflow", "", "Observed `%s` at main `%s` (sha256 `%s`):" % (wf["path"], wf["main_sha"], wf["sha256"]), ""]
    L += ["    " + q for q in wf["quote"]] + ["", "Current fallback width is %d. The repository variable's value was not read (config read forbidden); "
          "configured width is therefore UNKNOWN and is not equated with measured concurrency." % wf["fallback_width"], ""]
    L += ["## Missing coverage and confounders", ""] + ["- **%s**: %s" % (k, v) for k, v in sorted(src["missing_coverage"].items())]
    L += ["", "Confounders: PR vs push events and different heads change shard weight; other avocado workflows share the 8 runners; "
          "no width contrast exists in the window, so no causal claim about width is made.", "", "## Derived data", "", FENCE + json.dumps(d, indent=1, sort_keys=True) + "\n```", ""]
    return "\n".join(L)


def check(report_text, src):
    for h in HEADS:
        if h not in report_text:
            raise Bad("missing section %r" % h)
    m = re.search(re.escape(FENCE) + r"(.*?)\n```", report_text, re.S)
    if not m:
        raise Bad("missing derived block")
    got = json.loads(m.group(1), object_pairs_hook=_nodup)
    want = derive(src)
    if got != json.loads(json.dumps(want)):
        raise Bad("derived block does not match SOURCES.json")
    v = want["verdict"]
    if v["verdict"] == "HOLD" and ("**HOLD**" not in report_text or v["recommendation"] is not None):
        raise Bad("HOLD not stated honestly")
    if v["verdict"] != "HOLD" and want["missing_metrics"]:
        raise Bad("success asserted with missing metrics")
    if "#335" not in report_text or src["workflow"]["quote"][0] not in report_text:
        raise Bad("workflow/#335 binding missing")
    if report_text != render(src):
        raise Bad("report text differs from deterministic render")
    return v["verdict"]


# ---- one-shot extraction from the existing receipts -------------------------------------------------------------
def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def extract(cache, wf_path, out_rel):
    out = safe_path(out_rel)
    runs, inputs = [], []
    for day in ("2026-11-13", "2026-11-14"):
        p = os.path.join(cache, "runs-avocado-shack-%s.json" % day)
        d = json.load(open(p))
        inputs.append({"name": os.path.basename(p), "sha256": sha(p), "bytes": os.path.getsize(p), "captured": d["fetched"].replace("+00:00", "Z")})
        for x in d["runs"]:
            if in_window(x["created_at"]) and x["path"] == ".github/workflows/check.yml":
                runs.append({"id": x["id"], "attempt": x["run_attempt"], "head": x["head_sha"][:12], "event": x["event"],
                             "created": x["created_at"], "status": x["status"], "conclusion": x["conclusion"]})
    jp = os.path.join(cache, "jobs.json")
    inputs.append({"name": "jobs.json", "sha256": sha(jp), "bytes": os.path.getsize(jp), "captured": "UNKNOWN (cache file mtime only)"})
    jobs_all = json.load(open(jp))
    keys = {(r["id"], r["attempt"]) for r in runs}
    jobs = []
    for k, js in sorted(jobs_all.items()):
        rid, at, att = k.partition("@")
        if at and (int(rid), int(att)) in keys:
            for j in js:
                jobs.append({"run": int(rid), "attempt": int(att), "name": j["name"], "created": j["created_at"], "started": j["started_at"],
                             "completed": j["completed_at"], "conclusion": j["conclusion"]})
    text = open(wf_path).read()
    quote = [l.strip() for l in text.splitlines() if "HASS_SHARD_JOBS" in l and ("vars." in l or "Retune" in l)]
    src = {"schema_version": 1, "window": {"start": W0, "end_exclusive": W1}, "inputs": inputs,
           "workflow": {"path": ".github/workflows/check.yml", "main_sha": "1a8efafbef247783f6a64c0d1f4bf84d96ceaffc", "sha256": sha(wf_path),
                        "quote": quote, "fallback_width": 4},
           "missing_coverage": {"runner_identity": "UNKNOWN: receipts carry no runner name/alias per job",
                                "host_cpu_disk_metrics": "UNKNOWN: no per-interval CPU/iowait/disk series in the receipts",
                                "repository_variable_value": "UNKNOWN: HASS_SHARD_JOBS value not read (config read out of scope)",
                                "unsampled_runs": "jobs.json is a sample; runs without sampled jobs have no elapsed data"},
           "runs": runs, "jobs": jobs}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(src, f, indent=1, sort_keys=True)
        f.write("\n")


# ---- tests ------------------------------------------------------------------------------------------------------
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = load_json("fixtures.json")

    def test_equal_heads_and_overlapping_intervals_required_for_join(self):
        for c in self.fx["join_cases"]:
            self.assertEqual(joinable(c["a"], c["b"]), c["expect"], c["why"])

    def test_configured_width_not_measured_concurrency(self):
        d = derive(self.fx["width4_sequential"])
        r = d["run_rows"][0]
        self.assertEqual(r["observed_width"], 4)
        self.assertEqual(r["measured_own_peak"], 1)  # four shards configured, never concurrent
        self.assertIn("repository_variable_value", d["missing_metrics"])

    def test_confounded_or_insufficient_samples_produce_hold(self):
        for c in self.fx["verdict_cases"]:
            v = verdict(c["per_width"], c["missing"])
            self.assertEqual(v["verdict"] == "HOLD", c["hold"], c["why"])
            self.assertEqual(v["recommendation"] is None, c["hold"], c["why"])

    def test_missing_contention_metric_not_zero(self):
        d = derive(self.fx["width4_sequential"])
        self.assertIn("host_cpu_disk_metrics", d["missing_metrics"])   # named as missing, never rendered as 0
        self.assertNotIn("cpu", json.dumps(d["per_observed_width"]).lower())
        self.assertEqual(d["verdict"]["verdict"], "HOLD")
        self.assertIn("missing metrics", " ".join(d["verdict"]["reasons"]))

    def test_fixed_window_and_different_attempts_remain_distinct(self):
        d = derive(self.fx["attempts_and_window"])
        self.assertEqual(d["runs_in_window"], 2)           # run 3 created at W1 is excluded; attempts 1 and 2 of run 1 are distinct
        self.assertEqual(sorted((r["run"], r["attempt"]) for r in d["run_rows"]), [(1, 1), (1, 2)])
        dup = json.loads(json.dumps(self.fx["attempts_and_window"]))
        dup["runs"].append(dict(dup["runs"][0]))
        with self.assertRaises(Bad):
            derive(dup)

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        opened = []
        real = open
        import builtins
        builtins.open = lambda *a, **k: (opened.append(a[0]), real(*a, **k))[1]
        try:
            for bad in ("../x.json", "/etc/passwd", "a/../../x", ""):
                with self.assertRaises(Bad):
                    safe_path(bad)
            link = os.path.join(ROOT, "_sym_test")
            os.symlink("/", link)
            try:
                with self.assertRaises(Bad):
                    safe_path("_sym_test/etc")
            finally:
                os.unlink(link)
            with self.assertRaises(Bad):
                ts("2026-11-14 00:00:00")
            self.assertEqual(opened, [])               # nothing was opened for any refused path
            with self.assertRaises(Bad):
                json.loads('{"a":1,"a":2}', object_pairs_hook=_nodup)
            with self.assertRaises(Bad):
                check("no sections", self.fx["width4_sequential"])
        finally:
            builtins.open = real


def main(argv):
    try:
        if argv == ["--self-test"]:
            r = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
            return 0 if r.wasSuccessful() else 1
        if len(argv) == 4 and argv[0] in ("--check", "--render") and argv[2] == "--sources":
            src = load_json(argv[3])
            if argv[0] == "--render":
                with open(safe_path(argv[1]), "w", encoding="utf-8") as f:
                    f.write(render(src))
                return 0
            with open(safe_path(argv[1]), encoding="utf-8") as f:
                print("check OK verdict=%s" % check(f.read(), src))
            return 0
        if len(argv) == 4 and argv[0] == "--extract":
            extract(argv[1], argv[2], argv[3])
            return 0
    except (Bad, OSError, KeyError, ValueError) as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        return 2
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
