"""H09 demo with the REAL previewer: the whole fixture chain (owner text, draft, yes, private apply, real screenshot
check, history, undo) in ONE `fixture_chat.py --preview` run in a throwaway writer repo that holds the full tracked site.
Skipped when PLAYWRIGHT_MODULE is unset, like test_preview (locally also set CHROMIUM_PATH).
Run: python3 -B -m unittest hass.tests.test_demo_browser -v
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass.content_model import REPO_ROOT
from hass.tests import test_demo_transcript as demo
from hass.tests.test_editor import git

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MISSING_PLAYWRIGHT = "/nonexistent/hass-test/playwright"


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class DemoBrowserTests(unittest.TestCase):
    fresh, kinds, db = demo.DemoTranscriptTests.fresh, demo.DemoTranscriptTests.kinds, demo.DemoTranscriptTests.db

    def site(self):  # the writer worktree gets the full tracked storefront (as test_preview.make_previewer)
        repo = self.fresh()
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (repo.wt / rel).exists():
                (repo.wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, repo.wt / rel)
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-q", "-m", "full site")
        return repo

    def rebased(self, repo):  # the committed transcript with its times moved to now: a yes older than its draft is refused
        rows = [json.loads(line) for line in demo.DEMO.read_text("utf-8").splitlines()]
        shift = datetime.now(timezone.utc) - datetime.fromisoformat(rows[0]["at"])
        path = repo.state.parent / "demo-now.jsonl"
        path.write_text("".join(json.dumps({**r, "at": (datetime.fromisoformat(r["at"]) + shift).isoformat()}) + "\n"
                               for r in rows), "utf-8")
        return path

    def run_chain(self, repo, playwright=None):
        env = dict(os.environ) if playwright is None else {**os.environ, "PLAYWRIGHT_MODULE": playwright}
        run = subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state", str(repo.state),
                              "--fixture", str(self.rebased(repo)), "--interpreter", str(demo.MAPPING), "--preview"],
                             capture_output=True, text=True, cwd=REPO_ROOT, env=env)
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        return [json.loads(line) for line in run.stdout.splitlines()]

    def drafts(self, repo):
        return self.db(repo).execute("SELECT * FROM drafts ORDER BY row_id").fetchall()

    def test_whole_chain_with_real_screenshots(self):
        repo, before = self.site(), git(REPO_ROOT, "status", "--porcelain")
        original = demo._description(repo.state)
        rows = self.run_chain(repo)
        texts = [r["text"] for r in rows]
        self.assertEqual(self.kinds(texts), demo.EXPECTED)
        for i in (1, 4):
            self.assertTrue(texts[i].startswith("Applied and checked "), texts[i])
        state = repo.state.resolve()
        for i, row in enumerate(rows):  # draft and applied replies carry one private PNG; the rest none
            expected = 1 if texts[i].startswith(("Draft ", "Applied ")) or "\nDraft " in texts[i] else 0
            self.assertEqual(len(row["attachments"]), expected, (i, texts[i]))
            for name in row["attachments"]:
                png = Path(name)
                self.assertTrue(png.is_file() and not png.is_symlink(), name)
                self.assertEqual((stat.S_IMODE(png.stat().st_mode), png.read_bytes()[:8]), (0o600, PNG_SIGNATURE))
                self.assertTrue(png.resolve().is_relative_to(state), name)
                self.assertFalse(png.resolve().is_relative_to(repo.wt.resolve()) or png.resolve().is_relative_to(REPO_ROOT))
        edit, undo = self.drafts(repo)
        self.assertEqual((edit["state"], undo["state"]), ("reverted", "verified"))
        self.assertEqual(json.loads(undo["ops_json"])[0]["op"], "history.revert")
        self.assertEqual(demo._description(repo.state), original)
        self.assertEqual(git(REPO_ROOT, "status", "--porcelain"), before)
        messages = {r["provider_id"]: r["disposition"] for r in self.db(repo).execute("SELECT * FROM messages")}
        self.assertEqual((len(messages), len(self.drafts(repo)), len(texts)), (7, 2, 6))  # redelivered demo-1: no draft/reply
        self.assertEqual(messages["demo-6"], "ignored")  # the stranger's undo: no draft, no reply

    def test_missing_playwright_reports_the_failed_check_and_does_not_retry(self):
        repo = self.site()
        rows = self.run_chain(repo, MISSING_PLAYWRIGHT)
        texts = [r["text"] for r in rows]
        self.assertIn("\nPreview unavailable: ", texts[0])  # draft reply: no preview, no PNG
        edit, undo = self.drafts(repo)
        for i, draft in ((1, edit), (4, undo)):  # both apply replies name the failed check
            self.assertTrue(texts[i].startswith(f"Applied {draft['code']}, but the preview check failed: "), texts[i])
        self.assertTrue(all(not r["attachments"] for r in rows))  # no screenshot was made
        self.assertNotIn("verified", {edit["state"], undo["state"]})
        self.assertEqual((edit["state"], undo["state"]), ("reverted", "applied"))  # what main does: the undo still runs
        self.assertTrue(undo["reason"].startswith("not verified: "), undo["reason"])
        self.assertEqual(self.kinds(texts)[2:4], ["Recent changes:", "Undo "])
        for draft in (edit, undo):  # not retried: one commit per change, two since "full site"
            self.assertEqual(git(repo.wt, "log", "--format=%s", "--grep", draft["change_id"]).splitlines(),
                             [f"hass content: {draft['change_id']}"])
        self.assertEqual(git(repo.wt, "log", "-1", "--format=%s", "HEAD~2"), "full site")


if __name__ == "__main__":
    unittest.main()
