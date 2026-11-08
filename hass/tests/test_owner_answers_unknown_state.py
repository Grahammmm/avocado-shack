"""RF0910-5 tests (H17): an unknown change state is never answered as 'unchanged', 'Done' or 'waiting'.

Run: python3 -B -m unittest hass.tests.test_owner_answers_unknown_state
"""
import unittest
from datetime import datetime, timezone

from hass import owner_answers as answers
from hass.conversation import TRANSITIONS

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
SAVED_UNCONFIRMED = ("It's saved, but I'm not sure it's on the website. Copying it to the website hasn't been done, or didn't "
                     "finish. If copying it started and stopped partway, some pages may already show it. "
                     "Please ask Graham to copy it to the website again, which puts every page in place.")
# Each known state -> (did_it_work, history_words) with no install entry: the strings main gave before RF0910-5.
TODAY = {
    "needs-details": ("It's waiting for your yes. Nothing has changed yet.", 'waiting for your yes'),
    "proposed": ("It's waiting for your yes. Nothing has changed yet.", 'waiting for your yes'),
    "approved": ("You said yes, but it isn't saved yet, so nothing has changed on the website.",
                 "you said yes, but it isn't saved yet"),
    "reverted": ("That change was undone.", "undone"),
    "rejected": ('That change was cancelled, so nothing changed.', "cancelled, nothing changed"),
    "expired": ('That change was cancelled, so nothing changed.', "timed out, nothing changed"),
    "failed": ("I couldn't save that, and the website is unchanged. Please send the change again.",
               "I couldn't save it, so nothing changed"),
    "applied": (SAVED_UNCONFIRMED, "saved, but I'm not sure it's on the website"),
    "verified": (SAVED_UNCONFIRMED, "saved, but I'm not sure it's on the website"),
}
UNKNOWN = ("applied ", "Applied", "interrupted", 7, ["applied"])
INSTALLED = {"state": "installed", "installed_at": "2026-11-02T09:05:00-08:00"}


class UnknownStateTest(unittest.TestCase):
    def test_known_states_keep_todays_text(self):
        for state, (did, words) in TODAY.items():
            with self.subTest(state=state):
                change = {"state": state, "summary": "New hours"}
                self.assertEqual(answers.did_it_work(change, None, NOW), did)
                self.assertEqual(answers.history_words(change, None), words)

    def test_known_saved_state_with_install_still_done(self):
        change = {"state": "applied", "summary": "New hours"}
        self.assertEqual(answers.did_it_work(change, INSTALLED, NOW),
                         "Done. \ue000New hours\ue001 is on the website now (I checked today at 9:05 am).")
        self.assertEqual(answers.history_words(change, INSTALLED), "on the website")

    def test_unknown_states_ask_for_help(self):
        for state in UNKNOWN:
            for install in (None, {}, {"state": "failed", "reason": "write failed: x"}, INSTALLED):
                with self.subTest(state=state, install=install):
                    change = {"state": state, "summary": "New hours"}
                    did = answers.did_it_work(change, install, NOW)
                    words = answers.history_words(change, install)
                    self.assertEqual(did, answers.UNKNOWN_STATE)
                    self.assertEqual(words, "I'm not sure where this one stands - please ask Graham")
                    for claim in ("unchanged", "Done", "waiting", "Waiting", "on the website now"):
                        self.assertNotIn(claim, did)
                        self.assertNotIn(claim, words)

    def test_missing_or_none_state_keeps_waiting(self):
        for change in ({}, {"state": None}, {"summary": "New hours"}):
            with self.subTest(change=change):
                self.assertEqual(answers.did_it_work(change, INSTALLED, NOW),
                                 "It's waiting for your yes. Nothing has changed yet.")
                self.assertEqual(answers.history_words(change, INSTALLED), 'waiting for your yes')

    def test_known_matches_conversation_transitions(self):
        closed = set(TRANSITIONS) | {t for v in TRANSITIONS.values() for t in v}
        self.assertEqual(set(answers.KNOWN), closed)
        self.assertEqual(len(answers.KNOWN), len(set(answers.KNOWN)))


if __name__ == "__main__":
    unittest.main()
