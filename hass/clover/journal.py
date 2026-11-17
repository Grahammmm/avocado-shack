"""Private, merchant-bound write journal; flock serializes offer/apply/recovery across processes."""
import fcntl
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from hass.clover.cache import _private_dir, _private_file

class Journal:
    def __init__(self, state, config):
        self.path = Path(state) / "clover" / "journal.sqlite3"
        self.identity = json.dumps([config.environment, config.merchant_id])

    @contextmanager
    def locked(self):
        _private_dir(self.path.parent, True)
        lock = self.path.with_suffix(".lock")
        _private_file(lock, True)
        with open(lock, "r+b") as guard:
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
