#!/usr/bin/env python3
"""Compare two saved Hass retention reports without opening live state."""

import argparse
import json
from pathlib import Path
import re


REPORT_METADATA = {"days", "deletes", "cutoff"}
ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def reject_constant(_token):
    raise ValueError("not a JSON value")


def load_report(path, side, fail):
    try:
        regular = path.is_file()
    except OSError:
        regular = False
    if not regular:
        fail(f"no-file {side}")
        return None

    try:
        last = ""
        with path.open(encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    last = line
        report = json.loads(last, parse_constant=reject_constant)
        if isinstance(report, dict) and all(
            type(report.get(key)) is int for key in ("days", "deletes")
        ):
            return report
    except (OSError, ValueError, RecursionError):
        pass  # Do not echo paths, source lines, or parser diagnostics.
    fail(f"bad-report {side}")
    return None


def is_date(value):
    # The producer emits ISO calendar dates, never free-form strings.
    return isinstance(value, str) and ISO_DATE.fullmatch(value) is not None


def compare_classes(reports, fail):
    sides = ("before", "after")
    before, after = (reports.get(side, {}) for side in sides)
    for name in sorted((before.keys() | after.keys()) - REPORT_METADATA):
        for side, report in reports.items():
            if name not in report:
                continue
            value = report[name]
            if value == "unavailable":
                fail(f"unavailable {side} {name}")
            elif value is None:
                print(f"note absent {side} {name}")

        left, right = before.get(name), after.get(name)
        if not isinstance(left, dict) or not isinstance(right, dict):
            continue
        for member in sorted(left.keys() & right.keys()):
            old, new = left[member], right[member]
            if type(old) is int and type(new) is int:
                print(f"delta {name}.{member} {old} {new}")
            elif (
                (old, new) != (None, None)
                and (old is None or is_date(old))
                and (new is None or is_date(new))
            ):
                print(f"oldest {name} {old or 'null'} {new or 'null'}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="retention_report_diff.py", description=__doc__, allow_abbrev=False,
    )
    parser.add_argument("--before", required=True, type=Path, metavar="FILE")
    parser.add_argument("--after", required=True, type=Path, metavar="FILE")
    args, extras = parser.parse_known_args(argv)
    if extras:
        # argparse would otherwise echo unknown arguments, including paths.
        parser.error("unrecognized arguments")

    failed = False

    def fail(reason):
        nonlocal failed
        failed = True
        print(f"FAIL {reason}")

    reports = {}
    for side in ("before", "after"):
        report = load_report(getattr(args, side), side, fail)
        if report is not None:
            reports[side] = report

    if len(reports) == 2 and reports["before"]["days"] != reports["after"]["days"]:
        fail("days-mismatch")
    for side, report in reports.items():
        if report["deletes"] != 0:
            fail(f"deletes-nonzero {side}")
    compare_classes(reports, fail)

    print(f"{'FAIL' if failed else 'PASS'} retention_report_diff")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
