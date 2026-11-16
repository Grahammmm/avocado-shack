# AUDINV-OLD-64 — offline report candidate

CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED. No apply/live mode.
Primary handoff: `workspace/candidates/AUDINV-OLD-64/retention-access-enforcement-gap.md`
plus the complete package and builder signed-off commit SHA (in task/PR handoff).
Recipient: existing avocado-shack audit/integration custodian through existing pipeline.
Actual policy agreement and acceptance remain with the owner. No new verifier or job.

## Complete owned manifest
- `candidate.py`: stdlib CLI/read-only report checker and six embedded named synthetic tests.
- `fixtures.json`: schema 1 synthetic deciding cases, independently specified outcomes.
- `BASES.json`: inspected main, source digests, checker/input digests, no-apply flags.
- `SOURCES.json`: immutable sanitized source excerpts, class matrix and missing coverage.
- `retention-access-enforcement-gap.md`: single primary report and actual local receipt.
- `README.md`: invocation, boundaries and handoff.

From clone root (prefix either command with installed memcap when executing locally):
```text
python3 workspace/candidates/AUDINV-OLD-64/candidate.py --self-test
python3 workspace/candidates/AUDINV-OLD-64/candidate.py --check retention-access-enforcement-gap.md --sources SOURCES.json
```
Default invocation and unsupported flags fail closed. Paths resolve within this package;
absolute/traversal/symlink paths are refused before content opens. No host defaults scanned.
Source hashes bind full repo files or explicitly labeled sanitized decision excerpts;
BASES binds checker and inputs. Report is deterministically compared to those inputs.
Acceptance summaries in report are actual executed summaries; verbose per-test results
remain in the task execution output. Both tests and checker read only package files.

## Named local-only tests
- `test_each_policy_class_has_separate_enforcement_evidence`
- `test_report_counts_do_not_claim_deletion_enforcement`
- `test_dated_approval_not_undated_owner_acceptance`
- `test_missing_transport_receipt_and_conflicting_period_stay_hold`
- `test_no_private_identifiers_or_write_side_effects_in_report`
- `test_schema_path_escape_symlink_and_side_effect_boundary`

All fixture receipts are synthetic, not real transport evidence. Synthetic observed
matching receipt means technical receipt only, never owner acceptance/permission.
Qualification requires the class-specific period identity in `PERIODS` and an
observed, valid, dated receipt with a measured nonnegative integer count. Missing
counts are not zero. Period identities follow the report's recorded proposals;
`relay-pictures` retains the fixture's `clear-at-ack` identity for picture bytes
only, not its separate metadata cleanup period. Equal missing, malformed, unknown
or other-class periods stay HOLD. These synthetic identities do not configure or
approve policy, and a measured count does not by itself prove deletion.
No production modules are imported. No filesystem fixture setup or cleanup is needed.
No network/model/board/transport, credential/config/database read, send, service action,
owner contact, live deletion or access change. Current enforcement remains HOLD.
