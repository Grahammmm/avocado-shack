# HASS-STORE-TEST-1: the live test with Mike at the store (Monday 2026-11-09)

Card t_fc2b6272 · repo Grahammmm/avocado-shack · design and checklist only: no code was changed, no live state touched, nothing sent.
Written Sunday 2026-11-08 about 14:45 PST. Everything marked **checked** was read or run on AgentOrange while writing this (read-only: `git log`, `systemctl is-active`, `health.py`, a grep of one key in `host.json`). Everything marked **to check** is a pre-flight item for the operator.

G chose "go fully live": Mike adds things to the real theavocadoman.com by text and photo while standing in the store. The operator advised a private rehearsal first. This plan does both honestly: it prepares for live, and it says exactly when we drop to private on the spot (section 3) and what that costs.

## 0. Read this first: where we really are (checked 2026-11-08 ~14:40 PST)

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
| Add an item from a photo and plain words | yes, the older path: Hass asks "which product is this photo for", draft, `yes`. The photo is stored as the original upright JPEG (E2E-HIKE-1 4c). | house-style picture and one-message add: PR 504 HASS-NEWITEM-1 (and the SKILLS-PIC-2b branch, no PR yet). `hass/newitem_render.py` is **not on main**. |
| "Who grew this?" | yes: `listing <name>` and a plain question both answer from the saved site records and say "I don't know" otherwise | none |
| Sold out | yes, the older path: the ops `store.confirm_selection` and `product.set_availability` are in the runtime and the interpreter reads "I checked the selection today..." | the `stock.*` skills (`stock.set`, `stock.checked`) are PR 532, in `main` but **not** in `0a8114c` (the runtime has no `hass/skills/stock.py`) |
| Weekly special | the specials ops are on main (PR 520); chat skills for specials are PR 529 | PR 529 |
| Add a hike | yes, plain words (E2E-HIKE-1) | skills version: PR 530 |
| Change a notice | yes, plain words | skills version: PR 531 |
| Undo | yes | none |
| Refused kindly | yes: prices, protected facts, store phone and address | none |

So "using the skills" means different things depending on the runtime commit R we freeze. Rule: **R is chosen once, by 18:00 Sunday, and never moved after 21:00 Sunday except to fix a NO-GO.** Moving R means a new detached runtime worktree, `runtimeCommit` updated, services restarted, and the whole battery (P-10) re-run.

Decision for the operator at 15:00 Sunday (technical, not for G): say in the card which PRs (504, 525, 526, 529, 530, 531, 532) are merged by then and which R that gives. If the house-style picture is not in R, Mike's photo goes up as the plain upright photo and the script says so (step 1 variant B).

## 1. THE SCRIPT (what Mike and G do, in order)

Setting: Mike stands in the store with his phone, Hass is the business Messages account. G is beside him or on the phone with the operator. Mike only ever texts Hass; he never types a command he does not see in this list.

Ground rules for the visit, said to Mike first, in these words:
1. "Everything we do goes on the real website for real customers to see. Only say true things."
2. "After you say `yes`, wait for Hass to say it is showing on the website before you say the next `yes`. That takes one to three minutes."
3. "If anything looks wrong, text `stop changes`. That stops everything. You cannot break anything with that."
4. "If Hass takes more than a minute, do not send it again. Wait. Hass will answer."

What Hass should answer is described by shape, not exact words: the exact sentences come from `docs/hass/VOICE.md` and will be confirmed in the scratch rehearsal (P-0). The **pass test for every reply** is the same: plain everyday words, no codes except the one to type after yes/no/undo, one clear next step, and it never says "done", "live" or "saved" before that is true.

Time budget: about 30 to 40 minutes for seven changes (each live change waits for the previous one to show: minimum 2 minutes between two publishes, up to 15 minutes to confirm). Daily cap for live changes is 10; this script uses 5 (steps 1, 3, 4, 5, 6), plus 1 if the harmless pre-flight change is on the same day; undos do not count.

Step 0. **Hello.**
- Mike sends: `status`
- Hass: a thumbs-up on his message if tapbacks are on (otherwise nothing), then one short plain reply: everything is ready, nothing waiting for his yes, and he still needs to do today's shelf check.
- Pass: reply within about 10 seconds; no technical words. This is also the go/no-go round trip (section 3, check C).

Step 1. **Add an item with a photo.** Choose a real product on the shelf with a real maker. Photo: one photo, upright, JPEG or PNG, nothing else in the frame (no faces, no receipts, no price tags, no private places). Have the details on paper: name, who makes it, town and state, one sentence about it **in his own words**. Hass never invents where something grew or whether it is organic; if Mike says it, Hass may use it.
- Mike sends: the photo alone (a caption is never read as a command).
- Hass: one question: which product is this photo for / what is it called, and a few words describing the photo.
- Mike sends one message, for example: `It is a new product, the Test Orchard quince. It is made by Test Orchard in Paso Robles, California. A bowl of quinces on a wooden counter.` (use the real item)
- Hass: asks at most one more question if a needed fact is missing (for example the maker's town); otherwise a draft, said back in shop words (the product as Mike calls it, its maker, its shelf, the photo), with a preview picture of how the page will look, and "Reply yes <code> to save it, or no to cancel". In live mode it names theavocadoman.com and the code must be typed (`yes a1b2`, not a bare `yes`).
- Mike checks the picture, then sends: `yes <code>`
- Hass: first "Saved" (and nothing about the website yet). Then, in a separate message, "Now showing on theavocadoman.com" with a picture of the live page. If the picture is missing, that is a drop-to-private trigger (section 3).
- G opens theavocadoman.com on a phone and finds the product: it shows a **New** badge for 14 days.
- Variant B (no house-style picture in R): the draft preview shows the original photo, upright, with no location or camera data. Say to Mike: "this is your own photo as taken; the restyled version comes later."

Step 2. **"Who grew this?"** (reads only, changes nothing)
- Mike sends: `Who grew the Test Orchard quince?` (use the product he just added)
- Hass: answers only from what is on the site: the maker's name and town. If the site does not say who grew something, it says "I don't know who grew it" and asks what to say. Pass = no invented farm, no "organic", no guess.
- Mike then sends: `listing Test Orchard quince`
- Hass: "This is from my saved copy, not a live look at the website:" then its name, status, place. Pass = anything not saved reads "nothing yet".

Step 3. **Mark one thing sold out.** Pick something that really is sold out, or that Mike will put back at the end.
- Mike sends: `I checked the selection today: the eggs are limited and the sourdough is sold out.` (real names)
- Hass: a draft saying back exactly those words, which products change, and that today's shelf check will be recorded. If today's check is missing it may first ask "is the shelf list right for today?": Mike answers with a bare `yes` (that one is the only bare yes in the script) or tells it what is different.
- Mike sends `yes <code>`; waits for "Now showing on theavocadoman.com". The site shows "Selection last checked by Michael on <today>" and the words on the cards.

Step 4. **Add a weekly special.** A real one.
- Mike sends: `Add a weekly special: Fresh bread Friday, a free sample with any cheese, through Saturday.` (real title, real deal line, last day within 31 days; no links or phone numbers; a price only in the deal line, exactly as typed)
- Hass: draft with the title, the deal line and the last day written as people say it ("through Saturday"), then yes, then showing.
- Pass: the "This week's specials" box shows it; it disappears itself after its last day.

Step 5. **Add a hike.** A real hike, or skip this step (see item 2 in section 8: undoing an added hike leaves a public "cancelled" hike card).
- Mike sends: `Post a hike at Cass Hill on Saturday at 9am, meet at the trailhead gate.`
- Hass: asks only what is missing (for example the day if it is not clear), then a draft: title, day and time in plain words, meeting point. Hass never makes up difficulty, distance or trail facts and does not add seats or a capacity Mike did not give. (E2E-HIKE-1 saw an invented seat count once: Mike reads the draft and says `no <code>` if anything is there that he did not say.)
- Mike sends `yes <code>`; waits for "Now showing".

Step 6. **Change a notice.** Keep it true and short (160 characters, last day today up to 60 days ahead).
- Mike sends: `Put a notice on the home page: "Come say hi, we are testing a new way to update the shop", until 2026-11-10.`
- Hass: draft with the old notice (if any) and the new one, the last day in plain words; yes; showing. The notice appears at the top of the home page. This must be the **last** change, because step 7 undoes it.

Step 7. **Undo one change.**
- Mike sends: `undo`
- Hass: a draft that takes back the most recent change (the notice), in shop words, with a new code. (`history` shows the last five changes but no codes; a bare `undo` takes the latest.)
- Mike sends `yes <new code>`; Hass says saved, then showing; the notice is gone from the home page. Undo is exempt from the daily cap but not from STOP.
- If Mike wants to also take back a sold-out word at the end: `stop showing the sourdough as sold out` (draft, yes). Undoing the shelf check itself is refused if a later edit touched the same detail ("undo the newer one first").

Step 8. **A mistake, refused kindly.** The point is to show Mike that Hass says no gently and changes nothing.
- Mike sends: `Change the store phone number to 805 555 0100`
- Hass: says it cannot change that from chat, that nothing was changed, and that Graham can do it by hand. No draft, no code. (Protected from chat in live mode: store phone and address, brands and producers, maker places and links, club details, trail facts.)
- Second one, if time: `Put the Hass avocado at $2 each` → Hass says the site shows no prices and nothing changed; or `make the hikes better` → Hass asks one short question and changes nothing.
- Pass: no technical word, no "error", no blame.

Step 9. **Close.** Mike sends `did it work?` Hass answers "Last change:" in plain words (undone). G sends `problems` from G's own phone in G's own chat (needs `gSenders` and `gChat`, P-7) and reads the last ten problem moments. Then the operator makes the end-of-visit state decision (section 7).

Not in the script on purpose: voice notes (not understood yet), more than one photo per message, anything with a price except a special's deal line, hike photos (Hass only attaches photos to products).

## 2. PRE-FLIGHT

Who: the **operator** runs these on AgentOrange unless a line says **G (Mac)** or **G**. Two passes: the night before (Sunday 19:00-21:00) and the morning of (Monday 07:00-08:00). Each item has a command and an expected result. A red result is a NO-GO for that item until fixed; do not skip and do not repair by guessing. Paths: `R` = `~/.local/share/hass/runtime`, state = `~/.local/state/hass/state`, host file = `~/.local/state/hass/host/host.json`, site = `~/.local/share/hass/theavocadoman-site`.

| # | Check | Command | Expected | Night | Morning |
| --- | --- | --- | --- | --- | --- |
| P-0 | Script rehearsed on a scratch copy (no live, no phone) | the same method as HASS-E2E-HIKE-1: scratch writer + scratch state + synthetic owner, real code at R, real GPU interpreter; send the 9 steps' messages | each step ends as section 1 says; replies pass `voice.check`; no code path says "live" before it is | yes | - |
| P-1 | Runtime version | `git -C ~/.local/share/hass/runtime rev-parse HEAD` and `git -C ~/.local/share/hass/runtime status --porcelain` | HEAD equals `runtimeCommit` in `host.json` and the agreed R; second command prints nothing | yes | yes |
| P-2 | R contains what the script needs | `git -C ~/.local/share/hass/runtime merge-base --is-ancestor <merge commit of the PR> HEAD` for each PR we rely on | exit 0 for each (no output); anything missing is written on the card and the script step is shortened | yes | - |
| P-3 | Host config valid | `python3 -B ~/.local/share/hass/runtime/hass/host.py check --host ~/.local/state/hass/host/host.json` | one JSON line `ok`; exit 0 | yes | yes |
| P-4 | Services up | `systemctl --user is-active hass-receiver hass-worker hass-health.timer hass-backup.timer` | four lines `active` | yes | yes |
| P-5 | Services survive a logout/reboot | `loginctl show-user $USER -p Linger` | `Linger=yes`; if `no`, tell the operator: after a reboot nothing starts until someone logs in (support doc: unmeasured) | yes | - |
| P-6 | Health, the same flags as the timer | `python3 -B ~/.local/share/hass/runtime/hass/health.py --state ~/.local/state/hass/state --backups ~/.local/state/hass/backups --writer --model http://127.0.0.1:11434 --host-dir ~/.local/state/hass/host` | `"ok": true`, `"problems": []`, exit 0 (this is what it printed at 14:40). `info` may list `paused`: a paused system is a NO-GO until Mike sends `resume changes` | yes | yes |
| P-7 | Owners list right (without printing numbers) | health `settings` check passes in P-6; then three live texts, see P-15 | Mike's phone: reply. G's phone (it is in `gSenders`, never an owner): `problems` answered only in G's own chat. A third phone: no reply and no draft. G opens `~/.local/state/hass/state/config.json` privately and confirms `ownerSenders` = Mike's number, `ownerChat` = the one-to-one chat with Mike, `gSenders` = G, `gChat` = G's own chat, `approvalTtlSeconds` is long enough for Mike to read (3600 in the runbook) | yes (**G**) | - |
| P-8 | Interpreter on the GPU route | `curl -s -m 5 http://127.0.0.1:8010/v1/models` and `nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv` | the router answers with a model list that includes `qwen3.8:27b-thinkingcap-q6`; GPU memory shows the model loaded. (If the router has no `/v1/models`, use the router's own status page; do not restart it.) | yes | yes |
| P-9 | CPU fallback available (not proven) | `ollama list` and the P-6 `--model` check (it already tests `/api/tags`) | `qwen3.6:35b-a3b-64k` is listed; health has no `model` problem. State plainly in the go/no-go notes that fallback has never been run: if the GPU fails, replies take 25-90 s | yes | yes |
| P-10 | Full test battery passes at the exact R | in a separate scratch checkout, **never** the runtime worktree (a dirty runtime makes the host refuse to start): `git -C ~/.local/share/hass/avocado-shack worktree add --detach ~/agent-work/hass-store-test-R <R>` then in it `python3 -B hass/acceptance.py` and `python3 -B -m unittest discover -s hass/tests -t .` (about 20 minutes serial; CI splits it in four shards) | `acceptance.py` prints no `fail`; unittest ends `OK` with 0 failures and 0 errors. Skips are listed on the card. Remove the worktree afterwards (`git worktree remove`) | yes | - |
| P-11 | Pillow at the pinned version | `~/.local/share/hass/venv/bin/pip show Pillow` and `systemctl --user cat hass-worker` | `Version: 12.0.0`; and the service's `ExecStart` really uses `.../venv/bin/python3` (the template in `deploy/hass` still says `/usr/bin/python3`: PILLOW-HOST.md step 3 must have been done, and the worker restarted afterwards) | yes | - |
| P-12 | Picture guard test | from a scratch checkout: `~/.local/share/hass/venv/bin/python3 -B -m unittest discover -s tests -p test_pillow_ci.py -v` | `OK`. (If R has no house-style picture code this guard may not exist; note it and use variant B of step 1.) | yes | - |
| P-13 | Mac forwarder and BlueBubbles up | **G (Mac)**: `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py check --config ~/Library/Application\ Support/HassForwarder/config.json` | `{"reachable":2}`. Also `launchctl list | grep hass-forwarder` shows it loaded. If tapbacks are on: `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py ackcheck --config ~/Library/Application\ Support/HassForwarder/config.json` shows `"tapbackPossible": true` | yes | yes |
| P-14 | The 2026-11-08 lesson: restart Messages and BlueBubbles before the day | **G (Mac)**: quit Messages and BlueBubbles; open Messages first, wait until it shows the business account signed in; then open BlueBubbles, wait until it shows connected; then `launchctl kickstart -k gui/$(id -u)/com.avocadoshack.hass-forwarder`; then repeat P-13. (Source: the card text, not a repo document; no write-up of that incident was found. Operator: please link it here.) | `{"reachable":2}` after the restart; do it Monday 07:15 even if Sunday looked fine, then do not touch the Mac again unless something breaks | yes if it failed | **yes, always** |
| P-15 | A real round trip, fast | Mike texts `status` from his phone; the operator reads the stage log: `python3 -B ~/.local/share/hass/runtime/hass/stagelog.py ~/.local/state/hass/host/stages.jsonl` (add the Mac's `spool/stages.jsonl` after copying it over by Taildrop for the full picture) | thumbs-up (if on) and one reply in 10 s or less; `webhook-in` or `accepted` present; `reply-pulled` follows `reply-queued` within a few seconds | yes | yes |
| P-16 | Approvals mode and the stop file | `grep -o '"approvals": *"[a-z]*"' ~/.local/state/hass/host/host.json` and `ls ~/.config/hass/STOP` | Sunday night after the harmless change: `"approvals": "live"`; `ls` says no such file | yes | yes |
| P-17 | Live publishing set up (G, runbook 20-22) | steps 20, 21, 22 of `docs/hass/MAC_RUNBOOK.md` (copy-paste list in section 7); then `python3 -B ~/.local/share/hass/runtime/hass/publish_live.py status --host ~/.local/state/hass/host/host.json` | JSON with the live baseline present, **no open release**, daily-cap usage shown | yes (**G**) | status again |
| P-18 | Live publish proven with a harmless change | Sunday ~20:00, **G and Mike** together: Mike texts one tiny home page wording change (the runbook suggests the headline; a one-word change to the intro is smaller), `yes <code>`; wait for "Now showing on theavocadoman.com" with a picture; G looks at the site on a phone; operator runs `publish_live.py status` | "Saved", then "Now showing", picture present, site shows it, status: no open release | yes | - |
| P-19 | Revert of the last live change proven | right after P-18: Mike texts `undo`, then `yes <new code>`; wait for "Now showing"; G looks at the site | the wording is back exactly as before; status: no open release. This is the verified revert; it uses the same release path, so it is exempt from the daily cap but not from STOP | yes | - |
| P-20 | Fresh backup of Hass state, verified | `python3 -B ~/.local/share/hass/runtime/hass/statebackup.py create --state ~/.local/state/hass/state --out ~/.local/state/hass/backups`, then `... statebackup.py list --out ~/.local/state/hass/backups` and `... statebackup.py verify <newest hass-state-... folder>` | `create` reports a new folder (`busy`: retry later; `unsettled`: `editor.py recover` after `stop changes`, then retry); `verify` says `ok`; the folder's `complete` is true | after P-19 | 07:45 again |
| P-21 | Known-good site commit written down | `git -C ~/.local/share/hass/theavocadoman-site rev-parse HEAD` and `git -C ~/.local/share/hass/theavocadoman-site ls-remote origin refs/heads/main` | both print the same 40-character commit. The operator writes it on the card as **GOOD-SITE-COMMIT** (a commit id is not a secret) and in the FOR-G page | after P-19 | check it still equals the remote's main |
| P-22 | Host config backed up before any edit | `cp -p ~/.local/state/hass/host/host.json ~/.local/state/hass/host/host.json.bak-store-test` | file exists, mode 600 (`stat -c %a`) | yes | - |
| P-23 | Site is up and unchanged | `curl -sI https://theavocadoman.com` | `HTTP/2 200` (or 301 then 200) | - | yes |
| P-24 | Nothing is stuck | `python3 -B ~/.local/share/hass/runtime/hass/inbox.py status --state ~/.local/state/hass/state` and `publish_live.py status` | inbox: none pending; publishing: no open release; STOP absent | yes | yes |
| P-25 | The GPU is quiet | ask the fleet operator to hold bulk local-worker jobs from 08:30 to 11:00 Monday (a request, not an action here); then `nvidia-smi` | no other job generating when the visit starts. A Hass call that lands behind a fleet generation waits 3-9 s and can wait about 55 s before the CPU fallback fires (INTERP-OPENAI-1) | - | yes |

A read-only extra the operator can run any time: `bash ~/.local/share/hass/runtime/scripts/hass/live_selftest.sh --synthetic-only` (synthetic data only; restarts and sends nothing). Without `--synthetic-only` it also reads services, timers, health and disk and prints one `PASS|WARN|FAIL` line each.

## 3. GO / NO-GO

**GO LIVE only if all five are green at 08:00 Monday** (the same five lines go on the card):
1. **Setup**: P-17 and P-18 done, P-19 proven: live publishing works and the revert was seen working on the real site; STOP absent, no open release, daily cap not used up (at least 6 left).
2. **System**: P-1 to P-6 and P-24 green (R frozen and clean, services active, `health.py` ok and not paused, inbox empty).
3. **Phone**: P-13 `{"reachable":2}` after the Monday restart (P-14) and P-15 a `status` reply from Mike's phone in 10 s or less; owners right (P-7).
4. **Model and pictures**: P-8 GPU route answering, P-9 fallback present, Pillow 12.0.0 (P-11); in the last 10 interpreter calls (audit script in section 5) none fell back and the slowest was under 15 s.
5. **Safety net**: P-10 battery green at the same R, P-20 backup verified this morning, P-21 GOOD-SITE-COMMIT recorded and equal to the remote, and G and the operator both reachable by phone for the whole visit.

**DROP TO PRIVATE ON THE SPOT** (operator or G, no discussion; section 4, K2) if any one of these happens during the visit:
- Hass says something is done, saved or live when it is not, or the site does not show a change that Hass said is showing.
- A change is applied that Mike did not approve with its code, or it touches something Mike did not name.
- A reply or draft contains a fact Mike did not give (a farm, "organic", a price, a distance, seats) and Mike's `no` does not stop it.
- A release goes `not-published`, `unknown` or `unconfirmed`, or "Now showing" arrives without its picture.
- Two replies in a row take longer than 60 seconds, or two in a row run on the CPU fallback.
- The Mac is silent for 5 minutes (no reply to `status`) after one restart of Messages and BlueBubbles, or a stranger gets a reply.
- A photo with a person, a receipt or a private place is about to be published.

What **private mode** means for Mike: nothing changes on the website any more. Hass still reads his texts, makes drafts and result pictures, and `yes` still applies to the private working copy, so he can finish the demonstration. Tell him: "These changes are not on the website. Graham will decide later what to publish." Changes made in private are **not** automatically published later; getting them on the site afterwards is an attended step by G (the `baseline` path in runbook step 21) or they are left as the rehearsal record. Do not promise Mike they will appear. To go back to live after a drop, G only: settle any open release first (`publish_live.py status`, then K3/K4 as needed), re-run P-4, P-6, P-13, then switch back.

**Pause without dropping** (Mike's own brake): `stop changes` stops every approval from applying; `resume changes` lets them apply again and never applies a waiting draft by itself. Use it when someone just needs a minute.

## 4. THE KILL SWITCH AND ROLLBACK

All four run on AgentOrange unless said. Nothing here deletes a backup or a journal, and nothing is a force-push.

| | What | Command | Who | Time | After it, check |
| --- | --- | --- | --- | --- | --- |
| K0 | Instant brake from the phone | Mike (or G, from beside him) texts `stop changes` | Mike, G | seconds | `status` says changes are paused; `resume changes` undoes it |
| K0b | Instant brake on publishing | `touch ~/.config/hass/STOP` (undo: `rm ~/.config/hass/STOP`) | operator | seconds, no restart | `publish_live.py status`; careful: STOP **before a push** holds the saved release **open**, and an open release refuses every later change until G settles it. STOP **during** a push cannot recall it. Use K0 first when you can |
| K1 | **Stop all changes** (approvals hold) | `sed -i 's/"approvals": *"[a-z]*"/"approvals": "hold"/' ~/.local/state/hass/host/host.json` then `systemctl --user restart hass-worker` then `python3 -B ~/.local/share/hass/runtime/hass/host.py check --host ~/.local/state/hass/host/host.json` | operator (G may ask for it) | about 10 s | `check` says ok; the same grep as P-16 prints `hold`; mode is still 600; Mike's `yes` now applies nothing; chat still answers |
| K2 | **Return to private mode** | the same `sed` with `"private"` instead of `"hold"`, then `systemctl --user restart hass-worker` and the `host.py check` | operator | about 10 s | grep prints `private`; a small test change shows a draft, a result picture, **no** "Now showing" |
| K3 | **Revert the last live change** | Mike texts `undo`, then `yes <new code>` (a bare `undo` takes the latest change; the draft says in plain words what comes back). Then the operator checks `python3 -B ~/.local/share/hass/runtime/hass/editor.py history --state ~/.local/state/hass/state --limit 3` and `publish_live.py status` | Mike types it, operator watches | 1-3 min (a live publish) | the site shows the earlier text; no open release; `history` shows it undone. Refused if a later edit changed the same store detail ("undo the newer one first"). Undoing an added hike leaves a visible "cancelled" card, not an empty page |
| K4 | **Restore the site to a named commit** | by hand, by G or by the operator while G watches, only if K3 cannot fix it. (1) `touch ~/.config/hass/STOP` (2) `git -C ~/.local/share/hass/theavocadoman-site fetch origin` (3) `git -C ~/.local/share/hass/theavocadoman-site log --oneline origin/main -10` and confirm GOOD-SITE-COMMIT is in it (4) `git -C ~/.local/share/hass/theavocadoman-site revert --no-edit <GOOD-SITE-COMMIT>..HEAD` (5) `git -C ~/.local/share/hass/theavocadoman-site push origin HEAD:main` (a normal push, **never** `--force`) | G (live site) | 2-5 min plus the site's own deploy | `curl` and your eyes on theavocadoman.com; then, still attended, `publish_live.py resolve <change id> --as reverted` and the writer reconciled (`publish_live.py unblock` only after the writer was undone privately and equals the baseline); keep the journals. Unknown is not success |
| K4b | Fastest visual rollback (if K4 is too slow) | G in Cloudflare Pages: the project's deployment list, the last good deployment, Rollback (label UNVERIFIED in the runbook step 23). It shows the good site in about a minute but is overwritten by the next deploy, so do K4 after | G | 1 min | the site looks right |

Who may press what, as proposed here for G to confirm: **stopping** (K0, K0b, K1, K2) can be done by Mike, G or the operator at once without asking; **going back to live** after any stop (K1/K2 → `live`, removing STOP) and **touching the live site** (K4, K4b, `retry`, `resolve`, `baseline`) is G only. Reasoning: every stop reduces exposure; everything else can publish.

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
3. **The problems log.** G texts `problems` from G's phone (answers only in G's own chat, text only) after step 3 and after step 7 and reads the last ten moments: did not understand, could not do, asked again, slow reply, wording check fallback, Mike said no or "that's wrong". `weekly` gives the three most common with one suggested fix each. The operator may only count lines in `~/.local/state/hass/state/correspondence/` (newest `<day>.jsonl`; at most 80 characters of Mike's words each, numbers blanked; never copy these files off the box). More than two "did not understand" in a row = tell G; the third is a drop-to-private candidate if Mike is getting frustrated.
4. **Health and publishing.** The 5-minute health timer writes an ALERTS line only when the set of problems changes. Add by hand: `python3 -B ~/.local/share/hass/runtime/hass/health.py --state ~/.local/state/hass/state --backups ~/.local/state/hass/backups --writer --model http://127.0.0.1:11434 --host-dir ~/.local/state/hass/host` and `python3 -B ~/.local/share/hass/runtime/hass/publish_live.py status --host ~/.local/state/hass/host/host.json` after each "Now showing". The ones that page G: `release-open`, `release-books`, `live-unconfirmed` (card, admin) and `mac-silent` over 2 hours (hardware).
5. **Service log.** `journalctl --user -u hass-worker -n 40 --no-pager` (no message text is printed). A restart loop or a traceback = K1.

## 6. FALLBACKS

| If | What Mike sees | What happens next |
| --- | --- | --- |
| **The Mac mini or iMessage fails** (no thumbs-up, no reply after 60 s; `mac-silent` in health; `outbox-stuck`) | nothing comes back, or a reply arrives late starting `Late reply to your message from <day> <time>:` | Tell him: "Wait, don't send it again; I'll fix the phone side." **G (Mac)**: restart Messages, then BlueBubbles, then `launchctl kickstart -k gui/$(id -u)/com.avocadoshack.hass-forwarder`, then `check` = `{"reachable":2}` (P-14). The inbox keeps his messages and the replies are re-sent without duplicates (tested: reply retry without a duplicate). Back in 10 minutes: carry on from the step that was open, and ask him to send `status` first. Not back in 10 minutes: K1 (hold), then the demonstration continues **without the phone**: the operator runs Mike's messages through the scratch rehearsal copy (as in P-0, nothing live), or G makes the same change the normal way (the site's own repository and its usual deploy) while Mike watches. No texting from G's own phone as a stand-in: it is not an owner |
| **The GPU model is busy or down** | a slow reply (the thumbs-up comes first). Up to about 55 s behind a fleet job; after the 60 s limit the CPU model answers in 25-90 s, with `status`, `yes`, `undo`, `listing`, `find`, `report` unaffected (they do not call the model: 1 to 3 s) | Under 60 s: nothing to do, Mike waits. Over 60 s twice in a row: use the no-model steps first (step 2 `listing`, step 7 `undo`, `status`) while the operator checks `nvidia-smi`, the audit script and who holds the GPU; do not restart the router or Ollama (not allowed without G). Still slow after 10 minutes: drop to private (K2) so a slow model cannot delay a live publish |
| **The picture cannot be restyled** (house-style picture missing in R, Pillow missing, render fails) | no new look for the photo: the draft shows his original photo upright, or a plain "I couldn't make the picture look right" style message; never a fake success | The product still goes up with his original photo if he approves the draft; the picture is a nice-to-have. If the draft has **no picture at all**, that is the live-mode rule "no picture, no live" (runbook: live mode requires picture delivery): K2 private and carry on |
| **The live publish fails** (reply says saved but not on the website yet, no "Now showing", or a G card `release-open` / `live-unconfirmed`) | "Saved" and then, if it fails, a plain message that it is saved but not on the website yet (never "live") | Tell Mike: "It's saved, it isn't on the site yet. Don't send the next one." Operator: `publish_live.py status`. **G, by hand**: `not-published` → `python3 -B ~/.local/share/hass/runtime/hass/publish_live.py retry <change id> --host ~/.local/state/hass/host/host.json` once, only if the remote does not already have it; `unknown` or `unconfirmed` → look at the live page by eye, then `resolve <change id> --as live` or `--as reverted` (reverted needs the remote at the old head); not resolvable in 5 minutes → K2 private and K4 if the site is wrong. An open release blocks every later change, so the rest of the script continues in private mode |
| **The site is wrong in public** | n/a | K3 first; if it cannot, K0b then K4b then K4, in that order; G only |

## 7. TIMELINE: who does what

Times are PST. The store visit time is not in the card: `<visit time>` below. Mike's tasks need no tools, only his phone.

**Sunday 2026-11-08 (tonight)**
| Time | Who | What |
| --- | --- | --- |
| 15:00 | operator | Freeze R: record which of PRs 504, 525, 526, 529, 530, 531, 532 are merged and which commit is R; if R is newer than `0a8114c`, schedule the planned runtime move (new detached worktree, `runtimeCommit`, restart) for before 18:00. P-0 scratch rehearsal starts |
| by 17:00 | **Mike** | Picks the real things: one product with its real maker and town (in his own words, on paper), one item that is really sold out, a real weekly special, a real hike (or says skip), the notice text. Takes the photo: upright, plain background, nobody in it. Sends **nothing** yet |
| 17:00-18:30 | **G** | Runbook steps 20-22 (list below). If step 19 (private mode with a result picture) was never done, do that first: set `private` (K2 command), Mike approves one tiny change, a picture comes back, then `undo`. Stop and tell the operator at any unexpected result; do not retry an old code |
| 18:00 | operator | R frozen. P-1, P-2, P-3 |
| 18:30-19:30 | operator | P-4 to P-12, P-22; P-10 battery runs in the background |
| 19:30 | **G (Mac)** | P-13, P-14 |
| 20:00-20:30 | **G + Mike** + operator | P-15, then P-18 (harmless live change) and P-19 (undo). Mike needs about 15 minutes at his phone |
| 20:30 | operator | P-20 backup, P-21 GOOD-SITE-COMMIT, P-24 |
| 21:00 | operator | **Go/no-go #1** on the card: five lines, each green or red. If steps 20-22 or P-18/P-19 are red: Monday is **private mode** (K2): Mike still sees text, photo, draft, picture, `yes`, `undo` in real time, and G is told by 21:15. No more changes to R after this |
| 21:30 | operator | Leave Hass in the mode chosen; STOP absent (live) |

**Monday 2026-11-09 (morning)**
| Time | Who | What |
| --- | --- | --- |
| 07:00 | operator | P-1, P-3, P-4, P-6, P-8, P-9, P-16, P-23, P-24 |
| 07:15 | **G (Mac)** | P-14 restart Messages and BlueBubbles and the forwarder, P-13 check |
| 07:30 | **Mike** + operator | P-15: `status` from Mike's phone, reply under 10 s, stage table read |
| 07:45 | operator | P-20 backup verified, P-21 GOOD-SITE-COMMIT still equals the remote, P-25 GPU quiet |
| 08:00 | operator | **Go/no-go #2** (the five lines in section 3), posted on the card and to G. G answers "go live" or "private" |
| `<visit time>` -15 min | operator + G | Both on the phone line, second screen open (section 5); Mike told the four ground rules |
| `<visit time>` | **Mike**, G beside | The script, steps 0-9 |
| after | operator, G | K1 hold; stage table, audit and `problems` read; card comment with what failed; site content checked true (any item that is not real is removed by an undo or by G); G decides the everyday mode |

**The minimum list only G and Michael can do (copy-paste; replace `<...>` privately, never paste a secret into chat, a card, Git or logs).**

*Michael*: (1) confirm his phone number is the one in `ownerSenders` (G checks); (2) the real details and the photo above; (3) tonight, 15 minutes: text one tiny change, `yes <code>`, wait for the picture, then `undo`, `yes <new code>`; (4) Monday: phone charged, signal in the store, Messages open, no other app that needs the Apple Account on that phone being re-signed.

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
Add the `release` block to `~/.local/state/hass/host/host.json` (keep mode 600, absolute paths, **no** `~`): `"release": {"siteCheckout":"<absolute home>/.local/share/hass/theavocadoman-site","siteRemote":"git@github-avocadoman:Grahammmm/theavocadoman-site.git","liveUrl":"https://theavocadoman.com","stopFile":"<absolute home>/.config/hass/STOP","dailyCap":10,"minIntervalSeconds":120,"verifyMinutes":15}`, then:
```sh
cd ~/.local/share/hass/runtime
python3 hass/publish_live.py adopt --host ~/.local/state/hass/host/host.json
python3 hass/publish_live.py status --host ~/.local/state/hass/host/host.json
```
If `adopt` says `differs`: stop and ask the operator (the runbook has the `--from-remote` and `baseline --confirm` path; the confirm is a real live publication and G reads the path list first). Then edit the state `config.json` `settings` by hand: `"liveSite": "theavocadoman.com"`, `"approvalNeedsCode": true`, and (for G's problems log) `"gSenders": ["<G's address>"]`, `"gChat": "iMessage;-;<G's address>"`; set host `approvals` to `live` (the K1 `sed` with `"live"`), then:
```sh
systemctl --user restart hass-worker
python3 -B ~/.local/share/hass/runtime/hass/host.py check --host ~/.local/state/hass/host/host.json
```
*G, on the Mac mini* (P-13, P-14): quit Messages and BlueBubbles, open Messages (wait for the account), open BlueBubbles (wait for connected), then:
```sh
launchctl kickstart -k gui/$(id -u)/com.avocadoshack.hass-forwarder
python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py check --config ~/Library/Application\ Support/HassForwarder/config.json
```
Expected `{"reachable":2}`. Nothing else on the Mac is to be touched.

## 8. Open decisions and known gaps (said plainly)

1. **Live is not ready.** As of 14:40 steps 20-22 are not done and `approvals` is `hold`. Section 3 and the 21:00 gate decide Monday's mode; the honest default if G cannot finish them tonight is private mode. That is the operator's earlier advice, not a refusal of G's choice.
2. **A public site has no practice mode.** Everything in the script is seen by customers. Use only real details. If G wants a pure demonstration (a made-up hike or product), it must be private mode. Undoing an added hike leaves a cancelled hike card (E2E-HIKE-1). How undoing an added product looks on the page was not measured here: check it in the scratch rehearsal (P-0) before promising Mike that "undo" makes a new product vanish.
3. **The "skills".** The skills router (PRs 525, 526) and the hike, special and shop skills (PRs 529-531) are not in the runtime. The script works on the older plain-words path; wording of replies may differ from what the skills would say. R decides.
4. **House-style picture** is not on main. Variant B of step 1 is the default until R contains it.
5. **CPU fallback** has never run for real. The 25-90 s figures are measurements of the CPU model alone (FAST-1, MODEL-1).
6. **Private-mode changes are not published later by themselves** (section 3).
7. **Who may press K1-K4** is a proposal for G to confirm; the runbook itself says G performs every live step.
8. **Tapback (thumbs-up)** exists only if the BlueBubbles Private API (SIP off, approved by G 2026-11-08) was set up; the first sign of life may otherwise be the reply itself.
9. **Not found:** LIVE-PLAN-1, LIVE-STEPS-G-MICHAEL, APPLY-TEST-1 (not merged yet) and any write-up of the 2026-11-08 "restart Messages and BlueBubbles" incident; the P-14 wording is taken from the card text.
10. **Reply sentences** in section 1 are shapes, not quotes. P-0 (scratch rehearsal) is what turns them into quotes.
