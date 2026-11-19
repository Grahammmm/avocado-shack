"""Private, merchant-bound write journal; flock serializes offer/apply/recovery across processes."""
import fcntl
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

from hass.clover.cache import CacheUnsafe, _private_dir, _private_file

class Journal:
    def __init__(self, state, config):
        self.path = Path(state) / "clover" / "journal.sqlite3"
        self.identity = json.dumps([config.environment, config.merchant_id])

    @contextmanager
    def locked(self):
        _private_dir(self.path.parent, True)
        lock = self.path.with_suffix(".lock")
        _private_file(lock, True)
        try:
            fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
        except OSError:
            raise CacheUnsafe("file") from None
        with os.fdopen(fd, "r+b") as guard:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise CacheUnsafe("file")
            fcntl.flock(guard, fcntl.LOCK_EX)
            _private_file(self.path, True)
            db = sqlite3.connect(self.path, isolation_level=None)
            db.row_factory = sqlite3.Row
            try:
                db.executescript("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);"
                                 "CREATE TABLE IF NOT EXISTS changes(code TEXT PRIMARY KEY, draft TEXT, sender TEXT, chat TEXT,"
                                 "expires REAL, status TEXT, day TEXT, result TEXT);")
                db.execute("INSERT OR IGNORE INTO meta VALUES('identity',?)", (self.identity,))
                if db.execute("SELECT v FROM meta WHERE k='identity'").fetchone()[0] != self.identity:
                    raise ValueError("journal identity")
                yield db
            finally:
                db.close()

    @staticmethod
    def settle(db, code, status, result=None):
        db.execute("UPDATE changes SET status=?,result=? WHERE code=?", (status, json.dumps(result), code))
