"""RF0310-1 tests: an hours line needs a letter or digit; a street address or town needs a letter.

Uses the test_store_ops helpers (throwaway repo, production op registry). Nothing touches the checkout or live site.
Run: python3 -m unittest hass.tests.test_store_words -v
"""

import unittest

from hass.tests.test_store_ops import SET_ADDRESS, SET_HOURS, StoreTestCase, _req

STORE = "hass/content/store.json"


class StoreWordsTests(StoreTestCase):
    def assert_refused(self, repo, call, reason):
        before, head, drafts = repo.read(STORE), repo.head(), repo.drafts()
        out = repo.prepare(_req(call))
        self.assertEqual((out["result"], out.get("reason")), ("refused", reason), out)
        self.assertEqual((repo.read(STORE), repo.head(), repo.drafts(), repo.status()), (before, head, drafts, ""))

    def test_hours_line_without_letter_or_digit_is_refused_by_number(self):
        repo = self.repo()
        cases = [
            (["Mon–Sat 9am–6pm", "—"], "hours line 2 needs a day or time"),
            (["..."], "hours line 1 needs a day or time"),
            (["Open daily", "*", "-"], "hours line 2 needs a day or time"),
            (["Closed Sunday", "–––"], "hours line 2 needs a day or time"),
        ]
        for hours, reason in cases:
            with self.subTest(hours=hours):
                self.assert_refused(repo, (SET_HOURS, {"hours": hours}), reason)

    def test_no_word_refusal_wins_over_repeat_but_not_over_length_or_count(self):
        repo = self.repo()
        self.assert_refused(repo, (SET_HOURS, {"hours": ["...", "..."]}), "hours line 1 needs a day or time")
        self.assert_refused(repo, (SET_HOURS, {"hours": ["Open", "Open", "—"]}), "hours line 3 needs a day or time")
        self.assert_refused(repo, (SET_HOURS, {"hours": ["—", "-" * 61]}), "hours line 2 is longer than 60 characters")
        self.assert_refused(repo, (SET_HOURS, {"hours": ["—"] * 8}), "at most 7 hours lines (you sent 8)")

    def test_digits_only_and_accented_hours_apply(self):
        repo = self.repo()
        for hours in (["9-5"], ["Sábado 9–14"], ["Lunes", "24/7"]):
            with self.subTest(hours=hours):
                repo.run((SET_HOURS, {"hours": hours}))
                self.assertEqual(repo.store()["hours"], hours)
        self.assertEqual(repo.status(), "")

    def test_street_or_town_without_letter_is_refused_by_field(self):
        repo = self.repo()
        cases = [
            ({"streetAddress": "2200"}, "streetAddress needs at least one letter"),
            ({"town": "--"}, "town needs at least one letter"),
            ({"town": "123"}, "town needs at least one letter"),
            ({"streetAddress": "2200", "town": "--"}, "streetAddress needs at least one letter"),
            ({"streetAddress": "1023 Example Street", "town": "93442"}, "town needs at least one letter"),
            ({"town": "Cayucos", "streetAddress": "#12"}, "streetAddress needs at least one letter"),
        ]
        for args, reason in cases:
            with self.subTest(args=args):
                self.assert_refused(repo, (SET_ADDRESS, args), reason)

    def test_length_refusal_comes_first(self):
        repo = self.repo()
        self.assert_refused(repo, (SET_ADDRESS, {"town": "1" * 81}), "town is longer than 80 characters")
        self.assert_refused(repo, (SET_ADDRESS, {"streetAddress": "2200", "town": "t" * 81}),
                            "town is longer than 80 characters")

    def test_real_street_and_accented_town_apply(self):
        repo = self.repo()
        before = repo.store()
        repo.run((SET_ADDRESS, {"streetAddress": "1023 Example Street", "town": "Ñipomo"}))
        self.assertEqual(repo.store(), {**before, "streetAddress": "1023 Example Street", "town": "Ñipomo"})
        self.assertEqual(repo.status(), "")

    def test_current_valid_address_resent_is_still_already(self):
        repo = self.repo()
        current = repo.store()
        self.assert_refused(repo, (SET_ADDRESS, {"streetAddress": current["streetAddress"], "town": current["town"]}),
                            f"store address is already {current['streetAddress']}, {current['town']}")


if __name__ == "__main__":
    unittest.main()
