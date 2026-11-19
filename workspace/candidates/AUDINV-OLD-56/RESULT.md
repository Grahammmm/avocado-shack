# AUDINV-OLD-56 — retention characterization

**CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED**

**REAL_MODEL_UNVERIFIED**. No separately admitted sanitized actual request/response
transcript was supplied. Actual provider/model/runtime, actual prompt bytes, per-turn
model expectations, timestamps and owner semantic conclusions are UNKNOWN. Synthetic
transport replies below are inputs, not observed model reasoning or semantic acceptance.

## Inspected state and overlap

Inspected main: `b83d3615a2ff8802c5b82339b7802e6e62c8d97d`. It already persists bounded generic-question context via
Conversation and the real OpenRequests store; the historical no-persistence claim is
not current fact. A read-only open-PR query during this run confirmed #878 remains
open at `13040cd999a0bc2ef9be8bf879d56010ea5a0848`, touching conversation.py.
#879, #881, #875, #874 and #870 also overlap production Conversation. No equivalent
OLD-56 package existed in the clone or the open PR path lists. This package neither
modifies nor copies those production changes. No retention patch is warranted by
these synthetic observations; `candidate.patch` is intentionally absent.

## Coverage matrix (six named local-only tests)

| Test suffix | Observed result / deciding negative |
|---|---|
| generic_non_hike_question_and_short_answer_keep_needed_context | Earlier owner request, asked question and current answer are in actual LocalInterpreter request bytes. Correction carries both earlier texts; no apply. |
| recreated_conversation_binds_same_owner_request | New Conversation instance reuses actual SQLite open-request texts for the same owner; a stranger triggers no transport call and another owner cannot read the request. |
| cancel_expiry_other_owner_and_turn_limit_prevent_stale_context | Duplicate provider ID triggers no second request; cancel and +31 minute expiry remove recent context. Long repeated turns stay within production turn/character limits and drop old text. |
| operation_arguments_and_version_guard_not_invented_or_auto_applied | Actual pending payload retains exact hours operation/arguments. No commit before approval. An independent fixture content revision makes approval stale: old draft rejected, new draft proposed, old operations never committed. |
| fixture_pass_cannot_claim_real_model_acceptance | Synthetic PASS cannot be relabelled VERIFIED; fabricated transcript/runtime, naive capture time, unknown field and escaping source identity are rejected. |
| schema_path_escape_symlink_and_side_effect_boundary | Duplicate/malformed/unknown JSON, traversal, absolute protected paths, an actual relative symlink and naive timestamps refused. Explicit negative controls attempt a socket, protected read and out-of-root file/directory write: each intercepted before I/O; no unexpected disallowed attempts. |

## Real executions

cwd: repository root. Commands are run individually under the installed 8G memory cap.
The acceptance commands below are recorded from their own terminal outputs, not
inferred from a model reply. Fixture assertions also ran during manifest capture
with the identical named tests; that capture is not separate model evidence.

`/home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-56/candidate.py --self-test`

```console
test_cancel_expiry_other_owner_and_turn_limit_prevent_stale_context (__main__.ContextTests.test_cancel_expiry_other_owner_and_turn_limit_prevent_stale_context) ... ok
test_fixture_pass_cannot_claim_real_model_acceptance (__main__.ContextTests.test_fixture_pass_cannot_claim_real_model_acceptance) ... ok
test_generic_non_hike_question_and_short_answer_keep_needed_context (__main__.ContextTests.test_generic_non_hike_question_and_short_answer_keep_needed_context) ... ok
test_operation_arguments_and_version_guard_not_invented_or_auto_applied (__main__.ContextTests.test_operation_arguments_and_version_guard_not_invented_or_auto_applied) ... ok
test_recreated_conversation_binds_same_owner_request (__main__.ContextTests.test_recreated_conversation_binds_same_owner_request) ... ok
test_schema_path_escape_symlink_and_side_effect_boundary (__main__.ContextTests.test_schema_path_escape_symlink_and_side_effect_boundary) ... ok

----------------------------------------------------------------------
Ran 6 tests in 8.670s

OK
SELF-TEST PASS: 6 synthetic checks; REAL_MODEL_UNVERIFIED
exit: 0
```

`/home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-56/candidate.py --check RESULT.md --sources SOURCES.json`

```console
CHECK PASS: 6 synthetic checks; REAL_MODEL_UNVERIFIED; CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED
exit: 0
```

## Bindings and limits

BASES.json and SOURCES.json pin the same actual imported repository Python helper
closure, real editor content/template inputs, fixture source inputs and candidate
code. These are source digests, not live install pins. SOURCES capture time is the
metadata capture instant, not an actual model-call timestamp. Synthetic source
fixtures do not contain personal records. Recording FixtureAdapter delivery is
in-memory only. Temporary linked writer repositories, state and local Git commits
stay in the explicit task-workspace sibling `old56-fixtures/`, because production
open_state refuses repository-contained state. Native identity, state permissions,
approval and revision guards remain active. The Python audit fence records and
refuses network, protected reads and writes outside fixture scratch; subprocesses
are restricted to fixture-local Git verbs (no fetch/push/remote/model/service).
Git itself is the existing test helper, not a sandboxed untrusted executable.

This package has no actual transcript ingestion mode: without an admitted receipt,
claims remain unverified; unsupported flags fail closed. A later custodian may
admit sanitized immutable request/response bytes with exact model/provider/runtime,
prompt/source hashes, timezone-aware per-turn timestamps and independent semantic
expectations. Replay/qualification and any native integration remain with the
existing avocado-shack audit/integration custodian through the task pipeline. No
new verifier, job, source acquisition, model route, registry entry, install or live
owner trial is created. Machine-valid output is review-required, never release
or semantic acceptance. No live production files, shared CI inventory or policy
are changed. CI, review and merge are downstream-owned, not claimed here.

<!-- OLD56-RECEIPT
{
  "schema_version": 1,
  "synthetic_tests": 6,
  "failures": 0,
  "real_model_status": "REAL_MODEL_UNVERIFIED",
  "status": "CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED",
  "base": "b83d3615a2ff8802c5b82339b7802e6e62c8d97d",
  "sources_sha256": "fa331801bf9a599f4c86db221c17317ec2f4b6fe430323fb99bb886c045d8538"
}
-->
