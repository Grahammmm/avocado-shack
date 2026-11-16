# AUDINV-OLD-69 — offline consent policy candidate

CANDIDATE_ONLY / REVIEW_REQUIRED — NOT_INSTALLED.

From repository root:

```
python3 workspace/candidates/AUDINV-OLD-69/candidate.py --self-test
python3 workspace/candidates/AUDINV-OLD-69/candidate.py --check RESULT.md --sources SOURCES.json
```

Run both commands through the host's installed memcap wrapper for local builds.
Default invocation exits 2; unknown flags and combined modes are refused. Artifact
paths are single allowlisted package filenames; symlinks/traversal are refused.
The six named embedded unittest methods are local-only and explicitly invoked;
they are not registered as production tests or disguised discovery files.

## Complete owned manifest

- `candidate.py`: stdlib in-memory policy, CLI, checker, named tests and I/O fence.
- `fixtures.json`: version-1 synthetic alias, times and independent expected counts.
- `BASES.json`: inspected main and source/candidate digests; no-apply flags.
- `SOURCES.json`: immutable sanitized read-only source receipt metadata and gaps.
- `RESULT.md`: primary result, coverage, real command output and limitations.
- `README.md`: this boundary and invocation contract.

No existing production source/helper is imported or modified. This is a proposed
policy state machine, NOT an integration claim. It does not open SQLite, actual
subscriber records, host config or credentials. All policy events and delivery
records exist only in memory. No files are written by either CLI mode. The CLI
fence denies network, subprocesses, databases and out-of-package reads/writes.
The recording fake is the only accepted transport type; it has no send method.
Tokens are deterministic registered **fixture-only** references, NOT a proposal
for live authentication. This single-threaded candidate is not concurrency-safe
production delivery infrastructure, durable retry storage or a sender adapter.
Purpose values are `newsletter` and `hiking`; neither implicitly grants the other.
Revisions strictly increase, time cannot go backwards, expiry is exclusive,
revoked/expired/stale/cancelled entries cannot deliver, retries use a stable
(message, purpose, alias) key, and repeated unsubscribe reveals no membership.
A fresh explicit opt-in may restore only its stated purpose with a new revision;
old queued revisions and old unsubscribe references cannot affect that grant.
No event is deleted, including on unsubscribe. All examples are synthetic aliases,
never addresses. Checker validity is structural evidence, not semantic acceptance.

## Exact handoff

`workspace/candidates/AUDINV-OLD-69/RESULT.md` plus this complete owned package
and the builder's signed-off commit SHA (in the task/PR handoff). Record base SHA,
changed files, per-command real exits/output and source digest map in the package.
No force-push. Recipient is the existing avocado-shack audit/integration custodian
through the existing pipeline. CI, review, merge and installation are not claimed.
Any live send trial needs separate authorization and attended acceptance. No real
delivery, provider setup, account/config changes, publication or promise of live
subscriptions is authorized or implemented here.
