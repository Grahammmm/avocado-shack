# Social caption skills (social.item, social.hike, social.maker)

SKILLS-SOCIAL-1 part 1 (SKILLS-SPEC 3.27, 3.28). Code: `hass/skills/social.py`. Tests: `hass/tests/test_skills_social.py`.
Case rows: `hass/tests/fixtures/skills/social/`.

Hass writes a caption the owner can copy and post himself. **Hass posts nothing.** These three skills are read-only:
approval `none`, edits none, no draft, no `yes <code>`, nothing posted, sent, saved or scheduled, and no file is attached.

| Skill | Ask it like | The caption comes from |
|---|---|---|
| `social.item` | "write a post for the honey", "caption for the plum jam", "post about the avocado" | `social_draft.build` (the same text as `post <id>`) |
| `social.hike` | "write a post for the Bluff Walk", "caption to announce Saturday's hike" | `social_draft.build_hike` (the same text as `post hike <id>`) |
| `social.maker` | "write a meet the maker post for Linn's" | `social_draft.build_maker` (the same text as `python3 hass/social_draft.py --maker KEY`) |

## What the owner sees

```
Here's a post you can copy. I haven't posted anything.
<the caption, exactly as social_draft builds it>
The photo is the one on the product card; it isn't attached here.
```

A hike or maker caption ends with `No photo is attached here.` instead (those captions have no photo). The caption is
never reworded or shortened; a full caption may be longer than an everyday message (`dispatch.READ_ONLY_LONG`), while every
other voice rule still applies to Hass's own words.

The product photo is checked in the writer checkout's own `storefront-mockup/` folder (`Ctx.site_dir`), the same checkout
the content was read from. Without that folder Hass says it can't check the photo; it never falls back to another folder.

Two or more captions in one message give one answer each, in order (the same one asked twice is answered once). If one of
them needs a name, Hass asks for it after answering the others, and the rest wait their turn. A caption and a change in
the same message are not split up: Hass asks for the change in its own message and drafts nothing.

## Refusals (plain words, nothing changes)

- a held product: "That product is on hold, so I can't write a post for it yet."
- a hidden product: "That product is hidden, so I can't write a post for it."
- a product with no photo on the website (missing, or outside the site folder): "That product has no photo on the website yet, so I can't write a post for it."
- a cancelled hike / a past or completed one / one not scheduled: "That hike is cancelled, so there is nothing to announce." /
  "That hike has already happened, so there is nothing to announce." / "That hike isn't scheduled yet, so there is nothing to announce."
- a maker with no story: "That maker has no story yet, so I can't write a post about them. Add the maker's story first."
- a hidden maker, or one with nothing on the website, a `#` or `@` in the saved words, or a caption over 2200 characters: one plain sentence each.
- "post it now", "schedule it", "publish …", "send it to the club": "I can write a caption for you to copy, but I don't post, send or schedule anything."
  Ordinary caption wording ("post about the honey", "I'll post it myself") is a caption request, not a posting request.

## Not the same as

- `post <id>` and `post hike <id>` (typed commands, `hass/conversation.py`): unchanged. `post <id>` still attaches the product photo and
  its alt line; the skills reply text only.
- `python3 hass/social_draft.py …` (the command line): unchanged; prints the same captions as JSON.
- The later `social.recap` skill (AV1109-07) reuses this module's replies and registration; it is not part of this one.
