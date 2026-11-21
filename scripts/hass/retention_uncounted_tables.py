#!/usr/bin/env python3
"""List row counts for tables omitted by the Hass retention report."""

import argparse
from contextlib import closing, contextmanager
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
from typing import NoReturn


COUNTED = {
    "conversation": {"messages", "outbox", "drafts", "approvals", "memory"},
    "inbox": {"inbound"},
}


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Argparse can echo unknown arguments, including private paths.
        super().error("invalid arguments; use --help")


@contextmanager
def _open_snapshot(path):
    # Only for offline, stable inputs. SQLite can recover journals and build
    # WAL shared memory on the copy without touching the input directory.
    sources = [path]
    for suffix in ("-wal", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        try:
            mode = os.lstat(sidecar).st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise sqlite3.DatabaseError("unsafe SQLite sidecar")
        sources.append(sidecar)

    # Choose the directory explicitly: tempfile's default discovery can probe
    # TMPDIR (or the working directory) by creating a file there.
    state = path.parent.resolve()
    temp_root = Path(os.environ.get("TMPDIR") or "/tmp").resolve()
    if temp_root.is_relative_to(state):
        temp_root = state.parent
        if temp_root == state:
            raise sqlite3.DatabaseError("no snapshot location outside the input directory")

    with tempfile.TemporaryDirectory(dir=temp_root) as temp:
        snapshot = Path(temp)
        for source in sources:
            shutil.copyfile(source, snapshot / source.name)
        with closing(sqlite3.connect(snapshot / path.name)) as db:
            db.execute("PRAGMA query_only=ON")
            yield db


def table_counts(path, counted):
    with _open_snapshot(path) as db:
        names = db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        counts = []
        for (name,) in names:
            if name.lower().startswith("sqlite_") or name.lower() in counted:
                continue
            identifier = name.replace('"', '""')
            count, = db.execute(f'SELECT COUNT(*) FROM main."{identifier}"').fetchone()
            counts.append((name, count))
        return counts


def inspect(state, store, counted):
    name = f"{store}.sqlite3"
    path = state / name
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return f"unsafe-db {name}", []
    except (FileNotFoundError, NotADirectoryError):
        return f"missing-db {name}", []
    except (OSError, ValueError):
        return f"not-sqlite {name}", []
    try:
        return None, table_counts(path, counted)
    except (OSError, ValueError, sqlite3.Error):
        return f"not-sqlite {name}", []


def main(argv=None):
    parser = PrivateArgumentParser(prog="retention_uncounted_tables.py", description=__doc__)
    parser.add_argument("--state", required=True, type=Path, metavar="DIR",
                        help="directory of cleanly closed, checkpointed SQLite stores")
    args = parser.parse_args(argv)
    failed = False
    for store, counted in sorted(COUNTED.items()):
        reason, counts = inspect(args.state, store, counted)
        if reason:
            print(f"FAIL {reason}")
            failed = True
        for name, count in counts:
            print(f"table {store}.{name} rows {count}")
    print(f"{'FAIL' if failed else 'PASS'} retention_uncounted_tables")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
