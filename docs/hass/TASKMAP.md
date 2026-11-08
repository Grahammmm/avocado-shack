# Hass task map: every everyday job as a skill (HASS-TASKMAP-1)

Card t_b5c979c0 · repo Grahammmm/avocado-shack · written against `origin/main` 56c9070 (merge of #532) · 2026-11-08.
**Design only.** No code, service, live state, `host.json`, Mac, real owner message or finance record was touched or read. Every
Mike sentence below is synthetic. Every frequency is **ESTIMATED** (nothing is live, so nothing is measured; part 4 says how it
becomes measured). Statuses come from the repository and the PR list read on 2026-11-08, not from a run. Where something is a
design choice and not something found in code, it says "design" or "proposed".

Builds on `reports/hass/SKILLS-SPEC.md` (skill model, 32-skill catalog, D1-D9, cards 1-20). This page adds the task inventory, the
automation tiers, the cloud lane (with its money cap), the skill factory (with its export contract), a private-action contract for
the receipt ledger, and the build cards. It does not repeat the spec.

---

## Open decisions for G (part 7, placed first)

Nine decisions. Everything not listed is decided by the operator ladder.

**Building is separate from enabling.** Every card below can be designed, built and tested on fixtures and synthetic data without
an answer. An answer is needed to **turn a behaviour on**, and each of these ships **off** and stays off until the named answer is
recorded on the card (these are the existing holds, restated, not new requests):

* **Anything that leaves the box or costs money** (Tier 3 cloud jobs, cards 15-17): off until **both G1 and G9** are answered. The
  bridge is not installed and the dollar cap is `$0` (no job can be queued) until then (3.5).
* **Anything Hass starts** (the five prompts, cards 7 and 13): off until **G2**; the host's `prompts` list is empty until G names a type.
* **Finance data** (the receipt ledger, cards 8 and 10): the code ships with `ledger.enabled` false; no receipt is read or saved on the
  live box until **G3**. Nothing about finance ever leaves the box in any case (no G answer changes that).
* **Site closures** (cards 11-12): not merged to live until **G4** (and a full CI tier, as a site change).
* **Learned rules** (card 14): ships with automatic activation off until **G7**; before then rules are only suggested to the operator.
* **Order drafts** (card 9): the table shape follows **G6**; **prices** (card 18) stay unscheduled until **G8**; **G5** is wording only.

| # | Decision | Recommended | Other option | What waits |
|---|---|---|---|---|
| **G1** | May the words Mike wrote about **one item** (name, maker and place he named, his description words) and its metadata-free photo go to a cloud model for the "nicer description" and photo-plan jobs? Never receipts, orders, contacts, notes, costs, backlog text or any owner address. | **A. Yes**, only that closed list, through the operator's bridge (part 3), with a daily cap. | B. No: Tier 3 stays off and the plain template wording is final. | **BLOCKS enabling** the bridge and wiring (cards 15-17), together with G9; the plain template path is unaffected. This is an off-box export decision, G's to make. |
| **G2** | Hass may **start** a message to Mike (a reminder). | **A. Yes**, five named prompts, each off until G turns it on and Mike says `reminders on`; at most one a day; only Mike's own chat; none from 20:00 to 08:00 Pacific; `reminders off` stops all. | B. Never: Hass only answers. | Enabling cards 7 and 13 (the specials reminder is card 7). |
| **G3** | Receipts: Hass reads a receipt photo **locally** into a private ledger on the box, Mike confirms each one with `yes`. | **A. Yes**, ledger in the existing private database, nothing leaves the box, no cloud model ever sees it, no email. | B. Not now: Mike keeps receipts himself. | Enabling cards 8 and 10. |
| **G4** | A holiday closure shown on the site **ahead of time** (from 14 days before), then gone by itself. | **A. Yes**: a date-range closure, built like weekly specials. Until it exists, use the home notice (shows at once, up to 60 days). | B. Notice only, forever. | Cards 11-12 (card 11 is a site change, full CI). |
| **G5** | What Hass says when it cannot do something. | **A. "I can't do that yet. I wrote it down for Graham. Nothing changed."** Used now; the words "I've asked Graham" only after the daily digest to the board exists (card 2). | B. A real message to G's own chat for every request (a Hass-started message, outbound). | Wording only; the digest is card 2. |
| **G6** | Supplier order drafts keep **no supplier phone or email**, only the supplier's name and how Mike reaches them ("text", "email"). | **A. Yes**, no contact details stored. | B. Store contacts so the draft can show them. | Card 9's table shape. |
| **G7** | Everyday phrasings Hass learns become fast rules **by themselves** after 5 approved uses on 3 different days, stay only on the box, and are dropped after 2 corrections. | **A. Yes, automatic.** A wrong rule can only produce a draft that still needs Mike's `yes`. | B. Each new rule needs the operator's OK. | Enabling automatic activation in card 14. |
| **G8** | Prices stay as D9 says (refused, logged, counted) until the Clover answers in SKILLS-SPEC 5.2 exist. | **A. Confirm.** The weekly count of refused price requests tells G when this starts to matter. | B. A private price note per item now (never on the site). | Nothing. |
| **G9** | The **daily dollar cap** for cloud jobs (US dollars per Pacific day). It bounds all Tier 3 spend and is a prerequisite of G1: with the cap at $0 the bridge queues nothing and fails closed (3.5). This is spending, so it is G's to set. | **A. Keep $0 (Tier 3 off) until G writes one number.** No amount is invented here; the first 20 measured jobs can tune it afterwards. | B. G names the daily amount now. | Enabling cards 15-17 (with G1). |

**One finding that is not a decision.** The skill modules merged so far (items, makers, stock, the model, the test kit, the backlog)
are **not reachable from Mike's messages yet**: `hass/conversation.py` on main does not mention skills. They become reachable when
**SKILLS-FW-2 (#525) and SKILLS-FW-3 (#526) merge**. Until then Mike's messages still go through the raw interpreter, as today.
Both PRs are open; read on 2026-11-08, #525 had one failing check beside passing ones and #526 was all green. Merging them is the
critical path for everything below.

---

## 1. Task inventory

Grouped by how often Mike plausibly does them. **Freq** is ESTIMATED for a small food shop with a hiking club (nothing measured: no
approvals are live, so `history` has no counts). **Input**: T text, P photo, D forwarded document. **Changes**: S site content,
V private record on the box, M a message to someone (always a draft Mike sends himself; Hass sends nothing to anyone else).
**Status** (from the repo and PR list): `merged` skill module on main (not yet reachable from chat, see above), `PR` skill in an open
PR, `cmd` a merged owner command that already works as a command, `raw` only the raw interpreter handles it today (works, less
reliable, not measured per task), `designed` in SKILLS-SPEC only, `new` designed in this page only, `refused` Hass says it cannot.

### Daily

| # | Task | Mike might say | Freq | In | Changes | Skill | Status |
|---|---|---|---|---|---|---|---|
| T01 | Mark items sold out, low, back in stock | "eggs are out", "got more honey in" | several times a week, most shop days | T | S | `stock.set` | merged (#532) |
| T02 | Shelf check ("I checked the shelves") | "shelves are all good today" | each shop day | T | S (check date) | `stock.checked` | merged (#532); the shelf question flow merged (#517) |
| T03 | Morning report, what is low, anything waiting | "report", "what's sold out" | daily | T | none (reply) | `report.shelf` | `cmd` (`report`); skill wrapper not built (SOCIAL-1) |
| T04 | Quick notice | "closed early today", "back at 2" | 1-4 a month | T | S | `shop.notice` | PR #531 |
| T05 | **Receipts and expenses** | (receipt photo) "supplies" | several a week | P or D | V | `receipt.add` | **new** (part 5.1) |
| T06 | A question about the site | "what time do we close Saturday" | a few a week | T | none | `answer.site` | raw (answers from the prompt); skill not built |
| T07 | Safety commands: status, history, undo, find, hidden, pause | "undo", "status" | a few a week | T | S (undo) | commands | `cmd`, merged |

### Weekly

| # | Task | Mike might say | Freq | In | Changes | Skill | Status |
|---|---|---|---|---|---|---|---|
| T08 | **Add a new item** (photo, words, maker) | (photo) "new honey from Cal Poly, pantry" | 2-10 a week at restock, more at launch | P+T | S | `item.add` | prototype PR #504 (open, one failing check read 11-08); card not started; needs PIC-1 |
| T09 | **Weekly specials** (add, edit, remove, clear finished, show) | "salmon special Friday to Sunday, 2 for 1" | weekly | T | S | `specials.*` | site merged (#520); skill PR #529 |
| T10 | Specials reminder: "any specials this week?" | (Hass starts it) | weekly | none | M (to Mike) | `prompt.specials` | **new** (part 5.6) |
| T11 | Add a hike | "hike Sat 9am Cass Hill gate, easy" | 2-4 a month | T | S | `hike.add` | PR #530; open-ask flow merged (#515) |
| T12 | Move or cancel a hike | "cancel Saturday, rain" | 1-3 a month | T | S | `hike.reschedule`, `hike.cancel`, `hike.edit`, `hike.repeat` | PR #530 |
| T13 | Post-hike recap | "went great, 12 people" | after each hike | T | S | `hike.recap` | PR #530 |
| T14 | Social post for a new item | "post the new honey" | about weekly | none | M (draft) | `social.item` | `cmd` (`post <item>`); skill not built (SOCIAL-1); new-item wording **new** |
| T15 | Social post for a hike (announce, recap) | "post the Cass Hill hike" | per hike | none | M (draft) | `social.hike`, `social.recap` | announce `cmd` (`post hike`); recap draft not built (SOCIAL-1) |
| T16 | **Supplier order draft** | "order 4 dozen eggs and 6 honey from Linn's" | about weekly | T | M (draft), V | `order.draft` | **new** (part 5.2) |
| T17 | Replace an item's picture | (photo) "new photo for the sourdough" | weekly | P | S | `item.picture` | raw (`product.set_photo`); card not started |
| T18 | Edit an item's name, text, shelf, maker | "change the jam text to ..." | weekly | T | S | `item.edit` | merged (#527) |
| T19 | Hide or bring back an item | "we stopped carrying X", "X is back" | weekly | T | S | `item.hide`, `item.restore` | merged (#527) |
| T20 | Which items still need a real photo | "photos to take" | weekly | T | none | command | `cmd` |

### Monthly

| # | Task | Mike might say | Freq | In | Changes | Skill | Status |
|---|---|---|---|---|---|---|---|
| T21 | Store hours change | "Fridays we close at 6" | 1-2 a month | T | S | `shop.hours` | PR #531 |
| T22 | Month-end expense totals | "expenses for October" | monthly | T | none (private reply) | `expenses.show` | **new** (part 5.1) |
| T23 | Add or edit a maker and their about text | "add Bee Happy Farm, Atascadero" | 1-3 a month | T | S | `maker.add`, `maker.edit` | merged (#528) |
| T24 | Stop carrying a maker, bring one back | "we dropped Etto" | rare, about monthly | T | S | `maker.hide`, `maker.restore` | merged (#528) |
| T25 | Home page words and the store story | "change the intro to ..." | monthly or less | T | S | `page.home`, `page.about` | PR #531 |
| T26 | **Price change** | "eggs are $6.50 now" | weekly to monthly | T | nothing today | `price.change` | `refused` (D9); gated until Clover (part 5.5) |
| T27 | Counts ("how many eggs do we have") | "how many eggs" | occasional | T | none | none | `refused` (no counts exist; says the last check) |
| T28 | Contact: phone or street address | "new number is ..." | rare | T | S | `shop.contact` | PR #531 (live release is G's by hand) |

### Seasonal

| # | Task | Mike might say | Freq | In | Changes | Skill | Status |
|---|---|---|---|---|---|---|---|
| T29 | **Holiday closure, a date range** | "closed Dec 24 to 26" | 4-8 a year, announced weeks ahead | T | S | `shop.closure` | **new** (part 5.4); the home notice covers one at a time now (PR #531) |
| T30 | Holiday or seasonal hours | "winter hours: 10 to 5" | 2-4 a year | T | S | `shop.hours` | PR #531 |
| T31 | Seasonal items in and out, in bulk | "hide all the pumpkin stuff" | 4 times a year, many items | T | S | `item.hide` (shelf limit 6) | merged; the bulk case asks with the count |
| T32 | Home photo for the season | (photo) "new home photo" | 2-4 a year | P | S | `page.photo` | PR #531 |
| T33 | Repeat last year's hike | "do Cass Hill again on the 29th" | seasonal | T | S | `hike.repeat` | PR #530 |
| T34 | Holiday question from Hass ("Thanksgiving is the 26th: open?") | (Hass starts it) | a few a year | none | M (to Mike) | `prompt.holiday` | **new** (part 5.6) |

### One-off

| # | Task | Mike might say | Freq | In | Changes | Skill | Status |
|---|---|---|---|---|---|---|---|
| T35 | Add an FAQ, a new page, a gift page, a logo, a blog | "add an FAQ" | rare | T | nothing | `page.faq` | `refused` (merged #516: says so and logs it) |
| T36 | Message hike sign-ups or customers | "tell the club about Saturday" | occasional | T | nothing | none | `refused`: Hass sends nothing to anyone; no email is connected |
| T37 | Sales questions | "what did we sell this week" | occasional | T | none | none | `refused` until the POS gate (SKILLS-SPEC section 5) |
| T38 | Notes, nicknames, costs, margin arithmetic | "remember parking: back lot" | occasional | T | V | commands | `cmd`, merged |
| T39 | Add a second owner number, change the config | n/a | rare | n/a | none | none | operator only, not a skill |

Of G's seven named jobs, four have skill code on main or in an open PR: add an item (a prototype, #504), weekly specials (#529),
hikes (#530) and hours and notices (#531). Social drafts work today only as the commands `post` and `post hike`. Three things
had **no skill design at all** until this page: receipts and expenses (T05, T22), supplier orders (T16), and the Hass-started
prompts (T10, T34); holiday closures as a date range (T29) are also new. Prices (T26) are designed and gated.

---

## 2. The automation tier for each task

### 2.1 The three tiers, as built

```
Mike's iMessage (text, photo, forwarded file)
  -> Mac forwarder -> receiver on the box (existing, merged)
  -> Conversation: whole-message commands first (existing: yes/no/undo/status/report/post ...) -- no model at all
  -> TIER 2a  rule match (design, from part 4): a stored pattern picks the skill and fills slots -- no model, milliseconds
  -> TIER 2   local model (GPU Qwen via the router, about 1 s; CPU Ollama fallback): picks ONE skill and fills slots
                with Mike's words; never edits; `none` or unreadable -> the backlog, nothing changes
  -> TIER 1   the skill: fixed slots, code validates, ONE deterministic plan -> editor.prepare -> claims gate
                -> preview -> "yes <code>" -> apply -> undo.  Plain code. This is where the change is made.
  -> TIER 3   (only when a skill declares an `assist` step) a cloud model returns a PROPOSAL, never a change;
                the skill's code validates it and uses it as a slot value.  Part 3.
```

Rules that make the tiers safe (design): a skill never calls a model itself; the model never sees the editor, a path or a command;
Tier 2 and Tier 3 may only produce **slot values** that Tier 1 code validates; a skill that touches private records declares
`data_class` (new field, card 1) and the lint refuses a private-data skill that declares any cloud step; the interpreter client
already refuses a non-loopback URL (`interpreter_local.py`), so no Tier 2 call can leave the box by construction.

### 2.2 Tier per task, and what stays manual first

Tier shorthand: **1** a command or rule is enough once phrasings are learned (the model is skipped); **1+2** needs the local model
to read his words (until a rule covers them); **1+2+3** a creative step a rule cannot do. "Manual first" is what happens until the
skill exists: P = Mike does it himself on his phone or the site's own tools; O = the operator does it by hand through the manual
lane (2.3); G = G decides first.

| Task | Tier | Why | Manual first, and who |
|---|---|---|---|
| T01 stock | 1 (after rules), 1+2 now | a closed vocabulary: product, in/low/out; rules will cover most phrasings | raw interpreter works today (P) |
| T02 shelf check | 1 | "yes" to a fixed question, a fixed command | works today (`report`, shelf question) |
| T03 report | 1 | a fixed read-only command | works today |
| T04 notice, T21 hours, T30 | 1+2 | free words ("back at 2"), but 3 slots | raw interpreter today (P); O if it fails |
| T05, T22 receipts | **1+2 (local vision only), never 3** | reading a photo needs a vision model; finance data never leaves the box | P: Mike keeps the paper or the photo. O/G: none |
| T06 site questions | 1+2 | answered from the generated tables only | raw interpreter (P) |
| T08 add item | **1+2+3 (3 optional)** | the picture is Pillow code (no model); the description has a deterministic template; only the *nicer* house-voice sentence needs Tier 3 | today: `product.add` raw path or #504 prototype by hand (O) |
| T09 specials | 1+2 | free text title and deal line, fixed dates | raw ops (P) |
| T10, T34 prompts | 1 | a schedule and a fixed sentence; the answer is read like any message (1+2) | none; G decides (G2) |
| T11-T13, T33 hikes | 1+2 | slots (day, time, meeting point) are his words; no invention allowed | raw interpreter works but invents fields (E2E-HIKE-1); O when it does |
| T14-T15 social | 1 (templates) | a caption is a template over stored facts: `social_draft.py`; Hass never posts | works today for `post` and `post hike`; recap wording by hand (O) |
| T16 supplier orders | 1+2 | his own item and quantity words in a fixed message; local model reads the list | P: Mike writes his own message |
| T17 picture swap | 1+2 (+3 plan, optional) | Pillow render; a cloud "photo plan" (subject box) only when the render cannot find the subject | `photos to take` (cmd) then raw (O) |
| T18-T19, T23-T25, T31-T32 | 1+2 | slots from his words | merged skills, raw interpreter until FW-3 |
| T26 prices | none today | policy D9 | refused, counted |
| T27, T35-T37 | none | no counts, no pages, no sending, no sales data | refused and logged (`backlog.log`) |
| T29 closure | 1+2 | two dates and a label | home notice (P), or O |
| T38 notes | 1 | commands | works today |

Tier 3 is therefore used in **one skill family** (T08 and T17), and only for two jobs: the nicer description sentence and a photo
plan. Everything else, including every item in Mike's list, reaches "no model needed after the phrasing is learned". Two honest
limits: (a) **understanding a new phrasing is always a model's job** until a rule has been learned for it; (b) **reading a receipt
photo is always a model's job** (a local vision model; a plain OCR route could be tried later and measured, never assumed).

### 2.3 "I can't do that yet" path: how a request reaches G, what the operator does, how it is recorded

1. **Hass's reply (truthful, voice rules).** Nothing fits, the model says `none`, a policy blocks it, or three questions got nowhere:
   "I can't do that yet. I wrote it down for Graham. Nothing changed." (G5). Hass does not say "I've asked Graham" unless step 3b
   exists, and promises no time. This is `backlog.log`, merged (#516), plus the plain wording merged in VOICE-1.
2. **A row** in the private `backlog` table (merged): reason, a one-line summary (what the model said was asked), Mike's text kept
   privately for 90 days, a state. **The summary and the text never leave that table**: no digest, report, card, trace or git file
   carries them (the export contract, 4.4; the merged table stores a model-written summary and, when none is given, the first 160
   characters of Mike's own words, with no privacy filter, so nothing may read those columns into an export). The weekly report
   counts the same request seen again within 7 days by a closed **task code** (4.4), not by summary words; no schema change.
3. **How it reaches G.** (a) *Pull, exists today:* G-only `problems` and `weekly` in G's own chat (merged #523: "could not do" is
   one of the counted kinds). (b) *Push, design, card 2:* one operator-owned timer reads `python3 hass/skills/factory.py digest
   --state DIR`, which prints **only counts by reason, task code and day** (4.4; never Mike's text, never a summary), and updates
   one internal Hermes board card per day ("HASS-BACKLOG digest"). It is a digest, not a Telegram alert. Hass itself sends G nothing.
4. **What the operator does by hand (the manual lane).**
   * *A site change the existing ops can express* (for example something unusual about one item): the operator prepares it as an
     **ops draft** through the same editor and a normal validation, and Mike approves it with his own `yes <code>` in his chat.
     That hand-off needs the proposal ingest of card 5 (HASS-MANUAL-1). Until it exists the operator does **not** apply anything
     for Mike; G tells Mike how to do it (or to send it differently), which is why card 5 is early in the order. (This is the
     one place "we will do a lot manually at first" is limited: for a site change the only approved writer is a draft Mike
     approves in his chat, so the manual lane needs a way to put the operator's draft in front of him.)
   * *A private or message task* (an order text, a receipt): Mike does it himself; G or the operator may show him the wording.
   * *Policy refusals* (price, page, sales data, sending): never done by hand; they become G decisions (this page's G8, the POS gate).
5. **How the steps are recorded so it becomes a skill candidate.** The operator runs `factory.py trace add` (card 2). A trace is
   one private JSON line on the box (`<state>/factory/traces.jsonl`, 0700, not in git, not in the backup): backlog number, the
   candidate skill name, **slot names and kinds only (no values)**, the ops used (names and argument names), the question **codes**
   that were needed, which slot Mike corrected (a name and a count, never his words), minutes spent, whether a rule alone could do
   it, its `data_class`, and 3 to 10 **synthetic** example sentences the operator wrote (never copied from Mike; none at all when
   the candidate's `data_class` is not `site-public`). Only the export-checked view of a trace (4.4) may go to a card or git.
   Two traces of the same candidate, or one trace plus 3 backlog rows in 4 weeks, put it on the weekly ranking (part 4).
6. **When the skill ships**, its backlog rows close, and Mike hears about it once, inside his next ordinary reply ("By the way, I can now
   do X: just say ..."). That is a tip inside an answer, not a message Hass starts.

---

## 3. The cloud dispatch design (Tier 3)

### 3.1 Principles

1. **No credential, no network, no cloud name inside Hass.** Hass writes a job file and later reads a proposal file, in a private
   spool folder. Everything that touches the cloud is the host's **operator-owned bridge** (a script and timer the operator
   installs; not part of the Hass runtime). Hass cannot reach it except by the files.
2. **The model returns a proposal, never a change.** The proposal is untrusted data like a photo caption. Hass validates every
   field and uses it only as a slot value; the skill's plan, the editor, the claims gate, the preview, `yes <code>` and `undo` are
   unchanged. A proposal is **machine-valid, not accepted**: Mike's `yes` is the acceptance, and the draft says it wrote the words.
3. **Never in the routing path.** The cloud is called only after Tier 2 chose the skill, every required slot validated and the skill
   declared an `assist` step. Nothing Mike types can name a profile, a model or a lane.
4. **Mike never waits on it for long, and never loses his request to it.** A plain template draft always exists as the fallback.
5. **Allowlist, not blocklist.** The brief is built by code from a closed field list per kind. Anything not on the list cannot be
   sent. Finance, orders, contacts, notes, costs, backlog text, the sender and chat ids, other owners' messages, and any path are
   not on any list.

### 3.2 The flow, step by step

```
item.add (slots complete: photo, name, maker, place, shelf)            [Tier 1 code, in Hass]
 1. code builds the template description and the house render         -> a complete fallback draft now exists
 2. skill declares assist(kind="item.description"); Hass checks: G1 on? bridge alive? cap.json shows the day open (cap above $0, room left)?
      no  -> go straight to the template draft, say so in plain words (3.4)        [no waiting]
      yes -> reply "Working on it. This usually takes about a minute."
 3. Hass writes cloud/outbox/<job_id>.json (+ the photo copy) atomically; the request stays open, state `waiting`
 4. BRIDGE (operator): validates the job against its OWN schema and allowlist, RESERVES the attempt's cost against its own spend
      ledger under a lock (3.5; refuses if unknown or over the cap), creates a Hermes card for the lane's named profile,
      body = fixed instruction + the brief; max runtime 300 s
 5. The profile answers by completing the card with ONE JSON proposal (<= 4 KiB)
 6. BRIDGE writes cloud/inbox/<job_id>.json {job_id, brief_sha, proposal | error}; moves the job to done/
 7. Hass (each tick) validates (3.4). Valid -> the description slot is set -> normal plan -> editor.prepare -> claims gate ->
      preview -> the usual draft, with the line "I wrote the description; change it if you like."
      Invalid -> one more try (3.6) -> else the template draft.
 8. Mike answers `yes <code>` as always. Code applied the change; the model never did.
```

Files (design). `cloud/` lives in the private state folder, 0700, never in git, never in the state backup (like the correspondence
log). Job file keys: `v`, `job_id` (`j-` + 12 hex), `created`, `kind`, `lane` (`standard` or `strong`: Hass names a lane, never a
profile or a model), `attempt` (1-3), `brief` (closed keys per kind), `brief_sha` (SHA-256 of the canonical brief), `photo` (a
metadata-free copy, at most 1 MB, 1024 px long side; only for kinds that need it), `deadline_s` (240), `reply_to`. The bridge keeps
`cloud/bridge.alive` (touched each minute; older than 3 minutes means "bridge down") and `cloud/cap.json` (`{day, cap_usd,
used_usd, open_reservations, closed}`, rewritten by the bridge after every spend event; the bridge's spend ledger is the
**authority** for the cap, `cap.json` is only a copy Hass reads so it can answer at once; missing or older than 3 minutes means
"bridge down").

### 3.3 The brief and the proposal: the contract

**Kinds (design; two only).**

| Kind | Brief (closed) | Proposal (exact keys) |
|---|---|---|
| `item.description` | `name`, `maker` and `place` (only as Mike gave them), `shelf`, `owner_words` (the words Mike wrote about the item, links and numbers blanked, at most 400 characters), `style` (the public house-style rule text and 3 public example descriptions from the live site) | `{"v":1,"job_id","brief_sha","description": str, "alternates": [str, str]}` |
| `item.photo_plan` | the photo copy, its pixel size, `style` (public numbers: 800x800, subject about 90 percent, ivory) | `{"v":1,"job_id","brief_sha","subject_box":[x0,y0,x1,y1],"rotate":0\|90\|180\|270,"background":"plain"\|"busy","retake":"none"\|"plain-surface"\|"closer"\|"lighter","alt": str}` |

The cloud lane **never returns pixels**: a model that can only read a photo cannot restyle one, and an image-making model is not
approved (SKILLS-SPEC D6). The picture itself is made by the Pillow renderer of #504 using the model's numbers. Where the renderer
already finds the subject (6 of 8 synthetic cases in #504), no Tier 3 call is made at all.

**Size caps.** Brief at most 16 KiB plus a photo of at most 1 MB. Proposal at most 4 KiB. At most 2 alternates. Description at most
the product limit (600) and, for house style, 59 to 167 characters, 2 or 3 sentences (the measured numbers in #504). `alt` at most
200 characters.

**Validation has two layers, and every field belongs to exactly one of them.** The structural fields carry digits and numbers by
design (a version, a job id, a hash, pixel coordinates), so the prose prohibitions are **not** applied to them, and the prose
prohibitions are applied to **every** generated text field with no exception. A builder must implement both layers; neither may be
widened to skip a check.

**Layer 0, the whole object (any failure rejects it).** At most 4 KiB; strict JSON (no NaN or Infinity); exactly the keys listed
for the kind (no more, no fewer); no duplicate key; every value of its listed type.

**Layer A, structural fields: schema, type and range only. No prose rule is applied to these.**

| Field | Rule |
|---|---|
| `v` | the integer `1` exactly |
| `job_id` | matches `^j-[0-9a-f]{12}$`, names an open, unexpired job that has no proposal yet |
| `brief_sha` | matches `^[0-9a-f]{64}$` and equals the job's own `brief_sha` |
| `subject_box` | four integers `[x0, y0, x1, y1]` with `0 <= x0 < x1 <= width` and `0 <= y0 < y1 <= height` of the copy sent, and an area of at least 10 percent of the image |
| `rotate` | one of `0`, `90`, `180`, `270` |
| `background` | `"plain"` or `"busy"` |
| `retake` | `"none"`, `"plain-surface"`, `"closer"` or `"lighter"` |

These fields are never shown to Mike and never written to the site. A value outside its rule rejects the object.

**Layer B, generated text fields: `description`, each entry of `alternates`, and `alt`. The prose prohibitions apply here, and a
violation in any one rejects the whole object.**

* claims: origin, organic, grade, process, diet, fair-trade, health, awards, "local", "handmade" unless Mike stated it
  (`claims.unstated` over the joined texts of the brief);
* prices, money, sizes, weights, counts, **any digit**, the `$` sign, "per", "each", "free";
* contact details: phone numbers, addresses, emails, `@names`, `#tags`, "visit", "call";
* trail facts: distance, difficulty, duration, elevation, access;
* links and markup: `http`, `www`, `.com`, `<`, `>`, `{{`, `}}`, backticks, invisible or direction characters;
* a place, maker or person name that is not in the brief; hype words (the #504 list: best, amazing, perfect ...), `!` and `?`;
* limits and house style: `TEXT_LIMITS`/`FORBIDDEN_TEXT` of `content_model`, `house_style.check_description` (#504) for
  `description` and `alternates`, `ops/photos._alt_problem` for `alt` (a file name, placeholder or fewer than 3 letters is refused).

**Order of checks in Hass:** layer 0; layer A; `job_id` open and not used before; then layer B on each text field; then the claims
gate over the joined text. Authenticity is **not** a safety property: a forged file would face the same checks. A file that fails
is dropped and logged with a code, never a text.

**Valid examples** (synthetic; the brief was `name` "Wildflower Honey", `maker` "Bee Happy Farm", `place` "Atascadero", `shelf`
"pantry", `owner_words` "honey from the farm, good on toast"; the real brief also holds the public `style` block, left out here, so
the `brief_sha` shown is the SHA-256 of that shortened brief as sorted-key, compact, UTF-8 JSON with `kind` `item.description`,
computed for this page and illustrative only):

```json
{"v":1,"job_id":"j-3f9a1c07be52","brief_sha":"f8bed92f32a828c57d5b20cf3112d38ee87e5547f3e0192dca8818e710cbecb2",
 "description":"Wildflower honey from Bee Happy Farm in Atascadero. Good on toast, in tea, or by the spoonful.",
 "alternates":["From Bee Happy Farm in Atascadero, wildflower honey for the pantry shelf. Try it on warm bread.",
               "Wildflower honey from Atascadero, by Bee Happy Farm. Stir it into tea or spread it on toast."]}
```

(The description is 94 characters in 2 sentences; the alternates are 95 and 92 characters in 2 sentences. The digits in `v`,
`job_id` and `brief_sha` are structural and valid; the three text fields contain none.) A photo plan for a 1024 by 768 copy
(`brief_sha` of `{"kind":"item.photo_plan","width":1024,"height":768}`):

```json
{"v":1,"job_id":"j-8c21d4e0a967","brief_sha":"6d73d4c503c4d4c7a14782ccea314072826d2ed8dc90668be792a8f3d7ed2c48",
 "subject_box":[112,64,688,712],"rotate":0,"background":"busy","retake":"none",
 "alt":"A glass jar of honey with a plain label on a wooden table."}
```

(The box is inside the image and covers 47 percent of it; the digits and numbers are structural and valid; `alt` is 58 characters
and has no digit.)

**Invalid controls** (each must be rejected, and card 15 carries every one as a fixture):

| # | Object (change from the valid example) | Rejected by |
|---|---|---|
| 1 | `"v":2` or `"v":"1"` | layer A, `v` |
| 2 | `"job_id":"j-3F9A1C07BE52"` or a job id never issued | layer A, `job_id` |
| 3 | `brief_sha` of a different brief | layer A, `brief_sha` |
| 4 | an extra key (`"note":"..."`) or a duplicate `description` key | layer 0 |
| 5 | description "Twelve jars of wildflower honey, 4 left." | layer B: count and digit |
| 6 | description "Organic wildflower honey from Bee Happy Farm in Atascadero." (Mike never said organic) | layer B: claims gate |
| 7 | description naming "Paso Robles" (not in the brief) | layer B: place not in the brief |
| 8 | description "The best honey you will ever taste!" | layer B: hype and `!` |
| 9 | an alternate with `www.example.com` or `{{name}}` | layer B: link and markup |
| 10 | `alt` "IMG_2041.jpg" or "photo" | layer B: `_alt_problem` |
| 11 | `subject_box` `[0,0,2000,2000]`, `[600,600,620,620]` (under 10 percent), or `[5,5,5,9]` | layer A, `subject_box` |
| 12 | `"rotate":45`, `"retake":"call the shop"` | layer A, enums |
| 13 | a description of 700 characters, or a proposal over 4 KiB | size caps |

### 3.4 Timeouts and failure replies (plain words, voice rules)

Numbers are proposed, UNMEASURED: the end-to-end time through the real dispatcher has not been measured. Card 17 measures it
(p50, p95) on a scratch card, and "about a minute" is only promised in words if p50 is under 90 seconds.

| Situation | Hass does | Mike reads |
|---|---|---|
| Normal | waits up to 240 s | "Working on it. This usually takes about a minute." then the draft |
| Bridge down (no heartbeat for 3 minutes), G1 off, the daily cap is `$0`, a price or the spend record is missing or unreadable (cost unknown, 3.5), or no profile for the lane | no job, no wait | the draft with "I wrote a simple description because my extra writing help isn't available right now. You can change it." |
| Not back in 240 s | uses the template, drops a late proposal | "That took too long, so I used a simple description. You can change it." |
| Proposal fails a check | one more try with the reason **code** only (3.5), then the template | the same simple-description line |
| Daily cap used up (the dollar cap or the count fence) | no job | "I've used up my extra writing help for today, so I used a simple description. You can change it." |
| Cloud error | no job after one retry | the simple-description line |

Every line ends with the one next step Mike already has (`yes <code>` or `no`). None names a model, a queue or a limit. A cap or
bridge-down day adds one line to the problems log and to G's digest.

### 3.5 Lane choice and the per-day cap

* **Lane `standard` (Sonnet) by default.** Attempt 1 and, if the proposal failed validation, attempt 2 (told only the reason codes).
* **Lane `strong` (Opus) only after two failed attempts** on a description or photo plan, one attempt, never for a first try and
  never for any other kind. If that fails too: template, and a backlog row so the cause is read by a person.
* The bridge maps a lane to a named profile and **never substitutes**: if the configured profile or its route is held or
  unavailable, the job returns `error: unavailable` and Hass uses the template (the fleet rule: a held route stays held).

**The cap is money first, counts second.** A count of jobs does not bound spend, because the tokens, context and runtime of a job
vary, so the cap that matters is a **dollar cap per Pacific day**, designed now and an enablement prerequisite. The amount is
**G's to set (decision G9)**; nothing here invents it, and measured costs may tune it later. Everything below is enforced by the
**bridge**, which is operator-owned; Hass never spends and never decides.

1. **Setting and default.** `dailyCapUsd` lives in the bridge's own operator config (never in Hass, a brief or a proposal).
   **The default is `0`, which means no cloud job is ever queued.** A missing, zero, negative, non-numeric or unreadable value is
   treated as `0`. Turning Tier 3 on takes G1 **and** a G9 amount, written into that config by the operator from G's answer and
   recorded on the card.
2. **A price and reservation table per lane.** For each lane the config lists `reserve_usd`: a conservative **upper bound for one
   attempt**, which the operator computes from the hard limits it sets on the Hermes card (maximum input tokens for instruction,
   brief and photo; maximum output tokens, the 4 KiB proposal; maximum runtime, 300 s; text reply only, no tools) times the lane
   profile's listed price per token, times a safety factor of 2, plus a fixed allowance for the card run itself. A lane with no
   entry, a zero price, or an entry the operator has not refreshed in 30 days has an **unknown cost** (see 6).
3. **Reserve before queue, atomically.** Under one exclusive lock on `cloud/spend.jsonl` (append-only, the bridge's authority) the
   bridge: reads the Pacific-day total (settled spend plus every open reservation), checks `total + reserve_usd(lane) <=
   dailyCapUsd`, appends `{event:"reserve", job_id, attempt, lane, usd}`, and **only then** creates the card. The check and the
   append are one locked step, so two simultaneous jobs cannot both pass on the same headroom. A reservation counts as spent until
   it is settled. The day is the Pacific date, read under the lock; the day rolls over by the date changing, not by a timer.
4. **Every attempt reserves separately, including retries and the strong lane.** A retry after an invalid proposal reserves another
   standard attempt. The escalation to the strong lane reserves `reserve_usd(strong)` and runs only if that fits. A request is
   never started on headroom that covers attempt 1 while assuming escalation will fit: if the next attempt does not fit, the
   template is used and the log says `refused-cap`. One open job per request still holds, and at most 3 attempts per request.
5. **Settle when the job returns.** If the card reports its usage and the report parses, the reservation is replaced by the cost
   at the table's prices (a refund of the unused part). **If usage is missing, unparsable, or the card was killed or timed out,
   the full reservation stays as the charge** (`basis: reserve`): never a refund on missing data. If `reported` is above the
   reservation (an overrun), the larger number is charged, the day is **closed** (no more jobs until the next Pacific day) and the
   digest says so. A job with no result after the card's maximum runtime plus 120 s is settled at its full reservation.
6. **Fail closed on anything unknown.** Missing, unreadable, locked for more than 2 seconds, or malformed spend ledger; an unknown
   price or reservation (2); a cap of `0`; a clock that cannot be read; a `cap.json` that cannot be written: the bridge queues
   **nothing** and returns `error: unavailable`, which Hass shows as the "extra writing help isn't available" line (3.4). Cost is
   never estimated optimistically.
7. **Count limits stay as a second fence** (proposed; G may change): 8 jobs a day in all, at most 2 on the strong lane. A job
   must pass both the dollar check and the count check. The bridge counts and refuses; Hass also counts so it can answer without a
   round trip.
8. **Hass's side.** Hass reads `cap.json` only to answer at once; if it says the day is closed or the cap is `0`, or it is missing
   or older than 3 minutes, Hass queues no job and says the right line from 3.4. The bridge still re-checks. When the cap is reached
   Hass says so in plain words and G's digest shows `cap reached` (counts only). It never silently drops to a different route or a
   cheaper model.
9. **Measure, then tune.** After the first 20 jobs the operator compares settled spend with reservations and tells G (G9 can be
   asked again with real numbers); reservations are tuned by the operator from measurements, never by a model.
10. **Tests (cards 15 and 16).** With a fake bridge and a bridge self-test: cap `0` or missing queues no card; a job that exactly
    fits is queued and the next is refused; two simultaneous reserves let exactly one through; a retry and an escalation each
    reserve; a lane with no price is refused; missing usage is charged the full reservation; an overrun closes the day; a corrupt
    or locked ledger refuses; the Pacific date rollover; and no test ever calls a real model.

### 3.6 Audit log

`cloud/audit.jsonl` (append-only, private, kept 90 days, not backed up): one row per event: `at`, `job_id`, `request` (12-hex
one-way hash), `kind`, `lane`, `attempt`, `event` (`queued`, `refused-cap`, `refused-off`, `refused-cost-unknown`, `returned`,
`invalid:<code>`, `timeout`, `error:<code>`, `used`, `template`), `brief_sha`, `proposal_sha`, `bytes_out`, `bytes_in`, `seconds`,
`card` (the board card id the bridge reports), and the bridge's own money fields `reserved_usd`, `settled_usd` and `basis`
(`reported` or `reserve`). **No owner text, no proposal text, no prompt, no photo, no sender and no owner amount** (the only money
in this log is the bridge's own spend). The bridge keeps its own spend ledger (3.5) and its own log of cards on the board (the
second record, operator-side). The `status` command for Mike never shows any of it; G's weekly line gets counts (jobs, caps hit,
fallbacks, p50 seconds) and the day's spend against the cap.

### 3.7 Why code, not the model, writes the change

* **Validation and limits are code.** The editor, the closed argument kinds, `TEXT_LIMITS`, the claims gate and the live boundary
  already exist and are tested; a model cannot be asked to respect them with the same certainty.
* **Preview, approval and undo are bound to what code produced** (hash, base revision, expiry). A model-made edit would have to be
  turned back into ops before it could be previewed or undone, and at that point it is a proposal.
* **Prompt injection.** Mike's words, a photo's printed label or a forwarded text can contain instructions. A proposal is checked
  as data; a model with write access would obey them.
* **Determinism and tests.** A skill with a plan is replayed byte for byte by the test kit and the acceptance suite. A model's
  behaviour is measured in percent.
* **The goal.** "Do not need LLMs in the future" is reachable only if the knowledge is in code. When Tier 3 is replaced by a better
  template, the skill's code path does not change.
* **No credentials in Hass,** which is the only way a Hass bug cannot become a billing or data problem.

### 3.8 Compared with G's idea: the local model dispatches straight to Opus to do the changing

| | **Proposal lane (this design)** | **Local model hands the whole job to Opus** |
|---|---|---|
| Starts working on day 1 for any request, even one with no skill | no (needs a skill; the manual lane covers the gap) | **yes: its main gain**, nothing to build first |
| Handles an odd, one-off job | the manual lane (the operator) | **yes**, if Opus can express it |
| Who writes the change | code, through the editor | Opus would need write access, or its output turned into ops (then it is a proposal) |
| Credentials and network | none in Hass | something in Hass must reach the cloud and write |
| Prompt-injection exposure | low: a proposal is checked as data | high: a photo label or forwarded text could steer a writer |
| Same request twice | identical, free, instant after a rule is learned | different wording each time, paid each time |
| Tests and acceptance | exact diffs, undo to identical | percent of acceptable outcomes |
| Cost and delay | pennies and seconds for Tier 1-2; Tier 3 rarely | a cloud call and about a minute for every request |
| Reaches "no LLM needed" | yes, job by job | no: the knowledge stays in the model |
| Finance and private data | cannot reach the cloud by construction | the router would need a never-cloud rule per request |

**What we keep from G's idea:** the local model is still only the receptionist, and the cloud is still the specialist. **What
differs:** the specialist hands back words, never a change, and the first week's unskilled jobs go to the manual lane instead of a
model with write access. **A hybrid worth considering later** (not built here): for requests with no skill, an operator-started
(never automatic) Opus session drafts an ops draft for the operator to read, which then enters Mike's chat as an ops-draft
proposal (card 5). That gives the speed of "Opus does it" with a human before Mike and Mike's `yes` after.

### 3.9 Other flows I considered

* **Template first, cloud as an upgrade** (adopted for item.add above): Mike gets a complete draft; the cloud only improves one slot.
* **Teach by example** (small, optional): the reply to a change that was read by the local model ends once per skill with "Next
  time you can just say: eggs out." This raises the share of rules that match and lowers model calls. It is words inside an answer.
* **A `what can you do` list** generated from the registry (card 17 of the spec, DOCS-1): the same lever, on demand.
* **Hass asks first** (part 5.6): for weekly jobs a question once a week beats Mike remembering.
* **Rejected: a cloud model as the interpreter.** It would send every message off the box and put a cloud call in every reply.

---

## 4. The skill factory loop

### 4.1 Where the work comes from

Four private sources, all on the box: the **backlog** table (merged), the **correspondence log** (merged: "did not understand",
"could not do", "asked again", "corrected"), the **traces** of manual runs (2.3, card 2) and the **pattern table** (4.3). None of
them leaves the box. What may leave the box (reach a Hermes card, a report or git) is defined **once**, in 4.4, and is much
narrower than "counts and summaries": only **closed codes, integers and fixed sentences**. A free-text summary, even one the
model wrote, is Mike's words in other letters, so it is not exportable.

### 4.2 The weekly cycle (the operator, one fixed weekday; target 1-2 skills a week, ESTIMATED)

1. **Count.** `python3 hass/skills/factory.py report --state DIR` (card 2) prints, for the last 28 days and **as closed codes and
   integers only (4.4)**: backlog rows by reason and by task code, repeats per task code, correspondence "could not do" and "did
   not understand" by kind, traces by candidate, pattern hit rate and corrections. There is no grouping by summary words: rows the
   classifier cannot place are counted as `unclassified`. When a person needs to read the actual requests to understand a cluster
   (for example to write a spec), the operator uses the **on-box** view `factory.py review --local` (4.4), prints to the operator's
   terminal only, and writes the spec's example sentences by hand from scratch.
2. **Rank.** Score each candidate = rows in 28 days (or 2 traces) × a pain weight (the owner re-sent or corrected it) ÷ build size
   (a skill over ops that already exist is small; a new op, content field or data class is large), and put it aside if it is policy
   (price, page, sales, sending: those become a decision for G, as G8 did). A candidate is eligible with 3 requests in 4 weeks or 2
   traces. The top 1-2 go on.
3. **Spec card.** The operator (a planning lane, not a builder) writes the card in the SKILLS-SPEC shape: name, slots, rules, plan,
   edits, `data_class`, live class, undo and residue, 10 **synthetic** sentences (vague, misspelt, multi, refusals), the owned
   files, the builder tier (below). Anything that adds a data class, an outbound message or a cost goes to G first.
4. **Build.** A routine, well-specified skill is a Sol Medium card (the operator's route; SKILLS-SPEC said Sonnet by default, the
   operator's routing wins); a card that touches `conversation.py`, privacy or a content-model field is Sol High with an independent
   review, per `WORKER-GUIDE.md`.
5. **Test kit.** `hass/skills/testkit.py` (merged #518): lint, plan golden, case rows (at least 10, 2 refusals, 1 undo).
6. **Acceptance.** The new rows join the 72-message corpus and the chain (SKILLS-ACC-1/2). A new skill ships in `skills.mode=both`
   and is judged on its first 10 real uses: at least 80 percent approved without correction, 0 unapproved writes (the owner-trial
   numbers of SKILLS-SPEC 5.1).
7. **Close the loop.** Its backlog rows close, its first rule candidates start collecting (4.3), the tip to Mike goes in his next
   reply (2.3), and the report records the week.

### 4.3 Learning phrasings into deterministic rules, without keeping private text off the box

* **When.** At the moment Mike approves a draft that Tier 2 produced, code derives a **candidate rule** from that one message and
  throws the message away (the open-request texts already erase 24 hours after close, D7). Nothing is mined from messages that were
  not approved.
* **What a rule is.** A template of literal words with typed holes: `{product} is (sold out|out|gone)`, `{day} at {clock}`. The
  holes are the slot values code found in the text by the same resolvers the skill uses (`product_ref`, `day`, `clock` ...). The
  rule remembers the skill and the slot map, a support count, the days seen and a state.
* **No private text in a rule.** Every literal word must be a function word or a word from the **public lexicon** (the skill's
  triggers, `nl_prep` vocabulary and a closed list of everyday words). Any other word becomes a hole or the rule is dropped:
  a name, a number, an address, a phone, a link or an odd word cannot be learned as a literal.
* **Where rules live.** In the private database on the box, used by the matcher at Tier 2a. **Rules are never exported.** The repo
  gets no rule; a human writes the skill's public triggers from synthetic sentences.
* **Promotion.** A candidate becomes active at **5 approved uses on 3 different days** (proposed; G7), only if it reproduces the
  same skill and slots as the model on every stored use, gives a different result from no other rule, and matches none of the
  refusal cases. A rule never routes a message that holds a price, a claim word or an attachment the skill does not own.
* **Safety net.** A rule-routed request goes through the same slot validation, preview and `yes` as any other. A rule that sees
  2 corrections or rejections in its last 5 uses is retired. The weekly report shows the **model-skip rate** (share of requests
  answered with no model call) and the retired count; a falling skip rate or a rising correction rate is the signal to look.
* **Cost of a bad rule:** a wrong draft Mike can say no to. It is never a wrong change.

### 4.4 The export contract: what may leave the box from the factory (card 2)

The merged backlog stores, per row, a model-written one-line `summary` (up to 160 characters) and, when no summary is supplied, the
first 160 characters of Mike's own message; neither passes through any privacy filter (`hass/skills/backlog.py: _summary`).
A synthetic probe by the reviewer confirmed that both retain a vendor name, a dollar amount and an email address. So an
unsupported receipt request, a supplier message or any request that fails classification would carry finance or contact data into a
digest if summaries were exported. The factory therefore exports by **allowlist of closed values**, fails closed, and never reads
free text into anything it prints.

**What is exportable** (to a Hermes card, a report, a log line, git, or any place a cloud model can read), and nothing else:

1. integers (counts, and percentages computed from counts) and ISO day or week labels;
2. values from closed lists in code: `reason` (the six backlog reasons), `state`, `data_class`, a **task code** from the closed
   codebook below, a skill name from the registry, a question code, a slot name;
3. fixed sentences from templates in `factory.py`.

Not exportable, anywhere, ever: a `summary`, any owner text or fragment of it (including a quoted correction), anything a model
wrote, a vendor, supplier or maker name, an amount, a date taken from a document, a phone, email, address, link, `@name`, a path,
a sender or chat id, a photo name, or any value derived from a `finance-local` or `private-local` record.

**The task codebook** (closed): `T01` ... `T39` (the rows of part 1), a skill name when a registered skill exists, `finance`,
`sensitive`, `unclassified`. The classifier `factory.task_code(row)` is deterministic and runs **on the box**: it reads the private
summary and text **in memory**, and returns only a code. Order: (1) the sensitive detectors (a money amount, a `$` or digits with
cents, an email, a phone number, a run of 8 or more digits, a link, an `@name`, a street-address pattern) and the finance words
(receipt, invoice, expense, bill, paid, tax, bank, payroll, rent, total) return `finance` when a finance word is present, otherwise
`sensitive`; (2) the keyword table of the public lexicon returns the single matching `T` code or skill name; (3) **anything else,
two different matches, an empty row, an unknown reason, any exception, or a code not in the codebook returns `unclassified`.**
Unknown means the most restrictive bucket, never a guess. `finance`, `sensitive` and `unclassified` rows are exported as a **count
only** (never grouped further, with no age and no detail beyond the closed reason code), and a candidate whose skill `data_class`
is not `site-public` or is not known is exported only as a count under its `data_class`.

**The export guard.** `hass/skills/export_guard.py` is the only way `factory.py` (`digest`, `report`, `trace list --export`) writes
output. It builds the text from the templates and the closed values, then runs a final check on the whole text: it refuses (exit
code 2, writes nothing, logs only a code) if any sensitive detector fires, or if any word is outside the template vocabulary and
the closed lists. The classifier and the guard are two independent layers; either alone must stop a leak.

**Columns and paths.** `digest` and `report` select the day, `reason` and `state` for output and call the classifier on the text in
memory; no output structure has a free-text field. The existing G-only `problems` and `weekly` replies (merged #523) are pinned by
a card 2 test to carry no summary and no text; if one does, card 2 fixes it. The owner's own `backlog` command (his words back to
him, in his chat) is unchanged and is not an export. `traces.jsonl` has closed fields only (2.3 step 5); its synthetic example
sentences stay in the on-box file, are copied into a spec card only after the guard passes them, and are absent for any candidate
that is not `site-public`. `review --local` has no output-file option and refuses when its standard output is not a terminal.

**Tests (card 2), synthetic canaries only (no real owner text, ever).** Plant a made-up vendor ("Hartwell Supply Co"), `$84.12`,
`mike.example@example.com`, `805-555-0142`, a 16-digit number, a link and a street address in: the supplied model summary; a row with
**no** summary (the first-160-characters fallback); a summary over 160 characters; the text column; a trace's free fields; a
correction note. Assert that no canary and no fragment of 4 or more characters of one appears in the digest, the report, the trace
export, standard error or any log line; that a classification exception, an unknown reason and a code not in the codebook each land
in `unclassified`; that finance and sensitive rows add to a count only; that a guard refusal exits 2 and leaves no file; that
`review --local` refuses a pipe or a file; and that the digest's output has no string field that is not in the closed vocabulary.

---

## 5. The new skills

Shape per SKILLS-SPEC 2.2 (name, slots, rules, plan, edits, side effects, preview, approval, live class, undo, refusals, tags
`(v)` vague, `(t)` misspelt, `(m)` several, `(p)` photo, `(a)` answer, `(x)` must refuse). Sentences are synthetic. One new
field on every skill (card 1): **`data_class`**: `site-public` (default), `private-local` (stays on the box; no cloud step may
be declared) or `finance-local` (the same, and nothing about it appears in any log, report, card or prompt).

### 5.1 Receipts and expenses (T05, T22): `receipt.add`, `receipt.void`, `expenses.show`

**FINANCE DATA IS LOCAL-ONLY.** The local model reads it; **no cloud model ever sees it**; nothing leaves the box; no email inbox
is involved (hass@ was declined: receipts arrive as photos in the owner chat); no off-box export of any kind without a new G decision.

* **Skill `receipt.add`**, `data_class: finance-local`. Slots: `photo: attachment` (a receipt photo or a forwarded file or
  screenshot; JPEG or PNG, 20 MB, one per message, same checks as any photo) · `vendor: text R ≤60` (`? Who was it from?`) · `day: day R`
  (default: the date printed, else today; `? What day was it?`) · `total: money R` (cents, 0.01 to 100000; `? What was the total?`) ·
  `category: enum R` (see below; `? Which kind: stock, supplies, fuel, rent, utilities, fees or other?`) · `note: text O ≤100`
  · `paid: enum O` (card, cash, other). The local vision model reads the photo to **suggest** vendor, day and total; every suggested value is shown and confirmed,
  never silently saved; a value it cannot read is asked. Categories (proposed, to confirm with Mike's bookkeeper): `stock`,
  `supplies`, `fuel`, `rent`, `utilities`, `fees`, `marketing`, `equipment`, `other`.
* **Rules.** `local-only` (no `assist` step; the lint fails otherwise) · `amount-sane` (positive, at most 100000, two decimals) ·
  `day-sane` (not in the future, not older than 400 days; else ask) · `twin` (same vendor, day and total within 90 days: "I already have
  this one", draft nothing) · `one-per-photo` · `no-card-numbers` (the stored note drops any run of 8 or more digits) ·
  `no-prices-to-site` (nothing here can reach any site op; `edits` lists none).
* **Plan and edits.** No site op and no editor call. `Skill.plan` returns a typed **private action record** instead of ops
  (`{action: "ledger.add", args: {day, vendor, total_cents, category, note, paid, photo_sha}}`, 5.1a): one row in a new private table
  `ledger` (`id`, `day`, `vendor`, `total_cents`, `category`, `note`, `paid`, `photo_sha`, `draft_hash` UNIQUE, `state`
  `active|void`, `voided_by`, `created_at`) **inside the existing private `conversation.sqlite3`**, so the state backup, restore drill
  and the 0700 state folder already cover it; the receipt photo stays in the private media root. A separate file would be refused
  by the backup's closed layout list (`statebackup._scan` names an unknown entry as a problem). Nothing about a ledger entry is ever
  written to site content, generated files or Git.
* **Preview and approval.** A plain line to Mike's own chat, no screenshot: "Costco Wholesale, Nov 8, $84.12, supplies. Reply yes
  to save it, or no to cancel." (the vendor is an example; the sentence follows VOICE: no id, no code beyond the one he types).
  Approval is `owner-yes`, **bound to the exact entry shown** by the private-action contract (5.1a): hash, sender, chat, expiry,
  pause, one atomic save, recovery. The ordinary editor approval is not used, because it applies site ops and a ledger write is not
  one.
* **Undo.** `undo` (right after saving) or `void receipt <n>`: a second private action, `ledger.void`, also needing `yes` like a
  site undo (5.1a): the row becomes `void` (kept, struck out of totals), never deleted. Residue: the photo stays in the private
  store.

* **`expenses.show`** (read-only): "expenses for October" replies the month's total and a total per category, and the newest 5
  entries, as text, to Mike's own chat. A CSV for the bookkeeper is an **off-box export**: not built, not allowed without a G
  decision; until then Mike can screenshot the reply.
* **Reading the photo (card 10).** A local vision model call on the loopback router or the CPU model (the label reader's pattern,
  `label_reader.py`), with its own config key so the model is chosen on its own measured accuracy. Measured on **synthetic receipts
  only** (made up vendors and totals; no real receipt is read for the build): the gate to enable is the total exact on at least 90
  percent, the date exact on at least 85 percent, 0 saved without the owner's `yes`. A real-receipt trial is Mike's, on his phone,
  with G's go-ahead, and its results stay on the box. Standalone OCR or vision qualification elsewhere is not proof of this reader.
* **Photo routing.** A photo with no caption already asks one question; the question gains "a receipt". A caption with "receipt",
  "expense" or "for the books" goes straight to this skill. The label-reader job (a product label) is **not** queued for a photo
  routed here. The receipt photo is never offered as a product picture and never given a web copy.
* **Never in:** the interpreter prompt of any later message, the correspondence log (it already blanks numbers), the stage log (ids
  only), the audit, any report, the morning report, a card, git, or a cloud brief (the bridge's own allowlist refuses the kind).
* **Live class:** `private-only` (no site effect).
* **Sentences.** 1 `(p)` (photo) "receipt" 2 `(p)` (photo) "this is for the books" 3 `(p,v)` (photo only: Hass asks "Is this a new
  product, a new picture, the home photo or a receipt?") 4 `(p,t)` "resipt from costco, supplies" 5 `(a)` "I got fuel" → "Send the
  receipt, or tell me the total." → "$62.40" 6 `(m)` (two photos in two messages, each its own entry) 7 `(x)` "expenses for last
  year" (older than the ledger: says so) 8 `(x)` "email this to my accountant" (sending is not possible; says so; logged) 9 `(x)` (a
  photo of the shop shelf sent with "receipt": the reader finds no total, asks) 10 `(x)` the same receipt twice (twin).
* **Tier.** 1+2L (local vision only). **Zero cloud.**

#### 5.1a The private-action contract (what the ledger needs from the framework; card 1 and card 4)

**Why it is needed.** On main, `Skill.plan` returns registered **editor ops**, the lint limits a skill's edits to content and
generated paths, and an owner `yes` in `Conversation` ends in `editor.apply(change_id, draft_hash)` (the approval path in
`hass/conversation.py`), which writes the site. A ledger entry is none of that. Adding a `ledger.py` module would not say how a
bound approval saves a private row, or what `undo` means for it. So this page defines a bounded **private action** next to the
editor path, reusing its approval machinery rather than bypassing it, and gives it owners (part 6).

**1. The model (card 1, SKILLS-MODEL-2).** A skill may declare `private_action = PrivateAction(action, args_schema, approval,
undo)` instead of `edits`. The lint enforces: a skill whose `data_class` is not `site-public` has `edits=()`, no `assist` step,
and (if it writes anything) exactly one `private_action` with closed argument kinds; a `site-public` skill has none. `plan` returns
the validated action record; it never touches a database.

**2. The draft row (card 4, HASS-PRIVACT-1).** The `drafts` table gains a `kind` column (`site` by default, `private`; added with the
existing lazy `ALTER` pattern, so old databases open unchanged). A private draft uses the normal row and code, with these
differences:

* `change_id` is `pa-` plus 12 hex (no editor change exists); `ops_json` is `[]`;
* `summary` is a **fixed neutral phrase** from the action kind ("a receipt to save", "a receipt to cancel"): never a vendor or an
  amount, so `history`, `status`, `find`, the waiting lines, the problems log and the stage log show only the neutral phrase;
* `draft_hash` is the SHA-256 of the canonical JSON of `{kind, action, args, sender, chat, base, expires_at}` (same `sha256:` form
  and the same 4-character code derivation as a site draft);
* `base` is the **target's state**: for `ledger.add` a hash of the twin key (vendor, day, total) so an identical entry approved
  first makes this one stale (the reply is "I already have this one"); for `ledger.void` the target row id plus `active`. Other
  receipts arriving in between do **not** make a draft stale;
* the typed args live in `private_pending(change_id PRIMARY KEY, args_json, created_at)` in the same private database; the row is
  deleted when the draft ends (applied, rejected, expired or failed) and in any case 24 hours after it was proposed. For an applied
  add, the ledger row is the record.

**3. Approval binding (card 4).** The existing yes/no path is reused **unchanged** up to the `approvals` row: the owner sender and
chat check, the 4-character code, the approval TTL (`approvalTtlSeconds`), the rule that a yes sent before the draft existed does
not count, the repeat check, and the **pause check** (a paused system saves nothing, replies in the existing words with the code, and
the draft keeps its expiry). Differences: no live-site policy check (there is no site effect), and after the commit the message
handler calls `private_actions.apply(change_id, draft_hash)` **instead of** `editor.apply`, chosen by `kind`. A private draft is
never applied by any other path.

**4. One atomic, idempotent save (card 4 and the action's handler, card 8).** `apply` runs in one `BEGIN IMMEDIATE` transaction on
the conversation database:

1. load the `approvals` row for the `change_id`; require its `draft_hash` equals the draft row's, its sender equals the configured
   owner sender, its chat equals `ownerChat`, and `approved_at <= expires_at`;
2. recompute the hash from `private_pending` plus the settings and require it equals `draft_hash` (a changed argument is refused as
   tampering, nothing saved);
3. re-check `base` (the twin key, or the target row's state); a changed base makes the result `stale` (no write; a plain reply);
4. `INSERT INTO ledger ... ON CONFLICT(draft_hash) DO NOTHING`; zero rows inserted means `already-applied` (never a second row,
   so a repeated `yes`, a replay or a retry is harmless);
5. mark the draft `applied` and enqueue the reply into the outbox **in the same transaction**, so a crash leaves either nothing or
   everything (the same rule as the site `_outcome`: nothing says it worked before it is stored).

**5. Recovery (card 4).** `recover()` is extended for `kind = 'private'` drafts left `approved` after a crash: if a ledger row with
that `draft_hash` exists the draft becomes `applied` and its reply is queued; if none exists, the draft becomes `failed`
(`interrupted`) with the plain line "I couldn't finish saving that receipt, so nothing was saved. Send it again." Recovery never
calls `apply` again (the existing rule for site drafts).

**6. Void and undo (cards 4 and 8).** `undo` with no target proposes `ledger.void` for the most recent **applied or verified draft of
either kind** in the owner chat (one timeline: after a receipt, `undo` is the receipt); `void receipt <n>` names a row. It is a
private draft needing `yes <code>` with the same binding as above, exactly as a site undo is a draft needing a yes. Apply: `UPDATE
ledger SET state='void', voided_by=<hash> WHERE id=? AND state='active'` in one transaction; zero rows with the row already `void`
is `already-applied`, and voiding a void row is refused ("That one is already cancelled."). The original draft is marked `reverted`.
Ledger rows are never deleted by any command; totals exclude `void` rows and `expenses.show` says how many were cancelled.

**7. Privacy of what Hass says and stores (card 4 tests).** The pending-draft reply and the saved reply show the entry **only in
Mike's own chat** (he must see the numbers to confirm them). Everywhere else the neutral phrase is used (item 2). A reply
marked `private` has its outbox body replaced by the neutral phrase once it is sent, so finance values do not sit in the outbox
after delivery. The correspondence log already blanks numbers; the stage log has ids only; the audit and the factory export (4.4)
never see an entry. The tests plant a made-up vendor and amount and assert they are absent from the draft summary, `history`,
`status`, `find`, the waiting lines, the problems log, the correspondence log, the stage log, the outbox after send, any report and
every card file.

**8. Test kit (card 4).** `hass/skills/testkit.py` (merged #518) gains a `private` case kind: a golden for the canonical args and
hash, apply against an in-memory database, the void, a second apply (idempotent), a crash injected between approval and apply, a
paused system, an expired draft, a wrong sender, a wrong chat, a changed argument, the TTL boundary, and the neutral-text pins above.
The lint rule in item 1 is tested here too.

**9. The order copy (5.2) uses the same contract with `approval: none`:** the action applies in the same transaction as the message
that asked for it, keyed by the message's provider id, so a replay saves it once.

**10. Enablement.** All of this ships with `ledger.enabled` false (G3). Until then `receipt.add` is absent from the registry, a
receipt photo is answered as today, and no ledger table is created.

### 5.2 Supplier order drafts (T16): `order.draft`, `order.repeat`, `orders.show`

Hass **never sends and never spends**: the fleet rule is approval before any agent sends a message or spends money, and this skill
has no way to do either. It writes a message Mike can send himself.

* **`order.draft`**, `data_class: private-local`. Slots: `supplier: text|maker_ref R` (a maker on the site is matched by name;
  otherwise free text; `? Who is it for?`) · `lines: list of {item: text, qty: text}` R (his words: "4 dozen eggs", "honey, 6
  jars"; quantities are **allowed here** because this is a private message, not site content; never guessed; `? How many of each?`)
  · `when: text O` ("by Friday") · `note: text O ≤200`. Code never adds an item or a number he did not give, and never adds a price.
* **Rules.** `no-invention` (every line traces to his words) · `lines-max-12` · `no-send` (a request to send or text the supplier
  gets "I can't send messages to suppliers. Here is the message to copy." and the draft) · `local-only` · `no-price` (a price Mike
  says is kept in the draft text only if he said it, never looked up).
* **Plan and edits.** No site op, no ledger entry. The reply is the message text, ready to copy: "Hi, it's Mike at Avocado Shack. I'd
  like to order: 4 dozen eggs, 6 jars of honey. Could you have them by Friday? Thanks." (template, no model writing). A copy is
  saved in a private table `orders` (`id`, `supplier`, `lines`, `created_at`) so `order.repeat` ("same as last time, Linn's") can
  rebuild it. Supplier **name and how Mike reaches them (text, email)** may be kept; **no phone or email** (G6).
* **Approval.** `none` (a reply, nothing changes anywhere but the private copy); the draft says "I haven't sent anything." Undo:
  `forget order.<n>` (drops the copy; the same shape as `forget backlog.<n>`).
* **Optional helper (design).** "What's low from Linn's?" lists the limited and sold-out items of one maker from the last shelf
  check as a **starting list with blank quantities**, not a suggestion of how many (no counts exist).
* **Sentences.** 1 "order 4 dozen eggs and 6 honey from Linn's" 2 `(t)` "oder 2 caes of the jam fro Fair Hills" 3 `(v)` "I need to order
  more cheese" (asks which supplier and how many) 4 `(m)` "eggs 4 dozen, honey 6, and 10 loaves of bread for Friday, all from
  the farm" (asks which supplier is "the farm") 5 `(a)` "order eggs" → "How many?" → "5 dozen" 6 "same order as last week" (`order.repeat`)
  7 `(x)` "send the order to Linn's now" (cannot send; gives the text) 8 `(x)` "pay Linn's $120" (spending: refused, logged) 9 `(x)` "order from
  a supplier I don't have" (one question: name) 10 `(x)` "order enough eggs" (a number is needed).
* **Tier.** 1+2. **Zero cloud.** F05 (supplier channels) stays a later feature; this does not start it.

### 5.3 Social post drafts for items and hikes (T14, T15): extend `social_draft.py`

Existing and merged as owner commands: `post <item>` (item caption, site photo), `post hike <hike>` (announcement), and the
maker caption in the CLI. SKILLS-SPEC card 12 (SOCIAL-1) wraps them as `social.item`, `social.hike` and add `social.recap`. This page adds:

* `build_new_item(content, id)`: "New in: <name> from <maker>, <place>." + the stored description + fixed tags (the new-item variant
  of `build`; same photo; refuses an item older than 14 days or without a photo).
* `build_back_in_stock(content, id)`: "Back on the shelf: ..." from the product's stored text.
* `build_specials(content, today)`: the active specials exactly as Mike typed them (the deal line may hold the price he typed, because
  the site already shows it exactly as typed) + fixed tags; refuses when none is active.
* `build_closure(content, id)`: one line from the closure record (part 5.4).
* `build_recap(content, event)`: SKILLS-SPEC 3.29 (Mike's own recap words only, no people count he did not write).
All are **templates over stored facts**: no model, no cloud, `approval: none`, nothing posted, scheduled or sent. Hass has no
social account and none is proposed; Mike copies the text and the picture. The existing refusals stay (a `#` or `@` followed by a
letter in free text is refused, caption at most 2200 characters, at most 5 hashtags, fixed tags only). Sentences follow the
catalog's 3.27-3.29 style: "write the new-item post for the honey", "post that we're closed Thursday", "thank-you post for Saturday",
`(x)` "post it now" (Hass posts nothing, says so).
Tier 1 (templates) after Tier 2 reads which item or hike.

### 5.4 Holiday closures as a date-range skill (T29): `shop.closure` (and the site part)

Today the site has hours lines (up to 7, 60 characters each) and one notice with an end date up to 60 days out that **shows
immediately**. It has no scheduled closure, so a closure announced three weeks ahead cannot appear later or disappear alone.

* **Site card (AVO-CLOSURE-1), modelled on AVO-SPECIALS-1 (#520):** a new optional store field `closures` (a list, absent = none,
  so saved files do not change), each `{id, start, end, label, showFrom}`; a render slot (like `hass/specials.py: slots`) that shows
  "Closed Dec 24 to 26 for Christmas" in a notice-style line from `showFrom` (default 14 days before `start`) through `end`
  (Pacific, last day inclusive) and nothing after, with the same build-time and browser-side checks that make a special never show
  late. Ops `store.closure_add / closure_edit / closure_remove / closure_clear_expired`. A changed content model, ops and template run
  the **full CI tier**; this is a site card, reviewed as one.
* **Skill `shop.closure`**, `data_class: site-public`. Slots: `start: day R` · `end: day O` (default one day) · `label: text O ≤40,
  owner words` ("Christmas") · `reopens: clock O` (never invented). Rules: `future-only`, `at-most-6-active`, `end-not-before-start`,
  `no-hours-touched` (hours lines are never edited by this skill), `no-claims`, `twin`. Plan: one `store.closure_add`. Preview: `home`.
  Undo: `revert`, residue none. Live class: `chat-live` (a date and Mike's own label).
* **Until it exists:** Mike uses `shop.notice` ("closed Dec 24 to 26 for Christmas", last day Dec 26): it shows at once and for up to
  60 days. Hass says so when asked for a closure further than 60 days out: "I can do that from a few weeks before. I'll need you to
  ask me again then." (Hass does not remember it for him; the prompts of 5.6 do: `prompt.holiday`.)
* **Sentences.** 1 "closed Dec 24 to 26" 2 "we're closed Thanksgiving" 3 `(t)` "closd christmas eve and day" 4 `(v)` "we're closed
  for the holidays" (asks which days) 5 `(m)` "closed Nov 26 and Dec 25 and Jan 1" (three drafts in one, up to 6 active) 6 `(a)` "closed
  next week" → "Which days?" → "Monday to Wednesday" 7 `(x)` "closed yesterday" (past) 8 `(x)` "closed every Sunday" (that is hours, not a
  closure: points to `shop.hours`) 9 `(x)` "closed for the holidays, back on the 2nd, we're open 24/7 after" (claim words are not written)
  10 "cancel the Christmas closure" (`closure_remove`).
* **Tier.** 1+2.

### 5.5 Prices (T26): `price.change` (gated, D9, Clover)

The site shows no prices and `$` is rejected in content (`AGENTS.md`: catalog-only). The one place a price already appears is a
special's deal line, exactly as Mike typed it. Nothing is built now.

* **Stage 0, today (SKILLS-SPEC D9):** a price in a message is refused with the plain explanation and a backlog row (`reason:
  price`); the weekly report counts them. **G8 confirms this.**
* **Stage 1, the shape that waits for G.** `price.change`, `data_class: finance-local`, slots `item: product_ref R`, `price: money R`, `unit: text O`.
  If G chooses the private note (G8-B), it writes only a private `price.<id>` note (like `cost.<id>`), never the site, never a prompt,
  never a cloud brief, and feeds the margin arithmetic. A price on the site, or a price in the POS, is a product change (AGENTS.md
  scope) plus POS discovery answers (SKILLS-SPEC 5.2 questions 5 and 6): G's decisions, with approval that is never automatic.
* **Not built before:** G8 and the Clover answers. Hass never changes a price in a till.

### 5.6 Hass-started messages ("prompts"): the weekly specials ask and the others

A reminder is Hass **sending** a message, so it is a new class of action with its own approval and limits. Nothing here adds a
way to send to anyone but Mike.

**Approval (three layers, all required).**
1. **G approves the framework and each prompt type** by naming it in the private host config (`prompts: [...]`; default empty = no
   prompt ever). Removing a name stops it. (G2.)
2. **Mike opts in** with `reminders on` (all the enabled types) or by saying yes to an offer that is **appended to a reply** Mike
   already asked for (for example the answer to a specials change ends "Want me to ask you each Monday morning? Say reminders on.").
   Hass never opens with the offer.
3. **Each send is bound to a schedule record**, not to a model: a prompt is a fixed sentence plus a trigger rule. No model writes a
   prompt.

**Limits (proposed, all enforced in code and tested).**

| Limit | Value |
|---|---|
| Messages per day, all types together | **at most 1** (the first due type wins; others wait for the next day) |
| Recipient | **Mike's own one-to-one chat only** (`ownerChat`); never G's chat, never a group, never anyone else |
| Quiet hours | **none from 20:00 to 08:00 Pacific**; a prompt due in that window is sent at 08:00 if still wanted, else dropped |
| While paused (`stop changes`) | none |
| While something is waiting for Mike (a draft, a question) or he messaged Hass in the last 10 minutes | wait; at most until 20:00, then dropped for that day |
| Unanswered | asks **once**, never repeats the same prompt the same cycle; 3 unanswered in a row switches that type off and writes it to G's digest (nothing more sent) |
| Stop words | `reminders off` (all), `no more specials reminders` (one type), `reminders on`, and bare `reminders` lists what is on. (`stop` alone already means "stop changes", so it is never the reminder stop word.) |
| Sending | at most once: the send is recorded **before** it goes out, keyed by type and date, so a restart or a failed relay cannot send twice; a send that fails is not retried after quiet hours |
| Content | one fixed sentence, voice rules, no id or technical word; never carries an amount, a stock count, a guest list or finance data |
| Driver | a timer on the box owned by the operator calls an idempotent `tick`; Hass code has no scheduler of its own |
| Audit | one row in the correspondence log style (`kind: prompt`, type, day, sent/skipped reason), no text |

**The five prompts (design; all off until G2).**

| Prompt | When | Fixed sentence (example) | The answer goes to |
|---|---|---|---|
| `prompt.specials` | Monday 09:00 Pacific; skipped if a special is already active or starts this week | "Good morning, Mike. Any specials this week? Tell me what they are and which days, or reply none." | opens a `specials.add` request: his answer fills it; `none` or `no` closes it with "No problem, nothing changed." |
| `prompt.recap` | 09:00 the morning after a real hike's start day; once per hike; never for a sample hike or a cancelled one | "How did the Cass Hill hike go? Send me a few words and I'll save them for the page." | opens `hike.recap` |
| `prompt.holiday` | 10 days before each holiday on Mike's own list (set once with `reminders on`; the holiday dates are a fixed table in code); once per holiday | "Thanksgiving is on the 26th. Will the shop be open? Tell me the hours or the days you're closed, or reply no change." | opens `shop.closure` or `shop.hours` |
| `prompt.shelf` | shop-day opening time Mike chooses; skipped if the check is already done today | "Ready for the shelf check? Tell me what's low or out, or reply all good." | opens `stock.checked` / `stock.set` |
| `prompt.receipts` | Friday 17:00 (opt-in only) | "Any receipts to send me this week? You can just send photos." | none (the photos route by 5.1) |

A prompt is a question, not an action: nothing changes unless Mike answers and then approves the draft like any other.

**Cadence of a specials week (T09, T10) end to end.** Monday 09:00: ask once. If he answers, `specials.add` drafts (title, deal
line as typed, dates), he says `yes`, the site changes. If he does not answer, nothing happens, no second message; the Sunday
`report` includes "No specials this week" only if he asks for it. Specials end on their own (the last day rule is merged in #520).

---

## 6. The build order for the new skills

**Prerequisites that are not new cards** (existing cards or PRs, the operator's to merge or finish): **FW-2 #525 and FW-3 #526**
(critical: no skill is reachable before them); review and merge **SPECIALS-1 #529, HIKES-1 #530, SHOP-1 #531**; **SOCIAL-1** and
**ITEMADD-1 / PIC-1 / #504** from SKILLS-SPEC (unchanged, still unbuilt). `conversation.py` stays a hotspot (spec 4.4): exactly two
cards below edit it, **in series after FW-3**: card 3 (the command hook) and then card 4 (private drafts); every later card adds
commands as separate modules and does not touch it.

Builder tier (per `WORKER-GUIDE.md`): **R** routine and well specified, Sol Medium; **S** substantial or privacy-touching, Sol High,
independent review; **Op** an operator action (a reviewed candidate file or a host step, never a builder card); **P** planning only.

| # | Card | Files owned (C create, M modify) | Needs | Tier |
|---|---|---|---|---|
| 1 | **SKILLS-MODEL-2: `data_class`, `assist` and `private_action` fields plus lint** (5.1a item 1) | M `hass/skills/model.py`, M `hass/skills/__init__.py` (lint), C `hass/tests/test_skills_data_class.py`, M `docs/hass/SKILLS.md` | FW-1 (merged) | **R** |
| 2 | **HASS-FACTORY-1: export-safe backlog digest, weekly report, traces, runbook** (4.4) | C `hass/skills/factory.py` (`report`, `digest`, `trace add\|list`, `review --local`; `task_code`), C `hass/skills/export_guard.py`, C `hass/tests/test_factory.py`, C `hass/tests/test_export_guard.py` (the canary tests), C `docs/hass/FACTORY.md`; M `hass/tests/` only to pin that `problems`/`weekly` carry no summary | FW-1 (backlog, merged), VOICE-1 (merged) | **S** (an export surface; independent review) |
| 3 | **HASS-CMD-1: command registry hook** | M `hass/conversation.py` (**first of two edits**: look up extra commands in `hass/commands/*.py` before the request path), C `hass/commands/__init__.py`, M `docs/hass/COMMANDS.md`, `docs/hass/LIMITS.md` | **FW-3 merged** | **S** (the state machine; every existing test stays green). If FW-3 hard-codes the one photo question, this card also makes it list the receipt option from the registry (5.1). |
| 4 | **HASS-PRIVACT-1: private actions: hash-bound approval, atomic save, recovery, void** (5.1a) | M `hass/conversation.py` (**second and last edit**: `drafts.kind`, the dispatch after approval, `recover()`, `undo` selection, neutral summaries, outbox redaction), C `hass/private_actions.py` (the `apply`/`recover`/`void` machinery and handler registry), M `hass/skills/testkit.py` (the `private` case kind), C `hass/tests/test_private_actions.py`, M the pinned tests that count `drafts` columns or list `SCHEMA` (listed in the card's first comment), M `docs/hass/LIMITS.md` | 1, 3 | **S** (finance-adjacent approval path; a crash-injection test; independent review) |
| 5 | **HASS-MANUAL-1: operator ops-draft ingest (the manual lane)** | C `hass/commands/manual.py`, C `hass/manual.py` (reads `<state>/manual/*.json`: a plain summary + an ops list; validates through the same registry, claims and editor path; shows Mike a normal draft), C `hass/tests/test_manual.py` | 3, 2 | **S** |
| 6 | **SKILLS-SOCIAL-2: new-item, back-in-stock, specials and closure captions** | M `hass/social_draft.py`, C `hass/skills/social_extra.py`, C fixtures `social_extra/`, C `hass/tests/test_social_extra.py` | SOCIAL-1 (owner of `social_draft.py`) | **R** |
| 7 | **HASS-SAY-1: the prompt engine plus the specials ask** | C `hass/prompts.py` (rules table, once-a-day, quiet hours, bound send, `tick`), C `hass/commands/reminders.py` (`reminders on\|off\|list`), C `hass/skills/prompt_specials.py`, M `docs/hass/COMMANDS.md`, `docs/hass/LIMITS.md` (only these two pinned docs), C `hass/tests/test_prompts.py` | 3, SPECIALS-1; enabling **G2** | **S** (a new outbound class; independent review) |
| 8 | **SKILLS-LEDGER-1: ledger, `receipt.add` (typed), `receipt.void`, `expenses.show`** | C `hass/ledger.py` (the `ledger` table in `conversation.sqlite3` and the `ledger.add`/`ledger.void` handlers registered with card 4), C `hass/skills/receipts.py`, C `hass/commands/expenses.py`, C fixtures `receipts/`, C tests `test_ledger.py`, `test_skills_receipts.py`, C `docs/hass/skills/receipts.md` | 1, 3, 4; enabling **G3** | **S** (finance data; tests for no log, no prompt, no cloud brief, backup restore, `ledger.enabled` false by default) |
| 9 | **SKILLS-ORDERS-1: `order.draft`, `order.repeat`, `orders.show`** | C `hass/skills/orders.py`, C `hass/orders.py` (private table, saved through card 4 with `approval: none`), C fixtures `orders/`, C tests, C `docs/hass/skills/orders.md` | 1, 3, 4; shape follows **G6** | **R** |
| 10 | **SKILLS-LEDGER-2: read a receipt photo locally** | C `hass/receipt_reader.py` (local vision, loopback only, own config key), C `hass/receipt_eval.py`, C `hass/tests/fixtures/receipts-synthetic/` (made-up receipts), C tests | 8; enabling **G3** | **S** (vision accuracy gate; independent review; operator runs the live eval on the box) |
| 11 | **AVO-CLOSURE-1 (site): the `closures` field, ops, slot, template** | M `hass/content_model.py` (after STOCK-2 owns it), C `hass/ops/closures.py`, C `hass/closures.py`, M `hass/templates/index.html`, M `hass/sitegen.py` (the slot hook, as #520), site tests and the pinned template hashes | **G4**, STOCK-2 | **S** (full CI tier) |
| 12 | **SKILLS-CLOSURE-1: `shop.closure`** | C `hass/skills/closures.py`, C fixtures `closures/`, C `docs/hass/skills/closures.md` | 11, SHOP-1 | **R** |
| 13 | **HASS-SAY-2: recap, holiday, shelf and receipts prompts** | C `hass/skills/prompt_recap.py`, `prompt_holiday.py`, `prompt_shelf.py`, `prompt_receipts.py`, C tests | 7, HIKES-1, 12; enabling **G2** | **R** |
| 14 | **HASS-PATTERN-1: learned rules (Tier 2a)** | C `hass/skills/patterns.py` (derive, store, match, retire, report), M `hass/skills/router.py` (one pre-pass hook; FW-2 owns it, so this card starts from its merged code), C `hass/tests/test_patterns.py` | FW-2, FW-3, 2; automatic activation **G7** | **S** (privacy: no private text kept; independent review) |
| 15 | **HASS-CLOUD-1: Tier 3 contract on the Hass side** | C `hass/cloud/{contract,spool,validate,caps,audit}.py` (`validate.py` implements layers 0, A and B of 3.3 with every valid example and invalid control as a fixture; `caps.py` only reads `cap.json`), M `hass/skills/model.py` (the `assist` field's use; after card 1), C `hass/tests/test_cloud_*.py` with a fake bridge | 1, 3; enabling **G1 and G9** | **S** (privacy and export surface; independent review) |
| 16 | **HASS-CLOUD-2: the bridge (operator-owned, outside the Hass runtime)** | a candidate script and timer for the operator, reviewed as a local-only candidate (hash map, live bases) with a `--self-test` covering the cap tests of 3.5 item 10: a config naming lane to profile and `reserve_usd`, `dailyCapUsd` (default 0), the brief allowlist, the spend ledger `spend.jsonl`, `cap.json`, `bridge.alive` | 15; enabling **G1 and G9**, the operator's choice of a profile | **Op** |
| 17 | **SKILLS-CLOUD-3: wire `item.add` description and photo plan, measure** | M `hass/skills/item_add.py` (after ITEMADD-1 owns it), C fixtures, C `reports/hass/CLOUD-3.md` (a scratch run: p50 and p95 seconds, fallback rate, settled cost against reservation, every model-written text shown to a person) | 15, 16, ITEMADD-1, PIC-1; enabling **G1 and G9** | **S** |
| 18 | **SKILLS-PRICE-1** | not scheduled | **G8**, POS-0 | n/a |

**Waves for the operator.** W0: merge FW-2 and FW-3, ask G1-G9 (nothing in W1-W5 waits for an answer to be built; the answers gate
enabling, see the top of this page). W1 (parallel): 1, 2, 6. W2: 3, then 4, then 5. W3: 7, 8, 9 (8 after 4; each ships off until its
answer). W4: 10, 11, then 12. W5: 13, 14. W6: 15, 16 (the bridge is installed only after G1 and G9), then 17 after ITEMADD-1.
Cards 15 to 17 are last on purpose: ITEMADD-1 ships a deterministic template description first, and **Tier 3 is built only if the
corrected-description rate in the first 20 real adds shows the template is not enough** (the gate is a measured rate, not a guess).

**Which files only one card owns** (hotspots, extends spec 4.4): `hass/conversation.py` FW-3, then card 3, then card 4 (nothing
after); `hass/social_draft.py` SOCIAL-1 then card 6; `hass/content_model.py` and `hass/morning_report.py` STOCK-2 then card 11
(content_model only); `docs/hass/COMMANDS.md` and `LIMITS.md` FW-3, card 3, card 4 (LIMITS only), then card 7 (each strictly after
the last merges); `hass/skills/router.py` FW-2 then card 14; `hass/skills/model.py` FW-1 then card 1 then card 15;
`hass/skills/testkit.py` (#518, merged) then card 4 only.

---

## Where things stand (for the record; the decisions are at the top)

* Merged skill code: framework, registry, lint, backlog (#516), test kit (#518), items (#527), makers (#528), stock (#532); plus the
  weekly specials on the site (#520), plain wording and the problems log (#523, #524), the GPU interpreter (#509).
* Open and waiting: FW-2 (#525), FW-3 (#526), SPECIALS (#529), HIKES (#530), SHOP (#531), the new-item prototype (#504).
* Nothing is live: approvals are on hold, so **no frequency above is measured**. The first measured frequencies come from the
  weekly report (card 2) once Mike's trial runs: approved changes per skill per week (`history`), backlog rows, and the pattern
  skip rate.
* Unverified here and worth one operator check each: (a) the fleet router at `127.0.0.1:8010` serves **only local** models for the
  model name Hass is configured with (Hass's client enforces loopback, but a router could forward a name elsewhere); (b) the
  backup folder is not copied off the box (the ledger sits in the backed-up database); (c) the real dispatcher latency for a cloud card
  (never measured; part 3.4 depends on it).

*End of task map.*
