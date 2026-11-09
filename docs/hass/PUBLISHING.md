# Hass live publishing (HASS-PUBLISH-1)

This code is not live-use authorization. G must finish runbook steps 20–22,
including the site-scoped deploy key, checkout, adoption and explicit mode switch.
Tests use disposable local bare repositories; never use the real site as a fixture.

An owner `yes CODE` saves through the existing single writer and releases that
change. Existing sender/chat/hash/base/expiry and live-policy checks still apply.
Conversation says only Saved. Website outcomes are queued separately by recovery:
shown (with a picture when available), not published, unknown, or unconfirmed.
No preview approval is inserted into the chat flow.

## Configuration

`approvals: "live"` requires `previewer: true`, `pictures: true`, and writer
settings `liveSite: "theavocadoman.com"`, `approvalNeedsCode: true`.
The closed `release` object requires absolute `siteCheckout` and `stopFile`,
`siteRemote: "git@github-avocadoman:Grahammmm/theavocadoman-site.git"`, and
`liveUrl: "https://theavocadoman.com"`. Optional bounded settings are dailyCap
(1–50, default 10), minIntervalSeconds (60–3600, default 120), verifyMinutes
(5–60, default 15). Nothing here creates credentials or starts a service.

## Durable books and recovery

The host directory holds 0600 `publish.json` (adoption anchor only), a 0700
`releases/` with one 0600 JSON file per change, and `publish.lock`.
Writes use same-directory temporary files, fsync, replace, directory fsync.
Intent is durable before apply; built before local site writes/commit; pushing,
including its attempt timestamp, before push. No pipeline write changes the
anchor. Landed journals derive the publication head/date; first push attempts
count once per id, including unknown attempts. Missing/corrupt books fail closed.
Retention must not delete journals above anchor_seq; re-anchor first.

Restart never replays apply/build/push. Pre-push interruptions become saved but
not published. An ambiguous push stays unknown until the remote proves delivery
or two observations of the old head at least 120 seconds apart prove no delivery.
A foreign or unreachable remote never proves unchanged. Hash checks have bounded
HTTPS reads, no proxy or redirects, and check at most ten paths; omitted paths
prevent claiming full verification. A late deployment can settle unconfirmed.

STOP is detected by lstat (including dangling links), after the interval wait and
immediately before each push attempt. STOP before push resets only the local
site checkout and holds the saved release open. STOP during push cannot recall it.
An open release refuses every later change. Undo uses the same release path and
is exempt from the daily cap, not from STOP or baseline checks.

## Attended CLI

Use `python3 -m hass.publish_live COMMAND --host /path/to/host.json` from the
installed runtime checkout. Output is one JSON object; errors do not print paths,
owner text, identifiers of owner chats, credentials, or subprocess output.

- `status`: open ids/states, derived site head/date and cap usage.
- `adopt`: match a dated writer build exactly with a clean remote-tracking site.
  Initial mismatch: `adopt --from-remote` records a null-date anchor; only baseline
  is admitted until a dated build has landed.
- `baseline`: build/check and show a manifest confirmation plus privacy pattern
  ids. `baseline --confirm HASH12` releases only that matching privacy-safe build.
  No grandfathering is used for baseline publication.
- `retry CHANGE_ID`: only a not-published release, only if the remote does not
  already contain it. Rebuild/check, check STOP again, and attempt a normal push.
- `resolve CHANGE_ID --as live|reverted`: G's attended conclusion for unknown or
  unconfirmed. Reverted requires exact local/remote old head.
- `unblock [CHANGE_ID]`: only after the writer was undone privately and exact
  baseline equality is restored. No site push. A sole held release is implicit.

Emergency rollback is G-only, outside this worker, followed by writer
reconciliation and attended resolve/adopt as appropriate. Neither retry nor
unblock bypasses an exact baseline or authorizes a new content/privacy policy.

## Live from chat (HASS-LIVE-PLAN-1)

Design, the live table and the test plan: `reports/hass/LIVE-PLAN-1.md`. The steps only G and Michael can do:
`reports/hass/LIVE-STEPS-G-MICHAEL.md`.

- `hass/live_policy.py` `LIVE` is the allow-list of operations (and argument names) that may go live from chat; `PRIVATE` says
  why the others cannot. A refused change is kept as one `policy` row in the private backlog.
- `gIsOwner: true` (with `gSenders` and `gChat`) makes G's own chat a second owner chat, text only. Each owner's yes, no,
  undo and open request belong to that owner's chat.
- `python3 hass/host.py mode hold|private|live --host host.json` rewrites `approvals` (then restart `hass-worker`).
- `python3 hass/publish_live.py revert-last --host host.json` puts back the newest live change that was not undone.
