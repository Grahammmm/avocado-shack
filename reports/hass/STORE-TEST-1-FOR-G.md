# Monday at the store with Mike: the one-page plan for G

Plain-words copy of `reports/hass/STORE-TEST-1.md` (that file has every command and check). Written Sunday 2026-11-08 about 14:45. Nothing was sent, changed or published to write it.

## Where we are right now

- Hass is healthy and running, but it is set to **hold**: it applies nothing.
- The steps that let Hass change the real website (the GitHub key, the site copy, the Cloudflare setting, "go live") are **not done yet**. Only you can do them. Without them, "fully live" is not possible on Monday.
- Some of the newer skills (the one-message add with the restyled picture, the hike, special and notice skills) are not in the running copy yet. The older plain-words way works, so the test still works, with the photo shown as Mike took it.

## What Mike will do at the store (about 35 minutes)

1. Text `status`. Hass says it is ready.
2. Send one photo of a real product, then say its name, who makes it and where. Hass shows a draft and a picture. He types `yes` and the code. Hass says "Saved", then "Now showing on theavocadoman.com".
3. Ask "Who grew it?" Hass answers from the site, or honestly says "I don't know".
4. Mark one thing sold out. 5. Add a real weekly special. 6. Add a real hike. 7. Change the notice.
8. Type `undo` and `yes` and the new code: the notice goes away.
9. Ask for something Hass should refuse (change the phone number). Hass says no kindly and changes nothing.

Rules for Mike: only true things (customers can see it); wait for "Now showing" before the next `yes`; if anything looks wrong, text `stop changes`; do not send a message twice.

## What only you and Michael can do

- **You, tonight (about 90 minutes):** the GitHub deploy key, the Cloudflare setting, the site copy, then switch Hass to live (runbook steps 20 to 22; the commands are copy-paste in section 7 of the big file). On the Mac mini: quit and reopen Messages and BlueBubbles, then one command (same section).
- **Michael, tonight (15 minutes):** text one tiny change, say `yes` with the code, wait for the picture, then `undo`. This proves live works and that undo works.
- **Michael, before Monday:** pick the real product (name, maker, town, a photo with nobody in it), the real special, the real hike (or skip it), the notice words.
- **Monday 07:15, you:** restart Messages and BlueBubbles on the Mac mini again.

## Go or no-go (the operator checks at 21:00 Sunday and 08:00 Monday)

1. Live publishing works and undo was seen working on the real site tonight.
2. Hass is healthy: services running, nothing waiting, not paused.
3. The Mac mini answers: Mike's `status` gets a reply in 10 seconds or less.
4. The fast model is answering (not the slow backup), and Pillow is the right version.
5. Tests pass, a fresh backup is checked, and the last good website version is written down: `GOOD-SITE-COMMIT = ____________` (the operator fills this in).

If any line is red at 21:00, Monday runs in **private mode**: Mike still sees his text turn into a draft and a picture, but nothing reaches the website.

## The stop buttons

| I want to... | Do this | Who |
| --- | --- | --- |
| Pause everything right now | Mike texts `stop changes` (`resume changes` undoes it) | Mike or you |
| Stop all changes (hold) | the operator runs the K1 command in the big file | operator |
| Go back to private mode | the operator runs K2 | operator |
| Take back the last change | Mike texts `undo`, then `yes` and the new code | Mike |
| Put the website back to the good version | the K4 commands, using GOOD-SITE-COMMIT (or Cloudflare Pages, last good version, Rollback, for a quick fix) | you |

The operator can stop things any time. Only you put things back to live or touch the live site.

## We drop to private right away if

Hass says something is done when it is not; a change goes live that Mike did not approve; Hass invents a fact; the site does not show a change; "Now showing" arrives with no picture; two replies in a row take over a minute; the Mac mini goes quiet for 5 minutes; or a photo shows a person or a receipt.

## If something breaks

- **Mac mini or iMessage down:** Mike waits (do not resend); you restart Messages, BlueBubbles and the forwarder; late replies say "Late reply to your message".
- **The model is slow:** Mike waits; `status`, `yes` and `undo` still work fast.
- **Picture will not restyle:** the product goes up with his own photo.
- **Publish fails:** Hass says "saved, not on the website yet". You run the retry or check the site by eye; if it stays stuck, private mode.

## Two things for you to decide

1. If the live steps are not done by 21:00, run Monday in private mode (recommended), or push the live test to a later day.
2. Everything is public. If you want a made-up hike or product, do it in private mode.
