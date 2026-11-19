---
name: hass-style-judge
description: Use when scoring a new-product card against the gallery (private host, offline). Score 1-5 per dimension.
---

# Style judge (offline, private host)

## When to use
After an asset or pin change and weekly, on the private host: `npp_eval.py --judge` (NPP-H). Also asynchronously after a
live card, never blocking the owner. The judge is not part of a case pass or fail: a model-graded score never decides a CI result.

## Procedure
1. Give the judge the card (its rendered image and its field text), the four gallery screenshots and five golden cards
   as references, and `rubric.json`. Nothing else: no owner words, no price, cost or quantity.
2. Score each of the seven dimensions 1 to 5 with a one-line reason. Pass is a mean of at least 4.0 with no dimension below 3.
3. For a blind pairwise check, show a candidate card beside a live golden and ask which is live. Accuracy of 70% or less
   across the twelve goldens means the new cards are consistent with the gallery.
4. Calibrate before trusting a judge version: `--judge --calibrate` scores `calibration/manifest.json` three times. Every
   run must score every good item at 4.0 or more and every bad item at 2.5 or less, with a spread of 0.5 or less per item.
   Otherwise the judge version is not used and the reason goes to `metrics.tsv`. Commit the recorded scores under
   `hass/tests/npp/tapes/judge/` so a later run can be compared item by item.

## Pitfalls
- Reusing a score from an earlier judge version or model: the pin names the judge model and effort.
- Letting the judge see the owner's chat. Private transcripts stay local; the judge sees the public card only.
- Treating a high mean as permission to weaken a validator check. Gates are not graded.
- Calibrating on goldens only: the bad cards in `calibration/bad/` are there so the judge also fails what it should fail.
