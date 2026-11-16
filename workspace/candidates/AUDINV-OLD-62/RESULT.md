# OLD-62 recovery receipt

CANDIDATE_ONLY / REVIEW_REQUIRED; NOT_INSTALLED.

Inspected main: `b83d3615a2ff8802c5b82339b7802e6e62c8d97d`. No equivalent package existed; open PRs had no owned-path overlap.

## Actual local execution

Working directory: repository root.

```console
$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-62/candidate.py --self-test
test_ambiguous_stub_acceptance_suppresses_duplicate_send (__main__.RecoveryTests.test_ambiguous_stub_acceptance_suppresses_duplicate_send) ... ok
test_cancelled_expired_stale_and_interrupted_assistant_transaction (__main__.RecoveryTests.test_cancelled_expired_stale_and_interrupted_assistant_transaction) ... ok
test_content_media_assistant_and_release_identity_survive_fixture_recreation (__main__.RecoveryTests.test_content_media_assistant_and_release_identity_survive_fixture_recreation) ... ok
test_incomplete_release_is_paused_or_held_not_healthy (__main__.RecoveryTests.test_incomplete_release_is_paused_or_held_not_healthy) ... ok
test_interrupt_before_and_after_durable_commit_never_tears_state (__main__.RecoveryTests.test_interrupt_before_and_after_durable_commit_never_tears_state) ... ok
test_no_existing_process_service_or_real_transport_is_touched (__main__.RecoveryTests.test_no_existing_process_service_or_real_transport_is_touched) ... ok
test_schema_path_escape_symlink_and_side_effect_boundary (__main__.RecoveryTests.test_schema_path_escape_symlink_and_side_effect_boundary) ... ok

----------------------------------------------------------------------
Ran 7 tests in 1.948s

OK
OBSERVED {"after_accept": {"accepted": 1, "attempted": 1, "status": "HOLD"}, "after_commit": "PASS", "assistant_negative_paths": "PASS", "before_accept": {"accepted": 0, "attempted": 1, "status": "HOLD"}, "before_commit": "PASS", "forced_retry": {"accepted": 2, "attempted": 2, "status": "FAIL"}, "identity": "PASS", "incomplete_release": "HOLD", "isolation": "PASS", "schema_paths": "PASS"}
exit: 0
```

```console
$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-62/candidate.py --check RESULT.md --sources SOURCES.json
CHECK PASS: schema=1; 10 boundaries; 7 local tests; known retry FAIL and HOLD retained; 5 UNVERIFIED; NOT_INSTALLED
exit: 0
```

Source-evidence correction: the historical audit file is absent from current main's tracked tree. SOURCES.json preserves the spec's locator with a null digest and UNVERIFIED provenance, rather than inventing a fresh hash. Initial harness setup refused synthetic Git identity until fixture-local user.name/user.email were supplied; production guards were not changed.

## Boundary coverage

| Boundary | Result |
|---|---|
| after_accept | {"accepted": 1, "attempted": 1, "status": "HOLD"} |
| after_commit | "PASS" |
| assistant_negative_paths | "PASS" |
| before_accept | {"accepted": 0, "attempted": 1, "status": "HOLD"} |
| before_commit | "PASS" |
| forced_retry | {"accepted": 2, "attempted": 2, "status": "FAIL"} |
| identity | "PASS" |
| incomplete_release | "HOLD" |
| isolation | "PASS" |
| schema_paths | "PASS" |

Real editor recovery handles handcrafted durable draft/journal fixtures; no prepare/apply or real content validation claim. Content revisions, media bytes/sidecars, pending inbox identity, open request and outbox state survive object recreation. SQLite integrity checks are real. Synthetic release pointer uses only atomic JSON writes: incomplete work is HOLD, never healthy. No runtime_release import.

The recording stub demonstrates **FAIL** for forced retry after ambiguous acceptance (2 attempts, 2 acceptances). The ordinary candidate stops at HOLD without a retry. Production suppression is UNVERIFIED, not repaired or asserted successful.

Support agreement, ownership handover, live reboot/sleep, attended owner usability and production ambiguous-send dedup are **UNVERIFIED**. Historical spec-author baseline receipts are preserved in the admitted spec, not rerun or relabeled as fresh evidence. No install/service/process action or real messages/sends.

Full helper/fixture digest map: BASES.json and SOURCES.json; the latter is bound below. Named tests are local-only; no shared CI registry changed. Exact handoff and qualification limits: README.md.

<!-- OLD62_RECEIPT
{
  "installed": false,
  "observed": {
    "after_accept": {
      "accepted": 1,
      "attempted": 1,
      "status": "HOLD"
    },
    "after_commit": "PASS",
    "assistant_negative_paths": "PASS",
    "before_accept": {
      "accepted": 0,
      "attempted": 1,
      "status": "HOLD"
    },
    "before_commit": "PASS",
    "forced_retry": {
      "accepted": 2,
      "attempted": 2,
      "status": "FAIL"
    },
    "identity": "PASS",
    "incomplete_release": "HOLD",
    "isolation": "PASS",
    "schema_paths": "PASS"
  },
  "schema_version": 1,
  "sources_sha256": "84f1fceb413aa3479c6708536fc2ead24a7ba9cefa4a7fb866a560bd27ae8e3f",
  "status": "CANDIDATE_ONLY / REVIEW_REQUIRED",
  "tests": {
    "errors": 0,
    "failures": 0,
    "run": 7
  },
  "unverified": {
    "attended_owner_usability": "UNVERIFIED",
    "live_reboot_sleep": "UNVERIFIED",
    "ownership_handover": "UNVERIFIED",
    "production_ambiguous_transport_dedup": "UNVERIFIED",
    "support_agreement": "UNVERIFIED"
  }
}
OLD62_RECEIPT -->
