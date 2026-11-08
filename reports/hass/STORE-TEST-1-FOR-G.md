# Monday at the store with Mike: the one-page plan for G

Plain-words copy of `reports/hass/STORE-TEST-1.md` (that file has every command and check). First written Sunday 2026-11-08 about 14:45, revised about 15:30 and again after two reviews. Nothing was sent, changed or published to write it.

## The most important thing first

**Hass cannot add a brand-new product to the real website from a text today.** The safety rules keep a product's brand and a maker's place for Graham only, so a new product is refused in live mode (the draft says so and offers no `yes`). I tested this with the real rules on a scratch copy; the answer is the same for the code that is running now and for the newest code. Everything else on your list works live: a photo on a product that is already on the site, a sold-out mark, a weekly special, a hike, a notice, an undo, a kind refusal.

Your choice (reply with one word). **Your earlier "go fully live" was about adding a new item, so it does not count for this smaller plan. Only your own word below turns anything live on:**
1. **LIVE** (recommended): Monday is live and public with a photo on a product already on the site, a sold-out mark, a weekly special, a hike, a notice, an undo and a refusal. **No brand-new product.** Saying LIVE means you accept exactly this list.
2. **PRIVATE**: Monday is private and includes a brand-new product with its photo, draft and picture, but nothing reaches the website.
3. **LATER**: wait until the rules are changed by whoever owns them so new products can go live safely. I have not changed or proposed to change any rule.

**If you do not answer, nothing goes live.** At 21:00 Sunday Hass stays on hold (it applies nothing, nothing public), the operator asks you once more, and Monday has no live visit; Mike can still see Hass answer `status` and `listing` and refuse things. A silence or a deadline never counts as yes. PRIVATE also needs your word.

## Where we are right now

- Hass is healthy and running, but it is set to **hold**: it applies nothing.
- The steps that let Hass change the real website (the GitHub key, the site copy, the Cloudflare setting, "go live") are **not done yet**. Only you can do them. Without them, live is not possible on Monday.
- Some of the newer skills (the restyled picture, the hike, special and notice skills) are not in the running copy yet. The older plain-words way works, so the test still works, with the photo shown as Mike took it.

## What Mike will do at the store (about 35 minutes)

1. Text `status`. Hass says it is ready. Then `photos to take`: Hass lists products that still have a stock picture.
2. Send one photo of one of them, say what it is and what the photo shows. Hass shows a draft and a picture. He types `yes` and the code. Hass says "Saved", then that it is on the website, with a picture.
3. Ask "Who grew it?" Hass answers from the site, or honestly says "I don't know".
4. Mark one thing sold out. 5. Add a real weekly special. 6. Add a real hike. 7. Change the notice.
8. Type `undo` and `yes` and the new code: the notice goes away.
9. Ask for something Hass should refuse (change the phone number, or add a new product). Hass says no kindly and changes nothing.

Rules for Mike: only true things (customers can see it); wait for the website message before the next `yes`; if anything looks wrong, text `stop changes`; do not send a message twice. In the photo words, say only what can be seen (not "organic" or "farm": Hass refuses those).

## What only you and Michael can do

- **You, tonight, only after you have answered LIVE (about 2 hours):** the GitHub deploy key, the Cloudflare setting, the site copy, then switch Hass to live (runbook steps 20 to 22; copy-paste commands in section 7 of the big file; the commands use `python3 -B -m hass.publish_live`, the older `publish_live.py` form does not work).
- **You, on the Mac mini, tonight:** add one line to the forwarder's config (`"gChat": ...`, your own chat, the same as on AgentOrange), quit and reopen Messages and BlueBubbles, one restart command, then text `problems` from your phone and see an answer in your own chat. Without that line your `problems` and `weekly` texts get no answer.
- **Michael, tonight, only after your LIVE answer (25 minutes):** text one tiny change, say `yes` with the code, wait for the picture, then `undo`; then one real photo for one product, `yes`, picture, then `undo`. This proves live, the photo and undo.
- **Michael, before Monday:** pick the real things (a product already on the site for the photo, the sold-out item, the special, the hike, the notice words). Photo with nobody in it, fine to be public.
- **Monday 07:15, you:** restart Messages and BlueBubbles on the Mac mini again, then text `problems`.

## Go or no-go (the operator checks at 21:00 Sunday and 08:00 Monday)

1. Live publishing works, a harmless change and its undo and the photo were seen working on the real site tonight, and the safety-rule rehearsal passed.
2. Hass is healthy: services running, nothing waiting, not paused.
3. The Mac mini answers: Mike's `status` gets a reply in 10 seconds or less, and your `problems` text is answered in your own chat.
4. The fast model is answering (not the slow backup), and Pillow is the right version.
5. Tests pass, a fresh backup is checked, and the last good website version is written down: `GOOD-SITE-COMMIT = ____________` (the operator fills this in).

Line 1 also needs your recorded LIVE answer. If you said LIVE and a line is red at 21:00, Monday is **private** (or live without the photo step if only the photo check is red). If you have not answered, Monday stays on **hold**.

## The stop buttons

| I want to... | Do this | Who |
| --- | --- | --- |
| Pause everything right now | Mike texts `stop changes` (`resume changes` undoes it) | Mike or you |
| Stop all changes (hold) | the operator runs K1 | operator |
| Go back to private mode | the operator runs K2, but **only if no change is half-way to the website** (the operator checks first; if one is half-way, use hold instead) | operator |
| Take back the last change | Mike texts `undo`, then `yes` and the new code | Mike |
| Put the website back to the good version | the K4 steps, using GOOD-SITE-COMMIT (or Cloudflare Pages, last good version, Rollback, for a quick look-fix) | you |

The operator can stop things any time. Only you put things back to live or touch the live site. **After putting the website back with K4, Hass stays on hold until you and the operator finish the "R1 to R4" steps together** (tested on practice copies for one change; not for several): it is not a Monday-during-the-visit job.

## We drop to private right away if

Hass says something is done when it is not; a change goes live that Mike did not approve; Hass invents a fact; the site does not show a change; the website message arrives with no picture; two replies in a row take over a minute; the Mac mini goes quiet for 5 minutes; or a photo shows a person or a receipt. (If a change is stuck half-way, hold comes first, not private.)

## If something breaks

- **Mac mini or iMessage down:** Mike waits (do not resend); you restart Messages, BlueBubbles and the forwarder; late replies say "Late reply to your message".
- **The model is slow:** Mike waits; `status`, `yes` and `undo` still work fast.
- **Picture will not restyle:** the photo goes up as Mike took it.
- **Saved but not on the website yet:** nothing reached the site. Tell Mike to wait. You either run the retry once, or the operator goes private, Mike texts `undo` and `yes` (that takes back only the stuck change), then you run `unblock`. Nothing else should be changed in private before that.
- **"May or may not be on the website":** hold first; no more changes of any kind. You look at the live page and tell the operator whether it is there. If the site is wrong, K4.

## Two more things for you to decide

1. If the live steps are not done by 21:00, run Monday in private mode (recommended; reply PRIVATE), or push the live test to a later day (reply LATER). If you do not reply, Hass stays on hold and nothing goes live.
2. Everything in a live visit is public. If you want a made-up hike or product, do it in private mode.
