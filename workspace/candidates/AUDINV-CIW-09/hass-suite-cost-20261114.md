# Hass suite cost, 2026-11-14 (post-parallelism CI receipts)

Window: 2026-11-14T00:00:00Z inclusive to 2026-11-15T00:00:00Z exclusive. Repo `Grahammmm/avocado-shack`, workflow `check` (`.github/workflows/check.yml`), inspected main `1b0f5b877230e36c060a17777fa285d436bd7d43`.
Status: CANDIDATE_ONLY / REVIEW_REQUIRED, NOT_INSTALLED. Read-only evidence report: no monitoring, new CI run or timeout change is authorized or made.

## Source and method

- Receipts: GitHub Actions run and job records (read-only API) for every `check` run created in the window: 100 runs, 429 quick/shard jobs, captured 2026-11-16T02:03:11Z. Digest-bound metadata is in `SOURCES.json`.
- Test count of a shard = the `Ran N tests` line of that shard's own job log (an executed count). `hass/tests/ci_weights.json` estimates and planned module counts are not used anywhere.
- Elapsed = job `completed_at` minus `started_at`. Headroom = configured `timeout-minutes` x 60 minus observed elapsed; ratio = elapsed / timeout.
- Timeouts (exact workflow revision): the shard job is 30 min (1800 s), the quick job 20 min (1200 s). `check.yml` changed once in the window (commit 4f9ea651e538, 00:46:27Z, a comment-only edit); the file's sha256 is `6cf5f534356ece9dd71523a807a97814053af8d546f55c6d97136c8ace624957` before and `cc91cfaaaf826c693ab0f1d06ae1af18129bc917f44fb6d05df5fd74273471dd` after, and both have identical `timeout-minutes` lines. Per-PR-head workflow text was not fetched (UNKNOWN for a PR that edits `.github/`; such a PR is forced to the full tier by the workflow rules).
- Parallelism: all complete full-tier runs in the window used 4 shards (`HASS_SHARD_JOBS` default).

## Observed shard durations

Successful `hass shard` jobs: n=285; min 452 s, median 710 s, p90 862 s, max 1067 s.
Outcomes of 339 shard jobs: {'cancelled': 38, 'failure': 10, 'skipped': 6, 'success': 285}. Cancelled jobs are censored (not passes, not zero): 38 jobs, longest 850 s, none reached the timeout. Failed shard jobs (10) are in runs 43549651208, 43550458639, 43552723684, 43553546652, 43554558279, 43555213691, 43655881666; their durations are not in the distribution above.
Executed tests per successful shard: min 1432, median 1681, p90 1894, max 2022 (n=285; success shards without a parsed count: 0). Skipped-test counts are recorded per job in `SOURCES.json`; they are not summarised here.
Slowest shards:
- run 43632902790 shard 3 (head `17db1ca0cf67`): 1067s
- run 43629016385 shard 1 (head `48d0c32307b3`): 981s
- run 43631279410 shard 3 (head `cfc29b9960ec`): 971s

The `quick` job also runs the affected hass tests on pull requests. Successful quick jobs: n=89; median 16 s, p90 23 s, max 919 s. Its test counts are UNKNOWN (logs not parsed). Slowest:
- run 43540804205 (pull_request, head `a591655c881d`): 919s
- run 43634981469 (pull_request, head `84331abb7804`): 452s
- run 43634692444 (pull_request, head `08ee44f87bc8`): 176s
- run 43631721488 (pull_request, head `9f4234073e21`): 160s
- run 43551595026 (pull_request, head `b9a134ca1242`): 79s

## Timeout headroom

- Shard job (1800 s): the longest successful shard is 1067 s, so minimum observed headroom is 733 s and the highest elapsed/timeout ratio is 0.5928. Median headroom is 1090 s.
- Quick job (1200 s): longest successful 919 s gives minimum headroom 281 s, ratio 0.7658. This is the thinner margin, and it occurs in a pull-request run that executed the affected tier inside `quick` (the 480 s affected-tier budget is a selected-test-time budget; observed elapsed also includes setup).
- Reading: no shard approached its timeout in this window. Measured headroom does not by itself support raising the shard timeout. The quick job's single 919 s sample is the only one worth a later look; this report does not recommend or change any timeout.

## Per-run critical path

Runs where every shard succeeded with a parsed test count: 65 (all 4 shards). Summed shard time and critical path are different quantities:

| per run | n | min | median | p90 | max |
|---|---|---|---|---|---|
| summed shard time (s) | 65 | 2445 | 2760 | 3128 | 3363 |
| slowest shard (s) | 65 | 728 | 818 | 919 | 1067 |
| critical path, first job start to last job end (s) | 65 | 773 | 985 | 1685 | 3670 |
| executed tests, all shards | 65 | 6454 | 6914 | 7032 | 7080 |

The critical path includes the quick job and the site jobs, so a long value there can come from a slow `site static` or `quick` job or from runner wait between jobs, not only from the hass shards. Runs without all shards complete (cancelled, failed, or affected tier) are excluded here and counted above.

## Growth

- Cross-day growth, or any comparison with pre-parallelism receipts: UNKNOWN. This window holds one day and no pre-sharding runs; no other day was collected and none is authorized.
- Within this one day (descriptive only): the first 10 complete 4-shard runs by creation time have median 6456 executed tests and median slowest shard 865 s; the last 10 have 7034 tests and 875 s. Pull-request runs test different merged heads, so run-to-run test counts mix branch content with real suite growth; this is not a growth rate.
- Recommendation: no timeout review is supported by measured shard headroom. The quick job's headroom is the one place a future review could start, if its elapsed time recurs.

## Unknown / missing

- UNKNOWN: earlier attempts of re-run runs (API returns the latest attempt only)
- UNKNOWN: test counts of quick-job (affected-tier) runs (logs not parsed)
- UNKNOWN: hass-record-N artifacts (retention-days: 1, expired)
- UNKNOWN: any window before/after the parallelism change (no pre-sharding receipts in this window)
- UNKNOWN: per-PR-head workflow file text (timeouts bound to main revisions only)
- UNKNOWN: growth between days or versus before the parallelism change.

## Summary data (recomputed by `candidate.py --check`)

```json summary
{
 "complete_full_runs": 65,
 "cross_day_or_pre_parallelism_growth": "UNKNOWN",
 "growth_within_window": {
  "basis": "first 10 vs last 10 complete 4-shard runs by creation time, same workflow timeouts; descriptive only, not a trend or cross-day claim",
  "comparable": true,
  "first10_median_max_shard_s": 865.0,
  "first10_median_tests": 6455.5,
  "last10_median_max_shard_s": 875.0,
  "last10_median_tests": 7034.0
 },
 "per_run_critical_path_s": {
  "max": 3670.0,
  "median": 985.0,
  "min": 773.0,
  "n": 65,
  "p90": 1685.0
 },
 "per_run_max_shard_s": {
  "max": 1067.0,
  "median": 818.0,
  "min": 728.0,
  "n": 65,
  "p90": 919.0
 },
 "per_run_sum_shard_s": {
  "max": 3363.0,
  "median": 2760.0,
  "min": 2445.0,
  "n": 65,
  "p90": 3128.0
 },
 "per_run_tests": {
  "max": 7080,
  "median": 6914,
  "min": 6454,
  "n": 65,
  "p90": 7032
 },
 "quick_censored_cancelled": {
  "max_elapsed_s": 635.0,
  "n": 1,
  "reached_timeout": false
 },
 "quick_jobs_by_conclusion": {
  "cancelled": 1,
  "success": 89
 },
 "quick_max_elapsed_over_timeout": 0.7658,
 "quick_min_headroom_s": 281.0,
 "quick_success_elapsed_s": {
  "max": 919.0,
  "median": 16.0,
  "min": 11.0,
  "n": 89,
  "p90": 23.0
 },
 "runs": 100,
 "shard_censored_cancelled": {
  "max_elapsed_s": 850.0,
  "n": 38,
  "reached_timeout": false
 },
 "shard_jobs_by_conclusion": {
  "cancelled": 38,
  "failure": 10,
  "skipped": 6,
  "success": 285
 },
 "shard_max_elapsed_over_timeout": 0.5928,
 "shard_min_headroom_s": 733.0,
 "shard_success_elapsed_s": {
  "max": 1067.0,
  "median": 710.0,
  "min": 452.0,
  "n": 285,
  "p90": 862.0
 },
 "shard_success_without_test_count": 0,
 "shard_tests_ran": {
  "max": 2022,
  "median": 1681,
  "min": 1432,
  "n": 285,
  "p90": 1894
 },
 "superseded_attempt_records_excluded": 0
}
```

## Command receipts (run from the clone root)

```console
$ python3 workspace/candidates/AUDINV-CIW-09/candidate.py --self-test
Ran 6 tests in 0.002s
OK
exit: 0
$ python3 workspace/candidates/AUDINV-CIW-09/candidate.py --check hass-suite-cost-20261114.md --sources SOURCES.json
OK: report matches 100 runs / 429 jobs in SOURCES.json
exit: 0
```
