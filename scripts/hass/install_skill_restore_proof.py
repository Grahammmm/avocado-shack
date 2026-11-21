#!/usr/bin/env python3
"""Read-only proof against an operator-approved roster and prior-state manifest.

Roster JSON: {"profile/skill": {"backup": "/absolute/backup/file",
                               "target": "/absolute/profile/skills/skill/SKILL.md"}}
Prior JSON, with exactly the same keys:
    {"profile/skill": {"sha256": "<64 hex digits>", "mode": "0644"},
     "another/skill": "absent"}

Run `pre` against backups before installing, and `post` against targets after
restoring. Backups must have the prior bytes, but may have a more private mode;
restored targets must have both the prior bytes and the exact prior mode.
Use quiescent paths: this is point-in-time evidence, not a lock, approval check,
or proof of which skill a profile loads.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat


class ProofError(ValueError):
    """A refusal safe to report without echoing input values or paths."""


def path_parts(path):
    if not isinstance(path, str) or not path.startswith('/') or '\0' in path:
        raise ProofError('expected a canonical absolute file path')
    parts = tuple(path[1:].split('/'))
    if any(part in ('', '.', '..') for part in parts):
        raise ProofError('expected a canonical absolute file path')
    return parts


@contextmanager
def parent_dir(parts):
    # Open one component at a time so an intermediate symlink is never followed.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open('/', flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def read_evidence(parts, reader=None):
    """Read a stable regular file; return None if no entry exists."""
    name = parts[-1]
    try:
        with parent_dir(parts) as fd:
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            mode = stat.S_IMODE(before.st_mode)
            if reader is None:
                return None, mode  # Even a dangling link is an existing entry.
            if not stat.S_ISREG(before.st_mode):
                raise ProofError('expected a regular file, not a link or special entry')
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            with os.fdopen(os.open(name, flags, dir_fd=fd), 'rb') as stream:
                if fingerprint(before) != fingerprint(os.fstat(stream.fileno())):
                    raise ProofError('evidence changed during check')
                result = reader(stream)
                after = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if fingerprint(before) != fingerprint(after):
                    raise ProofError('evidence changed during check')
            return result, mode
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        raise ProofError('unsafe or unreadable path') from None


def unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ProofError('duplicate JSON key')
    return result


def load_document(path, label):
    if not path.startswith('/'):
        path = os.path.join(os.getcwd(), path)
    try:
        evidence = read_evidence(path_parts(path), lambda stream: json.load(
            stream, object_pairs_hook=unique_object))
    except (ValueError, RecursionError):
        raise ProofError(f'{label}: invalid or unreadable JSON document') from None
    if evidence is None:
        raise ProofError(f'{label}: missing JSON document')
    return evidence[0]


def validated_rows(roster, prior):
    if not isinstance(roster, dict) or not roster or not all(roster):
        raise ProofError('roster must be a nonempty object with nonempty keys')
    if not isinstance(prior, dict) or prior.keys() != roster.keys():
        raise ProofError('prior manifest keys must match the complete approved roster')

    rows, paths = [], set()
    for index, (key, pair) in enumerate(roster.items(), 1):
        if not isinstance(pair, dict) or pair.keys() != {'backup', 'target'}:
            raise ProofError(f'roster row {index}: expected backup and target paths')
        backup, target = path_parts(pair['backup']), path_parts(pair['target'])
        for path in (backup, target):
            if path in paths:
                raise ProofError('roster contains duplicate file paths')
            paths.add(path)
        state = prior[key]
        expected = None
        if state != 'absent':
            if not isinstance(state, dict) or state.keys() != {'sha256', 'mode'}:
                raise ProofError(f'prior row {index}: expected absent or SHA-256 and mode')
            digest, mode = state['sha256'], state['mode']
            if not (isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{64}', digest)
                    and isinstance(mode, str) and re.fullmatch(r'[0-7]{4}', mode)):
                raise ProofError(f'prior row {index}: invalid SHA-256 or four-digit octal mode')
            expected = digest.lower(), int(mode, 8)
        rows.append((backup, target, expected))
    if any(path[:size] in paths for path in paths for size in range(1, len(path))):
        raise ProofError('roster file paths overlap')
    return rows


def check_row(phase, path, expected):
    if expected is None:
        if read_evidence(path) is not None:
            raise ProofError('expected absence, but an entry exists')
        return
    observed = read_evidence(path, lambda stream: hashlib.file_digest(stream, 'sha256').hexdigest())
    if observed is None:
        raise ProofError('expected file is missing')
    digest, mode = observed
    if digest != expected[0]:
        raise ProofError('prior SHA-256 mismatch')
    if phase == 'post' and mode != expected[1]:
        raise ProofError('prior mode mismatch')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('phase', choices=('pre', 'post'))
    parser.add_argument('--roster', required=True, help='approved roster JSON file')
    parser.add_argument('--prior', required=True, help='prior-state manifest JSON file')
    args = parser.parse_args(argv)
    try:
        rows = validated_rows(load_document(args.roster, 'roster'), load_document(args.prior, 'prior'))
    except ProofError as exc:
        print(f'FAIL {args.phase}: {exc}')
        return 1

    failed = False
    for index, (backup, target, expected) in enumerate(rows, 1):
        try:
            check_row(args.phase, backup if args.phase == 'pre' else target, expected)
        except ProofError as exc:
            failed = True
            print(f'FAIL {args.phase} roster row {index}: {exc}')
    if failed:
        return 1
    kind = 'backup' if args.phase == 'pre' else 'restored target'
    print(f'PASS {args.phase}: {kind} evidence matches prior state for all {len(rows)} roster rows')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
