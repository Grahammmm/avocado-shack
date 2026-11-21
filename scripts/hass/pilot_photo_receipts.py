#!/usr/bin/env python3
"""Report photo receipts for one inbound message. Checks receipt indexes, not photo bytes."""

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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos-db", required=True, type=Path)
    parser.add_argument("--guid", required=True, help="inbound message GUID, not a pilot job code")
    parser.add_argument("--expect-sha256", type=expected_digest)
    parser.add_argument("--full", action="store_true", help="show all 64 digest digits")
    args = parser.parse_args(argv)
    try:
        with closing(sqlite3.connect(args.photos_db.absolute().as_uri() + "?mode=ro", uri=True)) as db:
            rows = db.execute("SELECT idx, count, sha256, received_at FROM photo_receipt "
                              "WHERE guid = ? ORDER BY idx", (args.guid,)).fetchall()
    except (sqlite3.Error, OSError, ValueError):
        print("error: could not read photo receipts", file=sys.stderr)
        return 1

    width = 64 if args.full else 12
    digests = set()
    for idx, count, digest, received_at in rows:
        shown = "-"
        if isinstance(digest, str) and HEX.fullmatch(digest):
            digests.add(digest.lower())
            shown = digest[:width]
        print(f"{idx}/{count} {shown} {received_at}")

    if not rows:
        reason = "no-rows"
    elif len({row[1] for row in rows}) != 1:
        reason = "count-disagrees"
    elif len(rows) != rows[0][1] or any(row[0] != idx for idx, row in enumerate(rows)):
        reason = "missing-index"
    else:
        reason = None
    print(f"INCOMPLETE {reason}" if reason else "COMPLETE")
    missing_digest = args.expect_sha256 is not None and args.expect_sha256 not in digests
    if missing_digest:
        print("EXPECTED-DIGEST-NOT-FOUND")
    return int(reason is not None or missing_digest)


if __name__ == "__main__":
    sys.exit(main())
