#!/usr/bin/env python3
"""Report stored photo digests and receipt completeness, without reading photo bytes."""

import argparse
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import sys


HEX = re.compile(r"[0-9a-fA-F]{64}")


def expected_digest(value):
    if not HEX.fullmatch(value):
        raise argparse.ArgumentTypeError("expected 64 hexadecimal digits")
    return value.lower()


def read_only(path):
    return closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True))


def incomplete_reason(rows):
    if not rows:
        return "no-rows"
    if len({row[1] for row in rows}) != 1:
        return "count-disagrees"
    if len(rows) != rows[0][1] or any(row[0] != idx for idx, row in enumerate(rows)):
        return "missing-index"
    return None


def status_line(reason):
    return f"INCOMPLETE {reason}" if reason else "COMPLETE"


def number(value):
    return value if type(value) is int else "-"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos-db", required=True, type=Path)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--code", help="pilot job code (requires --conversation-db)")
    target.add_argument("--guid", help="look up one inbound message directly")
    parser.add_argument("--conversation-db", type=Path, help="conversation store for --code only")
    parser.add_argument("--expect-sha256", type=expected_digest)
    parser.add_argument("--full", action="store_true", help="show all 64 digest digits")
    args = parser.parse_args(argv)
    if args.code is not None:
        if args.conversation_db is None:
            parser.error("--code requires --conversation-db")
        try:
            with read_only(args.conversation_db) as db:
                turns = db.execute("SELECT provider_id FROM npp_turns "
                                   "WHERE job_id = ? ORDER BY provider_id", (args.code,)).fetchall()
        except (sqlite3.Error, OSError, ValueError):
            print("error: could not read conversation turns", file=sys.stderr)
            return 1
        if not turns:
            print("INCOMPLETE unknown-code")
            return 1
    else:
        if args.conversation_db is not None:
            parser.error("--conversation-db is only used with --code")
        turns = [(args.guid,)]

    groups = []
    try:
        with read_only(args.photos_db) as db:
            db.execute("BEGIN")  # One photo-store snapshot for all mapped turns.
            for turn in turns:
                rows = db.execute("SELECT idx, count, sha256, received_at FROM photo_receipt "
                                  "WHERE guid = ? ORDER BY idx", turn).fetchall()
                if rows:  # Text-only turns have no photo receipts to check.
                    groups.append(rows)
    except (sqlite3.Error, OSError, ValueError):
        print("error: could not read photo receipts", file=sys.stderr)
        return 1

    width = 64 if args.full else 12
    digests = set()
    reason = None if groups else "no-rows"
    for ordinal, rows in enumerate(groups, 1):
        group_reason = incomplete_reason(rows)
        reason = reason or group_reason
        if len(groups) > 1:
            print(f"Message {ordinal}: {status_line(group_reason)}")
        for idx, count, digest, received_at in rows:
            shown = "-"
            if isinstance(digest, str) and HEX.fullmatch(digest):
                digests.add(digest.lower())
                shown = digest[:width]
            print(f"{number(idx)}/{number(count)} {shown} {number(received_at)}")

    print(status_line(reason))
    missing_digest = args.expect_sha256 is not None and args.expect_sha256 not in digests
    if missing_digest:
        print("EXPECTED-DIGEST-NOT-FOUND")
    return int(reason is not None or missing_digest)


if __name__ == "__main__":
    sys.exit(main())
