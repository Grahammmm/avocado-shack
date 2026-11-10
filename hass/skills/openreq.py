"""Open request store (SKILLS-FW-3): what Hass is in the middle of, so a short answer is joined to what it answers.

One private table, ``open_requests``, inside the existing conversation.sqlite3 (so ``statebackup`` already covers it).
It GENERALISES the HASS-HIKE-FLOW-1 / HASS-SHELFCHECK-FLOW-1 table ``open_asks`` (owner texts + our question + the
change waiting for today's shelf check): those rows are migrated in and the old table is dropped, so there is one
mechanism, not two. A row with ``skill`` NULL is that old kind of open request ("legacy": texts, question, optional
``pending_json``); a row with a skill also carries the validated slots, the asked slot and the call queue.

Rules (spec 2.6): at most ONE live (open or drafted) request per owner; expiry 30 minutes after the owner's last
message and never more than 2 hours after the first; the owner's texts are capped (each MAX_OWNER_TEXT, all
MAX_TOTAL_TEXT) and are erased 24 hours after the request closes (D7; a legacy row is erased at once); texts are private:
nothing here logs, prints or returns them to anyone but the owner's own next turn. Only the owner key given by the
caller reads or writes a row: another chat or a stranger never reaches it (the conversation drops them first, and
every read here also filters on the owner key).

Nothing in this module calls a model, the editor or the network.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from hass import nl_prep

TABLE = """CREATE TABLE IF NOT EXISTS open_requests(request_id INTEGER PRIMARY KEY AUTOINCREMENT, provider_id TEXT NOT NULL,
  owner TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('open','drafted','closed','expired','cancelled','superseded')),
  skill TEXT, slots_json TEXT NOT NULL DEFAULT '{}', calls_json TEXT NOT NULL DEFAULT '[]', texts_json TEXT NOT NULL,
  asked_slot TEXT, question TEXT, ask_json TEXT, attachments_json TEXT NOT NULL DEFAULT '[]', draft_code TEXT,
  pending_json TEXT, asks INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  expires_at TEXT NOT NULL, closed_at TEXT)"""
INDEX = "CREATE UNIQUE INDEX IF NOT EXISTS open_requests_one_live ON open_requests(owner) WHERE state IN ('open','drafted')"
LIVE = ("open", "drafted")
CLOSED = ("closed", "expired", "cancelled", "superseded")

TTL_MINUTES, MAX_MINUTES = 30, 120  # 30 minutes after the last owner message (RECENT_MINUTES), at most 2 hours from the first
MAX_OWNER_TEXT, MAX_TOTAL_TEXT = 4000, 8000  # each owner text, and all of a request's texts together (spec 2.6; D7)
RETENTION_HOURS = 24  # D7: a closed request keeps its row (not its meaning for anyone else) this long, then it is erased
MAX_UNRESOLVED = 3  # the same question may be asked three times; the third unresolved one closes the request ("stuck")
CHEAP_WORDS = 12  # an answer this short may be read by code alone, without the model
MAX_ATTACHMENTS = 5
SHA_RE = re.compile(r"[0-9a-f]{64}")
CHEAP_KINDS = ("product_ref", "maker_ref", "hike_ref", "route_ref", "shelf", "day", "clock", "availability")
FILLER = {"the", "one", "please", "a", "an", "that", "this", "it", "is", "its", "i", "mean", "means", "yes", "just"}
EXTRA = {"and", "also", "plus", "but", "call", "called", "rename", "change", "add", "instead", "title", "then", "too"}  # more than the answer
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
            "ninth": 9, "tenth": 10}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _idle_deadline(now: datetime) -> datetime:
    # Add on the timeline, not the repeated/skipped wall-clock hour. Keep naive semantics.
    if now.utcoffset() is None:
        return now + timedelta(minutes=TTL_MINUTES)
    return (now.astimezone(timezone.utc) + timedelta(minutes=TTL_MINUTES)).astimezone(now.tzinfo)


def bound_texts(texts, *, turns=None, per=MAX_OWNER_TEXT, total=MAX_TOTAL_TEXT) -> list:
    """The texts to keep: each cut to ``per`` characters, at most the last ``turns``, the oldest dropped while over ``total``."""
    kept = [str(t)[:per] for t in texts if isinstance(t, str) and t]
    if turns is not None:
        kept = kept[-turns:]
    while len(kept) > 1 and sum(map(len, kept)) > total:
        kept.pop(0)
    return kept


def _loads(raw, kind, default):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return default
    return value if isinstance(value, kind) else default


class OpenRequests:
    def __init__(self, db):
        """``db`` is an open sqlite3 connection with ``row_factory = sqlite3.Row`` (the Conversation's). Nothing is created
        until the first write, so a store that never held a request keeps the tables it had."""
        self.db = db

    # -- table ------------------------------------------------------------------------------------------------
    def exists(self) -> bool:
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'open_requests'").fetchone() is not None

    def ensure(self, owner: str = "") -> None:
        """Create the table (once) and fold a pre-FW-3 ``open_asks`` table into it, then drop that table."""
        self.db.execute(TABLE)
        self.db.execute(INDEX)
        self.adopt_legacy(owner)

    def adopt_legacy(self, owner: str) -> int:
        """Move rows of the old two-flow table ``open_asks`` into ``open_requests`` under ``owner``; drop the old table."""
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'open_asks'").fetchone():
            return 0
        self.db.execute(TABLE)
        self.db.execute(INDEX)
        cols = {c["name"] for c in self.db.execute("PRAGMA table_info(open_asks)")}
        moved = 0
        for row in self.db.execute("SELECT * FROM open_asks").fetchall():
            try:
                asked = datetime.fromisoformat(row["asked_at"])
            except (TypeError, ValueError):
                continue  # an unreadable row is no open request
            texts = _loads(row["texts_json"], list, None)
            if texts is None or not all(isinstance(t, str) and t for t in texts):
                continue
            pending = row["pending_json"] if "pending_json" in cols else None
            self.db.execute("DELETE FROM open_requests WHERE owner = ? AND state IN ('open','drafted')", (owner,))
            self.db.execute(
                "INSERT INTO open_requests(provider_id, owner, state, texts_json, pending_json, created_at, updated_at, expires_at)"
                " VALUES (?, ?, 'open', ?, ?, ?, ?, ?)",
                (row["provider_id"], owner, json.dumps(bound_texts(texts, per=MAX_OWNER_TEXT), ensure_ascii=False), pending,
                 _iso(asked), _iso(asked), _iso(asked + timedelta(minutes=TTL_MINUTES))))
            moved += 1
        self.db.execute("DROP TABLE open_asks")
        return moved

    # -- reading ----------------------------------------------------------------------------------------------
    def _row(self, where: str, *args):
        try:
            if not self.exists():
                return None
            return self.db.execute(f"SELECT * FROM open_requests WHERE {where}", args).fetchone()
        except sqlite3.Error:
            return None

    def get(self, owner: str, now: datetime):
        """The owner's live (open or drafted), unexpired request as a dict, else None. Never another owner's."""
        row = self._row("owner = ? AND state IN ('open','drafted') ORDER BY request_id DESC LIMIT 1", owner)
        return self._view(row, now)

    def by_provider(self, owner: str, provider_id: str, now: datetime):
        """The live request whose last owner message was ``provider_id`` (the HIKE-FLOW-1 lookup for \"earlier\")."""
        row = self._row("owner = ? AND provider_id = ? AND state IN ('open','drafted')", owner, provider_id)
        return self._view(row, now)

    def pending_of(self, owner: str, now: datetime):
        """The live row that carries a change waiting for the shelf check (SHELFCHECK-FLOW-1), else None."""
        row = self._row("owner = ? AND pending_json IS NOT NULL AND state = 'open'", owner)
        return self._view(row, now)

    def _view(self, row, now):
        try:
            return self._view_row(row, now)
        except (IndexError, KeyError, TypeError):
            return None  # a table that is not ours or a damaged row is no open request

    def _view_row(self, row, now):
        if row is None:
            return None
        try:
            if now > datetime.fromisoformat(row["expires_at"]):
                return None
        except (TypeError, ValueError):
            return None
        texts = _loads(row["texts_json"], list, [])
        return {"request_id": row["request_id"], "provider_id": row["provider_id"], "owner": row["owner"],
                "state": row["state"], "skill": row["skill"], "slots": _loads(row["slots_json"], dict, {}),
                "calls": _loads(row["calls_json"], list, []), "asked_slot": row["asked_slot"], "question": row["question"],
                "ask": _loads(row["ask_json"], dict, {}), "attachments": _loads(row["attachments_json"], list, []),
                "draft_code": row["draft_code"], "pending": _loads(row["pending_json"], dict, None) if row["pending_json"] else None,
                "asks": row["asks"], "texts": texts if all(isinstance(t, str) for t in texts) else [],
                "created_at": row["created_at"], "updated_at": row["updated_at"], "expires_at": row["expires_at"]}

    @staticmethod
    def snapshot(req) -> dict:
        """What the interpreter is shown in continue mode (replaces the old ``recent``): our question, the earlier texts, and
        for a skill request the skill, the slots so far and the asked slot. Never ids of other owners, never attachments' bytes."""
        out = {}
        if req.get("question"):
            out["question"] = req["question"]
        if req["texts"]:
            out["earlier"] = list(req["texts"])
        if req.get("skill"):
            out["skill"], out["slots"] = req["skill"], dict(req["slots"])
            if req.get("asked_slot"):
                out["asked_slot"] = req["asked_slot"]
            if req.get("draft_code"):
                out["draft"] = req["draft_code"]
        return out

    # -- writing ----------------------------------------------------------------------------------------------
    def put(self, owner: str, provider_id: str, now: datetime, *, texts, request_id=None, state="open", skill=None,
            slots=None, calls=None, asked_slot=None, question=None, ask=None, attachments=None, pending=None,
            draft_code=None, asks=0, legacy=False, turns=None, per=MAX_OWNER_TEXT, total=MAX_TOTAL_TEXT) -> int:
        """Write the owner's request. With ``request_id`` that row is updated (its first-message time and 2 hour limit are
        kept); without, any live row of this owner is erased/closed first and a new one is made. ``legacy`` rows (the
        old question-and-texts requests) renew their 30 minutes on every write, as the old table did."""
        self.ensure(owner)
        kept = json.dumps(bound_texts(texts, turns=turns, per=per, total=total), ensure_ascii=False)
        fields = dict(provider_id=provider_id, state=state, skill=skill, slots_json=json.dumps(slots or {}, sort_keys=True),
                      calls_json=json.dumps(calls or [], sort_keys=True), texts_json=kept, asked_slot=asked_slot,
                      question=question, ask_json=json.dumps(ask, sort_keys=True) if ask else None,
                      attachments_json=json.dumps(list(attachments or [])[:MAX_ATTACHMENTS]),
                      pending_json=json.dumps(pending, sort_keys=True) if pending else None, draft_code=draft_code,
                      asks=asks, updated_at=_iso(now))
        if request_id is not None:
            row = self.db.execute("SELECT created_at FROM open_requests WHERE request_id = ? AND owner = ?",
                                  (request_id, owner)).fetchone()
            if row is not None:
                created = datetime.fromisoformat(row["created_at"])
                expires = _idle_deadline(now)
                if not legacy:
                    expires = min(expires, created + timedelta(minutes=MAX_MINUTES))
                fields["expires_at"] = _iso(expires)
                sets = ", ".join(f"{k} = ?" for k in fields)
                self.db.execute(f"UPDATE open_requests SET {sets} WHERE request_id = ?", (*fields.values(), request_id))
                return request_id
        self.close_live(owner, now, "superseded" if skill is not None and not legacy else "closed")
        fields.update(owner=owner, created_at=_iso(now), expires_at=_iso(_idle_deadline(now)))
        cur = self.db.execute(f"INSERT INTO open_requests({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
                              tuple(fields.values()))
        return cur.lastrowid

    def close_live(self, owner: str, now: datetime, state: str = "closed") -> None:
        """End the owner's live request. A legacy-kind row (no skill, nothing attached) is erased at once; any other keeps
        its row, in ``state``, for RETENTION_HOURS (so ``status`` can name it), then ``sweep`` erases it."""
        if not self.exists():
            return
        for row in self.db.execute("SELECT request_id FROM open_requests WHERE owner = ? AND state IN ('open','drafted')",
                                   (owner,)).fetchall():
            self.mark(row["request_id"], state, now)

    def mark(self, request_id: int, state: str, now: datetime, **fields) -> None:
        if state not in CLOSED and state not in LIVE:
            raise ValueError("unknown state")
        row = self.db.execute("SELECT skill, attachments_json FROM open_requests WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            return
        if state in CLOSED and row["skill"] is None and row["attachments_json"] == "[]":
            self.db.execute("DELETE FROM open_requests WHERE request_id = ?", (request_id,))
            return
        sets = {"state": state, "updated_at": _iso(now), **fields}
        if state in CLOSED:
            sets["closed_at"] = _iso(now)
        self.db.execute(f"UPDATE open_requests SET {', '.join(f'{k} = ?' for k in sets)} WHERE request_id = ?",
                        (*sets.values(), request_id))

    def close_drafted(self, owner: str, now: datetime) -> None:
        """The draft this request made was approved: finish the request (its texts follow the 24 hour rule). A request that is
        still asking something is untouched."""
        if self.exists():
            for row in self.db.execute("SELECT request_id FROM open_requests WHERE owner = ? AND state = 'drafted'", (owner,)).fetchall():
                self.mark(row["request_id"], "closed", now)

    def delete_live(self, owner: str) -> None:
        """Forget the owner's live request and its texts now (a draft or a new question took over; or ``no``)."""
        if self.exists():
            self.db.execute("DELETE FROM open_requests WHERE owner = ? AND state IN ('open','drafted')"
                            " AND skill IS NULL AND attachments_json = '[]'", (owner,))

    def sweep(self, now: datetime) -> None:
        """Expire live requests past their time (a legacy row is erased, any other one is marked ``expired``); erase every
        closed request more than RETENTION_HOURS old, text and all."""
        if not self.exists():
            return
        for row in self.db.execute("SELECT request_id, expires_at FROM open_requests WHERE state IN ('open','drafted')").fetchall():
            try:
                due = now > datetime.fromisoformat(row["expires_at"])
            except (TypeError, ValueError):
                due = True
            if due:
                self.mark(row["request_id"], "expired", now)
        cutoff = _iso(now - timedelta(hours=RETENTION_HOURS))
        self.db.execute("DELETE FROM open_requests WHERE state IN ('closed','expired','cancelled','superseded')"
                        " AND closed_at IS NOT NULL AND closed_at < ?", (cutoff,))

    # -- the owner's photo (spec 2.7) -------------------------------------------------------------------------
    def bind_attachment(self, owner: str, provider_id: str, sha: str, now: datetime, registry=None):
        """The stored original ``sha`` (its sha256 only, never bytes) joins the owner's request.

        Returns ``(how, request)``: ``"filled"`` when the live request's asked slot is an unfilled attachment slot (the photo
        fills it); ``"attached"`` when it joined a live request some other way; ``"opened"`` when there was none, so a
        request with no skill and the photo bound now exists (the caller routes the caption, or asks what the photo is for)."""
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            raise ValueError("not a sha256")
        req = self.get(owner, now)
        if req is not None and sha not in req["attachments"]:
            skill = registry.get(req["skill"]) if registry is not None and req["skill"] else None
            slot = next((s for s in getattr(skill, "slots", ()) if s.name == req["asked_slot"]), None)
            attachments = [*req["attachments"], sha]
            if slot is not None and slot.kind == "attachment" and slot.from_attachment and not req["slots"].get(slot.name):
                self.put(owner, provider_id, now, texts=req["texts"], request_id=req["request_id"], state=req["state"],
                         skill=req["skill"], slots={**req["slots"], slot.name: sha}, calls=req["calls"], asked_slot=None,
                         question=req["question"], ask=None, attachments=attachments, draft_code=req["draft_code"],
                         asks=req["asks"])
                return "filled", self.get(owner, now)
            self.put(owner, provider_id, now, texts=req["texts"], request_id=req["request_id"], state=req["state"],
                     skill=req["skill"], slots=req["slots"], calls=req["calls"], asked_slot=req["asked_slot"],
                     question=req["question"], ask=req["ask"], attachments=attachments, draft_code=req["draft_code"],
                     asks=req["asks"], pending=req["pending"])
            return "attached", self.get(owner, now)
        if req is not None:
            return "attached", req
        self.put(owner, provider_id, now, texts=[], attachments=[sha])
        return "opened", self.get(owner, now)

    # -- status -----------------------------------------------------------------------------------------------
    def status_lines(self, owner: str, now: datetime, registry=None) -> list:
        """One plain line for the owner's live skill request, plus one for a request replaced a moment ago. [] when none.
        A legacy question-and-texts request has no line: ``status`` reads as it always did."""
        out = []
        req = self.get(owner, now)
        if req is not None and (req["skill"] or req["attachments"]):
            skill = registry.get(req["skill"]) if registry is not None and req["skill"] else None
            label = getattr(skill, "label", None) or "a request"
            if req["state"] == "drafted":
                out.append(f"Open: {label}, waiting for your yes")
            elif req["asked_slot"]:
                out.append(f"Open: {label}, waiting for the {req['asked_slot'].replace('_', ' ')}")
            else:
                out.append(f"Open: {label}")
        row = self._row("owner = ? AND state = 'superseded' ORDER BY request_id DESC LIMIT 1", owner)
        if row is not None and row["skill"] and now <= datetime.fromisoformat(row["expires_at"]):
            skill = registry.get(row["skill"]) if registry is not None else None
            out.append(f"Replaced: {getattr(skill, 'label', None) or 'an earlier request'}")
        return out


# -- cheap answers and merge (pure) ---------------------------------------------------------------------------
def _tokens(text) -> list:
    return [w for w in nl_prep.tokens(text or "") if w not in FILLER]


def pick_candidate(text: str, ask: dict):
    """A choice from the options we listed: its number ("2", "the second one") or its name ("the big sur one"). The id of the
    one option the words name, else None (no match, or more than one). ``ask`` = {"ids": [...], "names": [...]}."""
    ids, names = ask.get("ids") or [], ask.get("names") or []
    if not ids or len(ids) != len(names):
        return None
    choice = re.fullmatch(r"\s*(?:the\s+)?([0-9]+|" + "|".join(ORDINALS) +
                          r")(?:\s+one)?(?:\s+please)?[.!?,;:]*\s*", (text or "").lower())
    if choice:
        word = choice.group(1)
        n = int(word) if word.isdigit() else ORDINALS[word]
        return ids[n - 1] if 1 <= n <= len(ids) else None
    wanted = _tokens(text)
    if not wanted:
        return None
    hits = [i for i, name in zip(ids, names) if all(any(w == t or nl_prep.stem(w) == nl_prep.stem(t) for t in _tokens(name)) for w in wanted)]
    return hits[0] if len(hits) == 1 else None


def cheap_answer(slot, text: str, *, ask=None, content=None, aliases=None, today=None):
    """Read a short answer to the asked ``slot`` without the model. ``(True, value)`` when the 12-word-or-fewer message is
    that kind of value; ``(False, None)`` otherwise (the model reads it). Only ref, shelf, availability, day and clock
    kinds are read this way; a ref is accepted only when it resolves to exactly one record."""
    from hass.skills import kinds
    if slot is None or slot.kind not in CHEAP_KINDS or not isinstance(text, str):
        return False, None
    words = text.split()
    if not 1 <= len(words) <= CHEAP_WORDS or EXTRA & set(re.findall(r"[a-z']+", text.lower())):
        return False, None  # long, or it says more than the answer ("... and call it ..."): the model reads it
    if slot.kind.endswith("_ref"):
        chosen = pick_candidate(text, ask or {})
        if chosen is not None:
            return True, chosen
        if content is None:
            return False, None
        resolver = kinds.RESOLVERS[slot.kind]
        res = resolver(content, text, aliases) if slot.kind in ("product_ref", "maker_ref") else resolver(content, text)
    elif slot.kind == "day":
        if today is None:
            return False, None
        res = kinds.day(text, today)
    elif slot.kind in ("shelf", "availability", "clock"):
        res = kinds.RESOLVERS[slot.kind](text)
    else:
        return False, None
    return (True, res.value) if res.status == "one" else (False, None)


def merge(slots: dict, new: dict, valid_names) -> dict:
    """Code decides what is kept: the earlier valid values stay, a new value for a known slot replaces its old one, anything
    else (an unknown name, None) is ignored."""
    out = dict(slots)
    for name, value in (new or {}).items():
        if name in valid_names and value is not None:
            out[name] = value
    return out
