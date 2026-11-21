#!/usr/bin/env python3
"""Check that two local commits have the same maker allowlist."""

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import subprocess


SOURCES = "hass/npp/assets/hass-maker-research/sources.json"
SHA = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")


class DuplicateKey(ValueError):
    """A JSON object contained the same key twice."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey
        result[key] = value
    return result


def reject_constant(_token):
    raise ValueError


def canonical_json(value):
    """Serialize JSON deterministically without rounding decimal numbers."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError
        sign, digits, exponent = value.as_tuple()
        assert isinstance(exponent, int)
        digits = list(digits)
        while len(digits) > 1 and digits[-1] == 0:
            digits.pop()
            exponent += 1
        if not any(digits):
            exponent = 0
        coefficient = ''.join(map(str, digits))
        return (('-' if sign else '') + coefficient[0] + '.'
                + (coefficient[1:] or '0') + 'e' + str(exponent + len(digits) - 1))
    if isinstance(value, list):
        return '[' + ','.join(canonical_json(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(key) + ':' + canonical_json(value[key])
                              for key in sorted(value)) + '}'
    return json.dumps(value, separators=(',', ':'), allow_nan=False)


def git(repo, *args):
    # Forbid transport (including lazy fetch in partial clones) and ignore
    # replacement refs so the results describe the named commits themselves.
    env = dict(os.environ, GIT_ALLOW_PROTOCOL="", GIT_NO_LAZY_FETCH="1")
    try:
        result = subprocess.run(
            ["git", "--no-pager", "--no-replace-objects", *args], cwd=repo, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
        )
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None
    return result.stdout


def read_allowlist(repo, sha, side):
    if not SHA.fullmatch(sha):
        return None, "bad-sha"
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{sha}^{{commit}}")
    if commit is None or commit.strip() != sha.lower().encode("ascii"):
        return None, "unknown-commit"
    raw = git(repo, "show", "--no-textconv", f"{sha}:{SOURCES}")
    if raw is None:
        return None, f"absent {side}"
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                              parse_constant=reject_constant, parse_float=Decimal)
        if not isinstance(document, dict):
            return None, f"bad-json {side}"
        entries = document.get("allowlist")
        if not isinstance(entries, list):
            return None, f"not-list {side}"
        return Counter(canonical_json(entry) for entry in entries), None
    except DuplicateKey:
        return None, f"duplicate-key {side}"
    except (ValueError, InvalidOperation, RecursionError):
        return None, f"bad-json {side}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", required=True, help="local Git repository")
    parser.add_argument("--old", required=True, help="old full commit SHA")
    parser.add_argument("--new", required=True, help="new full commit SHA")
    args = parser.parse_args(argv)
    old, old_error = read_allowlist(args.repo, args.old, "old")
    new, new_error = read_allowlist(args.repo, args.new, "new")
    findings = [error for error in (old_error, new_error) if error is not None]
    if not findings:
        added, removed = new - old, old - new
        print(f"old_count {sum(old.values())} new_count {sum(new.values())} "
              f"added {sum(added.values())} removed {sum(removed.values())}")
        for label, entries in (("added", added), ("removed", removed)):
            for entry in sorted(entries):
                digest = hashlib.sha256(entry.encode("ascii")).hexdigest()[:12]
                for _ in range(entries[entry]):
                    print(f"{label} {digest}")
        if added or removed:
            findings.append("changed")
    for reason in findings:
        print(f"FAIL {reason}")
    print(f"{'FAIL' if findings else 'PASS'} install_allowlist_diff")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
