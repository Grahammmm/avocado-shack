# The hike page, spots left and RSVPs (design, HASS-HIKEPAGE-1)

Design and audit only. Nothing in the code, the live site, Cloudflare or any API was changed, no live address was called and no RSVP row was read.
Evidence, measurements and the card plan are in `reports/hass/HIKEPAGE-1.md`. Written 2026-11-08 (Sunday), against `origin/main` dead9f7.

Labels used below: **VERIFIED** = I ran it or saw it in this session. **READ** = read in the code or a repo document. **UNVERIFIED** = a reasonable expectation I could not check without breaking the "touch nothing live" rule.

---

## 0. Decisions for G (read these first)

One line each; the recommendation is the first option. **A recommendation is a proposal, not an approval.** Until G answers, the existing rule stays: where a decision would change something already decided, the **existing behaviour is kept** and the build cards must follow it. In particular: decision 3 would replace the existing D8 default (new hikes get sign-up **OFF**); **until G says yes to 3, sign-up stays OFF by default** (Mike can still turn it on explicitly, as in "sign-up on, 6 spots", which is also his Monday wording). Decision 2 (6 as a default rather than a ceiling) decides whether Mike may set **more than 6**; **until G says yes to 2-A, the most any hike can be set to is 6** and Hass says so. Decision 4 and 6 block live release of the cards that need them (the counts release and trail facts from chat). Everything else (the page standard, the roster, the skills) can be built now because it keeps today's defaults. The "unconfirmed" wording in section 2.1 field 14 is not a decision; it is how the page behaves whenever a count is missing.

| # | Question | Recommendation | Why |
|---|---|---|---|
| **1** | **There is no online RSVP on the live site today.** The live site is a static page; the RSVP form and `/api/community` exist only in a local test server on AgentOrange. So: **A)** for now people join by asking at the Shack, phoning or telling Mike, Mike tells Hass, and the page shows "N spots left" within minutes once decision 4 is yes (until then it shows the capacity-only line "Limited to 6 people · availability unconfirmed; ask at the Shack"). **B)** also build a real online sign-up now (a small Cloudflare function and database, your Cloudflare login, a token that must be kept away from the agents, **and guest names and any email typed in the form would be stored at Cloudflare, off the box**: sections 3.6.1 and 3.6.3). | **A now, B later** as its own card after Monday | A needs no new service, no Cloudflare change, no stored secret and no guest name leaves the box. B is a bigger, attended job and a data-exposure decision for you (section 3.6). |
| **2** | Is **6 a default or a hard ceiling**? **A)** default 6 per hike, Mike can raise or lower it per hike. **B)** never more than 6. | **A** | You said "max six"; some walks (a group at a market day) may want 8. B is one line to add later if you want it. **Until you answer A, the build treats 6 as the maximum (B)**: Hass lowers freely, refuses more than 6 and says "The most I can set is 6." |
| **3** | New hikes get **sign-up ON with 6 spots** (this replaces the earlier D8 default "sign-up off")? yes / no | **yes** | "Spots left" means nothing on a hike with sign-up off. **Until you say yes, D8 stays: new hikes are sign-up OFF**; Mike can still say "sign-up on" himself and then gets 6 spots by default. Hass still never invents anything else about the hike. |
| **4** | May Hass **publish the spots-left number by itself** after Mike adds or removes someone (numbers only, its own limit of 30 a day and 2 minutes apart, separate from the 10-a-day content limit)? yes / no | **yes** | The only way to keep a live count on a static site without spending the 10-a-day changes Mike needs for stock and text (section 3.3). This is a new kind of live publish, so it is your call. |
| **5** | **Topo map:** **A)** a topo map built once per route from free US government (USGS) data and OpenStreetMap lines, served from our own site; **B)** a link to an official map only; **C)** a live map from a map company. | **A** (we already have it for Point Buchon) | Fast, free, no visitor tracking, no keys. Two of the three routes still need their route data collected (section 2.3). |
| **6** | May a hike's trail facts (distance, difficulty, time, route link, meeting address) **go live from chat** when they are copied unchanged from our own reviewed route page? yes / no | **yes, after Monday's trial** | Today every hike that carries those facts is "private-only": Hass can draft it but a human must release it. A full page per hike makes that the normal case. This is the protected D4 boundary, so it is yours. |
| **7** | Keep guest **names only 30 days after the hike**, then erase them (the counts stay)? yes / no | **yes** | The names are only needed to run the hike. |

Defaults I chose for the **new** parts (change them if you disagree; none needs an answer first, and none overrides an existing rule): a spot is one **person** ("Jenna and a friend" = 2); Mike is not counted; names appear **only** in Mike's own chat; Hass never messages guests (outbound stays held), it tells Mike who is next on the waitlist and he contacts them; the first version needs one `yes <code>` for every RSVP change, like every other change (section 4.4).

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
| 14 | **Spots left** | REQUIRED when sign-up is on and the hike has a limit (see the state table below); when sign-up is off the page keeps today's "RSVP details will be shared when confirmed." | hike `capacity` (6 when Mike turns sign-up on without a number) and the count (section 3) | **Never a remaining-spots claim without a count.** If the count is unknown (no counts file, unreadable, hike not in it, API silent) **or its capacity does not match the hike's**, the position shows the capacity-only line **"Limited to 6 people · availability unconfirmed; ask at the Shack"** (6 = the hike's own capacity). Never "6 spots" or "6 spots left" unless the count says 6 are left |
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
5. **Spots line** (large and plain), by state (the full table, with the card wording, is in section 3.3.1): "4 spots left" / "1 spot left" / "Full. Ask at the Shack to go on the waitlist." / **"Limited to 6 people · availability unconfirmed; ask at the Shack"** when the count is not known.
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

* **The roster** is a new private store under Hass's state folder (`rsvp.sqlite3`, mode 0600, the same user and the same box as `conversation.sqlite3`; not the content store, not git, not the website). One row per party: `hike id, name, seats, status (confirmed / waitlist / removed), source (chat / site), created, updated`. Chat adds store **name and seats only** (no phone number or email: Mike already has those). This local roster is the single roster only while there is no online form. If option B is built (section 3.6), the Cloudflare D1 database becomes the single roster for upcoming hikes and this file stops holding them (one attended, one-time import, then the local copy of upcoming hikes is deleted), so there are never two rosters. Online-form rows carry the email the form collected; that email stays in D1 and never reaches Hass (3.6.3).
* **Taken** = the sum of `seats` where status is confirmed. **Left** = capacity − taken. These are computed in code, never by the model.
* **Hass needs no credential to know the count** on the default path, because it is the one writing the roster. For the old local test database it keeps using the existing read-only `guestCountsDb`. With option B it still holds no credential: it asks the bridge (3.6.1), which holds the only one.
* **Only integers go public** (`hike id → capacity, taken`, plus an "as of" time). No names, no emails, no party details.

### 3.3 How the public page gets the count without a republish per RSVP

| Option | How it works | Fits today? | Problems |
|---|---|---|---|
| **(a) page reads the count from the API at load** | `community.js` asks `/api/community` (it already does) and shows `remaining` | **No.** There is no public API on the static site | needs the backend of option B in decision 1: a Cloudflare function, a database and a stored token |
| **(b) Hass publishes a small counts file, as its own capped class** | `hike-spots.json`, integers only, written when the roster changes, released as class `counts` with its own limit (proposed 30/day, 2 minutes apart, changes coalesced) | **Yes** | a new live-publish class (decision 4); a count can lag by a few minutes, and by longer if a release is held |
| **(c) a rebuild and publish per RSVP** | the normal content publish after every RSVP | Yes, but worst | spends the shared **10-a-day** limit that stock, text and hikes also need, and a busy sign-up day plus one stock change exhausts it; same lag as (b) |

**Recommendation: (b) now, and keep `community.js` API-first so (a) takes over unchanged if option B is ever built.** The page uses `remaining` when the API answers, else the counts file, else **the capacity-only line, never a remaining-spots number** (section 3.3.1). To keep the lag honest the line carries a small "Updated 10:12 am", and a count is trusted only if its capacity equals the hike's capacity in `community.json` (a stale file after a limit change shows the capacity-only line with the hike's current limit, not a wrong number and not "6 spots"). Hass also tells Mike when the site lags, using the website-outcome message it already sends (shown / not published / unknown).

`hike-spots.json` is validated mechanically before release (known hike ids, whole numbers, `0 ≤ taken`, `1 ≤ capacity ≤ 1000`, nothing else): there is no wording to review, so it needs no claims check. The cap, spacing, STOP file and journal rules are the existing ones, with their own counter.

If the "counts" release is stuck (STOP, cap, network), nothing is lost: the roster is the truth and the next sync fixes the page. Because the join line always says "ask at the Shack", a stale count is an estimate, and Mike has the final word.

#### 3.3.1 What the Spots-left position shows, state by state

Capacity (a limit) and availability (how many are left) are different facts. The page may state the limit from `community.json` on its own; it may state "left" only from a count whose capacity matches. This table is the single source for the page, the card, the skill previews and the tests (section 4.4); `C` = the hike's own capacity.

| # | State | Page and card show |
|---|---|---|
| 1 | Count known, capacity matches, left = N, N ≥ 2 | "N spots left" |
| 2 | Count known, left = 1 | "1 spot left" |
| 3 | Count known, **left = 0** | "**Full.** Ask at the Shack to go on the waitlist." (the card says "Full") |
| 4 | **Capacity C, taken unknown** (counts file missing or unreadable, hike not in it, API silent, `null`) | "**Limited to C people · availability unconfirmed; ask at the Shack**" (never a number of spots left) |
| 5 | **Capacity mismatch** (the count was made for another limit) | same as 4, using the limit now in `community.json` |
| 6 | Sign-up off | "RSVP details will be shared when confirmed." (today's line; no spots line) |
| 7 | No limit (`noCapacityLimit`) | no spots line; "To join, ask at the Shack." |

Rows 1–3 need a trusted count, so before the count source exists (the Monday minimum) every hike with a limit is in row 4, and that is what Mike's Monday hike shows. Row 4 is also what a full hike shows if the counts file is unreadable: it never looks like an empty hike.

### 3.4 The last spot

* **Today's API:** atomic (VERIFIED above). Keep it.
* **Chat (version 1):** only Hass writes the roster, one writer, one transaction per change (`BEGIN IMMEDIATE`, count and insert together), so two messages cannot both take the last seat. Over capacity is never saved: Hass asks "Saturday has 1 spot left and that's 2 people. Put them on the waitlist, or raise the limit?"
* **Both at once (site form + chat), only if option B is built:** the rule must be one store, one check. The form function inserts with a single conditional statement (`INSERT … WHERE seats-so-far + party ≤ capacity`), and Hass changes the same store through the bridge in 3.6. A copy of the count held in two places is not allowed, because two copies can both say "one spot left". UNVERIFIED until built and tested.
* **Cancelling** reduces taken; if there is a waitlist, Hass tells Mike who is first and **asks** whether to move them in (a group that does not fit waits). It never moves anyone by itself and never messages a guest.

### 3.5 Privacy

**This table is for the default path (decision 1 = A: no online form, chat adds only).** The claim "guest names do not leave the box" holds **only on that path**. If G chooses option B (section 3.6), guest names, seats and any email a visitor types **are stored at Cloudflare, off the box**, and the extra table and the logging boundary in **section 3.6.3** replace the "No" answers in the first and third rows. Section 3.6.3 is part of decision 1: choosing B means accepting that off-box storage.

| Data | Where it may be | Who sees it | Leaves the box? |
|---|---|---|---|
| Guest names, seats, waitlist | the roster only | Hass code; Mike in his own chat (`who is coming`) | **No**, except in Mike's chat reply (see below). **With option B: yes, see 3.6.3** |
| Count (taken, capacity) | roster, `spots.json`, public `hike-spots.json` | everyone | yes, on purpose; integers only |
| Phone numbers / emails | **not stored** for chat adds. With option B the online form's email goes to Cloudflare, not to Hass (3.6.3) | nobody else on the default path | no on the default path. **With option B: yes, to Cloudflare** |
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

Only if G chooses B in decision 1. Pieces: a Cloudflare Pages Function for `POST /api/community/rsvps` and a public `GET /api/community`; a Cloudflare D1 database as the single roster (capacity per hike copied in by Hass); the existing form and counts in `community.js` start working unchanged. Reading or writing D1 from AgentOrange needs a Cloudflare token. **Hass (an agent) must never hold it.** The design below says exactly which account owns the token, how the bridge process gets it, and who may talk to the bridge. Decision 1 option B is a **Cloudflare change, a credential, a new live service and off-box storage of guest names and emails (3.6.3)**: it waits for G and is not on the Monday path. Cloudflare's free tier is probably enough at this size (UNVERIFIED: check current limits before committing).

#### 3.6.1 The credential holder: accounts, ownership, permissions

Three separate identities. Nothing here gives any agent a way to read the token.

| Identity | What it is | What it may touch |
|---|---|---|
| `root` (G, attended, via sudo) | installs the files and units once, rotates the token | owns the token file; no agent has root, sudo or membership of any group that can read it (checked at install, below) |
| `hass-rsvp` | new system account: no login shell, no home, no password, no sudo, no other files. Runs **only** the bridge unit | reads the token (via the systemd credential below), the bridge's own program, and its socket |
| the Hass account (the user that runs Hass and the other agents) | unchanged | may connect to the bridge socket and nothing else; **cannot read the token, the token's folder or the bridge's process memory** |

* **Token file:** `/etc/hass-rsvp/cf-token`, owner `root:root`, mode `0400`, in a folder `/etc/hass-rsvp/` owned `root:root`, mode `0700`. G creates it by pasting the token into `sudo install -m 0400 -o root -g root /dev/stdin /etc/hass-rsvp/cf-token` in an attended terminal, so it is never typed into a chat, an agent's file or a shell history an agent can read. It is never in the environment of any agent, never in `settings`/config the agents read, never in git, never in a log.
* **How the bridge, which is not root, gets a root-only file:** the unit is `hass-rsvp-bridge.service` with `User=hass-rsvp` and `LoadCredential=cf-token:/etc/hass-rsvp/cf-token`. systemd (which runs as root) reads the file and hands it to that one service as a private file under `$CREDENTIALS_DIRECTORY` (a per-service, in-memory folder readable only by `hass-rsvp`). The bridge reads the token from there at start and keeps it in memory. A mode-0400 root-owned file is therefore workable without making the file readable by the bridge account or by anyone else. (UNVERIFIED: this needs systemd 247 or newer on AgentOrange; the build card checks `systemctl --version` first.)
* **Fallback if systemd is older:** the file is owned `hass-rsvp:hass-rsvp`, mode `0400`, in `/etc/hass-rsvp/` owned `hass-rsvp:hass-rsvp` mode `0700`. The property that matters is the same: the owner is the bridge account, not the Hass account. The install check below must pass either way.
* **Unit hardening:** `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `PrivateDevices=yes`, `CapabilityBoundingSet=` (empty), `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`, `UMask=0077`, and outbound network allowed to the Cloudflare API host only if the box's firewall supports it (UNVERIFIED; otherwise the closed command list is the limit). The bridge has no debug route, no environment dump and no "show config".
* **The socket:** `/run/hass-rsvp/bridge.sock`, owner `hass-rsvp`, group `hass-rsvp-clients`, mode `0660`; the Hass account is the only member of `hass-rsvp-clients`. The bridge also checks the connecting process's user id with `SO_PEERCRED` and refuses any user id that is not the Hass account's, so a file-permission mistake alone does not open it.
* **The closed command list** (each is one fixed D1 statement with bound parameters; there is no raw query, no "run this SQL" and nothing that returns the token): `counts` (capacity and seats taken per hike, integers), `names` (names and seats for **one** hike, **no email**), `add` (name, seats, hike; one conditional insert that refuses over capacity), `remove` (one row), `set_capacity`, and `purge` (deletes all rows of hikes older than the retention date, decision 7). Anything else is refused and counted.
* **What an agent could still do:** ask the bridge to run those six commands. That is the intended power, it is bounded by the closed list, and every call is logged by name of command only (3.6.3). It cannot read the token, change the Cloudflare project, other databases or DNS: the token is the narrowest one the Cloudflare dashboard allows for this one D1 database (UNVERIFIED: label names and whether per-database scope exists, until G does it; if only a wider token exists, G is told before anything is installed and this is a new decision).
* **Install check (attended, the build card's acceptance):** as the Hass account, `cat /etc/hass-rsvp/cf-token` and `ls /etc/hass-rsvp/` fail with permission denied; `sudo -n true` fails; `id` shows no group that owns the token; `ps`/`/proc/<bridge pid>/environ` and `/proc/<pid>/mem` are not readable; the socket accepts the Hass account and refuses another account; a command outside the list returns "refused"; `journalctl -u hass-rsvp-bridge` and the bridge's own log contain no token, name or email after a test run with synthetic names. If the Hass or any agent account turns out to have root or sudo on the box, this design does not hold and G is told before anything is installed.
* **Rotation and removal:** G replaces the file and restarts the unit (token rotation, no code change); deleting the file and stopping the unit turns the whole online path off with no other effect on Hass.

This is the same shape as the site deploy key (a credential an agent can use through a narrow door but cannot read) and needs the same attended steps. The credential rule in one line: root owns the file, `hass-rsvp` is the only process that receives it, Hass only gets the socket.

#### 3.6.2 One store, one check

D1 is the single roster for the hikes that take online sign-ups (3.2, 3.4). The form function and the bridge both write it with the same conditional insert; Hass never keeps its own copy of those hikes' names. UNVERIFIED until built and tested with a simultaneous form and chat add.

#### 3.6.3 Option B privacy and logging boundary (replaces the "No" answers in 3.5)

What leaves AgentOrange or the visitor's browser and lands at Cloudflare, a third party, when option B is on:

| Data | Where | Who can read it | Notes |
|---|---|---|---|
| Name, seats, status, created time | Cloudflare D1 (single roster) | G (Cloudflare dashboard); the Function; the bridge; Mike through Hass (`names`, owner number only) | **Off-box.** Region and Cloudflare's own retention are UNVERIFIED and are checked before G chooses B |
| Email, if the visitor types one | Cloudflare D1, same row | G (dashboard) only. **The bridge's `names` and `counts` never return it, so it never reaches Hass, Mike's chat, the interpreter or any log.** Hass cannot learn an email | Recommendation: the online form's email is optional and the page says what it is for (the shop contacting you about the hike; nothing is sent automatically). Today's local form requires one, so this is a form change in ONLINE-RSVP-1 |
| Visitor IP address and request metadata | Cloudflare's own edge logs | Cloudflare | Cannot be switched off. The Function does not read, store or forward the IP, and no analytics script is added to the page |
| Counts | D1, the bridge, `spots.json`, public `hike-spots.json` | everyone (integers) | unchanged from 3.5 |

Rules the build must keep (each one is a test or a checklist line in ONLINE-RSVP-1):

* **The Function** returns only the same fields as today's public API (`confirmedGuests`, `remaining`). It never echoes a name or email back to any other visitor, and error messages are fixed text. It does not `console.log` a request body, name or email; no Cloudflare log, tail or analytics sink is turned on for it that would keep one (UNVERIFIED: the Pages dashboard options are checked at install).
* **The bridge** logs the command name, hike id, row count and outcome code only. Never a name, email, token, SQL text or Cloudflare response body. Its error paths log the code, not the payload. `names` is answered only to the Hass account and Hass shows it only to an owner number (3.5).
* **Hass** treats `names` output like the local roster: never in a log, journal, report, the correspondence log (RSVP skills are private-text), the interpreter prompt or git. The scan test of section 4.4 also covers the bridge's log file and its journal.
* **Retention:** the same decision-7 rule applies in D1: the bridge's `purge` runs daily by Hass's scheduler and deletes names **and emails** 30 days after the hike, counts stay. Deleting from D1 is not the same as every copy being gone: D1's own point-in-time backups may hold a row for a while (UNVERIFIED: the period is checked and written here before G chooses B).
* **Exposure approval:** storing guest personal data at Cloudflare is a data-exposure decision that belongs to G. Decision 1 option B is not approved by the build cards; ONLINE-RSVP-1 starts only after G has accepted this section in writing on the card.
* **Backups and exports:** no D1 export is made to the box, to git or to a report; any export G takes by hand from the dashboard is his to handle and is outside Hass.

---

## 4. The skill changes

All new skills use the standard shape of `reports/hass/SKILLS-SPEC.md` section 2.2 (name, label, summary, triggers ≥ 6 with a vague, a misspelt and a multi-item one, slots, rules, plan, edits, side effects, preview, approval, live class, undo, refuse, cases ≥ 10, version). Names already in use stay (`hike.add` etc.; "hike.create" is the op the skill plans). Wording follows `docs/hass/VOICE.md`: short, plain, no ids.

### 4.1 Edits to SKILLS-HIKES-1 (PR 530, open; `hass/skills/hikes.py`)

* `hike.add` v2, **builds the whole page**: slots `route` (a route idea by name), `title, day, clock, meeting_point` (asked one at a time), then **one** question for anything REQUIRED still missing ("How far is it and about how long?"; "skip" is a fine answer: the page says "to be confirmed"). When Mike names a route idea, difficulty, distance, time, route type, terrain, description and map are **copied from the route idea** (his words are not needed for them). A route that does not exist yet: Hass first drafts `route.add` (its own questions: place, short description, official source link) and then the hike, in **one** request with two drafts shown together.
* `capacity` slot: default **6** by code (`derive:default_capacity`, setting `defaultCapacity`) **whenever sign-up is on and Mike gave no number**, shown as "I set: 6 spots"; a number Mike gives wins, **up to 6 until G approves decision 2-A** (above 6 is refused: "The most I can set is 6."); "no limit" stays possible. This replaces the "no capacity unless he said so" rule for the default only: the model itself may still never write a capacity (E2E-HIKE-1 saw it invent 10 and 1).
* `signup` default: **stays OFF (D8) until G explicitly approves decision 3.** Mike can say "sign-up on" and then the 6-spot default applies and is shown as "I set: sign-up on, 6 spots". After G approves decision 3 the default becomes **on** (a one-line change of `derive:default_signup`, with the D8 tests changed in the same card and not before).
* `bring` default: the house line, shown as "I set: the usual bring list".
* The draft preview of a hike with a limit shows what the page will say **now**: "Page will say: Limited to 6 people · availability unconfirmed; ask at the Shack" until a count is published, never "6 spots left" (section 3.3.1).
* Rule `no-invention` keeps its meaning for everything else. Rule `spots-not-below-guests` already exists for `hike.edit` (capacity never below confirmed guests); it now reads the roster.
* `hike.edit` loses `capacity` (moved to `spots.set`, which also checks the roster); `hike.cancel` keeps its warning "N spots were taken; nobody is told" (count only); `hike.recap` gains one optional line: "N people were signed up. Say 'N came' if you want that in the recap" (never automatic).
* Live class: unchanged (`private-only` while trail facts are in the draft) until decision 6.

### 4.2 New skills (all `approval: owner-yes` in version 1)

| Skill | Mike says (examples; the build card writes 10 each) | Slots | What changes | Preview | Live class |
|---|---|---|---|---|---|
| `spots.set` | "make Saturday's hike 6 spots", "Cass Hill limit 4", "no limit on Saturday" | which hike R; number or no-limit R | hike `capacity` (1 to 6; above 6 refused until decision 2-A; never below the seats taken); then counts | the hike card with the new line, worded as the page will show it now (3.3.1) | `chat-live` (a number) |
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
| above six | "The most I can set is 6." (until decision 2-A) |
| capacity set, count not yet on the site | "Done. The page says: Limited to 6 people, availability unconfirmed. I'll show the spots left once the count is published." |
| not Mike | "I can only share that with Michael." |
| site lag | "The website still shows 3 spots. I'll update it as soon as I can." |
| unknown hike | "Which hike do you mean, Saturday's Cass Hill or Sunday's Point Buchon?" |

### 4.4 Approval, undo, tests

* **Approval.** Version 1: one `yes <code>` for every change, so nothing about approval, ownership or live rules changes. The RSVP draft is short, shows only first names and counts, and has **no wording check** (names are not public claims), and the count that follows publishes without a second approval **once decision 4 is yes**. Capacity, closing and page edits use the normal draft with the picture preview. If Mike finds the extra `yes` slow while a guest is standing in the shop, a later setting can make unambiguous, in-capacity adds and cancels apply at once with the reply "Done. Say undo to take it back." That is a change to a protected rule, so it waits for the trial and for G.
* **Undo.** `undo` drafts the inverse and needs its own `yes`. Residue statements: adding a hike (cancelled page card stays, as today), an RSVP add or remove (the roster row is restored or removed; the public count follows; the guest was never told), a purged name does not come back.
* **Tests.** (1) Roster unit tests: seats, waitlist order, `BEGIN IMMEDIATE` race with 8 threads, purge at day 30, file mode 0600, no names in any log, repr, exception or journal (a scan test over every file the code writes). (2) Skill cases (≥ 10 per skill including refusals and one undo) and plan goldens on the content diff and the roster diff. (3) The counts file: schema check, the stale-capacity rule, the cap and spacing, and a "refuses a name, an email or a phone number" case. (4) `community.js` checks (the repo's `site community` CI part), one concrete case per row of the 3.3.1 table: capacity 6 / count 4 taken → "2 spots left"; capacity 6 / 5 taken → "1 spot left"; **capacity 6 / remaining 0 → "Full" with the waitlist line**; **capacity 6 / taken unknown** (no counts file, unreadable file, hike missing from the file, API `null`) → "Limited to 6 people · availability unconfirmed; ask at the Shack" and the text must **not** contain "spots left" or a bare "6 spots"; **capacity mismatch** (page capacity 6, count made for 8) → the same capacity-only line with 6, no number of spots left; sign-up off → today's line; no limit → no spots line; API-first fallback order; nothing about a person in the page. (4a) The same strings are asserted in the skill previews and the card QA so page, card and preview cannot drift. (4b) Defaults: with decision 3 unanswered a new hike is sign-up OFF (the D8 tests stay unchanged); "sign-up on" gives 6; a request for more than 6 is refused until decision 2-A is recorded; the tests for the changed defaults are added in the card that records G's approval. (5) One chain on a scratch state: add hike → add 2 RSVPs → fill → waitlist → cancel → who → set limit → undo, asserting the public file never contains a name.

---

## 5. Cards, order and the Monday minimum

Full table with owned files and dependencies: `reports/hass/HIKEPAGE-1.md` section 5. In order:

1. **HIKEPAGE-SPOTS-1 (Monday minimum).** The hike card shows the limit as **"Limited to 6 people · availability unconfirmed; ask at the Shack"** (capacity-only, never "spots left") unless a trusted count exists; **"Full" with the waitlist line only when a count says 0 are left**; "N spots left" only from a matching count (API first, then the counts file when it exists); every state of table 3.3.1 has a test. Files: `storefront-mockup/community.js`, `hiking.css` if needed, the `community` QA fixture. Small, Sonnet medium.
2. **HIKES-1 fix round / follow-up**: default capacity 6 **when sign-up is turned on**, bring default, a 6-person maximum until decision 2-A; the sign-up default **stays OFF (D8)** unless and until G approves decision 3 (4.1, `hikes.py`; needs PR 530 merged).
3. **ROSTER-1**: the private roster, purge, privacy tests (`hass/rsvp_roster.py`, `hass/ops/rsvp.py`, editor hook).
4. **RSVP-SKILLS-1**: `rsvp.add`, `rsvp.remove`, `who.coming`, `waitlist`, `spots.set`, `hike.full`, the correspondence-log private-text flag.
5. **COUNTS-1** (needs decision 4; protected publish code): `hike-spots.json` and the `counts` release class.
6. **HIKEPAGE-CARD-1**: one renderer, the rich layout for every real hike, field table, placeholders.
7. **HIKE-ADD-2**: `hike.add` v2 and `route.add` chaining.
8. **TOPO-1**: a data-driven explorer and route builder; **TOPO-2 / TOPO-3**: Cass Hill and Fiscalini route data (blocked on collecting the route data).
9. **RECAP-2** and the retention purge (needs decision 7).
10. **ONLINE-RSVP-1** (only if decision 1 is B): attended, last. Starts only after G accepts the off-box guest-data section 3.6.3 in writing; builds the bridge as in 3.6.1.

**Monday (store test, 2026-11-09), honestly:** the minimum is "add a hike with spots shown". Mike can already say "add a hike Saturday at 9, Cass Hill gate, sign-up on, 6 spots" on the **older plain-words path** (the skills are not in the runtime, `STORE-TEST-1.md`): the hike is saved with `capacity: 6`, but **today's page does not show the number**; on the live static site it says only "To join, ask at the Shack." So the Monday minimum needs **card 1** published, which then shows "Limited to 6 people · availability unconfirmed; ask at the Shack" (a limit, not a count; it never says spots are left), which needs the operator to move the runtime to a main that contains it before the Sunday 21:00 go/no-go (an attended restart). If that is not done, the fallback uses no code: Mike says "…say in the description: limited to six people", his own words, which the page should print (not tried). **Live count updates, the waitlist, who is coming and the full per-hike page are all after Monday.**
