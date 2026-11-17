"""H09 demo: one fixture transcript through hass/fixture_chat.py, from request to undo, checked end to end.
The behaviours are unit-tested elsewhere (test_conversation, test_undo); this runs the CLI on conversation-demo.jsonl
in a throwaway writer repo (test_editor.WriterRepo) and checks the reply kinds.
Run: python3 -B -m unittest hass.tests.test_demo_transcript -v
"""

import json
import sqlite3
import subprocess
import sys
import unittest

from hass import conversation, editor
from hass.content_model import REPO_ROOT, load_and_validate
from hass.tests.test_conversation import CHAT, SETTINGS
from hass.tests.test_editor import WriterRepo

FIXTURES = REPO_ROOT / "hass" / "tests" / "fixtures"
DEMO, MAPPING = FIXTURES / "conversation-demo.jsonl", FIXTURES / "conversation-demo-interpreter.json"
KINDS = ("Here's the change I'd make:", "Saved:", "Here's what we changed lately:", "To undo that, I'd change it back:", conversation.NOTHING)
EXPECTED = ["Here's the change I'd make:", "Saved:", "Here's what we changed lately:", "To undo that, I'd change it back:", "Saved:", conversation.NOTHING]
PID = "photo-product-001"


def _description(state):
    wt = editor._load(str(state))[2]
    content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
    return next(p for p in content.products if p["id"] == PID)["description"]


class DemoTranscriptTests(unittest.TestCase):
    def fresh(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": SETTINGS})
        return repo

    def run_cli(self, state, interpreter=MAPPING):
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state", str(state),
                               "--fixture", str(DEMO), "--interpreter", str(interpreter)],
                              capture_output=True, text=True, cwd=REPO_ROOT)

    def transcript(self, repo):
        run = self.run_cli(repo.state)
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        rows = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual({(r["chat"], tuple(r["attachments"])) for r in rows}, {(CHAT, ())})
        return [r["text"] for r in rows]

    def kinds(self, texts):
        return [next((k for k in KINDS if t.startswith(k)), t) for t in texts]

    def db(self, repo):
        db = sqlite3.connect(repo.state / "conversation.sqlite3")
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        return db

    def test_demo_round_trip(self):
        repo = self.fresh()
        original = _description(repo.state)
        texts = self.transcript(repo)
        self.assertEqual(self.kinds(texts), EXPECTED)
        db = self.db(repo)
        edit, undo = db.execute("SELECT * FROM drafts ORDER BY row_id").fetchall()  # duplicate: no second draft
        self.assertIn("Hass avocado, the description:", texts[0])
        self.assertTrue(texts[1].startswith("Saved: the description for Hass avocado"))
        self.assertIn("the description for Hass avocado, approved Mon Nov 2 9:01 am: saved", texts[2])
        self.assertTrue(texts[3].startswith("To undo that, I'd change it back:\nHere's the change I'd make:"))
        self.assertTrue(texts[4].startswith("Saved: the description for Hass avocado"))
        self.assertEqual(texts[5], conversation.NOTHING)  # final bare yes: exactly one reply
        self.assertEqual(json.loads(undo["ops_json"])[0]["op"], "history.revert")
        self.assertIn(undo["state"], ("applied", "verified"))
        self.assertEqual(edit["state"], "reverted")
        self.assertEqual(_description(repo.state), original)
        messages = {r["provider_id"]: (r["disposition"], r["received_at"]) for r in db.execute("SELECT * FROM messages")}
        self.assertEqual(len(messages), 7)  # the redelivered demo-1 added no record and left its first one alone
        self.assertEqual(messages["demo-1"][0], "proposed")
        self.assertEqual(messages["demo-6"], ("ignored", None))  # stranger's undo: non-owner, no draft, no reply

    def test_two_fresh_runs_give_the_same_reply_kinds(self):
        self.assertEqual(self.kinds(self.transcript(self.fresh())), self.kinds(self.transcript(self.fresh())))

    def test_missing_interpreter_file_exits_2(self):
        repo = self.fresh()
        run = self.run_cli(repo.state, repo.state.parent / "missing-interpreter.json")
        self.assertEqual((run.returncode, run.stdout), (2, ""))
        self.assertIn("fixture_chat:", run.stderr)
