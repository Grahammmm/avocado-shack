# Hass Mac forwarder (HASS-FWD-1)

Python 3.12+ stdlib only, from a read-only checkout. This is code, not an install.
BlueBubbles REST response shapes and sleep recovery are **UNVERIFIED on a real Mac**;
G's attended smoke checks must pass before use. No doorbell-only fallback.

Commands: `python3 -B mac/hass_forwarder.py {serve,status,check} --config FILE`.
`status` prints numeric counts only; `check` uses GETs only (never sends a message).
`serve` binds the webhook to 127.0.0.1 and reaches the receiver over Tailscale.

Create the config privately (0600, regular file, owned by the dedicated Mac user):
closed keys `ownerChat` (`iMessage;-;<address>`), `receiverUrl`
(`http://<tailnet-name>:8795`), `bbPort`, `bbPasswordFile`, `secretFile`,
`spoolDir`, `webhookTokenFile`, and optional `webhookPort` (8796).
All file/directory paths are absolute. The spool directory must already exist at
0700. Password file: nonempty UTF-8, <=4096 bytes, 0600. Secret and webhook token
files: exactly 64 lowercase hex characters, optional newline, 0600. Never commit
these files. Webhook URL: loopback `/bb/<token>`; never publish it.

The webhook stores only an event type and guid until REST refetch. Normalization
and owner-chat filtering happen before storing text or posting. Pending messages
retry forever in FIFO order, with fresh envelope nonces; completed payloads are
erased. A rejected envelope remains pending and appears in `last_rejected`.
Replies use the sealed relay and persistent sent ids to avoid resending after a
lost ack. A crash between a BlueBubbles send and its sent-id commit can still
repeat that send; the external API and SQLite cannot form one transaction.
Catch-up starts at first-run time (no history backfill). Retries never rewrite the
provider's received time. The one outage notice resets after a successful post.

Render the plist's `@PYTHON@`, `@REPO@`, `@CONFIG@`, `@LOGDIR@` as XML-escaped
absolute paths. G installs it as a LaunchAgent in the dedicated user's logged-in
GUI session; Messages needs that session. FileVault reboot still needs a person.
No installation, launchctl, account setup or real send is part of this build.

Screenshots (HASS-ATTACH-1, UNVERIFIED on a real Mac until runbook step 19): when the host sets `pictures`, up to two PNGs
(<=1.5 MiB each, from the host's `screenshots/` dir) ride the sealed relay. The forwarder sends the text first, then each
picture to the owner chat only via loopback BlueBubbles `POST /api/v1/message/attachment`, after checking sha256, size and the
PNG signature. Progress is kept in the spool (`sent_pics`), so a restart never repeats the text. A picture that fails three
times or does not verify gets one fallback text and the reply is acknowledged. Nothing is written to disk on the Mac.

Tapback ack (HASS-TAPBACK-1; replaces the HASS-FAST-1 text `👀`, which G rejected: Hass must mark the owner's message, not send a message):
when the forwarder stores a NEW message from the owner's own address in the owner's one-to-one chat, it reacts to THAT message with one
real iMessage tapback (default `like`, thumbs up) through loopback BlueBubbles `POST /api/v1/message/react` (`chatGuid`,
`selectedMessageGuid`, `reaction`, `partIndex` 0), before the receiver or any model is involved. It never sends a text as an ack:
there is no text path left. It needs the BlueBubbles Private API (SIP off, helper connected: see the runbook add-on); the forwarder
asks the existing GET-only `/api/v1/server/info` (0.5 s, reused 30 s) and when `private_api` or `helper_connected` is not true, or
the server does not answer, it sends nothing. A react call that fails or takes longer than 1.5 s is recorded `react_failed` and
ignored (never retried, never turned into a text); each skip logs `ack_skipped reason=<code>` (stale, off, paused, unknown,
bad_guid, bad_reaction, private_api_off, helper_disconnected, private_api_unknown, react_failed; no id, text or sender).
Only six reactions exist in BlueBubbles (`love`, `like`, `dislike`, `laugh`, `emphasize`, `question`; no emoji reaction, so no 👀):
the optional config key `ack_reaction` (default `like`) must be one of them or the config is refused; a `-name` (remove) is refused.
It runs on its own dispatcher thread with its own SQLite connection, kicked the moment a message is stored (webhook fetch or
catch-up), and starts one worker thread per pending message (up to 50, one catch-up page), so a slow reply pull, picture, catch-up
query or receiver post cannot delay it, one slow react does not hold up the next message's, and a slow or failing react cannot
delay inbound delivery. Never for a stranger, a group, Hass's own message, an edit, a reaction, a message found more than 120 s after
it was sent, a message guid that is not a plain guid, or while changes are paused. Pause is asked of the host fresh before every
tapback (sealed read-only `state` op, 0.5 s limit, nothing cached): the host answers paused when its pause flag is set, when a pause
command is still unread in its queue, or when it cannot tell; the Mac also holds the tapback while a pause command (or an unreadable
message, or an earlier unresolved doorbell) is stored here and not yet handed to the host. No answer in time, or an old host that
does not know the op, means no tapback (final: never sent late). One tapback per message id (spool table `ack`, claimed before the call,
so a crash, a replay, a restart or two processes never send a second; the `sent` mark is in the spool file and survives restarts); a
tapback confirmed more than 2 s after the message was stored is recorded `late` (not a success), one still unsent after 10 s is
recorded `stale`. Optional config key `"ack": false` switches it off (the rollback). `ackcheck --config FILE` (GET only, sends
nothing) prints `privateApi`, `helperConnected`, `tapbackPossible`, `serverVersion`, the configured `ackReaction` and the six
`supportedReactions`.
Deploy the host first (it learns the `state` op), then the Mac; a new Mac with an old host just sends no tapback.
Timing: the forwarder writes `stages.jsonl` in the spool dir (stage name, time, a one-way hash of the message id; no text or
sender) and the host writes one in its host dir; `python3 hass/stagelog.py MAC_LOG HOST_LOG` prints the table. Reply pull is every
1 s for 3 minutes after an owner message (5 s otherwise); the catch-up poll is every 15 s (was 60 s).
