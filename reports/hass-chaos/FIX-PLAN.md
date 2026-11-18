# HASS-CHAOS-1 fix plan (ordered, card-ready)

Source: [CHAOS-REPORT.md](CHAOS-REPORT.md). Each item is one card, at most 3 h. Builder for code: **sol-escalation**. Each item gets ONE verify child: **sonnet-coder-gopus**.
Acceptance for every item: (a) the named chaos cases pass. Remove their `known` entries in `hass/tests/chaos/cases.json`; the runner prints `fixed:` for them. Re-record with `--record` on the private host only when the model call sequence changes. (b) `python3 -B -m unittest hass.tests.test_chaos_suite` stays green. (c) `python3 -B hass/acceptance.py` gives fail 0. One PR per card, `git commit -s`.
Waves are file-disjoint: cards in one wave can run in parallel; a later wave starts after the earlier wave merges.

## Wave 0: covered by HASS-LIVE-FIX-2 (t_4fbdc5f2, running now). Do not duplicate.
- **COVERED-1** "this is from miners" source edit plus no paste of instructions. HASS-LIVE-FIX-2 item 1. Add chaos case `edit-source-miners` (check `t2.no_echo` plus lacks) to its acceptance. The general paste rule is **F1 below** and goes beyond that one message.
- **COVERED-2** placeholder "Not read yet" reply before the photo listing (two replies). Item 2.
- **COVERED-3** store-style picture (gpt-image-2) instead of the raw photo. Item 3.
- **COVERED-4** 118 s photo reply measurement plus INSTALL note. Item 4. The measurements below feed it.

## Wave 1 (start after HASS-LIVE-FIX-2 merges; F1 touches the same edit path)
### HASS-FIX-F1: never paste owner chatter into the public listing (S1)
- Goal: while a listing waits, a message that is not a recognised field edit never changes the description. Examples: "no wait", "what time do we close sunday", "looks good yes please!", "yes 0846x", an instruction sentence. Instead: a near-yes ("looks good", "yes please") gets "Reply yes <code> to publish"; "no wait" / "undo" gets "Nothing is published. Keep it, change something, or say no <code>"; a question gets a short answer or the interpreter, with the draft left unchanged; a mistyped code gets the no-target reply naming the waiting code. Only an explicit description edit ("add: …", "description: …", "say it's …") appends text.
- Owned files: `hass/skills/intake_simple.py` (edit), `hass/skills/dispatch.py` (`_simple_answer` only), `hass/skills/item_intake.py` (`takes_answer` keyword gate only), tests `hass/tests/test_intake_simple*.py`.
- Acceptance cases: `edit-no-wait`, `edit-unrelated-question-mid-draft` (t2), `approve-yes-please`, `approve-typo-code`, `edit-source-miners`, plus F17: while asked for a name, "yes zzzz" must not become the name (add a case).

### HASS-FIX-F2: read the product name from a text that also has the price (S2)
- Goal: "add persimmins fuyu $3.50 a lb", "ADD BLOOD ORANGES $2.50 LB", voice run-ons and "add organic local strawberries best ever $6 a basket" each give ONE listing with the name, price and unit. Remove only the money/stock span from the clause, never the whole clause. Fix typos only by the owner's later edit; never invent a name.
- Owned files: `hass/skills/item_intake.py` (`caption_answers`), `hass/conversation.py` (`_read_intake` only), tests `hass/tests/test_item_intake*.py`.
- Acceptance cases: `intake-typo-persimmins`, `intake-price-letter-o`, `intake-extra-units`, `intake-all-caps`, `intake-voice-runon`, `intake-claims-food` (public text keeps no unproven "organic/best ever"), `price-huge`.
- Speed part (F14): call the answer reader only when the deterministic parse found no price/cost/qty. Expected saving: 1 to 21 s of Qwen per priced text.

## Wave 2 (after Wave 1)
### HASS-FIX-F3: one listing for text-only intake; no interview, no "website doesn't show prices" (S2)
- Goal: a new product sent as text (with or without commas, price in words, two products) gives one priced listing with default description and a generated picture. If there are two products: "One at a time: I'll start with <first>." Remove the catalog-only, no-prices refusal from the old-style interpreter prompt where item intake is on.
- Owned files: `hass/interpreter_prompt.py`, `hass/skills/router.py`, `hass/skills/item_add.py` (several_products wording only), tests.
- Acceptance cases: `intake-price-in-words`, `intake-two-products`, `intake-no-units`, `intake-long-ramble`, `price-negative-zero` (one price question, no listing at -$2), plus the 28 text-opener recordings re-recorded with the original "add fuyu persimmons $3.50/lb" opener (re-record needs the private host: ≤ 40 Codex calls).

### HASS-FIX-F4F5: plain-words price edits and price answers (S2)
- Goal: "make it $4", "actually make it 4 bucks", "wait $4.50", "no $3", "ok make it $4" set the price on the same code (the last one wins). A price answered after Hass's own "What price should it sell for?" (e.g. "$3.50 a pound") is taken. "from Etto" sets the source line (shared helper with COVERED-1). "That's already how it is" is only said when nothing would change.
- Owned files: `hass/skills/intake_simple.py` is owned by F1, so **this card waits for F1's merge** and then owns `intake_simple.py` (price/source edit grammar) and `hass/field_words.py`.
- Acceptance cases: `edit-price-plain`, `edit-contradiction`, `edit-unrelated-question-mid-draft` (t3), `intake-photo-then-two-messages-fast`, `approve-old-draft-after-edit` (publishes $4 after the edit).

### HASS-FIX-F9: label-path public text quality (S2)
- Goal: a non-food item keeps its kind in the name ("Lavender Honey Soy Candle"); no sentence with a dropped word ("is an with", "net weight of."); title-case label names; single spaces; a stable brand when the label shows one.
- Owned files: `hass/label_reader.py` (normalisation only), `hass/skills/intake_simple.py` is NOT touched (description assembly lives in `hass/itemstd.py`), tests.
- Acceptance cases: `intake-nonfood-foodwords`, `intake-photo-jam-organic-label`.

## Wave 3 (independent files; any order)
### HASS-FIX-F6: second product while one waits; price edits after publishing (S2)
- Goal: a new product photo or text while a draft waits starts a second draft with its own code (both listed by `status`). After a publish, "make the glue $4" drafts a `product.edit` of the published product, not a new nameless listing.
- Owned files: `hass/skills/dispatch.py` (request routing outside `_simple_answer`), `hass/skills/openreq.py`, tests.
- Acceptance cases: `approve-two-drafts-old-code` (add a check that the jam draft exists), `approve-then-change-price`.

### HASS-FIX-F7F8: photo edge cases (S2/S3)
- Goal: two photos in one message for one product give ONE listing and one reply (the extra photo is kept as a second image or ignored with one line). A blurry or irrelevant photo gets one short ask: "I can't read this photo. What is it, or can you send a clearer one?"
- Owned files: `hass/conversation.py` (`_photo`, `_photo_batch`, `_read_label` only; F2 owns `_read_intake`, which is a different function, so coordinate the merge order: after F2), tests.
- Acceptance cases: `intake-two-photos`, `intake-blurry-photo`, `intake-irrelevant-photo`.

### HASS-FIX-F10: till reads in plain words (S2)
- Goal: "how many avacados", "whats low", "how many glue left", "are eggs in stock?" are answered from the cache with a plain yes/no or a count, using fuzzy product matching; no interpreter call.
- Owned files: `hass/clover/chat.py`, tests `hass/tests/test_clover_chat*.py`.
- Acceptance cases: `stock-typo`, `stock-low`, `stock-in-stock-question`, `stock-avocado` (plural wording).

### HASS-FIX-F11F13: help, status, shelf, typos, expiry wording (S3)
- Goal: a short help (about 15 lines; the capability dump goes behind "help more"; build on PR #1009 if merged) whose yes line says "yes <code>". `status` explains the shelf check in one line. "shelf" means the shelf check. "stopp changes" is steered to "stop changes". "ok" after expiry names the expired listing and `again <code>`.
- Owned files: `hass/chat/commands.py`, `hass/chat/core_pack.py`, `hass/chat/wording.py`, tests.
- Acceptance cases: `cmd-help`, `cmd-shelf`, `cmd-stop-typo`, `approve-idle-hour-ok`.

### HASS-FIX-F12F15F16: claims, voice cost, polish (S3/S4)
- Goal: a health claim is dropped with one line ("Dropped from the listing: cures colds") and the listing is still made. "three bucks a basket … sell at three dollars" is the price, not the cost. "$3,500.00" has a thousands separator. The undo wording is plain ("hide SUPERGRIP GLUE from the website"). "I'll send a separate message about the website" is said only when one will be sent.
- Owned files: `hass/product_claims.py`, `hass/answer_reader.py` (prompt examples only), `hass/voice.py` (money format), tests.
- Acceptance cases: `intake-claims-health`, `intake-voice-runon` (after F2), `price-huge`, `approve-undo-after-publish`.

## Interpreter speed and timeout recommendation (measured, see the report)
- Codex (gpt-6.2-sol, effort low): interpret median 3.1 s / max 6.0 s; label median 5.3 s / max 5.8 s; the same finance prompts on Codex took 2.8 / 4.6 s. **Keep the timeout at 12 s.** It never fired here.
- Local Qwen thinking-cap: finance reads median 2.2 s but p90 18.2 s / max 20.9 s; interpret median 11.4 s / max 17.5 s. That is the slow part of every priced text. **Recommended, in order:** (1) code: call the answer reader only when the parser fails (F2 card); this needs no config change. (2) INSTALL, after G agrees: `interpreter.fallback.think` is not allowed with api `openai` (`cloud_codex.block_ok`), so the only config lever is a faster local model or tag for the fallback. Measure a non-thinking Qwen tag on these 13 recorded finance prompts first (local-worker card, GPU shared with live Hass). (3) Sending finance texts to Codex (2.8 s median) would change the PLAN-v2 finance-local privacy rule. That is a **G decision**, not an operator change; raise it only with (1) and (2) measured.

## INSTALL notes for astra-orchestrator
- No host.json change is recommended yet: the 12 s Codex timeout and 60 s Qwen fallback (capped by BUDGET 28 s) are not what makes these tests slow. Revisit after HASS-LIVE-FIX-2's measurement of the 118 s reply and the F2 code change.
- No install is needed for the chaos suite: replay runs in CI with no network. Re-recording (`--record --preview --node ~/agent-work/tools/node-v22.23.4-linux-x64/bin/node`) is for the private host only, with budgets `--max-codex` / `--max-qwen`.
