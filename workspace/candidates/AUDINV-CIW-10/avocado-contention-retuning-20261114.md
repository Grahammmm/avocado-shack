# Avocado shard contention retuning evidence, 2026-11-14 (UTC) — CIW-10

## Verdict

**HOLD** — no retuning is recommended.

- only one observed width (4); no comparable contrast
- missing metrics (not zero): host_cpu_disk_metrics,repository_variable_value,runner_identity

## Window and sources

Window [2026-11-14T00:00:00Z, 2026-11-15T00:00:00Z). #335 (width-two variable/cap) is merged and excluded; this report changes no variable, cap or workflow.

- `runs-avocado-shack-2026-11-13.json` sha256 `215d68b6d1b757f41c34151490158fc92c8e61f5235a084bbf1c4eabcc6647e4` (30555 bytes), captured 2026-11-15T06:10:00Z
- `runs-avocado-shack-2026-11-14.json` sha256 `7df05f1e04f09beb191ec87edf0a0812b7e035f471ceece34c80fa876f968837` (24717 bytes), captured 2026-11-15T06:10:00Z
- `jobs.json` sha256 `e106324b6ffa091f7211c2b7c15c4382e77a76e8f300cf209006db0dc2069c41` (1500714 bytes), captured UNKNOWN (cache file mtime only)

- runs created in window: 100; of those, runs whose jobs were sampled: 24; runs with completed `hass shard N` jobs: 21

## Observed widths and heads

| observed width | runs | p50 slowest-shard s | p90 s |
|---|---|---|---|
| 4 | 21 | 818.0 | 921.0 |

Distinct heads among those runs: 21. Per-run rows (head, attempt, own-peak concurrency, other sampled avocado jobs running at shard start, which includes the run's own sibling shards) are in the JSON block below; the 'others' count is a LOWER BOUND, counting only sampled jobs. Slowest-shard elapsed here is descriptive: the workflow comment expects ~290 s per shard at width 4, the observed p50 is higher, but without runner or host data that gap cannot be attributed to shard width.

## Current workflow

Observed `.github/workflows/check.yml` at main `1a8efafbef247783f6a64c0d1f4bf84d96ceaffc` (sha256 `cc91cfaaaf826c693ab0f1d06ae1af18129bc917f44fb6d05df5fd74273471dd`):

    # free. Retune with the repo variable HASS_SHARD_JOBS (1-8) without a code change.
    HASS_SHARD_JOBS: ${{ vars.HASS_SHARD_JOBS || 4 }}

Current fallback width is 4. The repository variable's value was not read (config read forbidden); configured width is therefore UNKNOWN and is not equated with measured concurrency.

## Missing coverage and confounders

- **host_cpu_disk_metrics**: UNKNOWN: no per-interval CPU/iowait/disk series in the receipts
- **repository_variable_value**: UNKNOWN: HASS_SHARD_JOBS value not read (config read out of scope)
- **runner_identity**: UNKNOWN: receipts carry no runner name/alias per job
- **unsampled_runs**: jobs.json is a sample; runs without sampled jobs have no elapsed data

Confounders: PR vs push events and different heads change shard weight; other avocado workflows share the 8 runners; no width contrast exists in the window, so no causal claim about width is made.

## Derived data

```json derived
{
 "distinct_heads": 21,
 "full_tier_runs_with_shard_jobs": 21,
 "missing_metrics": [
  "host_cpu_disk_metrics",
  "repository_variable_value",
  "runner_identity"
 ],
 "per_observed_width": {
  "4": {
   "n": 21,
   "p50_s": 818.0,
   "p90_s": 921.0
  }
 },
 "run_rows": [
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "a39fe43b8903",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 3,
   "run": 43536379911,
   "shard_elapsed_max_s": 921.0,
   "shard_elapsed_sum_s": 3136.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "cb43edfe3381",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 3,
   "run": 43537972553,
   "shard_elapsed_max_s": 740.0,
   "shard_elapsed_sum_s": 2491.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "3ba9874d39d4",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 3,
   "run": 43540587682,
   "shard_elapsed_max_s": 877.0,
   "shard_elapsed_sum_s": 2743.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "1d05adabd6fa",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 3,
   "run": 43541129095,
   "shard_elapsed_max_s": 899.0,
   "shard_elapsed_sum_s": 2933.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "c081b823f748",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43547142606,
   "shard_elapsed_max_s": 752.0,
   "shard_elapsed_sum_s": 2445.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "b82d711fb689",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43548441786,
   "shard_elapsed_max_s": 742.0,
   "shard_elapsed_sum_s": 2517.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "2dd855512c21",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43552723684,
   "shard_elapsed_max_s": 804.0,
   "shard_elapsed_sum_s": 2777.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "04dec5463fa5",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 4,
   "run": 43555213691,
   "shard_elapsed_max_s": 733.0,
   "shard_elapsed_sum_s": 2578.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "8336af99d441",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 3,
   "run": 43558398906,
   "shard_elapsed_max_s": 733.0,
   "shard_elapsed_sum_s": 2558.0
  },
  {
   "attempt": 1,
   "event": "push",
   "head": "8d22d9b33b3f",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 4,
   "run": 43561247442,
   "shard_elapsed_max_s": 790.0,
   "shard_elapsed_sum_s": 2632.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "1ff697b32c5a",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 7,
   "run": 43561454856,
   "shard_elapsed_max_s": 787.0,
   "shard_elapsed_sum_s": 2661.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "f8fc5168899a",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43566013954,
   "shard_elapsed_max_s": 800.0,
   "shard_elapsed_sum_s": 2662.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "86b43c1c75fb",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43573890602,
   "shard_elapsed_max_s": 798.0,
   "shard_elapsed_sum_s": 2645.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "b974638c4de6",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 4,
   "run": 43577516399,
   "shard_elapsed_max_s": 818.0,
   "shard_elapsed_sum_s": 2743.0
  },
  {
   "attempt": 1,
   "event": "push",
   "head": "f398337e7ed9",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43580280902,
   "shard_elapsed_max_s": 823.0,
   "shard_elapsed_sum_s": 2735.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "532972e37b99",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43602252624,
   "shard_elapsed_max_s": 842.0,
   "shard_elapsed_sum_s": 2877.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "e6cba5a94cf6",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 3,
   "run": 43627910752,
   "shard_elapsed_max_s": 824.0,
   "shard_elapsed_sum_s": 2922.0
  },
  {
   "attempt": 1,
   "event": "push",
   "head": "cfc29b9960ec",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 3,
   "run": 43631279410,
   "shard_elapsed_max_s": 971.0,
   "shard_elapsed_sum_s": 3224.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "7b26ce71d89f",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 3,
   "run": 43633924243,
   "shard_elapsed_max_s": 901.0,
   "shard_elapsed_sum_s": 2929.0
  },
  {
   "attempt": 1,
   "event": "push",
   "head": "acd7076176a9",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43639340719,
   "shard_elapsed_max_s": 870.0,
   "shard_elapsed_sum_s": 2918.0
  },
  {
   "attempt": 1,
   "event": "pull_request",
   "head": "705bc17cb8ea",
   "measured_own_peak": 4,
   "observed_width": 4,
   "others_at_start_max": 5,
   "run": 43655881666,
   "shard_elapsed_max_s": 925.0,
   "shard_elapsed_sum_s": 3187.0
  }
 ],
 "runs_in_window": 100,
 "runs_with_sampled_jobs": 24,
 "verdict": {
  "reasons": [
   "only one observed width (4); no comparable contrast",
   "missing metrics (not zero): host_cpu_disk_metrics,repository_variable_value,runner_identity"
  ],
  "recommendation": null,
  "verdict": "HOLD"
 },
 "window": [
  "2026-11-14T00:00:00Z",
  "2026-11-15T00:00:00Z"
 ]
}
```
