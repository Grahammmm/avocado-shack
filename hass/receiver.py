"""SHOP-3: the inbound receiver, up to but NOT including the live connection (fixtures only).
WORKS NOW: a sealed envelope -> bridge.unseal (MAC, 300 s window, nonce replay) -> Inbox.enqueue -> one drain ->
Conversation.handle(apply=False) (owner/chat/echo/kind guard) -> a draft that waits for the owner's approval.
An owner `yes` is held (`approval-held`): rolled back unapplied, the draft stays proposed; editor.apply is never called.
NOT HERE: no listener, socket, daemon, network call, key file, environment read or sign-in. The secret is a parameter.
Outbound is refused: the default reply raises NotConnected; receive() never sends and never applies a change.
CONNECTING THE REAL CHANNEL is G's job, step by step in docs/hass/CONNECT.md; no agent does any of it.
Envelope text with a repeated key or a NaN/Infinity constant is rejected unread (shape, before the MAC; nonce untouched).
"""
import json, sys  # noqa: E401
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import bridge, stagelog  # noqa: E402

CONNECT_DOC = "docs/hass/CONNECT.md"
REJECTED = {  # bridge.EnvelopeError code -> plain words
    "shape": "the envelope is not in the expected form, so it was not read",
    "version": "the envelope version is unknown, so it was not read",
    "mac": "the envelope signature does not match the shared secret, so it was not read",
    "stale": "the envelope time is over 5 minutes off this clock (expired or from the future), so it was not read",
    "size": "the envelope is larger than 64 KB, so it was not read",
}
MAX_ENVELOPE_BYTES = 64 * 1024  # str is measured as UTF-8 bytes; checked before json.loads
DROPPED = {  # bridge.Drop reason (fixture forwarder side) -> plain words
    "group-or-unknown-chat": "a group or unknown chat; only the owner's one-to-one chat is read",
    "receipt": "a delivered/read receipt, not a message",
    "unsupported-event": "an event type that is not a message",
    "malformed": "an event with missing or invalid fields",
}
IGNORED = {  # Conversation disposition -> plain words (no draft, nothing read as a change)
    "ignored": "not from the owner's sender in the owner's chat, so it was not read",
    "echo": "a message sent from this account (an echo), so it was not read",
    "edited-ignored": "an edit or reaction that is not from the owner, so it was not read",
    "not-read": "an owner reaction or edit; only new messages are read as changes",
}


class NotConnected(Exception):
    """Something tried to send while no channel is connected."""


def not_connected(chat, text, attachments=()):
    """The shipped reply: refuses every send. Nothing is sent until G connects the channel."""
    raise NotConnected(f"a person must connect the channel: see {CONNECT_DOC}")


def forward(event, secret, *, nonce, now):
    """FIXTURE STAND-IN for the Mac-side forwarder: bridge.normalize -> bridge.seal. Returns the envelope as JSON
    text, or the bridge.Drop for an event that is never forwarded. The real forwarder runs on G's Mac."""
    msg = bridge.normalize(event)
    if isinstance(msg, bridge.Drop): return msg
    return json.dumps(bridge.seal(msg, secret, nonce=nonce, now=now), sort_keys=True)


def _pairs(pairs):  # object_pairs_hook: a repeated key (at any depth) is not an envelope
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys): raise ValueError("repeated key")
    return dict(pairs)


def _no_constant(name): raise ValueError("not JSON")  # parse_constant: NaN, Infinity and -Infinity


def _result(result, reason, draft_id=None, disposition=None) -> dict:
    return {"result": result, "draft_id": draft_id, "reason": reason, "disposition": disposition}


class Receiver:
    """state: an open inbox.Inbox (durable queue + nonce store). settings: the Conversation on the same state dir;
    its config.json holds the owner settings (ownerSenders, ownerChat) and its guard decides who is the owner.
    reply: the outbound send callable, never called by receive(); the default refuses with NotConnected."""

    def __init__(self, *, state, settings, reply=not_connected, apply=False):
        self.inbox, self.conversation, self.reply, self._codes = state, settings, reply, {}
        self.stage = stagelog.off  # HASS-FAST-1: host.py swaps in a StageLog; the default records nothing
        self.apply = apply  # HASS-RCV-1: False holds every owner approval (SHOP-3); True lets the Conversation apply it

    def send(self, chat, text, attachments=()):
        """Outbox adapter shape, so Conversation.flush(receiver) goes to `reply` (refused by default)."""
        return self.reply(chat, text, attachments)

    def handle(self, msg, last_try=False) -> str:
        """What drain() calls for each message: Conversation.handle with apply=self.apply (False: an owner approval is
        held, never applied), noting the code of the draft THIS message made proposed (a new row, or a question it filled)."""
        before = self._proposed()
        disposition = self.conversation.handle(msg, last_try=last_try, apply=self.apply)
        if disposition == "proposed":
            made = {k: v for k, v in self._proposed().items() if k not in before}
            self._codes[msg.provider_id] = made[max(made)] if made else None  # None: a repeat reused a waiting draft
        return disposition

    def _proposed(self) -> dict:
        rows = self.conversation.db.execute("SELECT row_id, code FROM drafts WHERE state = 'proposed'")
        return {r[0]: r[1] for r in rows}

    def _intake(self, raw, secret, now):
        """Size, strict JSON, unseal, enqueue -> (result for a refusal or repeat, None) or (None, the queued message)."""
        if self.inbox.db.in_transaction:  # RF0824-10: acceptance is reported/logged only after OUR outermost COMMIT
            raise RuntimeError("receiver intake needs its own transaction: the inbox is already inside one, so a "
                               "'queued' answer could outlive a rollback")
        if isinstance(raw, (str, bytes, bytearray)):
            size = len(raw.encode("utf-8", "surrogatepass")) if isinstance(raw, str) else len(raw)
            if size > MAX_ENVELOPE_BYTES: return _result("rejected", REJECTED["size"]), None
        try:
            envelope = (json.loads(raw, object_pairs_hook=_pairs, parse_constant=_no_constant)
                        if isinstance(raw, (str, bytes, bytearray)) else raw)
        except (ValueError, UnicodeDecodeError, RecursionError):
            return _result("rejected", REJECTED["shape"]), None
        try:  # a missing or short secret is a ValueError from bridge: a setup fault, raised, never a message result
            with self.inbox._tx():  # RF0824-10: the nonce and the queue row commit together or not at all
                msg = bridge.unseal(envelope, secret, now=now, seen=self.inbox.seen())
                queued = self.inbox.enqueue(msg)
        except bridge.EnvelopeError as exc:
            if exc.code == "replay": return _result("duplicate", "this exact envelope was already received"), None
            return _result("rejected", REJECTED.get(exc.code, REJECTED["shape"])), None
        if queued == "duplicate": return _result("duplicate", "this message id was already received; not queued again"), None
        if queued == "history": return _result("history", "sent before the recorded start point; kept as history only"), None
        self.stage("receiver-accepted", msg.provider_id)  # HASS-FAST-1: stage time only (hashed id); nothing else
        return None, msg

    def accept(self, raw, *, secret, now) -> dict:
        """HASS-RCV-1: the first half of receive(): store only, never drain. rejected | duplicate | history | queued."""
        early, _ = self._intake(raw, secret, now)
        return early or _result("queued", "stored; the next drain handles it")

    def drain(self) -> list:
        """HASS-RCV-1: hand every pending message to handle(), in order; [(provider_id, disposition)]."""
        self._codes = {}
        return self.inbox.drain(self)

    def receive(self, raw, *, secret, now) -> dict:
        """One sealed envelope (JSON text, bytes or dict) -> {result, draft_id, reason, disposition}. result is
        drafted | duplicate | history | rejected | ignored | handled (owner message, no new draft) | queued (stored,
        waiting for a photo retry: its own or an earlier message's). draft_id is the new draft's code (None if a
        repeat reused a waiting draft). A crash in drain propagates: the message stays queued and the next
        receive() drains it first (Inbox order; Conversation answers `duplicate` for one it already recorded).
        A str/bytes envelope over MAX_ENVELOPE_BYTES is rejected unread (nonce untouched); a dict is not measured."""
        early, msg = self._intake(raw, secret, now)
        if early: return early
        handled = dict(self.drain())  # self.handle: draft-only, one code per message
        if msg.provider_id not in handled:
            return _result("queued", "stored; it waits behind an earlier message and is handled by the next drain")
        disposition = handled[msg.provider_id]
        if disposition == "duplicate": return _result("duplicate", "already handled; nothing new", None, disposition)
        if disposition in IGNORED: return _result("ignored", IGNORED[disposition], None, disposition)
        if disposition == "proposed":  # this message's own draft, whatever else the same drain handled
            return _result("drafted", "a draft waits for the owner's approval; nothing was applied",
                           self._codes.get(msg.provider_id), disposition)
        if disposition == "approval-held":
            return _result("handled", "an owner approval; this receiver applies nothing until the channel is "
                                      "connected, so the draft still waits", None, disposition)
        return _result("handled", f"an owner message handled without a new draft ({disposition}); its reply waits "
                                  "unsent in the outbox", None, disposition)

    def receive_event(self, event, *, secret, nonce, now) -> dict:
        """Fixtures end to end: forward() (the stand-in forwarder) then receive(). A dropped event is `ignored`."""
        raw = forward(event, secret, nonce=nonce, now=now)
        if isinstance(raw, bridge.Drop): return _result("ignored", DROPPED.get(raw.reason, DROPPED["malformed"]))
        return self.receive(raw, secret=secret, now=now)


def receive(raw, *, state, settings, secret, now, reply=not_connected) -> dict:
    """One-call form of Receiver(state=..., settings=..., reply=...).receive(raw, secret=..., now=...)."""
    return Receiver(state=state, settings=settings, reply=reply).receive(raw, secret=secret, now=now)
