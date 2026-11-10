# Item picture: put a new photo on one product

Code: `hass/skills/item_picture.py` (SKILLS-ITEMPIC-1). Cases: `hass/tests/fixtures/skills/item_picture/item.picture.jsonl`.
Tests: `hass/tests/test_skills_item_picture.py`. Design: `reports/hass/SKILLS-SPEC.md` section 3.5. Authoring guide:
`docs/hass/SKILLS.md`. Wording: `docs/hass/VOICE.md`.

Mike sends a photo and names the product. Hass drafts **one** change, `product.set_photo`, that points that product's picture
at the photo and sets a caption that says what it shows. He sees the preview of the product card and the picture advice, and
says `yes <code>`. Nothing is written before his yes. Undo needs its own yes.

## What Hass asks

One short question at a time, only for what is missing:

| Slot | Question | Notes |
|---|---|---|
| `item` (a product) | Which product is this photo for? | Resolved against the saved products. A held or hidden product is refused (below). |
| `photo` (the photo in his message) | Send the new photo. | Only a photo he sent in this request is used; an id the model makes up is never used ("I can't find that photo. Send the new photo."). |
| `image_alt` (the caption) | What does the photo show? | When he does not say one, the caption is the product's saved name and the proposal says "I set: the picture caption to ...". His own words ("photo for the Etto rigatoni, in the box" gives "Etto rigatoni in the box") are used as he said them. The op argument is `imageAlt`. |

## The caption must say what the photo shows

A file name (`IMG_1234.jpg`), a camera name (`DSC01234`), a placeholder (`photo`, `the picture 2`), a screenshot name, a web
link, the photo's id or a caption over the site's limit is never used. Hass asks: "The picture caption should say what the
photo shows, like “Meyer lemons in a wooden crate”. What should it say?" The caption is drafted from the product's name, never
from the old caption.

**Catalog illustrations (D1).** The page labels a catalog picture "<name> (illustration)". His photo is saved as a
`photo-<sha16>` file, which the page labels as a photo, so the " (illustration)" suffix goes away. A caption never carries
that suffix, even if an old caption had it.

## Rules (each has a case row or a test)

* `hidden-or-held-refused`: a product on hold: "I can't change Raw milk white cheddar right now. It is on hold until someone
  has looked at it." A hidden product: "Guacamole is hidden. Bring it back first, then I can change its picture." Nothing is
  restored or taken off hold.
* `already-this-photo`: the product already shows this very photo (the same stored photo, as a JPEG or a PNG): "Lemons
  already has this photo. Nothing changed." A new caption on the same photo is item.edit's job.
* `one-photo-one-product`: "photos for the lemons and the plums" asks "Send the photos one at a time. Which product is this
  photo for?". "use this for the home page and the lemons" asks "One photo can go in one place. Is this photo for the home
  page, or for a product?". Nothing is drafted until he names one product; his answer ("the lemons") goes on to one draft.
  A single product whose name has "and" in it (Salt and vinegar chips) is one product. The list is found with or without
  "the" ("photos for lemons and plums" asks too), and a reply that is itself a list ("lemons and plums please") is not
  the one product he was asked for, so it asks again. A list can be commas alone ("photos for lemons, plums", and the reply
  "lemons, plums please"); a comma before a caption or a reply word ("photo for the Etto rigatoni, in the box", "the
  lemons, please", "yes, the lemons") is still one product.
* No product list to check against (the plan is handed no content): nothing is drafted. The plan refuses with "I couldn't
  check that product just now, so nothing is changed. Try again in a moment." rather than skip the hidden/held recheck.
* `alt-says-what-it-shows`: above.
* `house-picture`: the advice beside the draft, the same advice item.add gives (`picture_review` is item.add's own function):
  * with the `houseRender` setting off (today's default), a photo that does not look like the other pictures gets "I'll use the
    photo as you took it, so it may look different from the other pictures. ... If this one is fine, just reply yes." He may
    approve it knowingly (D6).
  * with it on, a good photo says "The picture is tidied up to match the other pictures on the site." A busy background or a
    small photo is refused by the installer (`photos.install` returns its retake refusal) and nothing is drafted or saved,
    exactly as for item.add today. Approving the letterboxed fallback with the flag on is not built here; it belongs to the
    PIC-3/D6 photo-seam card.
  * a photo that cannot be read, or picture tools that are missing, is said ("I couldn't check how this photo will look ...").
    The check never passes silently.
  * a phone photo with a rotation tag keeps its tag (the page shows it upright); with the house render on it is turned
    upright. It is not called sideways.

## Preview, edits, undo

* Preview: the product card (`product:the product`).
* Edits: `products[id].image` and `products[id].imageAlt` in `hass/content/products.json`, the new picture file
  `storefront-mockup/assets/products/photo-<sha16>.<jpg|png>`, and the generated `storefront-mockup/catalog-products.js`.
  Nothing else on the product changes.
* Undo puts the old picture and caption back. **Residue:** the new photo file stays in the site folder, unused. The old
  picture file is never removed, so undo can always put it back.

## Live class: private-only

The catalogue calls this skill chat-live, but `product.set_photo` is not in the live boundary (`hass/live_policy.py`), so on
this base a picture change is kept private until the live boundary's own owner widens it. This card does not change that.

## The owner sentences (spec 3.5)

| Sentence | What Hass does |
|---|---|
| new picture for the lemons | Drafts the photo on Lemons, caption "Lemons". |
| here's a better one of the Stardust guacamole | Drafts it (refused while Guacamole is hidden). |
| fixed the pic for the oragnes | Drafts it on Oranges. |
| this one is better | Asks "Which product is this photo for?" |
| (photo first) the Big Sur honey | Drafts it on Big Sur Honey Company honey. |
| photos for the lemons and the plums | Asks him to send them one at a time. |
| photo for the Etto rigatoni, in the box | Caption "Etto rigatoni in the box". |
| new photo for the raw milk cheese | Refused: it is on hold. |
| retake of the bread, plain counter | Drafts it, with the picture advice before his yes. |
| use this photo for the lemons and the home page | Asks which place. |
