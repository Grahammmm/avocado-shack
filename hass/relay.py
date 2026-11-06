"""HASS-RCV-1: the reply pull relay shared by the receiver host and the Mac forwarder (HASS-FWD-1).
Pure protocol plus one small store. The Mac pulls owner replies (the host never dials out): `pull` -> sealed `replies`,
`ack` -> sealed `acked`. Control envelopes are v2, keyed by control_key(secret), so a v1 inbound envelope never verifies
as a control one. Nothing here opens a socket, reads the environment or logs; error messages never carry a path or bytes.
"""
import hmac, json, os, sqlite3, stat  # noqa: E401
from hashlib import sha256

from hass import bridge, memory

KEY_BYTES, MAX_KEY_FILE, MAX_TEXT, HAND_AFTER_S = 32, 128, 8192, 60
CONTROL_KEYS = {"v", "ts", "nonce", "body", "mac"}


class KeyFileError(Exception):
    """code: missing | not-regular | symlink | owner | mode | size | format. The message is the code only."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class RelayRefused(Exception): """The reply may not go to the Mac (other chat, text too long, too many pictures)."""


def read_key(path) -> bytes:
    """D5: a regular file (not a link) owned by this user, 0600-or-tighter, <= 128 bytes: 64 hex chars and an optional
    newline. Returns the 32 key bytes."""
    try:
        st = os.lstat(path)
    except OSError:
        raise KeyFileError("missing") from None
    if stat.S_ISLNK(st.st_mode): raise KeyFileError("symlink")
    if not stat.S_ISREG(st.st_mode): raise KeyFileError("not-regular")
    if st.st_uid != os.getuid(): raise KeyFileError("owner")
    if st.st_mode & 0o177: raise KeyFileError("mode")
    if st.st_size > MAX_KEY_FILE: raise KeyFileError("size")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try: data = os.read(fd, MAX_KEY_FILE + 1)
        finally: os.close(fd)
    except OSError:
        raise KeyFileError("missing") from None
    if len(data) > MAX_KEY_FILE: raise KeyFileError("size")
    text = data[:-1] if data.endswith(b"\n") else data
    if len(text) != 2 * KEY_BYTES or not all(c in b"0123456789abcdefABCDEF" for c in text): raise KeyFileError("format")
    return bytes.fromhex(text.decode("ascii"))


def control_key(secret) -> bytes:
    return hmac.new(bridge._check_key(secret), b"hass relay v2", sha256).digest()


def _item(i) -> bool:
    return (type(i) is dict and set(i) == {"id", "chat", "text", "pictures"} and type(i["id"]) is int
            and type(i["chat"]) is str and type(i["text"]) is str and len(i["text"]) <= MAX_TEXT
            and type(i["pictures"]) is int and 0 <= i["pictures"] <= 10
            and not bridge.SURROGATE_RE.search(i["chat"] + i["text"]))


def _ints(v, lo, hi) -> bool:
    return type(v) is list and lo <= len(v) <= hi and all(type(x) is int and x > 0 for x in v)


SHAPES = {  # body type -> (keys, validator of the whole body)
    "pull": ({"type", "max"}, lambda b: type(b["max"]) is int and 1 <= b["max"] <= 5),
    "ack": ({"type", "ids"}, lambda b: _ints(b["ids"], 1, 20)),
    "replies": ({"type", "items"}, lambda b: type(b["items"]) is list and len(b["items"]) <= 5
                and all(map(_item, b["items"]))),
    "acked": ({"type", "count"}, lambda b: type(b["count"]) is int and 0 <= b["count"] <= 20),
}


def _body_ok(body) -> bool:
    shape = SHAPES.get(body.get("type")) if type(body) is dict else None
    return shape is not None and set(body) == shape[0] and shape[1](body)


def seal_control(body, secret, *, nonce, now) -> dict:
    if not _body_ok(body): raise ValueError("control body is not in a known form")
    if not isinstance(nonce, str) or not bridge.NONCE_RE.fullmatch(nonce): raise ValueError("nonce must be hex >= 16 bytes")
    env = {"v": 2, "ts": bridge._seconds(now), "nonce": nonce, "body": body}
    env["mac"] = bridge._mac(control_key(secret), env)
    return env


def unseal_control(env, secret, *, now, seen) -> dict:
    """The body of a valid v2 envelope; adds its nonce to `seen`. Raises bridge.EnvelopeError (shape|version|mac|stale|replay)."""
    key = control_key(secret)
    if not isinstance(env, dict) or set(env) != CONTROL_KEYS: raise bridge.EnvelopeError("shape")
    if type(env["v"]) is not int or env["v"] != 2: raise bridge.EnvelopeError("version")
    ts, nonce, mac, body = env["ts"], env["nonce"], env["mac"], env["body"]
    if not (type(ts) is int and isinstance(nonce, str) and bridge.NONCE_RE.fullmatch(nonce) and isinstance(mac, str)
            and bridge.MAC_RE.fullmatch(mac) and _body_ok(body)):
        raise bridge.EnvelopeError("shape")
    if not hmac.compare_digest(bridge._mac(key, env), mac): raise bridge.EnvelopeError("mac")
    if abs(bridge._seconds(now) - ts) > bridge.MAX_SKEW: raise bridge.EnvelopeError("stale")
    if nonce in seen: raise bridge.EnvelopeError("replay")
    seen.add(nonce)
    return body


class RelayStore:
    """relay.sqlite3 in the host dir (0600): replies waiting for the Mac to pull and acknowledge them."""
    def __init__(self, host_dir):
        self.db = sqlite3.connect(memory.private_db(host_dir, "relay.sqlite3"), isolation_level=None, timeout=30)
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS relay(id INTEGER PRIMARY KEY, chat TEXT NOT NULL, text TEXT NOT NULL,"
            " pictures INTEGER NOT NULL, created_at INTEGER NOT NULL, handed_at INTEGER, acked_at INTEGER);"
            "CREATE TABLE IF NOT EXISTS meta(name TEXT PRIMARY KEY, value TEXT);")

    def add(self, chat, text, pictures, now) -> int:
        return self.db.execute("INSERT INTO relay(chat, text, pictures, created_at) VALUES (?, ?, ?, ?)",
                               (chat, text, pictures, int(now))).lastrowid

    def pull(self, n, now) -> list:
        """Unacked rows never handed, or handed more than 60 s ago, oldest first; marks them handed."""
        now = int(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rows = self.db.execute("SELECT id, chat, text, pictures FROM relay WHERE acked_at IS NULL AND"
                                   " (handed_at IS NULL OR ? - handed_at > ?) ORDER BY id LIMIT ?",
                                   (now, HAND_AFTER_S, n)).fetchall()
            self.db.executemany("UPDATE relay SET handed_at = ? WHERE id = ?", [(now, r[0]) for r in rows])
            self.db.execute("INSERT OR REPLACE INTO meta(name, value) VALUES ('last_pull_at', ?)", (str(now),))
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")
        return [{"id": r[0], "chat": r[1], "text": r[2], "pictures": r[3]} for r in rows]

    def ack(self, ids, now) -> int:
        """Idempotent; unknown ids are ignored. Returns how many rows this call newly acknowledged."""
        n = 0
        for i in ids:
            n += self.db.execute("UPDATE relay SET acked_at = ? WHERE id = ? AND acked_at IS NULL", (int(now), i)).rowcount
        return n

    def status(self) -> dict:
        waiting = self.db.execute("SELECT COUNT(*) FROM relay WHERE acked_at IS NULL").fetchone()[0]
        total = self.db.execute("SELECT COUNT(*) FROM relay").fetchone()[0]
        return {"waiting": waiting, "total": total}


class RelaySender:
    """Outbox adapter: send() stores the reply for the Mac to pull. Only the owner chat; no path is ever stored."""
    def __init__(self, store, owner_chat, clock):
        self.store, self.owner_chat, self.clock = store, owner_chat, clock

    def send(self, chat, text, attachments=()):
        if chat != self.owner_chat or len(text) > MAX_TEXT or len(attachments) > 10 or bridge.SURROGATE_RE.search(text):
            raise RelayRefused("reply refused")
        self.store.add(chat, text, len(attachments), self.clock())
