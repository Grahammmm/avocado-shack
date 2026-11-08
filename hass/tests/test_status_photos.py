"""NB-AV-12 (H17) tests: `status` counts photo drafts waiting for details and inbox messages still downloading.

PhotoDraftTests harness (temp Git repo + writer worktree, private media root, fake photo source, fixture
interpreter). Inbox files are temp SQLite databases with placeholder rows only. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_status_photos -v
"""

import contextlib
import json
import sqlite3
import unittest
from datetime import timedelta

from hass.tests import test_photo_draft as photo_draft
from hass.tests.test_conversation import T0
from hass.tests.test_photo_draft import ANSWER, PNG

INBOUND = ("CREATE TABLE inbound(provider_id TEXT PRIMARY KEY, received_at TEXT NOT NULL, payload TEXT, state TEXT"
           " NOT NULL, disposition TEXT, enqueued_at TEXT NOT NULL, done_at TEXT{})")
DRAFT = "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)"
SET_PHOTO = {"op": "product.set_photo", "args": {"photo": "0" * 64}}


class Harness(photo_draft.PhotoDraftTests):  # setUp/say/replies/drafts only; its tests run in their own module
    pass


for _name in [n for n in vars(photo_draft.PhotoDraftTests) if n.startswith("test_")]:
    setattr(Harness, _name, None)


class StatusPhotoTests(Harness):
    def status(self):
        self.assertEqual(self.say("status"), "status")
        [reply] = self.replies()
        return reply.splitlines()

    def inbox(self, rows=(), tries=True):
        path = self.repo.state / "inbox.sqlite3"
        with contextlib.closing(sqlite3.connect(path)) as db:
            db.execute(INBOUND.format(", tries INTEGER NOT NULL DEFAULT 0" if tries else ""))
            for i, (state, n) in enumerate(rows):
                db.execute("INSERT INTO inbound(provider_id, received_at, state, enqueued_at" + (", tries" if tries else "")
                           + ") VALUES (?, ?, ?, ?" + (", ?" if tries else "") + ")",
                           (f"i{i}", T0.isoformat(), state, T0.isoformat()) + ((n,) if tries else ()))
            db.commit()
        return path

    def insert(self, code, ops_json, expires=T0 + timedelta(hours=1)):
        self.conv.db.execute(DRAFT, (code, "needs-details", ops_json, "Which product?", "owner", "chat",
                                     T0.isoformat(), expires.isoformat()))

    def photo_line(self, lines):
        return [line for line in lines if "waiting for details from you" in line]

    def download_line(self, lines):
        return [line for line in lines if "still coming in" in line]

    def test_counts_only_waiting_photo_drafts(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.photos.data = PNG
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        self.insert("TXT1", json.dumps([{"op": "product.update", "args": {"id": "x"}}]))  # text question
        self.insert("MIX1", json.dumps([SET_PHOTO, {"op": "product.update", "args": {}}]))  # not photo-only
        self.insert("BAD1", "{not json")  # unparsable: not counted
        self.insert("NUL1", "[]")  # no ops: not counted
        self.insert("OLD1", json.dumps([SET_PHOTO]), expires=T0 - timedelta(minutes=1))  # lapsed: not listed
        lines = self.status()
        self.assertEqual(self.photo_line(lines), ["Some photos are waiting for details from you."])
        self.assertEqual(self.download_line(lines), [])  # no inbox file
        photo_codes = [d["code"] for d in self.drafts() if d["summary"] != "Which product?"]
        for code in photo_codes:  # the per-draft line stays
            self.assertIn("I'm waiting for details: " + next(d["summary"] for d in self.drafts() if d["code"] == code), lines)
        at = lines.index("Some photos are waiting for details from you.")
        self.assertTrue(all(not line.startswith("Last change:") for line in lines[:at]))
        self.assertTrue(all(i < at for i, line in enumerate(lines) if line.startswith("I'm waiting for details: ")))  # right after the draft lines

    def test_filled_photo_draft_is_no_longer_counted(self):
        self.say(attachments=1)
        self.replies()
        self.assertEqual(self.photo_line(self.status()), ["A photo is waiting for details from you."])
        self.assertEqual(self.say(ANSWER), "proposed")
        self.replies()
        self.assertEqual(self.photo_line(self.status()), [])

    def test_counts_pending_inbox_rows_with_tries(self):
        path = self.inbox([("pending", 1), ("pending", 0), ("done", 3)])  # a done row with tries is not counted
        before = path.read_bytes()
        lines = self.status()
        self.assertEqual(self.download_line(lines), ["A photo is still coming in."])
        self.assertEqual(self.photo_line(lines), [])
        self.assertEqual(path.read_bytes(), before)

    def test_no_inbox_file_or_no_tries_column_gives_no_line(self):
        path = self.repo.state / "inbox.sqlite3"
        self.assertEqual(self.download_line(self.status()), [])
        self.assertFalse(path.exists())  # status never creates the inbox
        self.inbox([("pending", 1)], tries=False)
        self.assertEqual(self.download_line(self.status()), [])
        path.unlink()
        self.inbox([("pending", 0), ("done", 1)])  # nothing pending is downloading
        self.assertEqual(self.download_line(self.status()), [])

    def test_corrupt_or_locked_inbox_is_unavailable_and_status_still_replies(self):
        path = self.repo.state / "inbox.sqlite3"
        path.write_bytes(b"not a database, just garbage bytes" * 64)
        lines = self.status()
        self.assertEqual(self.download_line(lines), ["I can't tell whether any photos are still coming in."])
        self.assertEqual(lines[0], "Everything is ready.")
        self.assertEqual(path.read_bytes(), b"not a database, just garbage bytes" * 64)
        path.unlink()
        self.inbox([("pending", 1)])
        with contextlib.closing(sqlite3.connect(path, isolation_level=None)) as lock:
            lock.execute("BEGIN EXCLUSIVE")
            self.assertEqual(self.download_line(self.status()), ["I can't tell whether any photos are still coming in."])
            lock.execute("ROLLBACK")
        self.assertEqual(self.download_line(self.status()), ["A photo is still coming in."])

    def test_status_is_read_only(self):
        self.say(attachments=1)
        self.replies()
        self.insert("OLD1", json.dumps([SET_PHOTO]), expires=T0 - timedelta(minutes=1))
        path = self.inbox([("pending", 1), ("pending", 0)])
        drafts, inbox = self.drafts(), path.read_bytes()
        with contextlib.closing(sqlite3.connect(path)) as db:
            dump = list(db.iterdump())
        self.status()
        self.assertEqual(self.drafts(), drafts)  # nothing expired, filled or moved
        self.assertEqual([d["state"] for d in drafts], ["needs-details", "needs-details"])
        self.assertEqual(path.read_bytes(), inbox)
        with contextlib.closing(sqlite3.connect(path)) as db:
            self.assertEqual(list(db.iterdump()), dump)


if __name__ == "__main__":
    unittest.main()
