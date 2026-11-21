#!/usr/bin/env python3
"""Count draft screenshot references against a stable offline state directory."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat


DB_NAME = "conversation.sqlite3"
PROPOSAL_SUFFIX = "-proposal.png"


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can echo an unrecognized private path.
        super().error("invalid arguments; use --help")


def read_drafts(path):
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None, f"unsafe-db {DB_NAME}"
    except (FileNotFoundError, NotADirectoryError):
        return None, f"missing-db {DB_NAME}"
    except (OSError, ValueError):
        return None, f"not-sqlite {DB_NAME}"

    try:
        # Immutable mode prevents SQLite from creating sidecars, but can ignore
        # pending journal contents. Do not report a possibly stale snapshot.
        for suffix in ("-wal", "-journal"):
            try:
                sidecar = os.lstat(path.with_name(path.name + suffix))
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(sidecar.st_mode) or sidecar.st_size:
                return None, f"not-sqlite {DB_NAME}"
        uri = path.absolute().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            return db.execute("SELECT drafts.change_id, drafts.screenshot FROM drafts").fetchall(), None
    except (OSError, ValueError, sqlite3.Error):
        return None, f"not-sqlite {DB_NAME}"


def screenshot_names(path):
    try:
        if stat.S_ISDIR(os.lstat(path).st_mode):
            with os.scandir(path) as entries:
                return {entry.name for entry in entries if entry.is_file(follow_symlinks=False)}
    except (OSError, ValueError):
        pass
    return None


def report(drafts, files):
    refs = []
    bad_refs = 0
    for _, screenshot in drafts or ():
        if screenshot is None:
            continue
        if not isinstance(screenshot, str) or not screenshot:
            bad_refs += 1
        else:
            refs.append(os.path.basename(screenshot))

    if drafts is not None:
        print(f"drafts {len(drafts)}")
        print(f"refs {len(refs)}")
    if files is not None:
        print(f"files {len(files)}")
    if drafts is not None:
        print(f"note bad-ref {bad_refs}")
    if drafts is None or files is None:
        return 0

    change_ids = {change_id for change_id, _ in drafts}
    proposal_orphans = {
        name
        for name in files
        if name.endswith(PROPOSAL_SUFFIX) and name.removesuffix(PROPOSAL_SUFFIX) not in change_ids
    }
    print(f"note proposal-orphans {len(proposal_orphans)}")
    print(f"note other-unreferenced {len(files.difference(proposal_orphans, refs))}")
    return sum(name not in files for name in refs)


def main(argv=None):
    parser = PrivateArgumentParser(prog="screenshot_refs.py", description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", required=True, type=Path, help="stable offline state directory")
    state = parser.parse_args(argv).state

    drafts, db_error = read_drafts(state / DB_NAME)
    files = screenshot_names(state / "screenshots")
    findings = [db_error] if db_error else []
    if files is None:
        findings.append("no-screenshots-dir")
    dangling = report(drafts, files)
    if dangling:
        findings.append(f"dangling-screenshot {dangling}")
    for finding in findings:
        print(f"FAIL {finding}")
    print("FAIL screenshot_refs" if findings else "PASS screenshot_refs")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
