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
7. Write and run, as services, the forwarder on the Mac (BlueBubbles webhook -> `normalize` -> `seal` -> post to
   the receiver) and the receiver host side (read the secret, call `receive`), with `BlueBubblesSender` as `reply`.
   Neither exists in this repository yet; each is its own reviewed change. This receiver holds every approval
   (`approval-held`); acting on an owner `yes` is part of that reviewed change, not a setting.
8. Smoke checks, by G, in this order: the owner texts `status` and gets one reply; a stranger's text gets no reply
   and no draft; the owner texts a small change, a draft arrives, the owner replies `no` and nothing changes;
   `python3 hass/inbox.py status --state <state dir>` shows the messages as done and no pending backlog.
9. If any step fails, stop the forwarder and the receiver services and leave the drafts unapproved.
