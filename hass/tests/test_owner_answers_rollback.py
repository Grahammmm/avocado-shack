"""RF1230-19 tests: a saved change whose install failed and whose rollback also failed reads as "ask for help" in the
change history, as the "did my change work?" answer does (hass/owner_answers.py history_words / did_it_work).

Pure functions only; nothing is read, written or sent.
Run: python3 -B -m unittest hass.tests.test_owner_answers_rollback
"""
import unittest
from datetime import datetime, timezone

from hass import owner_answers as answers

NOW = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
WORDS = "install failed, some website files not put back - ask for help"
BOTH = {"state": "failed", "reason": "write failed: x; rollback failed: y"}
DID_BOTH = ("This did not reach the website, and some website files could not be put back. "
            "The website files could not be written. Please ask for help before more changes.")
PUT_BACK = "some website files could not be put back"


class RollbackFailedHistoryTests(unittest.TestCase):
    def test_constant_is_the_designed_words(self):
        self.assertEqual(answers.ROLLBACK_FAILED_WORDS, WORDS)

    def test_saved_with_failed_rollback_asks_for_help(self):
        for state in ("applied", "verified"):
            with self.subTest(state=state):
                self.assertEqual(answers.history_words({"state": state}, BOTH), WORDS)
                self.assertEqual(answers.did_it_work({"state": state, "summary": "Price"}, BOTH, NOW), DID_BOTH)

    def test_failed_install_without_rollback_failure_unchanged(self):
        for reason in ("write failed: x", "readback mismatch: y", "", None, "rollback ok"):
            with self.subTest(reason=reason):
                install = {"state": "failed", "reason": reason}
                self.assertEqual(answers.history_words({"state": "applied"}, install), "not on the website yet")
                self.assertNotIn(PUT_BACK, answers.did_it_work({"state": "applied"}, install, NOW))

    def test_other_install_states_with_the_phrase_unchanged(self):
        for install, words in (({"state": "installed", "reason": "rollback failed: y"}, "on the website"),
                               ({"state": "running", "reason": "rollback failed: y"}, "not confirmed on the website"),
                               ({"reason": "rollback failed: y"}, "not confirmed on the website"),
                               ("rollback failed", "not confirmed on the website"),
                               ([BOTH], "not confirmed on the website")):
            with self.subTest(install=install):
                self.assertEqual(answers.history_words({"state": "applied"}, install), words)

    def test_non_string_reason_follows_str_rule_and_both_functions_agree(self):
        cases = ((None, False), (42, False), (["rollback failed"], True), (("x", "rollback failed: y"), True),
                 ({"rollback failed": 1}, True), ("ROLLBACK FAILED: y", False), ("rollback  failed", False),
                 ("write failed: x; rollback failed: y", True), ("rollback failed", True))
        for reason, expected in cases:
            for state in ("applied", "verified"):
                with self.subTest(reason=reason, state=state):
                    install = {"state": "failed", "reason": reason}
                    history = answers.history_words({"state": state}, install)
                    did = answers.did_it_work({"state": state}, install, NOW)
                    self.assertEqual(history == WORDS, expected)
                    self.assertEqual(PUT_BACK in did, expected)
                    self.assertEqual(history, WORDS if expected else "not on the website yet")

    def test_non_saved_states_ignore_the_install(self):
        for state, words in (("approved", "approved, not saved yet"), ("reverted", "undone"),
                             ("failed", "not saved; website unchanged"), ("proposed", "waiting for your OK"),
                             ("needs-details", "waiting for your OK"), ("rejected", "nothing changed"),
                             ("expired", "nothing changed"), (None, "waiting for your OK"),
                             ("bogus", "state unknown - ask for help")):
            with self.subTest(state=state):
                self.assertEqual(answers.history_words({"state": state}, BOTH), words)
                self.assertNotIn(PUT_BACK, answers.did_it_work({"state": state}, BOTH, NOW))

    def test_words_never_carry_the_reason_or_a_path(self):
        reason = "write failed: /srv/site/secret-page.html; rollback failed: /srv/site/index.html PermissionError"
        words = answers.history_words({"state": "verified"}, {"state": "failed", "reason": reason})
        self.assertEqual(words, WORDS)
        for fragment in ("/", "srv", "secret-page", "index.html", "PermissionError", "write failed", "rollback failed"):
            self.assertNotIn(fragment, words)


if __name__ == "__main__":
    unittest.main()
