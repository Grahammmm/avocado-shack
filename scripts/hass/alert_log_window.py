#!/usr/bin/env python3
"""Check a saved alert log for Hass health alerts in an attended window."""

import argparse
from datetime import datetime
from pathlib import Path
import re


HEALTH_LINE = re.compile(
    rb"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) HASS-HEALTH "
    rb"([0-9a-f]{12} [a-z0-9-]+(?: [a-z0-9-]+)*)"
)


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse can quote arbitrary arguments, including private log paths.
        super().error("invalid arguments; see --help")


def parse_time(text):
    # fromisoformat also accepts arbitrary single-character date separators.
    if "T" not in text and " " not in text:
        raise ValueError
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        raise ValueError
    return stamp


def scan(log, window):
    bad_line = False
    alerts = other = 0
    last_before = None
    for number, raw in enumerate(log, 1):
        if b" HASS-HEALTH " not in raw:
            other += 1
            continue
        line = raw[:-2] if raw.endswith(b"\r\n") else raw.removesuffix(b"\n")
        match = HEALTH_LINE.fullmatch(line)
        try:
            stamp = datetime.fromisoformat(match[1].decode("ascii")) if match else None
        except ValueError:
            stamp = None
        if match is None or stamp is None:
            print(f"FAIL bad-line {number}")
            bad_line = True
            continue
        if window is not None:
            since, until = window
            payload = f"{match[1].decode('ascii')} {match[2].decode('ascii')}"
            if since <= stamp < until:
                print(f"alert {payload}")
                alerts += 1
            elif stamp < since and (last_before is None or stamp >= last_before[0]):
                last_before = stamp, payload

    if window is not None:
        print("last-before", last_before[1] if last_before is not None else "none")
    print(f"note other-lines {other}")
    if alerts:
        print(f"FAIL alert-in-window {alerts}")
    return bad_line or alerts > 0


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--log", required=True, type=Path, help="copy of the alert log")
    parser.add_argument("--since", required=True, help="inclusive ISO-8601 time with timezone")
    parser.add_argument("--until", required=True, help="exclusive ISO-8601 time with timezone")
    args = parser.parse_args(argv)

    try:
        since, until = parse_time(args.since), parse_time(args.until)
        if since >= until:
            raise ValueError
        window = since, until
    except ValueError:
        print("FAIL bad-window")
        window = None

    try:
        if not args.log.is_file():
            raise OSError
        with args.log.open("rb") as log:
            failed = scan(log, window) or window is None
    except (OSError, ValueError):
        print("FAIL no-log")
        failed = True

    print("FAIL alert_log_window" if failed else "PASS alert_log_window")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
