# AUDINV-OLD-69 result

CANDIDATE_ONLY / REVIEW_REQUIRED — NOT_INSTALLED.

## Evidence-bound coverage

```json
{
  "schema_version": 1,
  "status": "CANDIDATE_ONLY / REVIEW_REQUIRED",
  "installed": false,
  "main": "b302d26bee6a4d8993f9da324d743bf206c56aca",
  "sources_sha256": "6cd6cf10999271261d66e8a2835f0e7f95d9c3284967e2e14170b80003345333",
  "bases_sha256": "6aeec46bbcfc49db09b0ed2597e75203ed9fb8448817a86cdeb59794facd368b",
  "test_count": 6,
  "tests": [
    "test_explicit_purpose_optin_allows_only_matching_fake_delivery",
    "test_missing_consent_and_other_purpose_suppress_delivery",
    "test_revocation_after_enqueue_blocks_send_at_boundary",
    "test_unsubscribe_is_idempotent_and_blocks_future_delivery",
    "test_duplicate_send_key_invalid_token_and_no_real_transport",
    "test_schema_path_escape_symlink_and_side_effect_boundary"
  ],
  "fixture_cases": {
    "newsletter_only": 1,
    "hiking_only": 1,
    "missing": 0,
    "other_purpose": 0,
    "revoked_pending": 0,
    "unsubscribed_future": 0,
    "duplicate": 1,
    "cancelled": 0,
    "expired": 0,
    "stale_revision": 0
  },
  "live_delivery": "HOLD",
  "provider_setup": "UNVERIFIED",
  "owner_acceptance": "UNVERIFIED",
  "production_integration": "UNVERIFIED"
}
```

| Acceptance | Deciding coverage (synthetic only) |
| --- | --- |
| Explicit purpose opt-in | Matching fake record; other purpose rejected; duplicate revision rejected |
| Default deny | Missing/other-purpose grants and expiry suppress records |
| Final-boundary consent | Revoke after enqueue; old pending revision after re-opt-in suppressed |
| Unsubscribe | Same safe response; append-only event history; pending/future suppression; other purpose unaffected |
| Retry/token handling | Stable key dedup; forged/malformed/expired/stale references do not revoke; cancelled key suppressed |
| Isolation/report integrity | Traversal/protected path refused before read; symlink guard; malformed schemas/identities/times; altered count/HOLD/hash rejected; audited disallowed I/O count |

## Current-main verification and limits

Inspected base: `b302d26bee6a4d8993f9da324d743bf206c56aca`. Package root was absent on inspected main;
open-PR path query found no owned-path overlap. The current source still records
separate local consent and explicitly disconnected delivery. Source citations,
capture time and full digests are in SOURCES.json; BASES.json repeats the exact
source digest map and pins this candidate, fixtures and README. No production
helper is reused or imported: this is an offline policy proposal, not integration.
Historical audit claims are context only, not fresh acceptance evidence.

Changed files are exactly the six owned paths listed in README.md. No production,
publication, policy, config, registry, sender or account changes. No real addresses,
subscriber data, mail transport, service commands, downloads or live sends.
Fixture-only deterministic token references are NOT production authentication.
Fake-only single-process dedup is not durable or concurrent delivery qualification.

Live delivery: HOLD. Provider setup and owner/semantic acceptance: UNVERIFIED.
Production integration: UNVERIFIED. Separate authorization and attended acceptance
are required for any live send trial. No live subscription promise. CI, merge,
installation and review approval are not builder acceptance and are not claimed.

## Actual local acceptance receipts

cwd: repository root. Commands include the required 8G host cap; output below is actual, not expected text.

```console
$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-69/candidate.py --self-test
test_duplicate_send_key_invalid_token_and_no_real_transport (__main__.Acceptance.test_duplicate_send_key_invalid_token_and_no_real_transport) ... ok
test_explicit_purpose_optin_allows_only_matching_fake_delivery (__main__.Acceptance.test_explicit_purpose_optin_allows_only_matching_fake_delivery) ... ok
test_missing_consent_and_other_purpose_suppress_delivery (__main__.Acceptance.test_missing_consent_and_other_purpose_suppress_delivery) ... ok
test_revocation_after_enqueue_blocks_send_at_boundary (__main__.Acceptance.test_revocation_after_enqueue_blocks_send_at_boundary) ... ok
test_schema_path_escape_symlink_and_side_effect_boundary (__main__.Acceptance.test_schema_path_escape_symlink_and_side_effect_boundary) ... ok
test_unsubscribe_is_idempotent_and_blocks_future_delivery (__main__.Acceptance.test_unsubscribe_is_idempotent_and_blocks_future_delivery) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.005s

OK
OFFLINE: tests=6; disallowed_io_attempts=0; real_delivery=NOT_RUN
exit: 0

$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-69/candidate.py --check RESULT.md --sources SOURCES.json
CHECK PASS: schema=1; source/hash bindings exact; tests=6; live=HOLD; review=REQUIRED
exit: 0
```

The self-test's I/O audit was active around every named acceptance test. No
scratch files, database, sockets or child processes were used by the candidate.
The source inspection was read-only; production isolation is not live delivery
qualification. The report checker also rejects a changed count, false live PASS
and mismatched source hash in deciding negative tests.
