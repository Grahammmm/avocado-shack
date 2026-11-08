"""RF2320-10 tests: owner answers never crash on a damaged change record or queue (hass/owner_answers.py).

Pure functions only: history_words with a non-object install result, stopped_state with an unusable waiting count,
a non-list applying value and non-code items. Nothing is read, written or sent.
Run: python3 -B -m unittest hass.tests.test_owner_answers_shapes
"""
import unittest

from hass import owner_answers as answers

PAUSED = "2026-11-01T10:00:00-07:00"
STOPPED = "Changes are stopped. Nothing new will be applied until you say 'resume'."
STAYS = "Changes already on the website stay there."
UNKNOWN = "Waiting requests: unknown."
STARTED = "had already started: the website is as it was before, and nothing is copied to it by itself."


class HistoryWordsShapeTests(unittest.TestCase):
    def test_non_object_install_is_not_confirmed(self):
        for state in ("applied", "verified"):
            for install in ([], ["installed"], "installed", 3, 0.5, True, ()):
                with self.subTest(state=state, install=install):
                    self.assertEqual(answers.history_words({"state": state}, install), "saved, but I'm not sure it's on the website")

    def test_object_install_unchanged(self):
        self.assertEqual(answers.history_words({"state": "applied"}, {"state": "installed"}), "on the website")
        self.assertEqual(answers.history_words({"state": "applied"}, {"state": "failed"}), "saved, but it didn't reach the website")
        self.assertEqual(answers.history_words({"state": "applied"}, {}), "saved, but I'm not sure it's on the website")
        self.assertEqual(answers.history_words({"state": "applied"}, None), "not confirmed on the website")

    def test_unsaved_states_ignore_a_damaged_install(self):
        self.assertEqual(answers.history_words({"state": "reverted"}, "installed"), "undone")
        self.assertEqual(answers.history_words({"state": "proposed"}, [1]), "waiting for your yes")


class StoppedStateShapeTests(unittest.TestCase):
    def test_unusable_waiting_count_is_unknown(self):
        for waiting in (None, -1, True, False, "3", 2.0, [2], {"n": 1}):
            with self.subTest(waiting=waiting):
                got = answers.stopped_state(PAUSED, {"waiting": waiting})
                self.assertEqual(got, f"{STOPPED} {UNKNOWN} {STAYS}")
                for raw in ("None", "-1", "True", "False", "2.0", "request is", "requests are"):
                    self.assertNotIn(raw, got)

    def test_missing_waiting_is_unknown(self):
        self.assertEqual(answers.stopped_state(PAUSED, {}), f"{STOPPED} {UNKNOWN} {STAYS}")
        self.assertEqual(answers.stopped_state(PAUSED, {"applying": []}), f"{STOPPED} {UNKNOWN} {STAYS}")

    def test_whole_non_negative_counts_unchanged(self):
        for n, words in ((0, "No requests are waiting."), (1, "1 request is waiting."), (5, "5 requests are waiting.")):
            with self.subTest(n=n):
                self.assertEqual(answers.stopped_state(PAUSED, {"waiting": n}), f"{STOPPED} {words} {STAYS}")

    def test_applying_string_is_never_split_into_letters(self):
        for applying in ("ABC", "", b"AB", 7, {"K7": 1}, None):
            with self.subTest(applying=applying):
                got = answers.stopped_state(PAUSED, {"waiting": 0, "applying": applying})
                self.assertEqual(got, f"Changes are stopped. I won't save anything new until you say 'resume changes'. No requests are waiting. {STAYS}")

    def test_only_code_items_are_listed_and_the_rest_counted_once(self):
        got = answers.stopped_state(PAUSED, {"waiting": 1, "applying": ["K7", 9, "../x", "Q2"]})
        self.assertEqual(got, f"Changes are stopped. I won't save anything new until you say 'resume changes'. 1 request is waiting. 2 changes had already started. The website is as it was before, and nothing is copied to it by itself. 2 more had already started. {STAYS}")
        self.assertNotIn("../x", got)

    def test_bad_items_each_skipped(self):
        bad = ["", "a b", "ab\tc", "x\n", "a/b", "A" * 41, None, ["K7"], 1.5, b"K7"]
        for item in bad:
            with self.subTest(item=item):
                got = answers.stopped_state(PAUSED, {"waiting": 0, "applying": (item,)})
                self.assertEqual(got, f"Changes are stopped. I won't save anything new until you say 'resume changes'. No requests are waiting. 1 more had already started. {STAYS}")
        got = answers.stopped_state(PAUSED, {"waiting": 0, "applying": ("A" * 40,) + tuple(bad)})
        self.assertEqual(got, f"{STOPPED} No requests are waiting. {'A' * 40} {STARTED} "
                              f"{len(bad)} more change(s) had already started. {STAYS}")
        self.assertEqual(got.count("more change(s)"), 1)

    def test_non_object_queue_is_empty(self):
        for queue in (None, [], [("waiting", 3)], "waiting", 4):
            with self.subTest(queue=queue):
                self.assertEqual(answers.stopped_state(PAUSED, queue), f"{STOPPED} {UNKNOWN} {STAYS}")

    def test_not_paused_is_on_for_any_queue(self):
        for queue in (None, [], {"waiting": None}, {"waiting": 2, "applying": "ABC"}):
            with self.subTest(queue=queue):
                self.assertEqual(answers.stopped_state(None, queue), "Changes are on.")
                self.assertEqual(answers.stopped_state("", queue), "Changes are on.")


if __name__ == "__main__":
    unittest.main()
