# Real guest sign-up for hikes: what it needs, options, recommendation (HASS-CHAT-1, design only)

Status: **design only, nothing built.** G decides. Written 2026-11-09 for card t_d536279f after G's hike test.

## Where we are

- The hike page can show an RSVP button only when a hike has `rsvpEnabled: true`, but the live website has **no sign-up
  backend**: `docs/hass/FEATURES.md` says RSVP storage is not connected, and the static site shows "To join, ask at the Shack."
- The live content boundary (`hass/live_policy.py`) lets a hike go live from chat only with sign-up **off**.
- Since HASS-CHAT-1, a guest limit he texts ("maximum of six") goes on the page as words: *"Limited to 6 people. Ask at the
  Shack to save a place."* with sign-up off. People ask at the shop; nobody's details are collected anywhere.

## What a real sign-up needs

1. **A form backend** that accepts a sign-up for one hike: name, party size, and one contact (phone or email) the guest chooses.
2. **Private storage** of RSVPs, never in the public site repo or any generated file; retention (delete N days after the hike).
3. **What the owner sees**: in chat, "who's coming to Saturday's hike?" answers with first names and party sizes; no contact
   details in chat unless he asks for one guest.
4. **Capacity enforcement** at the backend (not the page): the last place is taken once; the page shows places left.
5. **Confirmation** on screen at once; any message (text or email) only if the guest ticked a box asking for one.
6. **Cancel**: a private link (or code) that cancels the guest's own place; the owner can cancel a guest from chat.
7. **No email or text without consent**: no marketing list; reminders only when asked for at sign-up.
8. **Privacy**: a short notice on the form (what is kept, for how long, who sees it); spam protection (rate limit + a hidden
   field, no third-party tracking captcha); the live boundary then allows `rsvpEnabled` only once the backend is proven.

## Options

| | What | Cost | Effort | Pros | Cons |
|---|---|---|---|---|---|
| **A. Ask at the shop (today)** | Limit written on the page, sign-up off | $0 | done | no personal data at all; nothing to break | no count of who is coming; people must come in or call |
| **B. Hosted form service** (e.g. a Google Form or Tally per hike, link on the page) | the form service stores RSVPs; Hass posts the link | $0 to ~$30/month | ~1 day | quick; proven spam handling | data at a third party; capacity is not enforced reliably; a link per hike; the live boundary must allow an outside link |
| **C. Own small backend** (the existing `community-server.py` RSVP code behind Cloudflare, private SQLite on the host) | real RSVP button, places left, cancel link | ~$0-10/month (existing host + Cloudflare) | ~1-2 weeks incl. privacy notice, tests, a live rehearsal | data stays ours; capacity enforced; chat can answer "who's coming" | a public endpoint to run and watch; needs the security review and G's publication approval |

## Recommendation

**Stay on A now; build C next if hikes regularly fill up.** A is honest and needs nothing more. B moves guest data to a third
party for little gain. C reuses code we already have (RSVP storage in `community-server.py`, the capacity checks in
`hass/ops/hikes.py`) and keeps the data private, but it opens a public endpoint, so it needs its own card, a security review,
and G's approval before anything is published.

G decides: **A** (keep as is), **B**, or **C** (open a build card).
