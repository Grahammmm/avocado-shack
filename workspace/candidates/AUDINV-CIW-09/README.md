# AUDINV-CIW-09: hass suite cost report, 2026-11-14

CANDIDATE_ONLY / REVIEW_REQUIRED, NOT_INSTALLED. Local-only; not registered in CI.

Owned files (all under `workspace/candidates/AUDINV-CIW-09/`): `candidate.py`, `fixtures.json`, `BASES.json`, `SOURCES.json`, `hass-suite-cost-20261114.md`, `README.md`.

Run from the clone root:

```
python3 workspace/candidates/AUDINV-CIW-09/candidate.py --self-test
python3 workspace/candidates/AUDINV-CIW-09/candidate.py --check hass-suite-cost-20261114.md --sources SOURCES.json
```

`--check` recomputes every number in the report's `json summary` block from `SOURCES.json` and fails on any difference, missing section or missing UNKNOWN. Paths resolve beneath the package root; no network, no writes.
`SOURCES.json` holds sanitized run/job metadata read from the GitHub Actions API (read-only). It was collected once; nothing re-fetches it. `fixtures.json` is synthetic and holds no real data.

Handoff: the report plus this package, to the existing avocado-shack audit custodian through the normal pipeline. It authorizes no timeout change, monitoring or CI run.
