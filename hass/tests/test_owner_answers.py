"""SHOP-4 tests: "did my change work?" and "stop changes" answers (hass/owner_answers.py and its conversation call sites).

Pure answers first, then the conversation with the H05 throwaway repo (temp Git repo, linked writer worktree, private
state dir, fixture interpreter, injected clock) and a temp site dir for the SHOP-2 install step. Nothing is sent.
Run: python3 -B -m unittest hass.tests.test_owner_answers
"""
import re
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import conversation, install, owner_answers as answers
from hass.tests.test_conversation import SETTINGS, T0, ConversationTestCase
from hass.tests.test_editor import SITE_FILES

NOW = datetime(2026, 11, 2, 17, 30, tzinfo=timezone.utc)  # Mon 09:30 PST
INTERNAL = re.compile(r"chg-|sha256|[0-9a-f]{7,}|/|worktree|commit|revision|index\.html|PermissionError", re.I)
STOPPED = "Changes are stopped. Nothing new will be applied until you say 'resume'."
STAYS = "Changes already on the website stay there."
NOT_COPIED = ("Saved, but not on the website yet. Copying it to the website has not been done or did not finish. "
              "Nothing is broken; ask for help to put it on the website.")


def row(state, **kw):
    return {"state": state, "summary": "store store: hours", "reason": None, "commit": "a" * 40,
            "change_id": "chg-" + "b" * 12, "draft_hash": "sha256:" + "c" * 64, **kw}


class DidItWorkTests(unittest.TestCase):
    def test_each_state_has_its_sentence_and_no_internal_words(self):
        installed = {"state": "installed", "installed_at": "2026-11-02T17:05:00+00:00", "commit": "d" * 40, "files": 3}
        failed = {"state": "failed", "reason": "write failed: PermissionError", "commit": "d" * 40}
        cases = [
            (row("verified"), installed, "Done. store store: hours is on the website now (checked today 09:05)."),
            (row("applied"), None, NOT_COPIED),
            (row("verified"), failed, "This did not reach the website, and the website is unchanged. "
                                      "The website files could not be written."),
            (row("reverted"), installed, "That change was undone."),
            (row("proposed"), None, "Waiting for your OK - nothing has changed yet."),
            (row("failed", reason="generated file out of date: storefront-mockup/index.html"), None,
             "This was not saved, and the website is unchanged; send the change again to retry.")]
        for change, inst, want in cases:
            with self.subTest(state=change["state"], install=inst):
                got = answers.did_it_work(change, inst, NOW)
                self.assertEqual(got, want)
                self.assertIsNone(INTERNAL.search(got), got)

    def test_install_reasons_drop_the_file_name(self):
        for reason, plain in (("readback mismatch: index.html", "The website files did not read back as written"),
                              ("site path is not a regular file: index.html", "Something unexpected is in the website folder"),
                              ("a new reason: index.html", "The copy did not finish"), (None, "The copy did not finish")):
            with self.subTest(reason=reason):
                got = answers.did_it_work(row("applied"), {"state": "failed", "reason": reason}, NOW)
                self.assertEqual(got, f"This did not reach the website, and the website is unchanged. {plain}.")
                self.assertIsNone(INTERNAL.search(got), got)

    def test_failed_rollback_never_says_the_website_is_unchanged(self):
        got = answers.did_it_work(row("applied"), {"state": "failed", "reason": "write failed: OSError; rollback "
                                                   "failed: index.html"}, NOW)
        self.assertNotIn("unchanged", got)
        self.assertEqual(got, "This did not reach the website, and some website files could not be put back. The "
                              "website files could not be written. Please ask for help before more changes.")

    def test_not_yet_approved_is_never_described_as_applied(self):
        installed = {"state": "installed", "installed_at": "2026-11-02T17:05:00+00:00"}
        for state in ("proposed", "needs-details", "approved", None):
            with self.subTest(state=state):
                self.assertEqual(answers.did_it_work(row(state), installed, NOW),
                                 "Waiting for your OK - nothing has changed yet.")
                self.assertEqual(answers.history_words(row(state), installed), "waiting for your OK")
        for state in ("rejected", "expired"):
            self.assertEqual(answers.did_it_work(row(state), installed, NOW), "That draft was closed, so nothing changed.")

    def test_checked_time_today_another_day_and_unreadable(self):
        for at, want in (("2026-11-02T17:05:00+00:00", "today 09:05"), ("2026-11-01T17:05:00+00:00", "Sun Nov 1 09:05"),
                         ("not a time", "at an unknown time"), (None, "at an unknown time")):
            with self.subTest(at=at):
                got = answers.did_it_work(row("applied"), {"state": "installed", "installed_at": at}, NOW)
                self.assertEqual(got, f"Done. store store: hours is on the website now (checked {want}).")

    def test_preview_failure_is_the_reason_it_is_not_on_the_website(self):
        got = answers.did_it_work(row("applied", reason="not verified: check failed: productShown"), None, NOW)
        self.assertEqual(got, "Saved, but not on the website yet. The preview check failed (check failed: productShown)."
                              " Nothing is broken; ask for help to put it on the website.")

    def test_history_words(self):
        for state, inst, want in (("verified", {"state": "installed"}, "on the website"),
                                  ("applied", {"state": "failed"}, "not on the website yet"),
                                  ("applied", None, "not on the website yet"), ("reverted", None, "undone"),
                                  ("failed", None, "not saved; website unchanged"), ("expired", None, "nothing changed")):
            with self.subTest(state=state, install=inst):
                self.assertEqual(answers.history_words(row(state), inst), want)


class StoppedStateTests(unittest.TestCase):
    def test_waiting_counts_in_words(self):
        for n, words in ((0, "No requests are waiting."), (1, "1 request is waiting."), (3, "3 requests are waiting.")):
            with self.subTest(n=n):
                self.assertEqual(answers.stopped_state("2026-11-02T17:00:00+00:00", {"waiting": n, "applying": []}),
                                 f"{STOPPED} {words} {STAYS}")

    def test_not_paused_and_under_way(self):
        self.assertEqual(answers.stopped_state(None, {"waiting": 3}), "Changes are on.")
        self.assertEqual(answers.stopped_state("x", {"waiting": 0, "applying": ["ab12"]}),
                         f"{STOPPED} No requests are waiting. ab12 had already started: the website is as it was "
                         f"before, and nothing is copied to it by itself. {STAYS}")


class Killed(BaseException):
    """Stands in for the process dying in the middle of an install (no except clause runs)."""


class ConversationAnswerTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory(prefix="hass-site-")
        self.addCleanup(tmp.cleanup)
        self.site = Path(tmp.name).resolve() / "site"
        for rel in SITE_FILES:
            (self.site / rel[len("storefront-mockup/"):]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.repo.main / rel, self.site / rel[len("storefront-mockup/"):])
        self.set_settings({**SETTINGS, "site_dir": str(self.site)})
        self.conv = self.open()

    def snapshot(self):
        return {str(p.relative_to(self.site)): p.read_bytes() for p in sorted(self.site.rglob("*")) if p.is_file()}

    def applied(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        return draft

    def last_line(self, text="did it work?"):
        self.assertEqual(self.say(text), "status")
        [reply] = self.replies()
        return next(line for line in reply.splitlines() if line.startswith("Last change: "))

    def history(self):
        self.assertEqual(self.say("history"), "history")
        return self.replies()[0].splitlines()[1:]

    def test_phrases_parse_and_lookalikes_do_not(self):
        for text in ("did it work?", "Did it work", "did that work?!", "DID MY CHANGE WORK?"):
            self.assertEqual(conversation.parse_command(text), ("status", None), text)
        for text in ("stop changes", "Stop!", "stop", "STOP CHANGES."):
            self.assertEqual(conversation.parse_command(text), ("pause", None), text)
        for text in ("did it work for the hike", "it work", "did work", "did it work??", "stop selling eggs",
                     "please stop changes", "stop changes now"):
            self.assertIsNone(conversation.parse_command(text), text)

    def test_did_it_work_follows_the_install(self):
        draft = self.applied()
        self.assertEqual(self.last_line(), f"Last change: {draft['code']} store store: hours - {NOT_COPIED}")
        self.assertEqual(self.history(), [f"{draft['code']} applied: store store: hours - not on the website yet"])
        self.now = T0 + timedelta(minutes=5)
        out = install.install(draft["change_id"], state=str(self.repo.state), now=self.now)
        self.assertEqual(out["result"], "installed")
        line = self.last_line("Did my change work?")
        self.assertEqual(line, f"Last change: {draft['code']} store store: hours - Done. store store: hours is on the "
                               "website now (checked today 09:05).")
        self.assertEqual(self.history(), [f"{draft['code']} applied: store store: hours - on the website"])

    def test_failed_install_says_the_website_is_unchanged(self):
        draft, before = self.applied(), self.snapshot()
        with mock.patch.object(install, "_swap", side_effect=PermissionError("denied")):
            self.assertEqual(install.install(draft["change_id"], state=str(self.repo.state))["result"], "failed")
        self.assertEqual(self.snapshot(), before)  # SHOP-2 rolled back: what the answer says is true on disk
        self.assertEqual(self.last_line(), f"Last change: {draft['code']} store store: hours - This did not reach "
                                           "the website, and the website is unchanged. The website files could not "
                                           "be written.")

    def test_interrupted_install_is_not_called_done_until_a_retry_finishes(self):
        draft = self.applied()
        real = install._swap

        def killed(tmp, target):
            real(tmp, target)
            raise Killed()
        with mock.patch.object(install, "_swap", killed), self.assertRaises(Killed):
            install.install(draft["change_id"], state=str(self.repo.state))
        self.conv = self.open()  # restart: recovery has nothing to settle, the answer reads the change record
        self.assertEqual(self.last_line(), f"Last change: {draft['code']} store store: hours - {NOT_COPIED}")
        self.assertEqual(install.install(draft["change_id"], state=str(self.repo.state))["result"], "installed")
        self.assertIn("is on the website now", self.last_line())

    def test_stop_while_an_apply_is_under_way_then_recovery(self):
        draft, _reply = self.propose("hours")
        before = self.snapshot()
        self.editor.crash = True
        with self.assertRaises(RuntimeError):
            self.say("yes")  # the approval is stored; the apply never finished
        self.assertEqual(self.say("stop changes", pid="s1"), "pause")
        self.assertEqual(self.replies(), [f"{STOPPED} No requests are waiting. {draft['code']} had already started: "
                                          f"the website is as it was before, and nothing is copied to it by itself. "
                                          f"{STAYS}"])
        self.assertEqual((self.commits(), self.editor.applies), (0, 1))
        self.editor.crash = False
        self.conv = self.open()  # recovery never re-applies; it says what state the website is in
        self.assertEqual((self.drafts()[0]["state"], self.commits(), self.editor.applies), ("failed", 0, 1))
        self.assertEqual(self.snapshot(), before)  # nothing half-installed: the website really is as it was
        self.assertEqual(self.replies(), [f"{draft['code']} was interrupted and not saved. The website is as it was "
                                          "before; send the change again to make a new draft."])
        self.assertEqual(self.say("stop"), "pause")  # still stopped after the restart; nothing is under way now
        self.assertEqual(self.replies(), [f"{STOPPED} No requests are waiting. {STAYS}"])

    def test_stop_counts_waiting_drafts_and_unread_messages_but_not_itself(self):
        path = self.repo.state / "inbox.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE inbound(provider_id TEXT PRIMARY KEY, state TEXT NOT NULL)")
            db.executemany("INSERT INTO inbound VALUES (?, ?)", [("s1", "pending"), ("u1", "pending"),
                                                                 ("u2", "pending"), ("d1", "done")])
        self.propose("hours")
        self.assertEqual(self.say("stop changes", pid="s1"), "pause")
        self.assertEqual(self.replies(), [f"{STOPPED} 3 requests are waiting. {STAYS}"])
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.now = T0 + timedelta(hours=1)
        with sqlite3.connect(path) as db:  # the drain marked s1 done; u1 is the message being handled now
            db.execute("UPDATE inbound SET state = 'done' WHERE provider_id = 's1'")
        self.assertEqual(self.say("pause changes", pid="u1"), "pause")  # again: same answer, one pause row
        self.assertEqual(self.replies(), [f"{STOPPED} 1 request is waiting. {STAYS}"])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM control").fetchone()[0], 1)
        path.write_bytes(b"not a database")  # an unreadable inbox counts nothing and never fails the stop
        self.assertEqual(self.say("stop"), "pause")
        self.assertEqual(self.replies(), [f"{STOPPED} No requests are waiting. {STAYS}"])

    def test_expired_draft_is_not_waiting(self):
        self.propose("hours")
        self.now = T0 + timedelta(hours=1)  # past the 600 s approval window
        self.assertEqual(self.say("stop changes"), "pause")
        self.assertEqual(self.replies(), [f"{STOPPED} No requests are waiting. {STAYS}"])


if __name__ == "__main__":
    unittest.main()
