# AUDINV-CIW-06 - avocado queue percentiles (candidate only, not installed)

Status: CANDIDATE_ONLY / REVIEW_REQUIRED, NOT_INSTALLED. Base main `b83d3615a2ff8802c5b82339b7802e6e62c8d97d`.
Local-only; no network, gh, provider call, or live mode. Result of the report: HOLD / UNKNOWN (no day export).

## Owned paths (all under workspace/candidates/AUDINV-CIW-06/)
candidate.py, fixtures.json, BASES.json, SOURCES.json, avocado-queue-percentiles-20261114.md, README.md

## Invocation (from the clone root; local-only, not wired into CI)
    python3 workspace/candidates/AUDINV-CIW-06/candidate.py --self-test
    python3 workspace/candidates/AUDINV-CIW-06/candidate.py --check avocado-queue-percentiles-20261114.md --sources SOURCES.json
No arguments prints usage, exits 2. Paths resolve beneath the package root; traversal, absolute paths and symlinks are refused before open.
The self-test creates and removes one symlink inside this package root. Fixtures are synthetic.

## Run receipts
    $ python3 workspace/candidates/AUDINV-CIW-06/candidate.py --self-test
    Ran 8 tests ... OK            (exit 0)
    $ python3 workspace/candidates/AUDINV-CIW-06/candidate.py --check avocado-queue-percentiles-20261114.md --sources SOURCES.json
    check: PASS (structure only; not an acceptance of the evidence)   (exit 0)

Review-fix regressions were observed failing before each fix and passing afterward:
missing source exports reject COMPLETE even with HOLD, require HOLD rather than OK,
and prohibit improvement claims; report-data rejects unsupported/missing schema versions,
duplicate top-level/nested keys, and malformed JSON. The existing HOLD report is unchanged.

## Handoff
Custodian: avocado-shack audit/integration custodian supplies a read-only run+job export for 2026-11-14 with page counts and per-job created_at. Semantic acceptance of the report is UNVERIFIED.
