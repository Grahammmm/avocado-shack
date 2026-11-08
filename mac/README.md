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

Eyes ack (HASS-FAST-1): when the forwarder stores a NEW message from the owner's own address in the owner's one-to-one chat,
it sends one text `👀` to that chat through the same BlueBubbles send as replies, before the receiver or any model is involved.
It runs on its own thread with its own SQLite connection, kicked the moment a message is stored (webhook fetch or catch-up), so a
slow reply pull, picture, catch-up query or receiver post cannot delay it, and a slow or failing 👀 send cannot delay inbound
delivery. Never for a stranger, a group, Hass's own message (so never for its own 👀), an edit, a reaction, a message found more
than 120 s after it was sent, or while changes are paused. Pause is asked of the host fresh before every 👀 (sealed read-only
`state` op, 0.5 s limit, nothing cached): the host answers paused when its pause flag is set, when a pause command is still unread
in its queue, or when it cannot tell; the Mac also holds the 👀 while a pause command (or an unreadable message, or an earlier
unresolved doorbell) is stored here and not yet handed to the host. No answer in time, or an old host that does not know the op,
means no 👀 (final: never sent late). One ack per message id (spool table `ack`, claimed before the send, so a crash, a replay or
two processes never send a second); a failed or slow (1.5 s limit) send is recorded and ignored, an ack unsent after 10 s is
dropped. One attempt takes at most 0.5 s + 1.5 s. Optional config key `"ack": false` switches it off. The tapback route is not
used: BlueBubbles' react call needs the Private API (kept off) and iMessage has no 👀 tapback; `ackcheck --config FILE` (GET only,
sends nothing) prints whether this server could send any tapback.
Deploy the host first (it learns the `state` op), then the Mac; a new Mac with an old host just sends no 👀.
Timing: the forwarder writes `stages.jsonl` in the spool dir (stage name, time, a one-way hash of the message id; no text or
sender) and the host writes one in its host dir; `python3 hass/stagelog.py MAC_LOG HOST_LOG` prints the table. Reply pull is every
1 s for 3 minutes after an owner message (5 s otherwise); the catch-up poll is every 15 s (was 60 s).
