#!/usr/bin/env python3
"""Compare inbound coverage in stable offline SQLite snapshots, as counts only."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import stat


NAME = "transcript_inbound_parity"


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error text can echo raw arguments, including paths.
        super().error("invalid arguments; see --help")


def parse_time(value):
    try:
        stamp = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo is not None else None


def read_window(path, query, selection, since, until):
    try:
        mode = os.lstat(path).st_mode
    except (FileNotFoundError, NotADirectoryError):
        return "missing-db", None, 0
    except OSError:
        return "not-sqlite", None, 0
    if not stat.S_ISREG(mode):
        return "unsafe-db", None, 0

    counts = Counter()
    unparsed = 0
    try:
        # For stable offline snapshots only: avoid SQLite creating WAL sidecars.
        uri = path.absolute().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            for provider_id, category, raw_time in db.execute(query):
                stamp = parse_time(raw_time)
                if stamp is None:
                    unparsed += 1
                elif category == selection and since <= stamp < until:
                    counts[provider_id] += 1
    except (OSError, sqlite3.Error):
        return "not-sqlite", None, 0
    return None, counts, unparsed


def main(argv=None):
    parser = PrivateArgumentParser(prog=f"{NAME}.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", required=True, type=Path, metavar="DIR")
    parser.add_argument("--since", required=True, metavar="ISO", help="inclusive, with timezone")
    parser.add_argument("--until", required=True, metavar="ISO", help="exclusive, with timezone")
    args = parser.parse_args(argv)
    since, until = parse_time(args.since), parse_time(args.until)
    if since is None or until is None or since >= until:
        print("FAIL bad-window")
        print(f"FAIL {NAME}")
        return 1

    findings = []
    windows = []
    unparsed = 0
    for name, query, selection in (
        ("inbox.sqlite3", "SELECT provider_id, state, received_at FROM inbound", "done"),
        ("transcript.sqlite3", "SELECT provider_id, direction, utc FROM events", "in"),
    ):
        error, counts, invalid = read_window(args.state / name, query, selection, since, until)
        if error is not None:
            findings.append(f"{error} {name}")
        windows.append(counts)
        unparsed += invalid

    if not findings:
        expected, found = windows
        matched = sum(count for key, count in found.items() if key in expected)
        missing = sum(count for key, count in expected.items() if key not in found)
        print(f"inbound-done {sum(expected.values())}")
        print(f"matched {matched}")
        print(f"note transcript-only {sum(found.values()) - matched}")
        print(f"unparsed {unparsed}")
        if missing:
            findings.append(f"inbound-not-in-transcript {missing}")

    for finding in findings:
        print(f"FAIL {finding}")
    print(f"{'FAIL' if findings else 'PASS'} {NAME}")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
