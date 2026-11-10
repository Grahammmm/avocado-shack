# Skills acceptance report template (SKILLS-SPEC 4.3, card 18)

**Synthetic, offline, recorded-reply run. A passing run is not human acceptance:** model-written text and pictures are read by a person,
and the live browser preview is the live runner's. This file records measured counts only; it asserts no live success.

## Groups of the forty non-primary rows (AV1109-18)

Each row has exactly one primary tag and is counted once. `hass/tests/test_skills_acceptance_groups.py` compares these numbers with the executed rows.

| Group | Rows | Failed |
|---|---|---|
| vague | 10 | 0 |
| typo | 8 | 0 |
| multi | 8 | 0 |
| refuse | 8 | 0 |
| turns | 6 | 0 |

Total rows in the corpus = registry-derived Primary rows + the inherited `tag=photo` companions + 40. At this commit: 38 + 5 + 40 = 83.
The historical 32 or 72 totals of SKILLS-SPEC 4.3 are superseded by AV1109-17's registry-derived count.

Command: `python3 -B hass/skills/acceptance_run.py` (all rows, thresholds are constants) and
`python3 -B -m unittest hass.tests.test_skills_acceptance_offline hass.tests.test_skills_acceptance_groups`.
