"""Hass conversation core (H05): owner messages -> A2 drafts -> bound approval -> one apply.

The interpreter only turns text into typed ops (it never sees approvals or calls the editor); deterministic code
does every write. handle() stores each result (message id, draft state, reply) before any reply is sent; flush()
sends. Approval is bound to sender, chat, change id, draft hash, base revision and expiry. Fixture adapter only.
"""
import contextlib, copy, hashlib, json, os, re, sqlite3, sys  # noqa: E401
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor as editor_mod, memory as memory_mod, migration_check, preview as preview_mod, sitegen  # noqa: E402
from hass import claims, interpret_check, media  # noqa: E402
from hass.content_model import ContentError, load_and_validate, load_content  # noqa: E402
from hass.ops import catalog, hikes, load_registry  # noqa: E402

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
APPROVE, REJECT = ("yes", "approve", "approved"), ("no", "cancel", "reject")
KEYWORD_RE = re.compile(r"(yes|approved|approve|no|cancel|reject)(?: ([0-9a-f]{4,12}))?")
COMMAND_RE = re.compile(r"(history)|(undo)(?: ([0-9a-f]{4,12}))?"  # H06, same normalisation as KEYWORD_RE
                        r"|(status)|(pause)(?: changes)?|(resume)(?: changes)?|(help|commands|\?)")  # H17
HELP_TEXT = "\n".join(('Send a change in plain words: "Make the avocado description shorter".',  # AV1537-03, test_help
    'yes [code] - apply the waiting draft: "yes a1b2"',
    'no [code] - cancel the waiting draft or question: "no a1b2"',
    'status - pause state, waiting drafts, hike seats: "status"',
    'history - the last five changes: "history"',
    'undo [code] - draft an undo of an applied change: "undo a1b2"',
    'pause changes - stop approvals from applying: "pause changes"',
    'resume changes - let approvals apply again: "resume changes"',
    'remember <key>: <text> - save a note: "remember parking: back lot"',
    'forget <key> - delete a saved note: "forget parking"',
    'memory - list the saved notes: "memory"',
    'alias <name>: <id> - name an id: "alias jam: photo-product-001"',
    'help (or commands, ?) - this list: "help"'))
# H15 owner memory. Verb and key are case-insensitive (the key is stored lower-cased); the text keeps its case.
MEMORY_RE = re.compile(r"(remember)(?:\s+(.*))?|(forget)\s+(\S+)|(memory)|(alias)(?:\s+(.*))?", re.IGNORECASE | re.DOTALL)
MEMORY_LIST_MAX = 20
PAUSED_LINE = "Changes are paused; send resume changes before yes."
ATTACHMENT_REPLY = ("Photos, voice notes and files are not supported yet, so nothing changed. "
                    "Please send the change as text.")
PHOTO_QUESTION = ("Which product is this photo for, and how would you describe the photo in a few words (for people who "
                  "cannot see it)?")  # NB-AV-09 (H12): asked by every new photo draft
# H17 pause flag. Created by the first `pause` (not in SCHEMA) so the H05 store keeps its four tables until then.
CONTROL = """CREATE TABLE IF NOT EXISTS control(name TEXT PRIMARY KEY, value TEXT NOT NULL, set_at TEXT NOT NULL,
  provider_id TEXT NOT NULL)"""
USAGE = "CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY, calls INTEGER NOT NULL)"  # H22; lazy like CONTROL
DAILY_LIMIT = ("Today's limit for reading change requests is reached, so nothing was drafted. "
               "Commands (status, yes/no, undo) still work; send the change again tomorrow.")
TRANSITIONS = {"needs-details": {"proposed", "rejected", "expired"}, "proposed": {"approved", "rejected", "expired"},
               "approved": {"applied", "failed", "rejected"}, "applied": {"verified", "reverted"},
               "verified": {"reverted"}}
INTERRUPTED = "interrupted; not applied; approve a new draft"
NOTHING = "Nothing is waiting for approval."
UNREADABLE = {"unsupported": "Sorry, I could not understand that request."}
VALUE_CUT = 120
SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(provider_id TEXT PRIMARY KEY, disposition TEXT NOT NULL, received_at TEXT);
CREATE TABLE IF NOT EXISTS drafts(row_id INTEGER PRIMARY KEY, change_id TEXT, code TEXT NOT NULL, state TEXT NOT NULL,
  reason TEXT, replaced_by TEXT, draft_hash TEXT, base TEXT, ops_json TEXT NOT NULL, summary TEXT NOT NULL,
  sender TEXT NOT NULL, chat TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT, "commit" TEXT,
  screenshot TEXT, checked_at TEXT);
CREATE TABLE IF NOT EXISTS approvals(id INTEGER PRIMARY KEY, sender TEXT NOT NULL, chat TEXT NOT NULL,
  provider_id TEXT NOT NULL, change_id TEXT NOT NULL, draft_hash TEXT NOT NULL, base TEXT NOT NULL,
  expires_at TEXT NOT NULL, approved_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, chat TEXT NOT NULL, text TEXT NOT NULL,
  attachments TEXT NOT NULL, created_at TEXT NOT NULL, sent_at TEXT);
"""


class ConfigError(Exception): """ownerSenders, ownerChat or approvalTtlSeconds is missing or invalid; nothing starts."""


class TransitionError(Exception): """A draft state change outside the allowed transitions."""


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

    def interpret(self, text, pending):
        return copy.deepcopy(self.mapping.get(text, {"unsupported": "Sorry, I can't do that yet."}))


class Outbox:
    """Replies stored in the same transaction as the result; flush() sends them in order and marks each sent."""

    def __init__(self, db, now):
        self.db, self._now = db, now

    def add(self, chat, text, attachments=()):
        self.db.execute("INSERT INTO outbox(chat, text, attachments, created_at) VALUES (?, ?, ?, ?)",
                        (chat, text, json.dumps(list(attachments)), _iso(self._now())))

    def unsent(self):
        return self.db.execute("SELECT * FROM outbox WHERE sent_at IS NULL ORDER BY id").fetchall()

    def flush(self, adapter) -> int:
        """A raised send error propagates and leaves that row and every later row unsent."""
        sent = 0
        for row in self.unsent():
            adapter.send(row["chat"], row["text"], json.loads(row["attachments"]))
            self.db.execute("UPDATE outbox SET sent_at = ? WHERE id = ?", (_iso(self._now()), row["id"]))
            sent += 1
        return sent


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")


def load_settings(sdir, photos=False) -> dict:
    try:
        settings = json.loads((Path(sdir) / "config.json").read_text("utf-8")).get("settings")
    except (OSError, ValueError, AttributeError):
        settings = None
    if not isinstance(settings, dict): raise ConfigError("config.json settings are missing")
    senders, chat, ttl = (settings.get(k) for k in ("ownerSenders", "ownerChat", "approvalTtlSeconds"))
    problems = []
    if not isinstance(senders, list) or not senders or not all(isinstance(s, str) and s.strip() for s in senders):
        problems.append("ownerSenders must be a non-empty list of sender addresses")
    if not isinstance(chat, str) or not chat.strip(): problems.append("ownerChat must be a chat id")
    if type(ttl) is not int or ttl < 60: problems.append("approvalTtlSeconds must be an integer >= 60")
    root = settings.get("mediaRoot")  # NB-AV-09: required only with a photo source
    if photos and (not isinstance(root, str) or not root.strip()): problems.append("mediaRoot must be set to use photos")
    cap = settings.get("interpreterDailyCap")  # H22: optional; absent or null means no cap (no default enables it)
    if cap is not None and (type(cap) is not int or not 1 <= cap <= 10000):
        problems.append("interpreterDailyCap must be an integer 1-10000")
    if problems: raise ConfigError("; ".join(problems))
    return {"ownerSenders": tuple(senders), "ownerChat": chat, "approvalTtlSeconds": ttl, "mediaRoot": root,
            "guestCountsDb": settings.get("guestCountsDb"), "interpreterDailyCap": cap}  # guestCountsDb: H17, unchecked


def parse_keyword(text: str):
    """(verb, code or None) when the whole message is an approval keyword; otherwise None."""
    match = KEYWORD_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()))
    if not match: return None
    return ("approve" if match[1] in APPROVE else "reject"), match[2]


def parse_command(text: str):
    """("undo", code or None) or (history|status|pause|resume|help, None) when the whole message is that command;
    otherwise None."""
    match = COMMAND_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()))
    if not match: return None
    if match[7]: return "help", None
    return ("undo", match[3]) if match[2] else (next(v for v in (match[1], match[4], match[5], match[6]) if v), None)


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


def _value(v) -> str:
    text = "(none)" if v is None else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= VALUE_CUT else text[:VALUE_CUT - 3] + "..."


def _changes(record: dict):
    before, after = record.get("before"), record.get("after")
    if isinstance(before, dict) and isinstance(after, dict):
        return [(k, before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
    return [("record", before, after)]


def _summary(draft: dict) -> str:
    text = "; ".join(f"{r['collection']} {r['key']}: " + ", ".join(f for f, _b, _a in _changes(r))
                     for r in draft["records"])
    return _value(text or "no records")


def proposal_text(code: str, draft: dict, expires_at: str, repeat: bool = False) -> str:
    lines = [f"Draft {code}:"]
    lines += [f"{r['collection']} {r['key']}: {f} {_value(b)} → {_value(a)}"
              for r in draft["records"] for f, b, a in _changes(r)]
    lines += [f"Warning: {w}" for w in draft.get("warnings") or []]
    yes = f"yes {code}" if repeat else "yes"  # a repeat of a closed draft needs its new code
    lines += [f"Expires {_local(expires_at)}.", f"Reply {yes} to apply, no to cancel, or send a correction."]
    return "\n".join(lines)


class Conversation:
    def __init__(self, state_dir, editor, interpreter, clock, previewer=None, photos=None):
        """previewer (H06, e.g. preview.Previewer(worktree)): proposal screenshots and checked results; None keeps
        the H05 behaviour (no screenshot, an applied draft stays `applied`)."""
        sdir = editor_mod.open_state(state_dir)
        self.settings, self.photos = load_settings(sdir, photos is not None), photos  # fetch(provider_id, n) -> [bytes]
        self.editor, self.interpreter, self.clock = editor, interpreter, clock
        self.sdir, self.previewer = sdir, previewer
        path = sdir / "conversation.sqlite3"
        os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
        os.chmod(path, 0o600)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        columns = {r["name"] for r in self.db.execute("PRAGMA table_info(drafts)")}
        for column in ("screenshot", "checked_at"):  # an H05 database gains the H06 columns
            if column not in columns: self.db.execute(f"ALTER TABLE drafts ADD COLUMN {column} TEXT")
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
        self.outbox.add(self.settings["ownerChat"], text, attachments)

    def _proposal_reply(self, row, draft, prefix=""):
        """The proposal text plus, with a previewer, a private screenshot of the rendered draft (H06)."""
        text, shots = prefix + proposal_text(row["code"], draft, row["expires_at"], self._repeat(row)), []
        if self.previewer is not None:
            rendered = self.editor.render_draft(draft["change_id"])
            shot = self.previewer.capture(rendered["files"], preview_mod.target_for(draft["records"][0]),
                                          self.sdir / "screenshots" / f"{draft['change_id']}-proposal.png") \
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
                      ops_json=json.dumps(draft["ops"], sort_keys=True), summary=_summary(draft), expires_at=expires)
        if row is not None:
            self._move(row, "proposed", **fields)
            return self._row(row["row_id"])
        cur = self.db.execute(
            "INSERT INTO drafts(change_id, code, state, draft_hash, base, ops_json, summary, sender, chat, created_at,"
            " expires_at) VALUES (?, ?, 'proposed', ?, ?, ?, ?, ?, ?, ?, ?)",
            (fields["change_id"], self._code(draft["draft_hash"][7:]), fields["draft_hash"], fields["base"],
             fields["ops_json"], fields["summary"], sender, self.settings["ownerChat"], _iso(now), expires))
        return self._row(cur.lastrowid)

    # -- message handling ----------------------------------------------------------------------------------------
    def handle(self, msg: Inbound) -> str:
        """Process one inbound message; returns its disposition. Replies are only enqueued (see flush)."""
        with self._tx():
            disposition, approved = self._handle(msg)
        if approved is None: return disposition
        out = self.editor.apply(approved["change_id"], approved["draft_hash"])
        with self._tx():
            self._outcome(self._row(approved["row_id"]), out, self._now())
        self._verify_pending()
        return disposition

    def _handle(self, msg):
        if self.db.execute("SELECT 1 FROM messages WHERE provider_id = ?", (msg.provider_id,)).fetchone():
            return "duplicate", None
        s = self.settings
        ignored = "echo" if msg.from_me else "edited-ignored" if msg.kind != "new" else \
            "ignored" if msg.chat != s["ownerChat"] or msg.sender not in s["ownerSenders"] else None
        if ignored:
            self._record(msg, ignored, owner=False)
            return ignored, None
        if msg.attachments > 0 and self.photos is None:  # H12 part 1: the caption is never interpreted
            self._reply(ATTACHMENT_REPLY)
            self._record(msg, "attachment-unsupported")
            return "attachment-unsupported", None
        now, command = self._now(), None if msg.attachments > 0 else parse_command(msg.text)
        expired = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) <= now]
        if command and command[0] in ("status", "help"): expired = []  # H17: read-only; status only hides lapsed drafts
        for row in expired: self._move(row, "expired", expires_at=_iso(self._expiry(row)))
        if command or msg.attachments > 0:  # NB-AV-09: a photo caption is never a command, keyword or approval
            disposition = self._photo(msg, now) if msg.attachments > 0 else self._command(msg, now, *command)
            self._record(msg, disposition)
            return disposition, None
        memory = parse_memory(msg.text)
        if memory:  # not a site change: never the interpreter or editor, and pause does not apply
            disposition = self._memory(msg, *memory)
            self._record(msg, disposition)
            return disposition, None
        keyword = parse_keyword(msg.text)
        if keyword is None:
            disposition = self._request(msg, now)
            self._record(msg, disposition)
            return disposition, None
        verb, code = keyword
        # AV1537-02: no/cancel also closes an open (unexpired) question; yes only ever targets a proposal.
        states = "('proposed', 'needs-details')" if verb == "reject" else "('proposed')"
        targets = [r for r in self._drafts(f"state IN {states}") if code is None or r["code"] == code]
        if verb == "approve" and code and not targets and (ask := self._by_code(code, ("needs-details",))):
            # a waiting question is never approved; a bare yes keeps NOTHING (test_conversation pins it)
            self._reply(f"{ask['code']} still needs details: {ask['summary']}")
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
        except (OSError, ValueError, KeyError, TypeError, editor_mod.UnsafeState):
            return None
        return makers if isinstance(makers, dict) else None

    def _request(self, msg, now) -> str:
        cap = self.settings["interpreterDailyCap"]
        if cap is not None:  # H22: counted before the call in this transaction, so a failed call still counts
            day, calls = self._calls(now)
            if calls >= cap:
                self._reply(DAILY_LIMIT)
                return "daily-limit"
            self.db.execute(USAGE)
            self.db.execute("INSERT INTO usage VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET calls = calls + 1", (day,))
        pending = [{"code": r["code"], "state": r["state"], ("question" if r["state"] == "needs-details" else "summary"):
                    r["summary"]} for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) > now]
        try:
            result = _checked(self.interpreter.interpret(msg.text, pending))
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
        calls = [c for c in result["ops"] if c["op"] == "product.set_photo"] if photo else []
        if any(c["args"].setdefault("photo", photo) != photo for c in calls):
            return self._reply("That draft is for another photo.") or "photo-mismatch"
        out = self.editor.prepare(result["ops"])
        if out["result"] == "needs-details":
            ops_json = json.dumps(result["ops"], sort_keys=True)
            expires = _iso(now + timedelta(seconds=self.settings["approvalTtlSeconds"]))  # H16: questions lapse too
            if revised is not None and revised["state"] == "needs-details":  # the owner just answered: refresh
                self.db.execute("UPDATE drafts SET ops_json = ?, summary = ?, expires_at = ? WHERE row_id = ?",
                                (ops_json, out["question"], expires, revised["row_id"]))
            else:
                code = self._code(hashlib.sha256(msg.provider_id.encode()).hexdigest())
                self.db.execute(
                    "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at)"
                    " VALUES (?, 'needs-details', ?, ?, ?, ?, ?, ?)",
                    (code, ops_json, out["question"], msg.sender, msg.chat, _iso(now), expires))
                # An incomplete correction still supersedes the proposal it names: it can no longer be approved.
                if revised is not None: self._move(revised, "rejected", reason="revised", replaced_by=code)
            self._reply(out["question"])
            return "needs-details"
        if out["result"] != "ok":
            self._reply(f"Not drafted: {_reason(out)}")
            return "not-drafted"
        draft = out["draft"]
        if hits := claims.unstated(draft, msg.text, self._makers()):  # NB-AV-05: an unstated claim asks, never drafts
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

    def _photo(self, msg, now) -> str:  # NB-AV-09: store one photo, then open (or name) its needs-details draft
        if msg.attachments != 1: return self._reply("One photo at a time, please; nothing was saved.") or "attachment-many"
        try:
            sha = media.store_original(self.settings["mediaRoot"], self.photos.fetch(msg.provider_id, 1)[0],
                                       received_at=msg.received_at or _iso(now), source="owner-chat")["sha256"]
        except media.Refused as exc:
            return self._reply(exc.reply) or "photo-refused"
        dup = self._drafts("state IN ('proposed', 'needs-details') AND ops_json LIKE ?", f'%"photo": "{sha}"%')
        if dup: return self._reply(f"That photo is already in draft {dup[0]['code']}." + (
            f" {dup[0]['summary']}" if dup[0]["state"] == "needs-details" else "")) or "photo-duplicate"
        self.db.execute("INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at) VALUES"
                        " (?, 'needs-details', ?, ?, ?, ?, ?)", (code := self._code(sha), json.dumps(
                            [{"op": "product.set_photo", "args": {"photo": sha}}]), PHOTO_QUESTION, msg.sender, msg.chat, _iso(now)))
        self._reply(f"{PHOTO_QUESTION} Reply with the product and description (draft {code}).")
        caption = msg.text.replace("\ufffc", "").strip()  # handled as the next text, in this same transaction
        return self._request(Inbound(**{**vars(msg), "text": caption}), now) if caption else "photo-draft"

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
            if self.previewer is None: self._reply(f"Applied {row['code']}: {row['summary']}")
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
                        self._reply(f"Not applied: {INTERRUPTED}")
        self._verify_pending()
        return [self._row(r["row_id"])["state"] for r in rows]

    # -- H06: checked results, history and undo ------------------------------------------------------------------
    def verify(self, row):
        """(screenshot path, None) when the worktree is current, the migration checks pass and the result
        screenshot's checks pass; otherwise (None, error)."""
        wt = editor_mod._load(str(self.sdir))[2]
        try:
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            stale = sitegen.diff_paths(sitegen.render(content, wt / "hass" / "templates"), wt)
        except ContentError as exc:
            return None, "; ".join(exc.problems)
        problems = [f"generated file out of date: {p}" for p in stale] + migration_check.run_checks(wt)[0]
        if problems: return None, "; ".join(problems)
        change = self.editor.show(row["change_id"]).get("change") or {}
        if not change.get("records"): return None, "no change record"
        files = {p: (wt / p).read_bytes() for p in editor_mod.GENERATED_PATHS}  # the committed files
        shot = self.previewer.capture(files, preview_mod.target_for(change["records"][0]),
                                      self.sdir / "screenshots" / f"{row['change_id']}-result.png")
        return (shot["png"], None) if shot["ok"] else (None, shot["error"])

    def _verify_pending(self):
        if self.previewer is None: return
        for row in self._drafts("state = 'applied' AND checked_at IS NULL"):
            png, error = self.verify(row)  # outside the transaction; the result and reply are stored together
            with self._tx():
                if png:
                    self._move(row, "verified", screenshot=png, checked_at=_iso(self._now()))
                    self._reply(f"Applied and checked {row['code']}: {row['summary']}", [png])
                else:
                    self.db.execute("UPDATE drafts SET reason = ?, checked_at = ? WHERE row_id = ?",
                                    (f"not verified: {error}", _iso(self._now()), row["row_id"]))
                    self._reply(f"Applied {row['code']}, but the preview check failed: {error}")

    def _command(self, msg, now, verb, code) -> str:
        if verb == "help":
            self._reply(HELP_TEXT)
            return "help"
        if verb in ("status", "pause", "resume"): return self._control(msg, now, verb)
        if verb == "history":
            rows = self.db.execute("SELECT * FROM drafts ORDER BY row_id DESC LIMIT 5").fetchall()
            self._reply("\n".join(["Recent changes:"] + [
                f"{r['code']} {r['state']}: {r['summary']}" + (f" ({r['commit'][:7]})" if r["commit"] else "")
                for r in rows]) if rows else "No changes yet.")
            return "history"
        done = [r for r in self._drafts("change_id IS NOT NULL AND \"commit\" IS NOT NULL")
                if code is None and r["state"] in ("applied", "verified") or r["code"] == code]
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

    # -- H15: remember, forget, memory ---------------------------------------------------------------------------
    def _memory(self, msg, verb, key, value) -> str:
        """Owner-stated facts on this connection inside the message's transaction; a store ValueError undoes only
        that op's savepoint and the message is still recorded. The interpreter never reads memory."""
        if self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        if verb == "memory":
            rows = self.memory.list()
            lines = [f"{r['key']}: {r['value']} ({r['kind']}, since "
                     f"{datetime.fromisoformat(r['created_at']).astimezone(LOCAL_TZ):%Y-%m-%d})"
                     for r in rows[:MEMORY_LIST_MAX]]
            more = [f"… and {len(rows) - MEMORY_LIST_MAX} more."] if len(rows) > MEMORY_LIST_MAX else []
            self._reply("\n".join([f"Saved ({len(rows)}):"] + lines + more) if rows else "Nothing saved.")
            return "memory-list"
        if verb == "alias": return self._alias(msg, key, value)
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
        old, source = (self.memory.get(key) if valid else None), f"owner-stated:{msg.provider_id}"
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

    def _alias(self, msg, name, ident) -> str:
        """`alias <name>: <id>` saves memory alias.<slug> = product:<id> | maker:<key>, only if that record exists now."""
        key, found = "alias." + catalog._fold(name).replace(" ", "-"), []
        problem = ("alias name must be 1–60 plain letters, digits, spaces, . or -" if not memory_mod._clean(name)
                   or len(name) > 60 or not memory_mod.KEY_RE.fullmatch(key[6:]) or not memory_mod.KEY_RE.fullmatch(key)
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
        self.memory.remember(key, value, "fact", source) if old is None else self.memory.correct(key, value, source)
        kind, rec, status = found[0]
        target = f"{kind} {ident} ({rec['name']}" + ("" if status in ("active", "visible") else f", {status}") + ")"
        self._reply((f"Saved alias {name} → " if old is None else f"Updated alias {name} (was: {old}) → ")
                    + f"{target}. Send forget {key} to remove it.")
        return "memory-saved" if old is None else "memory-updated"

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

    def _control(self, msg, now, verb) -> str:
        since = self._paused()
        if verb == "status":
            self._reply(self._status(now, since))
        elif verb == "pause" and since:
            self._reply(f"Changes are already paused (since {_local(since)}).")
        elif verb == "pause":
            self.db.execute(CONTROL)
            self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('paused', '1', ?, ?)",
                            (_iso(now), msg.provider_id))
            self._reply("Changes paused. Drafts can still be prepared; nothing is applied until you send resume changes.")
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
        lines += [f"{r['code']} waiting (expires {_local(r['expires_at'])}): {r['summary']}" if r["state"] == "proposed"
                  else f"{r['code']} needs details: {r['summary']}"
                  for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) > now] or [NOTHING]
        last = self.db.execute(  # the most recently approved change that has a result
            "SELECT d.* FROM drafts d JOIN approvals a ON a.change_id = d.change_id WHERE d.state IN"
            " ('applied', 'verified', 'failed', 'reverted') ORDER BY a.id DESC, d.row_id DESC LIMIT 1").fetchone()
        if last:
            text = f"Last change: {last['code']} {last['state']}: {last['summary']}"
            text += f" ({last['commit'][:7]})" if last["commit"] else ""
            if last["reason"] and (last["state"] == "failed" or last["state"] == "applied"
                                   and last["reason"].startswith("not verified: ")):
                text += f" - {last['reason']}"
            lines.append(text)
        return "\n".join(lines + self._hike_lines(now))

    def _hike_lines(self, now) -> list:
        """Scheduled hikes after now with seat totals only (never names or emails); unknown counts are never guessed."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            events = json.loads((wt / "hass" / "content" / "community.json").read_text("utf-8"))["events"]
            upcoming = sorted(((datetime.fromisoformat(e["startsAt"]), e) for e in events
                               if e.get("status") == "scheduled"), key=lambda pair: pair[0])
            upcoming = [e for start, e in upcoming if start > now]
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            return ["Hikes: unavailable"]
        path, counts = self.settings.get("guestCountsDb"), None
        if any(e.get("rsvpEnabled") for e in upcoming) and isinstance(path, str) and path:  # RSVP-off only: never opened
            try:
                counts = hikes.guest_counts(path)
            except (sqlite3.Error, OSError, ValueError, TypeError):
                counts = None
        lines = []
        for e in upcoming:
            head = f"Hike {e.get('title')} {_local(e['startsAt'])}: "
            limit = e.get("capacity") if e.get("capacity") is not None else "no limit"
            lines.append(head + ("RSVPs off" if not e.get("rsvpEnabled") else "guest count unavailable" if counts is None
                                 else f"{counts.get(e.get('id'), 0)} confirmed of {limit}"))
        return lines
