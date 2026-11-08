# HASS-TAPBACK-1: a real tapback on the owner's message, never a text

G, 2026-11-08, after trying the live 👀 text: "I wanted it to MARK my message with the eyes to indicate it saw my message, not send me a message of eyes. It should interact as a person, like respond with thumbs on my message."

**Done in this PR (code, tests, docs only):** the forwarder's "seen" ack is now one real iMessage tapback (BlueBubbles `POST /api/v1/message/react`) on the owner's message. The text-👀 path is deleted, not switched off: `ACK_TEXT`, the `acker` argument and every call that sent the ack through the text sender are gone. **Not done, by design:** nothing was run on the Mac, nothing was sent, SIP, BlueBubbles settings and `~/.config/hass` were not touched. Until G does the runbook add-on, the Private API is off, so the forwarder sends **no ack at all** (and logs why); it never falls back to a text.

## What the server supports (which reactions, and how sure we are)

| Fact | Source | Status |
|---|---|---|
| The react endpoint is `POST /api/v1/message/react` with `chatGuid`, `selectedMessageGuid`, `reaction`, `partIndex`; it **requires the Private API**; minimum server 0.3.0; `partIndex` needs macOS Big Sur+ and server 1.4.0+ | BlueBubbles API reference (SDK docs, "Send a reaction" / "Private API features"), and `MessageInterface.sendReaction` in the BlueBubbles server source (`checkPrivateApiStatus()` first) | **Verified from docs and server source (read this run); not verified against the live server** |
| Exactly six reactions can be sent: `love`, `like` (thumbs up), `dislike`, `laugh`, `emphasize`, `question`; each can be removed with a `-` prefix (`-like`) | `MessageInterface.possibleReactions` (server v1.9.9 source) and the same docs | **Verified from source and docs; not verified live** |
| **No emoji reaction** (so no 👀) is documented or accepted by the send endpoint. An emoji tapback exists inside iMessage (incoming code 2006) but BlueBubbles' react call has no way to send one | same list; nothing about emoji in the docs or `possibleReactions` | **Not documented. Unverified on a live server and not offered by the code.** By the card's rule ("try the eyes emoji only if the server documents emoji reactions") the default and only choice is `like` |
| `GET /api/v1/server/info` returns `private_api`, `helper_connected` and `server_version` (the existing GET-only probe reads the first two; `ackcheck` now also prints the version) | existing probe code (FAST-1) and another BlueBubbles client that reads the same three keys | **Probe code verified by tests; response shape unverified on the live server** (same status as before: "BlueBubbles REST shapes remain UNVERIFIED on a real Mac") |

So the version is read (printed by `ackcheck` and recorded by G in the runbook step) but no known version documents emoji reactions, so there is nothing for the code to branch on: the allowlist is the six names and the default is `like`.

## What changed

`mac/hass_forwarder.py` (the one Mac-side file the operator ships):

- **Reactor:** new `BlueBubblesReactor.react(chat, guid, reaction)`: one POST to `/api/v1/message/react` with `{chatGuid, selectedMessageGuid, reaction, partIndex: 0}`, password only in the `password` query parameter, read fresh from its private file, 1.5 s limit (`ACK_TIMEOUT`, unchanged), no redirects or proxy. It has no text method. A reaction outside the allowlist (including any `-name`, which would *remove* a tapback), or a guid that is not a plain message guid, raises before any network call. Errors carry no URL or password.
- **Config key `ack_reaction`** (optional, default `like`): must be a string in `love, like, dislike, laugh, emphasize, question`, otherwise the config is refused at start. The row decision re-checks it (`bad_reaction`) so a bad value could never reach the wire. The existing `ack` boolean stays the on/off switch.
- **Private API gate:** before a tapback the forwarder asks the same GET-only `server/info` (0.5 s limit; the answer is reused 30 s, an unanswered probe 5 s, so a burst asks once). `private_api` and `helper_connected` must both be exactly `true`. Otherwise **no react call and no text**: reason `private_api_off`, `helper_disconnected`, or `private_api_unknown` (no answer, odd shape: fail closed).
- **Message guid check:** the guid must match `[A-Za-z0-9][A-Za-z0-9_-]{0,127}` (a UUID in practice). Missing or malformed means no call and nothing else leaves the Mac (`bad_guid`; the probe is not even asked). The message itself is still delivered as before.
- **Failure handling:** a failed, refused or slow react is recorded `react_failed`, never retried, never turned into a text. Every skip prints one stderr line `ack_skipped reason=<code>` (codes: `stale, off, paused, unknown, bad_guid, bad_reaction, private_api_off, helper_disconnected, private_api_unknown, react_failed`; no message id, text, chat or sender in it). The stage log still gets `ack-start`/`ack-end` with `outcome`.
- **`ackcheck`** (GET only) now prints `ackMethod: "tapback"`, `ackReaction`, `privateApi`, `helperConnected`, `tapbackPossible`, `serverVersion` and the six `supportedReactions`.

Unchanged on purpose (re-tested): owner chat and owner sender only; never a stranger, group, Hass's own message, edit, reaction, or a message older than 120 s; paused or unknown pause state means no tapback (fresh sealed `state` question every time, plus the Mac's own pause-ahead check); one tapback per message id via the spool `ack` table (claimed before the call, `sending` is never re-sent after a crash, the `sent` mark is in the spool file so it survives restarts and replays by webhook, catch-up poll and spool); the PR 506 bounded-burst scheduling (dispatcher thread, one worker per pending message, up to 50) and the 2 s `late` / 10 s `stale` rules. No second tapback when the reply is sent: there is exactly one ack call site. Approval, owner, reply and publish logic were not touched.

`docs/hass/MAC_RUNBOOK.md`: step 7 now says Private API stays off *for now*, the step 12 config block shows `"ack_reaction":"like"`, and an un-numbered **Add-on** section at the end lists what G runs on the mini (T1 `csrutil disable` in Recovery, T2 enable the Private API and install the helper from BlueBubbles Settings, T3 `ackcheck` and confirm `privateApi: true, helperConnected: true`, T4 operator ships the file, kickstart, owner texts `status`), plus choosing a reaction, the rollback and how to undo SIP. The 23-step numbering, phase counts and the runbook contract test are unchanged. `mac/README.md` describes the tapback in place of the text 👀.

## Tests (synthetic BlueBubbles only: `hass/tests/test_fast_ack.py`)

All the old ack tests were kept and re-pointed from "a text 👀" to "a tapback" (owner/stranger/group/echo/edit/old-message rules, replay by webhook + poll + direct accept + restart, crash mid-call, paused/unknown/pause-ahead, the real-host end-to-end and pause-race cases, the burst, `late`, `stale` and thread tests). New, one per card requirement:

- tapback sent once on an owner message, with the exact chat, guid and `like`, and **no text** anywhere (`NeverAText`, `WhoGetsAnAck`);
- Private API off, helper not connected, and a probe that cannot answer or answers oddly: no react call, no text, `ack_skipped` reason logged, delivery still happens; the probe is shared by a burst and re-asked after its TTL;
- stranger, group, other chat, echo, edit, reaction, look-alike address: nothing;
- replay and restart do not double-tap (a second test closes the spool, reopens it and replays by doorbell + poll + ack twice: still one call, mark still `sent`);
- a react failure (HTTP 4xx/5xx/3xx, odd status, transport error with the URL in its text, unreadable password file, any exception) sends nothing else, is logged by code only, and does not delay or block delivery or the real reply (the only text in that test is the reply itself);
- a message guid that is missing, empty, with spaces/newline/`/`/`;`/`?`/leading dash, over-long, non-ASCII or the wrong type: no call, probe not asked, message still delivered;
- allowlist enforced in config load (`-like`, `eyes`, 👀, `Like`, empty, non-string, bool all refused), in the row decision and in the reactor (no network call);
- wire shape: one `POST /api/v1/message/react?password=…` with exactly `chatGuid, selectedMessageGuid, reaction, partIndex: 0`, the default and the clamp timeouts, and a structural check that no text-ack constant, `acker` argument, text method on the reactor or reference to `message/text` remains in the forwarder.

## What this PR cannot show (open items, for the operator)

1. **Nothing was run against a live BlueBubbles.** Every status above marked "verified" means "read in the BlueBubbles docs/source and covered by tests against a synthetic transport", not "seen working".
2. **React latency is the main risk.** In the server source the react call waits (up to 60 s) for the reaction to appear in the Messages database before it answers. If that routinely takes more than the forwarder's 1.5 s limit, the tapback will land on the phone but be recorded `react_failed` (and `ack_skipped reason=react_failed` logged). It is harmless (no retry, so no duplicate, and no text) but it makes the log say "failed" for a delivered tapback. Check after deploy: ask for a tapback on a test message, then compare the phone with `ack-start`/`ack-end` `outcome` in the stage log. If the real time is 2–5 s, raising `ACK_TIMEOUT` is a one-line change for a follow-up; I did not change timing here because the card keeps the PR 506 scheduling as is.
3. The old FAST-1 benchmark script `reports/hass/fast-1/stage_bench.py` was a one-time measurement of the text 👀 with a stand-in sender; it is left as history and is not re-run (its stand-in does not answer the Private API probe, so it would now record no ack).
4. SIP, the Private API helper and the BlueBubbles settings are G's steps (add-on T1–T3). Rollback after rollout is just `"ack": false` in the Mac config and a forwarder kickstart; no SIP change is needed to roll back the code.
