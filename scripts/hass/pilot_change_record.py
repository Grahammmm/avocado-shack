#!/usr/bin/env python3
"""Read one stored pilot install outcome without opening the site."""

import argparse
import json
import os
import re
import stat
import sys

# Only names written by hass/install.py, never path, exception or rollback details.
FAILURE_NAMES = {
    "site path is not a regular file",
    "site file cannot be read",
    "readback mismatch",
    "write failed",
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def reject_constant(_token):
    raise ValueError("non-JSON number")


def read_record(state, change_id):
    # Match editor.CHANGE_ID_RE without importing the writer or its dependencies.
    if not re.fullmatch(r"chg-[0-9a-f]{12}", change_id):
        return None
    name = f"{change_id}.json"
    try:
        directory = os.open(os.path.join(state, "changes"),
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if not stat.S_ISREG(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode):
                return None
            # Open relative to the checked directory; recheck the opened file in
            # case the name was replaced. O_NONBLOCK avoids waiting on a FIFO swap.
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, encoding="utf-8") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    return None
                record = json.load(source, object_pairs_hook=unique_object, parse_constant=reject_constant)
        finally:
            os.close(directory)
    except (OSError, ValueError, RecursionError):
        return None
    return record if isinstance(record, dict) else None


def outcome(record):
    if record is None:
        return 1, "NOT-INSTALLED missing-record"
    result = record.get("install")
    if isinstance(result, dict):
        if result.get("state") == "installed":
            commit = result.get("commit")
            if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
                return 1, "NOT-INSTALLED bad-commit"
            if (result.keys() == {"state", "commit", "installed_at", "files"}
                    and isinstance(result["installed_at"], str) and result["installed_at"]
                    and type(result["files"]) is int and result["files"] > 0):
                return 0, f"INSTALLED commit {commit[:12]}"
        elif result.get("state") == "failed" and isinstance(result.get("reason"), str):
            name = result["reason"].partition(":")[0]
            if name in FAILURE_NAMES:
                return 1, f"NOT-INSTALLED {name}"
    return 1, "NOT-INSTALLED no-install-result"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--state", required=True, help="Hass state directory (read only)")
    parser.add_argument("--change-id", required=True, help="change ID (chg- followed by 12 lowercase hex digits)")
    args = parser.parse_args(argv)
    status, line = outcome(read_record(args.state, args.change_id))
    print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
