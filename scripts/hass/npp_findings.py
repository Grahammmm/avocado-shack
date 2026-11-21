#!/usr/bin/env python3
"""Maintain the private NPP findings ledger in an operator-owned directory outside Git.

Summaries must be redacted before submission; the character check is a backstop,
not a detector for names or other private prose. A repeat stays marked after
closure so the repeat count cannot fall when its card is resolved.
"""

import argparse
from collections import Counter
from datetime import date, timedelta
import fcntl
import os
from pathlib import Path
import re
import stat
import tempfile


COLUMNS = "id week stage class summary case_id card state reason".split()
HEADER = "\t".join(COLUMNS)
STAGES = {f"S{n}" for n in range(1, 14)}
WEEK = re.compile(r"([0-9]{4})-W([0-9]{2})")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CASE = re.compile(r"(?:case-[0-9]+-[a-z0-9]+(?:-[a-z0-9]+)*\.json|npp-[0-9]{8}-[0-9]+)")
CARD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class LedgerError(ValueError):
    """An error message safe to print without echoing any source values."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's usual errors can echo private input, especially a bad quote.
        self.exit(2, "error: invalid arguments (see --help)\n")


def monday(value):
    match = WEEK.fullmatch(value)
    if not match:
        raise LedgerError("invalid ISO week")
    try:
        return date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except ValueError:
        raise LedgerError("invalid ISO week") from None


def validate_add(week, stage, failure_class, summary):
    monday(week)
    if stage not in STAGES:
        raise LedgerError("invalid stage")
    if not SLUG.fullmatch(failure_class):
        raise LedgerError("invalid failure class")
    if (not summary.strip() or not summary.isprintable()
            or any(char.isdigit() or char in "@$" for char in summary)):
        raise LedgerError("summary must be redacted and on one line")


def validate_close(case, reason, card):
    if (not CARD.fullmatch(card) or bool(case) == bool(reason)
            or (case and not CASE.fullmatch(case))
            or (reason and not SLUG.fullmatch(reason))):
        raise LedgerError("closure requires a card and exactly one case filename, case tag or reason slug")


def ledger_path(path):
    # Check both the supplied ancestry and its physical destination: neither a
    # Git worktree's .git file nor a symlink into a checkout may hide it.
    resolved = path.resolve()
    for parent in (*path.absolute().parents, *resolved.parents):
        if os.path.lexists(parent / ".git"):
            raise LedgerError("ledger must be outside Git worktrees")
    if path.is_symlink() or resolved.name == ".git":
        raise LedgerError("invalid ledger path")
    return resolved


def open_private(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            raise LedgerError("ledger and lock must be regular private files")
    except BaseException:
        os.close(fd)
        raise
    return fd


def read_ledger(path):
    try:
        fd = open_private(path, os.O_RDONLY)
    except FileNotFoundError:
        return []
    rows = []
    weeks = Counter()
    with os.fdopen(fd, "rb") as source:
        line_no = 1
        try:
            if source.readline().decode("utf-8").removesuffix("\n").removesuffix("\r") != HEADER:
                raise LedgerError("invalid header")
            for line_no, raw in enumerate(source, 2):
                values = raw.decode("utf-8").removesuffix("\n").removesuffix("\r").split("\t")
                finding, week, stage, failure_class, summary, case, card, state, reason = values
                validate_add(week, stage, failure_class, summary)
                weeks[week] += 1
                if finding != f"F-{week}-{weeks[week]}" or state not in {"open", "closed", "repeat"}:
                    raise LedgerError("invalid finding id or state")
                if state == "closed" or (state == "repeat" and card):
                    validate_close(case, reason, card)
                elif case or card or reason:
                    raise LedgerError("unexpected closure fields")
                rows.append(dict(zip(COLUMNS, values)))
        except ValueError:
            raise LedgerError(f"bad-ledger {line_no}") from None
        if stat.S_IMODE(os.fstat(source.fileno()).st_mode) != 0o600:
            raise LedgerError("ledger mode must be 0600")
    return rows


def write_ledger(path, rows):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".npp-findings-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(HEADER + "\n")
            for row in rows:
                output.write("\t".join(row[column] for column in COLUMNS) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def update(path, args):
    # Lock a stable sidecar, not the ledger inode replaced on each commit.
    fd = open_private(path.with_name(f".{path.name}.lock"), os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.fchmod(fd, 0o600)
        rows = read_ledger(path)
        if args.command == "add":
            number = 1 + sum(row["week"] == args.week for row in rows)
            finding = f"F-{args.week}-{number}"
            repeat = any(row["card"] and row["class"] == args.failure_class for row in rows)
            values = (finding, args.week, args.stage, args.failure_class, args.summary,
                      "", "", "repeat" if repeat else "open", "")
            rows.append(dict(zip(COLUMNS, values)))
        else:
            finding = args.id
            row = next((row for row in rows if row["id"] == finding), None)
            if row is None or row["card"]:
                raise LedgerError("no matching open finding")
            row.update(card=args.card, case_id=args.case or "", reason=args.reason or "")
            if row["state"] != "repeat":
                row["state"] = "closed"
        write_ledger(path, rows)
    finally:
        os.close(fd)
    print(finding)


def report(rows, as_of):
    pending = [row for row in rows if not row["card"]]
    repeats = sum(row["state"] == "repeat" for row in rows)
    print(f"open={len(pending)} closed={len(rows) - len(pending)} repeat={repeats}")
    for row in pending:
        print(row["id"])
    if any(as_of - monday(row["week"]) > timedelta(weeks=2) for row in pending):
        print("FAIL npp_findings stale")
        return 1
    print("PASS npp_findings")
    return 0


def main(argv=None):
    parser = PrivateParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add")
    add.add_argument("--week", required=True)
    add.add_argument("--stage", required=True)
    add.add_argument("--class", dest="failure_class", required=True)
    add.add_argument("--summary", required=True)
    close = commands.add_parser("close")
    close.add_argument("id")
    closure = close.add_mutually_exclusive_group(required=True)
    closure.add_argument("--case")
    closure.add_argument("--reason")
    close.add_argument("--card", required=True)
    weekly = commands.add_parser("report")
    weekly.add_argument("--week", required=True, help="ISO week used to check the age of all open findings")
    args = parser.parse_args(argv)
    try:
        path = ledger_path(args.ledger)
        if args.command == "report":
            return report(read_ledger(path), monday(args.week))
        if args.command == "add":
            validate_add(args.week, args.stage, args.failure_class, args.summary)
        else:
            validate_close(args.case or "", args.reason or "", args.card)
        update(path, args)
    except LedgerError as error:
        print(f"FAIL {error}")
        return 1
    except (OSError, ValueError, RuntimeError):
        print("FAIL npp_findings ledger I/O")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
