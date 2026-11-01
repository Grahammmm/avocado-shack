"""RF1720-1 (H13): store.set_hours refuses hours lines that differ only by case, spacing or dash style, naming
both 1-based line numbers. Throwaway writer repo (test_store_ops.StoreRepo) only.
Run: python3 -m unittest hass.tests.test_store_hours_repeat -v
"""

import unittest

from hass.tests.test_store_ops import INDEX, SET_HOURS, StoreTestCase, _req


class HoursRepeatTests(StoreTestCase):
    def refused(self, repo, hours):
        drafts = repo.drafts()
        out = repo.prepare(_req((SET_HOURS, {"hours": hours})))
        self.assertEqual(out["result"], "refused", out)
        self.assertEqual(repo.drafts(), drafts)
        return out["reason"]

    def accepted(self, repo, hours):
        repo.run((SET_HOURS, {"hours": hours}))
        self.assertEqual(repo.store()["hours"], hours)

    def test_case_and_spacing_repeat_names_both_lines(self):
        repo = self.repo()
        self.assertEqual(self.refused(repo, ["Closed Sunday", "closed  sunday"]),
                         "hours lines 1 and 2 say the same thing")
        self.assertEqual(self.refused(repo, ["Closed Sunday", "CLOSED   Sunday"]),
                         "hours lines 1 and 2 say the same thing")
        self.assertEqual(self.refused(repo, ["Closed", "Closed"]), "hours lines 1 and 2 say the same thing")

    def test_dash_styles_repeat(self):
        repo = self.repo()
        for dash in ("\u2013", "\u2014", "\u2010", "\u2015", "\u2212"):
            self.assertEqual(self.refused(repo, [f"Mon{dash}Fri 9am{dash}6pm", "Mon-Fri 9am-6pm"]),
                             "hours lines 1 and 2 say the same thing", dash)

    def test_non_adjacent_repeat_and_first_pair_only(self):
        repo = self.repo()
        self.assertEqual(self.refused(repo, ["Closed Sunday", "Saturday 9am–5pm", "closed sunday"]),
                         "hours lines 1 and 3 say the same thing")
        self.assertEqual(self.refused(repo, ["A 9–5", "B 9–5", "b 9-5", "a 9-5"]),
                         "hours lines 2 and 3 say the same thing")
        self.assertEqual(self.refused(repo, ["A 9–5", "B 9–5", "a 9-5", "b 9-5"]),
                         "hours lines 1 and 3 say the same thing")

    def test_distinct_lines_sharing_words_are_applied(self):
        repo = self.repo()
        self.accepted(repo, ["Saturday 9am–5pm", "Sunday 9am–5pm"])
        self.assertIn("Saturday 9am–5pm<br>Sunday 9am–5pm", repo.text(INDEX))

    def test_accents_are_not_folded(self):
        self.accepted(self.repo(), ["Café hours 9–5", "Cafe hours 9–5"])

    def test_saved_text_keeps_the_owners_exact_text(self):
        repo = self.repo()
        hours = ["MONDAY—Friday  9am−6pm", "Closed sunday"]
        self.accepted(repo, hours)
        self.assertIn("MONDAY—Friday  9am−6pm", repo.text("hass/content/store.json"))

    def test_no_op_check_stays_exact(self):
        repo = self.repo()
        current = repo.store()["hours"]
        self.assertEqual(self.refused(repo, list(current)), "store hours are already " + " / ".join(current))
        recased = [current[0].upper(), *current[1:]]
        self.accepted(repo, recased)
        self.assertEqual(self.refused(repo, recased), "store hours are already " + " / ".join(recased))

    def test_existing_limits_refused_first(self):
        repo = self.repo()
        self.assertEqual(self.refused(repo, ["Closed"] * 8), "at most 7 hours lines")
        self.assertEqual(self.refused(repo, ["Closed", "closed", "a" * 61]),
                         "hours line 2 is longer than 60 characters")


if __name__ == "__main__":
    unittest.main()
