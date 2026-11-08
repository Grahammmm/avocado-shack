# The hike page, spots left and RSVPs (design, HASS-HIKEPAGE-1)

Design and audit only. Nothing in the code, the live site, Cloudflare or any API was changed, no live address was called and no RSVP row was read.
Evidence, measurements and the card plan are in `reports/hass/HIKEPAGE-1.md`. Written 2026-11-08 (Sunday), against `origin/main` dead9f7.

Labels used below: **VERIFIED** = I ran it or saw it in this session. **READ** = read in the code or a repo document. **UNVERIFIED** = a reasonable expectation I could not check without breaking the "touch nothing live" rule.

---

## 0. Decisions for G (read these first)

One line each; the recommendation is the first option. Nothing in the build waits on a decision that has a default, except 4 and 6, which block live release only.

| # | Question | Recommendation | Why |
|---|---|---|---|
| **1** | **There is no online RSVP on the live site today.** The live site is a static page; the RSVP form and `/api/community` exist only in a local test server on AgentOrange. So: **A)** for now people join by asking at the Shack, phoning or telling Mike, Mike tells Hass, and the page shows "N spots left" within minutes. **B)** also build a real online sign-up now (a small Cloudflare function and database, your Cloudflare login, a token that must be kept away from the agents). | **A now, B later** as its own card after Monday | A needs no new service, no Cloudflare change and no stored secret. B is a bigger, attended job (section 3.6). |
| **2** | Is **6 a default or a hard ceiling**? **A)** default 6 per hike, Mike can raise or lower it per hike. **B)** never more than 6. | **A** | You said "max six"; some walks (a group at a market day) may want 8. B is one line to add later if you want it. |
| **3** | New hikes get **sign-up ON with 6 spots** (this replaces the earlier D8 default "sign-up off")? yes / no | **yes** | "Spots left" means nothing on a hike with sign-up off. Hass still never invents anything else about the hike. |
| **4** | May Hass **publish the spots-left number by itself** after Mike adds or removes someone (numbers only, its own limit of 30 a day and 2 minutes apart, separate from the 10-a-day content limit)? yes / no | **yes** | The only way to keep a live count on a static site without spending the 10-a-day changes Mike needs for stock and text (section 3.3). This is a new kind of live publish, so it is your call. |
| **5** | **Topo map:** **A)** a topo map built once per route from free US government (USGS) data and OpenStreetMap lines, served from our own site; **B)** a link to an official map only; **C)** a live map from a map company. | **A** (we already have it for Point Buchon) | Fast, free, no visitor tracking, no keys. Two of the three routes still need their route data collected (section 2.3). |
| **6** | May a hike's trail facts (distance, difficulty, time, route link, meeting address) **go live from chat** when they are copied unchanged from our own reviewed route page? yes / no | **yes, after Monday's trial** | Today every hike that carries those facts is "private-only": Hass can draft it but a human must release it. A full page per hike makes that the normal case. This is the protected D4 boundary, so it is yours. |
| **7** | Keep guest **names only 30 days after the hike**, then erase them (the counts stay)? yes / no | **yes** | The names are only needed to run the hike. |

Defaults I chose (change them if you disagree; none needs an answer first): a spot is one **person** ("Jenna and a friend" = 2); Mike is not counted; names appear **only** in Mike's own chat; Hass never messages guests (outbound stays held), it tells Mike who is next on the waitlist and he contacts them; the first version needs one `yes <code>` for every RSVP change, like every other change (section 4.4).

---

## 1. The page today, field by field

Screenshots: `reports/hass/hikepage-1/01-live-static-hike-page.jpg` (the live site's own files served on loopback, which is what a visitor gets), `02-scratch-hike-with-api.jpg` (a made-up scratch hike through the local test server), `03-topo-layer.jpg` (the Topo button). VERIFIED.

### 1.1 What is live and how it works

* The live site is **static**: `Grahammmm/theavocadoman-site`, deployed by Cloudflare Pages from GitHub. The site checkout has no `functions/`, no worker, no `wrangler` file, no database binding (VERIFIED by listing it), and the repo's own static-site check asserts "no /api, POST answered with an HTML 405" (`storefront-mockup/static-site-qa.cjs`, READ). I did **not** call the live site, so "no `/api` live" is an inference from the code and the runbook; one `GET /api/community` by the operator would settle it.
* `/hike` is `hike/index.html` plus **`community.js`**, which builds the whole hike section in the browser. It first tries `GET /api/community`; if that fails it reads the published `community.json`, and marks every event `staticSite: true, remaining: null, rsvpOpen: false`.
* `/api/community` and `POST /api/community/rsvps` exist only in `storefront-mockup/community-server.py`, a **local** Python server (127.0.0.1, SQLite in `community-data/community.sqlite3`, it refuses a POST that does not come from loopback). READ.
* The live copy of `community.js` is older than `main` (it is the first published build, `c02e1eb`); `main` has later fixes (calendar location, past-hike entries). The next live release brings them.

### 1.2 What a visitor sees on `/hike` today (no real hike is scheduled)

| Where | What it shows | Where the words come from |
|---|---|---|
| Top | "North Coast Hiking Club." with Michael's photo and a short welcome | fixed text in `hike/index.html` |
| "THE NEXT HIKE" card | **A sample invitation** for Point Buchon, labelled "Sample invitation · plans to be confirmed". Date line "Sunday, November 8 · 9:00 am" (the sample is dated today; from tomorrow the code replaces it with "Date to be confirmed", READ) | `hiking-preview.json` + the Point Buchon route idea in `community.json` |
| Photo | A licensed photo of the bluffs with its credit (Mike Baird, CC BY 2.0) | `assets/trails/point-buchon-coast.webp` |
| Stats band | Round trip 6.7 miles, Difficulty Moderate, Elevation change, Allow 3–4 hours | route idea fields `distance`, `difficulty`, `elevation`, `duration` |
| **Map** | **An interactive map, Point Buchon only**: Aerial / Topo buttons, zoom and drag, the route in orange from Coon Creek parking to the turnaround, north arrow, scale, credits, and an elevation profile with a slider (~600 ft up and down) | `trail-explorer.js`, `assets/trails/point-buchon.json`, `-aerial.webp`, `-topo.webp` |
| Meet / on the trail / bring | Meet time, meeting place and address, start and back times, what to bring, an access note ("check-in with the trail attendant, no pets"), a trail-information link | `hiking-preview.json` |
| "WALK WITH US" | A sample RSVP form: "0 confirmed guests", name, how many (1–6), email, "Count me in", and the line "Sample RSVP · nothing is sent or saved." | `community.js` (`sampleInvitation`) |
| Trail journal | Sample archive: Cass Hill (October) and Fiscalini Ranch (September), each with its stats and an "Explore this trail" link; labelled "Sample archive · these outings are not confirmed club history" | route ideas + `hiking-preview.json` |
| Bottom | "Hear about the next one" email form, **disabled** with "Online signup isn't open yet. Please say hello at the Shack instead." | `community.js` |

`community.json` has `events: []` (no real hike) and three route ideas: Point Buchon, Cass Hill, Fiscalini Ranch, each with distance, difficulty, elevation, duration, route type, terrain, description, source link and status. RSVPs are off on all three (the content check forces it).

**"maps" in `hike/index.html`:** it appears once, in the page's meta description ("…trail maps, elevation profiles and community outings"). It is not a map. The real map is drawn into the page by `trail-explorer.js` and exists for Point Buchon only (`EXPLORER_TRAILS = {idea-point-buchon}` in `community.js` and a hard-coded `/assets/trails/point-buchon.json` in `trail-explorer.js`). VERIFIED.

The map costs the visitor nothing in privacy: loading the page and scrolling to the map contacted only our own host (VERIFIED with the browser's resource list). The 1.8 MB aerial image loads when the map is within one screen of view and it is the default view; the topo image (0.4 MB) loads when Topo is pressed.

### 1.3 What a real hike looks like today (the gap G noticed)

A real event (one in `events[]`) is **not** drawn with the nice invitation layout. It gets a plainer card (`hike-event`): date, title, description, a list of facts (Meet, Meet at, Address with a Directions link, Start, Back, Distance, "Pace / terrain" = difficulty, Time on trail, Bring along), an access note, a route line with the source link, the map **only if** the hike's route is Point Buchon, an "Add to calendar" link, and then the join line:

* with the local API answering: "N places available" and an RSVP button; "This hike is full." at 0; "N confirmed guests" above the facts;
* on the static live site: "To join, ask at the Shack." (sign-up on) or "RSVP details will be shared when confirmed." (sign-up off). **No spot count, no capacity, no map for Cass Hill or Fiscalini, no elevation, no route type or terrain.**

So the rich page G is thinking of is the **sample** layout; real hikes get the plain card. The standard in section 2 makes every real hike use the rich layout.

---

## 2. The hike page standard

One layout for every hike, drawn by one renderer in `community.js` from the hike's own record plus its route idea (if `trailId` names one). The route idea supplies the route facts, so the same words are never typed twice and never invented.

### 2.1 The fields

"REQUIRED" = the page always shows it (a missing one shows the stated placeholder, never a guess). "Cannot create" = Hass will not draft the hike without it. Mike's own words are the only source of facts; defaults are set by code and shown to him as "I set: …".

| # | Field | Status | Comes from | If it is missing the page shows |
|---|---|---|---|---|
| 1 | Title | REQUIRED, cannot create | hike | (not possible) |
| 2 | Day and start time | REQUIRED, cannot create | hike `startsAt` | (not possible) |
| 3 | Meeting place | REQUIRED, cannot create | hike `meetingPoint` | (not possible; existing rule) |
| 4 | Meet time and back time | OPTIONAL | hike `meetTime`, `returnTime` | the lines are left out; start time still shows |
| 5 | Meeting address + Directions link | OPTIONAL | hike `meetingAddress` | no address line, no Directions link |
| 6 | Difficulty | REQUIRED | hike, else the route idea | "Difficulty: to be confirmed" |
| 7 | Distance | REQUIRED | hike, else the route idea | "Distance: to be confirmed" |
| 8 | Time on trail | REQUIRED | hike `duration`, else the route idea | "Time: to be confirmed" |
| 9 | Elevation change | OPTIONAL | route idea `elevation` (and the map's profile when the route has one) | the tile is left out |
| 10 | Route type and terrain | OPTIONAL | route idea `routeType`, `terrain` | left out |
| 11 | Description in the shop's voice | REQUIRED | the route idea's reviewed description; else Mike's words (Hass may tidy them into two or three plain sentences for him to correct, as the new-item drafter does); never trail facts he did not give | "Michael will share the details soon." |
| 12 | **Topo map** | REQUIRED (a built map where the route has one, otherwise the official-map link; never an invented map) | per-route map files (section 2.3); else route idea `sourceUrl` | "Trail map: official guide ↗" when the route has a source link; "Map to come." when there is no route |
| 13 | What to bring | REQUIRED | Mike's words; else the house line **"The usual: water, sturdy shoes, a layer and a snack."** shown on the draft as "I set: the usual bring list" | (never missing, it has a default) |
| 14 | **Spots left** | REQUIRED | hike `capacity` (default 6) and the count (section 3) | (never missing, it has a default); "6 spots" when the count is not known |
| 15 | How to join | REQUIRED | derived from sign-up and the join mode | "To join, ask at the Shack." (today); the form (online, later) |
| 16 | Access note (permits, no pets, check-in) | OPTIONAL | hike `accessNote` | left out |
| 17 | Photo | OPTIONAL | licensed photo with its credit | no photo; the layout closes up |
| 18 | Add to calendar | automatic | existing `.ics` | (always for an upcoming hike) |
| 19 | Credits (USGS, OpenStreetMap, photo) | automatic | map files | (always with a map or photo) |

Nothing here changes the rule that Hass never invents difficulty, distance, trail facts or a photo. A required fact Mike does not know yet shows "to be confirmed" and Hass lists it under "Still missing" in `status` until he supplies it.

What is **new work** (not in the content model or the page today): fields 9, 10 live on the route idea only, so a hike on a **brand-new route** is two records, a route idea (`route.add`, undated, all route facts, a source link) and the hike (`hike.create` with `trailId`); the single renderer (field table above) for real hikes; the spots line; the default capacity; map files for more than Point Buchon.

### 2.2 The layout (one card, top to bottom)

1. Label (THE NEXT HIKE / COMING UP / TODAY), date and time, title, place line.
2. Description and "A community hike led by Michael Wolfe."
3. Photo if there is one.
4. Stats band: distance, difficulty, elevation, time.
5. **Spots line** (large and plain): "4 spots left" / "1 spot left" / "Full. Ask at the Shack to go on the waitlist."
6. Topo map and profile (or the official-map link).
7. Meet at / on the trail / bring along / access note.
8. How to join (and the calendar link).

### 2.3 Topo map: options and recommendation

| | A. Built once, served from our site (what Point Buchon has) | B. Link to an official map | C. Live map tiles in the page |
|---|---|---|---|
| What the visitor gets | Our own topo image with the route drawn on it, zoom and drag, elevation profile; an Aerial toggle is optional | A text link that opens someone else's page | A pan/zoom map that loads tiles as you move |
| Source and licence | USGS The National Map topo (US government work, public domain; USGS asks for credit, [policy](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits)); route line from OpenStreetMap data (ODbL, "© OpenStreetMap contributors" shown on the map); elevation from USGS 3DEP. All recorded in `reports/hiking-club/TRAIL_MAP_SOURCES.txt` | nothing is copied | OpenStreetMap's own tile server allows light use only with attribution, a proper User-Agent/Referer and caching, with **no guarantee and the right to block** ([policy](https://operations.osmfoundation.org/policies/tiles/)); other providers need an account key and billing |
| Cost | free; the work is one build per route | free | free for OSM at low use, otherwise paid plus a key (money and a credential for G) |
| Speed | topo image about 0.4 MB, loaded only when near the screen (aerial 1.8 MB is optional) | none | many small tile requests plus a map library |
| Visitor privacy | **no third-party request at all** (VERIFIED on the live site's files) | the visitor leaves to the other site only if they click | **every visitor's address and page go to the tile host on load** |
| Works offline of third parties | yes | n/a | no |
| Effort per route | needs the route's trail line, turnaround point and map frame collected and checked (a build step, not a chat step) | minutes | low |

**Recommendation: A**, generalised so any route with files gets the same map (the explorer reads the route id instead of the hard-coded Point Buchon), with **topo as the default view** and aerial loaded only when pressed (it is 4× the size and G asked for topo). **B is the fallback** for any route that has no built map yet, so a hike is never blocked on map work.

Honest state of the routes (READ, `reports/hiking-club/route-map-sources-2026-11.md`): Point Buchon is done. **Cass Hill and Fiscalini are blocked on data**: the trail line and turnaround for Cass Hill, and the exact map frame for both, are not settled, and neither has a reusable photo confirmed. Chat cannot fix that; it needs a short build step with a person checking the line against the official guide. The route builder must also stop being Point Buchon-only: `sitegen.py` lists the map files by name (`PUBLISH_ASSETS`) and `trail-explorer.js` hard-codes `point-buchon.json`.

---

## 3. Spots left and RSVPs

### 3.1 What exists today (READ, and VERIFIED on a scratch copy)

| Question | Answer |
|---|---|
| Where are RSVPs stored? | In SQLite on AgentOrange, `community-data/community.sqlite3`, table `rsvps(event_id, email, name, party_size 1–6, created_at)`, unique per (event, email), file mode 0600, outside git. **Only the local test server writes it; the live site has no way to.** |
| Who can read it? | The Linux user on AgentOrange that runs the test server and Hass (same account). The public side only ever returns counts (`confirmedGuests`, `remaining`), never names or emails (READ; the repo's own QA asserts it). |
| How does Hass learn the count? | `hass/ops/hikes.py: guest_counts()` opens that file **read-only** (`mode=ro`, `query_only`) through the private setting `guestCountsDb`: seat totals only, never names, fail closed ("guest count unavailable"). **No token, no credential, no network.** I did not read the host config, so whether `guestCountsDb` is set on the live Hass is UNVERIFIED (`health` reports it). |
| Capacity | `events[].capacity` exists (positive whole number up to 1000) and is optional; there is **no default**. |
| Two people, last spot | **Safe.** The POST runs in one `BEGIN IMMEDIATE` transaction that counts seats and inserts together. VERIFIED on a scratch server with synthetic names: with 2 of 6 seats left, 8 simultaneous one-seat RSVPs gave exactly **2 saved and 6 refused** ("There aren't enough places left…"), and a 2-person group when 0 remained was refused. |
| Cancel / remove | **Does not exist.** No endpoint, no op. |
| Walk-in or phone | **Does not exist.** The table needs an email, so Mike cannot add "Jenna and a friend" without inventing one. |
| Page | `community.js` already says "N places available" / "This hike is full." **when the API answers**; on the live static site it cannot. |

### 3.2 The data flow (end to end)

```
 Mike's chat ──► Hass (AgentOrange) ──► private roster  (state folder, 0600, never in git)
 (add / cancel /                         names + seats + waiting list
  who / limit)                                │ counts only (integers)
                                              ▼
                                   hass/content/spots.json ──► site build ──► hike-spots.json  (public)
                                                                       published as its own capped class
 Visitor's browser:  community.js  ──►  /hike-spots.json  ──►  "4 spots left"   (no names, ever)
```

* **The roster** is a new private store under Hass's state folder (`rsvp.sqlite3`, mode 0600, the same user and the same box as `conversation.sqlite3`; not the content store, not git, not the website). One row per party: `hike id, name, seats, status (confirmed / waitlist / removed), source (chat / site), created, updated`. Chat adds store **name and seats only** (no phone number or email: Mike already has those). Later site-form rows (section 3.6) also carry the email the form collected.
* **Taken** = the sum of `seats` where status is confirmed. **Left** = capacity − taken. These are computed in code, never by the model.
* **Hass needs no credential to know the count**, because it is the one writing the roster. For the old local test database it keeps using the existing read-only `guestCountsDb`.
* **Only integers go public** (`hike id → capacity, taken`, plus an "as of" time). No names, no emails, no party details.

### 3.3 How the public page gets the count without a republish per RSVP

| Option | How it works | Fits today? | Problems |
|---|---|---|---|
| **(a) page reads the count from the API at load** | `community.js` asks `/api/community` (it already does) and shows `remaining` | **No.** There is no public API on the static site | needs the backend of option B in decision 1: a Cloudflare function, a database and a stored token |
| **(b) Hass publishes a small counts file, as its own capped class** | `hike-spots.json`, integers only, written when the roster changes, released as class `counts` with its own limit (proposed 30/day, 2 minutes apart, changes coalesced) | **Yes** | a new live-publish class (decision 4); a count can lag by a few minutes, and by longer if a release is held |
| **(c) a rebuild and publish per RSVP** | the normal content publish after every RSVP | Yes, but worst | spends the shared **10-a-day** limit that stock, text and hikes also need, and a busy sign-up day plus one stock change exhausts it; same lag as (b) |

**Recommendation: (b) now, and keep `community.js` API-first so (a) takes over unchanged if option B is ever built.** The page uses `remaining` when the API answers, else the counts file, else the capacity only ("6 spots"). To keep the lag honest the line carries a small "Updated 10:12 am", and a count is trusted only if its capacity equals the hike's capacity in `community.json` (a stale file after a limit change shows "6 spots", not a wrong number). Hass also tells Mike when the site lags, using the website-outcome message it already sends (shown / not published / unknown).

`hike-spots.json` is validated mechanically before release (known hike ids, whole numbers, `0 ≤ taken`, `1 ≤ capacity ≤ 1000`, nothing else): there is no wording to review, so it needs no claims check. The cap, spacing, STOP file and journal rules are the existing ones, with their own counter.

If the "counts" release is stuck (STOP, cap, network), nothing is lost: the roster is the truth and the next sync fixes the page. Because the join line always says "ask at the Shack", a stale count is an estimate, and Mike has the final word.

### 3.4 The last spot

* **Today's API:** atomic (VERIFIED above). Keep it.
* **Chat (version 1):** only Hass writes the roster, one writer, one transaction per change (`BEGIN IMMEDIATE`, count and insert together), so two messages cannot both take the last seat. Over capacity is never saved: Hass asks "Saturday has 1 spot left and that's 2 people. Put them on the waitlist, or raise the limit?"
* **Both at once (site form + chat), only if option B is built:** the rule must be one store, one check. The form function inserts with a single conditional statement (`INSERT … WHERE seats-so-far + party ≤ capacity`), and Hass changes the same store through the bridge in 3.6. A copy of the count held in two places is not allowed, because two copies can both say "one spot left". UNVERIFIED until built and tested.
* **Cancelling** reduces taken; if there is a waitlist, Hass tells Mike who is first and **asks** whether to move them in (a group that does not fit waits). It never moves anyone by itself and never messages a guest.

### 3.5 Privacy

| Data | Where it may be | Who sees it | Leaves the box? |
|---|---|---|---|
| Guest names, seats, waitlist | the roster only | Hass code; Mike in his own chat (`who is coming`) | **No**, except in Mike's chat reply (see below) |
| Count (taken, capacity) | roster, `spots.json`, public `hike-spots.json` | everyone | yes, on purpose; integers only |
| Phone numbers / emails | **not stored** for chat adds; the site form's emails stay in the form store | nobody else | no |
| Correspondence log | reason code and skill name **only**; no excerpt of Mike's text for RSVP skills, no names, no numbers | G (weekly summary) | no (and nothing in it can name a guest) |
| Interpreter (local model) | loopback only (READ, `interpreter_local.py`); it sees Mike's own sentence to pick the skill; roster names are never put in its prompt, only counts | none | no |
| Interpreter audit, stage log | no text at all (READ) | operator | no |
| Approvals and change records (kept 2 years in the proposal) | a **pending-row id** and seats, not the name: the draft stores the name in the roster as a `pending` row that expires after 24 h or on `no`; the approval carries only the id | operator | no |
| Open-request texts | erased 24 h after close (D7) | operator | no |
| Release journals, git, reports, logs, this document | counts only, never a name | — | — |
| Chat history in Hass and in Messages | replies to Mike that contain names, kept like his other messages (1 year, H21 proposal) | Mike, operator | **names travel to Mike's phone by iMessage, the same channel as all his messages; this cannot be avoided for "who is coming"** |

Purge (decision 7): 30 days after the hike, names are erased from the roster and counts stay. `who is coming` answers only to an owner number; from G's chat or anyone else it says "I can only share that with Michael." Names are never added to the interpreter prompt, the morning report, the social drafts or the recap announcement (the recap announcement already adds no people count).

Two existing places need a small change so they cannot leak a guest: the correspondence log's 80-character excerpt does not blank letters (only numbers, addresses and links), so RSVP skills must be marked private-text and log no excerpt; and the daily state backup must be checked at build time: it has to stay on the box and cover the roster only there (I did not verify where it writes).

### 3.6 Option B (later): a real online RSVP form, and where the credential lives

Only if G chooses B in decision 1. Pieces: a Cloudflare Pages Function for `POST /api/community/rsvps` and a public `GET /api/community`; a Cloudflare D1 database as the single roster (capacity per hike copied in by Hass); the existing form and counts in `community.js` start working unchanged. Reading or writing D1 from AgentOrange needs a Cloudflare token. **Hass (an agent) must never hold it.** Design: a small host service, run as its own unit under a separate account, owns a root-readable token file (mode 0400, never in config the agents read, never in the environment, never in git). Hass talks to it over a local Unix socket with a **closed set of commands** (`counts`, `names for one hike`, `add`, `remove`, `set capacity`), never a raw query and never the token. G installs it and creates the token (the narrowest one the Cloudflare dashboard allows for that one database; UNVERIFIED label names until it is done). This is the same pattern as the site deploy key and needs the same attended steps. Cloudflare's free tier is probably enough at this size (UNVERIFIED: check current limits before committing). Decision 1 option B is therefore a **Cloudflare change, a credential and a new live service**: it waits for G and is not on the Monday path.

---

## 4. The skill changes

All new skills use the standard shape of `reports/hass/SKILLS-SPEC.md` section 2.2 (name, label, summary, triggers ≥ 6 with a vague, a misspelt and a multi-item one, slots, rules, plan, edits, side effects, preview, approval, live class, undo, refuse, cases ≥ 10, version). Names already in use stay (`hike.add` etc.; "hike.create" is the op the skill plans). Wording follows `docs/hass/VOICE.md`: short, plain, no ids.

### 4.1 Edits to SKILLS-HIKES-1 (PR 530, open; `hass/skills/hikes.py`)

* `hike.add` v2, **builds the whole page**: slots `route` (a route idea by name), `title, day, clock, meeting_point` (asked one at a time), then **one** question for anything REQUIRED still missing ("How far is it and about how long?"; "skip" is a fine answer: the page says "to be confirmed"). When Mike names a route idea, difficulty, distance, time, route type, terrain, description and map are **copied from the route idea** (his words are not needed for them). A route that does not exist yet: Hass first drafts `route.add` (its own questions: place, short description, official source link) and then the hike, in **one** request with two drafts shown together.
* `capacity` slot: default **6** by code (`derive:default_capacity`, setting `defaultCapacity`), shown as "I set: 6 spots"; a number Mike gives wins; "no limit" stays possible. This replaces the "no capacity unless he said so" rule for the default only: the model itself may still never write a capacity (E2E-HIKE-1 saw it invent 10 and 1).
* `signup` default **on** (decision 3), still shown as "I set: sign-up on".
* `bring` default: the house line, shown as "I set: the usual bring list".
* Rule `no-invention` keeps its meaning for everything else. Rule `spots-not-below-guests` already exists for `hike.edit` (capacity never below confirmed guests); it now reads the roster.
* `hike.edit` loses `capacity` (moved to `spots.set`, which also checks the roster); `hike.cancel` keeps its warning "N spots were taken; nobody is told" (count only); `hike.recap` gains one optional line: "N people were signed up. Say 'N came' if you want that in the recap" (never automatic).
* Live class: unchanged (`private-only` while trail facts are in the draft) until decision 6.

### 4.2 New skills (all `approval: owner-yes` in version 1)

| Skill | Mike says (examples; the build card writes 10 each) | Slots | What changes | Preview | Live class |
|---|---|---|---|---|---|
| `spots.set` | "make Saturday's hike 8 spots", "Cass Hill limit 4", "no limit on Saturday" | which hike R; number or no-limit R | hike `capacity`; then counts | the hike card with the new line | `chat-live` (a number) |
| `rsvp.add` | "add Jenna and a friend to Saturday", "put Sam and Priya down for Cass Hill", "Jenna +1" | hike R; who R (name, seats; "and a friend" = +1, "family of 4" = 4); | roster row; counts | card with new count | `counts` class |
| `rsvp.remove` | "Jenna cancelled", "take Sam off Saturday", "Sam can only bring 1 now" | hike R; who R (several people with that name: asks which) | roster row removed or seats lowered | card with new count | `counts` class |
| `who.coming` | "who's coming Saturday?", "how many are signed up?", "any spots left on Cass Hill?" | hike R | read only | none | read-only |
| `waitlist` | "put Dana on the Saturday waitlist", "who's on the waitlist?", "move Dana in" | hike R; who; action | roster row `waitlist` / `confirmed` | card | `counts` class when it changes seats |
| `hike.full` | "Saturday is full", "that's enough for Cass Hill", "open Saturday back up" | hike R; close or reopen | shorthand for `spots.set`: close sets the limit to the seats already taken (the page says Full) and remembers the old limit privately; reopen puts it back. With nobody signed up it asks "Nobody is signed up. Turn sign-up off instead?" (a limit cannot be 0). No new content field is needed. A later cancellation opens a spot again, and Hass says so | card | `chat-live` |
| `hike.recap` | (extended, 4.1) | | | | |

Rules shared by the RSVP skills: `hike-scheduled` (future, not cancelled, not a sample, sign-up on), `seats-fit` (a group that does not fit is a question, never saved), `one-person-one-row` (a repeated name asks "the same Jenna?"), `no-contact-details` (a phone number or email in the message is **not stored**; Hass says so), `owner-only-names` (names only to an owner number), `private-text` (no excerpt in the correspondence log), `no-price`.

Side effects: the closed lists in `hass/skills/model.py` get new names: side effects `rsvp-roster` (private, not in git, not the website) and `spots-sync` (the counts file), and a live class `counts` (numbers only, own limit; the table above uses it). Each needs an undo statement: roster changes are undone by the inverse change on the same row (`undo` drafts it, needing its own `yes <code>`); the public count follows on the next sync.

### 4.3 Plain replies

| Situation | Reply |
|---|---|
| draft, in capacity | "Add Jenna and 1 more (2 spots) to Saturday's Cass Hill hike? That leaves 2 spots. Say yes 4F2A." |
| after yes | "Done. Saturday's hike now has 2 spots left." then, when the site is updated, "The website shows 2 spots left." |
| over capacity | "Saturday's hike has 1 spot left and that's 2 people. Want them on the waitlist, or should I raise the limit?" |
| cancel | "Take Jenna (2 spots) off Saturday's hike? That opens 2 spots. Say yes 7B31." then "Done. Saturday's hike has 4 spots left. Dana is first on the waitlist, 2 people. I haven't told her. Want me to move her in?" |
| who | "Saturday's Cass Hill hike, 4 of 6 spots taken: Jenna (2), Sam, Priya. Nobody on the waitlist." |
| full | "That's all 6. The page now says Full and offers the waitlist." |
| below guests | "5 people are already signed up, so I can't go below 5." |
| not Mike | "I can only share that with Michael." |
| site lag | "The website still shows 3 spots. I'll update it as soon as I can." |
| unknown hike | "Which hike do you mean, Saturday's Cass Hill or Sunday's Point Buchon?" |

### 4.4 Approval, undo, tests

* **Approval.** Version 1: one `yes <code>` for every change, so nothing about approval, ownership or live rules changes. The RSVP draft is short, shows only first names and counts, and has **no wording check** (names are not public claims), and the count that follows publishes without a second approval **once decision 4 is yes**. Capacity, closing and page edits use the normal draft with the picture preview. If Mike finds the extra `yes` slow while a guest is standing in the shop, a later setting can make unambiguous, in-capacity adds and cancels apply at once with the reply "Done. Say undo to take it back." That is a change to a protected rule, so it waits for the trial and for G.
* **Undo.** `undo` drafts the inverse and needs its own `yes`. Residue statements: adding a hike (cancelled page card stays, as today), an RSVP add or remove (the roster row is restored or removed; the public count follows; the guest was never told), a purged name does not come back.
* **Tests.** (1) Roster unit tests: seats, waitlist order, `BEGIN IMMEDIATE` race with 8 threads, purge at day 30, file mode 0600, no names in any log, repr, exception or journal (a scan test over every file the code writes). (2) Skill cases (≥ 10 per skill including refusals and one undo) and plan goldens on the content diff and the roster diff. (3) The counts file: schema check, the stale-capacity rule, the cap and spacing, and a "refuses a name, an email or a phone number" case. (4) `community.js` checks (the repo's `site community` CI part): spots line for 6 / 1 / 0 / null, the waitlist line, API-first fallback, nothing about a person in the page. (5) One chain on a scratch state: add hike → add 2 RSVPs → fill → waitlist → cancel → who → set limit → undo, asserting the public file never contains a name.

---

## 5. Cards, order and the Monday minimum

Full table with owned files and dependencies: `reports/hass/HIKEPAGE-1.md` section 5. In order:

1. **HIKEPAGE-SPOTS-1 (Monday minimum).** The hike card shows the limit ("Limited to 6 spots") and, when it is 0, "Full" with the waitlist line, using the hike's own `capacity`; the count source hooks (API, then counts file) are in but optional. Files: `storefront-mockup/community.js`, `hiking.css` if needed, the `community` QA fixture. Small, Sonnet medium.
2. **HIKES-1 fix round / follow-up**: default capacity 6, sign-up default, bring default (4.1, `hikes.py`; needs PR 530 merged).
3. **ROSTER-1**: the private roster, purge, privacy tests (`hass/rsvp_roster.py`, `hass/ops/rsvp.py`, editor hook).
4. **RSVP-SKILLS-1**: `rsvp.add`, `rsvp.remove`, `who.coming`, `waitlist`, `spots.set`, `hike.full`, the correspondence-log private-text flag.
5. **COUNTS-1** (needs decision 4; protected publish code): `hike-spots.json` and the `counts` release class.
6. **HIKEPAGE-CARD-1**: one renderer, the rich layout for every real hike, field table, placeholders.
7. **HIKE-ADD-2**: `hike.add` v2 and `route.add` chaining.
8. **TOPO-1**: a data-driven explorer and route builder; **TOPO-2 / TOPO-3**: Cass Hill and Fiscalini route data (blocked on collecting the route data).
9. **RECAP-2** and the retention purge (needs decision 7).
10. **ONLINE-RSVP-1** (only if decision 1 is B): attended, last.

**Monday (store test, 2026-11-09), honestly:** the minimum is "add a hike with spots shown". Mike can already say "add a hike Saturday at 9, Cass Hill gate, sign-up on, 6 spots" on the **older plain-words path** (the skills are not in the runtime, `STORE-TEST-1.md`): the hike is saved with `capacity: 6`, but **today's page does not show the number**; on the live static site it says only "To join, ask at the Shack." So the Monday minimum needs **card 1** published, which needs the operator to move the runtime to a main that contains it before the Sunday 21:00 go/no-go (an attended restart). If that is not done, the fallback uses no code: Mike says "…say in the description: limited to six people", his own words, which the page should print (not tried). **Live count updates, the waitlist, who is coming and the full per-hike page are all after Monday.**
