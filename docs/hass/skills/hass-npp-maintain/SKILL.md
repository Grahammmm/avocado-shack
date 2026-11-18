---
name: hass-npp-maintain
description: Use when changing a Hass new-product pipeline asset or pin. Edit, replay, re-record, judge, bump pin, PR.
---

# Maintain the Hass new-product pipeline assets

## When to use
You are changing something under `hass/npp/assets/**`, `hass/npp/pins.json` or an eval case under `hass/tests/npp/cases/**`
(a skill text, template, phrase, rule table, schema, edit grammar, reply line, rubric, model pin). Design:
`reports/hass-npp/PIPELINE-DESIGN.md` (sections 2 and 4). Runtime assets are repo files pinned by sha256; nothing reads a
Hermes profile skill at runtime, so an edit never changes Hass output unseen.

## Procedure
1. Find the owner of the contract: which asset, which stage, which cases name it (each case file lists its `contracts`).
2. Edit the asset in `hass/npp/assets/`. Closed sets stay closed: a new template or phrase is reviewed for assertions, carries
   no digit, number word, currency or superlative, and keeps exactly one default per bank and kind.
3. If the TSV changed, regenerate `limits.json`: `python3 scripts/hass/npp_limits.py` (never edit it by hand).
4. Refresh the pins: `python3 scripts/hass/npp_limits.py pins`, then confirm with `python3 scripts/hass/npp_limits.py pins --check`.
5. Run the asset test: `python3 -B -m unittest hass.tests.test_npp_assets` and the offline replay for the cases the asset
   names (`hass/tests/npp/run_npp.py`, once NPP-H has landed).
6. For an asset or pin change that moves model output: re-record on the private host within the caps, then run the judge
   (`npp_eval.py --judge`, calibration first). Gates: replay passes; strict preview run passes; judge mean at least 4.0,
   no case regressing by more than 0.5, every validator check green.
7. A real failure adds one case (`npp-YYYYMMDD-n`) in the same PR as its fix, shown failing before and passing after.
8. Open one PR from `origin/main`, commits signed off, one card at a time. Review is cross-family.

## Pitfalls
- Tapes are keyed by asset hash: an asset edit invalidates its tapes. Re-record, do not hand-edit a tape.
- Never weaken a check, a threshold or a case expectation to make a change pass. A case id is permanent; a case is never deleted.
- A phrase that "just reads better" can assert something (an ingredient, a method). If it asserts, it is a template slot, not a phrase.
- Research policy (`hass-maker-research/sources.json`) is G-owned: the allowlist and the denylist change only by a reviewed update.
  Official-site discovery, search only to locate, cited facts, no story when unsure (G 2026-11-18 14:00) is not to be loosened.
- Do not edit `hass/conversation.py`: only NPP-B does.
- Private values (cost, quantity, owner chat) never enter an asset, a case or a receipt. Synthetic fixtures only.
