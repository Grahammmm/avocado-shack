# AUDINV-OLD-63 — fixture-only paused restore candidate

CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED. No apply or live mode.

From the clone root (each command separately, under the installed 8G memcap):

```
python3 workspace/candidates/AUDINV-OLD-63/candidate.py --self-test
python3 workspace/candidates/AUDINV-OLD-63/candidate.py --check RESULT.md --sources SOURCES.json
```

The six named embedded unittest cases are local-only and intentionally explicit;
this package does not enroll a new shared CI framework. Default/unsupported CLI
arguments refuse rather than scanning host defaults. Package-path arguments
resolve only beneath this directory; duplicate JSON keys and unsupported schemas
are rejected. Checks are read-only and repeatable. Self-tests use a fresh resolved
task-workspace sibling `old63-fixture-scratch` (required by production isolation
guards), then remove only their own synthetic fixtures. Existing scratch is refused.

Unchanged BackupTestCase supplies throwaway Git writer/drill worktrees, synthetic
conversation operations, an in-memory recording transport and fake previewer.
The real statebackup create/verify/drill, health, history, content rebuild and
sitegen check run unchanged; production identity and path guards are not mocked.
Only the atomic rename is fault-injected to model interrupted/cancelled restores.
Source catalog data is sanitized checked repository fixture input, not live state;
original/web media are synthetic JPEG fixture bytes. A fixture release manifest
binds source backup identity, manifest digest and revision; it is NOT a live server.
The Python audit fence denies host-private reads, out-of-fixture writes, network
and nonfixture subprocesses. The unchanged sitegen child is limited to its fixture
checkout; this is not a security qualification of arbitrary future source code.

Owned-path manifest: candidate.py, fixtures.json, BASES.json, SOURCES.json,
RESULT.md, README.md (all under workspace/candidates/AUDINV-OLD-63/).
BASES pins the reused checked source/helper/data closure and candidate inputs.
RESULT binds SOURCES and BASES; no circular self-hash is claimed. Repository source
pins do not update installed digests or authorize service/queue/registry changes.

Exact handoff: RESULT.md plus the complete owned package and the builder's
signed-off commit SHA, to the existing avocado-shack audit/integration custodian
through the existing pipeline. Routine-backup receipt gaps go to their existing
custodian; live release and live paused restore remain attended-owner verification.
Machine-valid evidence is review-required, not semantic acceptance or permission.
