# Hike lookup: name a hike, Hass finds it, proposes it, then builds the page (HASS-HIKE-LOOKUP-1)

Design plus an **offline, fixture-tested prototype**. Written 2026-11-09. **HIKE-LOOKUP-2 (card A6) has wired it into the hike chat: see section 7**; that part is off unless the operator sets `hikeLookup.contact`. Nothing here touches the live site, the running Hass runtime, `host.json`, approvals or any send. The only new files are `hass/hike_lookup.py`, its test and recorded fixtures, one manual script and this page. `hass/publish_live.py`, the receiver, the worker, the host and `hass/conversation.py` are unchanged.

**Assumption stated first.** G wrote "OS data". Ordnance Survey covers Great Britain only and the shop is in San Luis Obispo, California, so this design uses **OpenStreetMap** (names, route lines; Overpass and Nominatim) and **USGS 3DEP** (elevation; the ImageServer `getSamples` call, point queries as the fallback). If G meant something else, only `hass/hike_lookup.py`'s transport and the manual script change; the rest stands.

Labels: **RECORDED** = a real answer from the service on 2026-11-09, saved as a test fixture. **READ** = read in this repo. **DESIGN** = a choice made here, not yet wired into the running Hass.

## The six answers, one line each

1. **Matching.** The typed or spoken name is folded (accents, `Mt` to mount, filler words dropped, at most 6 words, no word with a digit, no address or link), searched loosely in the San Luis Obispo County box first and then over California; matches are judged by name similarity (at least 0.75). Several matches: at most three are offered and Mike picks. None: Hass says so plainly and never invents.
2. **The proposal.** `Did you mean "<name>" near <place>, about <x.x> miles <a loop | out and back | one way> on the map, with about <n> feet of climbing? Reply yes to use it, or no and tell me more.` Miles come from the haversine sum of the route line. When the line cannot be chained with confidence, Hass says "I'm not sure" and gives no number.
3. **Hass rules.** A looked-up route is a ROUTE IDEA (`route.add`, undated, sign-up off) until Mike gives an exact date, time and meeting place; it never becomes an event by itself. Every number is from the stored source record, with source name and retrieval date. Text is plain (no markup, no invisible characters). Publishing is the normal change request with the usual `yes <code>`. Nothing is mailed.
4. **The flow.** No second system: the lookup fills the `route` slot of the existing `hike.add` skill and plans the existing `route.add` and `hike.create` ops through `hass.editor.prepare`, the claims gate and `editor.apply`. Section 4 names every function.
5. **Failures.** Network down, slow, "try later", over our own limit, unreadable answer, stale copy and a closure note each get a plain-words reply (section 5) and change nothing.
6. **Safety and cost.** Only the hike name (as a search pattern) and public trail coordinates leave the box; at most 8 requests per lookup and 60 per day, spaced 0.5 to 2 seconds; saved answers live 30 days (names and lines), 90 (place), 365 (elevation); the log holds request keys and outcomes, never text.

## 1. Matching: how a name becomes candidates

**Chosen answer.**

0. **Hass's own route ideas first.** `hike_lookup.known_route_idea(name, route_ideas)` scores the name against the route ideas already on the page (`status` idea, not hidden). A fit (score at least 0.75, no tie) is used as it is and **nothing goes out**. Point Buchon, Cass Hill and Fiscalini Ranch are already reviewed route ideas, so naming one of them never triggers a lookup (and never replaces reviewed numbers with map numbers).
1. **Words.** `name_tokens`: accents and punctuation folded, `Mt`/`Pt`/`Rd` spelled out, `the`, `trail`, `hike`, `walk`, `trailhead` dropped, at most 6 words, any word with a digit dropped (phone numbers, zip codes), e-mail addresses and links removed.
2. **County first.** One Overpass request over the San Luis Obispo County box (34.90, -121.45, 35.80, -119.40) for: hiking route relations, ways that are paths, footways, tracks, bridleways or steps (never streets), and named peaks. The pattern is the first four letters of each long word in order (`bish.*peak`), so a typo past the fourth letter still finds it.
3. **Judge the names.** `name_score` (difflib ratio, with all-words-present counted as 0.9 when the extra words are trail words like "Fire Road" and 0.78 otherwise); under 0.75 is not a match.
4. **Wider California only if the county has no trail by that name.** One Nominatim search (California box, `bounded`, US only); only hits that are paths, tracks or hiking routes count (a street called "Mission Peak" is ignored). Their geometry is fetched by id. A hit that is only a peak or park is reported as "a place, no trail", never as a hike.
5. **Group.** Pieces that share a point, pieces of one relation, and same-name pieces whose nearest ends are within 200 m become one trail; everything else is a separate trail.
6. **Rank.** A trail whose distance is known comes before one that is not; then the closest name; then the nearest to the shop.

**Several matches.** At most **three** are offered, numbered, each with its place (reverse geocode of the trail's centre), and Mike picks by number. More than three: "There are more than 3 that fit; tell me more of the name if none is right." **None:** "I couldn't find a trail called X on the map. I won't guess. Could you say it another way, or tell me the park or trailhead it is near?" Nothing is drafted. **RECORDED**: `Bluff Trail` returns three trails (Cambria, Pismo Beach, Montaña de Oro), `Mount Doom Trail` returns none, `Mission Peak` (outside the county) is a peak with no mapped trail.

## 2. The proposal sentence, distance, shape and "I am not sure"

**Exact wording** (`hike_lookup.proposal`, passes `hass/voice.py` for every fixture):

> Did you mean "Bishop Peak Trail" in San Luis Obispo County, about 2.4 miles out and back on the map, with about 740 feet of climbing? Reply yes to use it, or no and tell me more.

Place reads "near Cambria" for a town and "in San Luis Obispo County" when the map only knows the county. A point-to-point trail adds "from the lower end" after the climb. Outside the county it starts "I didn't find that near San Luis Obispo."

**Distance.** Never from a tag or a guess: the haversine sum over the route line's points (R = 6,371,000 m, as the existing Point Buchon map data), shown in miles rounded to 0.1. Out and back is the round trip; a loop is the loop; point to point is one way (and says "one way"). The record keeps the metres.

**Chaining several pieces.** The pieces of a group are put in a graph by their points. Then:

| Graph | Result |
|---|---|
| a ring | **loop**, length of the ring |
| a single line, leaf to leaf | **open line**, length of the line |
| a line with small side spurs (total at most 12 % of the line) | the longest leaf-to-leaf line; spur metres kept in the record |
| same-name pieces joined across a gap of at most 200 m | joined by a straight bridge; bridges must total at most 8 % of the route, and the bridge metres are kept |
| anything else | **not sure** |

**Loop, out and back or one way.** A closed ring is a loop. An open line is **out and back** only with evidence: a named peak within 150 m of one end, or a destination word in the name (peak, summit, point, hill, mountain, mount, cerro, rock, falls, lookout, overlook, dome, knob, butte). Otherwise it is **one way**: OpenStreetMap geometry cannot tell out and back from point to point, so Hass says what the line is rather than assume a return.

**Elevation gain.** The route is sampled about every 50 m (never more than 120 samples, so one request), a 3-point median filter removes spikes, and the climb is the sum of rises, rounded to the nearest 10 ft. Out and back counts the climbing on both legs; one way is counted from the lower end; a loop as sampled. Same method as the existing Point Buchon profile (`reports/hiking-club/build-trail-data.py`).

**Hass says "I'm not sure" (no distance, no shape, no climb) when** the pieces do not join up (gaps over the limit), the trail branches in several places, it is a loop with extra trail attached, it has several loops, the map only has a very short piece (under 0.3 mile), or there is no usable line. The reply names the reason and asks Mike for the distance or a trail-guide link; the route idea path for that (Mike's own words and a source link, `route.add` as today) is unchanged. **RECORDED**: Point Buchon (a loop with a tail), Valencia Peak (branches) and the 19-piece Montaña de Oro "Bluff Trail" network are all "not sure".

## 3. Hass rules it respects

* **Route idea versus real event.** `plan_ops(candidate)` returns exactly one op, `route.add` (undated, `status` idea, `rsvpEnabled` false: the editor forces both). A hike is planned only when Mike's own confirmed `date`, `time` and `meetingPoint` are all present; anything missing raises, so a looked-up route never becomes an event silently. The time zone is the shop's `America/Los_Angeles`, fixed by the existing `hike.create` op, not asked or guessed. Sign-up stays off unless Mike says otherwise (D8). Tested through the real editor (`WithTheEditor`).
* **Claims policy.** Every number on the page comes from the stored source record: `route_add_args` writes only measured miles and feet; difficulty, time, terrain and the tagline say "To be confirmed" (the page's existing wording for a missing fact) and the description is `About 2.4 miles, out and back. Michael will share the details soon.` The route idea's `sourceName` is `OpenStreetMap contributors and USGS 3DEP, retrieved Nov 9, 2026` and `sourceUrl` is the OpenStreetMap way or relation page, so source and retrieval date travel with the record (the route-idea schema is closed, so the date rides in `sourceName`). The full record (query, OpenStreetMap ids, metres, bridge and spur metres, shape basis, sample count, sources, retrieval date, version) is `Candidate.record`, kept in the private lookup folder next to the saved answers. Names the map supplies still pass `claims.unstated`: a map name containing "Organic" is asked about, not published (tested).
* **Public-safe text.** Every map string goes through `clean_public`: tags removed, `<`, `>`, `$`, `{{`, `}}` removed, control and zero-width characters removed (same list as `content_model.INVISIBLE_RE`), one line, at most 120 characters. The route-idea arguments are then checked with the existing `content_model._text` and `_route_add`.
* **Publishing.** Nothing publishes. After Mike's identity "yes" Hass drafts the route idea (and hike), shows the usual draft with its code, and applies only on `yes <code>`. Live release of `route.*` stays what `hass/live_policy.py` says today (`PRIVATE["route.add"] = "is trail details"`): a human releases it. Making a looked-up route chat-live is HIKE-PAGE.md decision 6, still G's.
* **No mailing.** The lookup has no sender, no address and no outbox.

## 4. The flow in Hass commands (no second system)

Existing path, **READ**: owner text, `Conversation.handle` (`hass/conversation.py`), interpreter and skill dispatch (`hass.skills.dispatch.Dispatcher`, skill `hike.add` in `hass/skills/hikes.py`, `plan_add`), `Conversation._draft`, `editor.prepare(ops)` (`hass/editor.py`), `claims.unstated` (`hass/claims.py`), `live_policy.check`, the proposal with `yes <code>`, then `editor.apply(change_id, draft_hash)`, which regenerates the pages with `hass.sitegen`. The task text says `hike.draft`; the code has no function of that name: this path **is** the hike draft path, and the ops are `route.add` (`hass.ops.routes._route_add`) and `hike.create` (`hass.ops.hikes._hike_create`).

DESIGN, one step added at the `route` slot:

| Step | What happens | Existing function it uses |
|---|---|---|
| 1 | Mike: "add a hike on Bishop Peak Saturday at 9, Highland trailhead" (or just "find Bishop Peak"). | `Conversation.handle`, interpreter, `Dispatcher` fills the `hike.add` slots |
| 2 | The `route` slot does not resolve to a listed route idea (`hass.skills.kinds.route_ref` says none). New: the dispatcher calls `hike_lookup.lookup(name, transport, route_ideas=content.community["routeIdeas"])`. A listed idea ends here with its id as `trailId`. | `kinds.route_ref`, then **new** `hike_lookup.lookup` |
| 3 | Hass replies with the proposal or the pick-one list; the candidate(s) are kept privately as the open request (30 minutes, like any open question). Nothing is drafted yet. | the open-request store `hass/skills/openreq.py` (`Conversation._open_ask`, `_recent_question`) |
| 4 | Mike: "yes" (or "2"). This is the identity answer; it is not an approval. | `Conversation.handle` |
| 5 | Day, time and meeting place already given: `plan_ops(candidate, hike)` returns `route.add` + `hike.create` (with `trailId` = the new idea's id, predicted by `route_id`, which has the same slug rule as `_route_add`). Not yet given: Hass asks the one existing question ("What time on Saturday?"), or plans `route.add` alone (a route idea). | `Dispatcher` / `hikes.plan_add` question flow |
| 6 | The ops go through `editor.prepare`; `claims.unstated` runs on the draft; `live_policy.check` marks it private. Hass shows the draft: "Reply yes a1b2 to save it, or no to cancel." | `editor.prepare`, `claims.unstated`, `live_policy.check` |
| 7 | `yes a1b2`: `editor.apply`. The hike page is built in the private preview. Going live is the normal release. | `editor.apply`, `sitegen` |

Mike therefore says a hike's name once and answers "yes" twice (is it the right hike; save it). The second yes is the usual approval code and cannot be skipped. If a draft is already waiting, Hass does not start a lookup ("I still have a change waiting for your yes.") so a bare "yes" is never ambiguous.

**Sample exchange** (Bishop Peak, replayed from the recorded answers; every reply passes the voice rules):

> **Mike:** Add a hike on Bishop Peak this Saturday at 9, meet at the Highland trailhead
> **Hass:** Did you mean "Bishop Peak Trail" in San Luis Obispo County, about 2.4 miles out and back on the map, with about 740 feet of climbing? Reply yes to use it, or no and tell me more.
> **Mike:** yes
> **Hass:** (the usual draft: the new route idea and the hike on Saturday at 9 am, Highland trailhead, sign-up off, with "Reply yes a1b2 to save it, or no to cancel.")

Several matches:

> **Mike:** add Bluff Trail
> **Hass:** I found 3 that fit. Which one do you mean? 1. Bluff trail near Cambria, about 0.9 miles one way on the map, with about 50 feet of climbing from the lower end 2. Shell Beach Bluff Trail near Pismo Beach, about 0.7 miles one way on the map, with about 130 feet of climbing from the lower end 3. Bluff Trail in San Luis Obispo County, and I'm not sure of its distance. Reply 1, 2 or 3, or no if it isn't one of these.

Not sure, and none:

> **Hass:** I found Point Buchon Trail in San Luis Obispo County, but the trail has a loop with extra trail attached, so I'm not sure how far it is or what shape it is. I won't guess. Do you know the distance, or have a link to a trail guide?
> **Hass:** I couldn't find a trail called Mount Doom Trail on the map. I won't guess. Could you say it another way, or tell me the park or trailhead it is near?

(Point Buchon is already a route idea, so in the running Hass step 0 answers it without a lookup; the recorded case shows what the map alone gives.)

## 5. Failure behaviour (plain words, nothing changed)

| Situation | Reply |
|---|---|
| Network down | "I can't reach the map right now, so I couldn't look that hike up. Nothing was changed. Try again in a little while, or tell me the distance yourself." |
| Service slow (no answer in 60 s; the public Overpass server took 36 to 40 s on a county search while recording, and answered 502 several times) | "The map is slow to answer right now, so I stopped waiting. Nothing was changed. Try again in a few minutes." Hass does not retry by itself. |
| Service says try later (429, 503, 504) | "The map asked me to wait a bit before asking again. Nothing was changed. Try again in a few minutes." |
| Our own limit reached | "I've looked up a lot of trails today, so I'm stopping for now. Nothing was changed. Try again tomorrow, or tell me the distance yourself." |
| Unreadable answer | "The map gave me an answer I can't read, so I couldn't look that hike up. Nothing was changed. Try again later, or tell me the distance yourself." An answer is unreadable when it is not the structure the service sends (for example Overpass `elements` that is not a list, an element or point that is not an object or number, a Nominatim hit with the wrong field types): it never crashes the skill. |
| Saved copy older than its lifetime and the refresh failed | The answer is still given, with: "This is from a saved copy from Sep 1, and I couldn't check it again today." The record is marked stale and dated by the OLDEST answer used, including the map lines (so the route idea's source name never carries a fresh date for a saved copy). With several matches the sentence is said once, naming the trails it applies to. |
| Elevation unavailable | The distance stands; the sentence says "with no climbing figure I trust" and the route idea says "To be confirmed" for elevation. |
| A closure or warning in the source tags (`access` no/private/closed, construction, disused, or a `note`, `description` or `fixme` mentioning closed, closure, washout, damage, detour, reroute, unsafe, impassable, landslide, storm) | "The map notes say <the note, cleaned>. Please check with the park before we plan anything." The numbers stay; the warning travels with them. It is said on every reply path: a proposal, a not-sure answer (even with no distance) and a several-matches offer (written "For 2, the map notes say ..." next to the trail's number). |

The absence of a closure note is never said to mean the trail is open. All of these are tested (`Failures`, `PoliteClient`).

## 6. Safety and cost

* **What goes out.** Only (a) the Overpass query built from the hike name, (b) the same name for Nominatim, (c) public coordinates of the trail for the place and the elevation. No owner message, date, time, meeting place, chat id, phone, address or e-mail. `name_tokens` is the only door: it drops digits, addresses, links and everything past six words (tested with a phone number and an e-mail typed into the name). The module has no network code at all (tested): it only calls a `transport` it is given.
* **Client.** Plain HTTPS, standard library only, **no third-party client library** (none was installed or needed, so there is no source to inspect), no account, key or credential. The User-Agent names the app and a **contact address the operator chooses** (the manual script refuses to run without `--contact`; none is built in).
* **Limits.** `CachedTransport`: at most **8 requests per lookup** and **60 per day** (the day count is kept on disk since HIKE-LOOKUP-2); at least 2.0 s between Overpass requests, 1.1 s between Nominatim requests (the public Nominatim policy is one a second), 0.5 s for USGS; a lookup normally makes 3 to 6 requests (county search, then up to three place lookups and three elevation requests for the trails offered).
* **Cache lifetime.** Names and lines 30 days, place 90, elevation 365 (terrain does not change). A saved answer inside its lifetime means no request. Past it, one refresh; if that fails the old copy is used and marked stale. Folder mode 0700 in the state directory (DESIGN: `<state>/hike_lookup/`).
* **Logged.** One row per request: time, service, request key (a hash), outcome (`saved`, `fetched`, `busy`, `slow`, `network`, `budget`) and seconds. No query text, no coordinates, no reply text. The identity question's private row follows the existing open-request rules (kept on the box, 30 minutes).
* **Licences.** OpenStreetMap data is ODbL: the route idea's source line and the page's map credit say "OpenStreetMap contributors". USGS 3DEP is a US government work.

## 7. HIKE-LOOKUP-2: wired into the hike chat (card A6)

Built after the prototype above. **OFF unless the operator sets `hikeLookup.contact`.** With no setting, nothing in this section runs and
the hike flow is exactly what it was. This card edits `hass/conversation.py` (the lines below), so it is scheduled by the operator and
does not land during a live trial week.

**What Mike sees.** He names a hike and does not say where to meet or how far it is ("add a hike on Bishop Peak Saturday at 9am"). Where
Hass would ask "Where do people meet?", it asks the map's question instead, with at most three trails and measured numbers only:

> Did you mean "Bishop Peak Trail" in San Luis Obispo County, about 2.4 miles out and back on the map, with about 740 feet of climbing? Reply yes to use it, or no and tell me more.

With several trails: the numbered list of section 1 ("Reply 1, 2 or 3, or no if it isn't one of these"). A trail the map is "not sure" of is
listed with no number and cannot be picked into a route idea. After **yes** (or the number) Hass asks the usual "Where do people meet?";
after **no** (or anything that is not a clear yes or number) it asks the same and never looks again in that request. When Mike has given the
meeting place, a distance or a listed route idea himself, or Hass already has a route idea of that name, or the title is only a day or a
time of day ("Saturday morning hike"), or a draft is already waiting for his yes, or one message holds several asks, nothing is looked up.
A lookup that finds nothing, is "not sure", fails (network, slow, busy, unreadable, over our limit) or breaks for any other reason says
nothing about the map: the plain question is asked and the hike goes ahead without a route idea. (The failure sentences of section 5 are
kept for the manual script and for a later card that wants to say them in chat.)

**The draft.** With the place and the other details given, the draft is `route.add` (the map trail, measured miles and feet, source
name and retrieval date, `To be confirmed` for everything else) followed by `hike.create` linked to it by `trailId`, shown as one change
with the line "I'll also add a route idea for ... Source: OpenStreetMap contributors and USGS 3DEP, retrieved <date>." and, when the map
had one, its park-check or saved-copy sentence as a warning. It needs the usual `yes <code>`. A route idea Hass already has with the same
name is linked instead of added again. Nothing is published; `route.add` stays private-only (`live_policy`).

**Where the pieces are.**

| Piece | File | What |
|---|---|---|
| the setting | `hass/conversation.py` `load_settings` | `hikeLookup` `{"contact": <an e-mail address or an https link>}` (or the flat key `hikeLookup.contact`) becomes `hikeLookupContact`; anything else raises `ConfigError`; absent = off. No address is built in |
| the context | `hass/skills/dispatch.py` `Ctx.hike_lookup`, `Dispatcher._ctx` | `{"contact", "folder": <state>/hike_lookup, "waiting": <a draft waits for his yes>}` or `None` |
| the question | `hass/skills/hikes.py` `question` | the proposal, in place of the meeting-place question; keeps the offer privately (below) |
| the answer | `hass/skills/hikes.py` `answer` + `Dispatcher.takes_answer` / `cheap` + `Conversation._handle` | a bare yes, no or number to the offer is read by code (no model call) and is **not** an approval or a cancel; `yes <code>`, `no <code>`, `approve`, `cancel` and `reject` keep their meaning |
| the draft | `hass/skills/hikes.py` `plan_add`, `notes` | `route.add` + `hike.create`, and the line beside the draft |
| the live client | `hass/hike_fetch.py` | the standard-library fetch behind `CachedTransport`; the only module with network code. Also used by the manual script |
| the limits | `hass/hike_lookup.py` `CachedTransport` | spacing per server (shared across lookups), 8 requests per lookup, **60 per day kept on disk and reserved under a lock** (`day-count.json`, `day-count.lock`), and 90 seconds for one lookup in all (a request that starts inside the 90 seconds is given only the time left as its timeout, never a fresh 60) |

**The offer is kept without a new slot and without changing the open request.** The offered trails are saved as JSON in
`<state>/hike_lookup/offers/<sha256 of the owner's texts so far>.json` (mode 0700; the owner's words are only in the hash). The answer is
read from the next text of the same request (`hikes._state`), so the plan and the note beside the draft find the confirmed trail again by
the same hash. An offer is used for 2 hours (the open request's own limit); the next offer written after 24 hours erases it. A damaged or edited
file is ignored. The sentence that asks is asked once; a bare yes to several trails is asked one more time.

**Limits that are now on disk.** `<state>/hike_lookup/saved/` holds the saved answers (30, 90 and 365 days as in section 6) and
`day-count.json`: requests made per day, written before each request, last 7 days kept. A restart of Hass cannot reset it. A count file that
cannot be read or written fails closed: the day is counted as used up (no request), the damaged file is kept as `day-count.bad`, and
tomorrow starts clean. **One step, one lock:** checking the limit, adding one and writing the file happen together under an exclusive
`flock` on `day-count.lock` in the same folder, and the request is made only after that reservation succeeded; so Hass, a second chat turn
and the manual script can never both take the 60th request or overwrite each other's count. A lock held for more than 5 seconds, or a
system without `fcntl`, means no request (fails closed). Each writer uses a temp file of its own name (pid, thread, time), never a shared one.

**Spacing is shared across lookups.** Every chat lookup makes a new `CachedTransport`, so the chat gives all of them the one
`hike_lookup.shared_limiter()` of the process: the 2.0 s / 1.1 s / 0.5 s gaps hold from one lookup to the next, requests to one server are made
one at a time, and `nominatim_search` and `nominatim_reverse` are one server (`SERVICE_HOST`) with one 1.1 s gap. The default limiter of a bare
`CachedTransport` is private to it (the tests and the manual script).
 `requests.log` holds one row per request (time, service, hash, outcome, seconds) and stops growing at 1 MB.

**Operator steps** (nothing here was run against the real services by the card; CI and the tests use the recorded answers only):

1. Pick the contact address for the User-Agent. It is sent to OpenStreetMap, Nominatim and USGS with every request.
2. Once, by hand, check the real services still answer as recorded:
   `python3 scripts/hike_lookup_manual.py --contact <address> --cache <state>/hike_lookup/saved "Bishop Peak"` (it shares the day count with Hass).
3. Add `"hikeLookup": {"contact": "<address>"}` to `settings` in Hass's `config.json` and restart Hass (a restart is the operator's, not this card's).
4. **Rollback:** remove the setting and restart (the feature is off; saved answers and offers stay on disk and are never read). Or revert the PR.

**Known limits of this card.**

* Mike's yes is read from his own words by code, so only a plain yes, no or a number (one to three, or first/second/third) counts. Anything longer
  is a no, and the plain flow runs. A yes together with the meeting place in one message ("yes, Highland trailhead") is therefore a no.
* The editor's draft lists the route's `elevation` and `elevationLabel` under the same words (`hass/voice.py` line 299 words both as
  "the elevation"), so the draft shows "the elevation: Elevation gain" and not the climb. The measured climb is in the line beside the draft.
  (A change to that wording, not made here: it is not this card's file.)
* Spacing is kept inside one process. The manual script is a second process: it shares the day count (locked) but not the spacing, so do not run it
  while Hass is making a lookup (it is run once, by the operator).
* The map names in the question are the map's, shown in the usual Mike's-words marks. A saved offer holds them as plain text in the private state folder.
* HIKE-LOOKUP-3 (connectors, official-length cross-check, lollipops) is still open; a "not sure" trail still gets no number.

## Known limits (found while recording the fixtures)

* **A named line can be only part of the hike.** Bishop Peak's one named way is 1.2 miles one way and starts part-way up; popular guides give a longer round trip. The sentence says "on the map", the route idea says nothing else is known ("To be confirmed"), and live release is a human step, but the number should be checked against an official guide before the page goes live. Fix for the build card: also follow unnamed connectors to the nearest road or trailhead node, and compare with a `distance` tag or the source's stated length (a difference over 25 % becomes "not sure").
* **Lollipops** (a loop with a stem, like Point Buchon) and **networks** are "not sure" in this version, on purpose.
* **Open lines with no summit evidence** are described as one way; a trail walked out and back with no named destination is under-counted by half until Mike says so.
* **Wider California** works only for trails whose name matches closely; the public Overpass server often refuses large California queries (502 recorded), which shows as the network or slow reply.
* **Altitude noise.** DEM samples every 50 m overstate climbing a little on rough ground; the figure is "about", rounded to 10 ft.

## What is in this change, and how to run it

| File | What |
|---|---|
| `hass/hike_lookup.py` | the module: matching, chaining, distance, climb, proposal wording, `plan_ops`, `CachedTransport`, `FixtureTransport` |
| `hass/tests/test_hike_lookup.py` | 57 tests, no network (sockets are blocked during every test) |
| `hass/hike_fetch.py`, `hass/tests/test_hike_lookup_chat.py` | HIKE-LOOKUP-2: the live client (the only network code) and the hermetic tests of the chat flow, the on-disk count and the client with a fake `urlopen` |
| `hass/tests/fixtures/hike_lookup/*.json` | recorded answers, 2026-11-09: Bishop Peak, Cerro San Luis, Point Buchon, Valencia Peak, Bluff Trail (three matches), Mission Peak (outside the county), Mount Doom Trail (no match). Trimmed to the tags and geometry the code reads |
| `scripts/hike_lookup_manual.py` | **MANUAL, MAKES LIVE CALLS.** Looks a name up for real, or records a fixture with `--record`. Refuses to run when `CI` is set; the tests check that |

```
python3 -m unittest hass.tests.test_hike_lookup -v
python3 scripts/hike_lookup_manual.py --contact <an address> "Bishop Peak"                       # live, by hand only
python3 scripts/hike_lookup_manual.py --contact <an address> --record hass/tests/fixtures/hike_lookup/bishop_peak.json "Bishop Peak"
```

## Next cards (not built here)

1. **HIKE-LOOKUP-2: done (card A6), section 7.** Wired into the `hike.add` meeting-place question; the live transport and the private `hike_lookup/` folder in the state directory; the "draft already waiting" guard. Touches `hass/conversation.py` and `hass/skills/`, so the operator schedules it outside a live trial week.
2. **HIKE-LOOKUP-3:** the known limits above (connectors to the road, official-length cross-check, lollipops).
3. **Operator:** choose the contact address for the User-Agent (`hikeLookup.contact`, section 7); decide whether `route.add` from a lookup may ever be chat-live (HIKE-PAGE.md decision 6, G's).

No new G decision is needed for this design. Nothing was published, sent or deployed.
