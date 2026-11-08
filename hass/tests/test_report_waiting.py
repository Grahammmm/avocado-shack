"""AV1102-11 (F04/H17): the `report` reply ends with a "Waiting for you" block (drafts waiting for yes or details, then
the count of photos waiting for details) read from the same rows through the same code as `status`; read-only, works
while paused, expired drafts left out, an unreadable inbox gives no downloading line.
Run: python3 -B -m unittest hass.tests.test_report_waiting -v
"""

import json
import unittest
from datetime import timedelta

from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

NOTHING_WAITING = "Nothing is waiting for you."
DRAFT = "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)"
SET_PHOTO = json.dumps([{"op": "product.set_photo", "args": {"photo": "0" * 64}}])
TEXT_ASK = json.dumps([{"op": "product.update", "args": {"id": "x"}}])
GARBAGE = b"not a database, just garbage bytes" * 64


class ReportWaitingTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        path = self.repo.wt / "hass" / "content" / "store.json"  # today's shelf check, so the report asks nothing more
        path.write_text(json.dumps({**json.loads(path.read_text("utf-8")), "selection_checked_on": "2026-11-02"}), "utf-8")

    def report(self):
        self.assertEqual(self.say("report"), "report")
        [reply] = self.replies()
        return reply

    def insert(self, code, ops_json, summary="Which product?", expires=T0 + timedelta(hours=1)):
        self.conv.db.execute(DRAFT, (code, "needs-details", ops_json, summary, "owner", "chat", T0.isoformat(),
                                     expires.isoformat()))

    def block(self, reply):
        head, _sep, tail = reply.partition("\n\n")
        self.assertTrue(_sep, reply)
        return tail.splitlines()

    def dump(self):
        skip = {"messages", "outbox"}  # the message log and the reply queue grow by design
        return {t: [tuple(r) for r in self.conv.db.execute(f"SELECT * FROM {t}")] for t in sorted(self.tables() - skip)}

    def test_report_lists_the_waiting_draft_and_photo_count_as_status_does(self):
        draft, _reply = self.propose("hours")
        self.insert("PHO1", SET_PHOTO, "Which product is this photo of?")
        self.insert("TXT1", TEXT_ASK, "Which maker?")
        lines = self.block(self.report())
        draft_line = f"Waiting for your yes: {draft['summary']} (reply yes {draft['code']})"
        self.assertEqual(lines[0], "Waiting for you:")
        self.assertTrue(lines[1].startswith(draft_line), lines)
        self.assertEqual(lines[2:], ["I'm waiting for details: Which product is this photo of?",
                                     "I'm waiting for details: Which maker?", "A photo is waiting for details from you."])
        status = self.status()
        self.assertTrue(set(lines[1:4]) <= set(status), (lines, status))  # the very same lines as status
        self.assertIn("A photo is waiting for details from you.", status)
        self.assertNotIn("Nothing is waiting for your yes.", status)

    def test_report_leaves_out_the_downloading_row_and_an_unreadable_inbox_is_no_error(self):
        self.insert("PHO1", SET_PHOTO)
        path = self.repo.state / "inbox.sqlite3"
        path.write_bytes(GARBAGE)
        reply = self.report()
        self.assertEqual(self.block(reply), ["Waiting for you:", "I'm waiting for details: Which product?",
                                             "A photo is waiting for details from you."])
        self.assertNotIn("downloading", reply)
        self.assertNotIn("unavailable", reply)
        self.assertIn("I can't tell whether any photos are still coming in.", "\n".join(self.status()))  # status keeps its row
        self.assertEqual(path.read_bytes(), GARBAGE)

    def test_nothing_waiting_says_so_and_status_keeps_its_own_line(self):
        self.assertEqual(self.block(self.report()), [NOTHING_WAITING])
        self.assertIn("Nothing is waiting for your yes.", self.status())

    def test_a_lapsed_draft_is_absent_from_report_and_status(self):
        draft, _reply = self.propose("hours")
        self.insert("OLD1", SET_PHOTO, expires=T0 - timedelta(minutes=1))
        self.now = T0 + timedelta(seconds=601)  # past the draft's 600 s; no other message has swept it
        reply = self.report()
        self.assertEqual(self.block(reply), [NOTHING_WAITING])
        status = "\n".join(self.status())
        for text in (reply, status):
            self.assertNotIn(draft["code"], text)
            self.assertNotIn("OLD1", text)
            self.assertNotIn("waiting for details from you.", text)
        self.assertIn("Nothing is waiting for your yes.", status)
        self.assertEqual(self.drafts()[0]["state"], "proposed")  # read-only: reading did not expire it

    def test_report_while_paused_shows_the_block_and_changes_nothing(self):
        draft, _reply = self.propose("hours")
        self.insert("PHO1", SET_PHOTO)
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        before, drafts = self.dump(), self.drafts()
        lines = self.block(self.report())
        self.assertTrue(lines[1].startswith(f"Waiting for your yes: {draft['summary']} (reply yes {draft['code']})"), lines)
        self.assertEqual(lines[-1], "A photo is waiting for details from you.")
        self.assertNotIn("paused", "\n".join(lines).lower())  # the paused state is status's to show
        self.assertEqual((self.dump(), self.drafts()), (before, drafts))
        self.assertEqual(self.approvals(), 0)
        self.assertEqual(self.commits(), 0)

    def test_the_block_also_follows_the_fixed_line_when_the_shelf_report_is_unavailable(self):
        self.insert("TXT1", TEXT_ASK, "Which maker?")
        moved = self.repo.wt.with_name(self.repo.wt.name + "-moved")
        self.repo.wt.rename(moved)
        self.addCleanup(moved.rename, self.repo.wt)
        self.assertEqual(self.report(), "I can't read the shelf report right now, so I can't tell you what's on the shelves. Nothing has changed.\n\nWaiting for you:\nI'm waiting for details: Which maker?")


if __name__ == "__main__":
    unittest.main()
