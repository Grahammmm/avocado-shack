"""Hass conversation core (H05): owner messages -> A2 drafts -> bound approval -> one apply.

The interpreter only turns text into typed ops (it never sees approvals or calls the editor); deterministic code
does every write. handle() stores each result (message id, draft state, reply) before any reply is sent; flush()
sends. Approval is bound to sender, chat, change id, draft hash, base revision and expiry. Fixture adapter only.
"""
import contextlib, copy, hashlib, json, os, re, sqlite3, stat, sys  # noqa: E401
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor as editor_mod, memory as memory_mod, migration_check, preview as preview_mod, sitegen  # noqa: E402
from hass import claims, interpret_check, label_reader, margins, media, morning_report, morning_report as shelf, owner_answers as answers, social_draft  # noqa: E402
from hass.content_model import HOME_IMAGE_RE, SHELF_LABELS, ContentError, _text as checked_text, checked_on, load_and_validate, load_content, shop_today, validate  # noqa: E402
from hass.ops import catalog, hikes, load_registry  # noqa: E402
from hass.social_message import classify_social  # noqa: E402
from hass import corrlog, hike_chat, live_policy, voice  # noqa: E402
from hass import capabilities  # noqa: E402
from hass.skills import dispatch as dispatch_mod, openreq  # noqa: E402

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
APPROVE, REJECT = ("yes", "approve", "approved"), ("no", "cancel", "reject")
KEYWORD_RE = re.compile(r"(yes|approved|approve|no|cancel|reject)(?: ([0-9a-f]{4,12}))?")
NEAR_RE = re.compile(r"(ok|okay|yes please|yep|yeah|sure|go ahead|do it|sounds good|looks good)(?: ([0-9a-f]{4,12}))?")  # H05
COMMAND_RE = re.compile(r"(history)(?:\s+(?s:.*))?|(undo)(?: ([0-9a-f]{4,12}))?"  # H06, same normalisation as KEYWORD_RE
                        r"|(status|did (?:it|that|my change) work\??)|(pause|stop)(?: changes)?"  # H17; SHOP-4 phrases
                        r"|(resume)(?: changes)?|(help|commands|\?)"
                        r"|(find)(?:\s+(.*))?"  # AV1537-04; the query is re-read from the original text to keep its case
                        r"|(show)(?:\s+(.*))?"  # AV0022-08 (H17): groups 10/11, earlier indices unchanged
                        r"|((?:morning )?report)"  # AV1322-05 (F04): group 12; groups 1-11 keep their indices
                        r"|(post)(?:\s+((?:hike\s+)?\S+(?:\s+\S+){0,5}))?"  # AV1322-07 (F07): groups 13/14; AV1222-11: or "hike <id>"; the id is re-read from the original text to keep its case
                        r"|(margin)(?:\s+((?s:.*)))?"  # AV1102-12 (F03): groups 15/16; the rest is checked by MARGIN_RE
                        r"|(hidden)"  # AV1222-13 (H03): group 17
                        r"|(listing)(?:\s+(\S+(?:\s+\S+){0,5}))?"  # AV1622-09 (H17): groups 18/19; multiword names need a catalog check
                        r"|(photos to take)"  # AV0222-04 (H10/H17): group 20
                        r"|(backlog)")  # SKILLS-FW-3: group 21 (what I could not do yet; read-only)
q = voice.quote  # HASS-VOICE-1: words Mike typed himself, or commands he types, are shown as they are and never judged
HELP_TEXT = "\n".join(("Tell me what to change, in your own words. For example: " + q('"Stop showing the eggs as sold out"') + ".",  # AV1537-03, test_help
    "Other things you can say:",
    q("yes") + " - go ahead with the change waiting for you",
    q("no") + " - cancel it",
    q("status") + " - what I did last and what is waiting for you",
    q("history") + " - what we changed lately, or " + q("history hours") + " to look for one",
    q("undo") + " - take back the last change",
    q("stop changes") + " - I won't change anything until you say " + q("resume changes"),
    q("report") + " - the morning shelf report",
    q("find lion's mane") + " - look something up",
    q("photos to take") + " - the products that still need a photo",
    q("remember parking: back lot") + " - I'll keep a note; " + q("forget parking") + " removes it; " + q("notes") + " lists them",
    q("alias jam: Linn's blueberry preserves") + " - a nickname for a product or maker",
    q("cost Hass avocado: 24 for 12") + " - the price you pay, kept private",
    q("margin Hass avocado at 35%") + " - a price idea from the cost you saved",
    q("post Hass avocado") + " or " + q("post hike Point Buchon") + " - a caption to copy; I post nothing",
    q("listing Etto") + " - what's shown for one thing; " + q("hidden") + " lists what's hidden",
    q("show") + " and a word from the change - repeat a waiting change",
    q("help") + " - this list"))
HELP_TEXT = HELP_TEXT.replace(q("show") + " and a word from the change - repeat a waiting change\n",
                              q("show") + " and a word from the change - repeat a waiting change\n"
                              + q("backlog") + " - what I couldn't do yet; " + q("forget backlog.3") + " takes one off\n")  # SKILLS-FW-3
# H15 owner memory. Verb and key are case-insensitive (the key is stored lower-cased); the text keeps its case.
MEMORY_RE = re.compile(r"(remember)(?:\s+(.*))?|(forget)\s+(\S.*)|(memory|notes)|(alias)(?:\s+(.*))?"
                       r"|(cost)(?:\s+(.*))?", re.IGNORECASE | re.DOTALL)  # AV1222-10: groups 8/9
PHOTOS_TO_TAKE_MAX = 5  # AV0222-04, HASS-VOICE-1: names listed by `photos to take` (a short list, then ask again)
MEMORY_LIST_MAX, HISTORY_MAX = 20, 5  # AV1537-14: docs/hass/LIMITS.md states these (test_limits_doc)
ALIAS_LIST_MAX = 20  # AV0222-05: `memory` lists this many aliases apart from the notes (LIMITS.md)
HISTORY_STATES = ("approved", "applied", "verified", "failed", "reverted")  # AV2022-06: owner-approved changes only
FIND_TEXT_MAX, ALIAS_NAME_MAX = 60, 60  # AV0022-15: docs/hass/LIMITS.md states these (test_limits_doc)
HIDDEN_MAX = 20  # AV1222-13: lines of the hidden list
LISTING_DESC_MAX = 120  # AV1622-09: characters of a product description in `listing`
STATUS_PLAIN = {"active": "on the website", "hidden": "hidden", "held": "on hold", "visible": "on the website",
                "scheduled": "coming up", "cancelled": "cancelled", "completed": "done", "idea": "just an idea", "draft": "not finished"}
LISTING_USAGE = "Which one? Say it like " + q("listing Etto") + "."
LISTING_NONE = "I don't know that one. Try " + q("find") + " and a word from its name."
LISTING_MANY = "That fits more than one thing. Could you say a bit more of its name?"
HISTORY_SEARCH_MAX, HISTORY_TEXT_MAX = 10, 60  # AV2152-02 (H06/H17): `history <words>`; docs/hass/COMMANDS.md
HISTORY_USAGE = "Tell me a word or two to look for, like " + q("history opening hours") + "."
FIND_MAX, FIND_USAGE = 10, "Tell me a word or two to look for, like " + q("find lion's mane") + "."  # AV1537-04
POST_USAGE = "Which product is the post for? Say it like " + q("post Hass avocado") + "."  # AV1322-07
HIKE_USAGE = "Which hike is the post for? Say it like " + q("post hike Point Buchon") + "."  # AV1222-11
HIKE_REFUSALS = {"no such hike": "I don't know a hike called {id}. Try " + q("find") + " and a word from its name.",
                 "hike is cancelled": "{id} is cancelled, so there is nothing to announce.",
                 "hike already happened": "{id} has already happened.", "not scheduled": "{id} isn't scheduled yet."}  # other reasons: POST_CANT
POST_REFUSALS = {"no such product": "I don't know a product called {id}. Try " + q("find") + " and a word from its name.",
                 "not on the site": "{id} isn't on the website right now.",
                 "no photo on the site": "{id} has no photo on the website yet, so I can't make a post for it."}  # other reasons: POST_CANT
POST_CANT = "I can't make a post for {id} right now. Nothing was posted."
_NUM = r"[-+]?[0-9.][0-9.,_]*(?:e[-+]?[0-9]+)?"  # AV1102-12: looks like a number; margins.compute is the only validator
MARGIN_RE = re.compile(rf"\$?({_NUM})\s+for\s+({_NUM})\s+at\s+({_NUM})\s*%(?:\s+shrink\s+({_NUM})\s*%)?")
MARGIN_ID_RE = re.compile(rf"(?!\$?{_NUM}\s+for\s)(\S.*?)\s+at\s+({_NUM})\s*%(?:\s+shrink\s+({_NUM})\s*%)?")  # AV1222-10: saved cost
COST_RE = re.compile(r"\$?(\S+)\s+for\s+(\S+)", re.IGNORECASE)  # AV1222-10: margins.compute is the only number validator
COST_USAGE = "Tell me the product, what you pay for a pack and how many are in it, like " + q("cost Hass avocado: 24 for 12") + "."
PRIVATE_PREFIXES = ("alias.", "cost.")  # AV1222-10: memory keys the interpreter never sees
MARGIN_USAGE = "Tell me what you pay for a pack, how many are in it and the margin you want, like " + q("margin 24 for 12 at 35%") + "."
PAUSED_LINE = "Changes are paused, so nothing will be saved yet. Say " + q("resume changes") + " first, then yes."
ATTACHMENT_REPLY = ("I can't read photos, voice notes or files yet, so nothing changed. "
                    "Could you type the change instead?")
NOT_READ_REPLY = ("I only notice new messages, so I missed that tap or edit and nothing changed. "
                  "Please send yes, no or the change as a new message.")  # AV1737-03 (H08/H17): owner reaction or edit
PHOTO_QUESTION = "Which product is this photo for, and what does it show? A few words is fine."  # NB-AV-09 (H12): asked by every new photo draft
PHOTO_PATH_RE = re.compile(r"assets/products/photo-[0-9a-f]{16}\.(jpg|png)")
PHOTO_OPS = ("product.set_photo", "product.add")  # AV0022-04: ops in a photo-draft answer that get the draft's photo
FETCH_FAILED = "I couldn't get that photo after trying three times, so nothing changed. Could you send it again?"
# H17 pause flag. Created by the first `pause` (not in SCHEMA) so the H05 store keeps its four tables until then.
CONTROL = """CREATE TABLE IF NOT EXISTS control(name TEXT PRIMARY KEY, value TEXT NOT NULL, set_at TEXT NOT NULL,
  provider_id TEXT NOT NULL)"""
USAGE = "CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY, calls INTEGER NOT NULL)"  # H22; lazy like CONTROL
# HASS-INTERP-OPENAI-1: which backend answered each message. Lazy like CONTROL; written only for an interpreter that names its
# backend. Short codes and seconds only: never the owner's text, the prompt, a URL or a model reply.
AUDIT = """CREATE TABLE IF NOT EXISTS interpreter_audit(provider_id TEXT PRIMARY KEY, at TEXT NOT NULL, backend TEXT NOT NULL,
  fallback INTEGER NOT NULL, primary_error TEXT, error TEXT, seconds REAL)"""
DAILY_LIMIT = ("I've read as many new requests as I can for today, so I couldn't read that one and nothing changed. "
               "Yes, no, undo and status still work. Please send it again tomorrow.")
MAX_OWNER_TEXT = 4000  # AV1737-04 (H05/H22): twice the longest field limit (recap 2000); test_owner_text_cap checks it
MAX_INTERPRETER_ALIASES = 50  # AV0007-06: live owner aliases the interpreter sees (newest first)
MAX_NOTES = 20  # AV1102-09: saved notes the interpreter sees (newest first)
TOO_LONG = "That message is too long for me to read, so nothing changed. Could you send a shorter one?"
OPS_PENDING_MAX = 4096  # AV0022-03: bytes of a draft's ops_json sent in `pending`; larger -> "opsOmitted": true
TRANSITIONS = {"needs-details": {"proposed", "rejected", "expired"}, "proposed": {"approved", "rejected", "expired"},
               "approved": {"applied", "failed", "rejected"}, "applied": {"verified", "reverted"},
               "verified": {"reverted"}}
INTERRUPTED = "interrupted; not applied; approve a new draft"
NOTHING = "Nothing is waiting for your yes."
SOCIAL_REPLY = "Nothing changed. Tell me what you'd like to change, or say " + q("help") + "."  # AV0007-07
CANT_READ = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"
UNREADABLE = {"unsupported": "Sorry, I didn't understand that. Could you say it another way?"}
VALUE_CUT = 120
HOSTILE_RE = re.compile(r"\b(?:ignore|disregard|forget|override|bypass)\b[^.!?]{0,40}\b(?:rules|instructions|guidelines|approval|safeguards?|previous|above)\b"
                        r"|\b(?:publish|approve|apply|post)\s+(?:everything|all\s+(?:of\s+)?(?:it|changes|drafts))\b|\bskip\s+(?:the\s+)?approvals?\b"
                        r"|\b(?:system|developer)\s+prompt\b|\bjailbreak\b|\bact\s+as\b[^.!?]{0,30}\b(?:admin|root|developer)\b", re.I)
HOSTILE_REPLY = "I can only publish changes you approve one at a time. Nothing was changed."  # HASS-VOICE-1: no model call, no draft
CORRECTION_RE = re.compile(r"(?:no[,.!]|nope|that'?s (?:wrong|not right|not what)|not what i (?:meant|said|asked)|wrong\b|i didn'?t (?:mean|ask|say)|you got (?:it|that) wrong)", re.I)
RECENT_MINUTES, RECENT_MAX = 30, 500  # HASS-NL-1: how long our last question stays open for a short answer; longest kept
# HASS-HIKE-FLOW-1: the open request. While a question of ours is open, the owner's texts of that request are kept (this
# private store only) so the short answer is read with the request it answers. Gone after RECENT_MINUTES, when a draft or
# a new question outcome closes it, or on `no`; never more than the last ASK_TURNS texts and ASK_CHARS characters.
# SKILLS-FW-3: that store is hass/skills/openreq.py (table open_requests); a pre-FW-3 table open_asks is migrated into it.
# HASS-SHELFCHECK-FLOW-1: the same open request also carries the change Hass could not draft yet (pending_json), when the
# only thing missing was today's shelf check. Plain words only: no "selection", no "not drafted", no ids.
SHELF_ASK = "Is the shelf list right for today? Reply yes if it is, or tell me what is different."
SHELF_QUESTION = "Before I change that, " + SHELF_ASK[0].lower() + SHELF_ASK[1:]
SHELF_NO = "Okay, nothing was changed. Tell me what is different on the shelf list and I will draft that."
SHELF_FAILED = "Sorry, I could not set that up, so nothing was changed. Please send the change again."
SHELF_CLOCK = "The last shelf check is dated in the future, so the date on this phone or computer looks wrong. Nothing was changed."
MEET_NO = "Okay. Where should people meet? Tell me the spot, like a trailhead or a parking lot."  # HASS-CHAT-1
# HASS-CHAT-1 (C): a proposal whose picture could not be drawn is never silent; the picture is tried once more a bit later
PREVIEW_FAILED_HEAD = "I could not draw the picture right now; here is exactly what will change:"
PREVIEW_RETRY_LINE = "I'll try the picture again in a moment."
PREVIEW_RETRY_SECONDS = 30
PREVIEW_LATER = "Here is the picture of how {what} will look."
PREVIEW_STILL_FAILED = "I still couldn't draw the picture for {what}. The change I listed is exactly what will happen."
ASK_TURNS, ASK_CHARS, ASK_TEXT_CUT = 4, 2000, 1000
LATE_AFTER = timedelta(minutes=15)  # AV0022-10 (H16): a reply sent this much after the message it answers says so
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DELAYED_AFTER_S = 600  # AVB-07 (H16): an outbox reply older than this at send time is marked delayed
# HASS-SEC-2 (L5): a yes counts only when it reached the inbox within approvalTtlSeconds plus this of when it was sent (the
# envelope clock window is 300 s, so a yes forwarded at once is always inside it).
LATE_FORWARD_S = 300
LATE_YES_REPLY = ("Your yes reached me long after you sent it, so I haven't saved anything. "
                  "If you still want that change, tell me again.")
VERIFY_MAX = 5  # AV1737-08 (H06): result check captures at most this many distinct touched records
SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(provider_id TEXT PRIMARY KEY, disposition TEXT NOT NULL, received_at TEXT);
CREATE TABLE IF NOT EXISTS message_chats(provider_id TEXT PRIMARY KEY, chat TEXT NOT NULL);  -- HASS-LIVE-PLAN-1: which owner chat a message came from
CREATE TABLE IF NOT EXISTS drafts(row_id INTEGER PRIMARY KEY, change_id TEXT, code TEXT NOT NULL, state TEXT NOT NULL,
  reason TEXT, replaced_by TEXT, draft_hash TEXT, base TEXT, ops_json TEXT NOT NULL, summary TEXT NOT NULL,
  sender TEXT NOT NULL, chat TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT, "commit" TEXT,
  screenshot TEXT, checked_at TEXT, proposed_at TEXT, missing_json TEXT);
CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY, sender TEXT NOT NULL, chat TEXT NOT NULL,
  provider_id TEXT NOT NULL, change_id TEXT NOT NULL, draft_hash TEXT NOT NULL, base TEXT NOT NULL,
  expires_at TEXT NOT NULL, approved_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, chat TEXT NOT NULL, text TEXT NOT NULL,
  attachments TEXT NOT NULL, created_at TEXT NOT NULL, sent_at TEXT, reply_to TEXT);
"""


class ConfigError(Exception): """ownerSenders, ownerChat or approvalTtlSeconds is missing or invalid; nothing starts."""


class TransitionError(Exception): """A draft state change outside the allowed transitions."""


class AttachmentPending(Exception): """NB-AV-11 (H16): the photo could not be fetched yet; nothing was recorded."""


class _Held(Exception):
    """handle(apply=False): an owner approval that must roll back unapplied."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


HELD_REPLY = "I can't save changes yet, because I'm not fully connected. Your change is still waiting for you."  # {code} is not shown


@dataclass(frozen=True)
class Inbound:
    provider_id: str
    chat: str
    sender: str
    text: str
    from_me: bool = False
    kind: str = "new"  # new | edited
    received_at: str = ""
    attachments: int = 0  # H12: count only; nothing about the files is kept or downloaded


class Editor:
    """The A2 editor bound to one state dir (production op registry unless a test registry is given)."""

    def __init__(self, state, registry=None):
        self.state, self.registry = str(state), registry

    def prepare(self, ops):
        return editor_mod.prepare({"ops": ops}, state=self.state, registry=self.registry)

    routes_chat = False  # True on an editor that records which owner chat approved (LiveEditor); fixtures keep two arguments

    def apply(self, change_id, draft_hash):
        return editor_mod.apply(change_id, draft_hash, state=self.state, registry=self.registry)

    def show(self, change_id):
        return editor_mod.show(change_id, state=self.state)

    def recover(self):
        return editor_mod.recover(state=self.state)

    def render_draft(self, change_id):
        return editor_mod.render_draft(change_id, state=self.state, registry=self.registry)


class FixtureInterpreter:
    """Maps exact message text to an interpreter result; anything else is unsupported. No model, no network."""

    def __init__(self, mapping):
        self.mapping = dict(mapping)

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        return copy.deepcopy(self.mapping.get(text, {"unsupported": "Sorry, I can't do that yet."}))


class Outbox:
    """Replies stored in the same transaction as the result; flush() sends them in order and marks each sent."""

    log = None  # HASS-VOICE-1: a corrlog.CorrLog (set by Conversation); None logs nothing
    strict = os.environ.get("HASS_VOICE_STRICT") == "1"  # tests and CI: a message that breaks a voice rule raises
    msg_id = None  # provider id of the owner message being answered (for the correspondence log)
    emoji_ok = False  # the owner used an emoji first
    private_chat = None  # HASS-VOICE-1: G's own chat (set by Conversation); a reply there that cannot be sent never blocks the owner's

    def __init__(self, db, now):
        self.db, self._now = db, now

    def clean(self, text, long_ok=False, ids_ok=False, why="reply") -> str:
        """HASS-VOICE-1: the text to store: a message that breaks a voice rule becomes voice.SAFE_LINE and is logged."""
        broken = voice.check(text, emoji_ok=self.emoji_ok, long_ok=long_ok, ids_ok=ids_ok)
        if not broken: return voice.plain(text)
        if self.strict: raise voice.VoiceError(f"{'; '.join(broken)}: {voice.plain(text)!r}")
        if self.log: self.log.record("voice-fallback", "breaks-" + re.sub(r"[^a-z0-9]+", "-", broken[0].lower()).strip("-")[:30],
                                     msg=self.msg_id)
        return voice.SAFE_LINE

    def add(self, chat, text, attachments=(), reply_to=None, *, long_ok=False, ids_ok=False):
        text = self.clean(text, long_ok, ids_ok)
        self.db.execute("INSERT INTO outbox(chat, text, attachments, created_at, reply_to) VALUES (?, ?, ?, ?, ?)",
                        (chat, text, json.dumps(list(attachments)), _iso(self._now()), reply_to))

    def unsent(self):
        return self.db.execute("SELECT * FROM outbox WHERE sent_at IS NULL ORDER BY id").fetchall()

    def flush(self, adapter) -> int:
        """A raised send error propagates and leaves that row and every later row unsent, except a private row (G's chat):
        if that cannot be sent it is dropped and logged, so it never holds up an owner reply."""
        sent = 0
        for row in self.unsent():
            head = self._late(row["reply_to"]) or self._delayed(row["created_at"])  # the longer wait is the one named
            try: adapter.send(row["chat"], head + row["text"], json.loads(row["attachments"]))
            except Exception:
                if row["chat"] != self.private_chat or self.private_chat is None: raise
                self.db.execute("DELETE FROM outbox WHERE id = ?", (row["id"],))
                if self.log: self.log.record("error", "g-reply-not-sent")
                continue
            self.db.execute("UPDATE outbox SET sent_at = ? WHERE id = ?", (_iso(self._now()), row["id"]))
            self._slow(row)
            sent += 1
        return sent

    def _slow(self, row):
        """HASS-VOICE-1: a reply that left more than corrlog.SLOW_SECONDS after the message it answers is a problem moment."""
        if not self.log: return
        try: seconds = (self._now() - datetime.fromisoformat(row["reply_to"])).total_seconds()
        except (TypeError, ValueError): return
        if seconds > corrlog.SLOW_SECONDS: self.log.record("slow", "reply-over-20s", reply=row["id"], seconds=seconds)

    def _late(self, reply_to) -> str:
        """AV0022-10 (H16): send-time heading naming the owner message a reply answers, when sent over LATE_AFTER
        after it (older than 6 days: its date); empty, naive, bad or future -> ''. The stored text never changes."""
        try: sent, now = datetime.fromisoformat(reply_to), self._now()
        except (TypeError, ValueError): return ""
        if sent.tzinfo is None or now - sent <= LATE_AFTER: return ""
        return f"Sorry for the wait. This answers your message from {voice.natural(sent, now)}:\n"

    def _delayed(self, created_at) -> str:
        """AVB-07 (H16): send-time prefix for a reply held over DELAYED_AFTER_S; bad, naive or future -> ''."""
        try: age = (self._now() - datetime.fromisoformat(created_at)).total_seconds()
        except (TypeError, ValueError): return ""
        return "Sorry for the wait. " if age > DELAYED_AFTER_S else ""


def _row_chat(row):
    """The owner chat a draft row belongs to; None (the owner chat) for a row that does not say."""
    try: return row["chat"]
    except (KeyError, IndexError, TypeError): return None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _pending_ops(ops_json) -> dict:  # AV0022-03 (H05): a waiting draft's ops; too large or unreadable -> opsOmitted
    try: ops = json.loads(ops_json) if len(ops_json.encode()) <= OPS_PENDING_MAX else None
    except (TypeError, ValueError, AttributeError, RecursionError): ops = None
    return {"ops": ops} if isinstance(ops, list) else {"opsOmitted": True}


def _missing_ids(missing_json) -> list:  # AV0007-03: stored argument ids of a question; anything unreadable -> []
    try: ids = json.loads(missing_json) if missing_json else []
    except (TypeError, ValueError, RecursionError): return []
    out = []
    for i in ids if isinstance(ids, list) else []:
        if not isinstance(i, str): return []
        if i and i not in out: out.append(i)
    return out


def _answered_at(msg, now: datetime) -> datetime:
    """AV0022-06 (H16): when the owner sent the reply (received_at); empty, naive, bad or future -> now."""
    try: sent = datetime.fromisoformat(msg.received_at or "")
    except (TypeError, ValueError): return now
    return sent if sent.tzinfo is not None and sent <= now else now


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")


def _hike_time(iso):  # AV1737-07 (H04/H05): `Sat 2026-11-07 09:00 PST`; a bad or naive value is shown raw, never raised
    try: start = datetime.fromisoformat(iso)
    except (ValueError, TypeError): return iso
    return iso if start.tzinfo is None else start.astimezone(LOCAL_TZ).strftime("%a %Y-%m-%d %H:%M %Z")


def sender_key(value):
    """AV2022-08 (H08): an email (casefolded) or `+` and 8-15 digits (spaces, dashes, dots, brackets dropped); else None."""
    if not isinstance(value, str): return None
    value = value.strip()
    if re.fullmatch(r"\+[0-9 .()-]+", value):
        digits = re.sub(r"[^0-9]", "", value)
        return "+" + digits if 8 <= len(digits) <= 15 else None
    local, at, domain = value.partition("@")
    ok = at and local and "@" not in domain and "." in domain and not re.search(r"\s", value)
    return value.casefold() if ok else None


MAX_CONFIG = 1024 * 1024  # RF1910-2 (H08/H20)
MAX_OWNER_CHATS = 8  # HASS-OWNERS-2: the most owner chats one config may name


def _config_bytes(sdir):
    """RF1910-2: config.json bytes from a regular, non-link file <= 1 MiB; None when missing; else ConfigError."""
    path, bad = Path(sdir) / "config.json", ConfigError("config.json must be a regular file up to 1 MiB")
    try: st = os.lstat(path)
    except FileNotFoundError: return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_CONFIG: raise bad  # link, FIFO, folder, too big: never opened
    with open(path, "rb") as fh: data = fh.read(MAX_CONFIG + 1)
    if len(data) > MAX_CONFIG: raise bad  # grew past the cap after lstat; the reason names no path or content
    return data


def load_settings(sdir, photos=False) -> dict:
    try:
        data = _config_bytes(sdir)
        settings = None if data is None else json.loads(data.decode("utf-8")).get("settings")
    except (OSError, ValueError, AttributeError, RecursionError, UnicodeDecodeError):
        settings = None
    if not isinstance(settings, dict): raise ConfigError("config.json settings are missing")
    senders, chat, ttl = (settings.get(k) for k in ("ownerSenders", "ownerChat", "approvalTtlSeconds"))
    problems = []
    chats_in = settings.get("ownerChats")  # HASS-OWNERS-2: optional list; with it, ownerChat (if also set) is one of its entries
    keys = [sender_key(s) for s in senders] if isinstance(senders, list) else []
    if not keys: problems.append("ownerSenders must be a non-empty list of sender addresses")
    problems += [f"ownerSenders entry {n} is not an email address or a +country phone number"  # value never echoed
                 for n, key in enumerate(keys, 1) if key is None]
    if chats_in is not None: pass  # HASS-OWNERS-2: every entry is checked below, and ownerChat must be one of them
    elif not isinstance(chat, str) or not chat.strip(): problems.append("ownerChat must be a chat id")
    elif ";+;" in chat:  # AVB-02 (H08): the owner channel is the owner's one-to-one chat, never a group; ids never echoed
        problems.append("ownerChat is a group chat; it must be the owner's one-to-one chat")
    elif (direct := re.fullmatch(r"[^;]+;-;([^;]+)", chat)) and sender_key(direct[1]) not in keys:
        problems.append("ownerChat is a one-to-one chat with an address that is not in ownerSenders")
    chats, chat_keys, names, before = None, {}, {}, len(problems)
    if chats_in is not None:  # HASS-OWNERS-2: several owners, each in their own one-to-one chat; ids and addresses never echoed
        if not isinstance(chats_in, list) or not 1 <= len(chats_in) <= MAX_OWNER_CHATS:
            problems.append(f"ownerChats must be a list of 1 to {MAX_OWNER_CHATS} chat ids")
        else:
            for n, c in enumerate(chats_in, 1):
                direct = re.fullmatch(r"[^;]+;-;([^;]+)", c) if isinstance(c, str) else None
                if not isinstance(c, str) or not c.strip(): problems.append(f"ownerChats entry {n} must be a chat id")
                elif ";+;" in c: problems.append(f"ownerChats entry {n} is a group chat; it must be an owner's one-to-one chat")
                elif not direct: problems.append(f"ownerChats entry {n} must be a one-to-one chat id like iMessage;-;<address>")
                elif sender_key(direct[1]) not in keys: problems.append(f"ownerChats entry {n} is a one-to-one chat with an address that is not in ownerSenders")
                else: chat_keys[c] = frozenset({sender_key(direct[1])})
            strs = [c for c in chats_in if isinstance(c, str)]  # a {} or [] entry is already reported above and is never hashed
            if len(set(strs)) != len(strs): problems.append("ownerChats has the same chat twice")
            if chat is not None and chat not in chats_in: problems.append("ownerChat must be one of ownerChats")
            if len(problems) == before: chats, chat = tuple(chats_in), chat or chats_in[0]  # no ownerChat: the first owner chat is the main one
    n_in = settings.get("ownerNames")  # HASS-OWNERS-2: optional {chat id: short first name}, used only to say whose change it was
    if n_in is not None:
        if not isinstance(n_in, dict) or chats is None or any(k not in chats for k in n_in) or not all(
                isinstance(v, str) and re.fullmatch(r"[^\W\d_][^\W\d_ '.-]{0,19}", v) for v in n_in.values()):
            problems.append("ownerNames must map an ownerChats chat id to a short first name (letters only, up to 20)")
        else: names = dict(n_in)
    if type(ttl) is not int or ttl < 60: problems.append("approvalTtlSeconds must be an integer >= 60")
    root = settings.get("mediaRoot")  # NB-AV-09: required only with a photo source
    if photos and (not isinstance(root, str) or not root.strip()): problems.append("mediaRoot must be set to use photos")
    cap = settings.get("interpreterDailyCap")  # H22: optional; absent or null means no cap (no default enables it)
    if cap is not None and (type(cap) is not int or not 1 <= cap <= 10000):
        problems.append("interpreterDailyCap must be an integer 1-10000")
    g_senders = settings.get("gSenders")  # HASS-VOICE-1: optional; only these numbers may ask for `problems` (never an owner number)
    g_keys = [sender_key(g) for g in g_senders] if isinstance(g_senders, list) else []
    if g_senders is not None and (not isinstance(g_senders, list) or None in g_keys or set(g_keys) & set(keys)):
        problems.append("gSenders must be a list of sender addresses that are not owner senders")
    g_chat = settings.get("gChat")  # HASS-VOICE-1: G's own one-to-one chat; the only place `problems` and `weekly` are answered
    if g_keys and g_senders is not None:
        if not isinstance(g_chat, str) or not g_chat.strip(): problems.append("gChat must be set to G's own chat when gSenders is set")
        elif g_chat == chat or chats is not None and g_chat in chats: problems.append("gChat must not be the owner chat")
        elif ";+;" in g_chat: problems.append("gChat is a group chat; it must be G's one-to-one chat")
        elif (direct := re.fullmatch(r"[^;]+;-;([^;]+)", g_chat)) and sender_key(direct[1]) not in g_keys:
            problems.append("gChat is a one-to-one chat with an address that is not in gSenders")
    elif g_chat is not None: problems.append("gChat needs gSenders")
    g_owner = settings.get("gIsOwner", False)  # HASS-LIVE-PLAN-1: G's own chat is a second owner chat (text only)
    if type(g_owner) is not bool or g_owner and not (g_keys and isinstance(g_chat, str)): problems.append("gIsOwner must be true or false, and true needs gSenders and gChat")
    site, needs_code = settings.get("liveSite"), settings.get("approvalNeedsCode", False)
    if site is not None and (not isinstance(site, str) or not re.fullmatch(r"[a-z0-9.-]{3,253}", site) or "." not in site):
        problems.append("liveSite must be a hostname")
    if type(needs_code) is not bool or site is not None and needs_code is not True:
        problems.append("approvalNeedsCode must be a bool and true with liveSite")
    skills = settings.get("skills")  # SKILLS-FW-3: {"mode": ops-only | both | skills-first} (or the flat key "skills.mode"); absent = ops-only
    mode = settings.get("skills.mode", dispatch_mod.DEFAULT_MODE) if skills is None else skills.get("mode", dispatch_mod.DEFAULT_MODE) if isinstance(skills, dict) else None
    if mode not in dispatch_mod.MODES: problems.append("skills.mode must be ops-only, both or skills-first")
    house = settings.get("houseRender", False)  # SKILLS-FW-3: read here, used by the picture card (SKILLS-PIC-1); default off
    if type(house) is not bool: problems.append("houseRender must be true or false")
    if problems: raise ConfigError("; ".join(problems))
    return {"ownerSenders": tuple(senders), "ownerKeys": frozenset(keys), "ownerChat": chat, "approvalTtlSeconds": ttl,
            "mediaRoot": root, "guestCountsDb": settings.get("guestCountsDb"),  # guestCountsDb: H17, unchecked
            "interpreterDailyCap": cap, "skillsMode": mode, "houseRender": house,  # SKILLS-FW-3
            **({k: settings[k] for k in ("liveSite", "approvalNeedsCode") if k in settings}),
            **({"gKeys": frozenset(g_keys), "gChat": g_chat, "gSenders": tuple(g_senders)} if g_keys and isinstance(g_chat, str) else {}),
            **({"gOwner": True} if g_owner is True else {}),
            **({"ownerChats": chats, "chatKeys": chat_keys, "ownerNames": names} if chats is not None else {})}  # HASS-OWNERS-2: only when set


def parse_keyword(text: str):
    """(verb, code or None) when the whole message is an approval keyword; otherwise None."""
    match = KEYWORD_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()))
    if not match: return None
    return ("approve" if match[1] in APPROVE else "reject"), match[2]


COURTESY = {"please", "thanks", "ok", "okay"}


def parse_phone(text: str):
    """AV1352-04 (H05): (verb or None, code or None, question) when, after dropping punctuation other than ?, emoji and
    the courtesy words (please, thanks, thank you, ok, okay), the whole message is one approve/cancel word and one code in
    either order, or one code alone, or (with a ?) one such word alone; otherwise None. `question` is True when the
    original text held a ?. Only the candidate is normalised, never the message; a ? is never stripped into an answer."""
    question = "?" in text
    words = "".join(c if c.isalnum() else " " for c in text.lower()).split()
    kept, i = [], 0
    while i < len(words):
        if words[i] == "thank" and words[i + 1:i + 2] == ["you"]: i += 2
        else:
            if words[i] not in COURTESY: kept.append(words[i])
            i += 1
    verbs = [w for w in kept if w in APPROVE or w in REJECT]
    codes = [w for w in kept if re.fullmatch(r"[0-9a-f]{4,12}", w)]
    if not kept or len(verbs) + len(codes) != len(kept) or len(verbs) > 1 or len(codes) > 1: return None
    if not verbs: return None, codes[0], question  # a lone code is only ever a hint
    if not codes and not question: return None  # courtesy never makes a new bare yes/no
    return ("approve" if verbs[0] in APPROVE else "reject"), (codes[0] if codes else None), question


def parse_near(text: str):
    """AV2022-07 (H05): code or "" when the whole message is a casual yes (ok, go ahead, ...); otherwise None.
    It never approves anything; Hass only answers with the exact `yes <code>` to send."""
    match = NEAR_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()).removesuffix(","))
    return None if not match else match[2] or ""


def parse_command(text: str, *, listing_names=False):
    """("undo", code or None) or (history|status|pause|resume|help, None) when the whole message is that command;
    otherwise None."""
    match = COMMAND_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()))
    if not match: return None
    if match[21]: return "backlog", None  # SKILLS-FW-3
    if match[20]: return "photos", None  # AV0222-04
    if match[1]:  # AV2152-02: bare history stays (history, None); history <words> keeps the words in their own case
        stripped = re.sub(r"[.!]+$", "", text.strip())
        if stripped.lower() != "history": return "history", stripped[7:].strip()
    if match[18]:
        ident = re.sub(r"[.!]+$", "", text.strip())[7:].strip() if match[19] else ""
        # Several words need a catalog check in the message flow, not just a syntax match.
        return ("listing", ident) if listing_names or len(ident.split()) <= 1 else None
    if match[17]: return "hidden", None  # AV1222-13
    if match[15]: return "margin", match[16] or ""  # AV1102-12 (F03)
    if match[13]: return "post", re.sub(r"[.!]+$", "", text.strip())[4:].strip() if match[14] else ""  # AV1322-07: the id in its own case
    if match[12]: return "report", None  # AV1322-05 (F04)
    if match[10]: return "show", match[11] or ""  # AV0022-08: the code is checked by _show, never guessed
    if match[7]: return "help", None
    if match[8]: return "find", re.sub(r"[.!]+$", "", text.strip())[4:].strip()  # ("find", query in its own case)
    if match[2]: return "undo", match[3]
    found = next(v for v in (match[1], match[4], match[5], match[6]) if v)  # SHOP-4: did it work = status, stop = pause
    return ("status" if found.startswith("did ") else "pause" if found == "stop" else found), None


def _note_key(name: str) -> str:
    """AV1352-07: a note name as typed: trimmed, lower-cased, runs of spaces become one \"-\" (KEY_RE still decides)."""
    return re.sub(" +", "-", name.strip().lower())


def parse_memory(text: str):
    """("remember", key, text), ("forget", key, None) or ("memory", None, None) when the whole message is an H15
    memory command; otherwise None. `remember …` without `key:` still parses (as an empty text) so it is refused."""
    match = MEMORY_RE.fullmatch(text.strip())
    if match and match[1]:
        key, colon, value = (match[2] or "").partition(":")
        return "remember", _note_key(key), value.strip() if colon else ""
    if match and match[6]:  # ("alias", name, product id or maker key); a missing part is refused, not guessed
        name, colon, ident = (match[7] or "").partition(":")
        return "alias", name.strip(), ident.strip() if colon else ""
    if match and match[8]:  # AV1222-10 ("cost", product id, "<pack> for <units>"); a bad part is refused, not guessed
        ident, colon, rest = (match[9] or "").partition(":")
        return "cost", ident.strip().lower(), rest.strip() if colon else ""
    match = MEMORY_RE.fullmatch(re.sub(r"!+$", "", text.strip()))  # a key may end in "." (KEY_RE), never "!"
    if match and match[3]:  # AV1352-07: spaces in a note name become "-"; `forget alias <name>` removes alias.<name>
        operand = match[4].strip()
        if re.search(r"[^\S ]", operand) or re.fullmatch(r"it +all", operand, re.IGNORECASE): return None  # old routing
        if re.match(r"alias +\S", operand, re.IGNORECASE):
            name = operand[5:].strip()
            ok = memory_mod._clean(name) and len(name) <= ALIAS_NAME_MAX
            if not ok: return "forget", "alias. " + name.lower(), None
            return "forget", "alias." + catalog._fold(name).replace(" ", "-"), "spaced"  # may also be the note alias-<name>
        return "forget", _note_key(operand), None
    match = MEMORY_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip()))
    return ("memory", None, None) if match and match[5] else None


READ_ONLY = {"history", "status", "help", "find", "show", "report", "post", "margin", "hidden", "listing", "backlog"}


def _asked(text: str):
    """AV1352-05 (H17): the message without its closing run of . ! ? when that run holds a ?, else None."""
    cut = re.sub(r"[.!?]+$", "", text.strip())
    return cut if cut != text.strip() and "?" in text.strip()[len(cut):] else None


def read_command(text: str, *, listing_names=False):
    """AV1352-05 (H17): parse_command, but a closing ? is dropped for a read-only command only (never yes/no, undo, stop,
    resume); anything else keeps today's reading of the original text."""
    cut = _asked(text)
    found = parse_command(cut, listing_names=listing_names) if cut else None
    return found if found and found[0] in READ_ONLY else parse_command(text, listing_names=listing_names)


def read_memory(text: str):
    """AV1352-05 (H17): `memory?` lists notes; remember, forget and alias never see a stripped text."""
    cut = _asked(text)
    found = parse_memory(cut) if cut else None
    return found if found and found[0] == "memory" else parse_memory(text)


def _checked(result) -> dict:
    if isinstance(result, dict):
        if set(result) == {"ops", "revises"} and isinstance(result["ops"], list) \
                and (result["revises"] is None or isinstance(result["revises"], str)):
            return result
        for key in ("question", "unsupported"):
            if set(result) == {key} and isinstance(result[key], str) and result[key].strip(): return result
    return dict(UNREADABLE)


def _reason(out: dict) -> str:
    return out.get("reason") or "; ".join(out.get("problems") or []) or out.get("question") or str(out.get("result"))


def _is_undo(row) -> bool:
    """AV0022-07 (H06): the draft's ops are a non-empty list of only history.revert calls; unparsable is not an undo."""
    try: ops = json.loads(row["ops_json"])
    except (TypeError, ValueError, RecursionError): return False
    return isinstance(ops, list) and bool(ops) and all(isinstance(c, dict) and c.get("op") == "history.revert" for c in ops)


def _value(v) -> str:
    text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, dict) else voice.value_words(v)
    return text if len(text) <= VALUE_CUT else text[:VALUE_CUT - 3] + "..."


def _full(v) -> str:
    """AV1537-06 (H05): a proposal's new value uncut (TEXT_LIMITS bound it); a list of strings joins with "; ".
    Anything else (None, numbers, whole JSON records) keeps the _value cut."""
    if isinstance(v, list) and v and all(isinstance(i, str) for i in v): return "; ".join(v)
    return v if isinstance(v, str) else _value(v)


def _changes(record: dict):
    before, after = record.get("before"), record.get("after")
    if isinstance(before, dict) and isinstance(after, dict):
        return [(k, before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
    return [("record", before, after)]


COLLECTION_WORDS = {"products": "product", "makers": "maker", "events": "hike", "routeIdeas": "route idea"}
WHOLE_WORDS = {"store": "the shop details", "home": "the home page"}


def _name(record: dict):
    """The record's own name or title as the shop writes it (spacing folded), or None."""
    for side in (record.get("before"), record.get("after")):
        for key in ("name", "title"):
            if isinstance(side, dict) and isinstance(side.get(key), str) and side[key].strip(): return " ".join(side[key].split())
    return record.get("key") if record.get("collection") == "makers" and isinstance(record.get("key"), str) else None


def _subject(record: dict) -> str:
    """Who or what a change is about, for Mike: the name he knows (marked as his words) or the part of the shop."""
    name = _name(record)
    return q(name) if name else WHOLE_WORDS.get(record.get("collection"), "this")


def _summary(draft: dict) -> str:
    """One plain phrase for a draft, stored with it and shown in status and history: `the description for Hass avocado`."""
    parts = []
    for r in draft["records"]:
        name, word = _name(r), COLLECTION_WORDS.get(r.get("collection"), "")
        if r.get("before") is None and isinstance(r.get("after"), dict):
            parts.append(f"a new {word or 'entry'}" + (f": {name}" if name else ""))
            continue
        if _removed(r):
            parts.append(f"taking away the {word or 'entry'}" + (f": {name}" if name else ""))
            continue
        fields = list(dict.fromkeys(voice.field_phrase(f) for f, _b, _a in _changes(r)))
        what = ", ".join(fields[:3]) + (" and more" if len(fields) > 3 else "")
        parts.append(f"{what} for {name or WHOLE_WORDS.get(r.get('collection'), 'this')}")
    return _value("; ".join(parts) or "no changes")


def _when(field, value):
    """A start or end time is written as a day and time; any other value is None here."""
    return voice.natural_iso(value) if field in ("startsAt", "endsAt") and isinstance(value, str) else None


def _shown(field, v, cut=True) -> str:
    """A stored value in Mike's words (a time as a day and time, yes/no, status words); long text is cut unless cut is False."""
    if v is None: return "nothing"
    if (w := _when(field, v)): return w
    if isinstance(v, str) and field != "status": return v if not cut or len(v) <= VALUE_CUT else v[:VALUE_CUT - 3] + "..."
    return voice.value_words(v, field)


UNREADABLE_TIME = voice.natural_iso("soon")  # the words voice gives a time it cannot read
EVENT_ORDER = ("title", "startsAt", "meetingPoint", "trailId", "description", "difficulty", "distance", "duration", "bring",
               "accessNote", "rsvpEnabled", "capacity")  # HASS-CHAT-1: a new hike reads name, when, where first


def _shown_in(r: dict, k, v, routes=None, cut=True) -> str:
    """HASS-CHAT-1: _shown for one record: a hike's start says its time zone, and a route link is the route's name, never its id."""
    if k == "trailId" and isinstance(v, str):
        route = (routes or {}).get(v)
        return route["title"] if isinstance(route, dict) and isinstance(route.get("title"), str) and route["title"].strip() else "a saved route"
    shown = _shown(k, v, cut)
    return shown + " (Pacific time)" if r.get("collection") == "events" and k == "startsAt" and _when(k, v) and \
        isinstance(v, str) and _when(k, v) != UNREADABLE_TIME else shown


def _added(r: dict, routes=None) -> list:  # AV1737-06 (H05/H06): an added record's visible fields, one per line (at most 40)
    rows = [(k, v) for k, v in sorted(r["after"].items()) if v not in (None, "", []) and k not in voice.SKIP_FIELDS and k in voice.FIELDS]
    if r.get("collection") == "events":  # HASS-CHAT-1: name, when, where first; a new hike is scheduled, so that line says nothing
        rank = {k: i for i, k in enumerate(EVENT_ORDER)}
        rows = sorted((kv for kv in rows if kv != ("status", "scheduled")), key=lambda kv: (rank.get(kv[0], len(rank)), kv[0]))
    word, name = COLLECTION_WORDS.get(r.get("collection"), "entry"), _name(r)
    lines = [f"A new {word}" + (f": {q(name)}" if name else "")]
    for k, v in rows[:40]:
        photo = k == "image" and PHOTO_PATH_RE.fullmatch(str(v))
        lines.append(f"  {voice.field_phrase(k)}: " + ("the photo from your message" if photo else q(_shown_in(r, k, v, routes, False)).replace("\n", "\n    ")))
    return lines + (["  and a few more details"] if len(rows) > 40 else [])


def _change_line(r: dict, field, b, a, undo: bool, full_before: bool, routes=None) -> str:
    who, phrase = _subject(r), voice.field_phrase(field)
    if field == "image" and (PHOTO_PATH_RE.fullmatch(str(a)) or undo and PHOTO_PATH_RE.fullmatch(str(b))):
        return f"{who}: the photo goes back to the previous one" if undo else f"{who}: the photo will be the one from your message"
    old, new = _shown_in(r, field, b, routes, not full_before), _shown_in(r, field, a, routes, False)
    if "\n" in new or "\n" in old or len(old) + len(new) > 70:
        return f"{who}, {phrase}:\n  was: " + q(old).replace("\n", "\n    ") + "\n  now: " + q(new).replace("\n", "\n    ")
    return f"{who}, {phrase}: from {q(old)} to {q(new)}"


def _removed(r: dict) -> bool:
    return isinstance(r.get("before"), dict) and r.get("after") is None


def _removal(r: dict, done: bool = False) -> str:
    """A whole record going away (an undo of something added) is said as that, never as a list of fields going to nothing."""
    word, name = COLLECTION_WORDS.get(r.get("collection"), "entry"), _name(r)
    if done: return f"The {word} {q(name)} was removed." if name else f"That {word} was removed."
    return f"Remove the {word} {q(name)}." if name else f"Remove this {word}."


def _record_lines(draft: dict, undo: bool = False, full_before=False, done: bool = False, routes=None) -> list:  # AV0022-08: proposal_text and show
    lines = []
    for r in draft["records"]:
        lines += [_removal(r, done)] if _removed(r) else _added(r, routes) if r.get("before") is None and isinstance(r.get("after"), dict) else [
            _change_line(r, f, b, a, undo, full_before, routes) for f, b, a in _changes(r)]
    return lines + [f"Heads up: {voice.explain_warning(w)}" for w in draft.get("warnings") or []]


def proposal_text(code: str, draft: dict, expires_at: str, repeat: bool = False, head: str = "", undo: bool = False, live_site=None, now=None,
                  notes=(), routes=None, reasons=None) -> str:
    """notes (HASS-CHAT-1): plain lines on what Hass chose so the change can go live (sign-up, a detail left out), shown under
    the change; routes: route ideas by id, so a route link is shown by its name."""
    lines = [head or "Here's the change I'd make:"] + _record_lines(draft, undo, full_before=bool(live_site), routes=routes) + list(notes)
    wait = f"I'll hold this for you until {voice.natural_iso(expires_at, now)}."
    if live_site:
        reasons = live_policy.check(draft) if reasons is None else reasons  # HASS-SEC-2 (M1): the conversation's own reasons
        that_way = " that way" if notes else ""
        return "\n".join(lines + [wait, live_policy.refusal(reasons) if reasons else
                                 f"Reply {q('yes ' + code)} to put it on the website{that_way} (it should show within a few minutes), "
                                 f"or {q('no ' + code)} to cancel." + (" To change something, just tell me." if notes else "")])
    yes = f"yes {code}" if repeat else "yes"  # a repeat of a closed draft needs its new code
    lines += [wait, f"Reply {q(yes)} to save it, or no to cancel. If something's wrong, tell me what to fix."]
    return "\n".join(lines)


class Conversation:
    def __init__(self, state_dir, editor, interpreter, clock, previewer=None, photos=None, labels=None, skills=None):
        """previewer (H06, e.g. preview.Previewer(worktree)): proposal screenshots and checked results; None keeps
        the H05 behaviour (no screenshot, an applied draft stays `applied`). skills (SKILLS-FW-3): a skills Registry; only read
        when the setting skills.mode is not ops-only, and then loaded with load_skills() when None."""
        sdir = editor_mod.open_state(state_dir)
        self.settings, self.photos = load_settings(sdir, photos is not None), photos  # fetch(provider_id, n) -> [bytes]
        self.editor, self.interpreter, self.clock, self.labels, self._label_job = editor, interpreter, clock, labels, None
        self.sdir, self.previewer = sdir, previewer
        path = memory_mod.private_db(sdir, "conversation.sqlite3")
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        columns = {r["name"] for r in self.db.execute("PRAGMA table_info(drafts)")}
        for column in ("screenshot", "checked_at", "proposed_at", "missing_json"):  # an H05 database gains the H06 + AVB-03 + AV0007-03 columns
            if column not in columns: self.db.execute(f"ALTER TABLE drafts ADD COLUMN {column} TEXT")
        if "reply_to" not in {r["name"] for r in self.db.execute("PRAGMA table_info(outbox)")}:  # AV0022-10 (H16)
            self.db.execute("ALTER TABLE outbox ADD COLUMN reply_to TEXT")
        # AVB-03 (H05): an open draft from before proposed_at has no recoverable proposal instant (a filled question
        # keeps its question's created_at), so it counts as proposed when this store is opened: a yes sent earlier is
        # refused and the owner re-sends it; it is never judged from created_at or from the current ttl.
        if self.db.execute("SELECT 1 FROM drafts WHERE proposed_at IS NULL AND state = 'proposed' LIMIT 1").fetchone():
            self.db.execute("UPDATE drafts SET proposed_at = ? WHERE proposed_at IS NULL AND state = 'proposed'",
                            (_iso(self._now()),))  # the clock is read only when such a draft exists
        self.outbox = Outbox(self.db, self._now)
        self.outbox.private_chat = self.settings.get("gChat")
        self.log = self.outbox.log = corrlog.CorrLog(self.sdir, self._now)  # HASS-VOICE-1: the correspondence log (state folder only)
        self.memory = None  # H15 store on this same connection, opened by the first memory command
        self.requests = openreq.OpenRequests(self.db)  # SKILLS-FW-3: the one open-request store (lazy table)
        self.skills_mode = self.settings["skillsMode"]
        self.dispatch = None
        if self.skills_mode != dispatch_mod.DEFAULT_MODE:
            from hass.skills import load_skills
            self.dispatch = dispatch_mod.Dispatcher(self, skills if skills is not None else load_skills())
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'open_asks'").fetchone():
            self.requests.adopt_legacy(self.settings["ownerChat"])  # a store made before FW-3 keeps its open request
        self.recover()

    def _now(self) -> datetime:
        return self.clock()

    @contextlib.contextmanager
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def flush(self, adapter) -> int:
        return self.outbox.flush(adapter)

    # -- store helpers -------------------------------------------------------------------------------------------
    def _row(self, row_id):
        return self.db.execute("SELECT * FROM drafts WHERE row_id = ?", (row_id,)).fetchone()

    def _drafts(self, where: str, *args):
        return self.db.execute(f"SELECT * FROM drafts WHERE {where} ORDER BY row_id", args).fetchall()

    def _by_code(self, code, states=None):
        rows = [r for r in self._drafts("code = ?", code) if self._mine(r) and (states is None or r["state"] in states)]
        return rows[-1] if rows else None

    def _expiry(self, row) -> datetime:
        """H16: a needs-details row stored before expiry existed (expires_at NULL) lapses at created_at + ttl."""
        if row["expires_at"]: return datetime.fromisoformat(row["expires_at"])
        return datetime.fromisoformat(row["created_at"]) + timedelta(seconds=self.settings["approvalTtlSeconds"])

    def _proposed_at(self, row) -> datetime:
        """AVB-03 (H05): the stored instant the draft was proposed (_propose sets it on insert and on a needs-details
        fill), so a later approvalTtlSeconds change never moves it. Opening the store stamps an open draft from before
        the column with the open instant; a proposed row still without one fails closed (now: only a yes sent now)."""
        return datetime.fromisoformat(row["proposed_at"]) if row["proposed_at"] else self._now()

    def _move(self, row, state, **fields):
        current = self._row(row["row_id"])["state"]
        if state not in TRANSITIONS.get(current, ()) or \
                (current, state) == ("approved", "rejected") and fields.get("reason") != "stale":
            raise TransitionError(f"draft {row['code']}: {current} -> {state} is not allowed")
        cols = {"state": state, **fields}  # column names are fixed identifiers from this module, quoted ("commit")
        assignments = ", ".join('"%s" = ?' % k for k in cols)
        self.db.execute(f"UPDATE drafts SET {assignments} WHERE row_id = ?", (*cols.values(), row["row_id"]))

    def _code(self, hexdigest: str) -> str:
        """A code is never reissued, not even a cancelled/expired draft's: a late `yes <old code>` names only that draft.
        A repeat of the same hash has no unused prefix left, so it takes the next code from a derived digest."""
        taken = {r["code"] for r in self._drafts("1")}
        while True:
            for size in range(4, 13, 2):
                if hexdigest[:size] not in taken: return hexdigest[:size]
            hexdigest = hashlib.sha256(f"{hexdigest}:repeat".encode()).hexdigest()

    def _repeat(self, row) -> bool:
        """True when an earlier draft had this exact hash (it was cancelled, expired, replaced or failed)."""
        if not row["draft_hash"]: return False
        return bool(self._drafts("draft_hash = ? AND row_id < ?", row["draft_hash"], row["row_id"]))

    _to = None  # HASS-LIVE-PLAN-1: the owner chat being answered (a message's chat, or an old draft's); None means ownerChat

    def _chat(self) -> str:
        return self._to or self.settings["ownerChat"]

    # -- HASS-OWNERS-2: several owners, each in their own one-to-one chat (settings ownerChats); none set = ownerChat alone, as before
    @property
    def _owner_chats(self) -> tuple:
        return self.settings.get("ownerChats") or (self.settings["ownerChat"],)

    @property
    def _shared(self) -> bool:
        """True with two or more ownerChats: one site, so a draft, the open release and `history` are shared and say whose they are."""
        return len(self._owner_chats) > 1

    def _who(self, chat) -> str:
        """The short first name the config gives this owner chat (ownerNames), else `the owner`."""
        return self.settings.get("ownerNames", {}).get(chat) or "the owner"

    def _whose(self, chat, capital=True) -> str:
        """`Your change` for the asking chat, else `Mike's change` (`The owner's change` when no name is set)."""
        if chat == self._chat(): return "Your change" if capital else "your change"
        who = self._who(chat)
        return (who[0].upper() + who[1:] if capital else who) + "'s change"

    def _visible(self, row) -> bool:
        """With several owners a row shown as 'waiting for your yes' must be this chat's own; alone it is every row, as before."""
        return not self._shared or self._mine(row)

    def _writer_busy(self, now):
        """HASS-OWNERS-2 (one site, one writer, one release at a time): with several owners, the other owner chat that holds the
        writer (a draft waiting for a yes or for details, one being saved, or a release still open) as (chat, 'draft' | 'release'),
        else None. Alone this is always None, so a single owner is answered exactly as before."""
        if not self._shared: return None
        mine = self._chat()
        for r in self._drafts("state IN ('proposed', 'needs-details', 'approved')"):
            if r["chat"] != mine and (r["state"] == "approved" or self._expiry(r) > now): return r["chat"], "draft"
        release = getattr(self.editor, "open_release", None)  # a live editor names the chat whose release has not settled
        other = release() if callable(release) else None
        return (other, "release") if other is not None and other != mine else None

    def _busy_reply(self, busy) -> str:
        chat, kind = busy
        who = self._who(chat)
        who = who[0].upper() + who[1:]
        self._reply(f"{who} has a change waiting, so I haven't started yours. Please ask me again once it's saved or cancelled." if kind == "draft"
                    else f"{who}'s change is going on the website right now, so I haven't started yours. Please ask me again in a few minutes.")
        return "writer-busy"

    _asker = None  # HASS-OWNERS-2: the normalized sender key of the message handle() is running; None outside a message

    def _mine(self, row) -> bool:
        """A draft belongs to the owner chat that made it: another owner's yes, no or undo never reaches it. With several owners a
        draft that is still open (proposed, waiting for details, approved) is also bound to the sender who made it, so a draft kept
        from before a second owner was added (one shared chat) is never approved or cancelled by the other person."""
        if row["chat"] != self._chat(): return False
        if self._shared and self._asker is not None and row["state"] in ("proposed", "needs-details", "approved"):
            return sender_key(row["sender"]) == self._asker
        return True

    @contextlib.contextmanager
    def _answer_to(self, chat):
        before, self._to = self._to, chat
        try: yield
        finally: self._to = before

    _said = None  # SKILLS-FW-3: the text of the newest reply queued while handling a message (a question kept on the open request)
    _last_draft_code = None  # SKILLS-FW-3: the code of the draft row the last _draft call proposed or asked about

    def _reply(self, text, attachments=(), **flags):
        chat = self._chat()
        if chat not in self._owner_chats: attachments = ()  # G's chat is text only (the Mac sends no pictures there); every owner chat gets pictures
        self._said = text
        self.outbox.add(chat, text, attachments, self._answering or None, **flags)

    def _problem(self, kind, reason, **extra):
        """HASS-VOICE-1: one row in the correspondence log (state folder only) for the message being answered."""
        self.log.record(kind, reason, msg=self.outbox.msg_id, **extra)

    def _plain(self, technical, doing="make that change") -> str:
        """The refusal text in everyday words; a reason we have no words for gets the generic line. Always logged."""
        sentence, code = voice.explain(technical)
        self._problem("could-not-do", code)
        return sentence if code != "unmapped" else f"I couldn't {doing}, so nothing changed. Could you say it another way?"

    def _when(self, iso) -> str:
        return voice.natural_iso(iso, self._now())

    def _save_private(self, row, reasons):
        """HASS-LIVE-PLAN-1: a change chat may not put on the website is kept once as a private proposal (one `policy` row in
        the private backlog: what was asked, why it is refused, the exact steps), so Graham can do it by hand. It never changes
        the website or the writer worktree. Read it with `python3 hass/skills/backlog.py list --state DIR --text`."""
        from hass.skills.backlog import Backlog  # lazy: the skills package is not needed to read a conversation
        marker = f"[{row['code']}]"
        backlog = Backlog(self.db, self._now)
        if self.db.execute("SELECT 1 FROM backlog WHERE reason = 'policy' AND summary LIKE ?", (marker + "%",)).fetchone(): return
        backlog.record("policy", f"{marker} {row['summary']}", f"Live change refused ({'; '.join(reasons)}). Proposed change {row['code']}: "
                       f"{row['summary']}. Steps: {row['ops_json']}")
        self._problem("could-not-do", "live-policy")

    def _live_reasons(self, draft) -> list:
        """live_policy.check, and HASS-SEC-2 (M1): an undo of a change the release engine never put on the website (saved in
        private mode before live) is refused too. Only a live editor (publish_live.LiveEditor.went_live) can tell; its apply()
        refuses the same undo again."""
        reasons = live_policy.check(draft)
        went_live = getattr(self.editor, "went_live", None)
        if callable(went_live) and live_policy.is_undo(draft) and not all(went_live(cid) for cid in live_policy.undone(draft)):
            reasons = sorted({*reasons, live_policy.UNDO_NOT_LIVE})
        return reasons

    def _capture(self, draft):
        """The proposal screenshot of ``draft`` (H06): {"ok", "png", "error"}; never raises past the previewer's own guard."""
        rendered = self.editor.render_draft(draft["change_id"])
        extra = {"assets": rendered["assets"]} if rendered.get("assets") else {}  # a new photo the draft would add
        return self.previewer.capture(rendered["files"], preview_mod.target_for(preview_mod.proposal_record(draft["records"]), shop_today(), store=rendered.get("store")),
                                      self.sdir / "screenshots" / f"{draft['change_id']}-proposal.png", **extra) \
            if rendered.get("result") == "ok" else {"ok": False, "png": None, "error": _reason(rendered)}

    def _proposal_reply(self, row, draft, prefix="", notes=()):
        """The proposal text plus, with a previewer, a private screenshot of the rendered draft (H06). HASS-CHAT-1: a picture
        that could not be drawn is never silent: the text says so first, the proposal is complete without it, and the picture
        is tried once more PREVIEW_RETRY_SECONDS later (retry_previews, outside this message's transaction)."""
        reasons = self._live_reasons(draft) if self.settings.get("liveSite") else []
        if reasons: self._save_private(row, reasons)
        shots, head, tail = [], "", ""
        if self.previewer is not None:
            shot = self._capture(draft)
            shots = [shot["png"]] if shot.get("png") else []
            if not shot["ok"]:
                self._problem("error", "preview-failed", excerpt=preview_mod.failure_kind(shot.get("error")))
                if shots: tail = "\nThe picture may not show every part of this change; the list above is exactly what will change."
                else:
                    head, tail = PREVIEW_FAILED_HEAD, "\n" + PREVIEW_RETRY_LINE
                    self._queue_preview_retry(row)
        text = prefix + proposal_text(row["code"], draft, row["expires_at"], self._repeat(row), head=head, undo=_is_undo(row),
                                      live_site=self.settings.get("liveSite"), now=self._now(), notes=notes, routes=self._routes(), reasons=reasons) + tail
        if self._paused(): text += "\n" + PAUSED_LINE
        self._reply(text, shots, long_ok=True)

    PREVIEW_RETRY = ("CREATE TABLE IF NOT EXISTS preview_retry (row_id INTEGER PRIMARY KEY, change_id TEXT NOT NULL, chat TEXT NOT NULL,"
                     " due_at TEXT NOT NULL)")

    def _queue_preview_retry(self, row):
        """HASS-CHAT-1: one later try at the picture for this proposal (a second failure of the same row is not queued again)."""
        self.db.execute(self.PREVIEW_RETRY)
        due = _iso(self._now() + timedelta(seconds=PREVIEW_RETRY_SECONDS))
        self.db.execute("INSERT OR IGNORE INTO preview_retry(row_id, change_id, chat, due_at) VALUES (?, ?, ?, ?)",
                        (row["row_id"], row["change_id"], self._chat(), due))

    def retry_previews(self) -> int:
        """HASS-CHAT-1: draw the pictures that failed at least PREVIEW_RETRY_SECONDS ago, once each, and send them (or say once
        that it still failed). A proposal that is no longer waiting gets nothing. The slow capture runs outside any transaction;
        each row is taken off the list before its try, so a crash never tries it twice. Returns the number of rows taken."""
        if self.previewer is None or not self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'preview_retry'").fetchone(): return 0
        now, taken = self._now(), 0
        for due in self.db.execute("SELECT * FROM preview_retry ORDER BY row_id").fetchall():
            if datetime.fromisoformat(due["due_at"]) > now: continue
            with self._tx():
                if not self.db.execute("DELETE FROM preview_retry WHERE row_id = ?", (due["row_id"],)).rowcount: continue
            taken += 1
            row = self._row(due["row_id"])
            if row is None or row["state"] != "proposed" or row["change_id"] != due["change_id"] or self._expiry(row) <= now: continue
            draft = self.editor.show(row["change_id"]).get("draft")
            shot = self._capture(draft) if isinstance(draft, dict) else {"ok": False, "png": None}
            with self._tx(), self._answer_to(due["chat"]):
                what = q(row["summary"])
                if shot.get("png") and shot.get("ok"):
                    self._reply(PREVIEW_LATER.format(what=what) + f" To go ahead, reply {q('yes ' + row['code'])}.", [shot["png"]])
                else:
                    self._problem("error", "preview-failed", excerpt=preview_mod.failure_kind(shot.get("error")))
                    self._reply(PREVIEW_STILL_FAILED.format(what=what) + f" To go ahead, reply {q('yes ' + row['code'])}.")
        return taken

    def _record(self, msg, disposition, owner=True):
        self.db.execute("INSERT INTO messages(provider_id, disposition, received_at) VALUES (?, ?, ?)",
                        (msg.provider_id, disposition, msg.received_at if owner else None))
        if owner: self.db.execute("INSERT OR IGNORE INTO message_chats(provider_id, chat) VALUES (?, ?)", (msg.provider_id, msg.chat))

    def _propose(self, draft, sender, now, row=None):
        """Insert a proposed draft (or fill a needs-details row) bound to the A2 hash, base and expiry."""
        expires = _iso(now + timedelta(seconds=self.settings["approvalTtlSeconds"]))
        fields = dict(change_id=draft["change_id"], draft_hash=draft["draft_hash"], base=draft["base"],
                      ops_json=json.dumps(draft["ops"], sort_keys=True), summary=_summary(draft), expires_at=expires,
                      proposed_at=_iso(now), missing_json=None)  # AVB-03: the proposal instant itself; a filled question has nothing missing
        if row is not None:
            self._move(row, "proposed", **fields)
            return self._row(row["row_id"])
        cur = self.db.execute(
            "INSERT INTO drafts(change_id, code, state, draft_hash, base, ops_json, summary, sender, chat, created_at,"
            " expires_at, proposed_at) VALUES (?, ?, 'proposed', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fields["change_id"], self._code(draft["draft_hash"][7:]), fields["draft_hash"], fields["base"],
             fields["ops_json"], fields["summary"], sender, self._chat(), _iso(now), expires,
             fields["proposed_at"]))
        return self._row(cur.lastrowid)

    # -- message handling ----------------------------------------------------------------------------------------
    _answering = None  # AV0022-10 (H16): received_at of the message handle() is running; replies are tagged with it
    _forwarded = None  # HASS-SEC-2 (L5): when the message reached the inbox (inbox.Inbox.forwarded_at); None when not known

    def handle(self, msg: Inbound, last_try=False, apply=True, forwarded_at=None) -> str:
        self._answering, self._forwarded = msg.received_at, forwarded_at
        self._to = msg.chat if self._is_owner(msg) else None
        self._asker = sender_key(msg.sender)
        self.outbox.msg_id, self.outbox.emoji_ok = msg.provider_id, voice.has_emoji(msg.text)
        try: return self._handle_message(msg, last_try, apply)
        finally: self._answering, self._forwarded, self._to, self._asker, self.outbox.msg_id, self.outbox.emoji_ok = None, None, None, None, None, False

    def _forwarded_late(self, msg) -> bool:
        """HASS-SEC-2 (L5): a yes is judged at the time it was sent (AV0022-06), so one the Mac held back and forwarded long
        after must not approve anything: it counts only when it reached the inbox within the approval time plus LATE_FORWARD_S of
        its send time. A message whose forwarding time is not known (called directly, not through the inbox) is not late."""
        try:
            sent, forwarded = datetime.fromisoformat(msg.received_at), self._forwarded
            if isinstance(forwarded, str): forwarded = datetime.fromisoformat(forwarded)
            return forwarded is not None and (forwarded - sent).total_seconds() > self.settings["approvalTtlSeconds"] + LATE_FORWARD_S
        except (TypeError, ValueError):
            return False

    def _handle_message(self, msg: Inbound, last_try=False, apply=True) -> str:
        """Process one inbound message; returns its disposition. Replies are only enqueued (see flush).
        apply=False (SHOP-3 fixture receiver): an owner approval is rolled back before anything is written (no approval
        row, the draft stays proposed) and the message is recorded as `approval-held`; editor.apply is never called."""
        self._label_job = None
        try:
            with self._tx():
                disposition, approved = self._handle(msg, last_try)
                if approved is not None and not apply: raise _Held(approved["code"])
        except _Held as held:
            with self._tx():
                self._reply(HELD_REPLY.format(code=held.code))
                self._record(msg, "approval-held")
            return "approval-held"
        if self._label_job: self._read_label(*self._label_job)  # AV1537-15: after the commit, never holding the lock
        if approved is None: return disposition
        out = self.editor.apply(approved["change_id"], approved["draft_hash"], chat=approved["chat"]) \
            if getattr(self.editor, "routes_chat", False) else self.editor.apply(approved["change_id"], approved["draft_hash"])
        with self._tx():
            self._outcome(self._row(approved["row_id"]), out, self._now())
        self._verify_pending()
        return disposition

    def _is_owner(self, msg) -> bool:
        """The owner chat with an owner sender, or (gIsOwner) G's own one-to-one chat with a G sender. Nobody else."""
        key, st = sender_key(msg.sender), self.settings
        if msg.chat in self._owner_chats: return key in st.get("chatKeys", {}).get(msg.chat, st["ownerKeys"])  # HASS-OWNERS-2: that chat's own owner
        return bool(st.get("gOwner")) and msg.chat == st.get("gChat") and key in st.get("gKeys", ())

    def _handle(self, msg, last_try=False):
        if self.db.execute("SELECT 1 FROM messages WHERE provider_id = ?", (msg.provider_id,)).fetchone():
            return "duplicate", None
        if (g := self._for_g(msg)) is not None: return g, None
        owner = self._is_owner(msg)
        if owner and not msg.from_me and msg.kind in ("edited", "reaction"):  # AV1737-03: never read, never approves
            self._reply(NOT_READ_REPLY)
            self._record(msg, "not-read")
            return "not-read", None
        ignored = "echo" if msg.from_me else "edited-ignored" if msg.kind != "new" else None if owner else "ignored"
        if ignored:
            self._record(msg, ignored, owner=False)
            return ignored, None
        if msg.attachments > 0 and self.photos is None:  # H12 part 1: the caption is never interpreted
            self._reply(ATTACHMENT_REPLY)
            self._record(msg, "attachment-unsupported")
            return "attachment-unsupported", None
        now, command = self._now(), None if msg.attachments > 0 else read_command(msg.text, listing_names=True)
        if command and command[0] == "listing" and command[1] and len(command[1].split()) >= 2 and not self._listing_names_something(command[1]):
            command = None  # A sentence is not a listing request unless it names something in the catalog.
        if command and command[0] == "post" and len(command[1].split()) >= 2 and not self._post_names_something(command[1]):
            command = None  # HASS-VOICE-1: "post a sale on social media" is a sentence for the interpreter, not a product or hike name
        self._close_asks(now)  # HASS-HIKE-FLOW-1: an open request older than RECENT_MINUTES is forgotten (FW-3: and a closed one older than 24 h)
        # AV0022-06 (H16): a yes/no is judged at the time it was sent, so a reply queued while the service was down counts
        phone = None if msg.attachments > 0 else parse_phone(msg.text)  # AV1352-04
        coded = None if phone is None or phone[2] or phone[0] is None else phone[:2]  # decorated answer without a ?
        cutoff = _answered_at(msg, now) if msg.attachments <= 0 and (parse_keyword(msg.text) or coded) is not None else now
        late = cutoff != now and self._forwarded_late(msg)  # HASS-SEC-2 (L5): forwarded long after it was sent
        if late: cutoff = now  # ... judged when it arrived, never at its send time
        expired = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) <= cutoff]
        if command and (command[0] in ("status", "help", "find", "show", "report", "post", "margin", "hidden", "listing", "photos", "backlog")
                        or command[0] == "history" and command[1] is not None): expired = []  # H17: read-only; AV2152-02: history <words>, not bare history
        memory = None if command or msg.attachments > 0 else read_memory(msg.text)
        if memory and memory[0] == "memory": expired = []  # AV0222-05: the bare `memory` listing is read-only; writes still sweep
        for row in expired: self._move(row, "expired", expires_at=_iso(self._expiry(row)))
        if command or msg.attachments > 0:  # NB-AV-09: a photo caption is never a command, keyword or approval
            disposition = self._photo(msg, now, last_try) if msg.attachments > 0 else self._command(msg, now, *command)
            self._record(msg, disposition)
            return disposition, None
        if memory:  # not a site change: never the interpreter or editor, and pause does not apply
            disposition = self._memory(msg, *memory)
            self._record(msg, disposition)
            return disposition, None
        keyword = parse_keyword(msg.text) or coded
        social = classify_social(msg.text) if keyword is None and parse_near(msg.text) is None else None  # AV0007-07
        if social == "social":  # thanks, a greeting or emoji only: no interpreter call, draft or usage count
            self._reply(SOCIAL_REPLY)
            self._record(msg, "social")
            return "social", None
        if keyword is None and (near := "" if social == "near" else parse_near(msg.text)) is not None:  # AV2022-07: no approval, call or count
            codes = [r["code"] for r in self._drafts("state = 'proposed'")
                     if self._mine(r) and self._expiry(r) > now and near in ("", r["code"])]
            self._reply(f"I haven't changed anything yet. To go ahead, reply {q('yes ' + codes[0])}." if len(codes) == 1 else
                        "I haven't changed anything yet. Which one do you want?\n" + self._choices(codes) if codes else NOTHING, long_ok=True)
            self._record(msg, "near-approval")
            return "near-approval", None
        if keyword is None and phone is not None:  # AV1352-04: a question or a lone code is never an answer
            live = [r["code"] for r in self._drafts("state = 'proposed'") if self._mine(r) and self._expiry(r) > now]
            if phone[0] is not None or phone[1] in live:
                one = phone[1] if phone[1] in live else live[0] if len(live) == 1 else None
                self._reply(f"I haven't changed anything yet. To go ahead, reply {q('yes ' + one)}, or {q('no ' + one)} to cancel." if one else
                            "I haven't changed anything yet. Which one do you mean?\n" + self._choices(live) if live else NOTHING, long_ok=True)
                self._record(msg, "near-approval")
                return "near-approval", None
        if keyword is None:
            disposition = self._request(msg, now)
            self._record(msg, disposition)
            return disposition, None
        verb, code = keyword
        if late and verb == "approve":  # HASS-SEC-2 (L5): a yes that reached me long after it was sent approves nothing
            self._reply(LATE_YES_REPLY)
            self._record(msg, "no-target")
            return "no-target", None
        if code is None and (ask := self._shelf_ask(now)) is not None:  # HASS-SHELFCHECK-FLOW-1: a bare yes/no answers our question
            disposition = self._shelf_answer(msg, now, verb, ask)  # (never a waiting draft's approval or cancel)
            self._record(msg, disposition)
            return disposition, None
        if verb == "approve" and code is None and self.settings.get("approvalNeedsCode"):
            self._reply("To put a change on the website, reply yes and its code, like " + q("yes a1b2") + ".")
            self._record(msg, "no-target")
            return "no-target", None
        # AV1537-02: no/cancel also closes an open (unexpired) question; yes only ever targets a proposal.
        states = "('proposed', 'needs-details')" if verb == "reject" else "('proposed')"
        if verb == "reject": self._close_asks()  # HASS-HIKE-FLOW-1: no/cancel also drops the open request (the reply is unchanged)
        targets = [r for r in self._drafts(f"state IN {states}") if self._mine(r) and (code is None or r["code"] == code)]
        asks = [] if verb != "approve" or targets else [self._by_code(code, ("needs-details",))] if code else \
            [r for r in self._drafts("state = 'needs-details'") if self._mine(r) and self._expiry(r) > cutoff]  # AV1737-05: bare yes
        if asks := [a for a in asks if a is not None]:  # a waiting question is never approved; it is repeated
            self._reply("\n".join("I still need an answer from you first. " + q(a["summary"]) for a in asks),
                        long_ok=True)
            self._record(msg, "no-target")
            return "no-target", None
        if len(targets) != 1:
            self._reply(self._no_target(code, targets, expired))
            self._record(msg, "no-target")
            return "no-target", None
        target = targets[0]
        if verb == "reject":
            self._move(target, "rejected", reason="owner")
            self._reply("Okay, I've cancelled that. Nothing changed.")
            self._problem("corrected", "said-no")
            self._record(msg, "rejected")
            return "rejected", None
        if self._paused():  # H17: no approval row, no state move; the draft keeps its expiry
            self._reply(f"Changes are paused, so I haven't saved that. Say {q('resume changes')}, then reply {q('yes ' + target['code'])}.")
            self._record(msg, "paused")
            return "paused", None
        if cutoff != now and cutoff < self._proposed_at(target):  # AVB-03 (H05): a yes sent before the draft existed
            self._reply(f"Your yes came before I had written that change up, so I haven't saved it. If you still want it, reply {q('yes ' + target['code'])}.")
            self._record(msg, "no-target")
            return "no-target", None
        if code is None and self._repeat(target):  # a delayed bare `yes` must not approve a repeat of a closed draft
            self._reply(f"That is the same change that was cancelled earlier, so I want to be sure. Reply {q('yes ' + target['code'])} if you still want it.")
            self._record(msg, "no-target")
            return "no-target", None
        if self.settings.get("liveSite") and (reasons := self._live_reasons(self.editor.show(target["change_id"]).get("draft"))):
            self._save_private(target, reasons)  # HASS-LIVE-PLAN-1: refused for the website, kept for Graham, never lost
            self._reply(live_policy.refusal(reasons, understood=q(target["summary"])))
            self._record(msg, "no-target")
            return "no-target", None
        self.db.execute(
            "INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, approved_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (msg.sender, msg.chat, msg.provider_id, target["change_id"],
                                                 target["draft_hash"], target["base"], target["expires_at"], _iso(now)))
        self._move(target, "approved")
        self.requests.close_drafted(self._chat(), now)  # SKILLS-FW-3: the request that made this draft is finished
        self._record(msg, "approved")
        return "approved", self._row(target["row_id"])

    def _choices(self, codes) -> str:
        """One line per waiting change: the words to reply with, then what the change is."""
        rows = [self._by_code(c, ("proposed",)) for c in codes]
        return "\n".join(q(f"yes {c}") + ": " + (q(r["summary"]) if r else "") for c, r in zip(codes, rows))

    def _for_g(self, msg):
        """HASS-VOICE-1: `problems` (the last ten problem moments) and `weekly` (the week's three most common) from G's own number
        only (settings gSenders, never an owner sender). They read the correspondence log and nothing else; Mike never sees them."""
        if msg.from_me or msg.kind != "new" or msg.attachments > 0 or sender_key(msg.sender) not in self.settings.get("gKeys", ()): return None
        if msg.chat != self.settings.get("gChat") or msg.chat in self._owner_chats: return None  # only G's own chat; never an owner's
        word = msg.text.strip().lower().rstrip(".!")
        if word not in ("problems", "weekly"): return None
        text = corrlog.problems_text(self.log) if word == "problems" else corrlog.weekly_line(self.log)
        self.outbox.add(msg.chat, text, (), self._answering or None, long_ok=True, ids_ok=True)
        self._record(msg, "g-" + word, owner=False)
        return "g-" + word

    def _no_target(self, code, targets, expired) -> str:
        if targets:
            return "\n".join(["Which one do you mean? Reply yes or no and its code."] + [
                (q(f"yes {r['code']}") + ": " + q(r["summary"])) if r["state"] == "proposed" else "I'm waiting for details: " + r["summary"]
                for r in targets])
        if code and self._by_code(code) is None and self._shared and (other := [r for r in self._drafts("code = ?", code) if not self._mine(r)]):
            who = "someone else" if other[-1]["chat"] == self._chat() else self._who(other[-1]["chat"])  # same chat, other sender: a draft kept from before a second owner
            return f"That change belongs to {who}, so I can't save it or cancel it for you. Nothing changed."  # HASS-OWNERS-2: never its words
        if code and self._by_code(code) is None:  # AV2152-01 (H05/H17): a code that matches no draft; never guessed
            waiting = [r for r in self._drafts("state = 'proposed'") if self._mine(r)]
            return "\n".join(["I don't have a change with that code."] + (["These are waiting for you:"] + [
                q(f"yes {r['code']}") + ": " + q(r["summary"]) for r in waiting] if waiting else []))
        named = [self._by_code(code)] if code else [self._row(r["row_id"]) for r in expired if self._visible(r)]
        return "\n".join(self._state_text(r) for r in named if r is not None) or NOTHING

    def _state_text(self, row) -> str:
        state = row["state"]
        if state == "expired": return f"That change timed out {self._when(row['expires_at'])}, so nothing changed. Tell me again if you still want it."
        if state == "rejected" and row["replaced_by"]: return "That one was replaced by a newer one."
        if state == "rejected": return "That one was cancelled, so nothing changed."
        return {"approved": "That one is being saved.", "applied": "That one is already saved.", "verified": "That one is already saved.",
                "failed": "That one couldn't be saved.", "reverted": "That one was undone."}.get(state, "I'm not sure where that one stands.")

    def _registry(self):
        """The editor's ops registry (production: load_registry()), loaded once per conversation."""
        if getattr(self, "_ops", None) is None: self._ops = self.editor.registry or load_registry()
        return self._ops

    def _calls(self, now):
        """H22: (local day, interpreter calls counted for it). No usage table yet means no calls."""
        day = now.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'usage'").fetchone(): return day, 0
        row = self.db.execute("SELECT calls FROM usage WHERE day = ?", (day,)).fetchone()
        return day, row["calls"] if row else 0

    def _makers(self):
        """The worktree's makers (read-only) for the claim check; None when unreadable (every maker change asks)."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            makers = json.loads((wt / "hass" / "content" / "makers.json").read_text("utf-8"))["makers"]
        except (OSError, ValueError, KeyError, TypeError, RecursionError, editor_mod.UnsafeState):
            return None
        return makers if isinstance(makers, dict) else None

    def _routes(self):
        """The worktree's route ideas by id (read-only) for the claim check; None when unreadable (owner text only)."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            ideas = json.loads((wt / "hass" / "content" / "community.json").read_text("utf-8"))["routeIdeas"]
            return {i["id"]: i for i in ideas if isinstance(i, dict) and isinstance(i.get("id"), str)} if isinstance(ideas, list) else None
        except (OSError, ValueError, KeyError, TypeError, RecursionError, editor_mod.UnsafeState):
            return None

    def _sources(self):
        """AV1937-05: the worktree's real hikes by id (read-only) for a hike.repeat copy; None when unreadable (no exemption)."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            events = json.loads((wt / "hass" / "content" / "community.json").read_text("utf-8"))["events"]
            return {e["id"]: e for e in events if isinstance(e, dict) and isinstance(e.get("id"), str)} if isinstance(events, list) else None
        except (OSError, ValueError, KeyError, TypeError, RecursionError, editor_mod.UnsafeState):
            return None

    def _notes(self) -> list:
        """AV1102-09: the newest MAX_NOTES active non-alias memory rows as {"key", "text"}; any problem means none."""
        try:
            if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone():
                return []
            private = "".join(f"AND substr(key, 1, {len(p)}) != '{p}' " for p in PRIVATE_PREFIXES)  # constants, not owner text
            rows = self.db.execute(f"SELECT key, value FROM memory WHERE {memory_mod.ACTIVE} {private}"
                                   "ORDER BY created_at DESC, id DESC LIMIT ?", (MAX_NOTES,)).fetchall()
            return [{"key": r[0], "text": r[1]} for r in rows]
        except sqlite3.Error:
            return []

    def _interpreter_aliases(self) -> list:
        """AV0007-06: the newest MAX_INTERPRETER_ALIASES active aliases whose product or maker still exists, as
        {"name", "kind", "id"}; read-only (no table made, no write); any problem means none."""
        try:
            if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone():
                return []
            rows = self.db.execute(f"SELECT key, value FROM memory WHERE {memory_mod.ACTIVE} AND substr(key, 1, 6) = 'alias.' "
                                   "ORDER BY created_at DESC, id DESC").fetchall()
            if not rows: return []
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            product_ids = {p["id"] for p in content.products}
            out = []
            for key, value in rows:
                slug, (kind, colon, ident) = key[6:], str(value).partition(":")
                if not slug or not colon or not ident: continue
                if not (ident in product_ids if kind == "product" else ident in content.makers if kind == "maker" else False): continue
                out.append({"name": slug.replace("-", " "), "kind": kind, "id": ident})
                if len(out) >= MAX_INTERPRETER_ALIASES: break
            return out
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            return []

    def _asked_again(self, text, msg):
        """HASS-VOICE-1: the question about to be sent is the one we sent last time to this owner a moment ago: log it."""
        try:
            last = self.db.execute("SELECT text, created_at FROM outbox WHERE id < (SELECT MAX(id) FROM outbox) ORDER BY id DESC LIMIT 1").fetchone()
            if last and last["text"] == voice.plain(text) and self._now() - datetime.fromisoformat(last["created_at"]) <= timedelta(minutes=RECENT_MINUTES):
                self._problem("asked-again", "same-question")
        except (sqlite3.Error, ValueError, TypeError, KeyError): pass

    def _recent_question(self, now):
        """HASS-NL-1: {"question": text} when the newest owner message was answered with a question of ours at most
        RECENT_MINUTES ago (so the next short text is its answer); else None. HASS-HIKE-FLOW-1: plus "earlier", the owner's
        texts of the open request, oldest first, when they are still kept (see _open_ask)."""
        try:
            last = self.db.execute("SELECT provider_id, disposition, received_at FROM messages WHERE received_at IS NOT NULL"
                                   " AND COALESCE((SELECT chat FROM message_chats c WHERE c.provider_id = messages.provider_id), ?) = ?"
                                   " ORDER BY rowid DESC LIMIT 1", (self.settings["ownerChat"], self._chat())).fetchone()
            if last is None or last["disposition"] != "question": return None
            row = self.db.execute("SELECT text, created_at FROM outbox WHERE reply_to = ? AND chat = ? ORDER BY id DESC LIMIT 1",
                                  (last["received_at"], self._chat())).fetchone()
            if row is None or not row["text"] or len(row["text"]) > RECENT_MAX: return None
            if now - datetime.fromisoformat(row["created_at"]) > timedelta(minutes=RECENT_MINUTES): return None
            return {"question": row["text"], **({"earlier": earlier} if (earlier := self._ask_texts(last["provider_id"], now)) else {})}
        except (sqlite3.Error, ValueError, TypeError, KeyError): return None

    def _ask_texts(self, provider_id, now) -> list:
        """The owner texts kept for the open question that answered message ``provider_id``; any problem or a stale row: []."""
        try:
            req = self.requests.by_provider(self._chat(), provider_id, now)
            return req["texts"] if req and all(isinstance(t, str) and t for t in req["texts"]) else []
        except (sqlite3.Error, ValueError, TypeError, KeyError, RecursionError): return []

    def _open_ask(self, msg, now, earlier, pending=None):
        """HASS-HIKE-FLOW-1: keep this owner text with the earlier ones of the same open request, newest last, bounded.
        HASS-SHELFCHECK-FLOW-1: ``pending`` = {"ops": [...], "revises": code|None}, the change that waits for today's shelf check.
        SKILLS-FW-3: written to the one open-request store (a request with no skill)."""
        self.requests.put(self._chat(), msg.provider_id, now, texts=[*earlier, msg.text], pending=pending, legacy=True,
                          turns=ASK_TURNS, per=ASK_TEXT_CUT, total=ASK_CHARS)

    def _shelf_ask(self, now):
        """HASS-SHELFCHECK-FLOW-1: the open shelf-check question as {"ops", "revises", "texts"}, or None. It is open only while
        it is the newest thing the owner and Hass said (any other owner message, a stranger's does not count, closes it) and
        at most RECENT_MINUTES old; a stored change that cannot be read is no question."""
        try:
            row = self.requests.pending_of(self._chat(), now)
            last = self.db.execute("SELECT provider_id FROM messages WHERE received_at IS NOT NULL"
                                   " AND COALESCE((SELECT chat FROM message_chats c WHERE c.provider_id = messages.provider_id), ?) = ?"
                                   " ORDER BY rowid DESC LIMIT 1", (self.settings["ownerChat"], self._chat())).fetchone()
            if row is None or last is None or last["provider_id"] != row["provider_id"]: return None
            pending, texts = row["pending"], row["texts"]
            ops = pending["ops"]
            if not (isinstance(ops, list) and all(isinstance(c, dict) and isinstance(c.get("op"), str) for c in ops)): return None
            calls = row.get("calls") if hasattr(row, "get") else row["calls"]
            return {"ops": ops, "revises": pending.get("revises"), "texts": texts if isinstance(texts, list) else [],
                    "calls": calls if isinstance(calls, list) else [], "ask": pending.get("ask"),  # HASS-CHAT-1: "meet" or None (shelf check)
                    "suggest": pending.get("suggest"), "index": pending.get("index"), "notes": [n for n in pending.get("notes") or () if isinstance(n, str)]}
        except (sqlite3.Error, ValueError, TypeError, KeyError, RecursionError): return None

    def _check_day(self):
        """HASS-SHELFCHECK-FLOW-1: (the stored shelf-check date or None, True when readable) from the writer worktree."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            return checked_on(load_and_validate(wt / "hass" / "content", wt / "storefront-mockup").store), True
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError): return None, False

    def _ask_shelf(self, msg, now, result, earlier) -> str:
        """HASS-SHELFCHECK-FLOW-1: the change was refused only because today's shelf check is missing (none, or older than
        today): keep it with our question. Nothing is drafted or written until the owner's own yes; a check dated after
        today cannot be fixed by a yes, so that says so."""
        day, readable = self._check_day()
        if readable and day is not None and day > shop_today(now):
            self._reply(SHELF_CLOCK)
            return "not-drafted"
        self._open_ask(msg, now, earlier, {"ops": result["ops"], "revises": result.get("revises")})
        self._reply(SHELF_QUESTION)
        return "question"

    def _shelf_answer(self, msg, now, verb, ask) -> str:
        """SKILLS-FW-3: the shelf-check answer (below), then the owner's other queued asks go on one at a time: the next one
        becomes the open request and its question is asked, whichever way the shelf-check change went."""
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)  # HASS-OWNERS-2
        if ask.get("ask") in ("meet", "offer"): return self._meet_answer(msg, now, verb, ask)  # HASS-CHAT-1: our hike question
        disposition = self._shelf_decide(msg, now, verb, ask)
        calls = ask.get("calls") or []
        if calls and self.skills_mode != dispatch_mod.DEFAULT_MODE:
            self.dispatch._next_queued(msg, now, None, calls, ask["texts"], [], disposition)
        return disposition

    def _meet_answer(self, msg, now, verb, ask) -> str:
        """HASS-CHAT-1: our hike questions. "meet": a bare yes takes the suggested meeting place and drafts the waiting hike (its
        notes kept); a bare no, or a yes when there was no suggestion, asks where instead and keeps the request open for his
        answer in words. "offer": a bare yes drafts the offered change (the nearest one that can go live); no changes nothing."""
        self._close_asks()
        if ask.get("ask") == "offer":
            if verb != "approve":
                self._reply("Okay, I've left it as it is. Nothing changed.")
                return "offer-no"
            return self._draft(msg, now, {"ops": ask["ops"], "revises": ask["revises"]}, ask["texts"], notes=ask["notes"])
        if verb == "approve" and isinstance(ask.get("suggest"), str) and ask["suggest"]:
            ops = hike_chat.with_meeting(ask["ops"], ask["suggest"], self._routes(), ask.get("index"))
            return self._draft(msg, now, {"ops": ops, "revises": ask["revises"]}, ask["texts"], notes=ask["notes"])
        self._open_ask(msg, now, ask["texts"])  # the request stays open: his next words say where
        self._reply(MEET_NO)
        return "question"

    def _shelf_decide(self, msg, now, verb, ask) -> str:
        """HASS-SHELFCHECK-FLOW-1: the owner's bare yes or no to the open shelf-check question (never a draft's yes/no).
        yes: one draft that marks today's shelf check and then makes the waiting change (none, for the morning report's
        question), with the normal approval; no: nothing is changed and the question is closed."""
        self._close_asks()
        if verb == "reject":
            self._reply(SHELF_NO)
            return "shelf-no"
        ops = [{"op": "store.confirm_selection", "args": {}}, *ask["ops"]]
        out = self.editor.prepare(ops)
        draft = out.get("draft") if out["result"] == "ok" else None
        revised = self._by_code(ask["revises"], ("proposed", "needs-details")) if isinstance(ask["revises"], str) else None
        if draft is None or claims.unstated(draft, " ".join(ask["texts"]), self._makers(), self._routes(), self._sources()) or (
                self.settings.get("liveSite") and live_policy.unsaid(draft, "\n".join(ask["texts"]))):  # HASS-LIVE-ADD-1
            self._reply(SHELF_FAILED)
            return "not-drafted"
        same = [r for r in self._drafts("state = 'proposed' AND change_id = ?", draft["change_id"]) if self._mine(r)]
        row = same[0] if same else self._propose(draft, msg.sender, now)
        if revised is not None and not same: self._move(revised, "rejected", reason="revised", replaced_by=row["code"])
        self._proposal_reply(row, draft, "Got it. This draft also records that the shelf list was checked today.\n" if ask["ops"] else "")
        return "proposed"

    def _close_asks(self, now=None, state="closed"):
        """HASS-HIKE-FLOW-1: forget the open request (all of it, or with ``now`` only what is older than RECENT_MINUTES).
        SKILLS-FW-3: one store; a skill request is closed (``state``), and its text erased 24 hours later; a closed one older
        than that, and any backlog row older than its retention, goes at the same sweep."""
        owner = self._chat()  # HASS-LIVE-PLAN-1: per owner chat
        if now is None: self.requests.close_live(owner, self._now(), state)
        else:
            self.requests.sweep(now)
            if self.skills_mode != dispatch_mod.DEFAULT_MODE and self._backlog_table():
                from hass.skills.backlog import Backlog
                Backlog(self.db, self._now).purge()

    def _audit_backend(self, msg, now, failed):
        """HASS-INTERP-OPENAI-1: one audit row per interpreted message when the interpreter names the backend that answered
        (and whether the fallback was asked). No such interpreter, or a call that raised: no row."""
        itp = self.interpreter
        backend = getattr(itp, "last_backend", None)
        if failed is None or not isinstance(backend, str) or not backend: return
        code = lambda v: v if isinstance(v, str) and len(v) <= 40 else None  # noqa: E731 - short reason codes only
        seconds = getattr(itp, "last_seconds", None)
        self.db.execute(AUDIT)
        self.db.execute("INSERT OR REPLACE INTO interpreter_audit VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (msg.provider_id, _iso(now), backend[:20], 1 if getattr(itp, "last_fallback", False) is True else 0,
                         code(getattr(itp, "last_primary_error", None)), code(getattr(itp, "last_error", None)),
                         float(seconds) if isinstance(seconds, (int, float)) else None))

    def _request(self, msg, now) -> str:
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)  # HASS-OWNERS-2: before any model call or count
        if len(msg.text) > MAX_OWNER_TEXT:  # AV1737-04: code points; never interpreted, drafted or counted
            self._reply(TOO_LONG)
            return "too-long"
        if HOSTILE_RE.search(msg.text):  # a calm no, decided here: the model is never asked and nothing is drafted or counted
            self._reply(HOSTILE_REPLY)
            self._problem("could-not-do", "refused-request")
            return "unsupported"
        cap = self.settings["interpreterDailyCap"]
        skills_on = self.skills_mode != dispatch_mod.DEFAULT_MODE
        req = self.requests.get(self._chat(), now) if skills_on else None  # SKILLS-FW-3: the owner's own open request
        if skills_on and (done := self.dispatch.cheap(msg, now)) is not None: return done  # a short answer read by code: no model call
        if cap is not None:  # H22: counted before the call in this transaction, so a failed call still counts
            day, calls = self._calls(now)
            if calls >= cap:
                self._reply(DAILY_LIMIT)
                return "daily-limit"
            self.db.execute(USAGE)
            self.db.execute("INSERT INTO usage VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET calls = calls + 1", (day,))
        if CORRECTION_RE.match(msg.text.strip()): self._problem("corrected", "owner-corrected")
        pending = [{"code": r["code"], "state": r["state"], ("question" if r["state"] == "needs-details" else "summary"):
                    r["summary"], **_pending_ops(r["ops_json"]),  # AV0022-03: + "ops" or "opsOmitted"
                    **({"missing": _missing_ids(r["missing_json"])} if r["state"] == "needs-details" else {})}  # AV0007-03
                   for r in self._drafts("state IN ('proposed', 'needs-details')") if self._mine(r) and self._expiry(r) > now]
        notes = self._notes()  # AV1102-09: preferences only; no notes means no notes keyword
        kept = req is not None and bool(req["skill"] or req["attachments"])  # SKILLS-FW-3: a skill request replaces `recent`
        recent = self.requests.snapshot(req) if kept else self._recent_question(now)  # HASS-NL-1; HASS-HIKE-FLOW-1: with the owner's earlier texts of the same request
        context = {k: v for k, v in (("notes", notes), ("aliases", self._interpreter_aliases()),
                                     ("recent", recent)) if v}  # AV0007-06; HASS-NL-1
        sent_at = _answered_at(msg, now)  # AV1352-06: 'today' is the day it was sent; bad, naive or future means now
        failed = None  # AV1052-10: None until interpret actually returned; then the adapter's last_error (or "")
        skill_result = None
        try:
            raw = self.interpreter.interpret(msg.text, pending, **context, sent_at=sent_at)
            skill_result = dispatch_mod.checked(raw) if skills_on else None  # SKILLS-FW-3: skill / calls / none / cancel
            result = skill_result or _checked(raw)
            failed = getattr(self.interpreter, "last_error", None) or ""
        except Exception if cap is not None else ():  # H22: no cap: unchanged (an error rolls the message back)
            result = dict(UNREADABLE)  # keep the counted call; a failure stops safely with the unreadable reply
        self._audit_backend(msg, now, failed)
        if failed:  # AV1052-10: the reader itself failed: remember it for status (latest only, no error detail kept)
            self.db.execute(CONTROL)
            self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('reader-failed', ?, ?, ?)"
                            " ON CONFLICT(name) DO UPDATE SET value = excluded.value, set_at = excluded.set_at,"
                            " provider_id = excluded.provider_id",
                            (getattr(self, "_photo_draft", None) or "1", _iso(now), msg.provider_id))
        elif failed is not None and self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'control'").fetchone():
            self.db.execute("DELETE FROM control WHERE name = 'reader-failed'")  # a request was read again
        if skill_result is not None: return self.dispatch.reply(msg, now, skill_result, req)  # SKILLS-FW-3
        if skills_on and self.skills_mode == "skills-first" and "ops" in result and any(
                dispatch_mod.op_is_owned(c["op"], self.dispatch.registry) for c in result["ops"] if isinstance(c, dict) and isinstance(c.get("op"), str)):
            self._reply(UNREADABLE["unsupported"])  # a skill owns this change: raw ops are no longer taken for it (spec 2.4)
            return "unsupported"
        earlier = (recent or {}).get("earlier") or []  # HASS-HIKE-FLOW-1: the open request this text may be answering
        return self._draft(msg, now, result, earlier, failed=failed, req=req)

    def _draft(self, msg, now, result, earlier, prefix="", failed=None, req=None, legacy=True, notes=()):
        """Draft ``result["ops"]`` (from the interpreter, or from a skill plan: SKILLS-FW-3), or relay its question / unsupported
        reply: revises, the interpret check, the editor, the claims gate over the owner's JOINED texts, the proposal. The caller
        has already counted the model call, if there was one. Returns the disposition."""
        self._last_draft_code = None
        pending = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) > now and self._visible(r)]  # HASS-OWNERS-2
        codes = {p["code"] for p in pending}
        named = self._by_code(result["revises"]) if result.get("revises") and result["revises"] not in codes else None
        cancelled_question = named is not None and named["state"] == "rejected" and named["reason"] == "owner" \
            and named["change_id"] is None  # AV1537-02: a question the owner cancelled is not filled later
        if named is not None and named["state"] == "expired" or cancelled_question:  # H16 vs NB-AV-01 (2026-10-31):
            result = {**result, "revises": None}  # a closed draft has nothing left to revise; an unknown code still asks
        result = interpret_check.check(result, self._registry(), codes)  # NB-AV-01: a bad op/arg/kind/code asks
        if legacy and "question" in result:
            if req is not None and (req["skill"] or req["attachments"]):  # a question about a skill request stays on that request
                self.requests.put(self._chat(), msg.provider_id, now, texts=[*req["texts"], msg.text], request_id=req["request_id"],
                                  skill=req["skill"], slots=req["slots"], calls=req["calls"], attachments=req["attachments"],
                                  question=result["question"], draft_code=req["draft_code"], asks=req["asks"])
            else: self._open_ask(msg, now, earlier)  # keep the request with our question, for the answer
        elif legacy and "ops" in result: self._close_asks()  # a draft (or its own question) takes over; nothing stays open
        for key in ("question", "unsupported"):
            if key in result:
                self._reply(result[key])
                cant = "can't do that" in result[key].lower()
                if key == "unsupported" or cant:
                    self._problem("error" if failed else "could-not-do" if cant else "did-not-understand",
                                  "reader-failed" if failed else "no-skill" if cant else "unclear")
                else: self._asked_again(result[key], msg)
                return "reader-failed" if failed and key == "unsupported" else key
        revised = self._by_code(result["revises"], ("proposed", "needs-details")) if result["revises"] else None
        photo = next((c["args"].get("photo") for c in json.loads(revised["ops_json"]) if c["op"] == "product.set_photo"),
                     None) if revised else None  # NB-AV-09: a fill keeps the draft's photo; another one is refused
        calls = [c for c in result["ops"] if c["op"] in PHOTO_OPS] if photo else []  # AV0022-04: a new product too
        if len(calls) > 1:  # AV0022-04: one photo, one product; nothing changes until the owner says which
            return self._reply("A photo can go on one product at a time. Which product is it for?") or "photo-many-ops"
        if any(c["args"].setdefault("photo", photo) != photo for c in calls):
            return self._reply("That answer goes with a different photo, so nothing changed. Which product is this photo for?") or "photo-mismatch"
        notes = list(notes)
        if self.settings.get("liveSite") and any(c.get("op") in ("hike.create", "hike.update") for c in result["ops"]):  # HASS-CHAT-1
            shaped = hike_chat.shape(result["ops"], self._routes(), events=self._sources())
            if shaped.ask and shaped.ask["kind"] == "offer":  # sign-up asked for on a posted hike: the nearest live change, as a yes/no
                if shaped.ask["ops"] and legacy:
                    self._open_ask(msg, now, earlier, {"ops": shaped.ask["ops"], "revises": result["revises"], "ask": "offer", "notes": notes})
                self._reply(shaped.ask["question"])
                self._problem("could-not-do", "signup-offered")
                return "question" if shaped.ask["ops"] and legacy else "not-drafted"
            if shaped.ask and legacy:  # a trail name is not a place to meet: ask once, keep the shaped hike for his answer
                self._open_ask(msg, now, earlier, {"ops": shaped.ops, "revises": result["revises"], "ask": "meet",
                                                   "suggest": shaped.ask["suggest"], "index": shaped.ask.get("index"),
                                                   "notes": [*notes, *shaped.notes]})
                self._reply(shaped.ask["question"])
                self._asked_again(shaped.ask["question"], msg)
                return "question"
            result, notes = {**result, "ops": shaped.ops}, [*notes, *shaped.notes]
        out = self.editor.prepare(result["ops"])
        if out["result"] == "needs-details":
            ops_json = json.dumps(result["ops"], sort_keys=True)
            expires = _iso(now + timedelta(seconds=self.settings["approvalTtlSeconds"]))  # H16: questions lapse too
            missing_json = json.dumps(out.get("missing", []))  # AV0007-03: stored with the question, same transaction
            if revised is not None and revised["state"] == "needs-details":  # the owner just answered: refresh
                self.db.execute("UPDATE drafts SET ops_json = ?, summary = ?, expires_at = ?, missing_json = ? WHERE row_id = ?",
                                (ops_json, out["question"], expires, missing_json, revised["row_id"]))
                self._last_draft_code = revised["code"]
            else:
                code = self._code(hashlib.sha256(msg.provider_id.encode()).hexdigest())
                self.db.execute(
                    "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at, missing_json)"
                    " VALUES (?, 'needs-details', ?, ?, ?, ?, ?, ?, ?)",
                    (code, ops_json, out["question"], msg.sender, msg.chat, _iso(now), expires, missing_json))
                self._last_draft_code = code
                # An incomplete correction still supersedes the proposal it names: it can no longer be approved.
                if revised is not None: self._move(revised, "rejected", reason="revised", replaced_by=code)
            self._reply(out["question"])
            self._asked_again(out["question"], msg)
            return "needs-details"
        if out["result"] == "refused" and out.get("reason") == catalog.NOT_CHECKED_TODAY and not ({"store.confirm_selection"} & {c["op"] for c in result["ops"]}):
            return self._ask_shelf(msg, now, result, earlier)  # HASS-SHELFCHECK-FLOW-1: ask, keep the change, write nothing
        if out["result"] != "ok":
            self._reply(self._plain(_reason(out)))
            return "not-drafted"
        draft = out["draft"]
        if hits := claims.unstated(draft, " ".join([*earlier, msg.text]), self._makers(), self._routes(), self._sources()):  # NB-AV-05: an unstated claim asks, never drafts; HASS-HIKE-FLOW-1: the owner's earlier texts of this request count as stated
            self._reply(claims.question(hits))  # no row; a waiting draft named by revises is left as it was
            return "claim-question"
        if self.settings.get("liveSite") and (said := live_policy.unsaid(draft, "\n".join([*earlier, msg.text]))):
            self._reply(live_policy.unsaid_question(said))  # HASS-LIVE-ADD-1: a new product's brand, maker and town only in his words
            return "claim-question"
        same = [r for r in self._drafts("state = 'proposed' AND change_id = ?", draft["change_id"]) if self._mine(r)]
        if same and (revised is None or revised["row_id"] == same[0]["row_id"]):
            row = same[0]
        elif revised is not None and revised["state"] == "needs-details":
            row = self._propose(draft, msg.sender, now, row=revised)
        else:
            row = self._propose(draft, msg.sender, now)
            if revised is not None: self._move(revised, "rejected", reason="revised", replaced_by=row["code"])
        self._last_draft_code = row["code"]
        self._proposal_reply(row, draft, prefix, notes)
        return "proposed"

    def _photo(self, msg, now, last_try=False) -> str:  # NB-AV-09: store one photo, then open (or name) its needs-details draft
        if msg.attachments != 1: return self._reply(media.REPLIES["many"]) or "attachment-many"
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)  # HASS-OWNERS-2: nothing fetched or stored
        try: data = self.photos.fetch(msg.provider_id, 1)[0]  # NB-AV-11: an empty/short answer is a failure too
        except Exception:  # never applied or read without the photo: retry via the inbox, or one reply on the last try
            if not last_try: raise AttachmentPending("fetch") from None
            return self._reply(FETCH_FAILED) or "attachment-failed"
        try:
            media.check_photo(data)  # NB-AV-10: all checks before any write
            sha = media.store_original(self.settings["mediaRoot"], data,
                                       received_at=msg.received_at or _iso(now), source="owner-chat")["sha256"]
        except media.Refused as exc:
            return self._reply(exc.reply) or f"photo-refused:{exc.code}"
        dup = self._drafts("state IN ('proposed', 'needs-details') AND ops_json LIKE ?", f'%"photo": "{sha}"%')
        if dup: return self._reply("I already have that photo, and I'm waiting on you. " + (
            dup[0]["summary"] if dup[0]["state"] == "needs-details" else "It's in a change waiting for your yes.")) or "photo-duplicate"
        caption = msg.text.replace("\ufffc", "").strip()  # handled as the next text, in this same transaction
        try:  # H12: a photo that is an active or hidden product's picture opens no draft; unreadable worktree: as before
            image = re.compile(rf"assets/products/photo-{sha[:16]}\.(jpg|png)")
            on = next((p for p in sorted((p for p in load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                       .products if isinstance(p, dict)), key=lambda p: str(p.get("id")))
                       if p.get("status") in ("active", "hidden") and isinstance(p.get("image"), str)
                       and image.fullmatch(p["image"])), None)
            if on is not None and "id" not in on: raise KeyError("id")  # a matching record must still be readable
            said = on and f"That photo is already on {q(on['name'])}. To change that product, tell me what to change."
        except (OSError, ValueError, KeyError, TypeError, editor_mod.UnsafeState): said = None  # no id/name: as unreadable
        if said:
            self._reply(said)
            return self._request(Inbound(**{**vars(msg), "text": caption}), now) if caption else "photo-on-product"
        if self.skills_mode != dispatch_mod.DEFAULT_MODE and self.dispatch.photo_skills():  # SKILLS-FW-3 (spec 2.7): the photo joins the open request
            as_text = Inbound(**{**vars(msg), "text": caption})
            done = self.dispatch.photo(as_text, now, sha, caption)
            return done if done is not None else self._request(as_text, now)  # no skill yet: the caption is the next text of that request
        self.db.execute("INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, missing_json) VALUES"
                        " (?, 'needs-details', ?, ?, ?, ?, ?, ?)", (code := self._code(sha), json.dumps(
                            [{"op": "product.set_photo", "args": {"photo": sha}}]), PHOTO_QUESTION, msg.sender, msg.chat, _iso(now),
                            json.dumps(["id", "imageAlt"])))  # AV0007-03: set_photo's required args besides the photo
        self._reply(PHOTO_QUESTION)
        if self.labels is not None: self._label_job = (code, sha, self.db.execute("SELECT last_insert_rowid()").fetchone()[0])
        if not caption: return "photo-draft"
        self._photo_draft = code  # AV1052-10: if the reader fails on this caption, status names this draft
        try: return self._request(Inbound(**{**vars(msg), "text": caption}), now)
        finally: self._photo_draft = None

    def _read_label(self, code, sha, reply_id):  # AV1537-15: a read label joins the waiting question; never ops
        try:
            web = Path(media.web_copy(self.settings["mediaRoot"], sha)["path"]).read_bytes()  # metadata-free copy only
            products = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content").products
            found = self.labels.read(web, sorted({p["category"] for p in products if isinstance(p.get("category"), str)}))
        except Exception: return  # noqa: BLE001 - no label is today's reply exactly
        line = label_reader.question(found, self._makers(), products) if found else None  # AVB-10: matching records
        with self._tx():
            if line and self.db.execute("UPDATE drafts SET summary = summary || ? WHERE code = ? AND state = "
                                        "'needs-details'", (" " + line, code)).rowcount:
                self.db.execute("UPDATE outbox SET text = text || ? WHERE id = ? AND sent_at IS NULL", (" " + line, reply_id))

    def _outcome(self, row, out, now):
        """Store the apply result and its reply in one transaction (before anything is sent)."""
        with self._answer_to(_row_chat(row)): return self._outcome_to(row, out, now)

    def _outcome_to(self, row, out, now):
        result = out.get("result")
        if result in ("applied", "already-applied"):
            self._move(row, "applied", commit=out.get("commit"))
            for call in json.loads(row["ops_json"]):  # an applied undo closes the draft it reverted
                if call.get("op") == "history.revert":
                    for orig in self._drafts("change_id = ? AND state IN ('applied', 'verified')",
                                             call["args"].get("changeId")):
                        self._move(orig, "reverted", reason=f"undone by {row['code']}")
            if self.previewer is None or self.settings.get("liveSite"):
                self._reply(answers.applied_text(row["code"], row["summary"], live_site=self.settings.get("liveSite")))
            # with a previewer the reply waits for verify(): nothing says it worked before it is checked
        elif result == "stale":
            again = self.editor.prepare(json.loads(row["ops_json"]))
            if again["result"] == "ok":
                new = self._propose(again["draft"], row["sender"], now)
                self._move(row, "rejected", reason="stale", replaced_by=new["code"])
                self._proposal_reply(new, again["draft"], "The website changed while that was waiting, so I've written it up again. "
                                                          "Please look it over:\n")
            else:
                self._move(row, "rejected", reason="stale")
                self._reply("The website changed while that was waiting, and now I can't make this change. Nothing changed. "
                            + self._plain(_reason(again)))
        else:
            refused = self.settings.get("liveSite") and answers.live_refused(out.get("reason"))  # HASS-LIVE-PLAN-1: the real reason, in words
            # A failed draft is never approved again (yes only targets `proposed`), so recovery is a fresh proposal with
            # its own code, written up from the same change; the owner's next yes (and code, when needed) approves that one.
            again = None if refused else self.editor.prepare(json.loads(row["ops_json"]))
            new = self._propose(again["draft"], row["sender"], now) if again and again["result"] == "ok" else None
            self._move(row, "failed", reason=_reason(out), **({"replaced_by": new["code"]} if new else {}))
            self._problem("error", "save-failed")
            if refused: self._reply(refused)
            elif new:
                self._proposal_reply(new, again["draft"], "I couldn't save that change, so nothing changed. "
                                                          "I've written it up again so you can try once more:\n")
            else:
                self._reply("I couldn't save that change, so nothing changed. Please send me the request again in a minute.")

    def recover(self) -> list:
        """Settle drafts left `approved` by a crash from the editor's change record, then verify (once) any applied
        draft with no verification record. Never calls apply again."""
        rows = self._drafts("state = 'approved'")
        if rows:
            if hasattr(self.editor, "recover"): self.editor.recover()  # settles journals; never re-applies
            with self._tx():
                for row in rows:
                    change = self.editor.show(row["change_id"]).get("change") or {}
                    if change.get("state") == "applied":
                        self._outcome(row, {"result": "applied", "commit": change.get("commit")}, self._now())
                    else:
                        self._move(row, "failed", reason=INTERRUPTED)
                        with self._answer_to(_row_chat(row)): self._reply(answers.recovered_text(row["code"], live_site=self.settings.get("liveSite")))
        self._verify_pending()
        return [self._row(r["row_id"])["state"] for r in rows]

    # -- H06: checked results, history and undo ------------------------------------------------------------------
    def verify(self, row):
        """(screenshot path, None) when the worktree is current, the migration checks pass and the result
        screenshot's checks pass; otherwise (None, error)."""
        wt = editor_mod._load(str(self.sdir))[2]
        try:
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            stale = sitegen.stale_paths(content, wt)
        except ContentError as exc:
            return None, "; ".join(exc.problems)
        problems = [f"generated file out of date: {p}" for p in stale] + migration_check.run_checks(wt)[0]
        if problems: return None, "; ".join(problems)
        change = self.editor.show(row["change_id"]).get("change") or {}
        if not change.get("records"): return None, "no change record"
        files = {p: (wt / p).read_bytes() for p in editor_mod.GENERATED_PATHS}  # the committed files
        picked, png, unshown = [], None, []  # AV1737-08: each touched record with a distinct target, in order
        for record in change["records"]:
            target = preview_mod.target_for(record, shop_today(), store=content.store)  # the store the committed files were generated from
            if all(target != t for _r, t in picked): picked.append((record, target))
        for i, (record, target) in enumerate(picked[:VERIFY_MAX], 1):
            shot = self.previewer.capture(files, target, self.sdir / "screenshots" /
                                          f"{row['change_id']}-result{'' if i == 1 else f'-{i}'}.png")
            if not shot["ok"]: return None, f"{record['collection']} {record['key']}: {shot['error']}"
            png = shot["png"] if i == 1 else png  # the reply keeps the first record's screenshot
            unshown.append(bool(shot.get("unshown")))  # AV1222-06: a route /hike does not show was not checked
        if picked[VERIFY_MAX:]:
            print(f"verify {row['change_id']}: over {VERIFY_MAX} records, not checked: "
                  + ", ".join(f"{r['collection']} {r['key']}" for r, _t in picked[VERIFY_MAX:]), file=sys.stderr)
        return png, None, unshown

    def _verify_pending(self):
        if self.previewer is None: return
        for row in self._drafts("state = 'applied' AND checked_at IS NULL"):
            png, error, *flags = self.verify(row)  # outside the transaction; the result and reply are stored together
            unshown = flags[0] if flags else []
            with self._tx(), self._answer_to(_row_chat(row)):
                if png:
                    self._move(row, "verified", screenshot=png, checked_at=_iso(self._now()))
                    text = answers.applied_text(row["code"], row["summary"], checked=not (unshown and all(unshown)), live_site=self.settings.get("liveSite"))
                    if not self.settings.get("liveSite"): self._reply(text + ("\n" + answers.ROUTE_UNSHOWN if any(unshown) else ""), [png])
                else:  # the raw diagnostic stays on the row; the owner gets plain words (SHOP-4)
                    self.db.execute("UPDATE drafts SET reason = ?, checked_at = ? WHERE row_id = ?",
                                    (f"not verified: {error}", _iso(self._now()), row["row_id"]))
                    if not self.settings.get("liveSite"): self._reply(answers.applied_text(row["code"], row["summary"], error=error, live_site=self.settings.get("liveSite")))

    def screenshot(self, change_id) -> str | None:
        row = self.db.execute("SELECT screenshot FROM drafts WHERE change_id = ? AND state IN ('applied', 'verified') "
                              "AND screenshot IS NOT NULL ORDER BY row_id DESC LIMIT 1", (change_id,)).fetchone()
        return row[0] if row else None

    def _visible_undo(self, r) -> bool:
        """`undo` looks at this chat's own changes; with several owners at the whole site's (one site, one last change)."""
        return self._shared or self._mine(r)

    def _history_line(self, r) -> str:
        """One `history` line. HASS-OWNERS-2: with several owners it says whose change it was (`Mike's change`, `Your change`)."""
        words = f"{q(r['summary'])}: {answers.history_words(dict(r), self._install(r))}"
        return f"- {self._whose(r['chat'])}, {words}" if self._shared else f"- {words}"

    def _history_search(self, query: str) -> str:
        """AV2152-02: up to ten newest owner-approved changes whose summary holds every word; read-only."""
        words = catalog._fold(query).split() if 1 <= len(query) <= HISTORY_TEXT_MAX and query.isprintable() else []
        if not words:
            self._reply(HISTORY_USAGE)
            return "history"
        found = []
        for r in self.db.execute(f"SELECT * FROM drafts WHERE state IN ({', '.join('?' * len(HISTORY_STATES))}) "
                                 "ORDER BY row_id DESC", HISTORY_STATES):
            folded = catalog._fold(r["summary"])
            if all(w in folded for w in words): found.append(r)
            if len(found) >= HISTORY_SEARCH_MAX: break
        self._reply("\n".join(["These match:"] + [self._history_line(r) for r in found]) if found else f"I found no changes that match {q(query)}.", long_ok=True)
        return "history"

    def _command(self, msg, now, verb, code) -> str:
        if verb == "help":
            registry = self.dispatch.registry if self.dispatch else None
            self._reply(HELP_TEXT + "\n\n" + capabilities.help_section(registry), long_ok=True)
            return "help"
        if verb in ("status", "pause", "resume"): return self._control(msg, now, verb)
        if verb == "find": return self._find(code) if 1 <= len(code) <= FIND_TEXT_MAX else (self._reply(FIND_USAGE), "find")[1]
        if verb == "show": return self._reply(*self._show(code, now), long_ok=True) or "show"
        if verb == "report": return self._report(msg, now)
        if verb == "post": return self._post(code)
        if verb == "margin": return self._margin(code)
        if verb == "hidden": return self._hidden()
        if verb == "listing": return self._listing(code)
        if verb == "photos": return self._photos_to_take()
        if verb == "backlog": return self._backlog_list()  # SKILLS-FW-3
        if verb == "history" and code is not None: return self._history_search(code)
        if verb == "history":
            rows = self.db.execute(f"SELECT * FROM drafts WHERE state IN ({', '.join('?' * len(HISTORY_STATES))}) "
                                   "ORDER BY row_id DESC LIMIT ?", (*HISTORY_STATES, HISTORY_MAX)).fetchall()
            self._reply("\n".join(["Here's what we changed lately:"] + [  # SHOP-4: where it is now instead of the commit
                self._history_line(r) for r in rows]) if rows else "We haven't made any changes yet.", long_ok=True)
            return "history"
        done = [r for r in self._drafts("change_id IS NOT NULL AND \"commit\" IS NOT NULL")  # AV0022-07: skip undos
                if self._visible_undo(r) and (code is None and r["state"] in ("applied", "verified") and not _is_undo(r) or r["code"] == code)]
        # HASS-LIVE-PLAN-1: only the asking owner's own changes (by chat) can be taken back, with or without a code
        if not done:
            self._reply("I don't have a change with that code to undo." if code else "There's nothing to undo.")
            return "no-target"
        target = done[-1]
        theirs = self._shared and not self._mine(target)  # HASS-OWNERS-2: the site's last change was another owner's
        if theirs and code is None:  # a bare `undo` never reaches another owner's work: it says whose it is, and how to ask for it
            self._reply(f"The last change on the website was {self._whose(target['chat'], False)}: {q(target['summary'])}. I haven't undone anything. "
                        f"If you do want it undone, say {q('undo ' + target['code'])}.", long_ok=True)
            return "undo-other"
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)
        out = self.editor.prepare([{"op": "history.revert", "args": {"changeId": target["change_id"]}}])
        if out["result"] != "ok":
            self._reply(self._plain(_reason(out), "undo that"))
            return "not-drafted"
        same = [r for r in self._drafts("state = 'proposed' AND change_id = ?", out["draft"]["change_id"]) if self._mine(r)]
        row = same[0] if same else self._propose(out["draft"], msg.sender, now)
        self._proposal_reply(row, out["draft"], f"To undo {self._whose(target['chat'], False)}, I'd change it back:\n" if theirs else "To undo that, I'd change it back:\n")
        return "proposed"

    def _report(self, msg, now) -> str:
        """AV1322-05 (F04): the morning shelf report from the writer worktree content, Pacific today; read-only for the site.
        HASS-SHELFCHECK-FLOW-1: when today's shelf check is missing, the first report of the day also asks the owner
        SHELF_ASK (a yes then drafts the check; nothing is written by asking)."""
        ask = False
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            facts = morning_report.facts(content, shop_today(now))
            text = morning_report.render(facts)
            ask = facts["checked_on"] != shop_today(now).isoformat() and not facts["future"] and self._report_asked(msg, now)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "report-unreadable")
            text = "I can't read the shelf report right now, so I can't tell you what's on the shelves. Nothing has changed."
        waiting = self._waiting_lines(now) + [l for l in self._photo_lines(now) if "waiting for details" in l]
        self._reply(f"{text}\n\n" + "\n".join(["Waiting for you:"] + waiting if waiting else ["Nothing is waiting for you."])
                    + (f"\n\n{SHELF_ASK}" if ask else ""), long_ok=True)
        return "report"

    def _report_asked(self, msg, now) -> bool:
        """HASS-SHELFCHECK-FLOW-1: True the first time today that the report asks SHELF_ASK (and keeps it open); once a day."""
        day = shop_today(now).isoformat()
        self.db.execute(CONTROL)
        if (row := self.db.execute("SELECT value FROM control WHERE name = 'shelf-asked'").fetchone()) and row["value"] == day: return False
        self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('shelf-asked', ?, ?, ?)"
                        " ON CONFLICT(name) DO UPDATE SET value = excluded.value, set_at = excluded.set_at,"
                        " provider_id = excluded.provider_id", (day, _iso(now), msg.provider_id))
        self._open_ask(msg, now, [], {"ops": [], "revises": None})
        return True

    def _margin(self, rest) -> str:
        """AV1102-12 (F03): margins.render for one purchase line, text in and text out. Read-only: nothing is stored or
        drafted, no interpreter call or usage count; works while paused."""
        found = MARGIN_RE.fullmatch(rest)
        by_id = None if found else MARGIN_ID_RE.fullmatch(rest.strip())  # AV1222-10: the saved cost of a product (by name or id)
        try:
            text = margins.say(margins.compute(found[1], found[2], found[4] or "0", found[3])) if found else \
                self._margin_saved(*by_id.groups()) if by_id else MARGIN_USAGE
        except margins.InputError as exc:
            self._problem("did-not-understand", "margin-numbers")
            text = "I couldn't work that out. " + margins.plain_input_error(exc)
        self._reply(text)
        return "margin"

    def _margin_saved(self, ident, margin, shrink) -> str:
        """AV1222-10: margins for the saved cost.<id> (read-only; the memory table is not created for a read)."""
        has_table = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
        if self.memory is None and has_table: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        typed, ident = ident, self._pick("product", ident)
        row = next((r for r in self.memory.list() if r["key"] == f"cost.{ident}"), None) if has_table else None
        if row is None: return f"I don't have a cost saved for {q(typed)}. Tell me first, like " + q(f"cost {typed}: 24 for 12") + "."
        pack, _, units = row["value"].partition(" for ")
        since = datetime.fromisoformat(row["created_at"]).astimezone(LOCAL_TZ)
        return f"Using the cost you gave me {voice.natural(since, self._now())}.\n" + margins.say(margins.compute(pack, units, shrink or "0", margin))

    def _listing_names_something(self, text) -> bool:
        """Like post, a multiword listing needs a known name; unreadable content gets the usual read error."""
        try:
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return True
        return any(self._pick(kind, text, content) != text for kind in ("product", "maker")) \
            or self._pick_hike(content, text) != text or self._pick_hike(content, text, "routeIdeas") != text \
            or self._title_matches(content, text)

    @staticmethod
    def _title_matches(content, text) -> bool:
        """True when some hike or route idea title holds every word, even if several do (the listing then says it is not sure)."""
        words = catalog._fold(text).split()
        if not words or not isinstance(content.community, dict): return False
        return any(isinstance(e, dict) and isinstance(e.get("title"), str) and all(w in catalog._fold(e["title"]) for w in words)
                   for key in ("events", "routeIdeas") for e in (content.community.get(key) if isinstance(content.community.get(key), list) else []))

    def _post_names_something(self, text) -> bool:
        """HASS-VOICE-1: post takes a name, so several words only count as the post command when they point at one product
        or hike; anything else keeps going to the interpreter as before. Unreadable content counts as a name so the usual
        'can't read' answer follows."""
        try:
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return True
        words = text.split()
        if words[0].lower() == "hike" and len(words) == 2: return True  # one id after 'hike': the usual 'I don't know a hike' answer
        if words[0].lower() == "hike": return self._pick_hike(content, text[4:].strip()) != text[4:].strip()
        return self._pick("product", text, content) != text

    def _post(self, pid) -> str:
        """AV1322-07 (F07 prepare half): social_draft's caption for one active product plus its site photo, from the
        writer worktree content. Read-only: nothing is posted, scheduled, written or drafted; works while paused."""
        photo = None
        if pid.lower().split(None, 1)[:1] == ["hike"]: return self._post_hike(pid[4:].strip())
        try:
            if not pid: raise LookupError
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            out = social_draft.build(content, self._pick("product", pid, content), wt / "storefront-mockup")
            if out["draft"] and stat.S_ISREG(os.lstat(photo := wt / "storefront-mockup" / out["image"]).st_mode):
                text = f"Here's a post you can copy. I haven't posted anything.\n{q(out['caption'])}\nWhat the photo shows: {q(out['alt'])}"
            else:  # a refusal, or a photo that is itself a link: never attached
                reason = out.get("reason", "no photo on the site")
                text = POST_REFUSALS[reason].format(id=q(pid)) if reason in POST_REFUSALS else POST_CANT.format(id=q(pid))
                if reason not in POST_REFUSALS: self._problem("could-not-do", "post-refused")
                photo = None
                if reason == "cannot read content": raise OSError
        except LookupError:
            text = POST_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text, photo = CANT_READ, None
        self._reply(text, [str(photo)] if photo else [], long_ok=True)
        return "post"

    def _post_hike(self, hid) -> str:
        """AV1222-11 (F07): social_draft.build_hike's caption for one scheduled upcoming hike. Read-only, nothing is stored."""
        try:
            if not hid: raise LookupError
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            out = social_draft.build_hike(content, self._pick_hike(content, hid), self._now())
            if out["draft"]: text = f"Here's a post you can copy. I haven't posted anything.\n{q(out['caption'])}"
            elif out["reason"] == "cannot read content": raise OSError
            else:
                text = HIKE_REFUSALS[out["reason"]].format(id=q(hid)) if out["reason"] in HIKE_REFUSALS else POST_CANT.format(id=q(hid))
                if out["reason"] not in HIKE_REFUSALS: self._problem("could-not-do", "post-refused")
        except LookupError: text = HIKE_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text = CANT_READ
        self._reply(text, long_ok=True)
        return "post"

    def _pick(self, kind, text, content=None) -> str:
        """The id for what Mike typed: an exact id or maker key as before, else the one record whose name or nickname fits
        (catalog.lookup); anything else comes back unchanged so the usual 'I don't know that one' answer follows."""
        try:
            content = content or load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            ids = {p["id"] for p in content.products} if kind == "product" else set(content.makers)
            if text in ids: return text
            has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            found = catalog.lookup(content, kind, text, aliases=self.aliases() if has_memory else None)
            matched = found.get("match")
            # Maker keys keep their exact case; only names and nicknames are folded.
            if kind == "maker" and isinstance(matched, str) and not found.get("via") \
                    and catalog._fold(text) not in catalog._fold(content.makers[matched]["name"]):
                return text
            return matched if isinstance(matched, str) else text
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return text

    def _pick_hike(self, content, text, key="events") -> str:
        """A hike's (or, with key="routeIdeas", a route idea's) id from what Mike typed: an exact id, else the one whose
        title holds every word."""
        events = content.community.get(key) if isinstance(content.community, dict) else None
        events = [e for e in events if isinstance(e, dict)] if isinstance(events, list) else []
        if any(e.get("id") == text for e in events): return text
        words = catalog._fold(text).split()
        hits = [e for e in events if words and isinstance(e.get("title"), str) and all(w in catalog._fold(e["title"]) for w in words)]
        return hits[0]["id"] if len(hits) == 1 and isinstance(hits[0].get("id"), str) else text

    def _find(self, query) -> str:
        """AV1537-04: read-only lookup, products then makers; id/name/status only, never a draft or a memory table."""
        try:  # the current catalog, read from the writer worktree as _hike_lines does
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            try:  # AV1322-04: a malformed event/route idea is worded or skipped below; any other problem is unavailable
                validate(content, wt / "storefront-mockup")
            except ContentError as exc:
                if any(not p.startswith(("events[", "routeIdeas[")) for p in exc.problems): raise
            shown = []  # the fields a reply line repeats get the validator's text checks: no line break/markup injection
            for key in ("events", "routeIdeas"):
                for i, r in enumerate(content.community[key] if isinstance(content.community[key], list) else []):
                    for field in ("id", "title", "status") if isinstance(r, dict) else ():
                        if r.get(field) is not None and (field != "title" or isinstance(r[field], str)):
                            checked_text(shown, f"{key}[{i}].{field}", r[field])
            if shown: raise ContentError(shown)
            has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            aliases, lines, capped = self.aliases() if has_memory else {}, [], False
            records = {"product": {p["id"]: (p["name"], p["status"]) for p in content.products},
                       "maker": {k: (m["name"], "hidden" if m.get("hidden") else "visible") for k, m in content.makers.items()}}
            for kind in ("product", "maker"):
                found = catalog.lookup(content, kind, query, aliases=aliases)
                ids = [found["match"]] if "match" in found else [c["id"] for c in found["candidates"]]
                capped |= len(ids) >= catalog.MAX_CANDIDATES
                lines += [f"{q(records[kind][i][0])} ({STATUS_PLAIN.get(records[kind][i][1], 'not sure')}"
                          + (", your nickname" if found.get("via") else "") + ")" for i in ids]
            words = catalog._fold(query).split()  # AV1322-04: hikes by start, then route ideas by title
            def hits(recs): return [r for r in recs if isinstance(r, dict) and isinstance(r.get("title"), str)
                                    and words and all(w in catalog._fold(r["title"]) for w in words)]
            def when(event):  # Pacific start, or None when startsAt does not parse (never raises)
                try:
                    at = datetime.fromisoformat(event["startsAt"].replace("Z", "+00:00"))
                    return at.astimezone(LOCAL_TZ) if at.tzinfo else None
                except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
                    return None
            dated = sorted(((e, when(e)) for e in hits(content.community["events"])),
                           key=lambda pair: (pair[1] is None, pair[1].timestamp() if pair[1] else 0))
            lines += [f"{q(e['title'])} (hike, " + (voice.natural(at, self._now()) if at else "no date I can read")
                      + f", {STATUS_PLAIN.get(e.get('status'), 'not sure')})" for e, at in dated]
            lines += [f"{q(r['title'])} (route idea, {STATUS_PLAIN.get(r.get('status'), 'not sure')})"
                      for r in sorted(hits(content.community["routeIdeas"]), key=lambda r: catalog._fold(r["title"]))]
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "find"
        more = len(lines) - FIND_MAX
        tail = ["There are more. Add a word to narrow it down."] if more > 0 or capped else []
        self._reply("\n".join(lines[:FIND_MAX] + tail) if lines
                    else f"I couldn't find anything called {q(query)}.", long_ok=True)
        return "find"

    def _listing(self, ident) -> str:
        """AV1622-09 (H17): read-only view of one saved product, maker, hike or route idea by exact id, from the writer
        worktree content (strictly validated). Nothing is drafted or stored; works while paused."""
        if not ident:
            self._reply(LISTING_USAGE)
            return "listing"
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            validate(content, wt / "storefront-mockup")
            typed, ident = ident, self._pick("product", ident, content)
            if not any(p.get("id") == ident for p in content.products): ident = self._pick("maker", typed, content)
            if ident == typed: ident = self._pick_hike(content, typed)
            if ident == typed: ident = self._pick_hike(content, typed, "routeIdeas")
            found = [("product", p) for p in content.products if p.get("id") == ident]
            found += [("maker", m) for k, m in content.makers.items() if k == ident]
            found += [(kind, r) for kind, key in (("hike", "events"), ("route idea", "routeIdeas"))
                      for r in content.community[key] if r.get("id") == ident]
            if len(found) != 1: text = LISTING_NONE if not found else LISTING_MANY
            else:
                kind, rec = found[0]
                nope = "nothing yet"
                if kind == "product":
                    maker = content.makers.get(rec.get("producerKey"))
                    desc = rec.get("description")
                    if isinstance(desc, str) and desc:  # held records skip validate_products' description check
                        bad = []
                        checked_text(bad, "description", desc)
                        if bad: raise ValueError(bad[0])
                    desc = nope if not isinstance(desc, str) or not desc else desc[:LISTING_DESC_MAX] + ("…" if len(desc) > LISTING_DESC_MAX else "")
                    avail = (sitegen.availability_label(rec, content.store, shop_today(self._now())) or "not confirmed") \
                        if rec["status"] == "active" else "not showing"
                    fields = [("Name", rec["name"]), ("Maker", (maker or {}).get("name") or rec.get("brand") or nope),
                              ("Shelf", SHELF_LABELS.get(rec.get("category"), rec.get("category")) or nope), ("Description", desc),
                              ("Availability", avail), ("Status", STATUS_PLAIN.get(rec["status"], "not sure"))]
                elif kind == "maker":
                    fields = [("Name", rec["name"]), ("Place", rec.get("place") or nope),
                              ("Products showing", sum(1 for p in content.products if p["status"] == "active" and p.get("producerKey") == ident)),
                              ("Status", "hidden" if rec.get("hidden") else "on the website")]
                elif kind == "hike":
                    fields = [("Title", rec["title"]), ("Starts", voice.natural_iso(rec["startsAt"], self._now())),
                              ("Status", STATUS_PLAIN.get(rec["status"], "not sure")),
                              ("Meeting place", rec.get("meetingPoint") or nope), ("Guest limit", rec.get("capacity", nope))]
                else:
                    fields = [("Title", rec["title"]), ("Place", rec.get("place") or nope), ("Status", STATUS_PLAIN.get(rec["status"], "not sure"))]
                text = "\n".join(["This is from my saved copy, not a live look at the website:"] + [f"{k}: {q(v)}" for k, v in fields])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text = CANT_READ
        self._reply(text, long_ok=True)
        return "listing"

    def _photos_to_take(self) -> str:
        """AV0222-04 (H10/H17): active products whose image is not an installed photo-<16 hex> file, by shelf in site order;
        saved content only, read-only, works while paused. A filename convention, not proof of where a picture came from."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            order = tuple(SHELF_LABELS)
            todo = sorted((p for p in content.active_products() if not HOME_IMAGE_RE.fullmatch(p["image"])),
                          key=lambda p: (order.index(p["category"]), p["name"].casefold(), p["id"]))
            lines, shelf = [], None
            for p in todo[:PHOTOS_TO_TAKE_MAX]:
                lines.append(f"- {q(' '.join(str(p['name']).split()))} ({SHELF_LABELS[p['category']]})")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "photos"
        if not todo:
            self._reply("Every product on the website has your own photo.")
            return "photos"
        more = ["When you've sent those, ask again and I'll show the next few."] if len(todo) > PHOTOS_TO_TAKE_MAX else []
        self._reply("\n".join(["Some products still show a stock picture instead of your own photo. The first few:"] + [
            l if l.startswith("- ") else f"{l}" for l in lines] + more
            + ["To replace one, send a photo with the product's name as the caption."]), long_ok=True)
        return "photos"

    def _hidden(self) -> str:
        """AV1222-13 (H03): read-only list of hidden products then hidden makers; held products and visible makers never."""
        try:  # the current catalog from the writer worktree, as _find
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            one = lambda name: " ".join(str(name).split())  # stored text on one line
            lines = [f"- {q(one(p['name']))}" for p in sorted(content.products, key=lambda p: p["id"])
                     if p["status"] == "hidden"]
            first = next((one(p["name"]) for p in sorted(content.products, key=lambda p: p["id"]) if p["status"] == "hidden"), None)
            lines += [f"- {q(one(m['name']))} (maker)" for k, m in sorted(content.makers.items()) if m.get("hidden") is True]
            first = first or next((one(m["name"]) for k, m in sorted(content.makers.items()) if m.get("hidden") is True), "")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "hidden"
        more = ["And a few more."] if len(lines) > HIDDEN_MAX else []
        self._reply("\n".join(["These are hidden right now:"] + lines[:HIDDEN_MAX] + more
                               + ["To bring one back, tell me, like " + q(f"Bring back {first}") + "."])
                    if lines else "Nothing is hidden right now.", long_ok=True)
        return "hidden"

    def _show(self, code, now) -> tuple:
        """AV0022-08 (H17): (text, attachments) repeating one draft's stored proposal lines and its saved screenshot.
        Read-only: no state move, no expiry sweep, never prepared or rendered again; works while paused."""
        if not code:  # `show` on its own: the newest change that is waiting for a yes
            waiting = [r for r in self._drafts("state = 'proposed'") if self._mine(r) and self._expiry(r) > now]
            if not waiting: return NOTHING, []
            code = waiting[-1]["code"]
        if not re.fullmatch(r"[0-9a-f]{4,12}", code): return "Say " + q("show") + " on its own to see the change that is waiting for you.", []
        if (row := self._by_code(code)) is None: return "I don't have a change with that code.", []
        state = row["state"]
        if state in ("proposed", "needs-details") and self._expiry(row) <= now:  # lapsed, not swept: words it only
            return self._state_text({**dict(row), "state": "expired", "expires_at": _iso(self._expiry(row))}), []
        if state == "needs-details": return "I'm waiting for details: " + row["summary"], []
        if state not in ("proposed", "applied", "verified"): return self._state_text(row), []
        try:
            out = self.editor.show(row["change_id"])
            rec = (out.get("draft") or out.get("change") or {}) if out.get("result") == "ok" else {}
            draft = {"records": rec["records"], "warnings": rec.get("warnings"), "ops": rec.get("ops") or json.loads(row["ops_json"])}  # ops: the live check reads them
            if state == "proposed":
                text = proposal_text(code, draft, row["expires_at"], self._repeat(row), "Here's the change that is waiting:", undo=_is_undo(row), live_site=self.settings.get("liveSite"), now=now,
                                     reasons=self._live_reasons(draft) if self.settings.get("liveSite") else None)
                shot = self.sdir / "screenshots" / f"{row['change_id']}-proposal.png"
            else:
                text, shot = "\n".join(["Here's what was saved:"] + _record_lines(draft, _is_undo(row), done=True)), row["screenshot"]
            return text, [str(shot)] if shot and Path(shot).is_file() else []
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            return "I can't find the details of that change any more.", []

    # -- H15: remember, forget, memory ---------------------------------------------------------------------------
    def _backlog_table(self) -> bool:
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'backlog'").fetchone() is not None

    def _backlog_list(self) -> str:
        """SKILLS-FW-3 (spec 3.32): the last ten things Hass could not do, newest first, as number, day and one line. Read-only;
        never the stored message. No table made to answer it."""
        from hass.skills.backlog import EMPTY_LIST, Backlog
        rows = Backlog(self.db, self._now).rows() if self._backlog_table() else []
        if not rows:
            self._reply(EMPTY_LIST)
            return "backlog"
        def day(iso):  # "Nov 8": the owner never sees a computer date
            try: return f"{datetime.fromisoformat(iso):%b} {datetime.fromisoformat(iso).day}"
            except (TypeError, ValueError): return "a day I can't read"
        self._reply("Written down so far, newest first:\n" + "\n".join(f"{r['id']}. {day(r['received_at'])} - {r['summary']}" for r in rows)
                    + "\nSay " + voice.quote("forget backlog.3") + " (with that number) to remove one.")
        return "backlog"

    def _backlog_forget(self, number: int) -> str:
        """`forget backlog.<n>`: remove that one row (numbers are never reused). Never more than one row, never the whole list."""
        from hass.skills.backlog import FORGOTTEN, NOT_THERE, Backlog
        done = self._backlog_table() and Backlog(self.db, self._now).forget(number)
        self._reply(FORGOTTEN if done else NOT_THERE)
        return "backlog-forgot" if done else "backlog-none"

    def _memory(self, msg, verb, key, value) -> str:
        """Owner-stated facts on this connection inside the message's transaction; a store ValueError undoes only
        that op's savepoint and the message is still recorded. The interpreter reads notes other than PRIVATE_PREFIXES as preferences (AV1102-09); never facts or claims."""
        if verb == "forget" and re.fullmatch(r"backlog\.[0-9]{1,9}", key): return self._backlog_forget(int(key[8:]))  # SKILLS-FW-3
        if verb == "memory":  # AV0222-05: read-only; no memory table is created to answer it
            has_table = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            if has_table and self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
            every = self.memory.list() if has_table else []
            rows = [r for r in every if not r["key"].startswith("alias.")]
            aliases = [r for r in every if r["key"].startswith("alias.")]
            lines = [f"- {q(r['key'])}: {q(r['value'])} (since {voice.natural(datetime.fromisoformat(r['created_at']), self._now())})"
                     for r in rows[:MEMORY_LIST_MAX]]
            more = ["And a few more."] if len(rows) > MEMORY_LIST_MAX else []
            notes = "\n".join(["Notes I'm keeping:"] + lines + more) if rows else "I'm not keeping any notes."
            amore = ["And a few more."] if len(aliases) > ALIAS_LIST_MAX else []
            self._reply("\n".join([notes] + (["Nicknames:"] + self._alias_lines(aliases[:ALIAS_LIST_MAX]) + amore if aliases else
                                            ["I don't have any nicknames."])), long_ok=True)
            return "memory-list"
        if self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        if verb == "alias": return self._alias(msg, key, value)
        if verb == "cost": return self._cost(msg, key, value)
        valid = memory_mod.KEY_RE.fullmatch(key) is not None
        if verb == "forget":
            if value == "spaced" and valid and key.startswith("alias."):  # AV1352-07: `forget alias <name>`: alias or note
                note = "alias-" + key[6:]
                has_alias, has_note = self.memory.get(key) is not None, valid and self.memory.get(note) is not None
                if has_alias and has_note:  # never guess which record to erase
                    self._reply(f"I have both a nickname and a note called {q(key[6:])}, so I forgot neither. "
                                f"Say {q('forget alias ' + key[6:])} for the nickname or {q('forget ' + note)} for the note.")
                    return "memory-ambiguous"
                if has_note: key = note
            if not valid or self.memory.get(key) is None:
                self._reply(f"I don't have a note called {q(key)}.")
                return "memory-none"
            self.memory.forget(key)
            self._reply(f"Okay, I've forgotten {q(key)}.")
            return "memory-forgot"
        problem = "A note's name can only use letters, numbers, dots and dashes, and has to be short." if not valid else None
        if valid and (not memory_mod._clean(value) or len(value) > memory_mod.MAX_VALUE):
            problem = "The note needs to be short, plain text."
        if valid and key.startswith("alias."): problem = "To save a nickname, say it like " + q("alias jam: Linn's blueberry preserves")
        if valid and key.startswith("cost."): problem = COST_USAGE  # AV1222-10
        old, source = (self.memory.get(key) if valid else None), f"owner-stated:{msg.provider_id}"
        if problem is None and old is not None and old == value:  # AVB-15: the same text again changes nothing
            self._reply(f"I already have {q(key)} as {q(value)}, so nothing changed.")
            return "memory-unchanged"
        try:
            if problem is None and old is None: self.memory.remember(key, value, "fact", source)
            elif problem is None: self.memory.correct(key, value, source)
        except ValueError as exc:
            problem = self._memory_words(exc)
        if problem:
            self._problem("could-not-do", "note-refused")
            self._reply(f"I couldn't save that. {problem}" if not problem.startswith("To save") else problem)
            return "memory-invalid"
        self._reply((f"Saved {q(key)}: {q(value)}." if old is None else f"Updated {q(key)}. It was {q(old)}.")
                    + f" Say {q('forget ' + key)} to remove it.")
        return "memory-saved" if old is None else "memory-updated"

    def _memory_words(self, exc) -> str:
        """A note store refusal in plain words (the store's own text is technical)."""
        return "Please keep it short and plain, and try again."

    def _cost(self, msg, ident, rest) -> str:
        """AV1222-10 (F03): `cost <id>: <pack> for <units>` saves memory cost.<id> = "<pack> for <units>" (the dated,
        owner-stated, private purchase cost for an existing product, any status). Never the site or the interpreter."""
        typed, product, problem, value = ident, None, None, ""
        found = COST_RE.fullmatch(rest)
        try:
            if not found or not ident: problem = COST_USAGE
            else:
                shown = margins.compute(found[1], found[2], "0", "0")["inputs"]  # validates and normalises both numbers
                value = f"{shown['pack_cost']} for {shown['units']}"
                content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                ident = self._pick("product", ident, content)
                product = next((p for p in content.products if p["id"] == ident), None)
                problem = None if product else f"I don't know a product called {q(typed)}. Try {q('find')} and a word from its name."
        except margins.InputError as exc:
            problem = "I couldn't read those numbers. " + margins.plain_input_error(exc)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            problem = CANT_READ
        key, old, source = f"cost.{ident}", None, f"owner-stated:{msg.provider_id}"
        try:
            old = self.memory.get(key) if product else None
            if product and old == value:
                self._reply(f"I already have that cost for {q(product['name'])}, so nothing changed.")
                return "memory-unchanged"
            if product: self.memory.remember(key, value, "fact", source) if old is None else self.memory.correct(key, value, source)
        except ValueError:  # e.g. an id too long for a memory key
            problem = "I couldn't keep that one. Could you say it another way?"
        if problem:
            self._problem("could-not-do", "cost-refused")
            self._reply(f"I couldn't save that. {problem}" if not problem.startswith(("Tell me", "I ")) else problem)
            return "memory-invalid"
        pack, _, units = value.partition(" for ")
        self._reply((f"Saved. {q(product['name'])} costs you {pack} for {units}." if old is None else
                     f"Updated. {q(product['name'])} now costs you {pack} for {units}.")
                    + f" That stays private and is never on the website. Say {q('forget cost.' + ident)} to remove it.")
        return "memory-saved" if old is None else "memory-updated"

    def _alias(self, msg, name, ident) -> str:
        """`alias <name>: <id>` saves memory alias.<slug> = product:<id> | maker:<key>, only if that record exists now."""
        key, found = "alias." + catalog._fold(name).replace(" ", "-"), []
        problem = ("A nickname needs to be short, with just letters, numbers and spaces." if not memory_mod._clean(name)
                   or len(name) > ALIAS_NAME_MAX or not memory_mod.KEY_RE.fullmatch(key[6:]) or not memory_mod.KEY_RE.fullmatch(key)
                   else "Which product or maker is it for? Say it like " + q("alias jam: Linn's blueberry preserves") + "." if not ident else None)
        typed = ident
        try:  # the current catalog, read from the writer worktree as _hike_lines does
            content = None if problem else load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            if content is not None:
                ident = self._pick("product", ident, content)
                if not any(p["id"] == ident for p in content.products) and ident not in content.makers: ident = self._pick("maker", typed, content)
            found = [] if problem else [("product", p, p["status"]) for p in content.products if p["id"] == ident] + (
                [("maker", m, "hidden" if m.get("hidden") else "visible")] if (m := content.makers.get(ident)) else [])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            problem = CANT_READ
        problem = problem or (f"I don't know a product or maker called {q(typed)}. Try {q('find')} and a word from its name." if not found
                              else f"{q(typed)} fits both a product and a maker. Could you say a bit more of the name?" if len(found) > 1 else None)
        if problem:
            self._problem("could-not-do", "nickname-refused")
            self._reply(f"I couldn't save that. {problem}" if not problem.startswith(("Which", "I ", "A nick")) and CANT_READ not in problem else problem)
            return "memory-invalid"
        old, value, source = self.memory.get(key), f"{found[0][0]}:{ident}", f"owner-stated:{msg.provider_id}"
        try: self.memory.remember(key, value, "fact", source) if old is None else self.memory.correct(key, value, source)
        except ValueError:
            self._problem("could-not-do", "nickname-refused")
            self._reply("I couldn't save that nickname. Could you try a shorter one?")
            return "memory-invalid"
        kind, rec, status = found[0]
        target = f"{q(rec['name'])}" + ("" if status in ("active", "visible") else f" ({STATUS_PLAIN.get(status, status)})")
        self._reply((f"Saved. {q(name)} now means " if old is None else f"Updated. {q(name)} now means ") + f"{target}."
                    + f" Say {q('forget alias ' + name)} to remove it.")
        return "memory-saved" if old is None else "memory-updated"

    def _alias_lines(self, rows) -> list:
        """AV0222-05: one line per alias row: name -> target name (id), [hidden]/[held], or what is wrong with it.
        The catalog is read once, only when there is a line to show; never echoes unsafe stored or catalog text."""
        def safe(text):
            problems = []
            checked_text(problems, "x", text)
            return isinstance(text, str) and not problems
        parsed = []
        for r in rows:
            slug = r["key"][6:]
            kind, colon, ident = str(r["value"]).partition(":")
            ok = bool(colon) and kind in ("product", "maker") and bool(ident) and len(ident) <= 80 and safe(ident)
            parsed.append((slug, kind, ident, ok))
        records = None
        if any(ok for *_, ok in parsed):
            try:
                content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                records = {"product": {p["id"]: (p["name"], p["status"]) for p in content.products},
                           "maker": {k: (m["name"], "hidden" if m.get("hidden") else "visible") for k, m in content.makers.items()}}
            except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
                records = None
        lines = []
        for slug, kind, ident, ok in parsed:
            name = slug.replace("-", " ")
            if not ok:
                lines.append(f"- {q(name)}: I can't read this one. Say {q('forget alias ' + name)} to remove it.")
            elif records is None:
                lines.append(f"- {q(name)}: I can't look up what it means right now.")
            elif (found := records[kind].get(ident)) is None:
                lines.append(f"- {q(name)}: it points to something that is no longer on the website. Say {q('forget alias ' + name)} to remove it.")
            elif not safe(found[0]):
                lines.append(f"- {q(name)}: I can't show what it means right now.")
            else:
                mark = " (hidden)" if found[1] == "hidden" else " (on hold)" if found[1] == "held" else ""
                lines.append(f"- {q(name)} means {q(found[0])}{mark}")
        return lines

    def aliases(self) -> dict:
        """Read-only H15 aliases {name: (kind, id)} from active memory rows, for catalog.lookup(aliases=…)."""
        if self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        rows = [(r["key"][6:], r["value"].partition(":")) for r in self.memory.list() if r["key"].startswith("alias.")]
        return {slug.replace("-", " "): (kind, ident) for slug, (kind, colon, ident) in rows
                if colon and kind in ("product", "maker")}

    # -- H17: status, pause changes, resume changes ----------------------------------------------------------------
    def _paused(self):
        """When changes were paused (ISO time), or None. No control table yet means never paused."""
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'control'").fetchone():
            return None
        row = self.db.execute("SELECT set_at FROM control WHERE name = 'paused'").fetchone()
        return row["set_at"] if row else None

    def _install(self, row):
        """SHOP-4: the editor change record's SHOP-2 `install` entry for a draft row; None when there is none."""
        try:
            return (self.editor.show(row["change_id"]).get("change") or {}).get("install") if row["change_id"] else None
        except (OSError, ValueError, AttributeError, editor_mod.UnsafeState):
            return None

    def _queue(self, msg) -> dict:
        """SHOP-4: drafts waiting for an OK plus inbox messages not read yet (this one excluded; inbox opened
        read-only as _photo_lines does), and approvals already under way."""
        unread, path = 0, self.sdir / "inbox.sqlite3"
        if path.is_file():
            try:
                with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True, timeout=1)) as db:
                    unread = db.execute("SELECT COUNT(*) FROM inbound WHERE state = 'pending' AND provider_id != ?",
                                        (msg.provider_id,)).fetchone()[0]
            except sqlite3.Error:
                unread = 0
        waiting = [r for r in self._drafts("state = 'proposed'") if self._expiry(r) > self._now() and self._visible(r)]
        return {"waiting": len(waiting) + unread, "applying": [r["code"] for r in self._drafts("state = 'approved'")]}

    def _control(self, msg, now, verb) -> str:
        since = self._paused()
        if verb == "status":
            self._reply(self._status(now, since), long_ok=True)
        elif verb == "pause" and since:
            self._reply(answers.stopped_state(since, self._queue(msg)))
        elif verb == "pause":
            self.db.execute(CONTROL)
            self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('paused', '1', ?, ?)",
                            (_iso(now), msg.provider_id))
            self._reply(answers.stopped_state(_iso(now), self._queue(msg)))
        elif not since:
            self._reply("Changes are already on.")
        else:  # resume never applies anything by itself
            self.db.execute("DELETE FROM control WHERE name = 'paused'")
            codes = [r["code"] for r in self._drafts("state = 'proposed'") if self._visible(r)]
            self._reply("Changes are back on." + ("\nWaiting for your yes:\n" + self._choices(codes) if len(codes) > 1 else
                                                    f"\nOne change is waiting. Reply {q('yes ' + codes[0])} to save it." if codes else ""), long_ok=True)
        return verb

    def _status(self, now, since) -> str:
        """Read-only: pause state, waiting drafts, the last apply result and confirmed guests of upcoming hikes."""
        reader = self._reader_failed_lines(now)
        lines = [f"Changes are paused since {self._when(since)}. Say {q('resume changes')} when you're ready." if since
                 else "I'm having trouble reading your messages." if reader else "Everything is ready."]
        if (cap := self.settings["interpreterDailyCap"]) is not None and self._calls(now)[1] >= 0.8 * cap:  # H22, only near the cap
            lines.append("I'm close to the number of new requests I can read today.")
        waiting = self._waiting_lines(now)
        lines += waiting or [NOTHING]
        with contextlib.suppress(OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            f = shelf.facts(load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content"), shelf.shop_today(now))
            lines.append(shelf.check_line(f))  # AV1102-05
        lines += reader
        if self.skills_mode != dispatch_mod.DEFAULT_MODE:  # SKILLS-FW-3: one plain line per open request
            lines += self.requests.status_lines(self._chat(), now, self.dispatch.registry if self.dispatch else None)
        lines += self._photo_lines(now)  # NB-AV-12: counts only, before Last change
        last = self.db.execute(  # the most recently approved change that has a result
            "SELECT d.* FROM drafts d JOIN approvals a ON a.change_id = d.change_id WHERE d.state IN"
            " ('applied', 'verified', 'failed', 'reverted') ORDER BY a.id DESC, d.row_id DESC LIMIT 1").fetchone()
        if last:  # SHOP-4: did it work, in plain words (whether it is on the website now), never the commit
            whose = " (" + self._whose(last["chat"], False) + ")" if self._shared and not self._mine(last) else ""  # HASS-OWNERS-2
            lines.append(f"Last change{whose}: {q(last['summary'])}. " + answers.did_it_work(dict(last), self._install(last), now))
        return "\n".join(lines + self._hike_lines(now))

    def _reader_failed_lines(self, now) -> list:
        """AV1052-10: the last request was not read because the reader failed; read-only, never raises."""
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'control'").fetchone():
            return []
        row = self.db.execute("SELECT set_at, value FROM control WHERE name = 'reader-failed'").fetchone()
        if not row: return []
        try:
            when = voice.natural(datetime.fromisoformat(row["set_at"]), now)
        except (ValueError, TypeError, OverflowError, OSError):
            when = "a time I can't read"
        draft = row["value"] != "1" and self._by_code(row["value"], ("needs-details",))  # a photo caption
        if draft and self._expiry(draft) > now:  # resending the photo is a duplicate while its draft is open
            return [f"I couldn't read your request from {when}. I'm keeping the photo, so just reply with the product and what the photo shows."]
        if draft:  # the draft lapsed (status does not sweep it): a reply would find nothing, so the photo goes again
            return [f"I couldn't read your request from {when}, and the photo's time ran out. Please send the photo again with its caption."]
        return [f"I couldn't read your request from {when}. Could you send it again?"]

    def _waiting_lines(self, now) -> list:
        """AV1102-11: one line per unexpired draft waiting for yes or for details; `status` and `report` share it."""
        rows = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) > now]
        lines = [f"Waiting for your yes: {q(r['summary'])} (reply {q('yes ' + r['code'])})" if r["state"] == "proposed"
                 else "I'm waiting for details: " + r["summary"] for r in rows if self._visible(r)]
        for chat in dict.fromkeys(r["chat"] for r in rows if not self._visible(r)):  # HASS-OWNERS-2: another owner's change: said, never shown
            lines.append(f"{self._who(chat)[0].upper() + self._who(chat)[1:]} has a change waiting.")
        return lines

    def _photo_lines(self, now) -> list:
        """NB-AV-12: waiting photo drafts (every op product.set_photo) and pending inbox messages with tries > 0.
        The inbox is opened read-only (never created); no file or no tries column means no line."""
        def photo_only(raw):
            try: ops = json.loads(raw)
            except (TypeError, ValueError): return False
            return isinstance(ops, list) and bool(ops) and all(
                isinstance(c, dict) and c.get("op") == "product.set_photo" for c in ops)
        n = sum(self._expiry(r) > now and photo_only(r["ops_json"]) for r in self._drafts("state = 'needs-details'") if self._visible(r))
        lines, path = [f"{'A photo is' if n == 1 else 'Some photos are'} waiting for details from you."] if n else [], self.sdir / "inbox.sqlite3"
        if not path.is_file(): return lines
        try:
            with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True, timeout=1)) as db:
                if "tries" not in {r[1] for r in db.execute("PRAGMA table_info(inbound)")}: return lines
                m = db.execute("SELECT COUNT(*) FROM inbound WHERE state = 'pending' AND tries > 0").fetchone()[0]
        except sqlite3.Error:
            return lines + ["I can't tell whether any photos are still coming in."]
        return lines + ([f"{'A photo is' if m == 1 else 'Some photos are'} still coming in."] if m else [])

    def _hike_lines(self, now) -> list:
        """Scheduled hikes after now with seat totals only (never names or emails); unknown counts are never guessed.
        AV1537-07: then scheduled hikes whose start has passed (oldest first, at most 5, no guest counts)."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            events = json.loads((wt / "hass" / "content" / "community.json").read_text("utf-8"))["events"]
            scheduled = sorted(((datetime.fromisoformat(e["startsAt"]), e) for e in events
                                if e.get("status") == "scheduled"), key=lambda pair: pair[0])
            upcoming = [e for start, e in scheduled if start > now]
            passed = [e for start, e in scheduled if start <= now]  # the site hides these too (`>` rule)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, editor_mod.UnsafeState):
            return ["I can't read the hike list right now."]
        path, counts = self.settings.get("guestCountsDb"), None
        if any(e.get("rsvpEnabled") for e in upcoming) and isinstance(path, str) and path:  # RSVP-off only: never opened
            try:
                counts = hikes.guest_counts(path)
            except (sqlite3.Error, OSError, ValueError, TypeError):
                counts = None
        lines = []
        for e in upcoming:
            head = f"{q(e.get('title'))}, {voice.natural_iso(e['startsAt'], now)}: "
            limit = e.get("capacity")
            n = counts.get(e.get("id"), 0) if counts is not None else 0
            lines.append(head + ("sign-ups are off" if not e.get("rsvpEnabled") else "I can't see how many guests have signed up" if counts is None
                                 else f"{n} {'guest has' if n == 1 else 'guests have'} signed up" + (f", with room for {limit}" if limit is not None else "")))
        for e in passed[:5]:
            title = e.get("title")
            lines.append(f"{q(title)} was {voice.natural_iso(e['startsAt'], now)} and is still listed as coming up. "
                         "Tell me if it happened or was cancelled.")
        if len(passed) > 5:
            lines.append("A few more past hikes are still listed as coming up.")
        return lines
