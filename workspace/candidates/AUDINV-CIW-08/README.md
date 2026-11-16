# AUDINV-CIW-08 - avocado merges per pass, 2026-11-14 UTC day

Status: CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED. Offline, stdlib only, read-only; no network, no live mode, no apply switch. Local-only checks (not wired into CI).

## Owned paths (the whole change)

- `candidate.py` - analysis, report checker, CLI and the embedded named unittest cases
- `fixtures.json` - synthetic v1 cases with independently stated expected outcomes
- `BASES.json` - inspected main, reused-source digests, candidate digests, no-apply boundary
- `SOURCES.json` - sanitized ship.log receipt lines (avocado MERGED lines and group lines), digests, explicit missing coverage
- `avocado-merges-per-pass-20261114.md` - the single evidence report
- `README.md` - this file

## Run (from the clone root; `--check` paths resolve beneath this directory)

```text
python3 workspace/candidates/AUDINV-CIW-08/candidate.py --self-test
python3 workspace/candidates/AUDINV-CIW-08/candidate.py --check avocado-merges-per-pass-20261114.md --sources SOURCES.json
```

No arguments prints usage and exits 2. `--check` exits 1 on a malformed report/sources, a digest or receipt mismatch, or a presented ratio, numerator, denominator or unique-merge count that differs from the source-bound summary (including Markdown bullets, bold and code spans). Receipt binding includes row ID and group position. Unlinked merges or conflicting heads leave the numerator and ratio UNKNOWN even with complete pass enumeration; a supported zero-merge population still yields a known zero.

## Boundaries

SOURCES.json was extracted once from the live `modes/ship.log` by a throwaway script (not part of this package) that kept avocado-shack `MERGED` lines within 6 h of the window plus the `merge group of N` lines in the window. The report's machine summary block is recomputed by `candidate.py`, never typed by hand. Tests write nothing except a short-lived task-local symlink that is removed in the same test.
