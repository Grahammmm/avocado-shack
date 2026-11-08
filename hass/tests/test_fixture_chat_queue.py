"""RF0935-7 (H16): `fixture_chat.py --queue START_AT` stores every fixture message in <state>/inbox.sqlite3, then
drains it once. Runs the CLI as a subprocess against a throwaway writer repo (test_editor.WriterRepo), as
test_demo_transcript does. Run: python3 -B -m unittest hass.tests.test_fixture_chat_queue -v
"""

import json
import re
import sqlite3
import subprocess
import sys
import unittest

from hass import editor
from hass.content_model import REPO_ROOT
from hass.tests.test_conversation import CHAT, SETTINGS
from hass.tests.test_demo_transcript import MAPPING
from hass.tests.test_editor import WriterRepo

START = "2026-11-02T08:30:00-08:00"
REQUEST = "Make the avocado description shorter"


def line(mid, text, at, sender="owner@example.invalid"):
    return {"id": mid, "chat": CHAT, "sender": sender, "text": text, "fromMe": False, "kind": "new", "at": at}


PAIR = [line("q-1", REQUEST, "2026-11-02T09:00:00-08:00"), line("q-2", "yes", "2026-11-02T09:01:00-08:00")]


class FixtureChatQueueTests(unittest.TestCase):
    def fresh(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": SETTINGS})
        return repo

    def run_cli(self, repo, rows, *flags, state=None):
        fixture = repo.state.parent / "fixture.jsonl"
        fixture.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state",
                               str(state or repo.state), "--fixture", str(fixture), "--interpreter", str(MAPPING),
                               *flags], capture_output=True, text=True, cwd=REPO_ROOT)

    def masked(self, run, repo):
        out = re.sub(r"Expires [^\n]*?\.", "Expires <time>.", run.stdout)
        for code in self.query(repo, "conversation", "SELECT code FROM drafts"):
            out = out.replace(code[0], "<code>")
        return out

    def query(self, repo, db, sql):
        con = sqlite3.connect(repo.state / f"{db}.sqlite3")
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def summary(self, run):
        return run.stderr.strip().removeprefix("fixture_chat: ")

    def test_without_flag_output_unchanged_and_no_inbox(self):
        a, b = self.fresh(), self.fresh()
        ra, rb = self.run_cli(a, PAIR), self.run_cli(b, PAIR)
        self.assertEqual((ra.returncode, ra.stderr, rb.returncode, rb.stderr), (0, "", 0, ""))
        self.assertEqual(len(ra.stdout.splitlines()), 2)
        self.assertEqual(self.masked(ra, a), self.masked(rb, b))
        self.assertFalse((a.state / "inbox.sqlite3").exists())

    def test_queue_matches_direct_run_and_rerun_is_duplicate(self):
        plain, queued = self.fresh(), self.fresh()
        direct, run = self.run_cli(plain, PAIR), self.run_cli(queued, PAIR, "--queue", START)
        self.assertEqual((run.returncode, self.summary(run)), (0, "queued=2 duplicate=0 history=0 handled=2"))
        self.assertEqual(self.masked(run, queued), self.masked(direct, plain))
        head, drafts = queued.head(), self.query(queued, "conversation", "SELECT * FROM drafts")
        again = self.run_cli(queued, PAIR, "--queue", START)
        self.assertEqual((again.returncode, again.stdout), (0, ""))
        self.assertEqual(self.summary(again), "queued=0 duplicate=2 history=0 handled=0")
        self.assertEqual((queued.head(), self.query(queued, "conversation", "SELECT * FROM drafts")), (head, drafts))

    def test_history_message_never_reaches_conversation(self):
        repo = self.fresh()
        run = self.run_cli(repo, [line("old-1", REQUEST, "2026-11-02T08:00:00-08:00")], "--queue", START)
        self.assertEqual((run.returncode, run.stdout), (0, ""))
        self.assertEqual(self.summary(run), "queued=0 duplicate=0 history=1 handled=0")
        self.assertEqual(self.query(repo, "conversation", "SELECT code FROM drafts"), [])
        self.assertEqual(self.query(repo, "conversation", "SELECT * FROM messages"), [])
        self.assertEqual(self.query(repo, "inbox", "SELECT state, payload FROM inbound"), [("history", None)])

    def test_different_start_point_refused_nothing_enqueued(self):
        repo = self.fresh()
        self.assertEqual(self.run_cli(repo, PAIR, "--queue", START).returncode, 0)
        before = self.query(repo, "inbox", "SELECT * FROM inbound ORDER BY provider_id")
        run = self.run_cli(repo, [line("q-3", "history", "2026-11-02T09:05:00-08:00")], "--queue",
                           "2026-11-02T08:00:00-08:00")
        self.assertEqual((run.returncode, run.stdout), (2, ""))
        self.assertIn("start point already recorded as", run.stderr)
        self.assertEqual(self.query(repo, "inbox", "SELECT * FROM inbound ORDER BY provider_id"), before)

    def test_bad_time_stops_before_draining_and_rerun_handles_once(self):
        repo = self.fresh()
        bad = [PAIR[0], line("q-2", "yes", "2026-11-02T09:01:00"), line("q-3", "history", "2026-11-02T09:02:00-08:00")]
        run = self.run_cli(repo, bad, "--queue", START)
        self.assertEqual((run.returncode, run.stdout), (2, ""))
        self.assertEqual(run.stderr, "fixture_chat: fixture line 2: at must be an ISO time with a UTC offset\n")
        self.assertEqual(self.query(repo, "conversation", "SELECT code FROM drafts"), [])
        self.assertEqual(self.query(repo, "inbox", "SELECT provider_id, state FROM inbound"), [])  # nothing enqueued
        fixed = self.run_cli(repo, [*PAIR, bad[2]], "--queue", START)
        self.assertEqual((fixed.returncode, self.summary(fixed)), (0, "queued=3 duplicate=0 history=0 handled=3"))
        texts = [json.loads(r)["text"] for r in fixed.stdout.splitlines()]
        self.assertEqual([t.split(" ")[0] for t in texts[:2]], ["Here's", "Saved:"])
        self.assertEqual(len(self.query(repo, "conversation", "SELECT code FROM drafts")), 1)
        self.assertEqual(self.query(repo, "inbox", "SELECT DISTINCT state FROM inbound"), [("done",)])

    def test_out_of_order_lines_handled_in_time_order(self):
        repo = self.fresh()
        run = self.run_cli(repo, [PAIR[1], PAIR[0]], "--queue", START)
        self.assertEqual((run.returncode, self.summary(run)), (0, "queued=2 duplicate=0 history=0 handled=2"))
        texts = [json.loads(r)["text"] for r in run.stdout.splitlines()]
        self.assertEqual([t.split(" ")[0] for t in texts], ["Here's", "Saved:"])
        proposed, = self.query(repo, "conversation", "SELECT proposed_at FROM drafts")
        self.assertEqual(proposed[0], "2026-11-02T17:00:00+00:00")

    def test_direct_fixture_refuses_yes_before_proposal(self):
        repo = self.fresh()
        early = line("q-2", "yes", "2026-11-02T08:59:00-08:00")
        run = self.run_cli(repo, [PAIR[0], early, {**PAIR[1], "id": "q-3"}])
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        texts = [json.loads(r)["text"] for r in run.stdout.splitlines()]
        self.assertIn("came before", texts[1])
        self.assertTrue(texts[2].startswith("Saved:"), texts)

    def test_fixture_clock_advances_so_late_yes_expires(self):
        repo = self.fresh()
        late = line("q-2", "yes", "2026-11-03T09:01:00-08:00")
        run = self.run_cli(repo, [PAIR[0], late])
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        self.assertEqual(self.query(repo, "conversation", "SELECT state FROM drafts"), [("expired",)])

    def test_symlinked_unsafe_state_dir_refused_without_inbox(self):
        repo = self.fresh()  # open_state resolves links, so the link points at a group-readable dir
        target, link = repo.state.parent / "open", repo.state.parent / "state-link"
        target.mkdir(mode=0o755)
        target.chmod(0o755)
        link.symlink_to(target, target_is_directory=True)
        today, run = self.run_cli(repo, PAIR, state=link), self.run_cli(repo, PAIR, "--queue", START, state=link)
        self.assertEqual((run.returncode, run.stdout, run.stderr), (2, "", today.stderr))
        self.assertEqual(today.returncode, 2)
        self.assertIn("UnsafeState", run.stderr)
        self.assertEqual(list(repo.state.parent.rglob("inbox.sqlite3")), [])

    def test_summary_carries_counts_only(self):
        repo = self.fresh()
        run = self.run_cli(repo, [line("s-1", "SECRET-SENTINEL please", "2026-11-02T09:00:00-08:00")], "--queue", START)
        self.assertEqual((run.returncode, self.summary(run)), (0, "queued=1 duplicate=0 history=0 handled=1"))
        self.assertNotIn("SECRET-SENTINEL", run.stderr)


if __name__ == "__main__":
    unittest.main()
