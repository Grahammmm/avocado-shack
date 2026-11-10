# Stock skills: what is on the shelf (SKILLS-STOCK-1)

Three skills over the one inventory word a product carries (in stock, low, sold out) and the day the shelves were checked.
There are no counts and no prices: the site shows a word and nothing else. Design: `reports/hass/SKILLS-SPEC.md` 3.6, 3.7
and 3.9. Owner wording: `docs/hass/VOICE.md`. Skill model and authoring: `docs/hass/SKILLS.md`.

| Skill | What Mike says | What it plans | What changes |
|---|---|---|---|
| `stock.set` | "eggs are out", "avocados limited today", "got more honey in" | one `product.set_availability` per product | the product's word and its day |
| `stock.checked` | "I checked the shelves: avocados in, eggs low, bread out" | one `store.confirm_selection` | the shelf-check day, and the words of the products he names |
| `stock.clear` | "stop showing the eggs as sold out" | one `product.clear_availability` per product | the word and its day come off the card |

Code: `hass/skills/stock.py`. Cases: `hass/tests/fixtures/skills/stock/<skill>.jsonl`. Tests: `hass/tests/test_skills_stock.py`
and the generic kit tests (`test_skills_plans`, `test_skills_cases`).

## Today's shelf check: the merged question flow is the mechanism

A product's word only shows next to a shelf check dated today. When there is none, the editor refuses the change and
Conversation asks the one question of HASS-SHELFCHECK-FLOW-1, keeping the change in `open_asks` and writing nothing:

> Before I change that, is the shelf list right for today? Reply yes if it is, or tell me what is different.

His yes drafts the check and the change together ("This draft also records that the shelf list was checked today.", the
D2 default, said on its own line) and needs its own `yes <code>`. His no changes nothing.

So `stock.set` never plans `store.confirm_selection` itself: the flow adds it. The spec text planned it inside the skill
(`store.confirm_selection{yes|limited|no: [ids]}` when the check is missing); the card for this skill says to reuse the
merged flow instead of rebuilding it, and the flow produces the same draft. `stock.checked` is the skill for when he says
he did the check.

## The rules each skill applies (each repeats the editor's own, with a plain-words reply)

* **Six at a time (`stock.set`, `stock.clear`).** A shelf of at most six is one change each. More asks with the count:
  "That is 9 products, and I change six at a time. Which ones should I do first?" Never a bulk change.
* **Held or hidden.** Named and refused: "<name> is hidden. Do you want me to bring it back first?" or "I can't change <name>
  right now. It is on hold until someone has looked at it."
* **Not already true.** A word already set today says so: "<name> already says Sold out. Nothing to change." A word set
  on an earlier day is a re-check, not a repeat, and goes through.
* **One word per product.** The same product with two different words is one question ("Which one is right?"). In
  `stock.checked` a product named twice, in two lists or twice in one, is refused the same way, never counted once.
* **`stock.checked` days.** Today, or an earlier day at most a week back, and not before the last recorded check. A future
  day, an old day, or a repeat of a day that already says the same are refused in plain words.
* **`stock.clear`.** The product must have a word ("<name> has no label to clear."). It never sets "Sold out". It always
  needs its own `yes <code>`.
* **Prices.** None of these skills has a text slot. A price in the message is the interpreter's existing `PRICE_REPLY`.

## Undo

Every draft is undone with `undo` and its own yes (a `history.revert`): the word and its day go back, and a check day that
the same change wrote goes back with it. A later change keeps the check day it wrote. Nothing stays behind (residue: none).
`stock.clear` is also the other way back from `stock.set`.

## What the plans expect (interface assumptions for the dispatcher, SKILLS-FW-3)

* `plan(slots, ctx)` gets slots already resolved by code: product ids (`photo-product-NNN`), the words `yes` / `limited` /
  `no`, and an ISO Pacific day. Only `stock.set`'s `items` uses the structured kind `stock_items`: a non-empty list of
  `{"product": <id>, "availability": <word>}` objects with exactly those two keys, which the dispatcher checks for shape
  only (repeats, the six-product cap and every stock rule stay in the plan). The `stock.checked` and `stock.clear` lists
  stay `text_list` (product ids). Names and day words are resolved before the plan, as the spec says.
* `ctx.today` is the Pacific date as `YYYY-MM-DD`; `ctx.content` is the loaded content (`.products`, `.store`). Both are
  optional: with no `ctx` the plan skips the checks that need them and the editor repeats every one.
* A refusal is `hass.skills.stock.Refusal`, a `ValueError` whose `.reply` is the fixed owner reply (the same shape the test
  kit already reads). The dispatcher sends `.reply` and drafts nothing.
* `stock.clear` takes `items` (a list), not the spec's single `item`: "clear the words on eggs and honey" is one of its
  own sentences.

## Preview

The preview target is chosen by Conversation from the first record the draft touches. A draft that includes the shelf
check (the first change of the day, or `stock.checked`) previews the home page and its "Selection last checked by Michael
on <day>" line; a change after the check previews the product card. `stock.set` declares the card (`product:...`), as the
spec does; showing the card in the first-of-the-day case needs a preview change in `conversation.py`, which this card does
not touch.

## Sentences it must handle

Each is a case row (or a plan row for the part that needs a word already set); a row marked (x) must end in a refusal or a
question, never a draft.

* `stock.set`: eggs are out · egs r sold out again lol · avocados limited today · got more honey in · no more strawberries,
  peppers running low, lemons are back · bread is gone (a shelf of four) · honey is sold out (two honeys: asks which) ·
  the big sur one · we're low on stuff (asks which) · (x) everything is sold out (more than six).
* `stock.checked`: I checked the selection today: the avocados are in, the eggs are limited, the sourdough is sold out ·
  chekced shelves, avos in eggs low bread out · checked everything this morning, all good (records the day only) ·
  lemons in, strawberries in, figs out, honey limited · did the rounds (asks what he found) · I checked the shelves yesterday,
  eggs are out · (x) I'll check tomorrow · (x) checked on Monday last month · checked, nothing changed · shelf chek done. milk in, cheese out.
* `stock.clear`: stop showing the eggs as sold out · remvoe the sold out tag from honey · take the limited label off the
  peppers · clear the words on eggs and honey · clear the labels (asks which) · no label on the bread · the lemons shouldn't
  say anything · (x) clear every product's word · undo the sold out on eggs · (x) clear a product that has no word.

## Run

```
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/stock/stock.set.jsonl
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/stock/stock.checked.jsonl
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/stock/stock.clear.jsonl
python3 -B -m unittest hass.tests.test_skills_stock -v
```

The case runner starts from a shop with no check and no words, so its rows reach the question, the refusals and the whole
`stock.checked` draft, apply and undo. The paths that need an earlier approved change (a direct draft once today is
checked, not-already-true, clearing a real word, undoing the check day, a hidden product) are driven in
`test_skills_stock.py` on the same scratch shop.
