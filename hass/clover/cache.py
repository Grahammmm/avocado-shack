"""HASS-CLOVER-2: the PRIVATE till cache: `<state>/clover/cache.sqlite3` (folder 0700, file 0600, owned by the service user).

`hass/clover/cli.py sync` is the only writer; the conversation and `hass/health.py` only read (sqlite mode=ro). The cache holds the
inventory fields Hass answers from (name, SKU or code, price in cents, category ids, hidden, stock count) and when they were read. It never
holds a token, a header, a response body, or any sales, order, customer, payment or employee data, and it is never in git or on the site
(the state folder is neither). One sync replaces every row in ONE transaction, so a reader sees the old pull or the new one, never half.

Meta rows: `asOf` (UTC ISO of the last good pull), `lastAttempt`, `lastResult` ("ok" or one fixed word), `failures` (in a row) and
`nextAttempt` (the backoff: a failing till is asked less often, up to every BACKOFF_MAX_MINUTES).
"""
import json
import os
import sqlite3
import stat
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from hass.clover.mapper import CloverItem
from hass.clover.reads import Snapshot

DIRNAME, FILENAME = "clover", "cache.sqlite3"
BACKOFF_MINUTES, BACKOFF_MAX_MINUTES = 15, 240
RESULTS = ("ok", "token", "refused-key", "unreachable", "rate-limited", "clover-error", "bad-data")
SCHEMA = """
CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL, code TEXT NOT NULL, price_cents INTEGER,
  price_type TEXT NOT NULL, unit_name TEXT NOT NULL, category_ids TEXT NOT NULL, categories TEXT NOT NULL, hidden INTEGER NOT NULL,
  available INTEGER NOT NULL, stock TEXT, stock_modified INTEGER, modified_time INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
COLUMNS = ("id", "name", "sku", "code", "price_cents", "price_type", "unit_name", "category_ids", "categories", "hidden", "available", "stock",
           "stock_modified", "modified_time")


class CacheUnsafe(Exception):
    """The cache folder or file is not private to the service user (a link, another owner, a wider mode). Nothing was read or written."""


def path_for(state):
    return Path(state) / DIRNAME / FILENAME


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(text):
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else None


def _private_dir(folder, create):
    try:
        st = os.lstat(folder)
    except FileNotFoundError:
        if not create:
            return False
        os.mkdir(folder, 0o700)
        st = os.lstat(folder)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise CacheUnsafe("folder")
    return True


def _private_file(path, create):
    """The cache file exists (or is created 0600) as a regular file of this user with no group/other bits."""
    flags = os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | (os.O_CREAT if create else 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileNotFoundError:
        return False
    except OSError:
        raise CacheUnsafe("file") from None
    try:
        st = os.fstat(fd)
    finally:
        os.close(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise CacheUnsafe("file")
    return True


def _open_write(state):
    path = path_for(state)
    _private_dir(path.parent, create=True)
    _private_file(path, create=True)
    db = sqlite3.connect(path, isolation_level=None, timeout=10)
    db.executescript(SCHEMA)
    return db


def _open_read(state):
    """A read-only connection, or None when there is no cache yet. Raises CacheUnsafe for a cache that is not private."""
    path = path_for(state)
    if not _private_dir(path.parent, create=False):
        return None
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise CacheUnsafe("file")
    return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=5)


def _meta(db):
    try:
        return dict(db.execute("SELECT key, value FROM meta"))
    except sqlite3.Error:
        return {}


def _set_meta(db, values):
    db.executemany("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   [(k, str(v)) for k, v in values.items()])


def write_items(state, rows, now):
    """Replace every cached item with `rows` (dicts with COLUMNS) and mark the pull good, in one transaction."""
    with closing(_open_write(state)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("DELETE FROM items")
            db.executemany(f"INSERT INTO items({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                           [tuple(r[c] for c in COLUMNS) for r in rows])
            _set_meta(db, {"asOf": _iso(now), "lastAttempt": _iso(now), "lastResult": "ok", "failures": 0, "nextAttempt": "",
                           "itemCount": len(rows)})
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise


def backoff_minutes(failures, retry_after_seconds=None):
    wait = min(BACKOFF_MAX_MINUTES, BACKOFF_MINUTES * 2 ** max(0, failures - 1))
    if retry_after_seconds:
        wait = max(wait, -(-int(retry_after_seconds) // 60))
    return wait


def record_failure(state, word, now, retry_after_seconds=None):
    """Note a failed pull (one fixed word) and when to try next. The items and `asOf` are kept, so answers say how old they are."""
    if word not in RESULTS or word == "ok":
        word = "clover-error"
    with closing(_open_write(state)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            failures = int(_meta(db).get("failures", "0") or 0) + 1
            nxt = now + timedelta(minutes=backoff_minutes(failures, retry_after_seconds))
            _set_meta(db, {"lastAttempt": _iso(now), "lastResult": word, "failures": failures, "nextAttempt": _iso(nxt)})
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return failures


def facts(state):
    """{asOf, lastAttempt, lastResult, failures, nextAttempt, itemCount} as plain values, or None when there is no cache yet.
    For `cli status`, health and the backoff; no item data. Raises CacheUnsafe for a cache that is not private."""
    conn = _open_read(state)
    if conn is None:
        return None
    with closing(conn) as db:
        meta = _meta(db)
    return {"asOf": meta.get("asOf") or None, "lastAttempt": meta.get("lastAttempt") or None, "lastResult": meta.get("lastResult") or None,
            "failures": int(meta.get("failures") or 0), "nextAttempt": meta.get("nextAttempt") or None,
            "itemCount": int(meta.get("itemCount") or 0)}


def _item(row):
    r = dict(zip(COLUMNS, row))
    stock = None if r["stock"] is None else Decimal(r["stock"])
    return CloverItem(id=r["id"], name=r["name"], sku=r["sku"], code=r["code"], price_cents=r["price_cents"], price_type=r["price_type"],
                      unit_name=r["unit_name"], categories=tuple(json.loads(r["categories"])), tags=(), stock=stock,
                      stock_modified=r["stock_modified"], hidden=bool(r["hidden"]), available=bool(r["available"]),
                      modified_time=r["modified_time"])


def read(state):
    """(snapshot or None, reachable): the last good pull as a reads.Snapshot (None when there never was one) and whether the LAST
    attempt worked (True when nothing was tried yet). A cache that is not private or not readable reads as (None, False)."""
    try:
        conn = _open_read(state)
    except CacheUnsafe:
        return None, False
    if conn is None:
        return None, True
    with closing(conn) as db:
        meta = _meta(db)
        reachable = meta.get("lastResult", "ok") == "ok"
        as_of = _parse_iso(meta.get("asOf"))
        if as_of is None:
            return None, reachable
        try:
            items = tuple(_item(r) for r in db.execute(f"SELECT {', '.join(COLUMNS)} FROM items ORDER BY name, id"))
        except (sqlite3.Error, ValueError, ArithmeticError):
            return None, False
    return Snapshot(items, as_of), reachable
