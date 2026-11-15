# OLD-59 offline candidate

CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED. No live/apply mode.

From the repository root (use the fleet memcap wrapper for each invocation):

```
/home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-59/candidate.py --self-test
/home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-59/candidate.py --check RESULT.md --sources SOURCES.json
```

Default invocation exits nonzero with usage. The check validates structure and exact source bindings, not semantic acceptance or authorization. Tests are the six explicitly named embedded `RecoveryTests` methods, local-only, not a new CI inventory entry. Source drift deliberately fails closed; do not refresh pins without inspecting and retesting the changed closure.

## Manifest

- `candidate.py`: CLI, durable protocol, recording provider and real-forwarder harness with six named tests.
- `fixtures.json`: version-1 synthetic identity, independently stated expected counts, and synthetic-only idempotency contract.
- `BASES.json`: inspected main, complete loaded repository helper closure plus candidate/fixture/workflow digests and no-apply flags.
- `SOURCES.json`: immutable sanitized capture metadata, matching digests and missing coverage.
- `RESULT.md`: primary result, coverage, command receipts and limitations.

No production file or shared registry is edited. No integration patch is needed: the inert integration proposal is the fixture-bound sender/attachment wrappers in `candidate.py`, exercised through the exact unchanged Forwarder. Applying those wrappers to a live consumer is NOT authorized. There is no new reconciliation worker.

## Isolation and protocol

Only synthetic data is used. The harness loads the checked main's real `Forwarder`, `Spool`, relay envelope validators, picture-fetch hash validation, and unchanged import closure. It does not replace production state/identity guards. Only transports are recording-only fixture dependencies. The synthetic key is created mode 0600 under a unique package-local `.fixtures/` directory; no real config/password is read. No ack thread or real transport starts. Cleanup unlinks only this run's owned files. Scratch databases are never committed.

The audit fence blocks network/process execution and opens/writes outside admitted package/source/stdlib paths. Symlinks and traversal are refused before opening the target. Negative cases require zero disallowed I/O attempts. This is a bounded Python test fence, not a general untrusted-code sandbox.

Intent identity includes reply id, text/picture part, chat and payload SHA256. SQLite autocommit with synchronous FULL persists SENDING before recording-provider invocation and a definitive receipt before local sent/ack. A restarted receipt is reused without transport. An interrupted SENDING without a documented provider guarantee becomes UNKNOWN/HOLD; it is not marked sent or automatically retried. Definitive pre-accept failures return to READY. Cancelled/expired/stale candidate dispositions refuse transport. Unknown outcomes stop the current FIFO batch. Parts have independent receipts and completion markers. The fixture protocol is serialized; concurrency, provider reconciliation and a real BlueBubbles stable-key guarantee are unverified.

The idempotency test name refers ONLY to the contract documented in `fixtures.json`. It is not documentation of real provider support. SQLite alone does not establish exactly-once delivery. Suppressing an ambiguous retry may leave an unsent reply held; that is intentional and requires the existing custodian's reconciliation.

## Handoff

`RESULT.md` plus this complete owned package and the builder's signed-off commit SHA, recorded by the PR/task handoff. Recipient: existing avocado-shack audit/integration custodian through the existing pipeline; no duplicate verifier or new job. Reviewer route: existing `opus-coder` (preferred cross-family). No model/provider/tool settings changed. Machine-valid remains REVIEW_REQUIRED. Live install, rollout, real phone/model/provider, owner semantic acceptance and reconciliation remain UNVERIFIED.
