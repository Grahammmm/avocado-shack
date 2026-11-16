# OLD-63 — paused restore fixture proof; live recovery remains unverified

CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED. This is not full audit closure.

## Checked source and overlap

Inspected main: `b302d26bee6a4d8993f9da324d743bf206c56aca`. The current-main package path was absent and the
read-only open-PR query showed no overlapping owned paths. Existing production
content-bundle create/verify/restore/drill already implements #283/#300's behavior;
this candidate reuses it rather than rebuilding a lookalike restore engine.
No production, installed digest, CI registry, queue, timer or served site changed.
All six changed paths are within the owned manifest; 419 implementation/test lines
(target at most 450), plus compact synthetic fixtures and evidence. BASES pins the
whole reused hass/test helper tree and sanitized repository site inputs. This
conservative source closure includes some unchanged files copied by WriterRepo
but not executed. No actual backup or private state was read.

## Coverage matrix

| Coverage | Evidence and limit |
|---|---|
| Content | Fixture backup contentCommit equals rebuilt detached HEAD; generated and source content digests match. |
| Original media | Synthetic JPEG original and sidecar restore byte-for-byte; source media unchanged. |
| Web media | Committed synthetic JPEG is recovered from the bundle with matching digest. |
| Assistant state | Real conversation produces 3 history changes; all non-control DB table rows survive; integrity check passes. The added paused control is checked before publication and after recovery. |
| Fixture served release | Explicit fixture release pointer binds backup identity, manifest digest and revision; every wrong identity field is refused. No real server was involved. |
| Routine live backups | ROUTINE_BACKUPS_UNVERIFIED. No sanitized dated successful-backup receipts were supplied. Timer source says daily 03:30 America/Los_Angeles, not that it ran. Three expected dates, zero supplied covered dates; missing is not zero backups. |
| Actual served release | UNVERIFIED; live revision/content/media correspondence needs attended-owner evidence. |
| Actual live paused restore | HOLD_ATTENDED_OWNER; no service action, live pause, scheduling change or restoration is authorized. |

## Deciding negatives

Missing/corrupt bundle makes nothing; a rehashed wrong contentCommit is corrupt.
Wrong backup/release/manifest identity prevents a success claim. Existing state,
media and content destinations (directories and dangling symlinks) remain untouched.
Injected cancellation at each atomic publish step rolls back all newly made
state/media/content directories, preserves the source backup, and retry remains
paused. Routine metadata covers cancelled, expired, failed, stale, duplicate,
future and malformed receipts; enabled timer alone stays unverified. Schema,
path escape, symlink, unsupported flags, wrong report counts and falsely elevated
live coverage are deciding refusals. The passing run attempted zero forbidden I/O.

## Actual builder acceptance

Cwd: isolated builder clone root of avocado-shack. Commands shown exactly as run;
the installed memcap provides the required 8G bound. All six named tests are local-only.

```console
$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-63/candidate.py --self-test
test_corrupt_missing_bundle_or_wrong_release_identity_fails (__main__.self_test.<locals>.RestoreTests.test_corrupt_missing_bundle_or_wrong_release_identity_fails) ... ok
test_existing_destination_and_symlink_are_untouched (__main__.self_test.<locals>.RestoreTests.test_existing_destination_and_symlink_are_untouched) ... ok
test_paused_restore_matches_content_media_state_and_fixture_served_release (__main__.self_test.<locals>.RestoreTests.test_paused_restore_matches_content_media_state_and_fixture_served_release) ... ok
test_restore_interruption_retains_atomicity_and_pause (__main__.self_test.<locals>.RestoreTests.test_restore_interruption_retains_atomicity_and_pause) ... ok
test_schema_path_escape_symlink_and_side_effect_boundary (__main__.self_test.<locals>.RestoreTests.test_schema_path_escape_symlink_and_side_effect_boundary) ... ok
test_timer_enabled_without_dated_backup_receipt_stays_unverified (__main__.self_test.<locals>.RestoreTests.test_timer_enabled_without_dated_backup_receipt_stays_unverified) ... ok

----------------------------------------------------------------------
Ran 6 tests in 13.104s

OK
fixture-boundary: 0 disallowed I/O attempts; no live actions
exit: 0
```

## Bound report schema

```json
{
  "bases_sha256": "28b4209877e3f7515ae476128349b97b93df0a0164eabe6cda539e3e6968c8d9",
  "coverage": {
    "assistant_state": "FIXTURE_PROVEN",
    "content": "FIXTURE_PROVEN",
    "fixture_served_release": "FIXTURE_PROVEN",
    "live_paused_restore": "HOLD_ATTENDED_OWNER",
    "live_served_release": "UNVERIFIED",
    "original_media": "FIXTURE_PROVEN",
    "routine_live_backups": "ROUTINE_BACKUPS_UNVERIFIED",
    "web_media": "FIXTURE_PROVEN"
  },
  "inspected_main": "b302d26bee6a4d8993f9da324d743bf206c56aca",
  "routine": {
    "covered": 0,
    "expected": 3,
    "status": "ROUTINE_BACKUPS_UNVERIFIED"
  },
  "schema_version": 1,
  "sources_sha256": "e21e796c72e1753625080bb8f941b98c12b031098c254569c7a45376fcbfb154",
  "status": [
    "CANDIDATE_ONLY",
    "REVIEW_REQUIRED",
    "NOT_INSTALLED"
  ],
  "tests": {
    "errors": 0,
    "failures": 0,
    "run": 6
  }
}
```

## Artifact-check execution

```console
$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-63/candidate.py --check RESULT.md --sources SOURCES.json
artifact-check: PASS (6 local tests; 8 coverage rows; routine/live remain UNVERIFIED/HOLD)
exit: 0
```

## Main-merge revalidation

The builder receipts above remain historical. The PR repair merged main
`18eafb31833211e6ad324d647656648df750ff53`, including #898's correction of the
stale `ROUTER-15` assertion in `hass/tests/test_demo_rehearsal.py`. The original
PR head reproduced CI's `KeyError: 'known_gap'`; the merged demo module passed
all 21 tests. Comparing all 1,332 BASES source digests found only that test file
changed. Its pin and this report's BASES digest were refreshed; the original
inspection revision, candidate code, fixtures, source citations and live holds
remain unchanged. Current restore acceptance is recorded in the PR repair
handoff, separately from the builder receipts above.

A subsequent CI repair merged main
`6fc75b5b` and reproduced run 43806918209's acceptance `undo-not-identical`
failure. Restored fixture bytes were correct, but the freshness check used the
host day instead of the session clock. The narrow fix from PR #891
(`0a1ef76ac5ab9a9ad41be9c4da653688c8b19257`) scopes that check to the same fixture
clock, preserving stale-byte rejection and all exact undo/residue assertions.
All 1,332 existing source pins were compared: 14 changed files were verified
byte-identical to that main revision, and `hass/skills/acceptance_run.py` was
verified byte-identical to #891's fix before refreshing those 15 pins and the
bound BASES digest. The original inspection revision, source citations, candidate
code, fixtures, package inventory and live UNVERIFIED/HOLD gates are unchanged.
New proof is reported in the repair handoff, not substituted for historical
builder output above.

## Handoff and limits

RESULT.md plus the complete owned package and signed-off builder commit go to the
existing avocado-shack audit/integration custodian through the existing pipeline.
The commit SHA is supplied in the task/PR handoff (not embedded in its own tree).
Mechanical validity is not owner acceptance, successful live backup evidence,
review approval, installed recovery or authority to restart/pause/restore services.
Historical raw/resolved-TMPDIR receipts in the approved spec remain historical;
this run independently uses a resolved task-local scratch sibling before imports.
The unchanged real helper closure, fake previewer and recording transport are
explicitly distinguished. No real browser, message, model, phone or owner trial
was performed. Source receipt acquisition stays with existing custodians.
