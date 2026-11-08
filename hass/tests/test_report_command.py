"""AV1322-05 (F04): the whole message `report` (or `morning report`) replies the morning shelf report rendered from the
writer worktree content for the Pacific date of the message; read-only (no interpreter, editor, draft, expiry or
control row), works while paused. Run: python3 -B -m unittest hass.tests.test_report_command -v
"""

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from hass import conversation, morning_report
from hass.content_model import load_content
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS
from hass.tests.test_status_pause import StoreMixin

NOTHING_WAITING = "\n\nNothing is waiting for you."  # AV1102-11: the block every report now ends with
UNAVAILABLE = "I can't read the shelf report right now, so I can't tell you what's on the shelves. Nothing has changed." + NOTHING_WAITING


class ReportParseTests(unittest.TestCase):
    def test_report_wordings_and_lookalikes(self):
        for text in ("report", "Report.", "morning report!", " MORNING REPORT ", "report.!"):
            self.assertEqual(conversation.parse_command(text), ("report", None), text)
        for text in ("report now", "reports", "morning reports", "morning", "please report", "report a1b2",
                     "morning  report", "report\nnow"):
            self.assertIsNone(verb(text), text)


class ReportTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        # 7 days before T0's Pacific date (not stale) but 8 before the UTC date (stale): the date used shows
        self.edit("store.json", lambda doc: doc.update(selection_checked_on="2026-10-26"))

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")

    def expected(self, day):
        content = load_content(self.repo.wt / "hass" / "content")
        return morning_report.render(morning_report.facts(content, day)) + NOTHING_WAITING

    def report(self, text="report"):
        self.assertEqual(self.say(text), "report")
        self.assertEqual(self.disposition(f"m{self.n}"), "report")
        [reply] = self.replies()
        return reply

    def test_report_wordings_reply_the_rendered_report_and_change_nothing(self):
        want = self.expected(date(2026, 11, 2))
        self.assertTrue(want.startswith("Your last shelf check was Monday, October 26.\n"), want)
        for text in ("report", "Report.", "morning report!"):
            with self.subTest(text=text):
                self.assertEqual(self.report(text), want)
        self.assertEqual((self.calls, self.drafts(), self.commits(), self.approvals()), ([], [], 0, 0))
        self.assertNotIn("control", self.tables())

    def test_lookalikes_go_to_the_normal_request_path(self):
        for text in ("report now", "reports"):
            with self.subTest(text=text):
                self.interp.mapping[text] = _ops((HOURS, {"hours": NEW_HOURS}))
                self.assertEqual(self.say(text), "proposed")
                self.assertNotIn("Shelf check", "\n".join(self.replies()))
        self.assertIn("interpret", self.calls)

    def test_report_while_paused_and_with_a_lapsed_proposal(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.calls.clear()
        control = [dict(r) for r in self.conv.db.execute("SELECT * FROM control")]
        self.now = T0 + timedelta(seconds=601)  # lapsed; no other message has swept it yet
        before = self.drafts()
        reply = self.report()
        self.assertEqual(reply, self.expected(date(2026, 11, 2)))
        self.assertNotIn("paused", reply.lower())
        self.assertEqual((self.drafts(), self.calls, self.approvals(), self.commits()), (before, [], 0, 0))
        self.assertEqual([dict(r) for r in self.conv.db.execute("SELECT * FROM control")], control)
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it

    def test_missing_writer_worktree_gives_the_fixed_line(self):
        moved = self.repo.wt.with_name(self.repo.wt.name + "-moved")
        self.repo.wt.rename(moved)
        self.addCleanup(moved.rename, self.repo.wt)
        reply = self.report()
        self.assertEqual(reply, UNAVAILABLE)  # fixed words: no traceback, no path
        self.assertEqual((self.drafts(), self.calls), ([], []))

    def test_unreadable_content_gives_the_fixed_line(self):
        path = self.repo.wt / "hass" / "content" / "products.json"
        good = path.read_text("utf-8")
        path.write_text("{not json", "utf-8")
        self.assertEqual(self.report(), UNAVAILABLE)
        path.write_text(good, "utf-8")
        self.edit("products.json", lambda doc: doc["products"][0].update(name="Two\nlines"))  # fails validation
        self.assertEqual(self.report("morning report"), UNAVAILABLE)
        self.assertEqual(self.drafts(), [])

    def test_product_record_the_report_cannot_read_gives_the_fixed_line(self):
        err = ValueError("products.json product 3: name is empty")
        with mock.patch.object(morning_report, "_products", side_effect=err) as products:
            self.assertEqual(self.report(), UNAVAILABLE)
        self.assertEqual(products.call_count, 1)

    def test_message_time_uses_the_pacific_date_not_utc(self):
        self.now = datetime(2026, 11, 3, 7, 30, tzinfo=timezone.utc)  # 2026-11-02 23:30 PST
        pacific, utc = self.expected(date(2026, 11, 2)), self.expected(date(2026, 11, 3))
        self.assertNotEqual(pacific, utc)
        self.assertTrue(utc.startswith("Your last shelf check was Monday, October 26. That was more than a week ago"), utc)
        self.assertEqual(self.report(), pacific)


if __name__ == "__main__":
    unittest.main()
