#!/usr/bin/env python3
"""List inbound metadata as JSON lines, followed by counts. Never reads payloads."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys


STATES = ("pending", "done", "history")
# Inbox.drain writes 'unreadable' or a disposition returned by Receiver/Conversation.
# Permit fixed producer codes only; neither free text nor an open-ended prefix is safe.
DISPOSITIONS = frozenset("""
    unreadable duplicate approval-held approved rejected cancelled paused env-changed
    echo edited-ignored ignored not-read near-control near-approval no-target social command-typo
    npp-working npp-expired npp-unavailable answer question needs-details claim-question
    proposed not-drafted unsupported refused lookup offer-no shelf-no undo-other
    writer-busy too-long reader-failed daily-limit
    attachment-unsupported attachment-many attachment-failed photo-duplicate photo-on-product
    photo-draft photo-drafts photo-question photo-many-ops photo-mismatch
    status pause resume help history find show report post margin hidden listing photos shelf costs held again
    g-problems g-weekly g-till-report backlog backlog-forgot backlog-none
    memory-list memory-none memory-forgot memory-saved memory-updated memory-unchanged memory-invalid memory-ambiguous
    till-write-refused till-draft till-approved till-cancelled till-undo till-read
    photo-refused:empty photo-refused:too-large photo-refused:unsupported-type photo-refused:truncated
    photo-refused:corrupt-store photo-refused:unreadable photo-refused:needs-rotation photo-refused:audio
""".split())


def instant(value):
    if isinstance(value, str):
        try:
            time = datetime.fromisoformat(value)
            if time.tzinfo is not None:
                return time.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            pass
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox-db", required=True, type=Path, help="SQLite inbox path (read-only)")
    parser.add_argument("--since", required=True, help="inclusive start, ISO-8601 with a timezone")
    parser.add_argument("--until", required=True, help="inclusive end, ISO-8601 with a timezone")
    args = parser.parse_args(argv)
    since, until = instant(args.since), instant(args.until)
    if since is None or until is None or since > until:
        parser.error("expected an ordered window of timezone-aware ISO-8601 timestamps")

    counts: dict[str, int] = dict.fromkeys(STATES, 0)
    try:
        uri = args.inbox_db.absolute().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            rows = db.execute("SELECT provider_id, received_at, state, disposition, done_at "
                              "FROM inbound ORDER BY received_at, provider_id")
            for provider_id, received_at, state, disposition, done_at in rows:
                received = instant(received_at)
                # An unplaceable row is surfaced, not silently excluded from the receipt.
                if received is not None and not since <= received <= until:
                    continue
                state = state if state in STATES else "other"
                counts[state] = counts.get(state, 0) + 1
                print(json.dumps({
                    "provider_id": sha256(provider_id.encode("utf-8")).hexdigest()[:12],
                    "received_at": received_at if received is not None else "bad-time",
                    "state": state,
                    "disposition": disposition if disposition in DISPOSITIONS else "other",
                    "done_at": done_at if done_at is None or instant(done_at) is not None else "bad-time",
                }))
    except sqlite3.Error:
        print("error: could not read inbox store", file=sys.stderr)
        return 2
    print(json.dumps({"counts": counts}))
    # An unplaceable pending row cannot be cleared as outside the window.
    return int(counts["pending"] != 0)


if __name__ == "__main__":
    sys.exit(main())
