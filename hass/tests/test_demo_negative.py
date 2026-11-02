"""H09 negative demo: one fixture transcript through hass/fixture_chat.py in which nothing may reach the site.
A stranger, an owner `no`, a redelivered message id, a `yes` after the approval window and an unclear request each end
with no approval and no site write; the writer worktree is byte-identical after the whole run.
fixture_chat.py reads the real clock, so main() runs in-process with a clock that is each row's own `at` (the gaps
between rows are the elapsed time) and with Editor.apply armed to fail. fixture_chat.py itself is untouched.
Run: python3 -B -m unittest hass.tests.test_demo_negative -v
"""

import contextlib
import hashlib
import io
import json
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest import mock

from hass import conversation, editor, fixture_chat
from hass.content_model import REPO_ROOT
from hass.tests.test_conversation import CHAT, SETTINGS
from hass.tests.test_editor import WriterRepo

FIXTURES = REPO_ROOT / "hass" / "tests" / "fixtures"
TRANSCRIPT, MAPPING = FIXTURES / "conversation-demo-negative.jsonl", FIXTURES / "conversation-demo-negative-interpreter.json"
DISPOSITIONS = ["ignored", "proposed", "rejected", "duplicate", "proposed", "no-target", "question", "status"]
KINDS = ["Draft ", "Cancelled ", "Draft ", "expired at ", "Which product", "Changes: on"]
ASK = "Which product or maker should I change, and what should it say?"


class Clock(datetime):
    current = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.current


class ClockedConversation(conversation.Conversation):
    handled = []

    def handle(self, msg, *args, **kwargs):
        Clock.current = Clock.fromisoformat(msg.received_at)  # the clock moves to the row's own time
        self.handled.append(disposition := super().handle(msg, *args, **kwargs))
        return disposition


def _tree(root):  # every file of the writer worktree, by relative path and content hash
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.relative_to(root).parts}


class NegativeDemoTests(unittest.TestCase):
    def run_demo(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": SETTINGS})
        wt = editor._load(str(repo.state))[2]
        before, head = _tree(wt), repo.head()
        ClockedConversation.handled = []
        out = io.StringIO()
        with mock.patch.object(fixture_chat, "datetime", Clock), \
                mock.patch.object(fixture_chat, "Conversation", ClockedConversation), \
                mock.patch.object(conversation.Editor, "apply", side_effect=AssertionError("editor.apply called")) as apply, \
                contextlib.redirect_stdout(out):
            code = fixture_chat.main(["--state", str(repo.state), "--fixture", str(TRANSCRIPT), "--interpreter", str(MAPPING)])
        rows = [json.loads(line) for line in out.getvalue().splitlines()]
        db = sqlite3.connect(repo.state / "conversation.sqlite3")
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        return dict(code=code, rows=rows, db=db, apply=apply, handled=list(ClockedConversation.handled),
                    unchanged=(_tree(wt) == before and repo.head() == head and repo.status() == ""))

    def test_every_negative_row_ends_with_no_site_write(self):
        run = self.run_demo()
        self.assertEqual(run["code"], 0)
        self.assertEqual(run["handled"], DISPOSITIONS)
        self.assertEqual(run["apply"].call_count, 0)  # the editor never applied anything
        self.assertEqual(run["db"].execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)
        self.assertTrue(run["unchanged"])  # no file, no commit, nothing staged or modified in the worktree
        stored = [tuple(r) for r in run["db"].execute("SELECT provider_id, disposition FROM messages ORDER BY rowid")]
        self.assertEqual(stored, [("neg-1", "ignored"), ("neg-2", "proposed"), ("neg-3", "rejected"),
                                  ("neg-4", "proposed"), ("neg-5", "no-target"), ("neg-6", "question"),
                                  ("neg-7", "status")])  # the redelivered neg-3 added no record
        self.assertIsNone(run["db"].execute("SELECT received_at FROM messages WHERE provider_id = 'neg-1'").fetchone()[0])

    def test_replies_and_draft_states(self):
        run = self.run_demo()
        texts = [r["text"] for r in run["rows"]]
        self.assertEqual({(r["chat"], tuple(r["attachments"])) for r in run["rows"]}, {(CHAT, ())})
        self.assertEqual(len(texts), len(KINDS))  # no reply to the stranger, none to the redelivered `no`
        for text, kind in zip(texts, KINDS):
            self.assertTrue(text.startswith(kind) or kind in text, (kind, text))
        a, b = run["db"].execute("SELECT * FROM drafts ORDER BY row_id").fetchall()  # the unclear request opened no draft
        self.assertEqual((a["state"], a["reason"], b["state"]), ("rejected", "owner", "expired"))
        # fixture_chat flushes once, after the last row (09:32): a reply written over DELAYED_AFTER_S earlier carries
        # the AVB-07 (H16) send-time prefix; the 09:02 cancel is one, the 09:30 expiry reply onwards are not
        self.assertEqual(texts[1],
                         f"(Delayed reply, written 2026-11-02 09:02 PST) Cancelled {a['code']}; nothing changed.")
        self.assertEqual(texts[3], f"{b['code']} expired at 2026-11-02 09:14 PST; nothing changed.")  # 09:04 + 600 s
        self.assertEqual(texts[4], ASK)
        self.assertNotIn(b["code"], "".join(texts[4:]))  # the question and status name no draft code
        self.assertIn(conversation.NOTHING, texts[5])  # status: nothing pending, no last change
        self.assertNotIn("Last change", texts[5])

    def test_two_fresh_runs_give_the_same_replies_and_dispositions(self):
        first, second = self.run_demo(), self.run_demo()
        self.assertEqual(first["handled"], second["handled"])
        kinds = lambda run: [next((k for k in KINDS if k in r["text"]), r["text"]) for r in run["rows"]]  # noqa: E731
        self.assertEqual(kinds(first), kinds(second))
        self.assertEqual((first["unchanged"], second["unchanged"]), (True, True))
