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

from hass import editor as editor_mod  # noqa: E402

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
APPROVE, REJECT = ("yes", "approve", "approved"), ("no", "cancel", "reject")
KEYWORD_RE = re.compile(r"(yes|approved|approve|no|cancel|reject)(?: ([0-9a-f]{4,12}))?")
TRANSITIONS = {"needs-details": {"proposed", "rejected"}, "proposed": {"approved", "rejected", "expired"},
               "approved": {"applied", "failed", "rejected"}, "applied": {"verified", "reverted"}}
INTERRUPTED = "interrupted; not applied; approve a new draft"
NOTHING = "Nothing is waiting for approval."
UNREADABLE = {"unsupported": "Sorry, I could not understand that request."}
VALUE_CUT = 120
SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(provider_id TEXT PRIMARY KEY, disposition TEXT NOT NULL, received_at TEXT);
CREATE TABLE IF NOT EXISTS drafts(row_id INTEGER PRIMARY KEY, change_id TEXT, code TEXT NOT NULL, state TEXT NOT NULL,
  reason TEXT, replaced_by TEXT, draft_hash TEXT, base TEXT, ops_json TEXT NOT NULL, summary TEXT NOT NULL,
  sender TEXT NOT NULL, chat TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT, "commit" TEXT);
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


def load_settings(sdir) -> dict:
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
    if problems: raise ConfigError("; ".join(problems))
    return {"ownerSenders": tuple(senders), "ownerChat": chat, "approvalTtlSeconds": ttl}


def parse_keyword(text: str):
    """(verb, code or None) when the whole message is an approval keyword; otherwise None."""
    match = KEYWORD_RE.fullmatch(re.sub(r"[.!]+$", "", text.strip().lower()))
    if not match: return None
    return ("approve" if match[1] in APPROVE else "reject"), match[2]


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
    def __init__(self, state_dir, editor, interpreter, clock):
        sdir = editor_mod.open_state(state_dir)
        self.settings, self.editor, self.interpreter, self.clock = load_settings(sdir), editor, interpreter, clock
        path = sdir / "conversation.sqlite3"
        os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
        os.chmod(path, 0o600)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.outbox = Outbox(self.db, self._now)
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

    def _reply(self, text):
        self.outbox.add(self.settings["ownerChat"], text)

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
        now = self._now()
        expired = [r for r in self._drafts("state = 'proposed'") if datetime.fromisoformat(r["expires_at"]) <= now]
        for row in expired: self._move(row, "expired")
        keyword = parse_keyword(msg.text)
        if keyword is None:
            disposition = self._request(msg, now)
            self._record(msg, disposition)
            return disposition, None
        verb, code = keyword
        targets = [r for r in self._drafts("state = 'proposed'") if code is None or r["code"] == code]
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
            return "\n".join(["Which draft do you mean?"] + [f"{r['code']}: {r['summary']}" for r in targets]
                             + ["Reply yes <code> or no <code>."])
        named = [self._by_code(code)] if code else [self._row(r["row_id"]) for r in expired]
        return "\n".join(self._state_text(r) for r in named if r is not None) or NOTHING

    def _state_text(self, row) -> str:
        code, state = row["code"], row["state"]
        if state == "expired": return f"{code} expired at {_local(row['expires_at'])}; nothing changed."
        if state == "rejected" and row["replaced_by"]: return f"{code} was replaced by {row['replaced_by']}."
        if state == "rejected": return f"{code} was cancelled ({row['reason']}); nothing changed."
        return f"{code} is {state}."

    def _request(self, msg, now) -> str:
        pending = [{"code": r["code"], "state": r["state"], ("question" if r["state"] == "needs-details" else "summary"):
                    r["summary"]} for r in self._drafts("state IN ('proposed', 'needs-details')")]
        result = _checked(self.interpreter.interpret(msg.text, pending))
        for key in ("question", "unsupported"):
            if key in result:
                self._reply(result[key])
                return key
        revised = self._by_code(result["revises"], ("proposed", "needs-details")) if result["revises"] else None
        out = self.editor.prepare(result["ops"])
        if out["result"] == "needs-details":
            ops_json = json.dumps(result["ops"], sort_keys=True)
            if revised is not None and revised["state"] == "needs-details":
                self.db.execute("UPDATE drafts SET ops_json = ?, summary = ? WHERE row_id = ?",
                                (ops_json, out["question"], revised["row_id"]))
            else:
                code = self._code(hashlib.sha256(msg.provider_id.encode()).hexdigest())
                self.db.execute(
                    "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at)"
                    " VALUES (?, 'needs-details', ?, ?, ?, ?, ?)",
                    (code, ops_json, out["question"], msg.sender, msg.chat, _iso(now)))
                # An incomplete correction still supersedes the proposal it names: it can no longer be approved.
                if revised is not None: self._move(revised, "rejected", reason="revised", replaced_by=code)
            self._reply(out["question"])
            return "needs-details"
        if out["result"] != "ok":
            self._reply(f"Not drafted: {_reason(out)}")
            return "not-drafted"
        draft = out["draft"]
        same = [r for r in self._drafts("state = 'proposed' AND change_id = ?", draft["change_id"])]
        if same and (revised is None or revised["row_id"] == same[0]["row_id"]):
            row = same[0]
        elif revised is not None and revised["state"] == "needs-details":
            row = self._propose(draft, msg.sender, now, row=revised)
        else:
            row = self._propose(draft, msg.sender, now)
            if revised is not None: self._move(revised, "rejected", reason="revised", replaced_by=row["code"])
        self._reply(proposal_text(row["code"], draft, row["expires_at"], self._repeat(row)))
        return "proposed"

    def _outcome(self, row, out, now):
        """Store the apply result and its reply in one transaction (before anything is sent)."""
        result = out.get("result")
        if result in ("applied", "already-applied"):
            self._move(row, "applied", commit=out.get("commit"))
            self._reply(f"Applied {row['code']}: {row['summary']}")
        elif result == "stale":
            again = self.editor.prepare(json.loads(row["ops_json"]))
            if again["result"] == "ok":
                new = self._propose(again["draft"], row["sender"], now)
                self._move(row, "rejected", reason="stale", replaced_by=new["code"])
                self._reply(f"The site changed since {row['code']}; please approve {new['code']}.\n"
                            + proposal_text(new["code"], again["draft"], new["expires_at"], self._repeat(new)))
            else:
                self._move(row, "rejected", reason="stale")
                self._reply(f"The site changed since {row['code']}; not applied: {_reason(again)}")
        else:
            self._move(row, "failed", reason=_reason(out))
            self._reply(f"Not applied: {_reason(out)}")

    def recover(self) -> list:
        """Settle drafts left `approved` by a crash from the editor's change record. Never calls apply again."""
        rows = self._drafts("state = 'approved'")
        if not rows: return []
        if hasattr(self.editor, "recover"): self.editor.recover()  # settles journals; never re-applies
        with self._tx():
            for row in rows:
                change = self.editor.show(row["change_id"]).get("change") or {}
                if change.get("state") == "applied":
                    self._outcome(row, {"result": "applied", "commit": change.get("commit")}, self._now())
                else:
                    self._move(row, "failed", reason=INTERRUPTED)
                    self._reply(f"Not applied: {INTERRUPTED}")
        return [self._row(r["row_id"])["state"] for r in rows]
