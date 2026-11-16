# Avocado queue percentiles, UTC day 2026-11-14 (AUDINV-CIW-06)

Status: **HOLD - coverage INCOMPLETE.** Percentiles for the closed day
[2026-11-14T00:00:00Z, 2026-11-15T00:00:00Z) are **UNKNOWN**: no avocado-shack run/job
export for that day exists in the local sanitized sources, and this unit may not query the
network. No queue improvement is claimed.

```json report-data
{"schema_version": 1, "window": ["2026-11-14T00:00:00Z", "2026-11-15T00:00:00Z"], "status": "HOLD", "coverage": "INCOMPLETE", "n_runs_in_window": 0, "n_jobs_in_window": 0, "job_created_available": false, "true_queue_s": "UNKNOWN", "run_to_start_s": "UNKNOWN", "queue_improvement_claim": "NOT_ESTABLISHED", "source_ids": ["ci-audit-raw-avocado-shack", "ci-minutes-1-jobs", "ci-minutes-1-runs", "ci-weight-audit-2026-11-03"]}
```

## What was looked at

| source | covers | usable for the day? |
|---|---|---|
| ci-audit-raw-avocado-shack.json | avocado-shack, 2026-11-03T14:18Z to 2026-11-04T01:16Z, 76 jobs with job created + started | No - different day. Not comparable cohort. |
| ci-minutes-1 runs/jobs.json | **hermes-ops**, to 2026-11-14T15:36Z; 1 run in the day (a schedule run), no job created_at | No - wrong repo, no queue timestamp. |
| CI-WEIGHT-AUDIT-2026-11-03.md:426-440 | n=48 before / n=2 after 01:05Z cutover | Audit itself says n=2 "proves nothing". |

Digests are in `SOURCES.json`; the file `ci-audit-raw` row `queue_s` is job-created-to-start,
whereas `ci-minutes-1` has only run-created/job-started, so the two metrics are kept apart:
run-created-to-job-start (includes `needs:` scheduling) versus true job-created-to-start queue wait.
This report fills neither for 2026-11-14.

## Method fixed for when data arrives (implemented and tested in candidate.py)

- Select runs by `created_at` in the half-open UTC day; unique id = (run_id, attempt, job_id).
- Compute true queue only from real job `created_at`; if absent the metric is UNKNOWN, never 0.
- Partition PR vs main/nightly x conclusion x job name; keep zero waits; exclude and name
  negative/malformed/incomplete/duplicate rows; nearest-rank p50/p90/p95, rank=max(1,ceil(p*n)).
- Any page gap or missing export keeps coverage INCOMPLETE and status HOLD.

## Handoff

Custodian action (not taken here): a read-only `gh` run+job export of avocado-shack for the day,
with page counts and per-job `created_at`. Feed it through `measure()` and re-check. Until then
the two-job post-cutover sample stays unable to establish any queue improvement.

## Receipts

Command outputs are in README.md ("Run receipts").
