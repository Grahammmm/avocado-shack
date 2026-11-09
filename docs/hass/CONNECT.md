# Connecting the owner's text channel (SHOP-3 boundary)

`hass/receiver.py` takes an inbound message up to a draft that waits for the owner's approval. It works today only
on fixtures that stand in for the real channel. **No agent connects it.** Every step in section 2 is G's, done by a
person; no agent signs in, handles the shared secret or any password, or runs the services. Approval is required
before any agent sends a message (the fleet AGENTS.md/CLAUDE.md rule: no outbound message without G's approval).

## 1. What works now (fixtures)

- `receiver.forward()` stands in for the Mac-side forwarder: a BlueBubbles webhook fixture (`hass/tests/fixtures/
  bridge/*.json`) -> `bridge.normalize` -> `bridge.seal` with a throwaway test key.
- `Receiver.receive()` / `receiver.receive()`: `bridge.unseal` (signature, 5-minute clock window, nonce replay
  refusal) -> `Inbox.enqueue` (durable, start point, duplicates) -> one `Inbox.drain` -> `Conversation.handle`
  (owner sender, owner chat, echo and kind checks) -> a draft for approval.
- Results: `drafted` (with the code of the draft this message made), `duplicate`, `history`, `rejected`, `ignored`,
  `handled` (an owner command or question, no new draft; an owner `yes` is `approval-held`: not applied, the draft
  still waits) or `queued` (waiting behind an earlier photo retry), each with a reason in plain words.
- Nothing is applied by the receiver (it drains with `Conversation.handle(apply=False)`), nothing is sent: the
  default `reply` raises `NotConnected`, so replies stay unsent in the conversation outbox.
- Tests: `python3 -B -m unittest hass.tests.test_receiver`.

Full G-only setup, live gates and stop commands: [MAC_RUNBOOK.md](MAC_RUNBOOK.md).

## 2. What G must do to connect the channel

1. Choose the Mac and the Apple account that will carry the owner's messages, and keep that Mac powered and online.
2. Sign in to that Apple account in Messages on the Mac (G only; Apple sign-in and any 2FA code stay with G).
3. Install and configure BlueBubbles Server on that Mac, set its server password, and keep its REST API on
   loopback (`127.0.0.1`) as `hass/bridge.py` `BlueBubblesSender` requires.
4. Confirm the owner's phone reaches that account: a text from the owner's phone arrives in Messages on the Mac,
   and a test reply sent by G by hand arrives on the phone.
5. Create the shared envelope secret (at least 32 random bytes) and store it where only the forwarder and the
   receiver service accounts can read it (mode 0600). Never paste it into a chat, a card, a commit or a log.
6. Set the owner allowlist in the private state dir's `config.json` `settings`: `ownerSenders` (the owner's
   address), `ownerChat` (the one-to-one chat id, `iMessage;-;<address>`) and `approvalTtlSeconds`; record the
   inbox start point when the inbox is first opened, so older messages stay history.
   **A second owner (HASS-OWNERS-2).** To let two people be owners, each in their own one-to-one chat: put both
   addresses in `ownerSenders`, list both chats in `ownerChats` (`["iMessage;-;<first address>", "iMessage;-;<second
   address>"]`), and keep `ownerChat` as the first one (or leave it out: the first chat in `ownerChats` is then the main
   one). Every chat must be a one-to-one chat with one of the `ownerSenders` addresses, no chat may be listed twice, and
   G's separate `gChat` may not be one of them. To say whose change it was, add optional first names:
   `"ownerNames": {"iMessage;-;<first address>": "Mike", "iMessage;-;<second address>": "G"}` (letters only; no name
   means \"the owner\"). Without `ownerChats` nothing changes: one owner, one chat, exactly as before. Run
   `python3 hass/host.py check` and `python3 hass/health.py` after the edit, then restart the worker. The Mac forwarder
   carries only one owner chat (`ownerChat`) plus the text-only `gChat`; give the second owner's chat to the forwarder as its
   `gChat` for now, and the second owner will get text, not pictures (see LIMITS.md, "Several owners").
7. Run, as services, the forwarder on the Mac (HASS-FWD-1: BlueBubbles webhook -> `normalize` -> `seal` -> post to the
   receiver) and the receiver host, `python3 hass/host.py serve|work --host <host.json>` (HASS-RCV-1): `serve` stores sealed
   posts, `work` drains them and queues replies for the Mac to pull. The forwarder is not in this repository yet. First run
   `host.py check` (config, 0600 key file, runtime commit) and `host.py start-point --at <ISO time>`. `approvals` is `hold`
   (an owner `yes` is held) or `private` (applied through the editor's single-writer path); `live` is not installed.
8. Smoke checks, by G, in this order: the owner texts `status` and gets one reply; a stranger's text gets no reply
   and no draft; the owner texts a small change, a draft arrives, the owner replies `no` and nothing changes;
   `python3 hass/inbox.py status --state <state dir>` shows the messages as done and no pending backlog.
9. If any step fails, stop the forwarder and the receiver services and leave the drafts unapproved.
