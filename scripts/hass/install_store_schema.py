#!/usr/bin/env python3
"""Compare stable, checkpointed store copies with this checkout's schema."""

import argparse
from contextlib import closing, contextmanager
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile

# Use the release being checked, not an installed copy of Hass.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def schema(db):
    tables = db.execute("SELECT name FROM main.sqlite_master WHERE type = 'table' ORDER BY name")
    result = {}
    for (table,) in tables:
        quoted = table.replace('"', '""')
        result[table] = {row[1]: row[2] for row in db.execute(f'PRAGMA main.table_info("{quoted}")')}
    return result


def private_directory(input_dirs, prefix):
    # Select a root before tempfile can probe it: TMPDIR can be an input directory.
    roots = [os.environ.get(key) for key in ("TMPDIR", "TEMP", "TMP")]
    for candidate in (*roots, "/tmp", "/var/tmp", "/usr/tmp", os.curdir):
        if not candidate:
            continue
        root = Path(os.path.realpath(candidate))
        if any(root.is_relative_to(directory) for directory in input_dirs):
            continue
        try:
            return tempfile.TemporaryDirectory(prefix=prefix, dir=root)
        except OSError:
            continue
    raise OSError("no writable temporary directory outside the inputs")


def reference_schema(store, input_dirs):
    with private_directory(input_dirs, "hass-schema-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        if store == "relay":
            from hass.relay import RelayStore

            reference = RelayStore(root)
        else:
            from hass.inbox import Inbox

            reference = Inbox(root, start_at="2026-01-01T00:00:00+00:00")
        with closing(reference.db) as db:
            return schema(db)


@contextmanager
def _open_snapshot(path, input_dirs):
    if not stat.S_ISREG(path.lstat().st_mode):  # Do not follow a symlink supplied as the file.
        raise ValueError("not a regular file")
    sources = [path]
    for suffix in ("-wal", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        try:
            mode = sidecar.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("not a regular sidecar")
        sources.append(sidecar)
    # SQLite can recover the snapshot and rebuild SHM without touching the inputs.
    with private_directory(input_dirs, "hass-snapshot-") as directory:
        root = Path(directory)
        for source in sources:
            shutil.copyfile(source, root / source.name)
        with closing(sqlite3.connect(root / path.name)) as db:
            db.execute("PRAGMA query_only=ON")
            yield db


def check(store, path, input_dirs):
    try:
        expected = reference_schema(store, input_dirs)
    except Exception:
        print(f"FAIL reference-error {store}")
        return False
    try:
        with _open_snapshot(path, input_dirs) as db:
            actual = schema(db)
    except (OSError, ValueError, sqlite3.Error):
        print(f"FAIL not-sqlite {store}")
        return False

    passed = True
    for table, columns in expected.items():
        label = f"{store}.{table}"
        if table not in actual:
            print(f"FAIL missing-table {label}")
            passed = False
            continue
        present = actual[table]
        table_ok = True
        for column, declared_type in columns.items():
            if column not in present:
                print(f"FAIL missing-column {label}.{column}")
                table_ok = False
            elif present[column] != declared_type:
                print(f"FAIL type-mismatch {label}.{column}")
                table_ok = False
        if table_ok:
            print(f"ok {label}")
        else:
            passed = False
        for column in present:
            if column not in columns:
                print(f"note extra {label}.{column}")
    for table in actual:
        if table not in expected:
            print(f"note extra {store}.{table}")
    return passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relay", type=Path, metavar="FILE", help="stable copy of relay.sqlite3")
    parser.add_argument("--inbox", type=Path, metavar="FILE", help="stable copy of inbox.sqlite3")
    args = parser.parse_args(argv)
    stores = [(store, path) for store, path in vars(args).items() if path is not None]
    if not stores:
        print("FAIL no-store")
    input_dirs = {Path(os.path.realpath(path.parent)) for _, path in stores}
    outcomes = [check(store, path, input_dirs) for store, path in stores]
    if outcomes and all(outcomes):
        print("PASS install_store_schema")
        return 0
    print("FAIL install_store_schema")
    return 1


if __name__ == "__main__":
    sys.exit(main())
