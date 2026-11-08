# Add a new item: `item.add`

Skill `item.add` (SKILLS-ITEMADD-1, card 14 of 20 in `reports/hass/SKILLS-SPEC.md`, row 3.1). Code: `hass/skills/item_add.py`.
Cases: `hass/tests/fixtures/skills/item_add/item.add.jsonl`. Tests: `hass/tests/test_skills_item_add.py`,
`hass/tests/test_undo_new_item.py`, plus the shared runners `test_skills_plans` and `test_skills_cases`.
Authoring rules for any skill: `docs/hass/SKILLS.md`. Wording: `docs/hass/VOICE.md` (every reply below follows it).

## What it does

Mike sends a photo and a few words ("new honey from Cal Poly, goes on the pantry shelf"). Hass drafts **one** change that adds
the product, the maker when the maker is new, the picture, and (once he says whether it is in) the stock word with today's
shelf check. He sees the draft and a preview and says `yes <code>`. Nothing is written before that yes. The editor, the claims
gate, the live boundary, the preview and the approval are the existing ones; the skill only plans typed ops.

## What Hass asks, in order (one short plain question per reply)

| Field | Slot | Filled how | Question when missing |
|---|---|---|---|
| name | `name` | his words; a price or size is taken out | "What is it called?" |
| packaged or fresh | `form` | `derive:form_guess`: a container word (jar, bottle, bag ...) means packaged; "fresh", "picked" means fresh; else the shelf | "Is it packaged or fresh?" |
| maker or farm | `maker` | his words; "same" / "same farm as last time" = the maker of the product added last; "don't know" = from the market | "Who grew these tomatoes?" (fresh) / "Who makes this lemon curd?" (packaged), plus "(Say “same” for <Maker>, the farm/maker from last time.)" when there is one |
| their town | `place` | `derive:saved_place` for a maker already on the site; only asked for a new maker | "Where is <Maker> based (town and state)?" |
| shelf | `shelf` | the shelf he named, else `derive:same_kind_majority` (where most products of the same kind sit) | "Which shelf does it go on: Dairy & cheese, Meat, Pantry, Drinks & coffee or Bread?" |
| description | `description` | `derive:house_description`: one line in the shop's voice from his words and the serving sentences already on the site (#504 engine). Machine-valid, **not accepted**: shown as "I set: the description to ..., and you can send a different one if you like." | never asked unless the draft cannot be made |
| picture caption | `image_alt` | `derive:alt_text`: the name, plus "in a jar" only when he said jar | never asked unless the draft cannot be made |
| in stock or not | `availability` | his words only ("got in" = yes, "only a few" = limited, "sold out" = no) | "Is it in stock right now?" |
| the photo | `photo` (attachment) | the sha256 of the stored original | "Send a photo of it." |

Optional, never asked: `story` and `maker_url` for a new maker, `display_brand`.

A product his name and maker already have on the site (a twin) is named **before** anything else is asked:
"Rigatoni pasta is already on the site. Do you want to change it instead?" (a hidden twin: "... is on the site but hidden. Do you
want me to bring it back instead?"; a held twin is refused).

## The draft

* New maker: `maker.add` (with no story, the D5 one line "<Maker> is based in <place>.") and the line "<Maker> is new on the site,
  so I'm adding them too." A maker already on the site: "<Maker> is already on the site, so I'm using them." A hidden maker is
  never used: "<Maker> is hidden. Do you want me to bring them back first?"
* `product.add{name, brand, category, description, producerKey, photo, imageAlt}`; an unknown maker gets the house words
  (brand "Producer not identified", the card says "From the market", no maker record) and the line "I couldn't tell who makes
  it, so the card says it is from the market."
* **D2:** today's shelf check not recorded yet: `store.confirm_selection{<word>: [<new id>]}` and its own line "This also records
  today as the day you checked the shelves." Already recorded today: `product.set_availability{id, available}`, no extra line.
* **D9:** a price or size is never written: "Left off: the price ($9) and the size (8oz), because the website shows no prices or
  sizes." A name that is still a number after that is asked again.
* Claims (organic, local, origins) pass only when he said them; the claims gate in the editor checks the draft again and the
  live policy still stops a live release of a new product (brand, displayBrand and producerKey are protected: live class
  `private-only`, D4).
* **One photo, one product:** when his words ("add the lemon curd and the plum jam", a name that lists two products, `&`, `+`, or
  "both" beside an "and" in the name) put two products on the one photo, the skill itself asks "One photo can go on one product.
  Which one is this photo for?", whatever the interpreter returned. A single name with an "and" in it ("Salt and vinegar chips") is
  one product.
* **The house description is enforced, not only reported:** a description (his own, or the drafted one) with a digit or price, a
  hype word, `!` or `?`, a length outside the shop's measured 59 to 167 characters or a sentence count outside 2 to 3 is not
  drafted; he is asked: "That description won't match the others on the site: ... Could you send a different one?" A claim word
  he did not say is left to the claims gate, which asks him about it.
* **Preview:** the proposal screenshot is of the new product card (its picture and neighbours), also when a new maker is added
  with it (`preview.proposal_record`); the maker record comes first in the change only because the product needs it.
* **D6, the picture:** with the house render on (`houseRender`, SKILLS-PIC-1), a photo the render cannot make house-style gets a
  kind retake line ("I couldn't separate the product from the background ... A new photo on a plain surface ... If this one is
  fine, just reply yes."); a small one: "This photo is small ...". With the render off (today), the photo goes on as sent and a photo
  that misses the house look gets "I'll use the photo as you took it, so it may look different from the other pictures ...". The
  advice is read-only (`hass/house_style.py`, `hass/newitem_render.py`); Mike may say yes knowingly.

## Undo

`undo` drafts a `history.revert` that needs its own yes. The product is hidden, not deleted; a maker the change added is hidden
with it; the picture file stays in the site folder, unused (the declared residue). **The stock word and its day go with the
product, and the shelf-check day goes back**, so a new item and today's shelf check undo together (`hass/ops/history.py`). Every
other record, the store and the site files come back exactly as they were. Undoing the newest of two new items leaves the first
one as it is; an item Mike edited after adding it is a conflict ("changed after"), never overwritten.

## How the plan sees the world (dispatcher interface)

Built against the SKILLS-FW-3 dispatcher (PR 526) and the FW-2 router (PR 525), neither merged when this was written.

* `plan(slots, ctx)` is pure. `ctx.content`, `ctx.today`, `ctx.texts` (his joined texts) and `ctx.media_root` /
  `ctx.photo_bytes(sha)` are optional; `ctx.next_product_id` and `ctx.selection_checked_today` override what the content says.
* A plan that must stop raises `Refusal` (`.reply`, `.kind` "question" or "refuse").
* `question(slot, slots, ctx)` gives the dynamic question; `notes(name, slots, ctx)` gives the `say` / `set` / `warn` lines shown
  beside the draft.

**Known gaps until FW-3 grows three small hooks** (the test kit plays them; the live chat does not yet): the dispatcher must show
`Refusal.reply` instead of a generic "Sorry", call `notes()` so the shelf-check, "Left off" and picture lines are shown, and call
`question()` so the "same as last time" offer is made. "Same as last time" also meets the claims gate, which wants the maker
named in his own words: today he is asked once to name the farm, then the draft follows (case `same-farm-tomatoes`).

## Cases (`item.add.jsonl`)

13 conversation rows through the real Conversation and Editor and 6 plan rows: the ten spec sentences (clean, misspelled,
vague "add this", a photo with no words, twin, price and size, unknown maker, one question at a time, two items on one photo,
organic said), a photo with the name as its caption, same farm as last time, a hidden maker, and today's check already
recorded; 8 rows end in an approved draft that is undone. They use the synthetic photos of #504
(`reports/hass/newitem-1/synthetic/`).

```
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/item_add/item.add.jsonl
python3 -B -m unittest hass.tests.test_skills_item_add hass.tests.test_undo_new_item -v
```
