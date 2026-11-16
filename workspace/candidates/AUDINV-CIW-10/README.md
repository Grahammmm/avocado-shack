# AUDINV-CIW-10 — avocado contention retuning evidence (CANDIDATE_ONLY / REVIEW_REQUIRED, NOT_INSTALLED)

Verdict in the report: **HOLD**. Every shard run in the window (21 of 21 with completed shard jobs) ran at observed width 4,
so there is no width contrast; runner identity, host CPU/disk metrics and the repository-variable value are absent from the receipts.
No retuning is recommended. Local-only; no network, no live mode, no apply switch. #335 is excluded; no variable, cap or workflow changed.

Owned files (this directory only): `candidate.py`, `fixtures.json`, `BASES.json`, `SOURCES.json`,
`avocado-contention-retuning-20261114.md`, `README.md`. Base: avocado-shack main `1a8efafbef247783f6a64c0d1f4bf84d96ceaffc`.

Commands (run from the repo root, one at a time; paths resolve under this directory):

    python3 workspace/candidates/AUDINV-CIW-10/candidate.py --self-test
    python3 workspace/candidates/AUDINV-CIW-10/candidate.py --check avocado-contention-retuning-20261114.md --sources SOURCES.json

Recorded output at the builder's run: `--self-test` ran 6 tests, OK (exit 0); `--check` printed `check OK verdict=HOLD` (exit 0);
no arguments prints usage (exit 2); `--check ../x.md` prints `REFUSED: path escapes package root` (exit 2).
`--render` regenerates the report deterministically from SOURCES.json; `--extract` was run once to build SOURCES.json from the
existing `ci-metrics-cache` receipts (read-only; the cache is not part of this package, digests are in BASES.json).

Fixture boundary: `fixtures.json` is synthetic; nothing reads secrets, a database, a runner or the network.
Receipt caveat: `jobs.json` is a sample, so unsampled runs have no elapsed data; the 2026-11-14 PST run list was non-final when captured.
