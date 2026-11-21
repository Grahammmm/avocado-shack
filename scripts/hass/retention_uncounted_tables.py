#!/usr/bin/env python3
"""List row counts for tables omitted by the Hass retention report."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat
from typing import NoReturn


COUNTED = {
    "conversation": {"messages", "outbox", "drafts", "approvals", "memory"},
    "inbox": {"inbound"},
}


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Argparse can echo unknown arguments, including private paths.
        super().error("invalid arguments; use --help")


def table_counts(path, counted):
    # Only for offline, stable inputs. A plain mode=ro connection can still
    # create WAL sidecars; immutable prevents writes but may skip journal data.
    for suffix in ("-wal", "-journal"):
        try:
            sidecar = os.lstat(path.with_name(path.name + suffix))
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(sidecar.st_mode) or sidecar.st_size:
            raise sqlite3.DatabaseError("store must be cleanly closed and checkpointed")
    uri = f"{path.absolute().as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as db:
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
        return None, table_counts(path, counted)
    except (FileNotFoundError, NotADirectoryError):
        return f"missing-db {name}", []
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
