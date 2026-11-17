"""HASS-RCV-1: the reply pull relay shared by the receiver host and the Mac forwarder (HASS-FWD-1).
Pure protocol plus one small store. The Mac pulls owner replies (the host never dials out): `pull` -> sealed `replies`,
`ack` -> sealed `acked`. Control envelopes are v2, keyed by control_key(secret), so a v1 inbound envelope never verifies
as a control one. Nothing here opens a socket, reads the environment or logs; error messages never carry a path or bytes.
"""
import base64, hmac, json, os, sqlite3, stat  # noqa: E401
from hashlib import sha256
from pathlib import Path

from hass import bridge, bridge_photos, media, memory

KEY_BYTES, MAX_KEY_FILE, MAX_TEXT, HAND_AFTER_S = 32, 128, 8192, 60
MAX_PNG, MAX_SHOTS, PNG_SIG, B64_MAX = 1572864, 2, b"\x89PNG\r\n\x1a\n", 2097152  # HASS-ATTACH-1
PHOTO_MAX = 8 * 1024 * 1024
CONTROL_KEYS = {"v", "ts", "nonce", "body", "mac"}


class KeyFileError(Exception):
    """code: missing | not-regular | symlink | owner | mode | size | format. The message is the code only."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class RelayRefused(Exception): """The reply may not go to the Mac (other chat, text too long, too many pictures)."""


G_PENDING_MAX = 2  # replies for G's own chat that may wait at once, so a Mac that does not carry that chat can never crowd out Mike's


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


def _shots(v) -> bool:
    return (type(v) is list and 1 <= len(v) <= MAX_SHOTS
            and [s.get("idx") if type(s) is dict and type(s.get("idx")) is int else None for s in v] == list(range(len(v)))  # exact ints: False/0.0 == 0 in Python but cannot form a picture request
            and all(set(s) == {"idx", "sha256", "size"} and type(s["sha256"]) is str and bridge.MAC_RE.fullmatch(s["sha256"])
                    and type(s["size"]) is int and 1 <= s["size"] <= MAX_PNG for s in v))


def _item(i) -> bool:
    return (type(i) is dict and set(i) in ({"id", "chat", "text", "pictures"}, {"id", "chat", "text", "pictures", "shots"})
            and type(i["id"]) is int
            and type(i["chat"]) is str and type(i["text"]) is str and len(i["text"]) <= MAX_TEXT
            and type(i["pictures"]) is int and 0 <= i["pictures"] <= 10 and ("shots" not in i or _shots(i["shots"]))
            and not bridge.SURROGATE_RE.search(i["chat"] + i["text"]))


def _b64(s) -> bool:
    try: return type(s) is str and len(s) <= B64_MAX and len(base64.b64decode(s, validate=True)) <= MAX_PNG
    except ValueError: return False


def _ints(v, lo, hi) -> bool:
    return type(v) is list and lo <= len(v) <= hi and all(type(x) is int and x > 0 for x in v)


def _photo_index(b):
    return bridge_photos._valid_guid(b["guid"]) and type(b["idx"]) is int and 0 <= b["idx"] < media.MAX_PHOTOS_PER_MESSAGE


def _photo_count(b):
    return _photo_index(b) and type(b["count"]) is int and b["idx"] < b["count"] <= media.MAX_PHOTOS_PER_MESSAGE


def _photo_data(b):
    if not (_photo_count(b) and type(b["sha256"]) is str and bridge.MAC_RE.fullmatch(b["sha256"])
            and type(b["b64"]) is str and len(b["b64"]) <= 4 * ((PHOTO_MAX + 2) // 3)): return False
    try: data = base64.b64decode(b["b64"], validate=True)
    except ValueError: return False
    return 1 <= len(data) <= PHOTO_MAX and sha256(data).hexdigest() == b["sha256"]


SHAPES = {  # body op -> [(keys, validator)]; picture has request and answer forms
    "photo": [({"op", "guid", "idx", "count", "sha256", "b64"}, _photo_data)],
    "photo-refused": [({"op", "guid", "idx", "count", "code"}, lambda b: _photo_count(b)
                       and type(b["code"]) is str and b["code"] in ("too-large", "unsupported-type", "fetch-failed"))],
    "photo-ok": [({"op", "guid", "idx"}, _photo_index)],
    "pull": [({"op", "max"}, lambda b: type(b["max"]) is int and 1 <= b["max"] <= 5)],
    "ack": [({"op", "ids"}, lambda b: _ints(b["ids"], 1, 20))],
    "replies": [({"op", "items"}, lambda b: type(b["items"]) is list and len(b["items"]) <= 5
                 and all(map(_item, b["items"])))],
    "acked": [({"op", "ids"}, lambda b: _ints(b["ids"], 0, 20))],
    "picture": [({"op", "id", "idx"}, lambda b: type(b["id"]) is int and type(b["idx"]) is int and b["idx"] in (0, 1)),
                ({"op", "id", "idx", "sha256", "b64"}, lambda b: type(b["id"]) is int and type(b["idx"]) is int
                 and b["idx"] in (0, 1) and type(b["sha256"]) is str and bool(bridge.MAC_RE.fullmatch(b["sha256"]))
                 and _b64(b["b64"]))],
    "gone": [({"op", "id", "idx"}, lambda b: type(b["id"]) is int and type(b["idx"]) is int and b["idx"] in (0, 1))],
    # HASS-FAST-1: the Mac asks if the 👀 may be sent; the answer is true when changes are paused OR the host cannot tell
    "state": [({"op"}, lambda b: True), ({"op", "paused"}, lambda b: type(b["paused"]) is bool)],
}


def _body_ok(body) -> bool:
    if type(body) is not dict or type(body.get("op")) is not str: return False
    shapes = SHAPES.get(body["op"])
    return shapes is not None and any(set(body) == keys and check(body) for keys, check in shapes)


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
            "CREATE TABLE IF NOT EXISTS meta(name TEXT PRIMARY KEY, value TEXT);"
            "CREATE TABLE IF NOT EXISTS picture(relay_id INTEGER NOT NULL, idx INTEGER NOT NULL, sha256 TEXT NOT NULL,"
            " size INTEGER NOT NULL, data BLOB, PRIMARY KEY(relay_id, idx));")

    def add(self, chat, text, pictures, now, shots=()) -> int:
        """`shots`: PNG bytes (already checked) stored with the row, in one transaction."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rid = self.db.execute("INSERT INTO relay(chat, text, pictures, created_at) VALUES (?, ?, ?, ?)",
                                  (chat, text, pictures, int(now))).lastrowid
            self.db.executemany("INSERT INTO picture VALUES (?, ?, ?, ?, ?)",
                                [(rid, n, sha256(d).hexdigest(), len(d), d) for n, d in enumerate(shots)])
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")
        return rid

    def unacked(self, chat) -> int:
        return self.db.execute("SELECT COUNT(*) FROM relay WHERE chat = ? AND acked_at IS NULL", (chat,)).fetchone()[0]

    def picture(self, rid, idx):
        """(sha256 hex, bytes) of a stored shot whose row is not yet acknowledged, else None."""
        row = self.db.execute("SELECT p.sha256, p.data FROM picture p JOIN relay r ON r.id = p.relay_id WHERE p.relay_id = ?"
                              " AND p.idx = ? AND r.acked_at IS NULL AND p.data IS NOT NULL", (rid, idx)).fetchone()
        return tuple(row) if row else None

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
        items = [{"id": r[0], "chat": r[1], "text": r[2], "pictures": r[3]} for r in rows]
        for item in items:
            shots = self.db.execute("SELECT idx, sha256, size FROM picture WHERE relay_id = ? ORDER BY idx", (item["id"],)).fetchall()
            if shots: item["shots"] = [{"idx": a, "sha256": b, "size": c} for a, b, c in shots]
        return items

    def ack(self, ids, now) -> int:
        """Idempotent; unknown ids are ignored. Returns how many rows this call newly acknowledged."""
        n = 0
        for i in ids:
            n += self.db.execute("UPDATE relay SET acked_at = ? WHERE id = ? AND acked_at IS NULL", (int(now), i)).rowcount
            self.db.execute("UPDATE picture SET data = NULL WHERE relay_id = ?", (i,))
        self.db.execute("DELETE FROM picture WHERE relay_id IN (SELECT id FROM relay WHERE acked_at < ?)", (int(now) - 30 * 86400,))
        return n

    def status(self) -> dict:
        waiting = self.db.execute("SELECT COUNT(*) FROM relay WHERE acked_at IS NULL").fetchone()[0]
        total = self.db.execute("SELECT COUNT(*) FROM relay").fetchone()[0]
        return {"waiting": waiting, "total": total}


def read_shot(path, base):
    """PNG bytes of a screenshot, or None. The file must lie inside `base`, with no symlink in `base` or below it, be a
    regular file of 1..MAX_PNG bytes and start with the PNG signature. The path is never stored or sent."""
    try:
        p, b = Path(os.path.abspath(os.fspath(path))), Path(os.path.abspath(base))
        if b not in p.parents: return None
        for part in (b, *reversed([q for q in p.parents if b in q.parents]), p):
            if not (stat.S_ISDIR if part != p else stat.S_ISREG)(os.lstat(part).st_mode): return None
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            st = os.fstat(fd)
            data = os.read(fd, MAX_PNG + 1) if stat.S_ISREG(st.st_mode) and 1 <= st.st_size <= MAX_PNG else b""
        finally: os.close(fd)
    except (OSError, TypeError, ValueError):
        return None
    return data if 1 <= len(data) <= MAX_PNG and data.startswith(PNG_SIG) else None


class RelaySender:
    """Outbox adapter: send() stores the reply for the Mac to pull. Only the owner chat (and G's own chat, text only, when configured); no path is ever stored.
    With `shots_dir` (host `pictures` true) up to 2 screenshots from it travel as pictures; the rest are counted."""
    def __init__(self, store, owner_chat, clock, shots_dir=None, g_chat=None, picture_chats=None):
        """`owner_chat`: one chat id, or (HASS-OWNERS-2) a tuple of owner chats, each an owner's own one-to-one chat; the first is the main
        one (the host puts the configured ownerChat first). `picture_chats`: the owner chats that may get pictures (default: every
        owner chat; the Mac forwarder carries pictures to each of its owner chats). A picture for any other chat is dropped here and
        its text goes on alone. G's chat never gets one."""
        chats = tuple(owner_chat) if isinstance(owner_chat, (tuple, list)) else (owner_chat,)
        self.store, self.owner_chat, self.other_owner_chats, self.clock, self.shots_dir = store, chats[0], chats[1:], clock, shots_dir
        self.picture_chats = chats if picture_chats is None else tuple(picture_chats)
        self.g_chat = g_chat if isinstance(g_chat, str) and g_chat and g_chat not in chats else None  # G's one chat, text only

    @property
    def owner_chats(self) -> tuple:
        return (self.owner_chat, *self.other_owner_chats)

    def send(self, chat, text, attachments=()):
        """Stores the reply for the Mac to pull; returns the relay id (HASS-FAST-1: the stage log joins reply to message by it)."""
        if self.g_chat is not None and chat == self.g_chat and (attachments or self.store.unacked(chat) >= G_PENDING_MAX):
            raise RelayRefused("reply refused")  # G's chat: text only, and never more than G_PENDING_MAX waiting for the Mac
        if chat in self.other_owner_chats and chat not in self.picture_chats: attachments = ()  # HASS-OWNERS-2: only when a caller narrows picture_chats
        if (chat not in self.owner_chats and chat != self.g_chat) or len(text) > MAX_TEXT or len(attachments) > 10 or bridge.SURROGATE_RE.search(text):
            raise RelayRefused("reply refused")
        shots = []
        if self.shots_dir is not None:
            for path in attachments[:MAX_SHOTS]:
                data = read_shot(path, self.shots_dir)
                if data is not None: shots.append(data)
        return self.store.add(chat, text, len(attachments) - len(shots), self.clock(), shots)
