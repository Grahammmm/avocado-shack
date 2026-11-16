# OLD-56 offline retention candidate

From repository root, individually, under the host memory cap:

```text
/home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-56/candidate.py --self-test
/home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-56/candidate.py --check RESULT.md --sources SOURCES.json
```

Uncapped CLI spelling is `python3 workspace/candidates/AUDINV-OLD-56/candidate.py`
with the same flags. No flags prints usage and exits 2. Unknown/combined flags fail.
Report/source option values must name non-symlink paths below this package. JSON
schema version is 1; duplicate keys and malformed source identities are rejected.
The checker is read-only and deterministic for identical bytes. It validates the
report receipt, source digests, fixture schema, counts and explicit unknowns. It
does not authenticate transcripts, qualify a model, or approve deployment.

## Complete owned-path manifest

- `candidate.py`: stdlib CLI and six embedded, explicitly invoked local-only tests.
- `fixtures.json`: synthetic owner messages and independent expected boundaries.
- `BASES.json`: inspected main, imported helper/input digests, uninstalled/no-apply flags.
- `SOURCES.json`: same digests, prompt digest, synthetic transport identity, capture time and missing evidence.
- `RESULT.md`: primary characterization result, coverage and actual command output.
- `README.md`: invocation and handoff.

No production file, registry, live source pin, policy, queue or service is edited.
There is deliberately no candidate.patch: no gap reproduced in these synthetic
cases, and #878 owns overlapping native non-hike integration. This is not proof
that arbitrary real-model conversations work. No admitted actual transcript was
provided: REAL_MODEL_UNVERIFIED, owner semantic acceptance UNKNOWN.

The tests import the checked main's actual Conversation, LocalInterpreter,
OpenRequests, Editor and existing fixture helper closure. Actual model payloads
are inspected before a recording-only transport returns synthetic JSON. The
existing FixtureAdapter records replies in memory; it never sends a message.
State/linked writer fixtures use an explicit task-local scratch sibling outside
the clone (`old56-fixtures/`), with production state guards unchanged. Scratch
must have no symlink ancestors. Cleanup uses only created fixture entries. This
suite does not use private stores, real databases, provider calls or host config.
Its fixture-local config.json files are synthetic test state, not host settings.
The audit hook allows source/library reads and bounded local Git fixture commands,
refuses network and out-of-scratch writes, and tests deciding refusals. It is not
an OS sandbox for hostile Git binaries. No apply/live option exists. The stale
revision test changes only its throwaway writer fixture, never production.

## Exact handoff

Deliver `workspace/candidates/AUDINV-OLD-56/RESULT.md` plus this complete owned
package and the builder's signed-off commit SHA (recorded in the task/PR, not
self-referentially inside the commit). Base SHA and full source map are in
BASES.json; exact commands, real exits/output and limitations are in RESULT.md.
Recipient: existing avocado-shack audit/integration custodian via the existing
task pipeline. No new verifier or duplicate job is created.

**CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED**. Real-model replay needs
separately admitted sanitized immutable request/response bytes, exact runtime,
model/provider and prompt/source hashes, timezone-aware per-turn timestamps and
independent expectations. This package makes no new transcript acquisition or
backend substitution. Live installation, owner trial, legal/semantic acceptance,
review, CI and merge remain unperformed/downstream-owned. Machine validity is
review-required, not semantic acceptance or execution permission.
