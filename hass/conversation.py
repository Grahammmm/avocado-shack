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
from hass.content_model import ContentError, _text as checked_text, load_and_validate, load_content, shop_today, validate  # noqa: E402
from hass.ops import catalog, hikes, load_registry  # noqa: E402

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
APPROVE, REJECT = ("yes", "approve", "approved"), ("no", "cancel", "reject")
KEYWORD_RE = re.compile(r"(yes|approved|approve|no|cancel|reject)(?: ([0-9a-f]{4,12}))?")
NEAR_RE = re.compile(r"(ok|okay|yes please|yep|yeah|sure|go ahead|do it|sounds good|looks good)(?: ([0-9a-f]{4,12}))?")  # H05
COMMAND_RE = re.compile(r"(history)|(undo)(?: ([0-9a-f]{4,12}))?"  # H06, same normalisation as KEYWORD_RE
                        r"|(status|did (?:it|that|my change) work\??)|(pause|stop)(?: changes)?"  # H17; SHOP-4 phrases
                        r"|(resume)(?: changes)?|(help|commands|\?)"
                        r"|(find)(?:\s+(.*))?"  # AV1537-04; the query is re-read from the original text to keep its case
                        r"|(show)(?:\s+(.*))?"  # AV0022-08 (H17): groups 10/11, earlier indices unchanged
                        r"|((?:morning )?report)"  # AV1322-05 (F04): group 12; groups 1-11 keep their indices
                        r"|(post)(?:\s+(hike\s+\S+|\S+))?"  # AV1322-07 (F07): groups 13/14; AV1222-11: or "hike <id>"; the id is re-read from the original text to keep its case
                        r"|(margin)(?:\s+((?s:.*)))?"  # AV1102-12 (F03): groups 15/16; the rest is checked by MARGIN_RE
                        r"|(hidden)"  # AV1222-13 (H03): group 17
                        r"|(listing)(?:\s+(\S+))?")  # AV1622-09 (H17): groups 18/19; one token, the id is re-read from the original text
HELP_TEXT = "\n".join(('Send a change in plain words: "Stop showing the eggs as sold out".',  # AV1537-03, test_help
    'yes [code] - apply the waiting draft: "yes a1b2"',
    'no [code] - cancel the waiting draft or question: "no a1b2"',
    'status (or did it work?) - last change, waiting drafts: "status"',
    'history - the last five changes: "history"',
    'undo [code] - draft an undo of an applied change: "undo a1b2"',
    'stop changes (or pause changes) - nothing applies: "stop changes"',
    'resume changes - let approvals apply again: "resume changes"',
    'remember <key>: <text> - save a note: "remember parking: back lot"',
    'forget <key> - delete a saved note: "forget parking"',
    'memory - saved notes and aliases: "memory"',
    'alias <name>: <id> - name an id: "alias jam: photo-product-001"',
    'cost <id>: <$> for <n> - save: "cost photo-product-001: 24 for 12"',  # AV1222-10
    'find <words> - products/makers/hikes/route ideas: "find lion\'s mane"',
    'show <code> - repeat a draft and its screenshot: "show a1b2"',
    'report - the morning shelf report: "report"',
    'post <id> - draft a caption, posts nothing: "post photo-product-001"',
    'post hike <id> - hike draft: "post hike hike-2026-11-14-point-buchon"',  # AV1222-11
    'margin <id> at <m>% - price idea: "margin photo-product-001 at 35%"',  # AV1102-12, AV1222-10: saved cost
    'hidden - hidden products and makers, ids: "hidden"',  # AV1222-13
    'listing <id> - what the site shows for one id: "listing Etto"',  # AV1622-09
    'help (or commands, ?) - this list: "help"'))
# H15 owner memory. Verb and key are case-insensitive (the key is stored lower-cased); the text keeps its case.
MEMORY_RE = re.compile(r"(remember)(?:\s+(.*))?|(forget)\s+(\S+)|(memory)|(alias)(?:\s+(.*))?"
                       r"|(cost)(?:\s+(.*))?", re.IGNORECASE | re.DOTALL)  # AV1222-10: groups 8/9
MEMORY_LIST_MAX, HISTORY_MAX = 20, 5  # AV1537-14: docs/hass/LIMITS.md states these (test_limits_doc)
ALIAS_LIST_MAX = 20  # AV0222-05: `memory` lists this many aliases apart from the notes (LIMITS.md)
HISTORY_STATES = ("approved", "applied", "verified", "failed", "reverted")  # AV2022-06: owner-approved changes only
FIND_TEXT_MAX, ALIAS_NAME_MAX = 60, 60  # AV0022-15: docs/hass/LIMITS.md states these (test_limits_doc)
HIDDEN_MAX = 20  # AV1222-13: lines of the hidden list
LISTING_DESC_MAX = 120  # AV1622-09: characters of a product description in `listing`
LISTING_USAGE = "Send listing and an id from find."
LISTING_NONE = "No listing with that id; send find <words>."
LISTING_MANY = "That id matches more than one listing; send find <words>."
FIND_MAX, FIND_USAGE = 10, f"Send find and 1–{FIND_TEXT_MAX} characters, e.g. find lion's mane."  # AV1537-04
POST_USAGE = "Send post and a product id, e.g. post photo-product-001."  # AV1322-07
HIKE_USAGE = "Send post hike and a hike id, e.g. post hike hike-2026-11-14-point-buchon (find <words> gives ids)."  # AV1222-11
HIKE_REFUSALS = {"no such hike": "No hike {id}; send find <words> for ids.", "hike is cancelled": "{id} is cancelled; nothing to announce.",
                 "hike already happened": "{id} has already happened.", "not scheduled": "{id} is not scheduled yet."}  # other reasons: "Cannot draft a post for <id>: <reason>."
POST_REFUSALS = {"no such product": "No product {id}; send find <words> for ids.", "not on the site": "{id} is not on the site.",
                 "no photo on the site": "{id} has no photo on the site."}  # other build() reasons: "Cannot draft a post for <id>: <reason>."
_NUM = r"[-+]?[0-9.][0-9.,_]*(?:e[-+]?[0-9]+)?"  # AV1102-12: looks like a number; margins.compute is the only validator
MARGIN_RE = re.compile(rf"\$?({_NUM})\s+for\s+({_NUM})\s+at\s+({_NUM})\s*%(?:\s+shrink\s+({_NUM})\s*%)?")
MARGIN_ID_RE = re.compile(rf"([a-z0-9][a-z0-9-]*)\s+at\s+({_NUM})\s*%(?:\s+shrink\s+({_NUM})\s*%)?")  # AV1222-10: saved cost
COST_RE = re.compile(r"\$?(\S+)\s+for\s+(\S+)", re.IGNORECASE)  # AV1222-10: margins.compute is the only number validator
COST_USAGE = "send cost <id>: <pack cost> for <units>, e.g. cost photo-product-001: 24.00 for 12"
PRIVATE_PREFIXES = ("alias.", "cost.")  # AV1222-10: memory keys the interpreter never sees
MARGIN_USAGE = 'Send: margin <pack cost> for <units> at <margin>% (optional: shrink <S>%), e.g. "margin 24.00 for 12 at 35%".'
PAUSED_LINE = "Changes are paused; send resume changes before yes."
ATTACHMENT_REPLY = ("Photos, voice notes and files are not supported yet, so nothing changed. "
                    "Please send the change as text.")
NOT_READ_REPLY = ("I only read new messages, so that reaction or edit changed nothing. "
                  "Send yes, no or the change as a new message.")  # AV1737-03 (H08/H17): owner reaction or edit
PHOTO_QUESTION = ("Which product is this photo for, and how would you describe the photo in a few words (for people who "
                  "cannot see it)?")  # NB-AV-09 (H12): asked by every new photo draft
PHOTO_OPS = ("product.set_photo", "product.add")  # AV0022-04: ops in a photo-draft answer that get the draft's photo
FETCH_FAILED = "I could not download that photo after 3 tries, so nothing was changed. Please send it again."
# H17 pause flag. Created by the first `pause` (not in SCHEMA) so the H05 store keeps its four tables until then.
CONTROL = """CREATE TABLE IF NOT EXISTS control(name TEXT PRIMARY KEY, value TEXT NOT NULL, set_at TEXT NOT NULL,
  provider_id TEXT NOT NULL)"""
USAGE = "CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY, calls INTEGER NOT NULL)"  # H22; lazy like CONTROL
DAILY_LIMIT = ("Today's limit for reading change requests is reached, so nothing was drafted. "
               "Commands (status, yes/no, undo) still work; send the change again tomorrow.")
MAX_OWNER_TEXT = 4000  # AV1737-04 (H05/H22): twice the longest field limit (recap 2000); test_owner_text_cap checks it
MAX_NOTES = 20  # AV1102-09: saved notes the interpreter sees (newest first)
TOO_LONG = (f"That message is over {MAX_OWNER_TEXT} characters, so I did not read it and nothing changed. "
            "Send a shorter change.")
OPS_PENDING_MAX = 4096  # AV0022-03: bytes of a draft's ops_json sent in `pending`; larger -> "opsOmitted": true
TRANSITIONS = {"needs-details": {"proposed", "rejected", "expired"}, "proposed": {"approved", "rejected", "expired"},
               "approved": {"applied", "failed", "rejected"}, "applied": {"verified", "reverted"},
               "verified": {"reverted"}}
INTERRUPTED = "interrupted; not applied; approve a new draft"
NOTHING = "Nothing is waiting for approval."
UNREADABLE = {"unsupported": "Sorry, I could not understand that request."}
VALUE_CUT = 120
LATE_AFTER = timedelta(minutes=15)  # AV0022-10 (H16): a reply sent this much after the message it answers says so
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DELAYED_AFTER_S = 600  # AVB-07 (H16): an outbox reply older than this at send time is marked delayed
VERIFY_MAX = 5  # AV1737-08 (H06): result check captures at most this many distinct touched records
SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(provider_id TEXT PRIMARY KEY, disposition TEXT NOT NULL, received_at TEXT);
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


HELD_REPLY = "{code} was not applied: approvals are not acted on until the channel is connected. It still waits."


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

    def interpret(self, text, pending, notes=None):
        return copy.deepcopy(self.mapping.get(text, {"unsupported": "Sorry, I can't do that yet."}))


class Outbox:
    """Replies stored in the same transaction as the result; flush() sends them in order and marks each sent."""

    def __init__(self, db, now):
        self.db, self._now = db, now

    def add(self, chat, text, attachments=(), reply_to=None):
        self.db.execute("INSERT INTO outbox(chat, text, attachments, created_at, reply_to) VALUES (?, ?, ?, ?, ?)",
                        (chat, text, json.dumps(list(attachments)), _iso(self._now()), reply_to))

    def unsent(self):
        return self.db.execute("SELECT * FROM outbox WHERE sent_at IS NULL ORDER BY id").fetchall()

    def flush(self, adapter) -> int:
        """A raised send error propagates and leaves that row and every later row unsent."""
        sent = 0
        for row in self.unsent():
            head = self._late(row["reply_to"]) or self._delayed(row["created_at"])  # the longer wait is the one named
            adapter.send(row["chat"], head + row["text"], json.loads(row["attachments"]))
            self.db.execute("UPDATE outbox SET sent_at = ? WHERE id = ?", (_iso(self._now()), row["id"]))
            sent += 1
        return sent

    def _late(self, reply_to) -> str:
        """AV0022-10 (H16): send-time heading naming the owner message a reply answers, when sent over LATE_AFTER
        after it (older than 6 days: its date); empty, naive, bad or future -> ''. The stored text never changes."""
        try: sent, now = datetime.fromisoformat(reply_to), self._now()
        except (TypeError, ValueError): return ""
        if sent.tzinfo is None or now - sent <= LATE_AFTER: return ""
        at = sent.astimezone(LOCAL_TZ)
        day = at.strftime("%Y-%m-%d") if now - sent > timedelta(days=6) else WEEKDAYS[at.weekday()]
        return f"Late reply to your message from {day} {at:%H:%M}:\n"

    def _delayed(self, created_at) -> str:
        """AVB-07 (H16): send-time prefix for a reply held over DELAYED_AFTER_S; bad, naive or future -> ''."""
        try: age = (self._now() - datetime.fromisoformat(created_at)).total_seconds()
        except (TypeError, ValueError): return ""
        return f"(Delayed reply, written {_local(created_at)}) " if age > DELAYED_AFTER_S else ""


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
    keys = [sender_key(s) for s in senders] if isinstance(senders, list) else []
    if not keys: problems.append("ownerSenders must be a non-empty list of sender addresses")
    problems += [f"ownerSenders entry {n} is not an email address or a +country phone number"  # value never echoed
                 for n, key in enumerate(keys, 1) if key is None]
    if not isinstance(chat, str) or not chat.strip(): problems.append("ownerChat must be a chat id")
    elif ";+;" in chat:  # AVB-02 (H08): the owner channel is the owner's one-to-one chat, never a group; ids never echoed
        problems.append("ownerChat is a group chat; it must be the owner's one-to-one chat")
    elif (direct := re.fullmatch(r"[^;]+;-;([^;]+)", chat)) and sender_key(direct[1]) not in keys:
        problems.append("ownerChat is a one-to-one chat with an address that is not in ownerSenders")
    if type(ttl) is not int or ttl < 60: problems.append("approvalTtlSeconds must be an integer >= 60")
    root = settings.get("mediaRoot")  # NB-AV-09: required only with a photo source
    if photos and (not isinstance(root, str) or not root.strip()): problems.append("mediaRoot must be set to use photos")
    cap = settings.get("interpreterDailyCap")  # H22: optional; absent or null means no cap (no default enables it)
    if cap is not None and (type(cap) is not int or not 1 <= cap <= 10000):
        problems.append("interpreterDailyCap must be an integer 1-10000")
    if problems: raise ConfigError("; ".join(problems))
    return {"ownerSenders": tuple(senders), "ownerKeys": frozenset(keys), "ownerChat": chat, "approvalTtlSeconds": ttl,
            "mediaRoot": root, "guestCountsDb": settings.get("guestCountsDb"),  # guestCountsDb: H17, unchecked
            "interpreterDailyCap": cap}


def parse_keyword(text: str):
    """(verb, code or None) when the whole message is an approval keyword; otherwise None."""
    match = KEYWORD_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()))
    if not match: return None
    return ("approve" if match[1] in APPROVE else "reject"), match[2]


def parse_near(text: str):
    """AV2022-07 (H05): code or "" when the whole message is a casual yes (ok, go ahead, ...); otherwise None.
    It never approves anything; Hass only answers with the exact `yes <code>` to send."""
    match = NEAR_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()).removesuffix(","))
    return None if not match else match[2] or ""


def parse_command(text: str):
    """("undo", code or None) or (history|status|pause|resume|help, None) when the whole message is that command;
    otherwise None."""
    match = COMMAND_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()))
    if not match: return None
    if match[18]: return "listing", re.sub(r"[.!]+$", "", text.strip())[7:].strip() if match[19] else ""  # AV1622-09: the id in its own case
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


def parse_memory(text: str):
    """("remember", key, text), ("forget", key, None) or ("memory", None, None) when the whole message is an H15
    memory command; otherwise None. `remember …` without `key:` still parses (as an empty text) so it is refused."""
    match = MEMORY_RE.fullmatch(text.strip())
    if match and match[1]:
        key, colon, value = (match[2] or "").partition(":")
        return "remember", key.strip().lower(), value.strip() if colon else ""
    if match and match[6]:  # ("alias", name, product id or maker key); a missing part is refused, not guessed
        name, colon, ident = (match[7] or "").partition(":")
        return "alias", name.strip(), ident.strip() if colon else ""
    if match and match[8]:  # AV1222-10 ("cost", product id, "<pack> for <units>"); a bad part is refused, not guessed
        ident, colon, rest = (match[9] or "").partition(":")
        return "cost", ident.strip().lower(), rest.strip() if colon else ""
    match = MEMORY_RE.fullmatch(re.sub(r"!+$", "", text.strip()))  # a key may end in "." (KEY_RE), never "!"
    if match and match[3]: return "forget", match[4].lower(), None
    match = MEMORY_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip()))
    return ("memory", None, None) if match and match[5] else None


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
    text = "(none)" if v is None else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= VALUE_CUT else text[:VALUE_CUT - 3] + "..."


def _full(v) -> str:
    """AV1537-06 (H05): a proposal's new value uncut (TEXT_LIMITS bound it); a list of strings joins with "; ".
    Anything else (None, numbers, whole JSON records) keeps the _value cut."""
    if isinstance(v, list) and v and all(isinstance(i, str) for i in v): return "; ".join(v)
    return v if isinstance(v, str) else _value(v)


def _arrow(v) -> str:
    """`→ <new value>`; a value with a line break goes on its own lines, indented two spaces."""
    parts = (text := _full(v)).splitlines()
    return "→\n  " + "\n  ".join(parts) if text and parts != [text] else "→ " + text


def _changes(record: dict):
    before, after = record.get("before"), record.get("after")
    if isinstance(before, dict) and isinstance(after, dict):
        return [(k, before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
    return [("record", before, after)]


def _summary(draft: dict) -> str:
    text = "; ".join(f"{r['collection']} {r['key']}: " + ", ".join(f for f, _b, _a in _changes(r))
                     for r in draft["records"])
    return _value(text or "no records")


def _added(r: dict) -> list:  # AV1737-06 (H05/H06): an added record's non-empty fields, sorted, one per line (≤ 40)
    rows = [(k, _hike_time(v) if k == "startsAt" else v) for k, v in sorted(r["after"].items()) if v not in (None, "", [])]
    more = [f"  … and {len(rows) - 40} more fields"] if len(rows) > 40 else []
    return [f"{r['collection']} {r['key']}: new"] + [f"  {k}: " + "\n    ".join(
        (v if isinstance(v, str) else _value(v)).splitlines()) for k, v in rows[:40]] + more


def _record_lines(draft: dict) -> list:  # AV0022-08: a draft's record and warning lines (proposal_text and show)
    lines = []
    for r in draft["records"]:
        lines += _added(r) if r.get("before") is None and isinstance(r.get("after"), dict) else [
            f"{r['collection']} {r['key']}: {f} {_value(b)} {_arrow(a)}" for f, b, a in (
                (f, *(map(_hike_time, (b, a)) if f == "startsAt" else (b, a))) for f, b, a in _changes(r))]
    return lines + [f"Warning: {w}" for w in draft.get("warnings") or []]


def proposal_text(code: str, draft: dict, expires_at: str, repeat: bool = False, head: str = "") -> str:
    lines = [head or f"Draft {code}:"] + _record_lines(draft)
    yes = f"yes {code}" if repeat else "yes"  # a repeat of a closed draft needs its new code
    lines += [f"Expires {_local(expires_at)}.", f"Reply {yes} to apply, no to cancel, or send a correction."]
    return "\n".join(lines)


class Conversation:
    def __init__(self, state_dir, editor, interpreter, clock, previewer=None, photos=None, labels=None):
        """previewer (H06, e.g. preview.Previewer(worktree)): proposal screenshots and checked results; None keeps
        the H05 behaviour (no screenshot, an applied draft stays `applied`)."""
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
        self.memory = None  # H15 store on this same connection, opened by the first memory command
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
        rows = [r for r in self._drafts("code = ?", code) if states is None or r["state"] in states]
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

    def _reply(self, text, attachments=()):
        self.outbox.add(self.settings["ownerChat"], text, attachments, self._answering or None)

    def _proposal_reply(self, row, draft, prefix=""):
        """The proposal text plus, with a previewer, a private screenshot of the rendered draft (H06)."""
        text, shots = prefix + proposal_text(row["code"], draft, row["expires_at"], self._repeat(row)), []
        if self.previewer is not None:
            rendered = self.editor.render_draft(draft["change_id"])
            extra = {"assets": rendered["assets"]} if rendered.get("assets") else {}  # a new photo the draft would add
            shot = self.previewer.capture(rendered["files"], preview_mod.target_for(draft["records"][0], shop_today(), store=rendered.get("store")),
                                          self.sdir / "screenshots" / f"{draft['change_id']}-proposal.png", **extra) \
                if rendered.get("result") == "ok" else {"ok": False, "png": None, "error": _reason(rendered)}
            shots = [shot["png"]] if shot.get("png") else []
            if not shot["ok"]: text += f"\nPreview unavailable: {shot['error']}"
        if self._paused(): text += "\n" + PAUSED_LINE
        self._reply(text, shots)

    def _record(self, msg, disposition, owner=True):
        self.db.execute("INSERT INTO messages(provider_id, disposition, received_at) VALUES (?, ?, ?)",
                        (msg.provider_id, disposition, msg.received_at if owner else None))

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
             fields["ops_json"], fields["summary"], sender, self.settings["ownerChat"], _iso(now), expires,
             fields["proposed_at"]))
        return self._row(cur.lastrowid)

    # -- message handling ----------------------------------------------------------------------------------------
    _answering = None  # AV0022-10 (H16): received_at of the message handle() is running; replies are tagged with it

    def handle(self, msg: Inbound, last_try=False, apply=True) -> str:
        self._answering = msg.received_at
        try: return self._handle_message(msg, last_try, apply)
        finally: self._answering = None

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
        out = self.editor.apply(approved["change_id"], approved["draft_hash"])
        with self._tx():
            self._outcome(self._row(approved["row_id"]), out, self._now())
        self._verify_pending()
        return disposition

    def _handle(self, msg, last_try=False):
        if self.db.execute("SELECT 1 FROM messages WHERE provider_id = ?", (msg.provider_id,)).fetchone():
            return "duplicate", None
        owner = msg.chat == self.settings["ownerChat"] and sender_key(msg.sender) in self.settings["ownerKeys"]
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
        now, command = self._now(), None if msg.attachments > 0 else parse_command(msg.text)
        # AV0022-06 (H16): a yes/no is judged at the time it was sent, so a reply queued while the service was down counts
        cutoff = _answered_at(msg, now) if msg.attachments <= 0 and parse_keyword(msg.text) is not None else now
        expired = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) <= cutoff]
        if command and command[0] in ("status", "help", "find", "show", "report", "post", "margin", "hidden", "listing"): expired = []  # H17: read-only
        memory = None if command or msg.attachments > 0 else parse_memory(msg.text)
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
        keyword = parse_keyword(msg.text)
        if keyword is None and (near := parse_near(msg.text)) is not None:  # AV2022-07: no approval, call or count
            codes = [r["code"] for r in self._drafts("state = 'proposed'")
                     if self._expiry(r) > now and near in ("", r["code"])]
            self._reply(f"Nothing was applied. To apply {codes[0]}, reply yes {codes[0]}." if len(codes) == 1 else
                        f"Nothing was applied. Reply yes <code> with one of: {', '.join(codes)}." if codes else NOTHING)
            self._record(msg, "near-approval")
            return "near-approval", None
        if keyword is None:
            disposition = self._request(msg, now)
            self._record(msg, disposition)
            return disposition, None
        verb, code = keyword
        # AV1537-02: no/cancel also closes an open (unexpired) question; yes only ever targets a proposal.
        states = "('proposed', 'needs-details')" if verb == "reject" else "('proposed')"
        targets = [r for r in self._drafts(f"state IN {states}") if code is None or r["code"] == code]
        asks = [] if verb != "approve" or targets else [self._by_code(code, ("needs-details",))] if code else \
            [r for r in self._drafts("state = 'needs-details'") if self._expiry(r) > cutoff]  # AV1737-05: bare yes
        if asks := [a for a in asks if a is not None]:  # a waiting question is never approved; it is repeated
            self._reply("\n".join(f"{a['code']} still needs details: {a['summary']}" for a in asks))
            self._record(msg, "no-target")
            return "no-target", None
        if len(targets) != 1:
            self._reply(self._no_target(code, targets, expired))
            self._record(msg, "no-target")
            return "no-target", None
        target = targets[0]
        if verb == "reject":
            self._move(target, "rejected", reason="owner")
            self._reply(f"Cancelled {target['code']}; nothing changed.")
            self._record(msg, "rejected")
            return "rejected", None
        if self._paused():  # H17: no approval row, no state move; the draft keeps its expiry
            self._reply(f"Changes are paused; {target['code']} was not applied. "
                        f"Send resume changes, then yes {target['code']}.")
            self._record(msg, "paused")
            return "paused", None
        if cutoff != now and cutoff < self._proposed_at(target):  # AVB-03 (H05): a yes sent before the draft existed
            self._reply(f"That yes was sent before {target['code']} was proposed; reply yes {target['code']} to apply it.")
            self._record(msg, "no-target")
            return "no-target", None
        if code is None and self._repeat(target):  # a delayed bare `yes` must not approve a repeat of a closed draft
            self._reply(f"{target['code']} repeats a draft that was closed; reply yes {target['code']} to apply it.")
            self._record(msg, "no-target")
            return "no-target", None
        self.db.execute(
            "INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, approved_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (msg.sender, msg.chat, msg.provider_id, target["change_id"],
                                                 target["draft_hash"], target["base"], target["expires_at"], _iso(now)))
        self._move(target, "approved")
        self._record(msg, "approved")
        return "approved", self._row(target["row_id"])

    def _no_target(self, code, targets, expired) -> str:
        if targets:
            return "\n".join(["Which draft do you mean?"] + [f"{r['code']}: " + ("needs details: " if r["state"] ==
                             "needs-details" else "") + r["summary"] for r in targets]
                             + ["Reply yes <code> or no <code>."])
        if code and self._by_code(code) is None:  # AV2152-01 (H05/H17): a code that matches no draft; never guessed
            waiting = self._drafts("state = 'proposed'")
            return "\n".join([f"No draft {code}."] + (["Waiting drafts:"] + [
                f"{r['code']}: {r['summary']}; reply yes {r['code']}." for r in waiting] if waiting else []))
        named = [self._by_code(code)] if code else [self._row(r["row_id"]) for r in expired]
        return "\n".join(self._state_text(r) for r in named if r is not None) or NOTHING

    def _state_text(self, row) -> str:
        code, state = row["code"], row["state"]
        if state == "expired": return f"{code} expired at {_local(row['expires_at'])}; nothing changed."
        if state == "rejected" and row["replaced_by"]: return f"{code} was replaced by {row['replaced_by']}."
        if state == "rejected": return f"{code} was cancelled ({row['reason']}); nothing changed."
        return f"{code} is {state}."

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


    def _request(self, msg, now) -> str:
        if len(msg.text) > MAX_OWNER_TEXT:  # AV1737-04: code points; never interpreted, drafted or counted
            self._reply(TOO_LONG)
            return "too-long"
        cap = self.settings["interpreterDailyCap"]
        if cap is not None:  # H22: counted before the call in this transaction, so a failed call still counts
            day, calls = self._calls(now)
            if calls >= cap:
                self._reply(DAILY_LIMIT)
                return "daily-limit"
            self.db.execute(USAGE)
            self.db.execute("INSERT INTO usage VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET calls = calls + 1", (day,))
        pending = [{"code": r["code"], "state": r["state"], ("question" if r["state"] == "needs-details" else "summary"):
                    r["summary"], **_pending_ops(r["ops_json"]),  # AV0022-03: + "ops" or "opsOmitted"
                    **({"missing": _missing_ids(r["missing_json"])} if r["state"] == "needs-details" else {})}  # AV0007-03
                   for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) > now]
        notes = self._notes()  # AV1102-09: preferences only; no notes means exactly the two-argument call
        try:
            result = _checked(self.interpreter.interpret(msg.text, pending, notes=notes) if notes
                              else self.interpreter.interpret(msg.text, pending))
        except Exception if cap is not None else ():  # H22: no cap: unchanged (an error rolls the message back)
            result = dict(UNREADABLE)  # keep the counted call; a failure stops safely with the unreadable reply
        codes = {p["code"] for p in pending}
        named = self._by_code(result["revises"]) if result.get("revises") and result["revises"] not in codes else None
        cancelled_question = named is not None and named["state"] == "rejected" and named["reason"] == "owner" \
            and named["change_id"] is None  # AV1537-02: a question the owner cancelled is not filled later
        if named is not None and named["state"] == "expired" or cancelled_question:  # H16 vs NB-AV-01 (2026-10-31):
            result = {**result, "revises": None}  # a closed draft has nothing left to revise; an unknown code still asks
        result = interpret_check.check(result, self._registry(), codes)  # NB-AV-01: a bad op/arg/kind/code asks
        for key in ("question", "unsupported"):
            if key in result:
                self._reply(result[key])
                return key
        revised = self._by_code(result["revises"], ("proposed", "needs-details")) if result["revises"] else None
        photo = next((c["args"].get("photo") for c in json.loads(revised["ops_json"]) if c["op"] == "product.set_photo"),
                     None) if revised else None  # NB-AV-09: a fill keeps the draft's photo; another one is refused
        calls = [c for c in result["ops"] if c["op"] in PHOTO_OPS] if photo else []  # AV0022-04: a new product too
        if len(calls) > 1:  # AV0022-04: one photo, one product; nothing changes until the owner says which
            return self._reply("One photo can go on one product; say which.") or "photo-many-ops"
        if any(c["args"].setdefault("photo", photo) != photo for c in calls):
            return self._reply("That draft is for another photo.") or "photo-mismatch"
        out = self.editor.prepare(result["ops"])
        if out["result"] == "needs-details":
            ops_json = json.dumps(result["ops"], sort_keys=True)
            expires = _iso(now + timedelta(seconds=self.settings["approvalTtlSeconds"]))  # H16: questions lapse too
            missing_json = json.dumps(out.get("missing", []))  # AV0007-03: stored with the question, same transaction
            if revised is not None and revised["state"] == "needs-details":  # the owner just answered: refresh
                self.db.execute("UPDATE drafts SET ops_json = ?, summary = ?, expires_at = ?, missing_json = ? WHERE row_id = ?",
                                (ops_json, out["question"], expires, missing_json, revised["row_id"]))
            else:
                code = self._code(hashlib.sha256(msg.provider_id.encode()).hexdigest())
                self.db.execute(
                    "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at, missing_json)"
                    " VALUES (?, 'needs-details', ?, ?, ?, ?, ?, ?, ?)",
                    (code, ops_json, out["question"], msg.sender, msg.chat, _iso(now), expires, missing_json))
                # An incomplete correction still supersedes the proposal it names: it can no longer be approved.
                if revised is not None: self._move(revised, "rejected", reason="revised", replaced_by=code)
            self._reply(out["question"])
            return "needs-details"
        if out["result"] != "ok":
            self._reply(f"Not drafted: {_reason(out)}")
            return "not-drafted"
        draft = out["draft"]
        if hits := claims.unstated(draft, msg.text, self._makers(), self._routes(), self._sources()):  # NB-AV-05: an unstated claim asks, never drafts
            self._reply(claims.question(hits))  # no row; a waiting draft named by revises is left as it was
            return "claim-question"
        same = [r for r in self._drafts("state = 'proposed' AND change_id = ?", draft["change_id"])]
        if same and (revised is None or revised["row_id"] == same[0]["row_id"]):
            row = same[0]
        elif revised is not None and revised["state"] == "needs-details":
            row = self._propose(draft, msg.sender, now, row=revised)
        else:
            row = self._propose(draft, msg.sender, now)
            if revised is not None: self._move(revised, "rejected", reason="revised", replaced_by=row["code"])
        self._proposal_reply(row, draft)
        return "proposed"

    def _photo(self, msg, now, last_try=False) -> str:  # NB-AV-09: store one photo, then open (or name) its needs-details draft
        if msg.attachments != 1: return self._reply(media.REPLIES["many"]) or "attachment-many"
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
        if dup: return self._reply(f"That photo is already in draft {dup[0]['code']}." + (
            f" {dup[0]['summary']}" if dup[0]["state"] == "needs-details" else "")) or "photo-duplicate"
        caption = msg.text.replace("\ufffc", "").strip()  # handled as the next text, in this same transaction
        try:  # H12: a photo that is an active or hidden product's picture opens no draft; unreadable worktree: as before
            image = re.compile(rf"assets/products/photo-{sha[:16]}\.(jpg|png)")
            on = next((p for p in sorted((p for p in load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                       .products if isinstance(p, dict)), key=lambda p: str(p.get("id")))
                       if p.get("status") in ("active", "hidden") and isinstance(p.get("image"), str)
                       and image.fullmatch(p["image"])), None)
            said = on and f"That photo is already on {on['id']} ({on['name']}). To change that product, say what to change."
        except (OSError, ValueError, KeyError, TypeError, editor_mod.UnsafeState): said = None  # no id/name: as unreadable
        if said:
            self._reply(said)
            return self._request(Inbound(**{**vars(msg), "text": caption}), now) if caption else "photo-on-product"
        self.db.execute("INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, missing_json) VALUES"
                        " (?, 'needs-details', ?, ?, ?, ?, ?, ?)", (code := self._code(sha), json.dumps(
                            [{"op": "product.set_photo", "args": {"photo": sha}}]), PHOTO_QUESTION, msg.sender, msg.chat, _iso(now),
                            json.dumps(["id", "imageAlt"])))  # AV0007-03: set_photo's required args besides the photo
        self._reply(f"{PHOTO_QUESTION} Reply with the product and description (draft {code}).")
        if self.labels is not None: self._label_job = (code, sha, self.db.execute("SELECT last_insert_rowid()").fetchone()[0])
        return self._request(Inbound(**{**vars(msg), "text": caption}), now) if caption else "photo-draft"

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
        result = out.get("result")
        if result in ("applied", "already-applied"):
            self._move(row, "applied", commit=out.get("commit"))
            for call in json.loads(row["ops_json"]):  # an applied undo closes the draft it reverted
                if call.get("op") == "history.revert":
                    for orig in self._drafts("change_id = ? AND state IN ('applied', 'verified')",
                                             call["args"].get("changeId")):
                        self._move(orig, "reverted", reason=f"undone by {row['code']}")
            if self.previewer is None: self._reply(answers.applied_text(row["code"], row["summary"]))  # SHOP-4
            # with a previewer the reply waits for verify(): nothing says it worked before it is checked
        elif result == "stale":
            again = self.editor.prepare(json.loads(row["ops_json"]))
            if again["result"] == "ok":
                new = self._propose(again["draft"], row["sender"], now)
                self._move(row, "rejected", reason="stale", replaced_by=new["code"])
                self._proposal_reply(new, again["draft"], f"The site changed since {row['code']}; "
                                                          f"please approve {new['code']}.\n")
            else:
                self._move(row, "rejected", reason="stale")
                self._reply(f"The site changed since {row['code']}; not applied: {_reason(again)}")
        else:
            self._move(row, "failed", reason=_reason(out))
            self._reply(f"Not applied: {_reason(out)}")

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
                        self._reply(answers.recovered_text(row["code"]))  # SHOP-4: apply never touches the website
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
        picked, png = [], None  # AV1737-08: each touched record with a distinct target, in order
        for record in change["records"]:
            target = preview_mod.target_for(record, shop_today(), store=content.store)  # the store the committed files were generated from
            if all(target != t for _r, t in picked): picked.append((record, target))
        for i, (record, target) in enumerate(picked[:VERIFY_MAX], 1):
            shot = self.previewer.capture(files, target, self.sdir / "screenshots" /
                                          f"{row['change_id']}-result{'' if i == 1 else f'-{i}'}.png")
            if not shot["ok"]: return None, f"{record['collection']} {record['key']}: {shot['error']}"
            png = shot["png"] if i == 1 else png  # the reply keeps the first record's screenshot
        if picked[VERIFY_MAX:]:
            print(f"verify {row['change_id']}: over {VERIFY_MAX} records, not checked: "
                  + ", ".join(f"{r['collection']} {r['key']}" for r, _t in picked[VERIFY_MAX:]), file=sys.stderr)
        return png, None

    def _verify_pending(self):
        if self.previewer is None: return
        for row in self._drafts("state = 'applied' AND checked_at IS NULL"):
            png, error = self.verify(row)  # outside the transaction; the result and reply are stored together
            with self._tx():
                if png:
                    self._move(row, "verified", screenshot=png, checked_at=_iso(self._now()))
                    self._reply(answers.applied_text(row["code"], row["summary"], checked=True), [png])  # SHOP-4
                else:  # the raw diagnostic stays on the row; the owner gets plain words (SHOP-4)
                    self.db.execute("UPDATE drafts SET reason = ?, checked_at = ? WHERE row_id = ?",
                                    (f"not verified: {error}", _iso(self._now()), row["row_id"]))
                    self._reply(answers.applied_text(row["code"], row["summary"], error=error))

    def _command(self, msg, now, verb, code) -> str:
        if verb == "help":
            self._reply(HELP_TEXT)
            return "help"
        if verb in ("status", "pause", "resume"): return self._control(msg, now, verb)
        if verb == "find": return self._find(code) if 1 <= len(code) <= FIND_TEXT_MAX else (self._reply(FIND_USAGE), "find")[1]
        if verb == "show": return self._reply(*self._show(code, now)) or "show"
        if verb == "report": return self._report(now)
        if verb == "post": return self._post(code)
        if verb == "margin": return self._margin(code)
        if verb == "hidden": return self._hidden()
        if verb == "listing": return self._listing(code)
        if verb == "history":
            rows = self.db.execute(f"SELECT * FROM drafts WHERE state IN ({', '.join('?' * len(HISTORY_STATES))}) "
                                   "ORDER BY row_id DESC LIMIT ?", (*HISTORY_STATES, HISTORY_MAX)).fetchall()
            self._reply("\n".join(["Recent changes:"] + [  # SHOP-4: where it is now instead of the commit
                f"{r['code']} {r['state']}: {r['summary']} - {answers.history_words(dict(r), self._install(r))}"
                for r in rows]) if rows else "No approved changes yet.")
            return "history"
        done = [r for r in self._drafts("change_id IS NOT NULL AND \"commit\" IS NOT NULL")  # AV0022-07: skip undos
                if code is None and r["state"] in ("applied", "verified") and not _is_undo(r) or r["code"] == code]
        if not done:
            self._reply(f"Nothing to undo for {code}." if code else "Nothing to undo.")
            return "no-target"
        out = self.editor.prepare([{"op": "history.revert", "args": {"changeId": done[-1]["change_id"]}}])
        if out["result"] != "ok":
            self._reply(f"Not undone: {_reason(out)}")
            return "not-drafted"
        same = self._drafts("state = 'proposed' AND change_id = ?", out["draft"]["change_id"])
        row = same[0] if same else self._propose(out["draft"], msg.sender, now)
        self._proposal_reply(row, out["draft"], f"Undo {done[-1]['code']}:\n")
        return "proposed"

    def _report(self, now) -> str:
        """AV1322-05 (F04): the morning shelf report from the writer worktree content, Pacific today; read-only."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            text = morning_report.render(morning_report.facts(content, shop_today(now)))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            text = "Shelf report unavailable right now; nothing changed."
        waiting = self._waiting_lines(now) + [l for l in self._photo_lines(now) if l.startswith("Photos waiting")]
        self._reply(f"{text}\n\n" + "\n".join(["Waiting for you:"] + waiting if waiting else ["Waiting for you: nothing"]))
        return "report"

    def _margin(self, rest) -> str:
        """AV1102-12 (F03): margins.render for one purchase line, text in and text out. Read-only: nothing is stored or
        drafted, no interpreter call or usage count; works while paused."""
        found = MARGIN_RE.fullmatch(rest)
        by_id = None if found else MARGIN_ID_RE.fullmatch(rest)  # AV1222-10: the saved cost of a product
        try:
            text = margins.render(margins.compute(found[1], found[2], found[4] or "0", found[3])) if found else \
                self._margin_saved(*by_id.groups()) if by_id else MARGIN_USAGE
        except margins.InputError as exc:
            text = f"Not calculated: {exc}."
        self._reply(text)
        return "margin"

    def _margin_saved(self, ident, margin, shrink) -> str:
        """AV1222-10: margins for the saved cost.<id> (read-only; the memory table is not created for a read)."""
        has_table = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
        if self.memory is None and has_table: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        row = next((r for r in self.memory.list() if r["key"] == f"cost.{ident}"), None) if has_table else None
        if row is None: return f"No cost saved for {ident}; send cost {ident}: <pack cost> for <units> first."
        pack, _, units = row["value"].partition(" for ")
        since = datetime.fromisoformat(row["created_at"]).astimezone(LOCAL_TZ)
        return f"Using cost from {since:%Y-%m-%d}: {row['value']}.\n" + margins.render(margins.compute(pack, units, shrink or "0", margin))

    def _post(self, pid) -> str:
        """AV1322-07 (F07 prepare half): social_draft's caption for one active product plus its site photo, from the
        writer worktree content. Read-only: nothing is posted, scheduled, written or drafted; works while paused."""
        photo = None
        if pid.lower().split(None, 1)[:1] == ["hike"]: return self._post_hike(pid[4:].strip())
        try:
            if not pid: raise LookupError
            wt = editor_mod._load(str(self.sdir))[2]
            out = social_draft.build(load_content(wt / "hass" / "content"), pid, wt / "storefront-mockup")
            if out["draft"] and stat.S_ISREG(os.lstat(photo := wt / "storefront-mockup" / out["image"]).st_mode):
                text = f"Draft post (not posted):\n{out['caption']}\nPhoto description: {out['alt']}"
            else:  # a refusal, or a photo that is itself a link: never attached
                reason = out.get("reason", "no photo on the site")
                text = POST_REFUSALS[reason].format(id=pid) if reason in POST_REFUSALS else f"Cannot draft a post for {pid}: {reason}."
                photo = None
                if reason == "cannot read content": raise OSError
        except LookupError:
            text = POST_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            text, photo = "Catalog unavailable right now; nothing changed.", None
        self._reply(text, [str(photo)] if photo else [])
        return "post"

    def _post_hike(self, hid) -> str:
        """AV1222-11 (F07): social_draft.build_hike's caption for one scheduled upcoming hike. Read-only, nothing is stored."""
        try:
            if not hid: raise LookupError
            out = social_draft.build_hike(load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content"), hid, self._now())
            if out["draft"]: text = f"Draft post (not posted; copy it yourself):\n{out['caption']}"
            elif out["reason"] == "cannot read content": raise OSError
            else: text = HIKE_REFUSALS[out["reason"]].format(id=hid) if out["reason"] in HIKE_REFUSALS else f"Cannot draft a post for {hid}: {out['reason']}."
        except LookupError: text = HIKE_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError): text = "Catalog unavailable right now; nothing changed."
        self._reply(text)
        return "post"

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
                lines += [f"{kind} {i}: {records[kind][i][0]} ({records[kind][i][1]})"
                          + (" (your alias)" if found.get("via") else "") for i in ids]
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
            lines += [f"hike {e.get('id')}: {e['title']} (" + (f"{at:%A %b} {at.day}, {at.hour % 12 or 12}:{at:%M} "
                      f"{'am' if at.hour < 12 else 'pm'}" if at else "date unreadable") + f", {e.get('status')})"
                      for e, at in dated]
            lines += [f"route {r.get('id')}: {r['title']} ({r.get('status')})"
                      for r in sorted(hits(content.community["routeIdeas"]), key=lambda r: catalog._fold(r["title"]))]
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            self._reply("Catalog unavailable right now; nothing changed.")
            return "find"
        more = len(lines) - FIND_MAX
        tail = [f"… {more} or more; add a word." if capped else f"… {more} more; add a word."] if more > 0 else \
            ["… maybe more; add a word."] if capped else []
        self._reply("\n".join(lines[:FIND_MAX] + tail) if lines
                    else f'No product, maker, hike or route idea matches "{query}".')
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
            found = [("product", p) for p in content.products if p.get("id") == ident]
            found += [("maker", m) for k, m in content.makers.items() if k == ident]
            found += [(kind, r) for kind, key in (("hike", "events"), ("route idea", "routeIdeas"))
                      for r in content.community[key] if r.get("id") == ident]
            if len(found) != 1: text = LISTING_NONE if not found else LISTING_MANY
            else:
                kind, rec = found[0]
                nope = "not set"
                if kind == "product":
                    maker = content.makers.get(rec.get("producerKey"))
                    desc = rec.get("description")
                    if isinstance(desc, str) and desc:  # held records skip validate_products' description check
                        bad = []
                        checked_text(bad, "description", desc)
                        if bad: raise ValueError(bad[0])
                    desc = nope if not isinstance(desc, str) or not desc else desc[:LISTING_DESC_MAX] + ("…" if len(desc) > LISTING_DESC_MAX else "")
                    avail = (sitegen.availability_label(rec, content.store, shop_today(self._now())) or "not confirmed") \
                        if rec["status"] == "active" else "not shown on site"
                    fields = [("Name", rec["name"]), ("Maker", (maker or {}).get("name") or rec.get("brand") or nope),
                              ("Shelf", rec.get("category") or nope), ("Description", desc), ("Availability", avail),
                              ("Status", rec["status"])]
                elif kind == "maker":
                    fields = [("Name", rec["name"]), ("Place", rec.get("place") or nope),
                              ("Active products", sum(1 for p in content.products if p["status"] == "active" and p.get("producerKey") == ident)),
                              ("Status", "hidden" if rec.get("hidden") else "visible")]
                elif kind == "hike":
                    fields = [("Title", rec["title"]), ("Start", _hike_time(rec["startsAt"])), ("Status", rec["status"]),
                              ("Meeting point", rec.get("meetingPoint") or nope), ("Capacity", rec.get("capacity", nope))]
                else:
                    fields = [("Title", rec["title"]), ("Place", rec.get("place") or nope), ("Status", rec["status"])]
                text = "\n".join(["Saved listing (not a live website check):", f"{kind} {ident}"] + [f"{k}: {v}" for k, v in fields])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            text = "Catalog unavailable right now; nothing changed."
        self._reply(text)
        return "listing"

    def _hidden(self) -> str:
        """AV1222-13 (H03): read-only list of hidden products then hidden makers; held products and visible makers never."""
        try:  # the current catalog from the writer worktree, as _find
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            one = lambda name: " ".join(str(name).split())  # stored text on one line
            lines = [f"product {p['id']}: {one(p['name'])}" for p in sorted(content.products, key=lambda p: p["id"])
                     if p["status"] == "hidden"]
            lines += [f"maker {k}: {one(m['name'])}" for k, m in sorted(content.makers.items()) if m.get("hidden") is True]
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._reply("Catalog unavailable right now; nothing changed.")
            return "hidden"
        more = [f"… and {len(lines) - HIDDEN_MAX} more."] if len(lines) > HIDDEN_MAX else []
        self._reply("\n".join(lines[:HIDDEN_MAX] + more + ['To bring one back, send a change in plain words: "restore <id>".'])
                    if lines else "Nothing is hidden.")
        return "hidden"

    def _show(self, code, now) -> tuple:
        """AV0022-08 (H17): (text, attachments) repeating one draft's stored proposal lines and its saved screenshot.
        Read-only: no state move, no expiry sweep, never prepared or rendered again; works while paused."""
        if not re.fullmatch(r"[0-9a-f]{4,12}", code): return "Send show and a draft code, e.g. show a1b2.", []
        if (row := self._by_code(code)) is None: return f"No draft {code}.", []
        state = row["state"]
        if state in ("proposed", "needs-details") and self._expiry(row) <= now:  # lapsed, not swept: words it only
            return self._state_text({**dict(row), "state": "expired", "expires_at": _iso(self._expiry(row))}), []
        if state == "needs-details": return f"{code} still needs details: {row['summary']}", []
        if state not in ("proposed", "applied", "verified"): return self._state_text(row), []
        try:
            out = self.editor.show(row["change_id"])
            rec = (out.get("draft") or out.get("change") or {}) if out.get("result") == "ok" else {}
            draft = {"records": rec["records"], "warnings": rec.get("warnings")}
            if state == "proposed":
                text = proposal_text(code, draft, row["expires_at"], self._repeat(row), f"Draft {code} (waiting):")
                shot = self.sdir / "screenshots" / f"{row['change_id']}-proposal.png"
            else:
                sha = f" ({row['commit'][:7]})" if row["commit"] else ""
                text, shot = "\n".join([f"Applied {code}{sha}:"] + _record_lines(draft)), row["screenshot"]
            return text, [str(shot)] if shot and Path(shot).is_file() else []
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            return f"{code}: the draft details are not available any more.", []

    # -- H15: remember, forget, memory ---------------------------------------------------------------------------
    def _memory(self, msg, verb, key, value) -> str:
        """Owner-stated facts on this connection inside the message's transaction; a store ValueError undoes only
        that op's savepoint and the message is still recorded. The interpreter reads notes other than PRIVATE_PREFIXES as preferences (AV1102-09); never facts or claims."""
        if verb == "memory":  # AV0222-05: read-only; no memory table is created to answer it
            has_table = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            if has_table and self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
            every = self.memory.list() if has_table else []
            rows = [r for r in every if not r["key"].startswith("alias.")]
            aliases = [r for r in every if r["key"].startswith("alias.")]
            lines = [f"{r['key']}: {r['value']} ({r['kind']}, since "
                     f"{datetime.fromisoformat(r['created_at']).astimezone(LOCAL_TZ):%Y-%m-%d})"
                     for r in rows[:MEMORY_LIST_MAX]]
            more = [f"… and {len(rows) - MEMORY_LIST_MAX} more."] if len(rows) > MEMORY_LIST_MAX else []
            notes = "\n".join([f"Saved ({len(rows)}):"] + lines + more) if rows else "Nothing saved."
            amore = [f"... and {len(aliases) - ALIAS_LIST_MAX} more"] if len(aliases) > ALIAS_LIST_MAX else []
            self._reply("\n".join([notes, f"Aliases ({len(aliases)}):"] + self._alias_lines(aliases[:ALIAS_LIST_MAX]) + amore))
            return "memory-list"
        if self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        if verb == "alias": return self._alias(msg, key, value)
        if verb == "cost": return self._cost(msg, key, value)
        valid = memory_mod.KEY_RE.fullmatch(key) is not None
        if verb == "forget":
            if not valid or self.memory.get(key) is None:
                self._reply(f"Nothing saved as {key}.")
                return "memory-none"
            self.memory.forget(key)
            self._reply(f"Forgot {key}.")
            return "memory-forgot"
        problem = "key must be 1–64 of a-z 0-9 . -" if not valid else None
        if valid and (not memory_mod._clean(value) or len(value) > memory_mod.MAX_VALUE):
            problem = f"text must be 1–{memory_mod.MAX_VALUE} plain characters"
        if valid and key.startswith("alias."): problem = "send alias <name>: <id> to save an alias"
        if valid and key.startswith("cost."): problem = "send cost <id>: <pack cost> for <units> to save a cost"  # AV1222-10
        old, source = (self.memory.get(key) if valid else None), f"owner-stated:{msg.provider_id}"
        if problem is None and old is not None and old == value:  # AVB-15: the same text again changes nothing
            self._reply(f"Already saved {key}: {value}; nothing changed.")
            return "memory-unchanged"
        try:
            if problem is None and old is None: self.memory.remember(key, value, "fact", source)
            elif problem is None: self.memory.correct(key, value, source)
        except ValueError as exc:
            problem = str(exc)
        if problem:
            self._reply(f"Not saved: {problem}.")
            return "memory-invalid"
        self._reply((f"Saved {key}: {value}." if old is None else f"Updated {key} (was: {old}).")
                    + f" Send forget {key} to remove it.")
        return "memory-saved" if old is None else "memory-updated"

    def _cost(self, msg, ident, rest) -> str:
        """AV1222-10 (F03): `cost <id>: <pack> for <units>` saves memory cost.<id> = "<pack> for <units>" (the dated,
        owner-stated, private purchase cost for an existing product, any status). Never the site or the interpreter."""
        found, key, product, problem, value = COST_RE.fullmatch(rest), f"cost.{ident}", None, None, ""
        try:
            if not found or not ident: problem = COST_USAGE
            else:
                shown = margins.compute(found[1], found[2], "0", "0")["inputs"]  # validates and normalises both numbers
                value = f"{shown['pack_cost']} for {shown['units']}"
                content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                product = next((p for p in content.products if p["id"] == ident), None)
                problem = None if product else f"no product {ident}"
        except margins.InputError as exc:
            problem = str(exc)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            problem = "the catalog is unavailable"
        old, source = None, f"owner-stated:{msg.provider_id}"
        try:
            old = self.memory.get(key) if product else None
            if product and old == value:
                self._reply(f"Already saved cost for {ident}: {value}; nothing changed.")
                return "memory-unchanged"
            if product: self.memory.remember(key, value, "fact", source) if old is None else self.memory.correct(key, value, source)
        except ValueError as exc:  # e.g. an id too long for a memory key
            problem = str(exc)
        if problem:
            self._reply(f"Not saved: {problem}.")
            return "memory-invalid"
        self._reply((f"Saved cost for {ident} ({product['name']}): {value}" if old is None else
                     f"Updated cost for {ident} ({product['name']}): {value} (was: {old})")
                    + f" (private; never on the website). Send forget {key} to remove it.")
        return "memory-saved" if old is None else "memory-updated"

    def _alias(self, msg, name, ident) -> str:
        """`alias <name>: <id>` saves memory alias.<slug> = product:<id> | maker:<key>, only if that record exists now."""
        key, found = "alias." + catalog._fold(name).replace(" ", "-"), []
        problem = (f"alias name must be 1–{ALIAS_NAME_MAX} plain letters, digits, spaces, . or -" if not memory_mod._clean(name)
                   or len(name) > ALIAS_NAME_MAX or not memory_mod.KEY_RE.fullmatch(key[6:]) or not memory_mod.KEY_RE.fullmatch(key)
                   else "send alias <name>: <product id or maker key>" if not ident else None)
        try:  # the current catalog, read from the writer worktree as _hike_lines does
            content = None if problem else load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            found = [] if problem else [("product", p, p["status"]) for p in content.products if p["id"] == ident] + (
                [("maker", m, "hidden" if m.get("hidden") else "visible")] if (m := content.makers.get(ident)) else [])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            problem = "the catalog is unavailable"
        problem = problem or (f"no product or maker {ident}" if not found
                              else f"{ident} is both a product and a maker" if len(found) > 1 else None)
        if problem:
            self._reply(f"Not saved: {problem}.")
            return "memory-invalid"
        old, value, source = self.memory.get(key), f"{found[0][0]}:{ident}", f"owner-stated:{msg.provider_id}"
        try: self.memory.remember(key, value, "fact", source) if old is None else self.memory.correct(key, value, source)
        except ValueError as exc:
            self._reply(f"Not saved: {exc}.")
            return "memory-invalid"
        kind, rec, status = found[0]
        target = f"{kind} {ident} ({rec['name']}" + ("" if status in ("active", "visible") else f", {status}") + ")"
        self._reply((f"Saved alias {name} → " if old is None else f"Updated alias {name} (was: {old}) → ")
                    + f"{target}. Send forget {key} to remove it.")
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
                lines.append(f"{name} -> alias unreadable - send forget alias.{slug}")
            elif records is None:
                lines.append(f"{name} -> target unavailable right now ({ident})")
            elif (found := records[kind].get(ident)) is None:
                lines.append(f"{name} -> {ident} (no longer on the site - send forget alias.{slug})")
            elif not safe(found[0]):
                lines.append(f"{name} -> target unavailable right now ({ident})")
            else:
                mark = " [hidden]" if found[1] == "hidden" else " [held]" if found[1] == "held" else ""
                lines.append(f"{name} -> {found[0]} ({ident}){mark}")
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
        waiting = [r for r in self._drafts("state = 'proposed'") if self._expiry(r) > self._now()]
        return {"waiting": len(waiting) + unread, "applying": [r["code"] for r in self._drafts("state = 'approved'")]}

    def _control(self, msg, now, verb) -> str:
        since = self._paused()
        if verb == "status":
            self._reply(self._status(now, since))
        elif verb == "pause" and since:
            self._reply(answers.stopped_state(since, self._queue(msg)))
        elif verb == "pause":
            self.db.execute(CONTROL)
            self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('paused', '1', ?, ?)",
                            (_iso(now), msg.provider_id))
            self._reply(answers.stopped_state(_iso(now), self._queue(msg)))
        elif not since:
            self._reply("Changes are not paused.")
        else:  # resume never applies anything by itself
            self.db.execute("DELETE FROM control WHERE name = 'paused'")
            codes = [r["code"] for r in self._drafts("state = 'proposed'")]
            self._reply("Changes resumed." + (f"\nWaiting for approval: {', '.join(codes)}; reply yes <code> to apply."
                                              if codes else ""))
        return verb

    def _status(self, now, since) -> str:
        """Read-only: pause state, waiting drafts, the last apply result and confirmed guests of upcoming hikes."""
        lines = [f"Changes: paused since {_local(since)}" if since else "Changes: on"]
        if (cap := self.settings["interpreterDailyCap"]) is not None:
            lines.append(f"Interpreter today: {self._calls(now)[1]} of {cap}")  # H22, only with a cap
        with contextlib.suppress(OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            f = shelf.facts(load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content"), shelf.shop_today(now))
            lines.append(shelf.check_line(f, " - more than a week ago, the site says call to confirm"))  # AV1102-05
        lines += self._waiting_lines(now) or [NOTHING]
        lines += self._photo_lines(now)  # NB-AV-12: counts only, before Last change
        last = self.db.execute(  # the most recently approved change that has a result
            "SELECT d.* FROM drafts d JOIN approvals a ON a.change_id = d.change_id WHERE d.state IN"
            " ('applied', 'verified', 'failed', 'reverted') ORDER BY a.id DESC, d.row_id DESC LIMIT 1").fetchone()
        if last:  # SHOP-4: did it work, in plain words (whether it is on the website now), never the commit
            lines.append(f"Last change: {last['code']} {last['summary']} - "
                         + answers.did_it_work(dict(last), self._install(last), now))
        return "\n".join(lines + self._hike_lines(now))

    def _waiting_lines(self, now) -> list:
        """AV1102-11: one line per unexpired draft waiting for yes or for details; `status` and `report` share it."""
        return [f"{r['code']} waiting (expires {_local(r['expires_at'])}): {r['summary']}" if r["state"] == "proposed"
                else f"{r['code']} needs details: {r['summary']}"
                for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) > now]

    def _photo_lines(self, now) -> list:
        """NB-AV-12: waiting photo drafts (every op product.set_photo) and pending inbox messages with tries > 0.
        The inbox is opened read-only (never created); no file or no tries column means no line."""
        def photo_only(raw):
            try: ops = json.loads(raw)
            except (TypeError, ValueError): return False
            return isinstance(ops, list) and bool(ops) and all(
                isinstance(c, dict) and c.get("op") == "product.set_photo" for c in ops)
        n = sum(self._expiry(r) > now and photo_only(r["ops_json"]) for r in self._drafts("state = 'needs-details'"))
        lines, path = [f"Photos waiting for details: {n}"] if n else [], self.sdir / "inbox.sqlite3"
        if not path.is_file(): return lines
        try:
            with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True, timeout=1)) as db:
                if "tries" not in {r[1] for r in db.execute("PRAGMA table_info(inbound)")}: return lines
                m = db.execute("SELECT COUNT(*) FROM inbound WHERE state = 'pending' AND tries > 0").fetchone()[0]
        except sqlite3.Error:
            return lines + ["Photos still downloading: unavailable"]
        return lines + ([f"Photos still downloading: {m}"] if m else [])

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
            return ["Hikes: unavailable"]
        path, counts = self.settings.get("guestCountsDb"), None
        if any(e.get("rsvpEnabled") for e in upcoming) and isinstance(path, str) and path:  # RSVP-off only: never opened
            try:
                counts = hikes.guest_counts(path)
            except (sqlite3.Error, OSError, ValueError, TypeError):
                counts = None
        lines = []
        for e in upcoming:
            head = f"Hike {e.get('title')} {_hike_time(e['startsAt'])}: "
            limit = e.get("capacity") if e.get("capacity") is not None else "no limit"
            lines.append(head + ("RSVPs off" if not e.get("rsvpEnabled") else "guest count unavailable" if counts is None
                                 else f"{counts.get(e.get('id'), 0)} confirmed of {limit}"))
        for e in passed[:5]:
            title = e.get("title")
            lines.append(f"Hike {title} {_hike_time(e['startsAt'])} has passed but is still scheduled; "
                         f'send "complete {title}" or "cancel {title}" in your own words.')
        if len(passed) > 5:
            lines.append(f"… and {len(passed) - 5} more past hikes still scheduled.")
        return lines
