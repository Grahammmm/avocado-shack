# Social caption skills (social.item, social.hike, social.maker, social.recap)

SKILLS-SOCIAL-1 (SKILLS-SPEC 3.27 to 3.29). Code: `hass/skills/social.py`. Tests: `hass/tests/test_skills_social.py`, `hass/tests/test_social_recap.py`.
Case rows: `hass/tests/fixtures/skills/social/`.

Hass writes a caption the owner can copy and post himself. **Hass posts nothing.** These four skills are read-only:
approval `none`, edits none, no draft, no `yes <code>`, nothing posted, sent, saved or scheduled, and no file is attached.

| Skill | Ask it like | The caption comes from |
|---|---|---|
| `social.item` | "write a post for the honey", "caption for the plum jam", "post about the avocado" | `social_draft.build` (the same text as `post <id>`) |
| `social.hike` | "write a post for the Bluff Walk", "caption to announce Saturday's hike" | `social_draft.build_hike` (the same text as `post hike <id>`) |
| `social.maker` | "write a meet the maker post for Linn's" | `social_draft.build_maker` (the same text as `python3 hass/social_draft.py --maker KEY`) |
| `social.recap` | "write a post about how the Bluff Walk went", "caption from my hike recap" | `social_draft.build_recap` (`python3 hass/social_draft.py --recap EVENT_ID`) |

## social.recap: a caption from the saved recap

The caption is the title, the Pacific date (weekday, month, day and year; no time) and the recap the owner already saved for a
**completed** hike, word for word, then `#AvocadoShack #NorthCoastHikingClub`. Nothing else is added: no people count, route,
meeting point, thank-you or tag.

- A hike that is not completed (scheduled, cancelled, a merely past date) or has no recap: "That hike has no recap yet. Say how it went first."
  With no completed hike recap at all, Hass says so before asking which hike.
- A recap too long for 2200 characters is cut after its last `.`, `!` or `?` (followed by a space, a line break or the end) that
  fits: never mid-sentence, never an ellipsis. A very long single sentence is refused as too long.
- A `#` or `@` followed by a letter, digit or `_` anywhere in the title or the recap (also in the part that would be cut) is
  refused; nothing is stripped. Hass never makes up a tag or account.
- "say 40 people came" when the saved recap does not already say it: "Add that to the hike recap first, then ask me for the
  caption." A count already written in that hike's recap is just the unchanged caption; a mileage or date never counts.
  "tag the partners" or a typed `@name` / `#tag`: Hass adds no tags of its own and says so. Post, send or schedule: as above.
- `python3 hass/social_draft.py --recap EVENT_ID` prints the same caption as JSON (exit 1 with a reason on a refusal).

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
