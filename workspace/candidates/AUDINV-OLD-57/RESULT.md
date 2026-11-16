# AUDINV-OLD-57 — Offline ingress candidate

```json
{
  "base": "b83d3615a2ff8802c5b82339b7802e6e62c8d97d",
  "coverage": {
    "heic": "NOT SUPPORTED",
    "live-fetch": "UNKNOWN/HOLD",
    "needed-owner-format": "UNKNOWN/HOLD",
    "owner-acceptance": "UNKNOWN/HOLD",
    "real-phone": "UNKNOWN/HOLD",
    "replacement-trial": "UNKNOWN/HOLD",
    "synthetic-jpeg-2-8": "PASS_LOCAL",
    "synthetic-png": "PASS_LOCAL"
  },
  "schema_version": 1,
  "source_count": 53,
  "sources_sha256": "e4296c90a57e274c2f4071a02db44fab53d93ee27ee3fd2a8207fad28d3db404",
  "status": "CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED",
  "tests": 6
}
```

## Findings and boundaries

Current main already contains BlueBubblesPhotos, JPEG orientation retention and product-photo install. This package composes those exact helpers; it changes no production source or approval gate. Synthetic owner/chat/message/attachment identity and one-item count are bound before transport. Redirect, metadata/count, declared/actual byte-cap, truncation, cancelled, expired and stale paths fail closed. Originals and provenance stay private in task-local fixtures; only sanitized bytes reach the production install consumer’s queued assets. No site file is written.

JPEG orientations 2–8 are checked after real newitem_render._upright consumption against an independent asymmetric six-color matrix, with GPS/device/time removed. PNG is accepted without rotation; rotated PNG remains unsupported by the existing consumer. HEIC is NOT SUPPORTED and receives the existing Most Compatible/screenshot guidance with no partial original/publication saved. This is not conversion or a selection of the owner’s actual phone format.

The needed owner format, actual phone, live fetching, replacement trial and owner semantic acceptance remain UNKNOWN/HOLD. The format/source custodian must supply an approved compatibility requirement if HEIC is actually needed. No credentials, private records, native board bridge, socket, subprocess, send, model call, live install, publication, decoder install or service action occurs in the harness. The synthetic-token file is explicitly fake fixture data, not a password from the host.

Source digests cover every loaded Hass source/helper and synthetic fixture; SOURCES.json is immutable cited metadata. BASES.json refers to inspected source main, not the later candidate commit. Candidate commit identity is in the signed-off Git handoff. Existing spec-author baseline receipts, including the lexical TMPDIR failure and resolved-workspace pass, remain in the source spec; they are not presented as new runs.

## Execution receipts

Cwd: builder clone root `avocado-shack`. Commands run separately under the existing memory cap. These are local synthetic results, not CI/owner/live acceptance.

```console
$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-57/candidate.py --self-test
test_existing_supported_path_is_not_replaced_or_live_fetched (__main__.CandidateTests.test_existing_supported_path_is_not_replaced_or_live_fetched) ... ok
test_injected_approved_attachment_reaches_real_media_consumer (__main__.CandidateTests.test_injected_approved_attachment_reaches_real_media_consumer) ... ok
test_schema_path_escape_symlink_and_side_effect_boundary (__main__.CandidateTests.test_schema_path_escape_symlink_and_side_effect_boundary) ... ok
test_synthetic_jpeg_orientation_2_to_8_has_no_private_metadata (__main__.CandidateTests.test_synthetic_jpeg_orientation_2_to_8_has_no_private_metadata) ... ok
test_unsupported_heic_keeps_original_untouched_and_requests_retake (__main__.CandidateTests.test_unsupported_heic_keeps_original_untouched_and_requests_retake) ... ok
test_wrong_owner_redirect_bad_count_oversize_and_truncation_fail_closed (__main__.CandidateTests.test_wrong_owner_redirect_bad_count_oversize_and_truncation_fail_closed) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.540s

OK
CHECK PASS: exact source bindings; 6 local tests; UNKNOWN/HOLD retained; no apply authority
SELF-TEST PASS: 6 named local-only synthetic tests; disallowed I/O: 0
exit: 0

$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-OLD-57/candidate.py --check RESULT.md --sources SOURCES.json
CHECK PASS: exact source bindings; 6 local tests; UNKNOWN/HOLD retained; no apply authority
exit: 0
```

Development diagnostics retained here: the initial synthetic chart had a blue-channel wrap discontinuity, so mirrored sample centers were not equivalent; a six-solid-color chart with independent orientation matrices replaced that flawed test input. The audit fence initially misattributed `shutil.rmtree` relative dir-fd opens to clone-relative paths; cleanup now uses absolute task-owned entries. An artifact-negative test initially rebound its read fence along with the temporary package; the fence now retains its original immutable read root. These were harness issues, not fixes to production behavior; no production source guard or assertion was weakened.

## Changed files and review boundary

Exactly the six owned paths listed in README.md, with 429 authored implementation/test lines (target at most 450). No outside files or shared CI inventory changes. The signed-off candidate commit SHA and installed prepush result are carried in the PR/task handoff; subsequent CI/review/merge are owned by the existing ship queue. The source digest map is in both BASES.json and SOURCES.json, with exact SOURCES.json binding above. The candidate remains uninstalled and review-required.
