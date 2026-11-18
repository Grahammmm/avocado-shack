"""Bounded till jobs in the conversation transaction; journal intents are never resent.

The outbox row and job completion commit together. This is outbox idempotence,
not a guarantee about a transport dying after delivery but before its receipt.
"""
import fcntl
from types import SimpleNamespace

from hass import memory

SCHEMA = """CREATE TABLE IF NOT EXISTS till_jobs(
 provider_id TEXT PRIMARY KEY, identity TEXT NOT NULL, code TEXT NOT NULL,
 sender TEXT NOT NULL, chat TEXT NOT NULL, received_at TEXT NOT NULL,
 shelf INTEGER NOT NULL, allowed INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0,
 UNIQUE(identity, code))"""
MAX_JOBS = 256
HELD = "I couldn't finish your approved till change. I won't send it again; please check that item on the till."
PENDING = "That till change already has an approval being processed. I won't send it twice."
SAVED = "Your approved till change was saved and read back. I won't send it again."
FAILED = "Your approved till change did not finish. Please check that item on the till before asking for a new change."


def save(c, msg, job, allowed):
    """Called inside the very transaction that records the inbound provider id."""
    if job is None:
        return
    code, shelf = job if isinstance(job, tuple) else (job, False)
    if any(len(v) > cap for v, cap in ((msg.provider_id, 512), (msg.chat, 512), (c._asker, 320), (msg.received_at, 64))):
        raise ValueError("till approval identity too long")
    c.db.execute(SCHEMA)
    c.db.execute("DELETE FROM till_jobs WHERE done=1 AND provider_id IN (SELECT provider_id FROM till_jobs WHERE done=1 ORDER BY rowid LIMIT ?)",
                 (max(0, c.db.execute("SELECT count(*) FROM till_jobs").fetchone()[0] - MAX_JOBS + 1),))
    if c.db.execute("SELECT count(*) FROM till_jobs").fetchone()[0] >= MAX_JOBS:
        raise RuntimeError("till approval queue full; message not acknowledged")
    identity = c.till.engine.journal.identity
    # Completed jobs no longer own the code: a fresh message must get its own
    # outcome. Journal reconciliation still forbids replaying an intent.
    c.db.execute("DELETE FROM till_jobs WHERE identity=? AND code=? AND done=1", (identity, code))
    inserted = c.db.execute("INSERT OR IGNORE INTO till_jobs(provider_id,identity,code,sender,chat,received_at,shelf,allowed) VALUES(?,?,?,?,?,?,?,?)",
                            (msg.provider_id, identity, code, c._asker, msg.chat, msg.received_at, int(shelf), int(allowed)))
    if not inserted.rowcount:
        # Another approval is already pending. Do not turn this message into
        # a second write, but do not silently acknowledge it either.
        c._reply(PENDING, long_ok=True)


def finish(c, msg):
    """Same transaction as the outcome outbox row (also the future bundle hook)."""
    c.db.execute("UPDATE till_jobs SET done=1 WHERE provider_id=?", (msg.provider_id,))


def recover(c):
    """On desk attachment/start and after every message, including duplicates.

    A process lock spans journal reconciliation, execution and outcome enqueue;
    no conversation write lock is held while Clover is called.
    """
    if not c.db.execute("SELECT 1 FROM sqlite_master WHERE name='till_jobs'").fetchone():
        return
    with open(memory.private_db(c.sdir, "till-approvals.lock"), "r+b") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        for row in c.db.execute("SELECT * FROM till_jobs WHERE done=0 ORDER BY rowid").fetchall():
            msg = SimpleNamespace(**{k: row[k] for k in ("provider_id", "sender", "chat", "received_at")},
                                  text="", from_me=False, kind="new", attachments=0)
            old = c._to, c._asker, c._answering, c.outbox.msg_id
            c._to, c._asker, c._answering, c.outbox.msg_id = msg.chat, msg.sender, msg.received_at, msg.provider_id
            try:
                engine = getattr(c.till, "engine", None)
                text, site = HELD, False
                if engine is not None and engine.journal.identity == row["identity"] and c._is_owner(msg):
                    status, site = engine.reconcile(row["code"], sender=msg.sender, chat=msg.chat)
                    if status == "draft" and row["allowed"] and not c._paused():
                        c._till_apply(msg, (row["code"], bool(row["shelf"])), True)
                        continue
                    text = SAVED if status == "applied" else FAILED if status in ("failed", "dropped") else HELD
                with c._tx():
                    c._reply(text, long_ok=True)
                    if site: c._reply("Please check the website too; I haven't tried that part again.")
                    finish(c, msg)
            finally:
                c._to, c._asker, c._answering, c.outbox.msg_id = old
