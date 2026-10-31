"""Hass durable inbound queue (H16): every inbound message is stored before any processing and drained once, in order.

`<state>/inbox.sqlite3` (0600) records the approved start point on first open; a message received before it is kept as
`history` (id and time only) and never becomes a command. `drain()` hands each pending message to `Conversation.handle`
in `(received_at, provider_id)` order and only then marks it done, so a crash in between re-delivers the message and
`Conversation` answers `duplicate` without a second write. Payloads are erased once a message is done. A payload that
cannot be decoded into an `Inbound` is marked done as `unreadable` and skipped; its content is not kept. Fixtures only.
"""
import contextlib, json, os, sqlite3, sys  # noqa: E401
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor as editor_mod  # noqa: E402
from hass.conversation import Inbound  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inbound(provider_id TEXT PRIMARY KEY, received_at TEXT NOT NULL, payload TEXT,
  state TEXT NOT NULL CHECK (state IN ('pending', 'done', 'history')), disposition TEXT, enqueued_at TEXT NOT NULL,
  done_at TEXT);
CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY, seen_at TEXT NOT NULL);
"""
NONCE_KEEP_S = 86400  # >= 2 x bridge.MAX_SKEW; a pruned nonce's envelope is already stale


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
        path = sdir / "inbox.sqlite3"
        os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
        os.chmod(path, 0o600)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.executescript(SCHEMA)
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
            if wanted is not None and wanted != row["value"]:
                raise ValueError(f"start point already recorded as {row['value']}")
            return row["value"]

    @contextlib.contextmanager
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

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
        return self.db.execute("SELECT provider_id, payload FROM inbound WHERE state = 'pending'"
                               " ORDER BY received_at, provider_id LIMIT 1").fetchone()

    def _mark(self, provider_id: str, disposition: str) -> None:
        with self._tx():
            self.db.execute("UPDATE inbound SET state = 'done', disposition = ?, done_at = ?, payload = NULL"
                            " WHERE provider_id = ? AND state = 'pending'",
                            (disposition, _iso(self.clock()), provider_id))

    def drain(self, conversation) -> list:
        """Hand each pending message to conversation.handle in order, marking it done afterwards. An exception from
        handle (or the mark) propagates and leaves that message and every later one pending for the next drain."""
        handled = []
        while (row := self._next()) is not None:
            pid = row["provider_id"]
            try:
                msg = Inbound(**json.loads(row["payload"]))
                if msg.provider_id != pid: raise ValueError("payload names another message")
            except (TypeError, ValueError):  # a poison payload must not block every later message
                self._mark(pid, "unreadable")
                handled.append((pid, "unreadable"))
                continue
            disposition = conversation.handle(msg)
            self._mark(pid, disposition)
            handled.append((pid, disposition))
        return handled

    def state(self, provider_id: str):
        row = self.db.execute("SELECT state FROM inbound WHERE provider_id = ?", (provider_id,)).fetchone()
        return None if row is None else row["state"]

    def seen(self) -> Nonces:
        return Nonces(self)
