# HASS-INTERP-OPENAI-1: the Hass interpreter on the idle GPU Qwen, with the CPU model as fallback

Card t_37c417d0. Date 2026-11-07 (evening PST), AgentOrange. Author: sonnet-coder. Status: **built and measured; not applied**. `host.json` on the box is unchanged (the operator applies the block in section 6 after review). All inputs synthetic (the HASS-NL-1 corpus, the ten invented label photos). No owner text, photo, key or `~/.config/hass` was read. Nothing restarted, pulled, loaded or deleted; no Mac, no owner message.

## 1. Answer in five lines

1. `host.json` `interpreter` now accepts `"api": "openai"` (default stays `"ollama"`) and, with it, an optional `"fallback"` block for the Ollama CPU model. The router `http://127.0.0.1:8010` serves `qwen3.8:27b-thinkingcap-q6`.
2. **Measured: a free-text ask takes p50 1.26 s, p95 2.90 s, max 3.61 s (20 corpus items, 0 failed)**; the first call after the prompt was last seen took 9.3 s. The CPU model took p50 25 s and p95 104 s on the same kind of asks (recorded HASS-NL-1 run, shared box). Label photos: p50 2.09 s against about 65 s on CPU. The estimate in the card (2-6 s) held.
3. **Answers agree in kind, not always in words.** 18 of 20 asks have the same kind of answer as the CPU run (draft / question / refusal); 8 of 20 are word-for-word equal; the rest differ in wording only, except two (section 4). **One of the 20 is a wrong draft by the GPU model (n091)**; every draft still goes to the owner for yes/no first, so nothing is applied unasked.
4. **Shared model:** a Hass call that arrives while one fleet request is generating waits for it (no error, no rejection): about 3.4 s, 9.2 s and 9.0 s extra behind fleet generations of 3.7 s, 9.5 s and 9.5 s. With the 60 s timeout, a fleet generation that has more than about 55 s left makes Hass time out and use the CPU fallback.
5. Tests: 33 new tests (backend selection, fallback, thinking stripped, contract violations rejected, timeout, no socket beyond loopback, audit row, host.json keys); the full hass suite passes (3,645 tests over 6 shards, 0 failures).

## 2. What changed

- `hass/interpreter_local.py`: `LocalInterpreter(..., api="ollama"|"openai")`. The openai request: temperature 0, `response_format` JSON object, `max_tokens` 2000, `chat_template_kwargs.enable_thinking=false`; same loopback-only URL check, no proxy, no redirect, same 256 KiB limit and short error codes. The reply must be one choice with `finish_reason: stop`; a `<think>` block (or reasoning ending in `</think>`) is removed, any tag left elsewhere fails the call, `reasoning_content` is never read, and the rest must parse as one JSON object (no repeated keys, no NaN). `FallbackInterpreter(primary, fallback, valid)`: one retry, never a loop; triggers: error, timeout, unparseable text, or a JSON object outside the host's reply contract. A model's honest `{unsupported}` or `{question}` is an answer, not a failure.
- `hass/host.py`: `interpreter` accepts `api` and (only with `openai`) `fallback` {`url`,`model`,optional `timeout`,`think`}; `think` is refused beside `api: openai`. `python3 hass/host.py check` rejects everything else as before. The builder returns the plain interpreter when there is no `fallback` block.
- `hass/conversation.py`: one row per interpreted message in a lazily created table `interpreter_audit` (`provider_id`, `at`, `backend` that answered, `fallback` 0/1, `primary_error`, `error`, `seconds`): short codes only, never owner text, prompt, URL or reply. Only written for an interpreter that names its backend. The daily cap, timeout, approvals, owner, reply and publish logic are untouched; a fallback message counts once against the cap (test).
- `hass/label_reader.py`: `LabelReader(..., api="openai", fallback=<LabelReader>)` (data-URI photo, same prompt and `keep` rules). **Not wired into host.py** (it is not today either), so the photo path stays as it is until a separate card wires it.
- `hass/nl_eval.py`, `hass/label_eval.py`: `--api openai` for operator timing runs. `docs/hass/IMPLEMENTATION.md`: one paragraph.

## 3. Measured (real local router, synthetic inputs)

Method: `measure.py` (2026-11-07 evening): 20 cases from the 43 that the HASS-NL-1 CPU "after" run answered successfully (stratified over the intents, deterministic), sent one after another through `LocalInterpreter(api="openai", timeout=60)` with the same prompt builder, hints and fixed `sent_at` as `nl_eval --live`. Agreement is against those **recorded** CPU replies (qwen3.6:35b-a3b-64k, thinking off, prompt as of the HASS-NL-1 PR); I made no new CPU call because that would load a model on the shared Ollama.

| Measure | GPU Qwen3.8 via router (now) | CPU qwen3.6 (recorded) |
|---|---|---|
| Free-text ask, seconds p50 / p95 / max (n=20) | **1.26 / 2.90 / 3.61** (mean 1.44, min 0.63) | 25 / 104 (HASS-NL-1 report, 43 cases); 2 of these 20 timed out at 120 s on the first attempt |
| First call (prompt not in the server cache) | 9.33 s (run 1, 22 cases); 1.78 s in the rerun (cache warm) | 120 s timeout to 223 s after a model load |
| Failed calls | 0 | 1 of 43 |
| Label photo, seconds p50 / p95 / max (n=10) | **2.09 / 2.38 / 2.42** | p50 64.7 (HASS-MODEL-1 run, shared box) |
| JSON valid / contract valid | 20/20, 20/20 | 20/20, 20/20 |
| Strict pass (right ops, args, words) | 17/20 = 85% | 16/20 = 80% |
| Wrong drafts | 1 (n091) | 0 |
| Over-cautious (asked or refused a clear ask) | 2 | 3 (+1 content-miss) |
| Same answer, exactly | 8/20 | |
| Same kind of answer (draft / question / refusal) | 18/20 | |
| Pass-or-not agrees | 19/20 | |
| Label name / brand / category right | 10/10, 9/10 (+1 right null), 1/10 | 10/10, 9/10, 0/10 |
| Same label answer as CPU | 9/10 (l04: GPU also read category "eggs") | |

The category is almost always dropped because the label prompt does not list the catalog categories (already found in HASS-MODEL-1, separate card HASS-LABEL-CATS-1); unchanged here.

Queue wait (one synthetic "fleet" request in flight; I used a plain counting prompt through the same router, three times, about 35 s of slot time in total; the slot is single, parallel 1). The Hass ask is the longest-answer case (n110); idle it takes 2.7 s.

| Fleet request generating | Hass call started | Hass total | Extra wait |
|---|---|---|---|
| none | | 2.70 / 2.72 / 2.72 s | 0 |
| 3.69 s (100 tokens) | 0.5 s after it began | 6.10 s | about 3.4 s |
| 9.46 s (292 tokens) | 0.5 s after | 11.92 s | about 9.2 s |
| 9.46 s (292 tokens) | 0.5 s after | 11.74 s | about 9.0 s |
| after each: back to | | 2.71 s | |

The router queues the call (no 429, no error). The wait is the rest of the fleet generation, so the cost of sharing is "a long fleet answer delays Hass", not failure, until the 60 s timeout. A fleet generation of over 60 s was **not** run (it would hold the shared slot for a minute); the fallback test covers the timeout case with a fake transport. Worst case when the router is wedged: 60 s + the CPU model's 25-120 s.

## 4. Items that differ from the CPU answer (12 of 20; all synthetic texts)

| id | text | GPU | CPU (recorded) | Class |
|---|---|---|---|---|
| n072 | take the jam off | question "Which jam ... strawberry, raspberry, or blackberry?" | same question, with maker names | wording |
| n110 | the lemons description should say they are great in cocktails | edit product 017, same sentence ending "They are also great in cocktails." | same edit, "Great in cocktails too." | wording (free text) |
| n138 | move the hike to 9 | question, "9:00" | question, "9am" | wording |
| n207 | what's our address again | refusal text with the address | refusal text with the address ("Our address is ...") | wording |
| n229 | never mind | `send no` | `send no <code>` | wording |
| n248 | the good oil description ... Templeton | edit product 045 | same edit, different sentence order | wording (free text) |
| n253 | add Bacon avocados fruit shelf | question (asks if Bacon is a new product) | question (Hass or Bacon avocados?) | wording; both over-cautious |
| n257 | eggs out and the honey is limited | question about the honey only | same question | wording (both leave the eggs part out) |
| n215 | email everyone on the hike list | refusal explaining the site sends no email | refusal text `send status` (odd) | wording; GPU answer is the better one |
| n286 | cancel them both | `send no a1b2` | `send yes a1b2 c3d4` | **content**: the CPU text is wrong (yes); the GPU one answers only for one code (the scorer passes it, CPU is a content-miss) |
| n170 | put the old photo back on the homepage | question "Which photo ...?" | refusal (no previous image kept) | **kind**: both counted over-cautious |
| n091 | Linns is in Cambria, not Morro Bay | **draft: maker.edit Linn's place Cambria** | long question (Linn's or Stepladder?) | **kind: GPU wrong draft** per the corpus (a question was expected); the owner would see the draft and say yes or no |

Run 1 (22 cases, same 20 plus n192 and n240) is in `interp-openai-1/run1_*`: same behavior, 0 failed.

## 5. Safety checks

- Thinking text: the router puts the model's reasoning in a separate `reasoning_content` field and the answer in `content`; with `enable_thinking=false` the field is absent (checked live). Tests prove a `<think>` block in the text is dropped, tags elsewhere reject the call, and an answer hidden in `reasoning_content` is never used.
- Contract: replies outside `{ops, revises}`, `{question}`, `{unsupported}` fall back to the CPU model once; if that is also outside, the host's own check turns it into the unreadable reply (unchanged behavior).
- Loopback only: `check_url` is applied to the main and the fallback URL for both backends; `host.py check` rejects other hosts, https, userinfo and paths; a test opens no socket during a full fallback round.
- Audit: one row per message, short codes and seconds only (test greps for owner text, prompt, URL, model name).

## 6. host.json: apply and rollback (operator step; not applied)

I did not read `~/.config/hass/host.json`. **Save the current `interpreter` block verbatim before changing it.** From HASS-MODEL-1 and the card it is the Ollama CPU model; if it is exactly the block below, rollback is that block.

Apply (the one change; every other key unchanged; `timeout` 60 s for the GPU model, 120 s for the CPU fallback; the `think:false` on the fallback keeps CPU replies short):

```json
"interpreter": {
  "url": "http://127.0.0.1:8010",
  "model": "qwen3.8:27b-thinkingcap-q6",
  "api": "openai",
  "timeout": 60,
  "fallback": {"url": "http://127.0.0.1:11434", "model": "qwen3.6:35b-a3b-64k", "timeout": 120, "think": false}
}
```

Rollback (the current Ollama block; use your saved copy if its `timeout`/`think` differ):

```json
"interpreter": {"url": "http://127.0.0.1:11434", "model": "qwen3.6:35b-a3b-64k"}
```

Then `python3 hass/host.py check --host <host.json>` must say ok (it rejects a bad block), and the service picks the config up when the operator restarts hass-worker, which is also the operator's step. Needs the PR merged and `runtimeCommit` moved to the merged commit. Afterwards: `sqlite3 <state>/conversation.db "select backend, fallback, count(*), round(avg(seconds),1) from interpreter_audit group by 1,2"` shows which backend answers and how fast.

## 7. Limits and left

- CPU numbers are the recorded HASS-NL-1 / HASS-MODEL-1 runs, not re-run now (a new CPU call would load a model). Prompt differences since then are the #507 date-hint fix only.
- One run of 20 asks and 10 photos, one queue session of 3 trials; temperature 0 makes the model answer repeatable, but this is a sample, not a benchmark. The GPU model's accuracy (85% strict, 1 wrong draft in 20) is a small-sample number; approvals stay on.
- The fleet owner has not confirmed that Hass may use the single slot (operator decision named in HASS-MODEL-1).
- Not done (named, separate cards): wiring `LabelReader` into the service, listing categories in the label prompt (HASS-LABEL-CATS-1), "on it" acknowledgement for slow replies (HASS-ACK-1), `revises` default (HASS-REVISES-1).

## 8. Files

`reports/hass/interp-openai-1/`: `measure.py`, `queue.py` (the scripts that ran; they expect the card workspace layout), `text_summary.json`, `gpu_text.jsonl`, `labels_summary.json`, `gpu_labels.jsonl`, `queue.json` (its `impliedWaitSeconds` used a 1.3 s idle baseline by mistake; the table above uses the measured 2.7 s), `run1_*` (first 22-case run).
