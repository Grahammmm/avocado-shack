# AUDINV-FIX-041: Avocado 76-decision reconciliation (CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED)

Report-only. The 76 IDs classed PROPOSED (48) or UNCLEAR (28) in `reports/QUEUE-AUDIT.tsv:59-214`
(sha256 `59c09581...4995`, verified identical to the spec's digest) are joined by EXACT ID to recorded
decisions and unit state. Nothing here approves, denies, revives, edits state/queue/ledger or contacts G.

## Files (all owned; nothing else is changed)
- `candidate.py` - stdlib CLI plus the six embedded tests (local-only; not collected by CI)
- `fixtures.json` - synthetic cases (AV9001-* are invented IDs)
- `BASES.json` - inspected main, source and package digests, no-apply boundary
- `SOURCES.json` - sanitized snapshot of every cited source row, digests, missing coverage
- `avocado-76-decision-reconciliation.tsv` - the report (columns per spec; one row per frozen ID)
- `README.md` - this file

## Invocation (run from the repo root)
```
python3 workspace/candidates/AUDINV-FIX-041/candidate.py --self-test
python3 workspace/candidates/AUDINV-FIX-041/candidate.py --check avocado-76-decision-reconciliation.tsv --sources SOURCES.json
```
`--snapshot` (read explicit files, write only SOURCES.json) and `--emit` regenerate the artifacts; `--check` re-derives every
row from SOURCES.json and fails on any difference, missing/extra/duplicate ID or bad disposition.

## What the report says (counts from the TSV)
- 76 rows: 66 HOLD, 7 CUT-RECORDED, 2 RELEASE-RECORDED, 1 DENIED.
- DENIED: AV1922-08 (log line 1896 names AV1922-08/09/10; 09 and 10 are outside the 76). Stays denied.
- RELEASE-RECORDED: AV1622-08, AV2152-03 (line 1896 tranche 1 released those exact IDs). A hold lift, NOT a feature approval.
- CUT-RECORDED: 7 IDs (line 1930 "CUT all 62 per MILESTONE-MAP-1"; each is a CUT row in `reports/milestone-map-1/MILESTONE-MAP.tsv`
  and state records the cut). Identity comes from the map file, not the log line.
- HOLD: everything else. Reasons are in `scope_match`, `conflicts` and `missing_evidence`: 8 rows carry only an operator state note
  "G APPROVED 2026-11-07" plus the ID-less group line 1635 ("Avocado site 9 APPROVED"); others carry a hold/drop note or only the
  2026-11-05 audit hold (line 1565 / QUEUE-AUDIT-APPLIED.json); several have NO per-ID record.
- Line 1931 (approve ALL 295 NOT-STARTED audit rows) names no ID and does not authorize these feature proposals.
- `merged` rows are historical execution; 'state=merged while recorded hold stands' is flagged as a conflict and stays HOLD.

## Limits
- `units_all.tsv` named by the inventory is not present; current unit state is `modes/unit-state.json` (live file, snapshot hash in
  `state_as_of`, read at snapshot time; it changes as units move).
- QUEUE-AUDIT-APPLIED.json lists 74+27 held IDs vs "hold 108" in line 1565; not reconciled here.
- No per-ID record exists for the 11-07 "Avocado site 9" group; whether each such ID was truly approved is unverified.
- Mechanically valid output is review-required, not semantic acceptance.
