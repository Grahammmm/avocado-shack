"""RF0620-3 (H13): store.set_hours / set_address / set_intro treat a new value that differs from the current one only
by spacing as "already says that"; case changes and reorders stay real changes. Throwaway writer repo only.
Run: python3 -B -m unittest hass.tests.test_store_spacing_only -v
"""

import unittest

from hass.content_model import DEFAULT_INTRO
from hass.tests.test_store_ops import SET_ADDRESS, SET_HOURS, StoreTestCase, _req

SET_INTRO = "store.set_intro"
STORED = ["Monday–Saturday 9am–6pm", "Closed Sunday"]


class SpacingOnlyTests(StoreTestCase):
    def refused(self, repo, call):
        head, drafts, commits = repo.head(), repo.drafts(), repo.commits()
        out = repo.prepare(_req(call))
        self.assertEqual(out["result"], "refused", out)
        self.assertEqual((repo.head(), repo.drafts(), repo.commits(), repo.status()), (head, drafts, commits, ""))
        return out["reason"]

    def hours_repo(self):
        repo = self.repo()
        repo.run((SET_HOURS, {"hours": STORED}))
        return repo

    def test_hours_spacing_only_is_refused_naming_the_stored_lines(self):
        repo = self.hours_repo()
        for hours in (["Monday–Saturday 9am–6pm", "Closed  Sunday"], ["Monday–Saturday   9am–6pm", "Closed  Sunday"]):
            with self.subTest(hours=hours):
                self.assertEqual(self.refused(repo, (SET_HOURS, {"hours": hours})),
                                 "store hours are already " + " / ".join(STORED))
        self.assertEqual(repo.store()["hours"], STORED)

    def test_hours_exact_repeat_still_refused_with_the_same_text(self):
        repo = self.hours_repo()
        self.assertEqual(self.refused(repo, (SET_HOURS, {"hours": list(STORED)})),
                         "store hours are already Monday–Saturday 9am–6pm / Closed Sunday")

    def test_hours_reorder_case_and_extra_line_are_changes(self):
        for hours in ([STORED[1], STORED[0]], [STORED[0], "closed sunday"], [*STORED, "Holidays 10am–2pm"]):
            with self.subTest(hours=hours):
                repo = self.hours_repo()
                repo.run((SET_HOURS, {"hours": hours}))
                self.assertEqual(repo.store()["hours"], hours)

    def test_hours_saved_text_keeps_the_owners_spacing(self):
        repo = self.repo()
        hours = ["Monday–Saturday  9am–6pm", "Closed Sunday"]
        repo.run((SET_HOURS, {"hours": hours}))
        self.assertEqual(repo.store()["hours"], hours)
        self.assertEqual(self.refused(repo, (SET_HOURS, {"hours": STORED})), "store hours are already " + " / ".join(hours))

    def test_address_spacing_only_is_refused(self):
        repo = self.repo()
        repo.run((SET_ADDRESS, {"streetAddress": "1023 Example Street"}))
        refusal = "store address is already 1023 Example Street, Morro Bay"
        self.assertEqual(self.refused(repo, (SET_ADDRESS, {"streetAddress": "1023  Example Street"})), refusal)
        self.assertEqual(self.refused(repo, (SET_ADDRESS, {"streetAddress": "1023  Example Street", "town": "Morro  Bay"})),
                         refusal)
        self.assertEqual(self.refused(repo, (SET_ADDRESS, {"streetAddress": "1023 Example Street"})), refusal)

    def test_address_with_a_real_change_saves_the_exact_text(self):
        repo = self.repo()
        repo.run((SET_ADDRESS, {"streetAddress": "1023 Example Street"}))
        repo.run((SET_ADDRESS, {"streetAddress": "1023  Example Street", "town": "Cayucos"}))
        store = repo.store()
        self.assertEqual((store["streetAddress"], store["town"]), ("1023  Example Street", "Cayucos"))

    def test_address_case_change_is_a_change(self):
        repo = self.repo()
        repo.run((SET_ADDRESS, {"town": "morro bay"}))
        self.assertEqual(repo.store()["town"], "morro bay")

    def test_intro_spacing_only_is_refused_against_the_default(self):
        repo = self.repo()
        self.assertNotIn("intro", repo.store())
        spaced = DEFAULT_INTRO.replace(" ", "  ", 1)
        self.assertNotEqual(spaced, DEFAULT_INTRO)
        self.assertEqual(self.refused(repo, (SET_INTRO, {"text": spaced})), "the intro already says that")
        self.assertEqual(self.refused(repo, (SET_INTRO, {"text": DEFAULT_INTRO})), "the intro already says that")

    def test_intro_spacing_only_is_refused_against_the_stored_intro(self):
        repo = self.repo()
        repo.run((SET_INTRO, {"text": "Fresh from the coast."}))
        self.assertEqual(self.refused(repo, (SET_INTRO, {"text": "Fresh  from   the coast."})), "the intro already says that")
        self.assertEqual(self.refused(repo, (SET_INTRO, {"text": "Fresh from the coast."})), "the intro already says that")
        self.assertEqual(repo.store()["intro"], "Fresh from the coast.")

    def test_intro_tab_is_never_drafted(self):
        # A tab is a control character: the text kind rejects it before the op, so it can never become a change.
        repo = self.repo()
        repo.run((SET_INTRO, {"text": "Fresh from the coast."}))
        head, drafts = repo.head(), repo.drafts()
        out = repo.prepare(_req((SET_INTRO, {"text": "Fresh\tfrom the coast."})))
        self.assertEqual(out["result"], "invalid", out)
        self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, drafts, ""))

    def test_intro_case_change_is_a_change(self):
        repo = self.repo()
        repo.run((SET_INTRO, {"text": "Fresh from the coast."}))
        repo.run((SET_INTRO, {"text": "Fresh From The Coast."}))
        self.assertEqual(repo.store()["intro"], "Fresh From The Coast.")


if __name__ == "__main__":
    unittest.main()
