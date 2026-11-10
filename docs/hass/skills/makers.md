# Maker skills: add, edit, hide and restore a maker and their about text

Skills `maker.add`, `maker.edit`, `maker.hide` and `maker.restore` (SKILLS-MAKERS-1, card 10 of 20 in
`reports/hass/SKILLS-SPEC.md`, rows 3.16 to 3.19). Code: `hass/skills/makers.py`. Cases: `hass/tests/fixtures/skills/makers/`.
Tests: `hass/tests/test_skills_makers.py`, plus the shared runners `test_skills_plans` and `test_skills_cases`.
Authoring rules for any skill: `docs/hass/SKILLS.md`. Wording: `docs/hass/VOICE.md` (every reply below follows it).

## What a maker is on the site

A maker has a name, a place ("Town, State"), a story and an optional website. There is **no maker page**. The place shows as
"Based in ..." on each of their product cards, and the story shows under "Meet the maker". "About" for a maker means that story.
The one "COME ON IN" paragraph on the home page is a different thing (`store.set_story`). A maker with no product shows
nowhere on the site. Nothing is ever deleted: "remove" means hide.

## The four skills

| Skill | Owner says | Plans | Live |
|---|---|---|---|
| `maker.add` | "add a maker: Bee Happy Farm in Atascadero, they keep bees on the hill, beehappyfarm.com" | `maker.add` | private-only |
| `maker.edit` | "update Etto's story: they started in a small kitchen", "rename Linn's to Linn's Preserves" | `maker.edit` | private-only |
| `maker.hide` | "we stopped carrying Etto" (asks about their products) | `maker.hide`, with their products if he says yes | private-only |
| `maker.restore` | "Etto is back" | `maker.restore` | private-only |

Slots (snake_case; the plan turns them into the op's own argument names):

* `maker.add`: `name` (asks), `place` (asks "Where are they based (town and state)?"), `story` (optional), `url` (optional).
* `maker.edit`: `maker`, then any of `name`, `place`, `story` (replaces the whole text), `url`, `clear_url`.
* `maker.hide`: `maker`, `with_products`. `maker.restore`: `maker`.

### The about text (spec 3.16, D5)

* The story is **his sentences**. A sentence that starts with They, She, He, Their, His or Her gets the maker's name instead
  ("They keep bees on the hill." becomes "Bee Happy Farm keeps bees on the hill."), with the verb bent to fit when it is a plain
  one. A sentence we cannot bend safely is left exactly as he wrote it. Nothing is rewritten beyond that and nothing is invented.
* A claim (organic, origin, health and the rest of `claims.py`) only stays if he said it, as he said it. When the plan can see his
  joined texts (`ctx.owner_text`) a story sentence with a claim he did not say is left off and listed under "Left off". The editor
  runs the same claims check again on the draft, so the real conversation asks even without that.
* **D5 (G's default, 2026-11-08): a maker with no story gets the one line "<Maker> is based in <place>."** and the proposal says
  "I set the about text to ..., because you didn't give one". Leaving the story empty would need a content-model, sitegen and
  `shop.js` change (a separate card).

### Questions and refusals (plain words, one question at a time)

| Situation | Reply |
|---|---|
| no name / no town | "What is the maker called?" / "Where are they based (town and state)?" |
| the maker is already there | "<Maker> is already on the site. Do you want to change it instead?" (a hidden twin: offers to bring them back) |
| price in any maker text | the site-wide `PRICE_REPLY` ("The website doesn't show prices ...") |
| special marks (`<`, `>`, `{{`) | `PLAIN_TEXT_REPLY` |
| a website that is not one public https address | "That doesn't look like a full website address. Could you send it like https://example.com?" A bare "beehappyfarm.com" gets `https://` in front. |
| the new value is what is there already | "<Maker> already says that. I haven't changed anything." |
| nothing to change | "What should change about <Maker>?" |
| a website link the site started with | "... was on the site from the start, so I can't remove or change it. You can ask Graham." |
| unknown maker | "I don't know a maker called X. Who is it?", or "Do you mean A or B?" with close names |
| several fit | "Which maker do you mean: A or B?" (at most 10) |
| edit or hide a hidden maker / restore a visible one | "<Maker> is hidden. Do you want me to bring them back first?" / "<Maker> is already on the site." |
| hide a maker with products | "Do you want me to hide their 5 products too?"; "keep the products" is refused naming them ("... leave their products on the site: A, B and C. Do you want me to hide them too?") |

A hidden maker may not have active products on the site, so a hide takes the active ones with it (held products are never touched).
**Undo** of a combined hide brings the maker and those products back together. **Restore** brings only the maker back; their
products come back one at a time through `item.restore`, and the proposal says so.

## How the plan sees the world (interface assumptions for the dispatcher, SKILLS-FW-3)

`plan(slots, ctx)` is pure: it never writes, never calls the network and answers the same twice. `ctx` is read-only and every
attribute is optional:

| `ctx.` | Used for | When missing |
|---|---|---|
| `content` | name lookup (including hidden makers for restore), twin check, "already says that", the product names a hide takes, the claims check against the current text | the maker slot is taken as the exact key; the editor's own checks still refuse a twin, an unknown key or a maker that still has products |
| `owner_text` | the owner's joined texts, for the claims check on the story | the editor's claims gate on the draft (same rule, on the text the conversation passes it) |
| `source_urls` | website links recorded at migration | the frozen baseline in `hass/content/migration-baseline.json`, read once at import |

* The maker slot is the key or the name as he said it; the plan resolves it with `catalog.lookup` and says what is wrong in plain
  words. `maker_ref` in `kinds.py` hides hidden makers from restore, so these skills resolve their own (`find_maker`). The
  `maker.restore` slot is therefore declared as plain `text` (the dispatcher checks only that it is ordinary text) and its plan
  passes the owner's words to its own hidden-aware `find_maker`; `maker.edit` and `maker.hide` keep `maker_ref`, which still
  refuses a hidden maker.
* A plan that must stop raises `makers.Refusal` (a `ValueError` with `.reply`, the fixed owner reply, and `.kind`, "question" or
  "refuse"). The shared kit already turns a plan that raises into an `unsupported` reply carrying `.reply`.
* `describe_add / describe_edit / describe_hide / describe_restore` return `Outcome(ops, set_lines, left_off, notes)` for the proposal
  lines `I set: ...`, `Left off: ...` and a plain extra sentence. `plan_*` is `describe_*(...).ops`.
* **Preview.** A maker record previews as the `maker` target (`hass/preview.py`), which is what the conversation requests today. The
  spec lists `home` (add, hide, restore) and `product:<a product of that maker>` (edit). The kit now accepts the `maker` target for
  both; showing the product card with "Meet the maker" open is a previewer change, not part of this card.
* **Place change.** The editor's own "Heads up: ... changes the 'Based in' line on N product cards" is the `place-warning` rule; it is
  not repeated by the skill.
* **Website links from migration** cannot be removed *or replaced*: the editor's migration check fails the apply ("I couldn't save
  that change"), so the skill says so before the draft. Links added since can be changed or removed.

## What is proved and what is not

Proved in CI with no model and nothing live: the lint; every rule one by one; the plain-words check over every reply for all 26
current makers; the case files (about 60 rows: add 18, edit 20, hide 12, restore 10) through the real Conversation, Editor, sitegen and
claims on a scratch copy, including the exact content diff, the exact generated files, "nothing written before yes", undo returning
the tree (an added maker stays hidden, declared as the skill's residue), and a restore of a hidden maker with its undo.

Not proved: a real model choosing these skills (the dispatcher and router are SKILLS-FW-2 / FW-3, not touched here), the live boundary
on the real site, and a real maker added to the live site. A maker the owner adds shows nowhere until a product uses them.
