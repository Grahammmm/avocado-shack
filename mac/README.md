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
