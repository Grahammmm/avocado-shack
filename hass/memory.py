"""Hass owner memory store (H15): approved owner facts and preferences, kept apart from raw chat.

Rows live in a `memory` table inside the private state dir's conversation.sqlite3 (created on first use, so the H20
state backup covers it unchanged). Every row records its source and dates. A fact needs an explicit approved source:
chat history, model output or repetition is never proof. correct() supersedes in one transaction; forget() blanks the
text of every row of the key and keeps only the audit dates. Store only, plus a read-only history command: no chat
commands, interpreter or network. An owner-approved:<change id> source must name a change whose record in this state
dir is applied and not undone (RF1650-2); anything else is the same "unverified source". correct() with the exact value already active is refused (RF1650-4).
"""
import argparse, contextlib, errno, json, os, re, sqlite3, stat, sys  # noqa: E401
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
HIDDEN_CHARS = re.compile("[\x00-\x1f\x7f-\x9f\u200b\u200e\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")


def _clean(text) -> bool:
    """A non-empty str without HIDDEN_CHARS: C0/C1 controls and U+007F, U+200B, U+200E/F, U+2028/9, U+202A-E,
    U+2060-4, U+2066-9 and U+FEFF. U+200C/U+200D stay allowed (emoji ZWJ sequences, Persian/Indic scripts)."""
    return isinstance(text, str) and bool(text) and not HIDDEN_CHARS.search(text)


def _check_key(key) -> None:
    if not isinstance(key, str) or not KEY_RE.fullmatch(key): raise ValueError("invalid key")


def _check_value(value) -> None:
    # str.strip() only decides "blank" (RF0200-9); the stored text is never trimmed or normalised.
    if not _clean(value) or len(value) > MAX_VALUE or not value.strip():
        raise ValueError(f"value must be 1-{MAX_VALUE} plain characters")


def _check_source(source) -> None:
    """Only owner-approved:<change_id>, owner-stated:<provider_id> or operator:<note>; anything else is unverified.
    The detail after the prefix must have non-whitespace content (RF0200-9)."""
    match = SOURCE_RE.fullmatch(source) if _clean(source) and len(source) <= MAX_VALUE else None
    if match is None or not match[2].strip(): raise ValueError("unverified source")


def private_db(sdir, name) -> Path:
    path = sdir / name
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENXIO, errno.EISDIR): raise editor_mod.UnsafeState(
            f"{name} must be a regular file, not a link") from exc
        raise
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise editor_mod.UnsafeState(f"{name} must be a regular file, not a link")
        os.fchmod(fd, 0o600)
    finally: os.close(fd)
    # SQLite reopens by path; the intervening window is accepted for the owned 0700 state dir.
    return path
class Memory:
    def __init__(self, state_dir, clock):
        """state_dir is validated by editor.open_state (UnsafeState if shared/foreign); clock() returns a datetime."""
        self.sdir = sdir = editor_mod.open_state(state_dir)
        path = private_db(sdir, "conversation.sqlite3")
        self.clock = clock
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete = ON")  # forgotten text is zeroed in the file, not left in free space
        self.db.execute(TABLE)

    @classmethod
    def on_connection(cls, db, clock, state_dir=None):
        """Share an open connection (the H05 Conversation's, sqlite3.Row rows): no second writer on the file.
        Without state_dir no change record can be read, so an owner-approved source is refused."""
        self = cls.__new__(cls)
        self.db, self.clock = db, clock
        self.sdir = None if state_dir is None else editor_mod.open_state(state_dir)
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

    def _approved_problem(self, change_id):
        """None if change_id names an applied, not-undone change record in this state dir, else why not."""
        if not editor_mod.CHANGE_ID_RE.fullmatch(change_id): return "malformed id"  # before any path is built
        if self.sdir is None: return "no state dir"
        path = self.sdir / "changes" / f"{change_id}.json"
        try:  # regular file only (no symlink, no symlinked dir); O_NONBLOCK: a swapped-in FIFO cannot hang
            if path.parent.is_symlink() or not stat.S_ISREG(path.lstat().st_mode): return "no such change"
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with open(fd, encoding="utf-8") as fh: rec = json.load(fh)
        except FileNotFoundError: return "no such change"
        except (OSError, ValueError, RecursionError): return "unreadable change"
        if not isinstance(rec, dict): return "unreadable change"
        return "not applied" if rec.get("state") != "applied" else "undone" if "revertedBy" in rec else None

    def _check_approved(self, source):
        """The change id of an owner-approved source once its record checks out (else unverified); None otherwise."""
        change_id = source.split(":", 1)[1] if source.startswith("owner-approved:") else None
        if change_id is not None and self._approved_problem(change_id): raise ValueError("unverified source")
        return change_id

    def remember(self, key, value, kind, source, approved_change=None) -> None:
        _check_key(key)
        _check_value(value)
        if kind not in KINDS: raise ValueError("kind must be fact or preference")
        _check_source(source)
        if approved_change is not None and (not _clean(approved_change) or len(approved_change) > MAX_VALUE):
            raise ValueError("invalid approved_change")
        if source.startswith("owner-approved:") and approved_change not in (None, source.split(":", 1)[1]):
            raise ValueError("approved_change does not match source")
        with self._tx():
            if self._active(key) is not None: raise ValueError("use correct")
            change_id = self._check_approved(source)  # after the key check: a stored key still says "use correct"
            self._insert(key, value, kind, source, approved_change if change_id is None else change_id)

    def correct(self, key, value, source) -> None:
        """Supersede the active row with a new value (same kind) in one transaction; KeyError if none is active,
        ValueError("already remembered") if the value is exactly the active one."""
        _check_key(key)
        _check_value(value)
        _check_source(source)
        with self._tx():
            old = self._active(key)
            if old is None: raise KeyError(key)
            change_id = self._check_approved(source)  # before any write: a refusal leaves the active row as it was
            if old["value"] == value: raise ValueError("already remembered")  # exact text: no new row, the date stays
            self.db.execute("UPDATE memory SET superseded_at = ? WHERE id = ?", (self._now(), old["id"]))
            self._insert(key, value, old["kind"], source, change_id)

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


class UnsafeFile(Exception):
    """conversation.sqlite3 is a symlink (dangling too) or not a regular file: history reads nothing from it."""


def _cell(v, nullable=False):
    """A text cell as stored; None only where nullable (dates); a BLOB, number or other None reads "unreadable"."""
    return v if isinstance(v, str) or (v is None and nullable) else "unreadable"


def history(state_dir, key=None, values=False) -> dict:
    path, rows, out = Path(state_dir) / "conversation.sqlite3", [], []
    try: mode = os.lstat(path).st_mode  # lstat: a link is never followed to another state's database
    except FileNotFoundError: mode = None
    if mode is not None and not stat.S_ISREG(mode): raise UnsafeFile("conversation file is a link or not a regular file")
    if mode is not None:  # mode=ro: never created or written here; sqlite3.DatabaseError if unreadable
        with contextlib.closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone():
                rows = db.execute(f"SELECT {', '.join(AUDIT)}, {ACTIVE}, source, value FROM memory WHERE ? IS NULL "
                                  "OR key = ? ORDER BY created_at, id", (key, key)).fetchall()
    for *audit, active, source, value in rows:  # never the source detail, approved_change or an inactive value
        out.append({**{f: _cell(v, f.endswith("_at")) for f, v in zip(AUDIT, audit)},
                    "source_kind": m[1] if (m := SOURCE_KIND.match(str(source))) else "other",
                    "active": bool(active), **({"value": _cell(value)} if values and active else {})})
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
        except UnsafeFile as exc: doc, code = {"result": "unsafe", "problem": str(exc)}, 2
        except sqlite3.DatabaseError: doc, code = {"result": "unreadable"}, 1
    print(json.dumps(doc, ensure_ascii=False))
    return code


if __name__ == "__main__": sys.exit(main())
