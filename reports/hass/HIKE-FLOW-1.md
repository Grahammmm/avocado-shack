# HASS-HIKE-FLOW-1: a hike request must end in a draft

Card t_9a32fec3 · repo Grahammmm/avocado-shack · branch `rb/hass-hike-flow-1` (main `3c09f2a` merged in) · measured 2026-11-08 PST.

## What was wrong, in plain words

The three live replies were reproduced on a scratch copy (a temp state dir, the real `Conversation`, the real GPU `openai` interpreter; nothing live was touched). Three causes, all in code we own:

1. **The prompt had no "add a hike" rule, and one rule that told the model to refuse.** It said "never make a route idea … into a real hike". `hike.create` has an optional `trailId`; the model treated it as required, listed the three route ideas and asked "which trail?" even though the text already named Mill Creek (text 1), and asked "which hike should I create?" for a complete request (text 3).
2. **Hass kept only its own last question, never the owner's words.** When the owner answered "Fiscalini Ranch", the interpreter saw the question and the two words, but not "Saturday, 8am, easy, bring water" (text 2). The hints (day and time) and the unstated-claim check also ran over the answer alone.
3. **The hints made it worse.** "Fiscalini Ranch" arrived as a *route idea* hint, which the model read as "not a hike".

## What changed

- `hass/interpreter_prompt.py` (3 new rules, placed before the photo rule so the last six rules keep their places; the old refusal sentence is gone): adding a hike (add, create, schedule, put on, make; "new" or not) is always `hike.create`; one named place is the meeting point; a place not on the route-ideas list is plain text; `trailId` is set only when the owner names a listed route idea; `rsvpEnabled` is false unless sign-ups are mentioned; ask one short question, only for a missing day, time or place, never for a name, route, difficulty or things to bring. The `recent` rule now says: read the earlier texts, the question and the answer as one request.
- `hass/conversation.py`: new private table `open_asks` in `conversation.sqlite3` (one row). When the interpreter answers with a question, the owner's texts of that request (max 4, 1000 chars each, 2000 in all) are kept next to it. The next text, if our question is still the newest thing in the chat and is at most 30 minutes old, goes to the interpreter as `recent: {question, earlier: [...]}`; hints and the claim check read the earlier texts plus the answer. The row is deleted when a draft follows, on `no`, when a command comes in between, and on the first message after 30 minutes.
- `hass/interpreter_local.py`: sends `earlier` (max 4 strings, validated) with `recent`; hints read the whole request.
- Not changed: approval (`yes <code>` only), owner check, reply rules, publish rules. An unconfirmed message still writes nothing: every outcome above is a draft or a question, and the answer is interpreted like any other text.

## Regression tests (`hass/tests/test_hike_flow.py`, plus corpus rows tagged `hike-flow`)

The three live texts; edit a hike's time; cancel a hike; an answer after a question (time, place, two questions in a row); TTL expiry; a command or `no` in between; bounds on what is kept; a broken store means no earlier text, not a crash; a claim made in the first text still counts; the prompt rules; the corpus rows. Existing pins updated: prompt snapshot, rule count (26 → 29), the hike.repeat rule text.

## Measured on the GPU backend (`api=openai`, `http://127.0.0.1:8010`, `qwen3.8:27b-thinkingcap-q6`) — scratch state

Seconds are `interpreter_audit.seconds` for that one message; the CPU fallback never fired (`fallback=0` on every row). The first call of each run carries the cold prompt cost (about 12 s once); the rest are 1–5 s. Drafts take longer than questions because the JSON is longer.

| Scenario | Owner text (synthetic) | Result | Interp. s | CPU fallback |
|---|---|---|---|---|
| s1_live1 #1 | add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water | Draft: bring: Water; difficulty: easy; meetingPoint: Mill Creek trailhead; startsAt: Sat 2026-11-14 08:00 PST; title: Mill Creek hike | 12.317 | no |
| s2_live2_alone #1 | Fiscalini Ranch | Question: What day and time for the Fiscalini Ranch hike? | 0.954 | no |
| s3_live3 #1 | create a new hike on Fiscalini Ranch this Saturday at 8am, easy, bring water | Draft: bring: Water; difficulty: easy; meetingPoint: Fiscalini Ranch; startsAt: Sat 2026-11-14 08:00 PST; title: Fiscalini Ranch hike; trailId: idea-fiscalini-bluff | 5.009 | no |
| live_sequence #1 | add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water | Draft: bring: Water; difficulty: easy; meetingPoint: Mill Creek trailhead; startsAt: Sat 2026-11-14 08:00 PST; title: Mill Creek hike | 4.529 | no |
| live_sequence #2 | Fiscalini Ranch | Question: What day and time for the Fiscalini Ranch hike? | 1.04 | no |
| live_sequence #3 | create a new hike on Fiscalini Ranch this Saturday at 8am, easy, bring water | Draft: bring: Water; difficulty: easy; meetingPoint: Fiscalini Ranch; startsAt: Sat 2026-11-14 08:00 PST; title: Fiscalini Ranch hike; trailId: idea-fiscalini-bluff | 5.157 | no |
| answer_time #1 | add a hike Saturday, Mill Creek trailhead, easy, bring water | Question: What time on Saturday for the Mill Creek trailhead hike? | 1.173 | no |
| answer_time #2 | 8am | Draft: bring: Water; difficulty: easy; meetingPoint: Mill Creek trailhead; startsAt: Sat 2026-11-14 08:00 PST; title: Mill Creek trailhead hike | 3.412 | no |
| answer_place #1 | add a hike this Saturday at 8am, easy, bring water | Question: Where should we meet for the Saturday hike? | 1.082 | no |
| answer_place #2 | Mill Creek trailhead | Draft: bring: Water; difficulty: easy; meetingPoint: Mill Creek trailhead; startsAt: Sat 2026-11-14 08:00 PST; title: Mill Creek hike | 3.36 | no |
| answer_vague #1 | put a hike on the site for sometime next weekend, somewhere at the beach | Question: Which day next weekend for the beach hike: Saturday Nov 14 or Sunday Nov 15? | 1.285 | no |
| answer_vague #2 | Saturday | Question: What time on Saturday Nov 14 for the beach hike? | 1.116 | no |
| answer_vague #3 | 9am | Draft: meetingPoint: the beach; startsAt: Sat 2026-11-14 09:00 PST; title: Beach hike | 2.771 | no |
| answer_vague #4 | Morro Rock parking lot, easy, called Morro Rock Beach Stroll | Question: Is this a new hike, or a change to the pending “Beach hike” (f535)? | 1.599 | no |
| edit_time #1 | add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water | Draft: bring: Water; difficulty: easy; meetingPoint: Mill Creek trailhead; startsAt: Sat 2026-11-14 08:00 PST; title: Mill Creek hike | 4.522 | no |
| edit_time #2 | yes 18e2 | yes applied (no interpreter) | - | - |
| edit_time #3 | push the Mill Creek hike to 10am | Draft: events hike-2026-11-14-mill-creek-hike: startsAt Sat 2026-11-14 08:00 PST → Sat 2026-11-14 10:00 PST | 2.586 | no |
| cancel #1 | add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water | Draft: bring: Water; difficulty: easy; meetingPoint: Mill Creek trailhead; startsAt: Sat 2026-11-14 08:00 PST; title: Mill Creek hike | 4.751 | no |
| cancel #2 | yes 18e2 | yes applied (no interpreter) | - | - |
| cancel #3 | cancel the Mill Creek hike, it's going to rain | Draft: events hike-2026-11-14-mill-creek-hike: cancelNote (none) → It's going to rain; events hike-2026-11-14-mill-creek-hike: status scheduled → cancelled | 2.599 | no |
| new_unrelated_after_q #1 | add a hike Saturday, Mill Creek trailhead, easy | Question: What time on Saturday for the Mill Creek trailhead hike? | 1.261 | no |
| new_unrelated_after_q #2 | are the eggs sold out? | Question: Which one do you mean: the Cal Poly eggs or the Greek yogurt? | 1.179 | no |
| expire #1 | add a hike Saturday, Mill Creek trailhead, easy, bring water | Question: What time on Saturday for the Mill Creek trailhead hike? | 1.168 | no |
| expire #3 | 8am | Question: What should I set to 8am: the Monday–Friday hours, the Saturday hours, or a new hike? | 1.356 | no |
| v1 #1 | schedule a hike for next Saturday at 7:30am meet at Cuesta Grade parking lot, moderate | Question: Which Saturday is next: 2026-11-14 or 2026-11-21? | 1.57 | no |
| v2 #1 | new hike: Morro Bay estuary walk, Dec 5, 9am, meet at the Embarcadero, easy, bring binocul | Draft: bring: Binoculars; difficulty: easy; meetingPoint: the Embarcadero; startsAt: Sat 2026-12-05 09:00 PST; title: Morro Bay estuary walk | 4.643 | no |
| v3 #1 | put a hike on Dec 12 at 10am at Cass Hill, bring layers | Draft: bring: Layers; meetingPoint: Cass Hill; startsAt: Sat 2026-12-12 10:00 PST; title: Cass Hill hike; trailId: idea-cass-hill | 4.645 | no |
| v4 #1 | make a hike Saturday 8am at Montana de Oro | Draft: meetingPoint: Montaña de Oro; startsAt: Sat 2026-11-14 08:00 PST; title: Montaña de Oro hike | 2.896 | no |
| v5 #1 | add a hike at Bishop Peak Saturday | Question: What time on Saturday for the Bishop Peak hike? | 0.957 | no |
| v6 #1 | add a hike Saturday 9am | Question: Where should we meet for the Saturday 9am hike? | 1.009 | no |
| v7 #1 | add a hike with sign ups, capacity 12, Saturday 9am, Mill Creek trailhead | Draft: meetingPoint: Mill Creek trailhead; startsAt: Sat 2026-11-14 09:00 PST; title: Mill Creek hike | 4.109 | no |
| v8 #1 | create a hike Point Buchon Saturday 9am | Draft: meetingPoint: Point Buchon; startsAt: Sat 2026-11-14 09:00 PST; title: Point Buchon hike; trailId: idea-point-buchon | 4.268 | no |
| v9 #1 | add a hike | Question: What day, time, and place for the new hike? | 0.951 | no |
| v10 #1 | new hike sat 8am cayucos pier easy | Draft: difficulty: easy; meetingPoint: Cayucos pier; startsAt: Sat 2026-11-14 08:00 PST; title: Cayucos pier hike | 4.29 | no |

32 interpreted messages: min 0.951, median 2.599, p90 4.751, max 12.317; **0 CPU fallbacks**.

## The three live texts, now

| Live text | Before (live) | Now |
|---|---|---|
| 1. `add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water` | "Which trail should the Saturday hike use…" | **Draft**: title Mill Creek hike, Sat 2026-11-14 08:00, meeting point Mill Creek trailhead, easy, bring Water, sign-ups off |
| 2. `Fiscalini Ranch` alone | forgot message 1 | After a *question*, it is joined to the open request (`answer_place`, `answer_time`: **draft**). Sent as the very first message with no open request, it is one short question: "What day and time for the Fiscalini Ranch hike?" |
| 3. `create a new hike on Fiscalini Ranch this Saturday at 8am, easy, bring water` | "Which hike should I create…" | **Draft**: Fiscalini Ranch hike, Sat 08:00, easy, bring Water, linked to the route idea |

Note on live text 2: because text 1 now gives a draft, "Fiscalini Ranch" sent right after it has no open question to answer; the model asks for the day and time (live_sequence#2) rather than editing the waiting draft. That is a safe outcome (a question, nothing written).

## Whole corpus, before/after (357 cases, same GPU backend)

| Measure | base | after |
|---|---|---|
| Cases scored | 348 | 357 |
| Intent accuracy | 87.9% | 89.1% |
| Strict accuracy (right ops, args, words) | 84.2% | 84.9% |
| Wrong-draft rate (unsafe) | 6.6% | 7.8% |
| Drafted where a draft was NOT right | 3.8% | 5.1% |
| Asked a question when it should ask | 89.8% | 88.9% |
| Refused when it should refuse | 90.1% | 91.5% |
| Over-cautious (asked or refused a clear request) | 12.2% | 9.2% |
| JSON valid | 99.7% | 99.7% |
| Calls failed at the end | 1 | 1 |
| First attempts that timed out | 0 | 0 |
| Latency p50 (s) | 1.6 | 1.6 |
| Latency p95 (s) | 4.7 | 3.6 |


Compared 348 shared cases: fixed 7 (n097, n224, n255, n265, n267, n307, n311); regressed 4 (n078: drafted where question was right, n141: drafted where question was right, n312: question where a draft was right, n335: ops product.set_availability but expected product.restore); new wrong drafts 6 (n078, n099, n100, n141, n148, n335). These are case ids in `hass/tests/fixtures/nl-corpus.jsonl`; every one of them is still only a draft that needs `yes`.

The base run is the same corpus (348 rows) on main `663144c`; the after run also has the 9 new hike-flow rows.

## Not fixed / follow-up cards to write

1. **Prompt change moved some non-hike cases** (see the compare list above). The drafts all still need `yes`, but the wrong-draft rate should be re-checked by a person; maybe cut the new hike rules' wording or add the failing non-hike cases to the corpus as pins.
2. **Deterministic guard**: drop `rsvpEnabled` and `capacity` when the owner text has no sign-up words (E2E-HIKE-1 item 1). The prompt now says it; code would enforce it.
3. **`difficulty` normalisation** (easy/moderate/hard) is prompt-only.
4. **Answer sent after the draft** (live text 2 right after text 1) could be read as an edit of the waiting draft's meeting point; today it asks. A product decision.
5. **Photo + hike text** still refuses (E2E-HIKE-1 4a/4b); unchanged.

## Verification

- Full hass suite via `python3 hass/tests/run_parallel.py --jobs 6`: OK, 900 tests, 16 skipped, 4 shards, exit 0 (also green in CI on head 5ba486e: check, quick, hass shards 0-3, site static, site community).
- Review: author is Sonnet-class, so Opus 5.5 (`opus-coder`) reviews; merge is covered by G's standing approval once required CI is green on the exact head and the review approves.
