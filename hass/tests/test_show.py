"""AV0022-08 (H17): `show <code>` repeats a waiting or applied draft's stored proposal lines and saved screenshot.
Read-only: no state move, no expiry sweep, no approval row, nothing prepared or rendered again; works while paused.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import conversation
from hass.tests.test_conversation import CHAT, OWNER, T0, ConversationTestCase
from hass.tests.test_undo import H06TestCase

USAGE = "Send show and a draft code, e.g. show a1b2."


class ShowTestMixin:
    def state(self):
        db = self.conv.db
        return (self.drafts(), db.execute("SELECT * FROM approvals").fetchall(), self.commits(),
                getattr(self.editor, "applies", None))

    def show(self, text):
        self.assertEqual(self.say(text), "show")
        [reply] = self.sent()
        return reply["text"], reply["attachments"]


class ShowPreviewTests(ShowTestMixin, H06TestCase):
    def test_waiting_draft_repeats_the_proposal_and_its_screenshot(self):
        draft, _ = self.propose("hours")
        [original] = self.conv.db.execute("SELECT * FROM outbox ORDER BY id").fetchall()  # the proposal as sent
        self.assertEqual(self.say("desc"), "proposed")
        self.assertEqual(self.say("status"), "status")
        self.sent()
        before = self.state()
        targets = len(self.previewer.targets)
        text, shots = self.show(f"Show {draft['code'].upper()}.")
        code = draft["code"]
        self.assertEqual(text, f"Draft {code} (waiting):" + original["text"][len(f"Draft {code}:"):])
        png = self.repo.state / "screenshots" / f"{draft['change_id']}-proposal.png"
        self.assertEqual((shots, conversation.json.loads(original["attachments"])), ([str(png)], [str(png)]))
        self.assertEqual((self.state(), len(self.previewer.targets)), (before, targets))  # nothing rendered again
        self.assertEqual((self.drafts()[0]["state"], self.drafts()[0]["expires_at"]), ("proposed", draft["expires_at"]))

    def test_verified_draft_shows_commit_lines_and_result_screenshot(self):
        row = self.apply("hours")
        self.assertEqual(row["state"], "verified")
        draft = conversation.editor_mod.show(row["change_id"], state=str(self.repo.state))["change"]
        text, shots = self.show(f"show {row['code']}")
        lines = conversation._record_lines(draft)
        self.assertEqual(text, "\n".join([f"Applied {row['code']} ({row['commit'][:7]}):"] + lines))
        self.assertNotIn("Expires", text)
        self.assertNotIn("Reply yes", text)
        self.assertEqual(shots, [row["screenshot"]])
        Path(row["screenshot"]).unlink()  # a missing PNG file: text only
        self.assertEqual(self.show(f"show {row['code']}"), (text, []))

    def test_details_not_available_never_re_prepares_or_renders(self):
        draft, _ = self.propose("hours")
        before, targets = self.state(), len(self.previewer.targets)
        for out in ({"result": "not-found", "key": draft["change_id"]}, {"result": "ok", "draft": {"records": "x"}},
                    {"result": "ok", "draft": {}}, None):
            with self.subTest(out=out), mock.patch.object(self.editor, "show", return_value=out), \
                    mock.patch.object(self.editor, "prepare", side_effect=AssertionError("prepared")), \
                    mock.patch.object(self.editor, "render_draft", side_effect=AssertionError("rendered")):
                self.assertEqual(self.show(f"show {draft['code']}"),
                                 ("I can't find the details of that change any more.", []))
        self.assertEqual((self.state(), len(self.previewer.targets)), (before, targets))


class ShowTests(ShowTestMixin, ConversationTestCase):
    def sent(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return self.out.sent[before:]

    def test_applied_without_previewer_is_text_only(self):
        draft, _ = self.propose("hours")
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        row = self.drafts()[0]
        text, shots = self.show(f"show {row['code']}")
        self.assertTrue(text.startswith(f"Applied {row['code']} ({row['commit'][:7]}):\nstore store: hours"), text)
        self.assertEqual(shots, [])

    def test_waiting_draft_without_screenshot_is_text_only(self):
        draft, reply = self.propose("hours")
        self.assertEqual(self.show(f"show {draft['code']}"),
                         (f"Draft {draft['code']} (waiting):" + reply[len(f"Draft {draft['code']}:"):], []))

    def test_lapsed_draft_is_worded_expired_and_show_sweeps_nothing(self):
        draft, _ = self.propose("hours")
        self.now = T0 + timedelta(seconds=601)
        before = self.state()
        expired = f"{draft['code']} expired at 2026-11-02 09:10 PST; nothing changed."
        self.assertEqual(self.show(f"show {draft['code']}"), (expired, []))
        self.assertEqual(self.state(), before)
        self.assertEqual(self.drafts()[0]["state"], "proposed")  # still proposed after show
        self.assertEqual(self.say("no"), "no-target")  # the next ordinary message sweeps it
        self.sent()
        self.assertEqual(self.drafts()[0]["state"], "expired")
        self.assertEqual(self.show(f"show {draft['code']}"), (expired, []))

    def test_cancelled_and_needs_details_states(self):
        draft, _ = self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.sent()
        self.assertEqual(self.show(f"show {draft['code']}"),
                         ("That one was cancelled, so nothing changed.", []))
        self.conv.db.execute("INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at)"
                             " VALUES ('beef', 'needs-details', '[]', 'Which day?', ?, ?, ?, ?)",
                             (OWNER, CHAT, T0.isoformat(), (T0 + timedelta(hours=1)).isoformat()))
        self.assertEqual(self.show("show beef"), ("I'm waiting for details: Which day?", []))

    def test_usage_and_unknown_code(self):
        for text in ("show", "Show!", "show zz", "show 123", "show me the avocado page", "show a1b2c3d4e5f6a"):
            with self.subTest(text=text):
                self.assertEqual(self.show(text), (USAGE, []))
        self.assertEqual(self.show("show abcd"), ("I don't have a change with that code.", []))
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_while_paused_same_reply_and_no_approval_row(self):
        draft, _ = self.propose("hours")
        unpaused = self.show(f"show {draft['code']}")
        self.assertEqual(self.say("pause changes"), "pause")
        self.sent()
        before = self.state()
        self.assertEqual(self.show(f"show {draft['code']}"), unpaused)
        self.assertNotIn(conversation.PAUSED_LINE, unpaused[0])
        self.assertEqual(self.state(), before)
        self.assertEqual((self.drafts()[0]["state"], self.editor.applies), ("proposed", 0))

    def test_parse_tuples_and_attachment_is_a_photo(self):
        parse = conversation.parse_command
        self.assertEqual([parse(t) for t in ("find lion", "undo a1b2", "help", "status", "Show A1B2.", "show")],
                         [("find", "lion"), ("undo", "a1b2"), ("help", None), ("status", None), ("show", "a1b2"),
                          ("show", "")])
        self.assertIsNone(parse("showa1b2"))
        msg = conversation.Inbound("p1", CHAT, OWNER, "show a1b2", attachments=1, received_at=T0.isoformat())
        self.assertEqual(self.conv.handle(msg), "attachment-unsupported")
        self.assertEqual([r["text"] for r in self.sent()], [conversation.ATTACHMENT_REPLY])


if __name__ == "__main__":
    unittest.main()
