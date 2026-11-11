# Stock restock: note when more of a product is coming

Code: `hass/skills/restock.py` (AV1109-04, SKILLS-STOCK-2 part 2). Cases: `hass/tests/fixtures/skills/restock/stock.restock.jsonl`.
Tests: `hass/tests/test_skills_restock.py`, `hass/tests/test_morning_report_restock.py`. Design: `reports/hass/SKILLS-SPEC.md`
section 3.8. Authoring guide: `docs/hass/SKILLS.md`. Wording: `docs/hass/VOICE.md`. The operation is AV1109-03's
`product.set_restock` (`hass/ops/restock.py`).

Mike says which product and what day more is coming. Hass drafts **one** `product.set_restock` per product. He says
`yes <code>`; nothing is written before his yes, and undo (`undo`, then its own yes) restores the old day, or no day, exactly.

The day is kept in the product's private `restock_on` field. It is **never published**: the public site is unchanged, so the
skill has no site preview. It only shows in the owner's morning shelf report.

## Phrases it handles

| He says | What happens |
|---|---|
| "more honey coming Thursday" | Records Thursday for the honey. |
| "egs back on firday", "restock the lemons on the 14th" | Same; the interpreter corrects the spelling, "the 14th" is a date. |
| "eggs back in 2 weeks" | The day is computed from today (Pacific) and **said before his yes**: "Cal Poly eggs: more expected Sun Nov 22". |
| "honey and eggs both back Thursday" | Two products, one draft, one yes, one undo. |
| "never mind about the honey restock" | `clear`: takes the day off. No day is asked for. |
| "more soon", "the bread truck comes Monday" | Asks "Which product?" (then "What day is more coming?"). Nothing is written. |
| "more honey last Tuesday" | Refused: "Tue Nov 3 has already passed. Tell me a day from today on." |
| "restock 40 jars of honey" | "I don't keep counts yet." (below) |

## Rules

* **The window**: today up to 60 days ahead, both days included, in Pacific days. A past day, or a day more than 60 days
  ahead, is refused in plain words and nothing is written. A day Hass cannot read, or no today to judge it by, is asked for
  ("What day is more coming?"), never guessed.
* **Active products only**: a product on hold is named and refused ("I can't change ... right now. It is on hold until someone
  has looked at it."); a hidden one is named and refused ("... is hidden. Do you want me to bring it back first?"). Neither is
  brought back or released by this skill. An unknown product asks "Which product?".
* **Nothing to do**: setting a day the product already has, or clearing a product that has none, changes nothing and says so.
* **No counts, ever**: a number with a unit of goods ("40 jars", "2 dozen", "12 lbs") is never stored. When a day is still
  missing the one question starts "I don't keep counts yet."; when the request is otherwise complete it is refused with "I
  don't keep counts yet. Tell me the product and day without a count." and not even the date is written. A date ("the 14th",
  "Nov 12") or a wait ("in 2 weeks") is not a count.
* **A restock day never sets the shelf word.** It does not say "Available today", "Limited" or "Sold out", does not confirm
  the shelf check and does not change the checked day. "Got more honey in" (it is here now) is `stock.set`; "more honey is
  coming Thursday" is this skill.
* **Clear vs `stock.clear`**: this skill's clear removes only the restock day. `stock.clear` removes the in stock / low / sold
  out word. They never change each other's field.
* A day and clear together ask which he means.

## The shelf report

`python3 hass/morning_report.py` and the chat report add one line per **active** product whose restock day is today or later,
after the unchanged shelf block (`I still need your shelf check.` ... `These come from your last shelf check, so they are not
stock counts.`):

```
Honey: more expected Thu Nov 12
```

* The weekday and month come from fixed English tables and the date itself (a date has no time zone, so it is never shifted).
* Sorted by day, then name, then id. Products that share a name stay separate lines. The list is complete: it is not cut at ten
  names and not merged into "and N more", so a long list can make the report longer than its usual 1200 characters.
* A past day is never shown and is never cleared automatically. A hidden or held product shows no line. With no restock days
  the report, its `--json` facts and its text are exactly what they were; with some, the facts carry `restocks`
  (`[{"id", "name", "day"}]`, day as `YYYY-MM-DD`).
* A malformed day on an active product makes the report say it cannot read the content (exit 1), as for any unreadable record.
  Days further ahead than 60 days that are already saved are still readable and shown.

## Where it stands

`live_class` is `private-only`. `product.set_restock` is in neither live table (`hass/live_policy.py`), so a real draft is
refused as "not live" until the operator lists it; that listing is a separate operator step and nothing here changes it. There
is no public "Back <day>" badge on the product card: that is a separate product decision. `preview` is `none` (the card does not
change); the test kit accepts that only for a skill that declares it and fails the row if any public file changed.
