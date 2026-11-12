"""HASS-CHAT-1 tests: a proposal whose picture could not be drawn is never silent, and the picture is tried once more later.

2026-11-09: G's hike proposal ended "I couldn't make a picture of how it will look." Reproduced on a scratch writer with his
exact draft: the live worker runs ``node`` = /usr/bin/node v18 with no PLAYWRIGHT_MODULE, so screenshot.cjs stops at
require('playwright') ("Cannot find module"), and Playwright 1.64 refuses Node 18 even when found. Every live preview failed,
not only hikes; the log only kept "Node.js v18.19.1". These tests pin: the reply says first that the picture could not be drawn
and that the list is exactly what will change; one retry 30 s later (worker cycle, outside the message) sends the picture or
says once that it still failed; nothing is sent for a proposal that is no longer waiting; Node's real error line is the one
reported, as a fixed kind in the log; the previewer runs the Node named by NODE.
Run: python3 -m unittest hass.tests.test_preview_retry -v
"""

import json
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import conversation, preview
from hass.tests.test_undo import PNG, H06TestCase

NODE_STDERR = ("node:internal/modules/cjs/loader:1080\n  throw err;\n  ^\n\nError: Cannot find module 'playwright'\nRequire stack:\n"
               "- /runtime/hass/screenshot.cjs\n{\n  code: 'MODULE_NOT_FOUND'\n}\n\nNode.js v18.19.1\n")


class ScriptedPreviewer:
    """Each capture takes the next outcome: "ok", "fail" (no picture) or "check" (a picture whose checks failed)."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def capture(self, files, target, out_png, **_):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if outcome == "fail":
            return {"ok": False, "png": None, "checks": {}, "error": "Error: Cannot find module 'playwright'"}
        preview._write_private(Path(out_png), PNG)
        if outcome == "check":
            return {"ok": False, "png": str(out_png), "checks": {"eventShown": False}, "error": "check failed: eventShown"}
        return {"ok": True, "png": str(out_png), "checks": {"fake": True}, "error": None}


class RetryCase(H06TestCase):
    outcomes = ("fail",)

    def make_previewer(self):
        return ScriptedPreviewer(*self.outcomes)

    def problems(self):
        return [(r["reason"], r.get("excerpt")) for r in self.conv.log.rows() if r["kind"] == "error"]


class NeverSilentTests(RetryCase):
    def test_failed_picture_says_so_first_and_queues_one_retry(self):
        self.assertEqual(self.say("desc"), "proposed")
        [sent] = self.sent()
        self.assertTrue(sent["text"].startswith(conversation.PREVIEW_FAILED_HEAD), sent["text"])
        self.assertTrue(sent["text"].endswith(conversation.PREVIEW_RETRY_LINE), sent["text"])
        self.assertNotIn("I couldn't make a picture", sent["text"])
        self.assertEqual(sent["attachments"], [])
        self.assertEqual(self.problems(), [("preview-failed", "playwright-missing")])
        [due] = self.conv.db.execute("SELECT * FROM preview_retry").fetchall()
        self.assertEqual(due["due_at"], (self.now + timedelta(seconds=30)).isoformat())

    def test_retry_waits_30_seconds_then_sends_the_picture_once(self):
        self.say("desc")
        self.sent()
        code = self.drafts()[-1]["code"]
        self.now += timedelta(seconds=29)
        self.assertEqual((self.conv.retry_previews(), self.sent()), (0, []))
        self.now += timedelta(seconds=1)
        self.assertEqual(self.conv.retry_previews(), 1)
        [later] = self.sent()
        self.assertTrue(later["text"].startswith("Here is the picture of how"), later["text"])
        self.assertTrue(later["text"].endswith(f"To go ahead, reply yes {code}."), later["text"])
        self.assertEqual(len(later["attachments"]), 1)
        self.assertEqual((self.conv.retry_previews(), self.sent(), self.previewer.calls), (0, [], 2))

    def test_nothing_is_sent_for_a_proposal_that_is_no_longer_waiting(self):
        self.say("desc")
        self.sent()
        self.assertEqual(self.say("no"), "rejected")
        self.sent()
        self.now += timedelta(seconds=31)
        self.assertEqual((self.conv.retry_previews(), self.sent(), self.previewer.calls), (1, [], 1))


class StillFailingTests(RetryCase):
    outcomes = ("fail", "fail")

    def test_a_second_failure_is_said_once_and_never_retried_again(self):
        self.say("desc")
        self.sent()
        self.now += timedelta(seconds=30)
        self.conv.retry_previews()
        [later] = self.sent()
        self.assertIn("I still couldn't draw the picture for", later["text"])
        self.assertIn("The change I listed is exactly what will happen.", later["text"])
        self.now += timedelta(seconds=60)
        self.assertEqual((self.conv.retry_previews(), self.sent(), self.previewer.calls), (0, [], 2))


class FailedCheckTests(RetryCase):
    outcomes = ("check",)

    def test_a_picture_whose_checks_failed_is_sent_with_a_plain_caveat_and_no_retry(self):
        self.say("desc")
        [sent] = self.sent()
        self.assertEqual(len(sent["attachments"]), 1)
        self.assertIn("The picture may not show every part of this change; the list above is exactly what will change.", sent["text"])
        self.assertFalse(sent["text"].startswith(conversation.PREVIEW_FAILED_HEAD))
        self.assertIsNone(self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'preview_retry'").fetchone())


class NodeErrorTests(unittest.TestCase):
    def test_the_error_line_and_kind_come_from_nodes_own_message(self):
        self.assertEqual(preview._last_line(NODE_STDERR), "Error: Cannot find module 'playwright'")
        for error, kind in ((NODE_STDERR, "playwright-missing"), ("Please update your version of Node.js.", "node-too-old"),
                            ("TimeoutExpired: Command timed out", "timeout"), ("preview server did not start", "server-did-not-start"),
                            ("check failed: eventShown", "check-failed"), ("something new", "other"), (None, "other")):
            with self.subTest(error=error):
                self.assertEqual(preview.failure_kind(error), kind)

    def test_the_node_named_by_NODE_runs_the_capture(self):
        runs = []

        def run(argv, **kw):
            runs.append(argv)
            return subprocess.CompletedProcess(argv, 1, "", NODE_STDERR)
        server = mock.Mock(pid=1, poll=mock.Mock(return_value=None))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(preview.Previewer, "_copy_site", return_value=Path(tmp)), \
                mock.patch.object(preview, "_get_ok", return_value=True), mock.patch.object(preview.subprocess, "Popen", return_value=server), \
                mock.patch.object(preview.subprocess, "run", side_effect=run):
            got = preview.Previewer(tmp, env={"NODE": "/opt/node22/bin/node", "PATH": "/usr/bin"}).capture(
                {}, {"kind": "event", "title": "T"}, Path(tmp) / "shot.png")
        self.assertEqual(runs[0][0], "/opt/node22/bin/node")
        self.assertEqual((got["ok"], got["error"]), (False, "Error: Cannot find module 'playwright'"))
        self.assertEqual(json.loads(json.dumps(got))["png"], None)


if __name__ == "__main__":
    unittest.main()
