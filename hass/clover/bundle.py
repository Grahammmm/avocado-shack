"""Private, restartable till/site saga, NOT a cross-system transaction. No chat wiring.

Draft the website before approval to freeze its baseline; only LiveEditor applies it.
Notifications are durable pending owner/operator receipts, for the later outbox seam.
"""
import fcntl
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from hass.clover import drafts as d
from hass.clover.cache import _private_dir, _private_file
from hass.clover.chat import SITE_NOT_YET
from hass.clover.mapper import parse_item
from hass.conversation import sender_key

STATES = ("proposed", "till-intent", "till-applied", "till-uncertain", "link-written",
          "site-intent", "site-live", "done", "split", "failed", "undone")
LinkWriter = Callable[[str, str, str], None]


@dataclass(frozen=True)
class Bundle:
    code: str
    site_ops: tuple[dict, ...]
    till: d.Draft | None
    link: dict | None
    lines: tuple[str, ...]
    bundle_hash: str


def _hash(code, ops, till, link):
    return hashlib.sha256(json.dumps([code, ops, till.draft_hash if till else None, link],
                                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class BundleJournal:
    def __init__(self, state):
        self.path = Path(state) / "clover" / "bundles.sqlite3"
        _private_dir(self.path.parent, True)
        _private_file(self.path, True)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS bundles(code TEXT PRIMARY KEY, row TEXT NOT NULL)")

    @contextmanager
    def db(self):
        _private_file(self.path, False)
        with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            yield db

    @contextmanager
    def locked(self):
        lock = self.path.with_suffix(".lock")
        _private_file(lock, True)
        with lock.open("r+b") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX)
            yield

    def put(self, bundle, *, sender, chat, expires):
        row = dict(bundle=asdict(bundle), sender=sender, chat=chat, expires=expires, state="proposed",
                   till="pending" if bundle.till else "omitted", site="pending", notifications={})
        with self.db() as db:
            db.execute("INSERT INTO bundles VALUES(?,?)", (bundle.code, json.dumps(row)))

    def advance(self, code, state, **facts):
        if state not in STATES: raise ValueError("bundle state")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = json.loads(db.execute("SELECT row FROM bundles WHERE code=?", (code,)).fetchone()[0])
            row.update(facts, state=state)
            db.execute("UPDATE bundles SET row=? WHERE code=?", (json.dumps(row), code))
            db.commit()

    def get(self, code):
        with self.db() as db:
            row = db.execute("SELECT row FROM bundles WHERE code=?", (code,)).fetchone()
        return json.loads(row[0]) if row else None

    def open_rows(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT row FROM bundles ORDER BY code")
                    if json.loads(r[0])["state"] not in ("done", "failed", "undone")]


def _owner(sender, chat, engine, site):
    cfg = site.settings
    key = sender_key(sender)
    allowed = ((sender, chat) in engine.owners) if engine is not None else (
        key in cfg.get("chatKeys", {}).get(chat, cfg.get("ownerKeys", ()))
        and chat in (cfg.get("ownerChats") or (cfg.get("ownerChat"),)))
    if not allowed or ";+;" in chat: raise d.DraftRefused("Owner private chat only.")


def _paused(engine, site):
    if site.stopped() or (getattr(site.conv, "_paused", lambda: False)()): return True
    if engine is not None:
        with engine.journal.locked() as db:
            return bool(db.execute("SELECT 1 FROM meta WHERE k='paused'").fetchone())
    return False


def _out(journal, code, state, text, **facts):
    journal.advance(code, state, reply=text, notifications={who: {"text": text, "state": "pending"}
                    for who in ("owner", "operator")}, **facts)
    return state, text


def propose(*, site_ops, till_draft, link, sender, chat, journal, engine, site):
    with journal.locked():
        _owner(sender, chat, engine, site)
        if _paused(engine, site): raise d.DraftRefused("Changes are paused.")
        till, code = till_draft, secrets.token_hex(4)
        if till:
            try:
                if engine is None: raise d.DraftRefused("Till unavailable.")
                code, _ = engine.offer(till, sender=sender, chat=chat)
            except d.DraftRefused:
                till = None
        ops, link = tuple(site_ops), link if till else None
        lines = ("On the website: " + ", ".join(o["op"] for o in ops), "The website shows no prices",
                 "On the till: " + "\n".join(till.lines) if till else "I can't add it to the till yet")
        bundle = Bundle(code, ops, till, link, lines, _hash(code, ops, till, link))
        journal.put(bundle, sender=sender, chat=chat, expires=(engine.clock() if engine else time.time()) + 600)
        prepared = site.prepare(list(ops))
        if prepared.get("result") != "ok":
            _out(journal, code, "failed", "The website draft was refused.")
            raise d.DraftRefused("The website draft was refused.")
        draft = prepared["draft"]
        journal.advance(code, "proposed", change_id=draft["change_id"], draft_hash=draft["draft_hash"])
        return code, "\n".join((*lines, f"Reply yes {code} to apply both prepared halves."))


def _result(engine, code):
    with engine.journal.locked() as db:
        row = db.execute("SELECT result FROM changes WHERE code=? AND status='applied'", (code,)).fetchone()
    return json.loads(row[0]) if row and row[0] else None


def apply(code, *, sender, chat, journal, engine, site, link_writer, now):
    with journal.locked():
        _owner(sender, chat, engine, site)
        row = journal.get(code)
        if not row or (sender, chat) != (row["sender"], row["chat"]): raise d.DraftRefused("Not your bundle.")
        if _paused(engine, site): raise d.DraftRefused("Changes are paused.")
        if row["state"] == "split" and row.get("link_state") == "written" and row["till"] in ("applied", "omitted"):
            return _site_apply(journal, code, row, site, chat)
        if row["state"] != "proposed": return row["state"], row.get("reply", "Reconcile before continuing.")
        if now >= row["expires"] or "change_id" not in row: raise d.DraftRefused("Expired or incomplete bundle.")
        b = row["bundle"]
        till = d.Draft(**b["till"]) if b["till"] else None
        if b["bundle_hash"] != _hash(code, b["site_ops"], till, b["link"]): raise d.DraftRefused("Changed bundle.")
        if till:
            journal.advance(code, "till-intent", till="intent")
            try:
                status = engine.handle("yes " + code, sender=sender, chat=chat)
            except d.DraftRefused:
                status = "failed"
            if status != "applied":
                return _out(journal, code, "till-uncertain" if status == "uncertain" else "failed",
                            "Check the till; I will not send this again.", till=status)
            result = _result(engine, code)
            if not result: return _out(journal, code, "till-uncertain", "Check the till; read-back is missing.")
            journal.advance(code, "till-applied", till="applied", clover_id=result["result_item_id"])
        try:
            if b["link"]:
                link_writer(b["link"]["product_id"], journal.get(code)["clover_id"], b["link"]["sku"])
            journal.advance(code, "link-written", link_state="written")
        except Exception:
            return _out(journal, code, "split", SITE_NOT_YET + " Say 'retry'.")
        return _site_apply(journal, code, row, site, chat)


def _site_apply(journal, code, row, site, chat):
    journal.advance(code, "site-intent", site="intent")
    try:
        site.apply(row["change_id"], row["draft_hash"], chat)
        return _finish(journal, code, site)
    except Exception:
        return _out(journal, code, "split", "Website not confirmed; check both halves. Say 'retry'.")


def _finish(journal, code, site):
    row = journal.get(code)
    if not site.went_live(row["change_id"]):
        return _out(journal, code, "split", SITE_NOT_YET + " Say 'retry'.", site="not-confirmed")
    journal.advance(code, "site-live", site="live")
    text = "The website is live; " + ("the till was read back." if row["till"] == "applied" else "the till was not changed.")
    if row.get("undo_of"): journal.advance(row["undo_of"], "undone")
    return _out(journal, code, "done", text)


def reconcile(*, journal, engine, site, now):
    outcomes = []
    with journal.locked():
        for row in journal.open_rows():
            code, state = row["bundle"]["code"], row["state"]
            if state == "proposed": continue
            if state in ("till-intent", "till-uncertain"):
                status, _ = engine.reconcile(code, sender=row["sender"], chat=row["chat"])
                result = _result(engine, code) if status == "applied" else None
                state = "split" if result else "till-uncertain"
                outcomes.append(_out(journal, code, state, "Check both halves; no till write was repeated.",
                                     till="applied" if result else "uncertain"))
            elif state in ("site-intent", "site-live", "split") and row.get("change_id"):
                outcomes.append(_finish(journal, code, site))
            else:
                outcomes.append(_out(journal, code, "split", SITE_NOT_YET + " Say 'retry'."))
    return outcomes


def undo(code, *, sender, chat, journal, engine, site):
    _owner(sender, chat, engine, site)
    row = journal.get(code)
    if not row or row["state"] != "done" or (sender, chat) != (row["sender"], row["chat"]):
        raise d.DraftRefused("No completed bundle to undo.")
    till = None
    if row["bundle"]["till"]:
        entry = _result(engine, code)
        try: till = d.build_undo(entry, parse_item(engine._client().get_item(entry["result_item_id"])), engine.config)
        except d.DraftRefused: pass  # A newer till value stays; the conflict-checked site inverse can still go.
    new, text = propose(site_ops=[{"op": "history.revert", "args": {"changeId": row["change_id"]}}],
                        till_draft=till, link=None, sender=sender, chat=chat, journal=journal, engine=engine, site=site)
    journal.advance(new, "proposed", undo_of=code)
    return new, text
