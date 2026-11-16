# OLD-62 isolated recovery candidate

CANDIDATE_ONLY / REVIEW_REQUIRED; NOT_INSTALLED; no apply authority.

From the repository root, use the local memory cap:

```
/home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-62/candidate.py --self-test
/home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-62/candidate.py --check RESULT.md --sources SOURCES.json
```

These are explicitly embedded local-only unittest checks, not a registered CI suite.
The default CLI refuses missing actions; there is no live/apply mode. Check inputs
must be nonsymlink package-relative files. Formats are version 1, duplicate keys
and stale source digests are refused. Checks never rewrite the immutable receipts.

## Owned manifest

- candidate.py: bounded harness, CLI, named tests and report validation.
- fixtures.json: entirely synthetic input and independent expected results.
- BASES.json: inspected main and actual imported Python helper closure digests.
- SOURCES.json: capture metadata, immutable source/fixture bindings and missing coverage.
- RESULT.md: actual execution receipt, coverage and limits.
- README.md: invocation and isolation/handoff contract.

Each run creates and cleans only its unique `old62-*` scratch sibling in this
task workspace, outside the clone because the unchanged production guards refuse
repository-contained state. The package path and workspace are resolved and
symlinks refused before setup. Editor writer identity/private-directory checks
remain enabled. Synthetic Git objects use synthetic identity and empty HOME,
without global/system configuration; no live worktree or database is opened.
All subprocesses are fixture-scoped Git only, with no network URL, hooks or shell.
Network sockets, existing-process signals and service commands are refused.
The photograph is a deliberately tiny synthetic JPEG-shaped byte fixture; no
claim of image decode/vision or realistic media fidelity is made.

The real editor recovery path consumes synthetic on-disk drafts and journals on
a linked fixture worktree. This tests recovery, not prepare/apply, rendering or
publication correctness. Production `Inbox`, `OpenRequests`, `Outbox`, media
store and atomic-file helpers are reused unchanged. Database connections and
writer calls are closed/re-created; no OS/service restart or power-loss durability
is claimed. The served-release pointer is ONLY a fixture JSON file; HOLD is a
candidate disposition, not proof of runtime_release recovery. No runtime_release
module is imported.

Transport is recording-only. Before/after ambiguous acceptance, the candidate
stops with HOLD (no automatic retry). A separate deliberate fake-only retry is
a negative control: the real outbox accepts twice after losing the first response.
This is a known FAIL, not a passing production dedup claim. The test passes only
when it detects that limitation and the receipt preserves FAIL/HOLD/UNVERIFIED.
No production controller or approval chain is changed.

## Exact handoff

`workspace/candidates/AUDINV-OLD-62/RESULT.md` plus this complete owned package and
the builder's signed-off commit SHA, through the existing avocado-shack audit /
integration pipeline. Base SHA and source digests are in BASES.json; command
exits/output are in RESULT.md. The task/PR supplies the signed-off head SHA (it
cannot be embedded in its own commit). No force-push. Existing `opus-coder` is the
preferred reviewer; ship-queue owns CI and subsequent release routing.

Support agreement, ownership handover, live reboot/sleep, attended owner usability
and production ambiguous transport dedup remain UNVERIFIED. A machine-valid report
is not semantic acceptance, an install, a release, a send authorization or an owner
trial. These missing conclusions remain with their existing human/custodian gates.
