"""Hass owner memory store (H15): approved owner facts and preferences, kept apart from raw chat.

Rows live in a `memory` table inside the private state dir's conversation.sqlite3 (created on first use, so the H20
state backup covers it unchanged). Every row records its source and dates. A fact needs an explicit approved source:
chat history, model output or repetition is never proof. correct() supersedes in one transaction; forget() blanks the
text of every row of the key and keeps only the audit dates. Store only, plus a read-only history command: no chat
commands, interpreter or network.
"""
import argparse, contextlib, json, os, re, sqlite3, sys  # noqa: E401
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor as editor_mod  # noqa: E402

TABLE = """CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY, key TEXT NOT NULL, value TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('fact','preference')), source TEXT NOT NULL, approved_change TEXT,
  created_at TEXT NOT NULL, superseded_at TEXT, forgotten_at TEXT)"""
ACTIVE = "superseded_at IS NULL AND forgotten_at IS NULL"
KEY_RE = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}")
SOURCE_RE = re.compile(r"(owner-approved|owner-stated|operator):(.+)", re.DOTALL)
KINDS = ("fact", "preference")
SOURCE_KIND = re.compile(r"(owner-approved|owner-stated|operator):")  # history shows only this part of a source
AUDIT = ("key", "kind", "created_at", "superseded_at", "forgotten_at")
MAX_VALUE = 500
COLUMNS = ("key", "value", "kind", "source", "approved_change", "created_at")


def _clean(text) -> bool:
    """A non-empty str without control characters (below U+0020, or U+007F)."""
    return isinstance(text, str) and bool(text) and not any(ord(c) < 0x20 or ord(c) == 0x7F for c in text)


def _check_key(key) -> None:
    if not isinstance(key, str) or not KEY_RE.fullmatch(key): raise ValueError("invalid key")


def _check_value(value) -> None:
    if not _clean(value) or len(value) > MAX_VALUE: raise ValueError(f"value must be 1-{MAX_VALUE} plain characters")


def _check_source(source) -> None:
    """Only owner-approved:<change_id>, owner-stated:<provider_id> or operator:<note>; anything else is unverified."""
    if not _clean(source) or len(source) > MAX_VALUE or not SOURCE_RE.fullmatch(source):
        raise ValueError("unverified source")


class Memory:
    def __init__(self, state_dir, clock):
        """state_dir is validated by editor.open_state (UnsafeState if shared/foreign); clock() returns a datetime."""
        sdir = editor_mod.open_state(state_dir)
        path = sdir / "conversation.sqlite3"
        os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
        os.chmod(path, 0o600)
        self.clock = clock
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete = ON")  # forgotten text is zeroed in the file, not left in free space
        self.db.execute(TABLE)

    @classmethod
    def on_connection(cls, db, clock):
        """Share an open connection (the H05 Conversation's, sqlite3.Row rows): no second writer on the file."""
        self = cls.__new__(cls)
        self.db, self.clock = db, clock
        for sql in ("PRAGMA secure_delete = ON", TABLE): db.execute(sql)
        return self

    def close(self) -> None:
        self.db.close()

    def _now(self) -> str:
        return self.clock().isoformat()

    @contextlib.contextmanager
    def _tx(self):
        nested = self.db.in_transaction  # inside the caller's transaction a failure undoes only this op's savepoint
        self.db.execute("SAVEPOINT memory_op" if nested else "BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            for sql in ("ROLLBACK TO memory_op", "RELEASE memory_op") if nested else ("ROLLBACK",): self.db.execute(sql)
            raise
        self.db.execute("RELEASE memory_op" if nested else "COMMIT")

    def _active(self, key):
        return self.db.execute(f"SELECT * FROM memory WHERE key = ? AND {ACTIVE}", (key,)).fetchone()

    def _insert(self, key, value, kind, source, approved_change) -> None:
        self.db.execute("INSERT INTO memory(key, value, kind, source, approved_change, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)", (key, value, kind, source, approved_change, self._now()))

    def remember(self, key, value, kind, source, approved_change=None) -> None:
        _check_key(key)
        _check_value(value)
        if kind not in KINDS: raise ValueError("kind must be fact or preference")
        _check_source(source)
        if approved_change is not None and (not _clean(approved_change) or len(approved_change) > MAX_VALUE):
            raise ValueError("invalid approved_change")
        with self._tx():
            if self._active(key) is not None: raise ValueError("use correct")
            self._insert(key, value, kind, source, approved_change)

    def correct(self, key, value, source) -> None:
        """Supersede the active row with a new value (same kind) in one transaction; KeyError if none is active."""
        _check_key(key)
        _check_value(value)
        _check_source(source)
        with self._tx():
            old = self._active(key)
            if old is None: raise KeyError(key)
            self.db.execute("UPDATE memory SET superseded_at = ? WHERE id = ?", (self._now(), old["id"]))
            self._insert(key, value, old["kind"], source, None)

    def forget(self, key) -> None:
        """Mark the active row forgotten and blank the value of every row of the key; the dates stay."""
        _check_key(key)
        with self._tx():
            old = self._active(key)
            if old is None: raise KeyError(key)
            self.db.execute("UPDATE memory SET forgotten_at = ? WHERE id = ?", (self._now(), old["id"]))
            self.db.execute("UPDATE memory SET value = '' WHERE key = ?", (key,))

    def get(self, key):
        _check_key(key)
        row = self._active(key)
        return None if row is None else row["value"]

    def list(self) -> list:
        rows = self.db.execute(f"SELECT * FROM memory WHERE {ACTIVE} ORDER BY key")
        return [{name: row[name] for name in COLUMNS} for row in rows]


def history(state_dir, key=None, values=False) -> dict:
    path, rows, out = Path(state_dir) / "conversation.sqlite3", [], []
    if path.exists():  # mode=ro: never created or written here; sqlite3.DatabaseError if unreadable
        with contextlib.closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone():
                rows = db.execute(f"SELECT {', '.join(AUDIT)}, {ACTIVE}, source, value FROM memory WHERE ? IS NULL "
                                  "OR key = ? ORDER BY created_at, id", (key, key)).fetchall()
    for *audit, active, source, value in rows:  # never the source detail, approved_change or an inactive value
        out.append({**dict(zip(AUDIT, audit)), "source_kind": m[1] if (m := SOURCE_KIND.match(str(source))) else "other",
                    "active": bool(active), **({"value": value} if values and active else {})})
    return {"result": "ok", "rows": out, "keys": len({r["key"] for r in out}), "active": sum(r["active"] for r in out),
            **{f: sum(r[f + "_at"] is not None for r in out) for f in ("superseded", "forgotten")}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/memory.py", description="Read-only owner memory history (H15).")
    hist = parser.add_subparsers(dest="cmd", required=True).add_parser("history")
    hist.add_argument("--state", required=True)
    hist.add_argument("--key")
    hist.add_argument("--values", action="store_true", help="print the value of active rows")
    args = parser.parse_args(argv)
    doc, code = {"result": "unsafe"}, 2
    if not Path(args.state).is_symlink() and Path(args.state).is_dir():
        try:
            if args.key is not None: _check_key(args.key)
            doc, code = history(args.state, args.key, args.values), 0
        except ValueError: doc, code = {"result": "usage", "problem": "invalid key"}, 2
        except sqlite3.DatabaseError: doc, code = {"result": "unreadable"}, 1
    print(json.dumps(doc, ensure_ascii=False))
    return code


if __name__ == "__main__": sys.exit(main())
