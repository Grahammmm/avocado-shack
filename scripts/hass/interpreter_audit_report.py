#!/usr/bin/env python3
"""Summarize interpreter calls in a half-open window from a saved SQLite store."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
import math
import os
from pathlib import Path
import re
import sqlite3
import stat


DB_NAME = "conversation.sqlite3"
REPORT = "interpreter_audit_report"
LABEL = re.compile(r"[a-z][a-z0-9_-]{0,31}")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can include raw arguments (including input paths) in errors.
        super().error("invalid arguments; see --help")


def aware_time(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def label(value):
    return value if isinstance(value, str) and LABEL.fullmatch(value) else "other"


def fail(*reasons):
    for reason in reasons:
        print(f"FAIL {reason}")
    print(f"FAIL {REPORT}")
    return 1


def summarize(path, since, until, expected):
    backends, primary_errors, errors = Counter(), Counter(), Counter()
    unexpected = set()
    calls = fallbacks = unparsed = 0
    seconds = []
    # Immutable reads cannot create SQLite sidecars, but may ignore a WAL.
    # Refuse an uncheckpointed snapshot rather than reporting stale data.
    try:
        wal = os.lstat(path.with_name(path.name + "-wal"))
    except FileNotFoundError:
        pass
    else:
        if wal.st_size or not stat.S_ISREG(wal.st_mode):
            raise ValueError("audit snapshot has an active WAL")
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)) as db:
        has_table = db.execute(
            "SELECT COUNT(*) FROM sqlite_schema "
            "WHERE type = 'table' AND name = 'interpreter_audit' COLLATE NOCASE"
        ).fetchone()[0]
        if has_table:
            rows = db.execute(
                "SELECT at, backend, fallback, primary_error, error, seconds FROM interpreter_audit"
            )
            for at, backend, fallback, primary_error, error, elapsed in rows:
                timestamp = aware_time(at)
                if timestamp is None:
                    unparsed += 1
                    continue
                if not since <= timestamp < until:
                    continue
                calls += 1
                backend_label = label(backend)
                backends[backend_label] += 1
                if expected and backend not in expected:
                    unexpected.add(backend_label)
                fallbacks += bool(fallback)
                if primary_error is not None:
                    primary_errors[label(primary_error)] += 1
                if error is not None:
                    errors[label(error)] += 1
                if elapsed is not None:
                    if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed):
                        raise ValueError("invalid audit duration")
                    seconds.append(elapsed)

    if not has_table:
        print("note no-audit-table")
    print(f"calls {calls}")
    for name, count in sorted(backends.items()):
        print(f"backend {name} {count}")
    print(f"fallback {fallbacks}")
    for kind, counts in (("primary-error", primary_errors), ("error", errors)):
        for code, count in sorted(counts.items()):
            print(f"{kind} {code} {count}")
    if seconds:
        seconds.sort()
        p50 = seconds[(50 * len(seconds) - 1) // 100]
        p90 = seconds[(90 * len(seconds) - 1) // 100]
        print(f"seconds p50 {p50:.3f} p90 {p90:.3f}")
    else:
        print("seconds none")
    print(f"unparsed {unparsed}")
    return sorted(unexpected)


def main(argv=None):
    parser = Parser(prog=REPORT, description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="checkpointed state snapshot (not a live store)")
    parser.add_argument("--since", required=True, help="inclusive ISO timestamp with offset")
    parser.add_argument("--until", required=True, help="exclusive ISO timestamp with offset")
    parser.add_argument("--expect-backend", action="append", metavar="NAME", help="allowed backend (repeatable)")
    args = parser.parse_args(argv)

    since, until = aware_time(args.since), aware_time(args.until)
    if since is None or until is None or since >= until:
        return fail("bad-window")

    try:
        path = (args.state / DB_NAME).absolute()
        mode = os.lstat(path).st_mode
    except (FileNotFoundError, NotADirectoryError):
        return fail(f"missing-db {DB_NAME}")
    except (OSError, ValueError):
        return fail(f"not-sqlite {DB_NAME}")
    if not stat.S_ISREG(mode):
        return fail(f"unsafe-db {DB_NAME}")
    try:
        unexpected = summarize(path, since, until, set(args.expect_backend or ()))
    except (sqlite3.Error, OSError, ValueError):
        return fail(f"not-sqlite {DB_NAME}")
    if unexpected:
        return fail(*(f"unexpected-backend {name}" for name in unexpected))
    print(f"PASS {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
