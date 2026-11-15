# avocado-shack merges per pass, 2026-11-14 (UTC day) - AUDINV-CIW-08

Status: CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED. Measurement and no-gap report only; no workflow edit, cancellation, new pass or merge was made.

## Result

- Window: `2026-11-14T00:00:00Z` inclusive to `2026-11-15T00:00:00Z` exclusive (= 2026-11-13 16:00 to 2026-11-14 16:00 PST in the ship log). Repo: `Grahammmm/avocado-shack`.
- **Denominator (passes): UNKNOWN.** `modes/ship.log` records no pass ID and no per-pass start/end/zero-merge line, so the pass population cannot be enumerated. Missing pass evidence is unknown, not zero.
- **Numerator (verified unique merges linked to a recorded pass): 0 linked**, because there are no recorded pass IDs to link to. Nothing was joined by timestamp proximity.
- **Merges per pass: UNKNOWN** (no ratio is claimed).
- Verified unique merges in window (PR + full 40-hex head, each bound to its ship.log receipt line): **34**, all reported below as unlinked. No PR has conflicting heads; no duplicate receipts.
- Not a substitute for the ratio (a different quantity, shown only so the data is useful): merge groups (one repo's back-to-back group in one ship-queue run) = 23, so 34 merges / 23 groups = 1.48 merges per merge group. A pass with no merge produces no group, so this cannot be read as merges per pass.
- Group-size distribution in window: 16 group(s) of 1, 3 group(s) of 2, 4 group(s) of 3. Seven of these have an explicit `merge group of N back to back` line (18 merges); the rest are single merges identified only by `group position 1`.
- #332 (cancel-in-progress only for pull_request; main checks finish) is already merged and is excluded: it is neither rebuilt nor used to infer throughput.
- No-gap check: no equivalent `merges-per-pass` report exists under `~/agent-work/reports` (filename search), so this report is not a duplicate.

## Missing coverage

- ship.log records no pass ID; ship-queue run starts/ends are not logged as discrete events, so the pass population cannot be enumerated
- zero-merge passes are not recorded as such (no per-pass summary line), so the denominator is UNKNOWN, not zero
- only multi-merge groups have an explicit group line (7 in window); single-merge groups are identified only by "group position 1" and are not pass-linked
- no per-pass CI/main-verdict export (check runs for main pushes) was available as an existing sanitized receipt; main verdict coverage is UNKNOWN
- merge heads are as logged by ship-queue at merge time; not re-verified against GitHub (no network allowed)
- timezone of ship.log is inferred from the host clock (PST), not recorded in the log
- Informational (all repos / avocado, in window): `SKIPPED run: ship.lock busy` lines = 0; `main red at pass start for Grahammmm/avocado-shack` lines = 11. The latter lines show passes at which avocado main was red, but only red passes log them, so they are not an enumeration.
- Timezone: ship.log timestamps are host-local PST (UTC-8; DST ended 2026-11-01); window is 2026-11-13 16:00:00 to 2026-11-14 16:00:00 local.

## Source binding

- `modes/ship.log` (live ship-queue log, 31614583 bytes / 190520 lines at capture 2026-11-15T23:16:13Z). Cited: 40 avocado MERGED receipt lines (SHA-256 of the lines joined by newline: `d5662076f39cd3da84b3e3b4cd74fc7a812334cfcca1105fc88093aa30d268b0`) in `SOURCES.json` `receipt_lines`; 6 of them lie outside the window (6 h margin kept as boundary evidence: #808, #809, #843, #844, #845, #846) and are excluded.
- Base: avocado-shack main `b83d3615a2ff8802c5b82339b7802e6e62c8d97d`; reused read-only sources and digests are in `BASES.json`.

## Merges in window (unlinked: no recorded pass ID)

| PR | exact merge head | merged UTC | group position |
|---|---|---|---|
| #811 | `d1d8911254bca8e83dab7b006f24fde87c04ac58` | 2026-11-14T02:53:16Z | 1 |
| #816 | `f46233a8c10b5ecb30946b267ad65f8a88ce6d03` | 2026-11-14T02:53:24Z | 2 |
| #818 | `aeea70d3314e3065864863b5985b681d40fdaefb` | 2026-11-14T02:53:38Z | 3 |
| #813 | `a39fe43b890330506c7facbb4a48923e1456eba3` | 2026-11-14T03:03:30Z | 1 |
| #819 | `3ba9874d39d4bbaf1b7e039688745b0066513718` | 2026-11-14T03:03:46Z | 2 |
| #820 | `a591655c881d6cf458d863d01815e48102f1498f` | 2026-11-14T03:04:01Z | 3 |
| #821 | `1d05adabd6fa12a79a49d99c5e38ec24ab1221ae` | 2026-11-14T03:12:50Z | 1 |
| #823 | `7f4eee40a0160212f1d6885ad43dd413696e955d` | 2026-11-14T03:13:04Z | 2 |
| #825 | `c02382d9290e8ce5a1bc9b26fcc8bc60433a9ec2` | 2026-11-14T04:34:52Z | 1 |
| #822 | `c081b823f74804d778728e2b55bc7bde67be10ac` | 2026-11-14T04:42:40Z | 1 |
| #571 | `b82d711fb68919fd47223569bb7a2dee21ed0780` | 2026-11-14T04:52:47Z | 1 |
| #815 | `452f80270d762001c6e2f9b7b8e361fb5924eaaa` | 2026-11-14T05:22:46Z | 1 |
| #559 | `1ff697b32c5a9c223f69c25bf2874323008dd579` | 2026-11-14T05:52:51Z | 1 |
| #817 | `c0d55989dab2706223d9f5249e29b06b8f9c4d63` | 2026-11-14T06:02:51Z | 1 |
| #814 | `2d330107e3d97b1f95a1983fc1d2c2d01763d507` | 2026-11-14T06:52:42Z | 1 |
| #810 | `86b43c1c75fbd870408239e99e51ba4ee2d2071b` | 2026-11-14T08:22:53Z | 1 |
| #812 | `6abd773fb18d574ce9f5912d0c064d90795410f8` | 2026-11-14T09:02:51Z | 1 |
| #827 | `b974638c4de6d40d5c91fda2f36fc412d62363ec` | 2026-11-14T09:12:52Z | 1 |
| #826 | `0c372b53c2405766937bd8387f1ff3fee068a15e` | 2026-11-14T09:22:51Z | 1 |
| #828 | `9f5e1602b92e00f565a41b7c195787052a0fa476` | 2026-11-14T11:34:00Z | 1 |
| #829 | `532972e37b99665912a14e0f98fadf51a86f1bd9` | 2026-11-14T14:25:23Z | 1 |
| #830 | `c44793989fa441bbe7c1ad111ad998048db48dc4` | 2026-11-14T14:55:32Z | 1 |
| #832 | `e6cba5a94cf656471b1a21066e61c3022564ebb4` | 2026-11-14T19:06:54Z | 1 |
| #833 | `cd95f88aab067079a7aafb0f8e132176fc92bfda` | 2026-11-14T19:17:13Z | 1 |
| #831 | `48d0c32307b300ad1fda1fe9ae4698cdbeea6bcd` | 2026-11-14T19:17:28Z | 2 |
| #834 | `08ee44f87bc898addfc5189824b6315bf8360c6f` | 2026-11-14T20:36:28Z | 1 |
| #839 | `7b26ce71d89f4c6ccf2f9619915fcc54c3f74ba4` | 2026-11-14T20:36:42Z | 2 |
| #835 | `d545eeaaac7d1e61bdb576676c761aaf4ecb431d` | 2026-11-14T20:46:50Z | 1 |
| #836 | `cfe6090a4ee8ae72c1bba7bb68367c90e09efa57` | 2026-11-14T20:47:04Z | 2 |
| #838 | `17db1ca0cf67acc8bd699c758b275107dd781fbf` | 2026-11-14T20:47:20Z | 3 |
| #837 | `ff9825ce5c4a7363dc93e929a86bbdacfda48083` | 2026-11-14T20:56:34Z | 1 |
| #840 | `299278c21f4ad9b61e28a1f8e8be78e26bfd7020` | 2026-11-14T20:56:47Z | 2 |
| #841 | `84331abb78045d2a0bf4fd56e90ca7bbcede9a8b` | 2026-11-14T20:57:00Z | 3 |
| #842 | `ad7fbc392722e7644de51976cbdb335c930eeb60` | 2026-11-14T21:45:55Z | 1 |

## Explicit multi-merge group lines (not pass IDs)

- 2026-11-14T02:53:38Z UTC: 3 merges: #811, #816, #818
- 2026-11-14T03:04:02Z UTC: 3 merges: #813, #819, #820
- 2026-11-14T03:13:05Z UTC: 2 merges: #821, #823
- 2026-11-14T19:17:29Z UTC: 2 merges: #833, #831
- 2026-11-14T20:36:43Z UTC: 2 merges: #834, #839
- 2026-11-14T20:47:21Z UTC: 3 merges: #835, #836, #838
- 2026-11-14T20:57:01Z UTC: 3 merges: #837, #840, #841

## Machine summary (recomputed by `candidate.py --check`)

<!-- MACHINE-SUMMARY -->
```json
{
 "schema_version": 1,
 "repo": "Grahammmm/avocado-shack",
 "window": [
  "2026-11-14T00:00:00Z",
  "2026-11-15T00:00:00Z"
 ],
 "passes_recorded": 0,
 "passes_missing_id": 0,
 "pass_enumeration": "none",
 "denominator": null,
 "unique_merges_in_window": 34,
 "numerator": 0,
 "ratio": null,
 "overall_status": "UNKNOWN",
 "unlinked_merges": [
  {
   "pr": 559,
   "head": "1ff697b32c5a9c223f69c25bf2874323008dd579"
  },
  {
   "pr": 571,
   "head": "b82d711fb68919fd47223569bb7a2dee21ed0780"
  },
  {
   "pr": 810,
   "head": "86b43c1c75fbd870408239e99e51ba4ee2d2071b"
  },
  {
   "pr": 811,
   "head": "d1d8911254bca8e83dab7b006f24fde87c04ac58"
  },
  {
   "pr": 812,
   "head": "6abd773fb18d574ce9f5912d0c064d90795410f8"
  },
  {
   "pr": 813,
   "head": "a39fe43b890330506c7facbb4a48923e1456eba3"
  },
  {
   "pr": 814,
   "head": "2d330107e3d97b1f95a1983fc1d2c2d01763d507"
  },
  {
   "pr": 815,
   "head": "452f80270d762001c6e2f9b7b8e361fb5924eaaa"
  },
  {
   "pr": 816,
   "head": "f46233a8c10b5ecb30946b267ad65f8a88ce6d03"
  },
  {
   "pr": 817,
   "head": "c0d55989dab2706223d9f5249e29b06b8f9c4d63"
  },
  {
   "pr": 818,
   "head": "aeea70d3314e3065864863b5985b681d40fdaefb"
  },
  {
   "pr": 819,
   "head": "3ba9874d39d4bbaf1b7e039688745b0066513718"
  },
  {
   "pr": 820,
   "head": "a591655c881d6cf458d863d01815e48102f1498f"
  },
  {
   "pr": 821,
   "head": "1d05adabd6fa12a79a49d99c5e38ec24ab1221ae"
  },
  {
   "pr": 822,
   "head": "c081b823f74804d778728e2b55bc7bde67be10ac"
  },
  {
   "pr": 823,
   "head": "7f4eee40a0160212f1d6885ad43dd413696e955d"
  },
  {
   "pr": 825,
   "head": "c02382d9290e8ce5a1bc9b26fcc8bc60433a9ec2"
  },
  {
   "pr": 826,
   "head": "0c372b53c2405766937bd8387f1ff3fee068a15e"
  },
  {
   "pr": 827,
   "head": "b974638c4de6d40d5c91fda2f36fc412d62363ec"
  },
  {
   "pr": 828,
   "head": "9f5e1602b92e00f565a41b7c195787052a0fa476"
  },
  {
   "pr": 829,
   "head": "532972e37b99665912a14e0f98fadf51a86f1bd9"
  },
  {
   "pr": 830,
   "head": "c44793989fa441bbe7c1ad111ad998048db48dc4"
  },
  {
   "pr": 831,
   "head": "48d0c32307b300ad1fda1fe9ae4698cdbeea6bcd"
  },
  {
   "pr": 832,
   "head": "e6cba5a94cf656471b1a21066e61c3022564ebb4"
  },
  {
   "pr": 833,
   "head": "cd95f88aab067079a7aafb0f8e132176fc92bfda"
  },
  {
   "pr": 834,
   "head": "08ee44f87bc898addfc5189824b6315bf8360c6f"
  },
  {
   "pr": 835,
   "head": "d545eeaaac7d1e61bdb576676c761aaf4ecb431d"
  },
  {
   "pr": 836,
   "head": "cfe6090a4ee8ae72c1bba7bb68367c90e09efa57"
  },
  {
   "pr": 837,
   "head": "ff9825ce5c4a7363dc93e929a86bbdacfda48083"
  },
  {
   "pr": 838,
   "head": "17db1ca0cf67acc8bd699c758b275107dd781fbf"
  },
  {
   "pr": 839,
   "head": "7b26ce71d89f4c6ccf2f9619915fcc54c3f74ba4"
  },
  {
   "pr": 840,
   "head": "299278c21f4ad9b61e28a1f8e8be78e26bfd7020"
  },
  {
   "pr": 841,
   "head": "84331abb78045d2a0bf4fd56e90ca7bbcede9a8b"
  },
  {
   "pr": 842,
   "head": "ad7fbc392722e7644de51976cbdb335c930eeb60"
  }
 ],
 "conflicting_head_prs": [],
 "excluded_other_repo": 0,
 "excluded_outside_window": 6
}
```


## Command receipts (run from the clone root, base b83d3615a2ff8802c5b82339b7802e6e62c8d97d)

```console
$ /home/user/agent-work/bin/memcap -- python3 workspace/candidates/AUDINV-CIW-08/candidate.py --self-test
test_conflicting_head_and_unlinked_merge_not_silently_joined ... ok
test_duplicate_receipt_same_head_counted_once ... ok
test_explicit_two_passes_include_zero_merge_denominator ... ok
test_fixtures_file_expected_outcomes ... ok
test_missing_pass_id_or_capped_export_keeps_overall_ratio_unknown ... ok
test_report_check_rejects_false_ratio_and_tampered_sources ... ok
test_schema_path_escape_symlink_and_side_effect_boundary ... ok
test_window_start_inclusive_end_exclusive_and_other_repo_excluded ... ok
Ran 8 tests in 0.003s
OK
exit: 0

$ python3 workspace/candidates/AUDINV-CIW-08/candidate.py --check avocado-merges-per-pass-20261114.md --sources SOURCES.json
CHECK OK: Grahammmm/avocado-shack merges=34 numerator=0 denominator=UNKNOWN ratio=UNKNOWN status=UNKNOWN
exit: 0
```
