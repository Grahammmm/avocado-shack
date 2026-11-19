---
name: hass-product-photo
description: Use when deciding the picture for a new card (S6). Match the gallery; change no existing picture rule.
---

# Product picture (pipeline stage S6)

## When to use
Stage S6 decides, and freezes, which picture the existing `ops/photos.install` will publish for this listing, and records
its variant, site path and bytes sha256 on the version. The image recipe the picture must match is in `hass-gallery-style`.

## The rule in one paragraph
There is no new picture format, path, threshold or label. The polished picture is a `gpt-image-2` high **edit of the
owner's own photo** onto the gallery's ivory background, and the existing fidelity gate (`photo_polish.gate`, `frame`,
`house_style.check_image`, OCR both ways) says whether it is the same product. If it fails or is late, the pipeline uses
what install would publish today: the owner's own web copy (raw) with the live settings, or the house render when the
polish is switched off. A photo that cannot be published safely gets the existing retake sentence.

## Procedure
1. Ask `ops/photos` which variant install would choose (a pure helper; install semantics unchanged). Order and conditions
   are in `photo.json` `variant_order`.
2. For `raw`, check every `raw_conditions` entry. All must hold: no person or screen in the frame, a successful OCR read,
   no money-shaped or private token, no phone, email or home path, and a sharp photo. Otherwise the variant is **none**.
3. Freeze `image_variant`, `image_path` and `image_sha256` on the version. Later edits copy them from the previous version.
4. Alt text: plain words, from the `alt-*` templates; no `(illustration)` suffix.
5. Tell the owner when the variant is not polished: `(picture: house style)` or `(picture: your own photo)`.

## Rules
- The edit prompt is `photo.json` `prompt`, identical to `photo_polish.PROMPT`. Change its words only after a re-evaluation
  (private-host run, gate results) in the same card; the test pins the two together.
- A styled picture that finishes after the write-once decision is never used (`polish-late`). "Try the picture again" asks for a
  new photo.
- After a restart with `polish_started_at` set and no decision, never start a second edit.
- Never weaken a gate threshold to make a picture pass.

## Pitfalls
- Using the raw photo for a card whose photo shows a screen, a person, a price sticker or a cost sticker.
- Treating "house" as the normal fallback: with the live settings the fallback is raw.
- Writing the alt text as `(illustration)`: all three variants are installed owner paths.
