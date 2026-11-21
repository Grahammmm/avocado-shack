#!/usr/bin/env python3
"""Check a checkpointed state DB copy against a private transcript JSONL export."""

import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import stat
import sys


class BadInput(Exception):
    """A fixed diagnostic label, never an input value."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default diagnostic can echo paths, job IDs and stray values.
        self.print_usage(sys.stderr)
        self.exit(2, 'npp_transcript_check: invalid arguments\n')


def input_file(name):
    supplied = Path(name).absolute()
    resolved = supplied.resolve(strict=True)
    # A linked Git worktree has a .git file, not a .git directory. Check both
    # paths so a link into or out of a worktree does not bypass the refusal.
    if any((parent / '.git').exists() or (parent / '.git').is_symlink()
           for path in (supplied, resolved) for parent in path.parents):
        raise BadInput('git-worktree')
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise ValueError
    return resolved


def state_rows(path, selected_job):
    # A regular read-only WAL open may create -shm. Immutable mode prevents
    # that, but must not silently ignore changes in a journal or WAL file.
    for suffix in ('-wal', '-journal'):
        try:
            if path.with_name(path.name + suffix).stat().st_size:
                raise BadInput('state-db-needs-checkpoint')
        except FileNotFoundError:
            pass
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA temp_store=MEMORY')
        where, params = (' WHERE job_id = ?', (selected_job,)) if selected_job is not None else ('', ())
        jobs = {jid for jid, in db.execute('SELECT job_id FROM npp_jobs' + where, params)}
        if not all(isinstance(jid, str) and re.fullmatch(r'[A-Za-z0-9_-]+', jid) for jid in jobs):
            raise BadInput('state-db')
        # Turns have no stored ordinal. Number them in insertion order, as
        # Jobs does when it uses rowid to find the latest turn in a segment.
        turns = db.execute('SELECT job_id, provider_id FROM npp_turns' + where + ' ORDER BY rowid', params).fetchall()
        delivered = db.execute('SELECT job_id, n, card_png_sha FROM npp_versions' + where
                               + (' AND' if where else ' WHERE') + ' delivered_at IS NOT NULL', params).fetchall()
    return jobs, turns, delivered


def reject_constant(_value):
    raise ValueError


def transcript_index(path):
    inbound, outbound = Counter(), set()
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            event = json.loads(line, parse_constant=reject_constant)
            if not isinstance(event, dict):
                raise ValueError
            direction, provider_id, attachments = event['direction'], event['provider_id'], event['attachments']
            if (direction not in ('in', 'out')
                    or (provider_id is not None and not isinstance(provider_id, str))
                    or not isinstance(attachments, list)
                    or not all(isinstance(sha, str) for sha in attachments)):
                raise ValueError
            if direction == 'in' and provider_id is not None:
                inbound[provider_id] += 1
            elif direction == 'out':
                outbound.update(attachments)
    return inbound, outbound


def findings(jobs, turns, delivered, inbound, outbound):
    ordinals = Counter()
    for jid, provider_id in turns:
        if jid not in jobs:
            raise BadInput('state-db')
        ordinals[jid] += 1
        count = inbound[provider_id]
        if count != 1:
            kind = 'duplicate-inbound' if count else 'missing-inbound'
            yield f'FAIL {kind} {jid} {ordinals[jid]}'
    for jid, version, sha in delivered:
        if jid not in jobs or type(version) is not int:
            raise BadInput('state-db')
        if sha not in outbound:
            yield f'FAIL missing-card {jid} {version}'


def main(argv=None):
    parser = PrivateParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--state-db', required=True, metavar='FILE')
    parser.add_argument('--export', required=True, metavar='FILE')
    parser.add_argument('--job', metavar='ID')
    args = parser.parse_args(argv)
    source = 'state-db'
    try:
        db_path = input_file(args.state_db)
        jobs, turns, delivered = state_rows(db_path, args.job)
        if args.job is not None and not jobs:
            print('FAIL no-job')
            return 1
        source = 'export'
        inbound, outbound = transcript_index(input_file(args.export))
        lines = sorted(findings(jobs, turns, delivered, inbound, outbound))
    except BadInput as exc:
        print(f'FAIL bad-input {exc}')
        return 1
    except (OSError, ValueError, RuntimeError, KeyError, sqlite3.Error):
        print(f'FAIL bad-input {source}')
        return 1
    if lines:
        print(*lines, 'FAIL npp_transcript_check', sep='\n')
        return 1
    print(f'PASS npp_transcript_check {len(jobs)} jobs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
