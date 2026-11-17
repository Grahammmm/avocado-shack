"""Private, one-use photo arrivals in the host directory; never a host-to-Mac fetch."""
import base64
import contextlib
import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from hass import bridge_photos, media, memory, relay


class PhotoRefused(media.Refused):
    def __init__(self, code, position):
        if code == "fetch-failed":
            from hass.conversation import FETCH_FAILED
            Exception.__init__(self, code)
            self.code, self.reply = code, FETCH_FAILED
        else:
            super().__init__(code)
        self.position = position


class RelayPhotos:
    def __init__(self, host_dir, clock=lambda: datetime.now(timezone.utc)):
        self.path, self.clock = memory.private_db(Path(host_dir), "photos.sqlite3"), clock
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS photo_in(guid TEXT, idx INTEGER, count INTEGER, sha256 TEXT,"
                       " data BLOB, code TEXT, received_at INTEGER, PRIMARY KEY(guid, idx))")

    @contextlib.contextmanager
    def _db(self):
        with contextlib.closing(sqlite3.connect(self.path, timeout=30)) as db:
            with db: yield db

    def _expire(self, db, now):
        db.execute("DELETE FROM photo_in WHERE received_at <= ?", (now - 86400,))

    def put(self, body, now):
        if not relay._body_ok(body) or body["op"] not in ("photo", "photo-refused"): raise ValueError("photo")
        data = base64.b64decode(body["b64"], validate=True) if body["op"] == "photo" else None
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, now)
            old = db.execute("SELECT count FROM photo_in WHERE guid = ?", (body["guid"],)).fetchall()
            if any(row[0] != body["count"] for row in old): raise ValueError("photo count")
            try:
                db.execute("INSERT INTO photo_in VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (body["guid"], body["idx"], body["count"], body.get("sha256"), data, body.get("code"), now))
            except sqlite3.IntegrityError: raise ValueError("photo duplicate") from None

    def fetch(self, guid, n):
        return self._fetch(guid, n, consume=True)

    def fetch_for_inbox(self, guid, n):
        """Keep the arrival until the durable inbox marks this message done."""
        return self._fetch(guid, n, consume=False)

    def reconcile(self, inbox):
        """Remove completed arrivals, including a crash after marking the inbox."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, int(self.clock().timestamp()))
            guids = db.execute("SELECT DISTINCT guid FROM photo_in").fetchall()
            db.executemany("DELETE FROM photo_in WHERE guid = ?",
                           ((guid,) for (guid,) in guids if inbox.state(guid) == "done"))

    def _fetch(self, guid, n, *, consume):
        if not bridge_photos._valid_guid(guid) or type(n) is not int or not 1 <= n <= media.MAX_PHOTOS_PER_MESSAGE:
            raise ValueError("photo request")
        refused, out = None, []
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, int(self.clock().timestamp()))
            rows = db.execute("SELECT idx, count, sha256, data, code FROM photo_in WHERE guid = ? ORDER BY idx", (guid,)).fetchall()
            refused = next((PhotoRefused(code, idx + 1) for idx, count, digest, data, code in rows if code), None)
            if refused is None:
                pending = len(rows) != n or any(idx != i or count != n or not isinstance(data, bytes)
                        or not 1 <= len(data) <= relay.PHOTO_MAX or sha256(data).hexdigest() != digest
                        for i, (idx, count, digest, data, code) in enumerate(rows))
                if not pending: out = [row[3] for row in rows]
            if consume and (refused is not None or out): db.execute("DELETE FROM photo_in WHERE guid = ?", (guid,))
        if refused is not None: raise refused
        if not out: raise ValueError("photo pending")
        return out
