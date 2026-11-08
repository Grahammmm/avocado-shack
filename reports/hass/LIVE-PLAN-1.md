# HASS-LIVE-PLAN-1: how an approved chat change reaches the live site

Card t_a0a46444 · repo Grahammmm/avocado-shack · branch `rb/hass-live-plan-1` (candidate PR, code + tests + this report) · written against `origin/main` 0a8114c · 2026-11-08.
No live site, host.json, live state, key, Mac or credential was touched, and nothing was sent. Read-only look at GitHub metadata of `Grahammmm/theavocadoman-site` (commit list, check run, deploy keys, branch protection) to learn how it is deployed.

## Decisions from G (2026-11-08), recorded as given

1. **Mike's `yes` publishes the change to the live site, with undo.** No second approval, no daily batch. The existing safety rules still block risky edits (origin or organic claims, health claims, awards, endorsements, trail facts, prices, contact details, the 10-record limit); undo is allowed.
2. **Owners who may text Hass: Mike and G (two numbers).** Strangers get nothing.
3. **A photo that cannot be made house-style:** say so kindly and ask for a retake; Mike may approve using it as is, knowingly (D6 default). *Not part of this PR: no photo op is live-allowed here (see table, `product.set_photo` stays private), so this decision lives in the picture cards.*
4. **No supervised trial:** straight to Mike once the full test battery passes; G watches the problems log.
5. **Problems:** one line in each session report plus a weekly top 3 to G only. *Status: `problems` and `weekly` (G's chat) and `morning_report.py --for-g` already exist. Nothing sends the weekly top 3 on a schedule yet; that is a small follow-up card (a timer that queues `corrlog.weekly_line` to G's chat). I did not build it here.*

D4 of SKILLS-SPEC §6 ("live boundary: no change") is relaxed by decision 1 for exactly the skills in section C.

## Summary

* **The release engine already exists** (`hass/publish_live.py`, PUBLISH-1) and is fixture-tested. What was missing was not the machinery but (a) a live boundary that matches G's list (the old one was a deny-list that also let shop hours, notice and headline through), (b) a second owner number, (c) a plain "saved for Graham" outcome when a change is refused, (d) a one-line switch back to private mode and a one-command revert, and (e) a scratch-site test battery. All five are in the candidate PR.
* **Found and fixed on the way:** the runbook (steps 21–23) tells G to run `python3 hass/publish_live.py …`; that form failed with `ModuleNotFoundError: No module named 'hass'` (only `python3 -m hass.publish_live` worked). Fixed in the PR with a regression test. Also: when the release engine refused a change (limit reached, STOP, last change unsettled) Mike got only "I couldn't save that change"; he now gets the real reason in words.
* **What only G and Michael can do** is in `reports/hass/LIVE-STEPS-G-MICHAEL.md`.

## A. The end-to-end path, from `yes <code>` to the public page

How the site is deployed today (checked, read-only): `theavocadoman.com` is served by **Cloudflare Pages from the git repo `Grahammmm/theavocadoman-site`, branch `main`** (GitHub shows a `Cloudflare Pages: success` check on its one commit, "Initial published build … hass/sitegen.py --publish"). That repo holds only generated static files; it has no GitHub Actions, no deploy keys yet, and `main` is not protected. The avocado-shack repo (this one) has only the `check` CI workflow and no deploy. **The writer branch `hass/live` never leaves AgentOrange**: it is the local worktree `~/.local/share/hass/writer` holding the editable content (`hass/content/*.json`); only the generated files built from it are pushed to the site repo.

1. **Mike texts a change.** Mac forwarder → sealed envelope → receiver on AgentOrange → worker. The interpreter turns it into typed operations; the claims gate asks about any claim Mike did not state.
2. **Proposal.** `live_policy.check` runs first (section C). Allowed: Mike gets the change in words with the **full previous text** and "Reply yes <code> to put it on the website (it should show within a few minutes), or no <code> to cancel", plus a picture. Refused: plain refusal, saved privately (section C), no `yes` offered.
3. **`yes <code>`** (a bare `yes` is refused in live mode). The approval row is bound to sender, chat, change id, exact draft hash, base revision and expiry (`approvalTtlSeconds`); expired, duplicate, cancelled or stale approvals do nothing. The live policy is checked again at this point.
4. **Gate in `LiveEditor.apply`** (under one release lock): STOP file absent; no release still open; no earlier release record for this change; draft hash unchanged; **daily cap 10** (undo exempt); wait until the minimum interval (120 s) since the last attempt; policy again; the site checkout is clean, on the recorded head and equal to `origin/main`; and the **writer's build equals the site byte for byte** (otherwise "the website and Hass's copy differ; G must check"). Any failure: refused, website unchanged, nothing written.
5. **Writer commit.** A release journal entry (`intent`) is written first, then the single-writer editor applies the change and commits it on `hass/live` as `hass content: <change id>` (signed off).
6. **Build and checks** (from that commit, in a scratch folder): content validates; generated files are current; migration checks pass; `hass.tests.test_publish`, `test_content`, `test_style_no_commerce` pass; only the pages this kind of change should touch changed (`unexplained-diff` otherwise); **privacy scan** of every new byte and the commit message (emails, phone numbers, keys, home paths, loopback addresses, database names, chat ids, and now also G's numbers). Any failure: the site checkout is reset, journal `not-published`, Graham is alerted, nothing was pushed.
7. **Commit and push.** The changed files are written to the site checkout and committed as `hass live: <change id> (<code>)` (signed off); then `git push origin <commit>:refs/heads/main` over the site-only deploy key. Connect-level failures retry at 0/10/30/60 s; STOP is checked before each attempt; a timeout or unclear result is recorded `unknown`, never assumed.
8. **Deploy.** The push to `main` makes Cloudflare Pages build and publish the new commit (no step of ours). The site answers `cache-control: public, max-age=0, must-revalidate`, so the new page is served as soon as Pages finishes (usually a minute or two).
9. **Reply 1, immediately:** "Saved: <what changed>. I'll send a separate message about the website." It never claims the site changed.
10. **Verify, then reply 2.** The worker re-checks every second or so: it fetches up to 10 of the changed pages from `https://theavocadoman.com/…?hass=<id>` (no proxy, no redirects, 2 MiB cap) and compares SHA-256 with what was built. Match → state `live` → **"Your change is on the website now."** plus a picture. No match within `verifyMinutes` (15) → `unconfirmed`: "I sent that change to the website, but I can't see it there yet. Graham has been told." It can still settle to `live` later.
11. **If it fails or is only saved** (the website is unchanged unless stated):
    * Checks or commit failed, or push refused before sending: "That change is saved on my side but did not go on the website: <reason>. The website is unchanged. Graham has been told."
    * Push may have landed but cannot be proven: "I sent that change to the website, but I can't tell whether it arrived. It may or may not show. Graham has been told, and no other change will go on the website until this is sorted." The engine reads the remote until it proves delivery or proves non-delivery twice, 120 s apart.
    * Refused before starting (new): one plain line naming why — another change is going out; changes are paused; the last change is still being checked; today's limit is reached ("send it again tomorrow"); the website and Hass's copy differ — each ending "Nothing changed on the website."
    * Refused by the live table: "I can't put this on the website from chat: <reason>. Nothing will be published. I've saved it for Graham to look at, and he can do it by hand."
12. **Undo.** `undo` then `yes <code>` (from Mike's or G's chat; each owner can only take back their own changes, with or without a code, and the website answer goes to the chat whose `yes` released it, recorded in the release entry). It is a new, conflict-checked inverse change that goes through steps 4–10, is exempt from the daily cap, and is never blocked by the content table. The site ends byte-identical to before (checked in test 2). G's console version is `revert-last` (section E).

What is verified before the reply says "on the website now": the page bytes served by `theavocadoman.com` match the build. A screenshot is attached (live mode requires pictures to be working; see prerequisites in the steps file).

Known limits (not changed here): publishing runs inside the worker cycle and includes the 120 s minimum wait and the build checks, so a second message can wait a few minutes behind a publish; a G-chat reply that cannot be sent is dropped after two are waiting (so it never holds up Mike's).

## B. What only G and Michael can do

See `reports/hass/LIVE-STEPS-G-MICHAEL.md` (one page, plain words, copy-paste, what to check after each step). In short: create the site-only deploy key (G), add it on GitHub with write access (G), check two Cloudflare settings (G), clone the site and add the `release` block (G), set the owner numbers and `liveSite` (G), `adopt`/`baseline` (G), switch `approvals` to `live` (G), Michael's first change.

## C. The policy change

`live_policy.py` is now an **allow-list** (`LIVE`, one row per operation with the argument names it may carry). A change that is not in the table is refused and kept as a private proposal. On top of the table the old gates still apply unchanged: protected fields, protected sentences (origin/organic, health/awards/endorsements, trail facts, prices, contact details), 10 records.

| Skill (operation) | Live from chat? | Reason |
|---|---|---|
| Hide / restore a product (`product.hide`, `product.restore`) | **Live** | Changes visibility only; held products stay refused by the editor |
| Edit a product's description or category (`product.edit`, args `id description category` only) | **Live** | Free text, still claim-scanned; name, brand, producer, picture are not allowed args |
| Stock word, with the shelf-check day (`product.set_availability`, `product.clear_availability`, `store.confirm_selection`) | **Live** | A status word, not a number; the check day is the owner's own statement |
| Weekly specials (`specials.add/edit/remove/clear_expired`) | **Live, if no price** | A price in the deal line is a protected sentence, so "2 for $5" stays private (G's "prices" rule). Ask G if deal-line prices should be allowed |
| Hikes: add / edit / cancel (`hike.create/update/cancel`) | **Live, sign-up off only** | If the hike (before or after) has sign-up on, people are involved: private. Trail fields (`trailId`, distance, difficulty, duration, access note, meeting address) stay private |
| Maker "about" text (`maker.edit`, args `key story` only) | **Live** | Free text, claim-scanned; place, link and name are not allowed args |
| Undo (`history.revert`) | **Live** | Restores earlier content |
| Add a product (`product.add`), change its picture (`product.set_photo`) | Private | A new item carries a brand and maker; pictures cannot be claim-checked. Revisit with the picture cards |
| Add / hide / restore a maker, maker place or link or name | Private | Brands, producer places and links |
| Product brand, display brand, producer | Private | Brands and producers |
| Hike repeat / complete / recap / sample hikes | Private | Not in G's list |
| Club details | Private | Club fields are protected |
| Route ideas, trail facts | Private | Trail facts |
| Prices | Private | Prices; the content model cannot even hold one except in a special's deal line |
| Store phone, address | Private | Contact details |
| Home hero photo (`store.set_home_image`, `clear_home_image`) | Private | G's rule |
| **Shop hours, notice, headline, intro, story** | **Private for now** | **Open question for G.** These were live-allowed by the old deny-list but are not on G's list. They are claim-scanned like the rest; recommend adding them (one-line change in `LIVE`) |

A refused change gets the plain message above and **one row in the private backlog** (`reason policy`: what was asked, why, the exact steps). Nothing touches the writer branch (a private commit would make the writer differ from the site and block every later live change). Graham reads it with `python3 hass/skills/backlog.py list --state DIR --text`. A test fails if any new operation is not classified live or private.

## D. Owners: Mike and G, nobody else

* Setting `gIsOwner: true` (needs `gSenders` and `gChat`) makes G's own one-to-one chat a second owner chat. Without it nothing changes: one owner chat, G's number only reads `problems`/`weekly`. G's number can never also be one of Mike's.
* **A non-owner changes nothing and gets no reply** (tested for 13 message kinds across strangers, groups, G-while-not-owner, wrong sender in an owner chat).
* **A stranger cannot read or close an owner's open request** (tested: `no`, `cancel`, `yes`, an answer, `status`, `show`; the request is intact and the owner's own answer still joins it).
* **Each owner's `yes`, `no`, `undo`, `show` and open request belong to that owner's chat.** Mike's `yes` cannot publish G's change or the reverse; G's text never sees Mike's open question. Replies and the "on the website now" message go to the chat that asked; G's chat is text only (no picture). `pause`/`resume`, `status` and the daily interpreter cap are shared on purpose (G can pause everything).
* G's and Mike's numbers are both scanned out of anything published.

## E. Rollout and rollback

* **Rollout (decision 4):** G does the steps file; the test battery (section F plus the 72-message skills battery) passes; then Michael. G watches `problems`/`weekly`.
* **One-line switch back to private mode:** `python3 hass/host.py mode private --host ~/.local/state/hass/host/host.json && systemctl --user restart hass-worker`. Rewrites only `approvals` (file stays 0600, refuses and changes nothing if the result would not load). In `private` mode a `yes` saves to the writer branch only and the replies say "saved, not on the website yet". The site is not touched. `mode hold` stops applying anything. `mode live` is refused unless the release block, `liveSite`, pictures and previewer are in place. **Returning to live after a private period** needs G's adopt/baseline (the writer is ahead of the site), exactly step 21 of the runbook.
* **Fastest stop (no restart):** `touch ~/.config/hass/STOP`: refuses any publication (an in-flight push cannot be recalled).
* **One-command revert of the last live change:** `cd ~/.local/share/hass/runtime && python3 hass/publish_live.py revert-last --host ~/.local/state/hass/host/host.json`. It finds the newest change that reached the site and was not undone and puts it back through the normal release path (new commit; checks; one push; live check), refuses while STOP is present or a release is open, and tells Mike "Graham took your last change off the website." Run `status` a minute later. From the phone the same thing is `undo` then `yes <code>`. If the site itself is wrong and nothing else works: Cloudflare Pages → Rollback (G), then `resolve <id> --as reverted`.

## F. Test plan on a scratch site (never the live site)

`hass/tests/test_live_drill.py` builds, per test, a throwaway writer repo and 0700 state, a throwaway **bare git remote standing in for theavocadoman-site**, a clone of it as the site checkout, a fake page fetch that reads that remote, an injected clock, a real `Conversation` and the real `LiveEditor`. (Page build is the fixture build used by `test_publish_live`; the real build and its checks run at G's baseline step 21 and in `test_publish`.)

| # | Scenario | Checks |
|---|---|---|
| 1 | apply, publish, verify | proposal shows full previous text; `yes` → one push; remote page changed; reply 1 says "Saved" only; after reconcile state `live` and "on the website now" said once |
| 2 | undo | `undo` + `yes` → remote page byte-identical to before; two journal entries; message |
| 3 | publish failure | push refused → state `not-published`, remote and local site unchanged, "did not go on the website … unchanged … Graham has been told"; the next change is refused in words; (3b) a timeout is `unknown`, never "live" |
| 4 | refused risky edit | origin/organic edit → refusal text; `yes` cannot get round it; no push, no commit, no journal; one private backlog row |
| 5 | stranger | 5 texts × 3 stranger kinds → no reply, no change, nothing stored |
| 6 | G as second owner | G's yes publishes; every message to G's chat, none with a picture; Mike's yes cannot publish G's change; G's numbers are in the privacy scan |
| 7 | revert-last | site back to before; Mike told; draft marked undone; second call: nothing to revert; refused under STOP |
| 8 | switch to private | `mode` round trip keeps 0600 and validity; an invalid `live` leaves the file unchanged; private mode ignores `liveSite` |

Other new tests: `test_live_table.py` (every real operation classified; G's table exactly; real drafts of every allowed skill pass and the private ones are refused; plain reasons pass the voice check) and `test_live_owners.py` (13 tests, section D). Results (HASS_VOICE_STRICT=1): live_table 12 OK, live_owners 13 OK, live_drill 34 OK (includes inherited receiver cases), plus the existing live_policy/live_proposal/publish_live/host/conversation modules OK. Full-suite result: see the PR.

## G. Open items and honest limits

1. Shop hours/notice/headline/intro/story: decision for G (section C).
2. Deal-line prices in specials stay private; say so if G wants them live.
3. Prerequisite not checked by me: runbook step 19 (reply pictures reach the phone) — the live-audit of 2026-11-07 said they did not; live mode requires it.
4. The 72-message skills battery (SKILLS-SPEC §4.3) is the gate in decision 4; I did not run it.
5. The first `baseline` publishes everything currently on avocado-shack main that differs from the site's only commit (built from main c02e1eb): G must look before confirming (steps file, step 6).
6. Weekly top 3 to G on a schedule (decision 5) is not built; follow-up card.
7. Three of my own tool calls this run were refused by the command guard (inline interpreter forms); none changed anything; none retried.
