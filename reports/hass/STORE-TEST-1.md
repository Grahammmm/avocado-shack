# HASS-STORE-TEST-1: the live test with Mike at the store (Monday 2026-11-09)

Card t_fc2b6272 · repo Grahammmm/avocado-shack · design and checklist only: no code was changed, no live state touched, nothing sent. **Revision 3** (the first review returned five findings, answered in sections 0, 1, 2 (P-0b, P-7b, command forms), 4, 6 and the two appendices; the second review returned two more: this revision is delivered as a new docs-only PR, and silence from G never turns live on, see section 0, A).
Written Sunday 2026-11-08, first draft about 14:45 PST, revision about 15:30 PST. Everything marked **checked** was read or run on AgentOrange or in a disposable scratch copy while writing this (read-only: `git log`, `systemctl is-active`, `health.py`, a grep of one key in `host.json`, `--help` of each command named here, the two scratch scripts in the appendices). Everything marked **to check** is a pre-flight item for the operator.

G chose "go fully live": Mike adds things to the real theavocadoman.com by text and photo while standing in the store. The operator advised a private rehearsal first. This plan prepares for live, says plainly what live **cannot** do today (section 0, A), and says exactly when we drop to private on the spot (section 3) and what that costs.

## 0. Read this first

> **UPDATE 2026-11-09 (card t_9e6bce5b, HASS-LIVE-ADD-1): G decided that a new product may go live from chat. The table below now shows
> that row as allowed under rules, and Appendix A's rehearsal is `reports/hass/rehearse_live_policy.py` (output
> `reports/hass/rehearse_live_policy.out`: "add a new product" now ALLOWED, every still-private row REFUSED). The rest of this section
> is the 2026-11-08 text, kept as written, and its "NO-GO" statements about a new product are superseded by that decision (G's
> live-scope confirmation, P-0b and the other pre-flight items still apply).**

### A. The headline request is NOT possible live today: a brand-new product from chat is refused by the live boundary

G's wish was "an item added to the real website in real time by text and photo". The live content policy (`hass/live_policy.py`, line 21: protected `products.brand`, `products.displayBrand`, `products.producerKey`, `makers.place`, `makers.url`) refuses any live change that adds or changes a product's brand or a maker's place. Every new product has a brand, so a new product from chat cannot go on the real site; the draft says so instead of offering `yes`. **Checked** with the real op registry and the real policy in a scratch writer (Appendix A), at `main` (56c9070) and at the running runtime commit (0a8114c), same result:

| What Mike asks | Live policy result |
| --- | --- |
| add a new product (with its brand) | **ALLOWED since HASS-LIVE-ADD-1 (G 2026-11-09)**, under these rules: the brand, display brand, maker and town are in Mike's own words of that request (else Hass asks and drafts nothing); it comes with its own picture; every sentence gate (origin/organic, health/awards, trail facts, prices, contact), the 10-record limit and sign-up-off stay; undo always passes. *Written 2026-11-08 it was **REFUSED**: `protected field: products.brand` (and `displayBrand`).* |
| add a new maker with a place or web link | **ALLOWED only as part of a new product, with its name and town** (HASS-LIVE-ADD-1); the web link is still **REFUSED** (`protected field: makers.url`), a maker on its own is refused, and an existing maker's place or link is still refused |
| change the brand or producer of a product that already exists | **REFUSED** (unchanged): `protected field: products.brand` |
| put a photo on a product that **already exists** | allowed (only `image` and the picture words change) |
| ... but the picture words say "organic" or "farm" | **REFUSED**: `protected sentences: origin/organic` |
| mark sold out (shelf check), weekly special, hike, notice | allowed |
| change the store phone number | **REFUSED**: `protected operation: store.set_phone` |

So, until the policy owner admits a reviewed path for new products (a policy change; **not made or proposed to be made here**, and this plan does not weaken it):

- **LIVE new-item demonstration: NO-GO.** It is not part of the live script. It stays NO-GO until its actual approved runtime path is proven in a scratch LIVE-policy rehearsal (P-0b) and G confirms.
- What the live visit **can** show: a photo added to an existing product (the "photos to take" list), a sold-out mark, a weekly special, a hike, a notice, an undo, and the kind refusal (including a brand-new product refused, kindly, in live mode).
- What only **private mode** can show: the full new-item experience (photo, name, maker, draft, picture, `yes`), with nothing reaching the website. A private new-item rehearsal does **not** satisfy G's request for a live new item; it shows the experience only.

Decision for G (also in the FOR-G page), recommendation first:
1. **Live visit with an existing-product photo** (recommended): everything in section 1 except step 1P. Pro: really live, real photo on the real site. Con: no brand-new product.
2. **Whole visit in private mode, including a brand-new product** (step 1P). Pro: the complete new-item experience, zero public risk. Con: nothing reaches the site.
3. **Postpone the live new-item test** until the policy owner decides a live path for new products. Pro: the request can be met properly. Con: not Monday.

**G's answer is the live-scope confirmation (LSC).** The live visit in option 1 is **not** the live new-item demonstration G asked for; it is a smaller live scope (an existing-product photo and the other allowed changes above, no brand-new product). So it needs G's own explicit word, on purpose, for this scope:

- **LSC = G answers `LIVE` to the FOR-G page** (which lists the exact scope) or says the same in plain words to the operator, and the operator records it on the card with the time and G's words. Nothing else counts: not a deadline, not the operator's recommendation, not G's earlier "go fully live" (that was about a different scope, a new item).
- **Until the LSC is recorded, nothing live is enabled or published.** That means no `approvals: live`, no P-16 to P-19 or P-18b live change, no steps 20-22 side effects beyond what G does himself at the Mac, and Hass stays in its present mode (today: `hold`, which applies nothing).
- **No answer by 21:00 Sunday = no live visit on Monday.** Hass stays in `hold`. The operator reminds G once at 21:00 and once at 08:00; a later explicit `LIVE` can still enable live only if P-17 to P-19 and P-18b were already done and are green at the 08:00 go/no-go. A deadline never authorizes a live publication.
- `PRIVATE` (option 2) is also G's word. The operator does not switch `hold` to `private` for the visit on silence; with no answer Mike sees at most the read-only things (`status`, `listing`, `who grew this`, `problems`) and any refusal. The scratch rehearsal on the operator's side (P-0, nothing live, no phone) needs no answer and can be shown on a screen if G agrees on the day.
- If G answered `LIVE` and the checks later turn red, the drop to `private` (section 3) is already covered: it is non-public and safer than live, and G is told by 21:15.

### B. Where we really are (checked 2026-11-08 ~14:40 PST)

| Thing | State now | What it means |
| --- | --- | --- |
| Runtime on AgentOrange | detached at `0a8114c` (merge of PR 527, SKILLS-ITEMS-1) | `origin/main` is already ahead (`56c9070`, PR 532 SKILLS-STOCK-1). Moving the runtime is an attended restart. |
| Services | `hass-receiver`, `hass-worker`, `hass-health.timer`, `hass-backup.timer` all `active` | good |
| Health | `health.py` with the same flags as the 5-minute timer: `ok: true`, no problems, no info | good |
| Approvals mode in `host.json` | **`hold`** | nothing a person approves is applied at all right now (not even privately) |
| Interpreter | GPU router `http://127.0.0.1:8010`, model `qwen3.8:27b-thinkingcap-q6`, timeout 60 s; CPU fallback `qwen3.6:35b-a3b-64k` on Ollama, timeout 120 s | the CPU fallback has **never been exercised** (E2E-HIKE-1 says so) |
| Live publishing (runbook steps 20-22) | **not done**: no `~/.ssh/hass_site` key, no site checkout `~/.local/share/hass/theavocadoman-site`, no `release` block in `host.json`, no `publish.json` / `releases/` in the host folder, no `~/.config/hass/STOP` | only G can do these (GitHub deploy key, Cloudflare setting). Until they are done and proven, "live" is **not possible**. |
| Private mode with a result picture (runbook step 19) | not known to me | to check: ask G whether Michael ever got a picture back after `yes` |
| Newest backup | `hass-state-20261108T113006Z` | the timer makes one at 03:30; a fresh one is a pre-flight item |
| Docs named in the card | `LIVE-PLAN-1.md`, `LIVE-STEPS-G-MICHAEL.md` and an APPLY-TEST-1 report **do not exist** on `main` or on any pushed branch yet (t_a0a46444 still open). This plan stands alone; reconcile it with them when they land. | |

Which of the steps in section 1 work on the runtime as it is, and which need a pull request that is **still open** (all at 2026-11-08 ~14:30 PST):

| Script step | Works on today's runtime (`0a8114c`)? | Needs (open PR) |
| --- | --- | --- |
| Photo on an existing product | yes, the older path: Hass asks "which product is this photo for", draft, `yes`. The photo is stored as the original upright JPEG (E2E-HIKE-1 4c). | house-style picture: PR 504 HASS-NEWITEM-1 (and the SKILLS-PIC-2b branch, no PR yet). `hass/newitem_render.py` is **not on main**. |
| "Who grew this?" | yes: `listing <name>` and a plain question both answer from the saved site records and say "I don't know" otherwise | none |
| Sold out | yes, the older path: `store.confirm_selection` and `product.set_availability` are in the runtime | the `stock.*` skills are PR 532, in `main` but **not** in `0a8114c` |
| Weekly special | the specials ops are on main (PR 520); chat skills for specials are PR 529 | PR 529 |
| Add a hike | yes, plain words (E2E-HIKE-1) | skills version: PR 530 |
| Change a notice | yes, plain words | skills version: PR 531 |
| Undo | yes | none |
| Refused kindly | yes | none |

So "using the skills" means different things depending on the runtime commit R we freeze. Rule: **R is chosen once, by 18:00 Sunday, and never moved after 21:00 Sunday except to fix a NO-GO.** Moving R means a new detached runtime worktree, `runtimeCommit` updated, services restarted, and the whole battery (P-10) and P-0b re-run.

Decision for the operator at 15:00 Sunday (technical, not for G): say in the card which PRs (504, 525, 526, 529, 530, 531, 532) are merged by then and which R that gives. If the house-style picture is not in R, Mike's photo goes up as the plain upright photo and the script says so (step 1 variant B).

### C. How to run the commands in this file (checked)

- Run from AgentOrange. `python3 -B ~/.local/share/hass/runtime/hass/<tool>.py ...` works for `host`, `health`, `statebackup`, `editor`, `inbox` and `stagelog` (each has its own path bootstrap; `--help` run on this checkout).
- **`publish_live` is different.** `python3 .../hass/publish_live.py ...` fails with `ModuleNotFoundError: No module named 'hass'` (checked, even `--help`). The working form, the one `docs/hass/PUBLISHING.md` names, is the module form run from the runtime folder, and `--host` is **required** on every command:
  `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live <command> --host ~/.local/state/hass/host/host.json`
  Commands: `status`, `adopt [--from-remote]`, `baseline [--confirm HASH12]`, `retry <change id>`, `resolve <change id> --as live|reverted`, `unblock [<change id>]`. Output is one JSON line; exit 0 for `ok`, `adopted`, `preview`, else 1. Below it is written out in full every time and called **PL**.
- The Mac commands use `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py {check,status,ackcheck,serve} --config <config>` (`--help` checked).

## 1. THE SCRIPT (what Mike and G do, in order)

Setting: Mike stands in the store with his phone, Hass is the business Messages account. G is beside him or on the phone with the operator. Mike only ever texts Hass; he never types a command he does not see in this list. **Live visit = steps 0, 1L, 2 to 9. Step 1P (new product) is private mode only.**

Ground rules for the visit, said to Mike first, in these words:
1. "Everything we do goes on the real website for real customers to see. Only say true things."
2. "After you say `yes`, wait for Hass to say it is showing on the website before you say the next `yes`. That takes one to three minutes."
3. "If anything looks wrong, text `stop changes`. That stops everything. You cannot break anything with that."
4. "If Hass takes more than a minute, do not send it again. Wait. Hass will answer."

What Hass should answer is described by shape, not exact words: the exact sentences come from `docs/hass/VOICE.md` and are confirmed in the scratch rehearsal (P-0). The **pass test for every reply** is the same: plain everyday words, no codes except the one to type after yes/no/undo, one clear next step, and it never says "done", "live" or "saved" before that is true.

Time budget: about 30 to 40 minutes for the changes (each live change waits for the previous one to show: minimum 2 minutes between two publishes, up to 15 minutes to confirm). Daily cap for live changes is 10; this script uses 5 (steps 1L, 3, 4, 5, 6); undos do not count.

Step 0. **Hello.**
- Mike sends: `status`
- Hass: a thumbs-up on his message if tapbacks are on (otherwise nothing), then one short plain reply: everything is ready, nothing waiting for his yes, and he still needs to do today's shelf check.
- Pass: reply within about 10 seconds; no technical words. This is also the go/no-go round trip (section 3, check C).

Step 1L. **Add a photo to a product that is already on the site** (the live version of "an item with a photo"). Mike first sends `photos to take`; Hass lists up to five products that still show a stock picture. He picks one that is really on the shelf. Photo: one photo, upright, JPEG or PNG, nothing else in the frame (no faces, no receipts, no price tags, no private places), one that he is happy to have public.
- Mike sends: the photo alone (a caption is not read as a command).
- Hass: one question: "Which product is this photo for, and what does it show? A few words is fine."
- Mike sends one message, for example: `It's for the Hass avocado. A ripe avocado cut open on a wooden counter.` (the product's name as the site shows it; say only what can be seen; the words organic, farm, local or any health word make Hass refuse, see section 0)
- Hass: a draft in shop words (which product, the new photo, the picture words), with a preview picture of the page, and "Reply yes <code> to put it on the website (it should show within a few minutes), or no <code> to cancel." The code must be typed (`yes a1b2`, not a bare `yes`).
- Mike checks the picture, then sends: `yes <code>`
- Hass: first "Saved" (and nothing about the website yet). Then, in a separate message, that it is on the website now, with a picture of the live page. If the picture is missing, that is a drop-to-private trigger (section 3).
- G opens theavocadoman.com on a phone and finds the product with the new picture.
- Variant B (no house-style picture in R): the draft preview shows the original photo, upright, with no location or camera data. Say to Mike: "this is your own photo as taken; the restyled version comes later."
- The undone photo file stays in the site repository, unused (checked in IMPLEMENTATION.md: "the committed photo file stays, unreferenced"), so choose a photo that is fine to be public.
- **Status of this step on the live path: policy allows it (Appendix A, S1c) but the full chain (staged photo, draft, live release, picture, undo) has not been run live.** It is proven by P-0b (policy) plus P-18b (one real photo, shown and undone the night before). If P-18b is red, drop step 1L from Monday's live script; do not improvise it.

Step 1P. **New product with a photo: PRIVATE MODE ONLY** (not part of the live visit; see section 0, A).
- Mike sends the photo alone, then one message: `It's a new product, the Test Orchard quince, brand Test Orchard. A bowl of quinces on a wooden counter.` (COMMANDS.md: a new product needs one brand.) Hass asks at most one more question for a missing fact, then drafts it; `yes` applies it to the private working copy only. In live mode the same message gets a draft that ends with the kind refusal instead of a `yes` line: that is step 8b, and it is the honest answer to "can he add a new item live?" today.

Step 2. **"Who grew this?"** (reads only, changes nothing)
- Mike sends: `Who grew the Hass avocado?` (use the product he just gave a photo)
- Hass: answers only from what is on the site: the maker's name and town. If the site does not say who grew something, it says "I don't know who grew it" and asks what to say. Pass = no invented farm, no "organic", no guess.
- Mike then sends: `listing Hass avocado`
- Hass: "This is from my saved copy, not a live look at the website:" then its name, status, place. Pass = anything not saved reads "nothing yet".

Step 3. **Mark one thing sold out.** Pick something that really is sold out, or that Mike will put back at the end.
- Mike sends: `I checked the selection today: the eggs are limited and the sourdough is sold out.` (real names)
- Hass: a draft saying back exactly those words, which products change, and that today's shelf check will be recorded. If today's check is missing it may first ask "is the shelf list right for today?": Mike answers with a bare `yes` (the only bare yes in the script) or tells it what is different.
- Mike sends `yes <code>`; waits for "on the website". The site shows "Selection last checked by Michael on <today>" and the words on the cards. (Live policy: allowed, Appendix A S3.)

Step 4. **Add a weekly special.** A real one.
- Mike sends: `Add a weekly special: Fresh bread Friday, a free sample with any cheese, through Saturday.` (real title, real deal line, last day within 31 days; no links or phone numbers; a price only in the deal line, exactly as typed. Live policy refuses prices elsewhere.)
- Hass: draft with the title, the deal line and the last day written as people say it ("through Saturday"), then yes, then showing.
- Pass: the "This week's specials" box shows it; it disappears itself after its last day.

Step 5. **Add a hike.** A real hike, or skip this step (see section 8, item 2: undoing an added hike leaves a public "cancelled" hike card).
- Mike sends: `Post a hike at Cass Hill on Saturday at 9am, meet at the trailhead gate.`
- Hass: asks only what is missing (for example the day if it is not clear), then a draft: title, day and time in plain words, meeting point. Hass never makes up difficulty, distance or trail facts. (Live policy refuses distance, difficulty, duration, access notes and meeting addresses; the meeting point in words is allowed, Appendix A S5. E2E-HIKE-1 saw an invented seat count once: Mike reads the draft and says `no <code>` if anything is there that he did not say.)
- Mike sends `yes <code>`; waits for "on the website".

Step 6. **Change a notice.** Keep it true and short (160 characters, last day today up to 60 days ahead).
- Mike sends: `Put a notice on the home page: "Come say hi, we are testing a new way to update the shop", until 2026-11-10.`
- Hass: draft with the old notice (if any) and the new one, the last day in plain words; yes; showing. The notice appears at the top of the home page. This must be the **last** change, because step 7 undoes it.

Step 7. **Undo one change.**
- Mike sends: `undo`
- Hass: a draft that takes back the most recent change (the notice), in shop words, with a new code. (`history` shows the last five changes but no codes; a bare `undo` takes the latest.)
- Mike sends `yes <new code>`; Hass says saved, then showing; the notice is gone from the home page. Undo is exempt from the daily cap but not from STOP.
- If Mike wants to also take back a sold-out word at the end: `stop showing the sourdough as sold out` (draft, yes). Undoing the shelf check itself is refused if a later edit touched the same detail ("undo the newer one first").

Step 8. **A mistake, refused kindly.** The point is to show Mike that Hass says no gently and changes nothing. In live mode the refusal replaces the `yes` line of the draft (checked, `conversation.proposal_text`): Mike sees what would change, then the refusal, and there is no code to type.
- 8a. Mike sends: `Change the store phone number to 805 555 0100`
  Hass: shows the change it understood, then "I can't put this on the website from chat: it is a kind of change only Graham can make. Nothing will be published. Graham can do it by hand." Nothing changed.
- 8b. Mike sends: `Add a new product: Test Orchard quince, brand Test Orchard` (with a photo if he likes)
  Hass: a draft, then "...it changes something only Graham can change. Nothing will be published." This is today's honest answer for a new product in live mode; G can say "new products still go through Graham while we are testing".
- 8c. If time: `Put the Hass avocado at $2 each` → Hass says the site shows no prices and nothing changed; or `make the hikes better` → Hass asks one short question and changes nothing.
- Pass: no technical word, no "error", no blame.

Step 9. **Close.** Mike sends `did it work?` Hass answers "Last change:" in plain words (undone). G sends `problems` from G's own phone in G's own chat (needs `gSenders`, `gChat` on both AgentOrange and the Mac, P-7 and P-7b) and reads the last ten problem moments. Then the operator makes the end-of-visit state decision (section 4).

Not in the script on purpose: voice notes (not understood yet), more than one photo per message, anything with a price except a special's deal line, hike photos (Hass only attaches photos to products), a brand-new product or maker (section 0).

## 2. PRE-FLIGHT

Who: the **operator** runs these on AgentOrange unless a line says **G (Mac)** or **G**. Two passes: the night before (Sunday 19:00-21:00) and the morning of (Monday 07:00-08:00). Each item has a command and an expected result. A red result is a NO-GO for that item until fixed; do not skip and do not repair by guessing. **P-16 (approvals `live`) and P-17 to P-19 and P-18b are not started until the LSC (section 0, A) is on the card:** they put a real change on the public site. Paths: `R` = `~/.local/share/hass/runtime`, state = `~/.local/state/hass/state`, host file = `~/.local/state/hass/host/host.json`, site = `~/.local/share/hass/theavocadoman-site`. **PL** = `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live` (section 0, C); `--host ~/.local/state/hass/host/host.json` is always written out.

| # | Check | Command | Expected | Night | Morning |
| --- | --- | --- | --- | --- | --- |
| P-0 | Script rehearsed on a scratch copy (no live, no phone) | the same method as HASS-E2E-HIKE-1: scratch writer + scratch state + synthetic owner, real code at R, real GPU interpreter; send the messages of steps 0 to 8, with a photo for 1L | each step ends as section 1 says; replies pass `voice.check`; no code path says "live" before it is | yes | - |
| P-0b | **Live-policy rehearsal at R: the script's changes pass, the new product is refused** | in the scratch checkout of R from P-10: `python3 -B ~/agent-work/hass-store-test/rehearse_live_policy.py ~/agent-work/hass-store-test-R` (script: `reports/hass/rehearse_live_policy.py` in the checkout; the version in Appendix A is the 2026-11-08 original; scratch writer and state in a temp folder, no network, no live files) | the lines of `reports/hass/rehearse_live_policy.out` exactly (HASS-LIVE-ADD-1: S1 and S1a, the new product, ALLOWED; S1b to S1b5, S1e to S1i, S6, S8, S1c to S1d REFUSED; S3 S4 S5 and the undo S9 ALLOWED; last line `ROWS OUT OF LINE: none`; the script exits 1 otherwise). The older nine-line output of the first version of this script is kept in Appendix A for history. Any `PREPARE-` line, or S1c not ALLOWED, = **NO-GO for the live photo step**; any change in S1 = tell G (the boundary moved: the new-item decision in section 0 must be redone). Dates in the script are Monday's; edit them to rehearse on another day | yes | - |
| P-1 | Runtime version | `git -C ~/.local/share/hass/runtime rev-parse HEAD` and `git -C ~/.local/share/hass/runtime status --porcelain` | HEAD equals `runtimeCommit` in `host.json` and the agreed R; second command prints nothing | yes | yes |
| P-2 | R contains what the script needs | `git -C ~/.local/share/hass/runtime merge-base --is-ancestor <merge commit of the PR> HEAD` for each PR we rely on | exit 0 for each (no output); anything missing is written on the card and the script step is shortened | yes | - |
| P-3 | Host config valid | `python3 -B ~/.local/share/hass/runtime/hass/host.py check --host ~/.local/state/hass/host/host.json` | one JSON line `ok`; exit 0 | yes | yes |
| P-4 | Services up | `systemctl --user is-active hass-receiver hass-worker hass-health.timer hass-backup.timer` | four lines `active` | yes | yes |
| P-5 | Services survive a logout/reboot | `loginctl show-user $USER -p Linger` | `Linger=yes`; if `no`, tell the operator: after a reboot nothing starts until someone logs in (support doc: unmeasured) | yes | - |
| P-6 | Health, the same flags as the timer | `python3 -B ~/.local/share/hass/runtime/hass/health.py --state ~/.local/state/hass/state --backups ~/.local/state/hass/backups --writer --model http://127.0.0.1:11434 --host-dir ~/.local/state/hass/host` | `"ok": true`, `"problems": []`, exit 0 (this is what it printed at 14:40). `info` may list `paused`: a paused system is a NO-GO until Mike sends `resume changes` | yes | yes |
| P-7 | Owners and G's own chat set on AgentOrange (without printing numbers) | health `settings` check passes in P-6. **G** opens `~/.local/state/hass/state/config.json` privately and confirms `settings`: `ownerSenders` = Mike's number, `ownerChat` = the one-to-one chat with Mike, `gSenders` = G's number (never also an owner), `gChat` = G's own one-to-one chat (never Mike's, never a group), `approvalTtlSeconds` long enough for Mike to read (3600 in the runbook). Then three live texts: Mike's phone gets a reply; a third phone gets no reply and no draft | Mike's `status` answered; the third phone silent. G's `problems` is tested in P-7b, because it needs the Mac too | yes (**G**) | - |
| P-7b | **G's problems chat works end to end** (needs the same `gChat` on the Mac, LIMITS.md "Problems log": the forwarder carries that chat only when its own config also has `gChat`) | **G (Mac)**: in a private editor (not shell history) add one key to `~/Library/Application Support/HassForwarder/config.json`: `"gChat": "iMessage;-;<G's address>"`, the same text as `gChat` on AgentOrange, not equal to `ownerChat`, one-to-one only; keep mode 600; add nothing else (the key set is closed; an extra key makes the forwarder refuse its config). Then `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py check --config ~/Library/Application\ Support/HassForwarder/config.json` and `launchctl kickstart -k gui/$(id -u)/com.avocadoshack.hass-forwarder` and `check` again. Then **G texts `problems`** to the business account from G's own phone | `{"reachable":2}` before and after the restart; within about 15 s G's own chat gets a plain-text answer (the last problems, or "nothing yet"); **nothing** appears in Mike's chat; Mike's `status` still answers in 10 s or less. Hass answers only G's own chat, only as text, and never any other chat: do not add other chats. If G's chat stays silent: the usual cause is `gChat` missing or different on one side; fix the Mac or AgentOrange value (restart `hass-worker` after changing `gChat` on AgentOrange); a red P-7b does not stop the live changes but the problems log is then read by the operator only (section 5, item 3) and the card says so | yes (**G**) | `check` again after the 07:15 restart |
| P-8 | Interpreter on the GPU route | `curl -s -m 5 http://127.0.0.1:8010/v1/models` and `nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv` | the router answers with a model list that includes `qwen3.8:27b-thinkingcap-q6`; GPU memory shows the model loaded. (If the router has no `/v1/models`, use the router's own status page; do not restart it.) | yes | yes |
| P-9 | CPU fallback available (not proven) | `ollama list` and the P-6 `--model` check (it already tests `/api/tags`) | `qwen3.6:35b-a3b-64k` is listed; health has no `model` problem. State plainly in the go/no-go notes that fallback has never been run: if the GPU fails, replies take 25-90 s | yes | yes |
| P-10 | Full test battery passes at the exact R | in a separate scratch checkout, **never** the runtime worktree (a dirty runtime makes the host refuse to start): `git -C ~/.local/share/hass/avocado-shack worktree add --detach ~/agent-work/hass-store-test-R <R>` then in it `python3 -B hass/acceptance.py` and `python3 -B -m unittest discover -s hass/tests -t .` (about 20 minutes serial; CI splits it in four shards) | `acceptance.py` prints no `fail`; unittest ends `OK` with 0 failures and 0 errors. Skips are listed on the card. Keep the worktree until P-0b is done, then `git worktree remove` | yes | - |
| P-11 | Pillow at the pinned version | `~/.local/share/hass/venv/bin/pip show Pillow` and `systemctl --user cat hass-worker` | `Version: 12.0.0`; and the service's `ExecStart` really uses `.../venv/bin/python3` (the template in `deploy/hass` still says `/usr/bin/python3`: PILLOW-HOST.md step 3 must have been done, and the worker restarted afterwards) | yes | - |
| P-12 | Picture guard test | from a scratch checkout: `~/.local/share/hass/venv/bin/python3 -B -m unittest discover -s tests -p test_pillow_ci.py -v` | `OK`. (If R has no house-style picture code this guard may not exist; note it and use variant B of step 1L.) | yes | - |
| P-13 | Mac forwarder and BlueBubbles up | **G (Mac)**: `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py check --config ~/Library/Application\ Support/HassForwarder/config.json` and `launchctl print gui/$(id -u)/com.avocadoshack.hass-forwarder` | `{"reachable":2}`; the second shows the agent loaded and running. If tapbacks are on: `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py ackcheck --config ~/Library/Application\ Support/HassForwarder/config.json` shows `"tapbackPossible": true` | yes | yes |
| P-14 | The 2026-11-08 lesson: restart Messages and BlueBubbles before the day | **G (Mac)**: quit Messages and BlueBubbles; open Messages first, wait until it shows the business account signed in; then open BlueBubbles, wait until it shows connected; then `launchctl kickstart -k gui/$(id -u)/com.avocadoshack.hass-forwarder`; then repeat P-13 and P-7b's `problems` text. (Source: the card text, not a repo document; no write-up of that incident was found. Operator: please link it here.) | `{"reachable":2}` after the restart; do it Monday 07:15 even if Sunday looked fine, then do not touch the Mac again unless something breaks | yes if it failed | **yes, always** |
| P-15 | A real round trip, fast | Mike texts `status` from his phone; the operator reads the stage log: `python3 -B ~/.local/share/hass/runtime/hass/stagelog.py ~/.local/state/hass/host/stages.jsonl` (add the Mac's `spool/stages.jsonl` after copying it over by Taildrop for the full picture) | thumbs-up (if on) and one reply in 10 s or less; `webhook-in` or `accepted` present; `reply-pulled` follows `reply-queued` within a few seconds | yes | yes |
| P-16 | Approvals mode and the stop file | `grep -o '"approvals": *"[a-z]*"' ~/.local/state/hass/host/host.json` and `ls ~/.config/hass/STOP` | Sunday night after the harmless change: `"approvals": "live"`; `ls` says no such file | yes | yes |
| P-17 | Live publishing set up (G, runbook 20-22) | steps 20, 21, 22 of `docs/hass/MAC_RUNBOOK.md` (copy-paste list in section 7); then `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live status --host ~/.local/state/hass/host/host.json` | JSON with `"result": "ok"`, the live baseline present, `"open": []` (no open release), daily-cap usage shown | yes (**G**) | status again |
| P-18 | Live publish proven with a harmless change | Sunday ~20:00, **G and Mike** together: Mike texts one tiny home page wording change (the runbook suggests the headline; a one-word change to the intro is smaller), `yes <code>`; wait for "on the website" with a picture; G looks at the site on a phone; operator runs the P-17 `status` command | "Saved", then the website message, picture present, site shows it, `"open": []` | yes | - |
| P-18b | **The photo path proven live** (only if the live visit keeps step 1L) | right after P-19: Mike sends one real photo for one product from `photos to take`, answers the question, `yes <code>`; wait for the website message and picture; G looks at the product on a phone; then Mike texts `undo`, `yes <new code>` and G sees the old picture back; status `"open": []` | the new picture on the site, then the old one back, no open release. Red = step 1L is dropped from Monday's live script | yes (**G + Mike**) | - |
| P-19 | Revert of the last live change proven | right after P-18: Mike texts `undo`, then `yes <new code>`; wait for the website message; G looks at the site | the wording is back exactly as before; `"open": []`. This is the verified revert; it uses the same release path, so it is exempt from the daily cap but not from STOP | yes | - |
| P-20 | Fresh backup of Hass state, verified | `python3 -B ~/.local/share/hass/runtime/hass/statebackup.py create --state ~/.local/state/hass/state --out ~/.local/state/hass/backups`, then `python3 -B ~/.local/share/hass/runtime/hass/statebackup.py list --out ~/.local/state/hass/backups` and `python3 -B ~/.local/share/hass/runtime/hass/statebackup.py verify <newest hass-state-... folder>` | `create` reports a new folder (`busy`: retry later; `unsettled`: `editor.py recover` after `stop changes`, then retry); `verify` says `ok`; the folder's `complete` is true | after P-19 | 07:45 again |
| P-21 | Known-good site commit written down | `git -C ~/.local/share/hass/theavocadoman-site rev-parse HEAD` and `git -C ~/.local/share/hass/theavocadoman-site ls-remote origin refs/heads/main` | both print the same 40-character commit. The operator writes it on the card as **GOOD-SITE-COMMIT** (a commit id is not a secret) and in the FOR-G page. Written **after P-19**, so it is the site with the harmless change undone | after P-19 | check it still equals the remote's main |
| P-22 | Host config backed up before any edit | `cp -p ~/.local/state/hass/host/host.json ~/.local/state/hass/host/host.json.bak-store-test` | file exists, mode 600 (`stat -c %a`) | yes | - |
| P-23 | Site is up and unchanged | `curl -sI https://theavocadoman.com` | `HTTP/2 200` (or 301 then 200) | - | yes |
| P-24 | Nothing is stuck | `python3 -B ~/.local/share/hass/runtime/hass/inbox.py status --state ~/.local/state/hass/state` and the P-17 `status` command | inbox: none pending; publishing: `"open": []`; STOP absent | yes | yes |
| P-25 | The GPU is quiet | ask the fleet operator to hold bulk local-worker jobs from 08:30 to 11:00 Monday (a request, not an action here); then `nvidia-smi` | no other job generating when the visit starts. A Hass call that lands behind a fleet generation waits 3-9 s and can wait about 55 s before the CPU fallback fires (INTERP-OPENAI-1) | - | yes |

A read-only extra the operator can run any time: `bash ~/.local/share/hass/runtime/scripts/hass/live_selftest.sh --synthetic-only` (synthetic data only; restarts and sends nothing; syntax checked). Without `--synthetic-only` it also reads services, timers, health and disk and prints one `PASS|WARN|FAIL` line each.

## 3. GO / NO-GO

**GO LIVE only if all five are green at 08:00 Monday** (the same five lines go on the card):
1. **Setup**: **the LSC is on the card (G's explicit `LIVE` for the scope in section 0, A; silence never counts)**, P-17 and P-18 done, P-19 proven (live publishing works and the revert was seen working on the real site), P-0b clean at the frozen R, and, if step 1L stays, P-18b proven; STOP absent, no open release, daily cap not used up (at least 6 left). **A live brand-new product is NO-GO regardless** (section 0, A): it is not in the live script, and no one promises it to Mike.
2. **System**: P-1 to P-6 and P-24 green (R frozen and clean, services active, `health.py` ok and not paused, inbox empty).
3. **Phone**: P-13 `{"reachable":2}` after the Monday restart (P-14) and P-15 a `status` reply from Mike's phone in 10 s or less; owners right (P-7); G's `problems` answered in G's chat (P-7b; if red, the operator reads the problems log and the card says so).
4. **Model and pictures**: P-8 GPU route answering, P-9 fallback present, Pillow 12.0.0 (P-11); in the last 10 interpreter calls (audit script in section 5) none fell back and the slowest was under 15 s.
5. **Safety net**: P-10 battery green at the same R, P-20 backup verified this morning, P-21 GOOD-SITE-COMMIT recorded and equal to the remote, and G and the operator both reachable by phone for the whole visit.

**DROP TO PRIVATE ON THE SPOT** (operator or G, no discussion; section 4, K2, and **only after reading the release rule below**) if any one of these happens during the visit:
- Hass says something is done, saved or live when it is not, or the site does not show a change that Hass said is showing.
- A change is applied that Mike did not approve with its code, or it touches something Mike did not name.
- A reply or draft contains a fact Mike did not give (a farm, "organic", a price, a distance, seats) and Mike's `no` does not stop it.
- A release goes `not-published`, `unknown` or `unconfirmed`, or the website message arrives without its picture.
- Two replies in a row take longer than 60 seconds, or two in a row run on the CPU fallback.
- The Mac is silent for 5 minutes (no reply to `status`) after one restart of Messages and BlueBubbles, or a stranger gets a reply.
- A photo with a person, a receipt or a private place is about to be published.

**Release rule for any drop** (checked in `host.make_worker`: only `live` mode runs the release engine; `private` mode uses the plain editor, which neither checks nor reconciles an open release, and every change it applies moves the private writer away from what the release engine expects): before anything else run the P-17 `status` command.
- `"open": []`: K2 is clean.
- `not-published`: K2, then settle it as in section 6 (undo it privately, then `unblock`) **before** any other demonstration change.
- `pushing`, `unknown` or `unconfirmed`: **use K1 (hold), not K2.** Nothing further is applied, the writer stays exactly as it is, and G settles the release (sections 4 and 6). The visit can go on only with things that change nothing: `status`, `listing`, `who grew this`, `problems`, and step 8's refusals.

What **private mode** means for Mike (when the release rule allows it): nothing changes on the website any more. Hass still reads his texts, makes drafts and result pictures, and `yes` applies to the private working copy, so he can finish the demonstration (and, now, show step 1P). Tell him: "These changes are not on the website. Graham will decide later what to publish." Changes made in private are **not** published later by themselves; getting them on the site afterwards is an attended step by G (the `baseline` path in runbook step 21) or they are left as the rehearsal record. Do not promise Mike they will appear. To go back to live after a drop, G only: settle any open release first (sections 4 and 6), re-run P-4, P-6, P-13, P-17 `status`, then switch back.

**Pause without dropping** (Mike's own brake): `stop changes` stops every approval from applying; `resume changes` lets them apply again and never applies a waiting draft by itself. Use it when someone just needs a minute.

## 4. THE KILL SWITCH AND ROLLBACK

All commands run on AgentOrange unless said. Nothing here deletes a backup or a journal, edits a journal by hand, or force-pushes. **PL** = `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live`, always with `--host ~/.local/state/hass/host/host.json`.

| | What | Command | Who | Time | After it, check |
| --- | --- | --- | --- | --- | --- |
| K0 | Instant brake from the phone | Mike (or G, from beside him) texts `stop changes` | Mike, G | seconds | `status` says changes are paused; `resume changes` undoes it |
| K0b | Instant brake on publishing | `touch ~/.config/hass/STOP` (undo: `rm ~/.config/hass/STOP`) | operator | seconds, no restart | the P-17 `status`; careful: STOP **before a push** holds the saved release **open** as `not-published`, and an open release refuses every later live change until G settles it (section 6). STOP **during** a push cannot recall it. Use K0 first when you can |
| K1 | **Stop all changes** (approvals hold) | `sed -i 's/"approvals": *"[a-z]*"/"approvals": "hold"/' ~/.local/state/hass/host/host.json` then `systemctl --user restart hass-worker` then `python3 -B ~/.local/share/hass/runtime/hass/host.py check --host ~/.local/state/hass/host/host.json` | operator (G may ask for it) | about 10 s | `check` says ok; the P-16 grep prints `hold`; mode is still 600; Mike's `yes` now applies nothing; chat still answers. K1 does not settle an open release; it only freezes everything where it is |
| K2 | **Return to private mode** (read the release rule in section 3 first) | the same `sed` with `"private"` instead of `"hold"`, then `systemctl --user restart hass-worker` and the `host.py check` | operator | about 10 s | grep prints `private`; a small test change shows a draft, a result picture, **no** website message. K2 does **not** settle an open release |
| K3 | **Revert the last live change** | Mike texts `undo`, then `yes <new code>` (a bare `undo` takes the latest change; the draft says in plain words what comes back). Then the operator checks `python3 -B ~/.local/share/hass/runtime/hass/editor.py history --state ~/.local/state/hass/state --limit 3` and the P-17 `status` | Mike types it, operator watches | 1-3 min (a live publish) | the site shows the earlier text; `"open": []`; `history` shows it undone. Refused if a later edit changed the same store detail ("undo the newer one first") or while a release is open. Undoing an added hike leaves a visible "cancelled" card, not an empty page |
| K4 | **Restore the site to a named commit** (GOOD-SITE-COMMIT) | by hand, by G or by the operator while G watches, **only if K3 cannot fix it** and **only for a release that is closed or has been seen on the site**; see the state table and steps below | G (live site) | 5-10 min plus the site's own deploy | the site shows the good version; then the recovery steps R1 to R4, which are attended and **not** during the visit. K4 never resumes live by itself |
| K4b | Fastest visual rollback (if K4 is too slow) | G in Cloudflare Pages: the project's deployment list, the last good deployment, Rollback (label UNVERIFIED in the runbook step 23). It shows the good site in about a minute but is overwritten by the next deploy, and Git and the books are untouched, so do K4 after | G | 1 min | the site looks right |

**Recovery depends on the release's actual state** (read it with `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live status --host ~/.local/state/hass/host/host.json`: the `open` list names each unsettled change and its state):

| State | What it means | What to do (G / operator) |
| --- | --- | --- |
| `"open": []`, site shows a bad change (a release is `live`, `reverted` or `closed`) | the change landed and is settled | K3 first. If K3 cannot (refused, or the site is wrong another way): K4 below, then R1-R4 |
| `not-published` | saved on the writer, **never** reached the site | **No K4, nothing to restore on the site.** `retry <change id> --host ...` once if the cause was transient and the remote does not already have it, **or** the private-undo path in section 6 (K2, Mike `undo` + `yes`, then `unblock <change id> --host ...`). The repo's own disposable-repository test covers this path (`test_stop_undo_in_private_then_unblock_and_retry_no_duplicate`, passed in the 24-test run recorded in Appendix B) |
| `pushing` | a push is in flight | wait 2 minutes, run `status` again (each run lets the engine look again; it rate-limits itself); STOP cannot recall a push |
| `unknown` or `unconfirmed` | the push may or may not have landed, or landed but the page does not match yet | **K1, not K2. Do not touch the writer.** G looks at the live page by eye. If the site is right: `resolve <change id> --as live --host ...`. If the site is wrong or unwanted: K4, then see "after K4 on an unsettled release" below |

**K4 steps** (a normal push only, never `--force`; checked on disposable repositories, Appendix B):
1. `touch ~/.config/hass/STOP` and K1 (hold).
2. `git -C ~/.local/share/hass/theavocadoman-site fetch origin` and `git -C ~/.local/share/hass/theavocadoman-site status --porcelain` (prints nothing) and confirm `git -C ~/.local/share/hass/theavocadoman-site rev-parse HEAD` equals `git -C ~/.local/share/hass/theavocadoman-site rev-parse origin/main`.
3. Verify the target **before** changing anything: `git -C ~/.local/share/hass/theavocadoman-site merge-base --is-ancestor <GOOD-SITE-COMMIT> HEAD` (exit 0); `git -C ~/.local/share/hass/theavocadoman-site log --merges --oneline <GOOD-SITE-COMMIT>..HEAD` (prints nothing: a merge in the range means stop, the range revert does not handle it); `git -C ~/.local/share/hass/theavocadoman-site log --format='%h %an %s' <GOOD-SITE-COMMIT>..HEAD` and read it: every line should be `hass live:` or `hass baseline:`; **any other commit is someone else's work: stop and ask G**.
4. `git -C ~/.local/share/hass/theavocadoman-site revert -s --no-edit <GOOD-SITE-COMMIT>..HEAD` (new revert commits; the history is kept).
5. Verify the result: `git -C ~/.local/share/hass/theavocadoman-site diff --quiet <GOOD-SITE-COMMIT> HEAD` (exit 0: the tree is exactly the good one). If not, `git -C ~/.local/share/hass/theavocadoman-site revert --abort` or reset the local checkout to `origin/main` and stop; do not push.
6. `git -C ~/.local/share/hass/theavocadoman-site push origin HEAD:main`.
7. Look at theavocadoman.com (and `curl -sI`) after the site's own deploy.

**After K4: R1-R4 (attended; the CLI cannot settle a normal-push rollback by itself, so Hass stays in hold until this is done).** What the current CLI does after a revert-commit rollback, **proved on disposable local repositories** (Appendix B), single change:
- A later change is **refused** (`someone else changed the website repo; G must check`): the site head is no longer the head the books expect. Hass is safe but stuck until R3.
- `resolve <id> --as reverted` is **refused** (it needs the site and the checkout at the exact old commit, and a revert commit is a new one, even with identical bytes), and `resolve` on a closed release says `wrong-state`.
- R1. Release closed (it was `live`): nothing to resolve. Release `unknown`/`unconfirmed` (the push did land, K4 took it off): run `status` every 10 minutes until the state is `unknown` or `unconfirmed` (about an hour of simulated clock in the test; each real `status` run lets the engine look at most once every 10 minutes), then `resolve <change id> --as live --host ...`. **Write on the card that the books say "live" for a change that was rolled back**; the CLI has no word for "landed and rolled back". `wrong-state` here only means not yet unknown/unconfirmed: wait, do not edit any journal.
- R2. K2 (private) and bring the **writer** back to the site: Mike's `undo` + `yes`, one per rolled-back change, newest first, until `history` shows them undone and the writer equals the site.
- R3. `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live adopt --host ~/.local/state/hass/host/host.json`. Expected `{"result":"adopted"}`. `differs` (the writer and the site are not byte-equal after R2) or `open-release`: **stop, Hass stays in hold for attended disposition**; do not force anything and do not use `baseline --confirm` without G reading the path list.
- R4. Only after `adopted`: P-1, P-4, P-6, P-13, then a harmless live change and its undo (P-18, P-19) with G watching, then `live`. Proven with one rolled-back change; **rolling back several changes, or a K4 that included someone else's commits, is not proven**: treat as stay-in-hold.
- If any R step gives anything unexpected: stay in hold, keep every journal and backup, no force push, no editing `releases/`, and ask the policy/admission owner (a code card may be needed to give the CLI an explicit "rolled back" settlement).

Who may press what, as proposed here for G to confirm: **stopping** (K0, K0b, K1; K2 only under the release rule in section 3) can be done by Mike, G or the operator at once without asking; **going back to live** after any stop (K1/K2 → `live`, removing STOP) and **touching the live site** (K4, K4b, `retry`, `resolve`, `unblock`, `adopt`, `baseline`) is G only (the operator may type while G watches). Reasoning: every stop reduces exposure; everything else can publish or settle a release.

End of the visit (decision at the time, default K1): leave Hass in **hold** until G has read the problems log and the stage table, so nothing from a stray text can reach the site. G then chooses `private` or `live` for ordinary use.

## 5. WHAT TO WATCH (the operator, from a second screen, during the visit)

1. **Replies' timing.** Stage table: `python3 -B ~/.local/share/hass/runtime/hass/stagelog.py ~/.local/state/hass/host/stages.jsonl` after each step (ids are hashed; no text). Read it as legs: no `webhook-in`/`accepted` = the Mac or BlueBubbles; a long `interp-start` to `interp-end` = the model; a long `reply-queued` to `reply-pulled` = the Mac pulling; a long `bb-send-start` to `bb-send-end` = BlueBubbles sending. Normal (E2E-HIKE-1, GPU): question 1-2 s, draft with all fields 3-5 s, whole round trip with preview picture 7-9 s, `yes` and `undo` about 3 s. Over 20 s is logged as a "slow reply" problem. Over 60 s: section 3.
2. **Which model answered.** Save this as `~/agent-work/hass-watch-audit.py` (read-only; opens the file in read-only mode; prints times, backend, fallback and seconds; no message text) and run `python3 ~/agent-work/hass-watch-audit.py ~/.local/state/hass/state/conversation.sqlite3 10`. There is no `sqlite3` program on the box.

   ```python
   #!/usr/bin/env python3
   """Read-only: the last N interpreter calls (time, backend, fell back to CPU, seconds). No message text is read."""
   import sqlite3, sys
   from pathlib import Path

   db = Path(sys.argv[1]).expanduser()
   n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
   con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
   rows = con.execute("SELECT at, backend, fallback, primary_error, seconds FROM interpreter_audit ORDER BY at DESC LIMIT ?", (n,)).fetchall()
   for at, backend, fb, perr, sec in rows:
       print(at, backend, "CPU-FALLBACK" if fb else "primary", perr or "-", "-" if sec is None else f"{sec:.1f}s")
   print("rows:", len(rows), "fallbacks:", sum(1 for r in rows if r[2]), "slowest:", max((r[4] or 0 for r in rows), default=0))
   ```
   (Run once against a synthetic table while writing this: it printed the two rows and `rows: 2 fallbacks: 1 slowest: 61.2`. It was not run on the live file.) `backend` `openai` = the GPU route, `ollama` = the CPU fallback.
3. **The problems log.** G texts `problems` from G's phone (answers only in G's own chat, text only; needs P-7b) after step 3 and after step 7 and reads the last ten moments: did not understand, could not do, asked again, slow reply, wording check fallback, Mike said no or "that's wrong". `weekly` gives the three most common with one suggested fix each. If P-7b was red, the operator may only count lines in `~/.local/state/hass/state/correspondence/` (newest `<day>.jsonl`; at most 80 characters of Mike's words each, numbers blanked; never copy these files off the box). More than two "did not understand" in a row = tell G; the third is a drop-to-private candidate if Mike is getting frustrated.
4. **Health and publishing.** The 5-minute health timer writes an ALERTS line only when the set of problems changes. Add by hand after each website message: `python3 -B ~/.local/share/hass/runtime/hass/health.py --state ~/.local/state/hass/state --backups ~/.local/state/hass/backups --writer --model http://127.0.0.1:11434 --host-dir ~/.local/state/hass/host` and `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live status --host ~/.local/state/hass/host/host.json`. The ones that page G: `release-open`, `release-books`, `live-unconfirmed` (card, admin) and `mac-silent` over 2 hours (hardware).
5. **Service log.** `journalctl --user -u hass-worker -n 40 --no-pager` (no message text is printed). A restart loop or a traceback = K1.

## 6. FALLBACKS

| If | What Mike sees | What happens next |
| --- | --- | --- |
| **The Mac mini or iMessage fails** (no thumbs-up, no reply after 60 s; `mac-silent` in health; `outbox-stuck`) | nothing comes back, or a reply arrives late starting `Late reply to your message from <day> <time>:` | Tell him: "Wait, don't send it again; I'll fix the phone side." **G (Mac)**: restart Messages, then BlueBubbles, then `launchctl kickstart -k gui/$(id -u)/com.avocadoshack.hass-forwarder`, then `check` = `{"reachable":2}` (P-14). The inbox keeps his messages and the replies are re-sent without duplicates (tested: reply retry without a duplicate). Back in 10 minutes: carry on from the step that was open, and ask him to send `status` first. Not back in 10 minutes: K1 (hold), then the demonstration continues **without the phone**: the operator runs Mike's messages through the scratch rehearsal copy (as in P-0, nothing live), or G makes the same change the normal way (the site's own repository and its usual deploy) while Mike watches. No texting from G's own phone as a stand-in: it is not an owner |
| **The GPU model is busy or down** | a slow reply (the thumbs-up comes first). Up to about 55 s behind a fleet job; after the 60 s limit the CPU model answers in 25-90 s, with `status`, `yes`, `undo`, `listing`, `find`, `report` unaffected (they do not call the model: 1 to 3 s) | Under 60 s: nothing to do, Mike waits. Over 60 s twice in a row: use the no-model steps first (step 2 `listing`, step 7 `undo`, `status`) while the operator checks `nvidia-smi`, the audit script and who holds the GPU; do not restart the router or Ollama (not allowed without G). Still slow after 10 minutes: drop under the release rule (section 3: with `"open": []` K2, otherwise K1) so a slow model cannot delay a live publish |
| **The picture cannot be restyled** (house-style picture missing in R, Pillow missing, render fails) | no new look for the photo: the draft shows his original photo upright, or a plain "I couldn't make the picture look right" style message; never a fake success | The photo still goes up in its original form if he approves the draft; the restyle is a nice-to-have. If the draft has **no picture at all**, that is the live-mode rule "no picture, no live" (runbook: live mode requires picture delivery): drop under the release rule (section 3) and carry on |
| **The live publish fails: `not-published`** (reply says saved but not on the website yet; a G card `release-open`) | "Saved" and then a plain message that it is saved but not on the website yet (never "live") | Tell Mike: "It's saved, it isn't on the site yet. Don't send the next one." Nothing reached the site, so the site is exactly as before. Operator: P-17 `status`. **G**, one of: (a) `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live retry <change id> --host ~/.local/state/hass/host/host.json` once, only if the cause was transient and the remote does not already have it (`already-landed` means stop and look at the site); or (b) **settle it privately, in this order, before any other change**: K2 (private), Mike texts `undo` then `yes <new code>` (that undoes only the held change on the private writer; nothing is published), then `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live unblock <change id> --host ~/.local/state/hass/host/host.json` which must print `"state": "closed"` (it checks the writer equals the site's baseline exactly). Only then may the demonstration go on privately. Any other private change made **before** the undo and `unblock` can break the equality `unblock` needs, and then Hass stays held for attended disposition. If G wants to keep the live writer untouched, the alternative is to stop the visit's changes (K1) and finish with the scratch rehearsal copy, not Mike's phone |
| **The live publish is unsettled: `unknown`, `unconfirmed` or `pushing`** (G card `live-unconfirmed`; or a push that returned no clear answer) | "Saved", then a plain message that it may or may not be on the website yet | Tell Mike: "I'm checking whether it is on the site. Don't send the next one." **K1 (hold), not K2, and no further change of any kind**: K2 does not settle this, and any private change moves the writer. Operator: `status` every 10 minutes (it lets the engine look again). **G**: look at the live page by eye; `cd ~/.local/share/hass/runtime && python3 -B -m hass.publish_live resolve <change id> --as live --host ~/.local/state/hass/host/host.json` once the state is `unknown` or `unconfirmed` and the page shows the change. `--as reverted` needs the remote and checkout at the exact old commit and refuses otherwise (checked). Not resolvable in 10 minutes, or the site is wrong: stay in hold, K4b for the look and K4 plus R1-R4 for the repository, G only. The rest of Mike's visit is reads and refusals only (step 2, step 8) |
| **The site is wrong in public** | n/a | K3 first; if it cannot, K0b then K4b then K4 (with R1-R4), in that order; G only |

## 7. TIMELINE: who does what

Times are PST. The store visit time is not in the card: `<visit time>` below. Mike's tasks need no tools, only his phone.

**Sunday 2026-11-08 (tonight)**
| Time | Who | What |
| --- | --- | --- |
| 15:00 | operator | Gives G the FOR-G page and asks for the one-word answer (`LIVE`, `PRIVATE` or `LATER`) before 17:00; records it on the card as the LSC. Freeze R: record which of PRs 504, 525, 526, 529, 530, 531, 532 are merged and which commit is R; if R is newer than `0a8114c`, schedule the planned runtime move (new detached worktree, `runtimeCommit`, restart) for before 18:00. P-0 scratch rehearsal starts; P-0b runs as soon as R and its scratch checkout exist |
| by 17:00 | **Mike** | Picks the real things: one product already on the site to give a real photo (from `photos to take`), one item that is really sold out, a real weekly special, a real hike (or says skip), the notice text. Takes the photo: upright, plain background, nobody in it, fine to be public. Sends **nothing** yet |
| 17:00-18:30 | **G** | **Only if the LSC is recorded:** runbook steps 20-22 (list below). Without the LSC G does not enable live; the operator keeps `hold`. If step 19 (private mode with a result picture) was never done, do that first: set `private` (K2 command), Mike approves one tiny change, a picture comes back, then `undo`. Stop and tell the operator at any unexpected result; do not retry an old code |
| 18:00 | operator | R frozen. P-1, P-2, P-3. P-0b must already be clean or the live photo step is dropped |
| 18:30-19:30 | operator | P-4 to P-12, P-22; P-10 battery runs in the background |
| 19:30 | **G (Mac)** | P-13, P-14, **P-7b** (the `gChat` line in the Mac config, the check, the restart, the `problems` text) |
| 20:00-20:45 | **G + Mike** + operator | P-15, then P-18 (harmless live change), P-19 (undo), P-18b (one real photo, then undo). Mike needs about 25 minutes at his phone |
| 20:45 | operator | P-20 backup, P-21 GOOD-SITE-COMMIT, P-24 |
| 21:00 | operator | **Go/no-go #1** on the card: five lines, each green or red; the first line includes the recorded LSC. **No LSC on the card: nothing live, Hass stays in `hold`, and G is asked once more; there is no automatic choice.** LSC recorded and steps 20-22 or P-18/P-19 red: Monday is **private mode** (K2): Mike still sees text, photo, draft, picture, `yes`, `undo` in real time, plus step 1P, and G is told by 21:15. LSC recorded and only P-18b red: live visit without step 1L. G's `PRIVATE` answer alone: private mode as chosen. No more changes to R after this |
| 21:30 | operator | Leave Hass in the mode G's answer and the gate allow (`hold` if there is no answer); STOP absent only in live mode |

**Monday 2026-11-09 (morning)**
| Time | Who | What |
| --- | --- | --- |
| 07:00 | operator | P-1, P-3, P-4, P-6, P-8, P-9, P-16, P-23, P-24 |
| 07:15 | **G (Mac)** | P-14 restart Messages and BlueBubbles and the forwarder, P-13 check, and the `problems` text of P-7b |
| 07:30 | **Mike** + operator | P-15: `status` from Mike's phone, reply under 10 s, stage table read |
| 07:45 | operator | P-20 backup verified, P-21 GOOD-SITE-COMMIT still equals the remote, P-25 GPU quiet |
| 08:00 | operator | **Go/no-go #2** (the five lines in section 3), posted on the card and to G. G answers "go live" or "private" in his own words; the operator restates the live scope (existing-product photo, no brand-new product) in the message. No answer means no live visit: Hass stays in `hold` |
| `<visit time>` -15 min | operator + G | Both on the phone line, second screen open (section 5); Mike told the four ground rules |
| `<visit time>` | **Mike**, G beside | The script (live: steps 0, 1L, 2-9; private: add 1P) |
| after | operator, G | K1 hold; stage table, audit and `problems` read; card comment with what failed; site content checked true (any item that is not real is removed by an undo or by G); G decides the everyday mode |

**The minimum list only G and Michael can do (copy-paste; replace `<...>` privately, never paste a secret into chat, a card, Git or logs).**

*Michael*: (1) confirm his phone number is the one in `ownerSenders` (G checks); (2) the real details and the photo above; (3) tonight, 25 minutes: text one tiny change, `yes <code>`, wait for the picture, then `undo`, `yes <new code>`; then one real photo for one product, `yes`, picture, then `undo`; (4) Monday: phone charged, signal in the store, Messages open, no other app that needs the Apple Account on that phone being re-signed.

*G, on AgentOrange* (runbook steps 20-22; from `docs/hass/MAC_RUNBOOK.md`, labels in GitHub and Cloudflare are UNVERIFIED until the first real run):
```sh
ssh-keygen -t ed25519 -N "" -C hass-site -f ~/.ssh/hass_site
```
(do not overwrite an existing key). In `~/.ssh/config` add the `github-avocadoman` host block from step 20 (IdentityFile `~/.ssh/hass_site`, IdentitiesOnly yes). On GitHub, repo theavocadoman-site only: Settings, Deploy keys, Allow write access, paste the contents of `~/.ssh/hass_site.pub`. Then:
```sh
ssh -T git@github-avocadoman
```
(check the host fingerprint against GitHub's published list before accepting). In Cloudflare Pages: turn off HTML rewriting including email obfuscation. Then:
```sh
git clone git@github-avocadoman:Grahammmm/theavocadoman-site.git ~/.local/share/hass/theavocadoman-site
git -C ~/.local/share/hass/theavocadoman-site config user.name '<chosen identity>'
git -C ~/.local/share/hass/theavocadoman-site config user.email '<chosen commit address>'
```
Add the `release` block to `~/.local/state/hass/host/host.json` (keep mode 600, absolute paths, **no** `~`): `"release": {"siteCheckout":"<absolute home>/.local/share/hass/theavocadoman-site","siteRemote":"git@github-avocadoman:Grahammmm/theavocadoman-site.git","liveUrl":"https://theavocadoman.com","stopFile":"<absolute home>/.config/hass/STOP","dailyCap":10,"minIntervalSeconds":120,"verifyMinutes":15}`, then (the module form; `--host` is required):
```sh
cd ~/.local/share/hass/runtime
python3 -B -m hass.publish_live adopt --host ~/.local/state/hass/host/host.json
python3 -B -m hass.publish_live status --host ~/.local/state/hass/host/host.json
```
If `adopt` says `differs`: stop and ask the operator (the runbook has the `--from-remote` and `baseline --confirm` path; the confirm is a real live publication and G reads the path list first). Then edit the state `config.json` `settings` by hand: `"liveSite": "theavocadoman.com"`, `"approvalNeedsCode": true`, and (for G's problems log) `"gSenders": ["<G's address>"]`, `"gChat": "iMessage;-;<G's address>"`; set host `approvals` to `live` (the K1 `sed` with `"live"`), then:
```sh
systemctl --user restart hass-worker
python3 -B ~/.local/share/hass/runtime/hass/host.py check --host ~/.local/state/hass/host/host.json
```
*G, on the Mac mini* (P-7b, P-13, P-14): in a private editor add `"gChat": "iMessage;-;<G's address>"` to `~/Library/Application Support/HassForwarder/config.json` (the same text as on AgentOrange; nothing else; mode 600); quit Messages and BlueBubbles, open Messages (wait for the account), open BlueBubbles (wait for connected), then:
```sh
launchctl kickstart -k gui/$(id -u)/com.avocadoshack.hass-forwarder
python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py check --config ~/Library/Application\ Support/HassForwarder/config.json
```
Expected `{"reachable":2}`. Then G texts `problems` from G's own phone and sees the answer in G's own chat only. Nothing else on the Mac is to be touched.

## 8. Open decisions and known gaps (said plainly)

1. **A live brand-new product is not possible today** (section 0, A): G's headline request is **NO-GO** as asked. Not a code change here; the policy owner decides whether and how a reviewed live path for new products is admitted. Until then: existing-product photo live (option 1), or private (option 2), or later (option 3).
2. **Live is not ready.** As of 14:40 steps 20-22 are not done and `approvals` is `hold`. Section 3 and the 21:00 gate decide Monday's mode, but only inside what G has explicitly confirmed (the LSC in section 0, A). If G cannot finish steps 20-22 tonight, the recommendation is private mode, which G must also choose in his own words; silence leaves Hass in `hold`. That is the operator's earlier advice, not a refusal of G's choice.
3. **A public site has no practice mode.** Everything in the live script is seen by customers. Use only real details. If G wants a pure demonstration (a made-up hike or product), it must be private mode. Undoing an added hike leaves a cancelled hike card (E2E-HIKE-1). How undoing a photo or an added hike looks on the page is shown by P-18b and P-0; do not promise Mike that "undo" makes everything vanish.
4. **The "skills".** The skills router (PRs 525, 526) and the hike, special and shop skills (PRs 529-531) are not in the runtime. The script works on the older plain-words path; wording of replies may differ from what the skills would say. R decides.
5. **House-style picture** is not on main. Variant B of step 1L is the default until R contains it.
6. **CPU fallback** has never run for real. The 25-90 s figures are measurements of the CPU model alone (FAST-1, MODEL-1).
7. **Private-mode changes are not published later by themselves** (section 3), and K2 does not settle an open release.
8. **Rollback by normal push is proven only for one rolled-back change on disposable repositories** (Appendix B). The CLI has no explicit "rolled back" settlement; after K4 Hass stays in hold until R1-R4 are done attended. A code card for a proper settlement would be a good follow-up (not made here).
9. **Who may press K1-K4** is a proposal for G to confirm; the runbook itself says G performs every live step.
10. **Tapback (thumbs-up)** exists only if the BlueBubbles Private API (SIP off, approved by G 2026-11-08) was set up; the first sign of life may otherwise be the reply itself.
11. **Not found:** LIVE-PLAN-1, LIVE-STEPS-G-MICHAEL, APPLY-TEST-1 (not merged yet) and any write-up of the 2026-11-08 "restart Messages and BlueBubbles" incident; the P-14 wording is taken from the card text.
12. **Reply sentences** in section 1 are shapes, not quotes (except the refusal and photo-question sentences, which are quoted from the code). P-0 (scratch rehearsal) is what turns the rest into quotes.
13. **The photo path (1L) is policy-allowed but not run end to end live** until P-18b. The picture words (`imageAlt`) are checked by the same claims filter as other text.

## Appendix A. Live-policy rehearsal script (P-0b) and its output

**Update 2026-11-09 (HASS-LIVE-ADD-1):** the maintained script is `reports/hass/rehearse_live_policy.py`, with its output in `reports/hass/rehearse_live_policy.out`. A new product is now ALLOWED (S1, S1a); the still-private rows are REFUSED (maker alone, maker link, existing maker place/link, hide, brand or producer of an existing product, organic/price words, brand not in the owner's words, the `image` argument, notice, phone, set_photo). Below is the original (2026-11-08) script and output, kept for history; in it `S1`, `S1b` read REFUSED because the policy then refused every new product.

Read-only and scratch-only: it builds a temporary writer repository and state with the checkout's own test helper, runs the checkout's real op registry and its real `live_policy.check`, and prints one line per case. It touches no live file, no network, no Mac. Save as `~/agent-work/hass-store-test/rehearse_live_policy.py`; run `python3 -B ~/agent-work/hass-store-test/rehearse_live_policy.py <scratch checkout of R>`.

```python
"""Scratch-only rehearsal: run the real op registry at this checkout through the real LIVE policy.

Uses a temporary writer repo + state (hass.tests.test_editor.WriterRepo). No live state, no network, no messages.
Usage: python3 -B rehearse_live_policy.py <checkout>
"""
import json
import sys
from pathlib import Path

CHECKOUT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(CHECKOUT))

from hass import editor, live_policy  # noqa: E402
from hass.ops import load_registry  # noqa: E402
from hass.tests.test_editor import WriterRepo  # noqa: E402

repo = WriterRepo()
reg = load_registry()
products = json.loads((CHECKOUT / "hass/content/products.json").read_text())
products = products if isinstance(products, list) else products.get("products", products)
pid, pimg = products[0]["id"], products[0].get("image")
cat = products[0].get("category")
print("checkout", CHECKOUT.name, "ops loaded:", len(reg), "sample product id:", pid)


def draft_for(label, *ops):
    out = editor.prepare({"ops": [{"op": n, "args": a} for n, a in ops]}, state=str(repo.state), registry=reg)
    if out["result"] != "ok":
        print(f"{label:55s} PREPARE-{out['result']}: {str(out.get('problems') or out)[:110]}")
        return None
    reasons = live_policy.check(out["draft"])
    print(f"{label:55s} LIVE-POLICY: {'ALLOWED' if not reasons else 'REFUSED ' + str(reasons)}")
    return out["draft"]


draft_for("S1  product.add (brand given)", ("product.add", {
    "name": "Test Orchard quince", "brand": "Test Orchard", "category": cat, "image": pimg,
    "description": "A bowl of quinces."}))
draft_for("S1b maker.add (new maker with a place)", ("maker.add", {
    "key": "test-orchard", "name": "Test Orchard", "place": "Paso Robles, California", "story": "A small orchard.", "url": "https://www.example.com/orchard"}))
draft_for("S3  store.confirm_selection (sold out, shelf check)", ("store.confirm_selection", {"no": [pid]}))
draft_for("S4  specials.add", ("specials.add", {
    "title": "Fresh bread Friday", "deal": "A free sample with any cheese", "end": "2026-11-14"}))
draft_for("S5  hike.create (meeting point trailhead gate)", ("hike.create", {
    "title": "Cass Hill walk", "date": "2026-11-14", "time": "09:00", "meetingPoint": "The trailhead gate",
    "rsvpEnabled": False}))
draft_for("S6  store.set_notice", ("store.set_notice", {
    "text": "Come say hi, we are testing a new way to update the shop", "until": "2026-11-10"}))
draft_for("S8  store.set_phone (must be refused)", ("store.set_phone", {"phone": "805 555 0100"}))

# product.set_photo: build the record shape the op writes (only image and imageAlt change; no staged photo needed)
rec = {"collection": "products", "before": {"id": pid, "name": "x", "brand": "b", "image": "old.jpg"},
       "after": {"id": pid, "name": "x", "brand": "b", "image": "assets/products/photo-0123456789ab.jpg",
                 "imageAlt": "A bowl of quinces on a wooden counter"}}
r = live_policy.check({"ops": [{"op": "product.set_photo", "args": {}}], "records": [rec]})
print(f"{'S1c product.set_photo on an EXISTING product (record shape)':55s} LIVE-POLICY: {'ALLOWED' if not r else 'REFUSED ' + str(r)}")
rec2 = {"collection": "products", "before": rec["before"],
        "after": {**rec["after"], "imageAlt": "Organic quinces from a farm"}}
r = live_policy.check({"ops": [{"op": "product.set_photo", "args": {}}], "records": [rec2]})
print(f"{'S1d same, but the picture words claim organic/farm':55s} LIVE-POLICY: {'ALLOWED' if not r else 'REFUSED ' + str(r)}")
repo.cleanup()
```

Output when run (twice: at `main` 56c9070, and at runtime commit 0a8114c; identical):

```
checkout wt ops loaded: 39 sample product id: photo-product-001
S1  product.add (brand given)                           LIVE-POLICY: REFUSED ['protected field: products.brand', 'protected field: products.displayBrand']
S1b maker.add (new maker with a place)                  LIVE-POLICY: REFUSED ['protected field: makers.place', 'protected field: makers.url']
S3  store.confirm_selection (sold out, shelf check)     LIVE-POLICY: ALLOWED
S4  specials.add                                        LIVE-POLICY: ALLOWED
S5  hike.create (meeting point trailhead gate)          LIVE-POLICY: ALLOWED
S6  store.set_notice                                    LIVE-POLICY: ALLOWED
S8  store.set_phone (must be refused)                   LIVE-POLICY: REFUSED ['protected operation: store.set_phone']
S1c product.set_photo on an EXISTING product (record shape) LIVE-POLICY: ALLOWED
S1d same, but the picture words claim organic/farm      LIVE-POLICY: REFUSED ['protected sentences: origin/organic']
```

S1c and S1d use the record shape that `product.set_photo` writes (only `image` and `imageAlt` change), because a real staged photo is not needed to see the policy decision; the full photo chain is P-0 and P-18b.

## Appendix B. Rollback reconciliation proof on disposable repositories (K4 / R1-R4)

Uses the repo's own release fixture (`hass.tests.test_publish_live.ReleaseCase`: a local bare repository standing in for the site remote, the real editor, an injected clock and fetch). No live state, no network. Save anywhere outside the repository; run `python3 -B <file> <scratch checkout>`. (Its last line runs only the two rollback scenarios; removing the test names there runs the 24 inherited release tests as well, which all passed in an earlier run here.)

```python
"""Scratch-only proof of the K4 rollback reconciliation, on disposable local bare repositories.

Reuses the repo's own release fixture (hass.tests.test_publish_live.ReleaseCase). No live state, no network.
Usage: python3 -B prove_rollback.py <checkout>
"""
import subprocess
import sys
import unittest
from datetime import timedelta
from pathlib import Path

CHECKOUT = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(CHECKOUT))

from hass import editor  # noqa: E402
from hass.tests.test_editor import _req, git  # noqa: E402
from hass.tests.test_publish_live import ReleaseCase  # noqa: E402


class RollbackProof(ReleaseCase):
    def g_rollback(self, good):
        """What the plan tells G to do: checks, then a revert range and a NORMAL push (never --force)."""
        s = self.site
        git(s, 'fetch', 'origin')
        self.assertEqual(git(s, 'status', '--porcelain'), '')
        self.assertEqual(git(s, 'rev-parse', 'HEAD'), git(s, 'rev-parse', 'origin/main'))
        subprocess.run(['git', '-C', str(s), 'merge-base', '--is-ancestor', good, 'HEAD'], check=True)
        self.assertEqual(git(s, 'log', '--merges', '--oneline', good + '..HEAD'), '')
        git(s, 'revert', '-s', '--no-edit', good + '..HEAD')
        subprocess.run(['git', '-C', str(s), 'diff', '--quiet', good, 'HEAD'], check=True)  # tree equals GOOD
        git(s, 'push', 'origin', 'HEAD:main')

    def private_undo(self, cid):
        undo = editor.prepare(_req(('history.revert', {'changeId': cid})), state=self.repo.state, registry=self.live.registry)['draft']
        self.assertEqual(editor.apply(undo['change_id'], undo['draft_hash'], state=self.repo.state, registry=self.live.registry)['result'], 'applied')

    def test_T1_closed_release_then_rollback_then_adopt_then_resume(self):
        good = self.site_before
        self.assertEqual(self.apply()['result'], 'applied'); self.settle()
        cid = self.entry()['change_id']
        print('\nT1 release state before rollback:', self.entry()['state'])
        self.g_rollback(good)
        self.assertEqual(git(self.bare, 'rev-parse', 'main'), git(self.site, 'rev-parse', 'HEAD'))
        self.now += timedelta(seconds=120)
        r = self.apply(self.draft(['Fixture new hours']))
        print('T1 next change right after rollback ->', r['result'], '|', r.get('reason'))
        self.assertEqual(r['result'], 'refused')
        print('T1 resolve on a closed release ->', self.live.operate('resolve', cid, resolution='reverted'))
        self.private_undo(cid)           # the writer goes back to equal the site
        a = self.live.operate('adopt')
        print('T1 adopt after private undo ->', a)
        self.assertEqual(a['result'], 'adopted')
        self.now += timedelta(seconds=120)
        r = self.apply(self.draft(['Fixture new hours']))
        self.settle()
        print('T1 next change after adopt ->', r['result'], '| release state', self.entry()['state'])
        self.assertEqual(r['result'], 'applied')
        self.assertEqual(self.entry()['state'], 'live')

    def test_T2_unknown_release_then_rollback(self):
        good = self.site_before

        def lose(cwd, args):
            if args[0] == 'push':
                git(cwd, *args)
                raise subprocess.TimeoutExpired('git', 60)
            if args[0] == 'ls-remote': raise subprocess.TimeoutExpired('git', 60)
        self.fault = lose
        self.apply(); self.settle()
        cid = self.entry()['change_id']
        print('\nT2 state after lost push response:', self.entry()['state'])
        self.fault = None
        self.g_rollback(good)
        try:
            print('T2 resolve --as reverted ->', self.live.operate('resolve', cid, resolution='reverted'))
        except ValueError as exc:
            print('T2 resolve --as reverted -> ValueError (CLI prints {"result":"refused"}):', exc)
        # let the engine look again (it re-reads the remote and the live page)
        self.now += timedelta(minutes=20)
        self.settle()
        for _ in range(3):
            self.now += timedelta(minutes=11); self.settle()
        print('T2 state after the engine looked again (3 more checks, 11 min apart):', self.entry()['state'])
        state = self.entry()['state']
        if state in ('unknown', 'unconfirmed'):
            print('T2 resolve --as live ->', self.live.operate('resolve', cid, resolution='live'))
        print('T2 state:', self.entry()['state'])
        self.private_undo(cid)
        a = self.live.operate('adopt')
        print('T2 adopt ->', a)
        if a['result'] == 'adopted':
            self.now += timedelta(seconds=120)
            r = self.apply(self.draft(['Fixture new hours'])); self.settle()
            print('T2 next change after adopt ->', r['result'], '| release state', self.entry()['state'])


if __name__ == '__main__':
    unittest.main(argv=['x', 'RollbackProof.test_T1_closed_release_then_rollback_then_adopt_then_resume', 'RollbackProof.test_T2_unknown_release_then_rollback'])
```

Output (the two rollback scenarios, `Ran 2 tests ... OK`; an earlier run of the whole fixture class also passed, `Ran 24 tests ... OK`):

```
Ran 2 tests in 5.578s
OK
T1 release state before rollback: live
T1 next change right after rollback -> refused | someone else changed the website repo; G must check. The website is unchanged.
T1 resolve on a closed release -> {'result': 'wrong-state'}
T1 adopt after private undo -> {'result': 'adopted'}
T1 next change after adopt -> applied | release state live
T2 state after lost push response: unknown
T2 resolve --as reverted -> ValueError (CLI prints {"result":"refused"}): site-state
T2 state after the engine looked again (3 more checks, 11 min apart): unconfirmed
T2 resolve --as live -> {'result': 'ok', 'change_id': 'chg-b299834b9eb1', 'state': 'live'}
T2 state: live
T2 adopt -> {'result': 'adopted'}
T2 next change after adopt -> applied | release state live
```

What it shows: after a revert-commit rollback pushed normally, the next change is refused, `resolve --as reverted` is refused, `resolve` on a closed release is `wrong-state`; for an unsettled release the engine reaches `unconfirmed` after repeated looks and `resolve --as live` closes it; after the writer is undone privately, `adopt` is accepted and the next change is applied and goes live. **Single rolled-back change only.** Several changes, someone else's commits in the range, or an `adopt` that says `differs` are not proven and stay held.
