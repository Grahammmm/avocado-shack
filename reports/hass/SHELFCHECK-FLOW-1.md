# HASS-SHELFCHECK-FLOW-1: "mark it sold out" works; the daily shelf check is one plain question

Card t_3894b1bc · repo Grahammmm/avocado-shack · branch `rb/hass-shelfcheck-flow-1` · written 2026-11-08. Everything below ran on a scratch copy (throwaway repo, state and clock). Nothing live was touched, no service restarted, nothing sent.

## What was wrong (plain words)

Hass will only write a product's "Sold out / Limited / Available" word onto a day that has a **shelf check** (the store's `selection_checked_on`), so an old word is never shown as if it were checked today. That safety rule is right. The defect was how Hass handled it: `hass/ops/catalog.py` refused the change with `the selection was not checked today; check the selection first`, `Conversation` sent that out as `Not drafted: ...`, and nothing told Mike how to do the check (it was only possible by saying "I checked the selection today: ..." in the exact shape the docs show). So "mark the Hass avocado sold out", the most common daily job, never produced a draft.

How the check is set today (read first): `store.confirm_selection` (`hass/ops/store.py`) is the only op that writes `selection_checked_on`; it goes through the normal draft and approval path. `product.set_availability` refuses unless that date is today (Pacific). `morning_report` / `status` only *show* the date ("Shelf check: not done yet").

## What changed

1. **The refusal becomes a question** (`hass/conversation.py`, `_request` / `_ask_shelf`). When the interpreter's change is refused *only* because today's check is missing (none yet, or older than today; matched by the constant `catalog.NOT_CHECKED_TODAY`, not by a fuzzy string), Hass replies:
   > Before I change that, is the shelf list right for today? Reply yes if it is, or tell me what is different.

   and keeps the interpreted request. Nothing is drafted or written.
2. **The request is kept in the HIKE-FLOW-1 open-request store**, not a second one: the same one-row `open_asks` table, now with a nullable `pending_json` column (added on first use to a store made before this change). The kept request is bounded by the same 30 minute limit (`RECENT_MINUTES`).
3. **Mike's bare `yes` drafts the check and the change as ONE draft** (`_shelf_answer`): the ops `store.confirm_selection {}` + the kept ops go through the normal editor and proposal path, so the check is dated by the editor clock, shown in the draft, and recorded as a draft / approval / commit like any change. The draft still needs his normal `yes`. `no` closes the question and changes nothing. Any other message is read as his next request and closes the old question.
4. **The morning report asks the same question once** (`_report`). The first `report` of the day with no check for today ends with `Is the shelf list right for today? Reply yes if it is, or tell me what is different.` and opens the same kind of row with no change attached, so his `yes` drafts the check alone. A `control` row `shelf-asked` holds the day, so a second report the same day asks nothing.
5. A check dated *after* today (wrong clock) cannot be fixed by a yes, so Hass says: "The last shelf check is dated in the future, so the date on this phone or computer looks wrong. Nothing was changed."

Files: `hass/conversation.py`, `hass/ops/catalog.py` (one constant), tests `hass/tests/test_shelf_check_flow.py` (35 new), `test_report_command.py` / `test_report_waiting.py` (the report now ends with the question when no check is today; those tests either strip it or set today's check), docs `COMMANDS.md`, `IMPLEMENTATION.md`, `TRIAL.md`. The interpreter prompt is **unchanged** (no prompt snapshot, corpus or pin moved).

## Safety rules kept (and where they are tested)

| Rule | How it holds | Test |
|---|---|---|
| Only the owner can answer | the question is only asked of, and a `yes` only read from, the owner chat/sender; a stranger's message is `ignored` before any of this | `OnlyTheOwnerTests` (stranger yes in the owner chat and in a group, stranger asking for the change, the owner's own echoed message) |
| An unconfirmed message never writes | asking only writes the private chat store; the site is written only by the existing approval of the draft | every test asserts 0 commits and 0 approval rows before the approving `yes` |
| The check is dated and logged | it is an op in a normal draft: dated today by the editor clock, recorded in the draft row, the approval row and the commit | `test_the_approval_applies_both_dated_today_and_it_is_logged` |
| Approvals do not change | the draft needs the usual `yes`; `yes <code>` still only approves that draft; a bare yes/no answers the question and never approves or cancels a waiting draft | `test_a_yes_does_not_approve_a_waiting_draft_while_the_question_is_open`, `test_a_yes_with_a_code_is_an_approval_not_the_answer`, `test_no_changes_nothing_closes_the_question_and_cancels_no_waiting_draft` |
| Stale availability is not published as if checked | `product.set_availability` is untouched: it still refuses without today's check; the check is added *in the same draft*, never skipped | `test_a_refusal_that_is_not_the_check_is_unchanged` and the existing `test_selection_checked` / `test_selection_per_product_day` still pass |
| The question is only open while it is the newest thing said | any other owner message (including a command) or 30 minutes closes it | `test_an_unrelated_message...`, `test_a_command_while_...`, `ExpiryTests` |

## The scenarios, with the real replies

Scripted interpreter, test clock Monday 2026-11-02 09:00 PST, from `transcript.py` (run on this branch). "Mike" is the owner.

**1. Sold out, no check yet: ask, yes, draft, approve**
```
Mike: mark the Hass avocado sold out
Hass: Before I change that, is the shelf list right for today? Reply yes if it is, or tell me what is different.
Mike: yes
Hass: Got it. This draft also records that the shelf list was checked today.
      Draft 4337:
      store store: selection_checked_on (none) → 2026-11-02
      products photo-product-001: available (none) → no
      products photo-product-001: available_on (none) → 2026-11-02
      Expires 2026-11-02 09:10 PST.
      Reply yes to apply, no to cancel, or send a correction.
Mike: yes
Hass: Applied 4337: store store: selection_checked_on; products photo-product-001: available, available_on
```
(0 commits and 0 approvals until the last `yes`; then 1 commit.)

**2. A check older than today (2026-10-30)**: same two replies; the draft line reads `store store: selection_checked_on 2026-10-30 → 2026-11-02`.

**3. Today's check exists**: `mark the Hass avocado sold out` → a draft at once (`Draft 83b1: products photo-product-001: available (none) → no ...`), no question.

**4. A stranger says yes** (after the question): disposition `ignored`, no reply, no draft, no commit. Mike's own `yes` afterwards still drafts.

**5. `no`**
```
Mike: no
Hass: Okay, nothing was changed. Tell me what is different on the shelf list and I will draft that.
Mike: yes
Hass: Nothing is waiting for approval.
```

**6. A different answer** (`oranges are low`): read as the next change. Because it is another shelf change it needs the check too, so Hass asks the same question again; the interpreter is given the earlier request and the question as context (`recent.earlier`, the HIKE-FLOW-1 mechanism). His `yes` then drafts the check + the oranges only; the Hass avocado is **not** silently marked.

**7. An unrelated message while the question is open** (`change the hours to nine to five`): drafted as usual, the shelf question is closed; `yes` approves the hours draft only, the check is not marked, the avocado is untouched, and a second `yes` says `Nothing is waiting for approval.`

**8. The question expires** (31 minutes): `yes` → `Nothing is waiting for approval.`; the stored request is deleted, not just ignored. Just inside the limit (29 minutes) the yes still works.

**9. Morning report asks once**
```
Mike: report
Hass: Shelf check: not done yet
      Available 0 · Limited 0 · Sold out 0 · Not confirmed 170
      These are your last shelf checks, not stock counts.

      Waiting for you: nothing

      Is the shelf list right for today? Reply yes if it is, or tell me what is different.
Mike: report
Hass: (the same report, no question)
```
**10. `yes` after the report** → `Draft 9e99: store store: selection_checked_on (none) → 2026-11-02 ...`; a second `yes` applies it (1 commit).

**11. A check dated after today** → `The last shelf check is dated in the future, so the date on this phone or computer looks wrong. Nothing was changed.`

Also tested: several products in one message are one question and one draft; a change that revises a waiting draft replaces it after the yes; a store made before this change gains the `pending_json` column; a stranger asking for the report gets nothing and opens nothing.

## Real interpreter check (GPU, scratch state)

`probe_live.py` (adapted from the HIKE-FLOW-1 probe) runs the real `Conversation` + real `LocalInterpreter` (`api=openai`, `127.0.0.1:8010`, `qwen3.8:27b-thinkingcap-q6`) on a throwaway state, 9 scenarios, 20 messages. The real model turned "mark the Hass avocado sold out", "the Hass avocado is back in" and "put the Hass avocado to sold out" into the right op every time, and the replies were word for word the ones above (no check, a 2026-11-04 check, today's check, `no`, a different answer, an unrelated question, the 31-minute expiry, and the report). **11 interpreter calls, all on the GPU backend, 0 CPU fallbacks, 0 errors; 1.2 / 1.7 / 2.7 s (min / median / max).** `yes`, `no`, the report and the check itself use no model call. This probe measures the model on synthetic texts; it is not a live owner test.

## What I did not change, and follow-ups

- **Draft wording.** The draft preview lines (`store store: selection_checked_on (none) → ...`, `photo-product-001`) are the existing draft format used for every change; they contain ids and technical words. Rewording them is the voice work (HASS-VOICE-1), not this card. My own new sentences follow the voice rules (no "selection", no "not drafted", no ids). The older `Not drafted: ...` reply still exists for other refusals.
- **`status` still says `Shelf check: not done yet`** (pinned by `test_status_shelf_check`). It does not ask. Could be made to point at the question; left alone to keep `status` read-only and its tests byte-exact.
- **A different answer asks again** (scenario 6) rather than treating his "what is different" as the check. That is the safe reading of "only a yes marks the check", but it means two questions in a row for "mark Hass sold out" → "oranges are sold out too". A possible follow-up: carry the first request along with the correction so one `yes` covers both. Not built; his original request is dropped when he answers with something else.
- **A yes needs to arrive within 30 minutes of the question**, measured when Hass processes it. After that Mike simply asks again.
- **The whole thing depends on HIKE-FLOW-1 (t_9a32fec3), which is not merged** (that card is blocked; its branch was never pushed). This branch contains its three commits so the open-request store exists; the PR will show them until HIKE-FLOW-1 lands. Merge order: HIKE-FLOW-1 first (or this PR carries it, and HIKE-FLOW-1's own PR shrinks to nothing).
- **Live use** needs a normal deploy of this code (service restart) which I did not do.

## Checks run

- `python3 -B -m unittest hass.tests.test_shelf_check_flow` → 35 tests OK.
- The existing modules touching this: `test_conversation test_report_command test_report_waiting test_commands_doc test_help test_status_shelf_check test_selection_checked test_selection_per_product_day test_morning_report test_auto_policy test_hike_flow test_nl_prep test_interpreter_prompt_design` OK after updating the two report test modules.
- Full CI tier locally (`hass/tests/ci_shards.py`, plan against origin/main = full tier, 4 shards run at once on a busy box): shards 0 and 2 OK (944 and 856 tests). Shard 1 had 4 timing failures in `test_fast_ack.ThreadedAck` (sends must start within 0.5-2 s) that came from running four shards at once; that module passes alone (with `test_readonly_questions`: 103 tests OK). Shard 3 had one real failure, `test_readonly_questions` (`report` compared with `report?` and the first one now carries the once-a-day question); fixed in the test, passes. The PR's CI is the check at the exact head.
