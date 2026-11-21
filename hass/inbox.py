"""Hass durable inbound queue (H16): every inbound message is stored before any processing and drained once, in order.

`<state>/inbox.sqlite3` (0600) records the approved start point on first open; a message received before it is kept as
`history` (id and time only) and never becomes a command. `drain()` hands each pending message to `Conversation.handle`
in `(received_at, provider_id)` order and only then marks it done, so a crash in between re-delivers the message and
`Conversation` answers `duplicate` without a second write. Payloads are erased once a message is done. A payload that
cannot be decoded into an `Inbound`, or whose fields have the wrong types (RF0220-10), is marked done as `unreadable`
and skipped; its content is not kept. Fixtures only.
NB-AV-11: a photo that cannot be fetched (`AttachmentPending`) stays pending with a try count and holds every later
message until its next try (30 s, then 2 min); the 3rd try is handled as the last one and replies once.
RF1710-3: `python3 hass/inbox.py status --state DIR` prints one JSON line of counts (sqlite mode=ro; no ids or text;
clock_behind when a pending row is stamped after now).
"""
import argparse, contextlib, json, os, re, sqlite3, stat, sys  # noqa: E401
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor as editor_mod  # noqa: E402
from hass.conversation import AttachmentPending, Inbound  # noqa: E402
from hass.memory import private_db  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inbound(provider_id TEXT PRIMARY KEY, received_at TEXT NOT NULL, payload TEXT,
  state TEXT NOT NULL CHECK (state IN ('pending', 'done', 'history')), disposition TEXT, enqueued_at TEXT NOT NULL,
  done_at TEXT);
CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY, seen_at TEXT NOT NULL);
"""
NONCE_KEEP_S = 86400  # >= 2 x bridge.MAX_SKEW; a pruned nonce's envelope is already stale
MAX_TRIES, BACKOFF_S = 3, (30, 120)  # NB-AV-11: photo fetch tries; wait after the 1st and 2nd failure


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """Fixed-width UTC form, so the stored text sorts in time order whatever offset the message carried."""
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def parse_aware(value, what="received_at") -> datetime:
    """A timezone-aware ISO-8601 time; anything else (empty, no zone, not a date, not a string) is a ValueError."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{what} must be a timezone-aware ISO-8601 time")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{what} must be a timezone-aware ISO-8601 time") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{what} must be a timezone-aware ISO-8601 time")
    return dt


_STR_FIELDS = ("provider_id", "chat", "sender", "text", "kind", "received_at")


def _decode_payload(payload, provider_id: str) -> Inbound:
    """RF0220-10: a stored payload as an Inbound with exactly typed fields; anything else is a ValueError (or the
    TypeError/ValueError/RecursionError of decoding), which drain treats as unreadable. The wording is never shown."""
    msg = Inbound(**json.loads(payload))
    if msg.provider_id != provider_id: raise ValueError("payload names another message")
    if any(type(getattr(msg, f)) is not str for f in _STR_FIELDS) or type(msg.from_me) is not bool \
            or type(msg.attachments) is not int or msg.attachments < 0:
        raise ValueError("invalid queued payload")
    return msg


class Nonces:
    """Persistent replay set for bridge.unseal(..., seen=inbox.seen()): `nonce in seen` and `seen.add(nonce)`."""

    def __init__(self, inbox):
        self._inbox = inbox

    def __contains__(self, nonce) -> bool:
        return self._inbox.db.execute("SELECT 1 FROM nonces WHERE nonce = ?", (str(nonce),)).fetchone() is not None

    def add(self, nonce) -> None:
        now = self._inbox.clock()
        cut = _iso(now - timedelta(seconds=NONCE_KEEP_S))  # a future-dated row (clock moved back) is kept
        with self._inbox._tx():
            self._inbox.db.execute("DELETE FROM nonces WHERE seen_at < ?", (cut,))
            self._inbox.db.execute("INSERT OR IGNORE INTO nonces(nonce, seen_at) VALUES (?, ?)",
                                   (str(nonce), _iso(now)))


class Inbox:
    def __init__(self, state_dir, start_at=None, clock=_utc_now):
        """The first open records `start_at` (timezone-aware ISO-8601); later opens reuse it and refuse a different
        value. This module never changes a recorded start point."""
        sdir = editor_mod.open_state(state_dir)
        self.clock = clock
        path = private_db(sdir, "inbox.sqlite3")  # RF1520-11: a link, directory or FIFO is UnsafeState, never followed
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.executescript(SCHEMA)
            columns = {r["name"] for r in self.db.execute("PRAGMA table_info(inbound)")}  # an older H16 inbox
            for column, kind in (("tries", "INTEGER NOT NULL DEFAULT 0"), ("next_try_at", "TEXT")):
                if column not in columns: self.db.execute(f"ALTER TABLE inbound ADD COLUMN {column} {kind}")
            self.start_at = datetime.fromisoformat(self._start_point(start_at))
        except BaseException:
            self.db.close()
            raise

    def _start_point(self, start_at) -> str:
        wanted = None if start_at is None else _iso(parse_aware(start_at, "start_at"))
        with self._tx():
            row = self.db.execute("SELECT value FROM meta WHERE name = 'start_at'").fetchone()
            if row is None:
                if wanted is None: raise ValueError("start point required")
                self.db.execute("INSERT INTO meta(name, value) VALUES ('start_at', ?)", (wanted,))
                return wanted
            try: parse_aware(row["value"], "start_at")  # RF0440-12: a damaged recorded cutoff is refused, never echoed
            except ValueError: raise ValueError("recorded start point is unreadable") from None
            if wanted is not None and wanted != row["value"]:
                raise ValueError(f"start point already recorded as {row['value']}")
            return row["value"]

    @contextlib.contextmanager
    def _tx(self):
        """One write transaction. RF0824-10: inside a caller's open transaction it is a SAVEPOINT instead, so a failed
        inner operation undoes only itself and a successful one commits nothing until the outermost transaction does
        (the receiver wraps the nonce record and the enqueue in one). A failed COMMIT is rolled back, never left open."""
        nested = self.db.in_transaction
        self.db.execute("SAVEPOINT inbox_op" if nested else "BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("RELEASE inbox_op" if nested else "COMMIT")
        except BaseException:
            if self.db.in_transaction:
                for sql in ("ROLLBACK TO inbox_op", "RELEASE inbox_op") if nested else ("ROLLBACK",): self.db.execute(sql)
            raise

    def close(self) -> None:
        self.db.close()

    def enqueue(self, msg: Inbound) -> str:
        """Store one message before any processing: `queued`, `duplicate` (id already stored, nothing changes) or
        `history` (received before the start point; only id and time are kept)."""
        received = parse_aware(msg.received_at)
        with self._tx():
            if self.db.execute("SELECT 1 FROM inbound WHERE provider_id = ?", (msg.provider_id,)).fetchone():
                return "duplicate"
            if received < self.start_at:
                state, payload = "history", None
            else:
                state, payload = "pending", json.dumps(asdict(msg), sort_keys=True)
            self.db.execute("INSERT INTO inbound(provider_id, received_at, payload, state, enqueued_at)"
                            " VALUES (?, ?, ?, ?, ?)", (msg.provider_id, _iso(received), payload, state,
                                                        _iso(self.clock())))
        return "queued" if state == "pending" else "history"

    def _next(self):
        return self.db.execute("SELECT provider_id, payload, tries, next_try_at, enqueued_at FROM inbound WHERE state = 'pending'"
                               " ORDER BY received_at, provider_id LIMIT 1").fetchone()

    def _retry(self, provider_id: str, tries: int) -> None:
        wait = BACKOFF_S[min(tries, len(BACKOFF_S)) - 1]
        with self._tx():
            self.db.execute("UPDATE inbound SET tries = ?, next_try_at = ? WHERE provider_id = ? AND state = 'pending'",
                            (tries, _iso(self.clock() + timedelta(seconds=wait)), provider_id))

    def _mark(self, provider_id: str, disposition: str) -> None:
        with self._tx():
            self.db.execute("UPDATE inbound SET state = 'done', disposition = ?, done_at = ?, payload = NULL"
                            " WHERE provider_id = ? AND state = 'pending'",
                            (disposition, _iso(self.clock()), provider_id))

    def drain(self, conversation) -> list:
        """Hand each pending message to conversation.handle in order, marking it done afterwards. An exception from
        handle (or the mark) propagates and leaves that message and every later one pending for the next drain;
        AttachmentPending counts a try and stops the drain until that message's next try time."""
        handled = []
        while (row := self._next()) is not None:
            if row["next_try_at"] is not None and row["next_try_at"] > _iso(self.clock()): break  # order is kept
            try:
                msg = _decode_payload(row["payload"], row["provider_id"])
            except (TypeError, ValueError, RecursionError):  # a poison payload must not block every later message
                msg = None
            try:  # last_try only on the last try, so a plain handle(msg) stand-in still works
                photos = getattr(getattr(conversation, "conversation", conversation), "photos", None)
                lifetime = getattr(photos, "retry_seconds", 0) if msg is not None and msg.attachments else 0
                if not isinstance(lifetime, (int, float)) or isinstance(lifetime, bool):
                    lifetime = 0  # Mock/fake photo sources retain the legacy attempt limit.
                last = row["tries"] + 1 >= MAX_TRIES
                if lifetime:
                    try:
                        enqueued_at = parse_aware(row["enqueued_at"], "enqueued_at")
                    except ValueError:
                        pass  # An unreadable timestamp leaves the attempt limit in effect.
                    else:
                        last = self.clock() >= enqueued_at + timedelta(seconds=lifetime)
                disposition = "unreadable" if msg is None else \
                    conversation.handle(msg, last_try=True) if last else conversation.handle(msg)
            except AttachmentPending:
                self._retry(row["provider_id"], row["tries"] + 1)
                break
            self._mark(row["provider_id"], disposition)
            handled.append((row["provider_id"], disposition))
        return handled

    def waiting(self) -> int:
        """Pending messages whose photo fetch has failed at least once (read-only; NB-AV-12 status)."""
        return self.db.execute("SELECT COUNT(*) FROM inbound WHERE state = 'pending' AND tries > 0").fetchone()[0]

    def state(self, provider_id: str):
        row = self.db.execute("SELECT state FROM inbound WHERE provider_id = ?", (provider_id,)).fetchone()
        return None if row is None else row["state"]

    def forwarded_at(self, provider_id: str):
        """HASS-SEC-2 (L5): when the message reached this inbox (its enqueue time, within the envelope's 300 s clock window of
        the forwarder's send), or None when it is not here or the time cannot be read."""
        row = self.db.execute("SELECT enqueued_at FROM inbound WHERE provider_id = ?", (provider_id,)).fetchone()
        try: return None if row is None else parse_aware(row["enqueued_at"], "enqueued_at")
        except ValueError: return None

    def seen(self) -> Nonces:
        return Nonces(self)


def _zoned(value) -> bool:  # only a timezone-aware ISO-8601 string; a BLOB, number or garbage cell is not
    try: return isinstance(parse_aware(value, "start_at"), datetime)
    except (ValueError, TypeError): return False


def status(state_dir, now=None):
    """(report, exit code) for `<state_dir>/inbox.sqlite3` opened mode=ro: never creates it, never shows an id or text."""
    sdir = Path(state_dir)
    if sdir.is_symlink() or not sdir.is_dir(): return {"result": "unsafe", "reason": "missing or a symlink"}, 2
    try: mode = os.lstat(path := sdir / "inbox.sqlite3").st_mode  # lstat: a planted (even dangling) link is seen
    except FileNotFoundError: return {"result": "ok", "inbox": "none"}, 0
    if not stat.S_ISREG(mode): return {"result": "unsafe", "reason": "inbox file is a link or not a regular file"}, 2
    try:
        with contextlib.closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("BEGIN")  # one deferred read snapshot: counts, dispositions, ages and nonces agree; close() ends it
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok": return {"result": "unreadable"}, 1
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            rows = lambda table, sql: db.execute(sql).fetchall() if table in tables else []  # noqa: E731
            counts = dict(rows("inbound", "SELECT state, COUNT(*) FROM inbound GROUP BY state"))
            start = (rows("meta", "SELECT value FROM meta WHERE name = 'start_at'") or [(None,)])[0][0]
            out = {"result": "ok", "start_at": None if start is None else start if _zoned(start) else "unreadable",
                   **{k: counts.get(k, 0) for k in ("pending", "done", "history")}}
            if "disposition" in {r[1] for r in db.execute("PRAGMA table_info(inbound)")}:  # an older schema lacks it
                out["dispositions"] = disp = {}
                for (code,) in db.execute("SELECT disposition FROM inbound WHERE state = 'done'"):
                    ok = isinstance(code, str) and re.fullmatch(r"[a-z0-9-]{1,32}", code)
                    disp[key] = disp.get(key := "none" if code is None else code if ok else "other", 0) + 1
            try:
                times = [parse_aware(t, "enqueued_at") for (t,) in
                         rows("inbound", "SELECT enqueued_at FROM inbound WHERE state = 'pending'")]
                now_ = now or _utc_now()
                future, past = [t for t in times if t > now_], [t for t in times if t <= now_]
                out["oldest_pending_minutes"] = int((now_ - min(past)).total_seconds() // 60) if past else (0 if future else None)
                if future: out["clock_behind"] = True
            except (ValueError, TypeError):
                out["oldest_pending_minutes"] = "unreadable"
            out["nonces"] = (rows("nonces", "SELECT COUNT(*) FROM nonces") or [(0,)])[0][0]
            return out, 0
    except sqlite3.DatabaseError:
        return {"result": "unreadable"}, 1


def main(argv=None, now=None) -> int:
    ap = argparse.ArgumentParser(prog="inbox.py", description="H16 inbound queue (read-only status).")
    ap.add_subparsers(dest="cmd", required=True).add_parser("status").add_argument("--state", required=True)
    report, code = status(ap.parse_args(argv).state, now)
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
