"""RF1058-11 (H21): routine tool output carries no sender, chat or message text. One fixture state holds made-up
canary strings; every routine CLI runs on it and none may echo a canary on stdout/stderr or in MANIFEST.json.
fixture_chat.py stdout is the owner's replies: the chat id may appear there (reply address), message text may not.
Run: python3 -B -m unittest hass.tests.test_output_hygiene -v
"""

import json
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from hass import editor
from hass.content_model import REPO_ROOT
from hass.tests.test_demo_transcript import MAPPING
from hass.tests.test_editor import WriterRepo

OWNER, CHAT, STRANGER = "+155****0777", "chat-canary-5150", "+155****0999"
OWNER_TEXT, STRANGER_TEXT, HISTORY_TEXT = "zebra-canary-7781", "quokka-canary-4242", "yak-canary-3131"
TEXTS = (OWNER_TEXT, STRANGER_TEXT, HISTORY_TEXT)
CANARIES = (OWNER, CHAT, STRANGER, *TEXTS)
SETTINGS = {"ownerSenders": [OWNER], "ownerChat": CHAT, "approvalTtlSeconds": 600}
START = "2026-11-02T08:30:00-08:00"
SORRY = "Sorry, I can't do that yet."
HEALTH_IDS = {"settings", "db-integrity", "outbox-stuck", "apply-stuck", "inbox-stuck", "inbox-integrity", "backup-age"}


def line(mid, sender, text, at="2026-11-02T09:00:00-08:00"):
    return {"id": mid, "chat": CHAT, "sender": sender, "text": text, "fromMe": False, "kind": "new", "at": at}


ROWS = [line("c-1", OWNER, OWNER_TEXT), line("c-2", STRANGER, STRANGER_TEXT, "2026-11-02T09:01:00-08:00")]
HISTORY = line("c-0", OWNER, HISTORY_TEXT, "2026-11-02T08:00:00-08:00")


def git_status():
    return subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=REPO_ROOT).stdout


class OutputHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.status_before = git_status()

    @classmethod
    def tearDownClass(cls):
        assert git_status() == cls.status_before, "test left the repository changed"

    def fresh(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        self.assertFalse(repo.state.resolve().is_relative_to(REPO_ROOT.resolve()))  # temp dirs outside the repo
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": SETTINGS})
        return repo

    def run_tool(self, tool, *args):
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / tool), *map(str, args)],
                              capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)

    def chat(self, repo, rows, *flags, fixture=None):
        if fixture is None:
            fixture = repo.state.parent / "fixture.jsonl"
            fixture.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        return self.run_tool("fixture_chat.py", "--state", repo.state, "--fixture", fixture, "--interpreter", MAPPING,
                             *flags)

    def assert_clean(self, run, code, canaries=CANARIES, stdout=True):
        self.assertEqual(run.returncode, code, run.stderr)
        for canary in canaries:
            self.assertNotIn(canary, run.stderr)
            if stdout: self.assertNotIn(canary, run.stdout)

    def assert_replies(self, run):
        """fixture_chat stdout: exactly one reply, to the owner chat, carrying no message text or sender."""
        self.assert_clean(run, 0, canaries=(OWNER, STRANGER, *TEXTS))
        self.assertEqual([json.loads(r) for r in run.stdout.splitlines()],
                         [{"chat": CHAT, "text": SORRY, "attachments": []}])  # none to the stranger's message

    def test_routine_outputs_carry_no_canary(self):
        repo = self.fresh()
        run = self.chat(repo, ROWS)
        self.assert_replies(run)
        self.assertEqual(run.stderr, "")
        health = self.run_tool("health.py", "--state", repo.state)
        self.assertIn(health.returncode, (0, 1))
        self.assert_clean(health, health.returncode)
        self.assertLessEqual({p["check"] for p in json.loads(health.stdout)["problems"]}, HEALTH_IDS)
        out = repo.state.parent / "backups"
        out.mkdir(mode=0o700)
        create = self.run_tool("statebackup.py", "create", "--state", repo.state, "--out", out)
        self.assert_clean(create, 0)
        backup = Path(json.loads(create.stdout)["backup"])
        verify = self.run_tool("statebackup.py", "verify", backup)
        self.assert_clean(verify, 0)
        self.assertEqual(json.loads(verify.stdout)["result"], "ok")
        history = self.run_tool("editor.py", "history", "--state", repo.state, "--limit", 5)
        self.assert_clean(history, 0)
        manifest = (backup / "MANIFEST.json").read_bytes()
        for canary in CANARIES: self.assertNotIn(canary.encode("utf-8"), manifest)
        doc = json.loads(manifest)
        self.assertEqual(set(doc), {"schemaVersion", "createdAt", "worktree", "files"})
        self.assertTrue(doc["files"] and all(not Path(k).is_absolute() and ".." not in Path(k).parts and len(v) == 64
                                             for k, v in doc["files"].items()))

    def test_queue_summary_is_counts_only(self):
        repo = self.fresh()
        run = self.chat(repo, [HISTORY, *ROWS], "--queue", START)
        self.assert_replies(run)
        self.assertEqual(run.stderr, "fixture_chat: queued=2 duplicate=0 history=1 handled=2\n")
        again = self.chat(repo, [HISTORY, *ROWS], "--queue", START)  # repeats: no reply, still counts only
        self.assert_clean(again, 0)
        self.assertEqual((again.stdout, again.stderr), ("", "fixture_chat: queued=0 duplicate=3 history=0 handled=0\n"))

    def test_missing_fixture_names_problem_without_canary(self):
        repo = self.fresh()
        missing = repo.state.parent / "no-such-fixture.jsonl"
        for flags in ((), ("--queue", START)):
            run = self.chat(repo, [], *flags, fixture=missing)
            self.assert_clean(run, 2)
            self.assertEqual(run.stdout, "")
            self.assertEqual(run.stderr, "fixture_chat: --fixture: unreadable\n")  # RF1510-12: the flag, not the path
            self.assertNotIn(missing.name, run.stderr)

    def test_stuck_outbox_detail_is_count_only(self):
        repo = self.fresh()
        self.assert_replies(self.chat(repo, ROWS))
        db = sqlite3.connect(repo.state / "conversation.sqlite3")
        try:  # an unsent reply from long ago whose text holds a canary
            with db:
                db.execute("UPDATE outbox SET sent_at = NULL, created_at = '2000-01-01T00:00:00+00:00', text = ?",
                           (f"{OWNER_TEXT} from {STRANGER}",))
        finally:
            db.close()
        health = self.run_tool("health.py", "--state", repo.state, "--outbox-minutes", 15)
        self.assert_clean(health, 1)
        self.assertEqual(json.loads(health.stdout)["problems"], [{"check": "outbox-stuck", "detail": "1"}])


if __name__ == "__main__":
    unittest.main()
