"""RF0550-3 tests: an approved change (the owner said yes; saving has not finished) is never "waiting for your OK".

did_it_work says it is being saved and nothing changed on the website yet; its history line says "approved, not
saved yet". Every other state keeps its words. Pure answers, then one conversation-level history line (H05 throwaway
repo, an apply interrupted before the editor ran). Nothing is sent.
Run: python3 -B -m unittest hass.tests.test_owner_answers_approved
"""
import unittest

from hass import owner_answers as answers
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_owner_answers import INTERNAL, NOW, row

UNDER_WAY = "You said yes, but it isn't saved yet, so nothing has changed on the website."
WAITING = "It's waiting for your yes. Nothing has changed yet."
INSTALLED = {"state": "installed", "installed_at": "2026-11-02T17:05:00+00:00", "commit": "d" * 40, "files": 3}
FAILED = {"state": "failed", "reason": "write failed: PermissionError"}


class ApprovedAnswerTests(unittest.TestCase):
    def test_approved_is_being_saved_whatever_the_install_entry(self):
        self.assertEqual(answers.UNDER_WAY, UNDER_WAY)
        for inst in (None, INSTALLED, FAILED, {}, [], "installed"):  # an install entry never upgrades it to "Done"
            with self.subTest(install=inst):
                self.assertEqual(answers.did_it_work(row("approved"), inst, NOW), UNDER_WAY)
                self.assertEqual(answers.history_words(row("approved"), inst), "you said yes, but it isn't saved yet")

    def test_approved_is_not_pending(self):
        self.assertNotIn("approved", answers.PENDING)
        self.assertEqual(answers.PENDING, ("proposed", "needs-details"))

    def test_not_yet_approved_states_keep_their_waiting_words(self):
        for state in ("proposed", "needs-details", None):
            for inst in (None, INSTALLED):
                with self.subTest(state=state, install=inst):
                    self.assertEqual(answers.did_it_work(row(state), inst, NOW), WAITING)
                    self.assertEqual(answers.history_words(row(state), inst), 'waiting for your yes')

    def test_other_states_unchanged(self):
        self.assertEqual(answers.did_it_work(row("reverted"), INSTALLED, NOW), "That change was undone.")
        self.assertEqual(answers.did_it_work(row("rejected"), None, NOW), "That change was cancelled, so nothing changed.")
        self.assertEqual(answers.did_it_work(row("verified"), INSTALLED, NOW),
                         "Done. \ue000store store: hours\ue001 is on the website now (I checked today at 9:05 am).")
        for state, inst, want in (("verified", INSTALLED, "on the website"), ("failed", None,
                                  "I couldn't save it, so nothing changed"), ("reverted", None, "undone")):
            self.assertEqual(answers.history_words(row(state), inst), want)

    def test_words_are_plain_and_never_claim_it_is_applied(self):
        for text in (UNDER_WAY, answers.history_words(row("approved"), INSTALLED)):
            with self.subTest(text=text):
                self.assertIsNone(INTERNAL.search(text), text)
                for word in ("Done", "applied", "on the website now", "waiting for your yes", "Waiting for your yes"):
                    self.assertNotIn(word, text)
        self.assertIn("nothing has changed on the website", UNDER_WAY)

    def test_approved_lookalike_states_are_not_under_way(self):  # only the exact state, no wording bypass
        for state in ("Approved", "approved ", "APPROVED"):
            with self.subTest(state=state):
                self.assertEqual(answers.history_words(row(state), INSTALLED), "I'm not sure where this one stands - please ask Graham")
                self.assertNotEqual(answers.did_it_work(row(state), INSTALLED, NOW), UNDER_WAY)


class ApprovedHistoryTests(ConversationTestCase):
    def test_interrupted_apply_history_says_approved_not_saved_yet(self):
        draft, _reply = self.propose("hours")
        self.editor.crash = True
        with self.assertRaises(RuntimeError):
            self.say("yes")  # the approval is stored; the apply never finished
        self.assertEqual(self.drafts()[0]["state"], "approved")
        self.assertEqual(self.say("history"), "history")
        [reply] = self.replies()
        self.assertEqual(reply.splitlines(), ["Here's what we changed lately:",
                                              f"- {draft['summary']}: you said yes, but it isn't saved yet"])
        self.assertNotIn('waiting for your yes', reply)


if __name__ == "__main__":
    unittest.main()
