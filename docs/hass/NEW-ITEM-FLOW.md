# New item from a photo: what exists and how it fits (HASS-LIVE-ADD-2)

When Mike texts a new item with a picture, Hass makes **one** change (the product, the maker if new, the picture, the
description, the maker's story) and he says one `yes <code>`. One `undo` takes all of it back. This file is the discovery
that came first: short answers, then the rules. Mike's side is in [the phone guide](PHONE_GUIDE.md); the skill is in
[skills/item_add.md](skills/item_add.md).

## Discovery answers

1. **What `item.add` already did with a photo.** It asked for the name, packaged or fresh, the maker, their town, the shelf and
   whether it is in stock; drafted one change (`maker.add` + `product.add` with the photo and its caption, plus today's shelf
   check); showed a preview; one yes; one undo. The description came from `house_description` (serving sentences already on the
   site). A new maker got only the one line "<Maker> is based in <place>."
2. **What makes the house picture.** The pictures on the live site (`photo-product-NNN.webp`) were made on the Mac by an image
   model (`storefront-mockup/image-generation-log.json`). That cannot run unattended. The only unattended pipeline is
   `hass/newitem_render.py` (Pillow only: an 800 x 800 ivory square, the item cut out of a plain background, a soft shadow,
   JPEG), wired into `photos.install` behind the setting `houseRender` (off unless the setting is the JSON value `true`). Its
   pinned dependency is Pillow 12.0.0 (`PILLOW_VERSION` in `.github/workflows/check.yml`, [PILLOW-HOST.md](PILLOW-HOST.md));
   the venv `~/.local/share/hass/venv` has it, the system python does not.
3. **Descriptions and maker stories.** Descriptions: 2 to 3 sentences, 59 to 167 characters, present tense, no digits, `!`,
   `?` or hype words, a serving suggestion in a calm voice. Maker stories: 3 to 4 sentences, third person, present tense,
   taken from the maker's own about page. The checks are in `hass/house_style.py` and `hass/claims.py`.
4. **What did not exist before this change.** Reading a maker's website, asking Mike about a new maker, and letting a picture
   go live from chat.

## What was added

* **Picture.** `product.set_photo` is a live operation (only `id`, `photo` and `imageAlt`), for a product added in the same
  request and for an existing one. A photo the render cannot cut out (a busy shelf, too dark, too blurry, too small) is not
  put on the site: Mike gets one plain sentence asking him to take it again on a plain surface, and nothing is drafted.
* **Description.** Drafted in the house voice from Mike's words only. A claim (where it comes from, organic, health, award,
  price, contact, trail facts) is never written. His own wording that carries one is replaced by the house draft and the
  reply says "Left off: ...". A claim in the name, the story or the picture caption is refused in plain words and written down
  for Graham. He can still send a different description before `yes`.
* **Maker story.** A maker already on the site is reused. A new maker takes Mike's own words, plus a short story written by
  code from a few facts on the maker's **own** website when he gives its address (`hass/maker_site.py`: https only, a plain
  public name, the site's `robots.txt` obeyed, one request per site every 2 seconds, no accounts, keys, cookies or proxy,
  same-site redirects only (each hop checked like the first request), the whole read at most 8 seconds, 640 KB and 6
  requests, and done before the conversation's write transaction). No page sentence is copied: only what they make, the
  explicit founding year, and the town Mike confirmed, never a claim, contact, price, third party or instruction. What they make is
  written only with plain product words, so a claim joined to a product ("makes jam and relieves migraines") leaves that
  page sentence out, and the year and the town are taken only from a sentence that says them of the maker, with no
  negation (HASS-559-FIX). Each fact is taken only from a page sentence that is wholly one closed shape, every word from
  a closed list: after the product only workplace words ("in small copper pots", "in a shared kitchen", "by hand"), after
  the year only who or with what ("by two sisters", "with one pot"). Anything else ("and shut down in 2005", "and the date
  is fictional", "in a fictional story", "in a dream") is never stripped off: that fact is left out, and with no product
  left Hass asks him (AVO-FIX-559). Every sentence in the complete source block must state an allowed affirmative fact;
  unknown context drops the whole block, so abbreviation splitting and a later retraction cannot detach a usable fact.
  Product-making history is omitted, not turned into a founding year (AVO-FIX-559b). Mike sees it as "The
  maker's own site says: ... (source: <address>, read on <day>)" and it goes live only with his `yes <code>` to that draft
  (HASS-SEC-3). A site that cannot be read, or not in time, gets "I could not read their site; tell me about them in a
  sentence." With no words and no address Hass asks once: "What should we say about <Maker>? A sentence is enough." and
  invents nothing; "skip" keeps only the one line about the town. The address, the day and the complete supporting page
  blocks are kept privately with the draft (`maker-sources.jsonl`); the maker's website field stays protected and is not
  published.
* **One change.** The existing multi-op draft carries it all, so it uses one daily live-change slot and one undo hides the
  product and the new maker together. The picture file stays in the site folder, unused.

## Honest limits

* The render needs a plain background. A shelf photo gets a retake request, not a picture.
* The maker story from a website is at most two short sentences written by code from facts on the page, not model prose and
  never a page sentence; Mike reads it, with its address and day, before he says yes.
* The label text in the photo only helps with the name and brand question; it does not feed the description.
* **Host setting (operator):** `houseRender: true` in the Hass writer settings and the services on the Pillow 12.0.0 venv
  python. Until then a photo goes on as sent, and Hass says so before the yes.
* A page about a different maker would be rewritten under the name Mike gave; he sees the story and the address first.

## Rehearsal

`reports/hass/live-add-2/` holds the sample photo, the result picture and the exact command (Pillow 12.0.0, scratch writer).
