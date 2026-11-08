# Items: hide, restore and edit a product

Code: `hass/skills/items.py` (SKILLS-ITEMS-1). Cases: `hass/tests/fixtures/skills/items/`. Design: `reports/hass/SKILLS-SPEC.md`
sections 3.2 to 3.4. Authoring guide: `docs/hass/SKILLS.md`. Wording: `docs/hass/VOICE.md`.

Three skills let Mike take a product off the website, bring it back, and change its name, description, maker or shelf.
"Remove" and "delete" mean **hide**: nothing is ever deleted, and a hidden product comes back with everything it had
(its picture, its words, and no new "New" badge). **There is no price.** The website shows no prices and this build does not
change that (decision D9): a price anywhere in a message is refused with the existing sentence "The website doesn't show
prices, so I haven't made any change. Could you send it without the price?"

All three skills draft a change that Mike approves with `yes <code>`, show a preview of the product card, and are undone
with `undo` (which needs its own `yes`). Undo leaves nothing behind.

## `item.hide`: hide a product

Slots: `items` (one or more products, a list of at most six) and `reason` (optional; listed back in the reply and kept nowhere, never written to the product; it also helps Hass
tell "delete it for good" from "hide it"). Plan: one `product.hide` per product. Edits: `products[id].status`
(`hass/content/products.json`) and the generated product list. Preview: the first product. Live class: `chat-live`.

Rules (each one has a case row):

* `held-refused`: a product on hold is never changed ("I can't change ... right now. It is on hold until someone has looked at it. What was written down: ..."). The sentence repeats the recorded concern (for the raw milk cheese: that the maker's site shows a raw-milk cheese recall and the hold waits for exact product and lot checking), never a web address, file or id.
* `already-hidden`: "I already have ... hidden. Nothing changed." With a list, the sentence names the product and offers to do the rest.
* `whole-shelf`: a shelf word such as "all the bread" is a list of its products. More than six asks with the count: "That is 13 products at once. Which ones should I hide?"
* `no-permanent-delete`: "delete it for good" is answered "I don't delete anything for good. I can hide it instead: ..." and the caller writes the request down (`Refusal.backlog` is `policy`).

The ten owner sentences:

| Sentence | What Hass does |
|---|---|
| hide the plums | There are no plums on the website, so it asks "I don't know a product called that. What is it called on the site?" |
| take the cashews off the site | Hides Cashews. |
| remvoe the strawbery jam | Hides Cal Poly strawberry jam. |
| hide the figs, the cashews and the guacamole | One draft, three products. |
| get rid of the old stuff | Asks "Which product should I hide?" |
| we dont carry Etto anymore | Asks whether to hide all five Etto products; the answer ("all of them") is one draft of five. (Hiding the maker itself is the makers skill.) |
| delete the guacamole | Hides it, and says it is hidden, not deleted (see `notes` below). |
| pull all the bread | The four breads in one draft. |
| stop selling the lemons | Hides Lemons. |
| delete everything | Asks which ones; never a bulk hide. |

## `item.restore`: bring a hidden product back

Slots: `items` (one or more hidden products). Plan: one `product.restore` per product. Edits: `products[id].status`
and the generated product list. Preview: the first product. Live class: `chat-live`.

Rules:

* `not-hidden`: "I already have ... on the website. Nothing changed."
* `held-refused`: a product on hold is not brought back; the refusal gives the recorded concern in plain words (for the raw milk cheese: the maker's raw-milk cheese recall and the exact product and lot check the hold waits for).
* `maker-hidden`: "I can't bring ... back while its maker, ..., is hidden. Bring ... back first, ..."
* `image-missing`: the picture file must still be there. The editor already refuses; the skill says it in plain words when it is told where the site folder is.

| Sentence | What Hass does |
|---|---|
| bring back the lemons | Restores Lemons. |
| put the cashews back | Restores Cashews. |
| resotre the figs | Restores Figs. |
| lemons and guacamole are back on | One draft, two products. |
| undo what I hid yesterday | Points at `undo` and `history` ("To undo the last change, say undo. To see what we changed lately, say history."). |
| make the cashews visible again | Restores Cashews. |
| un-hide the garlic pesto | Restores Garlic pesto. |
| bring back the raw milk cheese | Refused: it is on hold. |
| put it back | Asks "Which hidden product should come back?" |
| restore everything I hid | Asks which ones and points at `hidden`; never a bulk restore. |

## `item.edit`: change a product

Slots: `item` (required) and any of `name`, `description`, `category` (a shelf), `maker`, `display_brand` (the maker line
on the card), `image_alt` (the picture caption) and `clear` (`clearProducer`, `clearImageAlt`). At least one change is
needed ("What should change on ...?"). A change of maker sets the maker and the brand together and the maker line on the card
follows the maker unless Mike gives another label (Hass says "I set: the maker line on the card to ..."). Clearing the maker
makes the product "Producer not identified", shown as "From the market", as the 62 products with no maker already are. A text slot
replaces the **whole** text, so a partial change ("add a line to ...") arrives as the full new text built from the current one.
Plan: one `product.edit` with only the fields that really change. Edits: `products[id].name`, `.description`,
`.category`, `.brand`, `.producerKey`, `.displayBrand`, `.imageAlt` and the generated product list.
Preview: the product, with the old text shown in full. Live class: `private-only` for the skill as a whole, because a maker, brand or
maker line is a protected field; a name, description or shelf change on its own is `chat-live` (both are tested against the real
live policy).

Rules:

* `not-already-true`: a field that already has the asked value is dropped; nothing left says "It already says that on ... Nothing changed."
* `twin`: a rename may not give two products the same name and maker.
* `no-price`: `$`, "per lb", "cents", "dollars", "bucks" or an amount such as "two for five", "2 for 5" or "five bucks each" in any text refuses with the price sentence (a number on its own, "two for five minutes" or "Bucks County" does not). A `price` slot does not exist, and one that arrives anyway is refused the same way.
* `held-refused`: a product on hold is not changed, and the refusal gives the recorded concern in plain words.

Also refused in plain words: a hidden product (bring it back first), a hidden or unknown maker, an unknown shelf, text that is too
long or carries special marks (`< > {{ }}`).

| Sentence | What Hass does |
|---|---|
| rename the Hass avocado to Hass avocados | Changes the name. |
| chnage the pesto desription to say its great on toast | Changes the description (the whole new text). |
| move the garlic pesto to the dairy shelf | Changes the shelf. |
| rename the oranges to Navel oranges and add a line to the lemons description: try a squeeze over roasted vegetables | One draft, two products. The line is the owner's own; the lemons text is the current one plus that line. Without the line Hass asks for it and writes nothing of its own. |
| the guacamole text is boring | Asks "What should the guacamole description say instead?" |
| the figs are by Fair Hills Farm now, not Producer not identified | Changes the maker, brand and maker line (private-only). |
| make the eggs $6.50 | Refused: the website doesn't show prices. |
| the lemons description: 3 for $5, best deal | Refused the same way; Mike can send it without the price. |
| add a line to the guacamole description: pairs well with chips | Changes the description (the current text plus the new line). |
| fix the picture caption on the lemons | Asks what the photo shows; the answer becomes the caption. |

## What the owner sees besides the draft: `notes()`

`items.notes(name, slots, ctx)` returns the extra lines for the proposal: `say` (`item.hide`: "It is hidden, not deleted. You can bring
it back any time.", and when Mike gave a reason, "You told me why: ... I haven't saved that on the product."), `set` (`item.edit`: the "I set: ..." line for the maker line) and `warn` (`item.edit`: advice when a new description is
longer or shorter than the site's 59 to 167 characters, has no full stop, or uses `!` or `?`; advice only, never a refusal).
The test kit plays this contract: after a skill's plan it calls `notes` and appends the lines to the reply of a message that ends in a
draft, so the rows assert them (`hide-7-delete-means-hide`, `hide-15-with-reason`, `edit-4-two-products`, `edit-6-maker`, `edit-18-no-maker`).
The live conversation does not show these lines yet; that is the dispatcher card's job.

## Interface assumed (the router and dispatch are not merged yet)

This card changes neither `conversation.py`, `interpreter_prompt.py` nor the router. It is proved with the test kit, which plays the
recorded model reply and turns it into ops with the skill's own `plan`, as the dispatcher will. What the skill assumes of the dispatcher:

* Slot values arrive resolved by `hass.skills.kinds`: product ids (`items` is a list), a maker key, a shelf word. Which product, and which
  of several, is asked by the dispatcher from `Slot.ask` and the resolver replies. The `items` slot is declared as a `product_ref` that takes a list.
* `plan(slots, ctx)` gets `ctx.today`, and in a conversation `ctx.content` (the loaded, read-only content), and `ctx.site_dir` when
  picture files can be checked. Rules that need the current content run only when `ctx.content` is there; the editor checks them again.
* A refusal or question the plan cannot avoid is raised as `items.Refusal`, a `ValueError` with `.reply` (the owner's sentence) and
  `.backlog` (a backlog reason when the request should also be written down, else `None`).
* Slot names are lower case (`display_brand`, `image_alt`) as the lint requires; the op arguments keep `displayBrand` and `imageAlt`.

## Found while building

* **`show` is a command.** The spec's sentence "show the cashews again" begins with `show`, and `conversation.COMMAND_RE` takes any message
  that starts with `show` as `show <code>` before any skill runs. The fixtures use "make the cashews visible again" instead, and
  `test_skills_items.py` fails if any sentence of these skills is a whole-message command. The dispatcher card may want `show`
  to match only a draft code.
* **Clearing a maker asks about wording.** The claims gate (`AV2022-04`) wants a changed brand or maker line to share a word with Mike's message, so
  "nobody knows who makes the guacamole" is answered with a question. The row uses "the guacamole should say producer not identified, from the market".
* **The product names in the spec's sentences** (plums, walnut oil, quince, lavender honey) are not on the website today. Where a happy-path row needs a
  product, the fixtures use one that is. "hide the plums" is kept as it is and answered honestly with "I don't know".
* The generated site files that change are `catalog-products.js` only (not `index.html` or the producer files); the declared edits say so.

## Running the cases

```
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/items/item.hide.jsonl
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/items/item.restore.jsonl
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/items/item.edit.jsonl
python3 -B -m unittest hass.tests.test_skills_items hass.tests.test_skills_plans hass.tests.test_skills_cases -v
```

A restore row starts from a hidden product, which the shop's content does not have, so the kit gained two small optional row fields:
`setup` (ops applied through the real editor before the row starts) and `undo` (the row must end in an approved draft that is undone). See
`hass/tests/fixtures/skills/README.md`.
