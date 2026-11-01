"""RF1239-3 tests: hike.create ids keep accented letters as plain letters; existing ids are never renamed.

Runs through prepare + apply of the H02 editor on the throwaway repo of test_hike_ops.HikeRepo (temp content,
synthetic titles, injected clock). Run: python3 -m unittest hass.tests.test_hike_ids -v
"""

import json

from hass.content_model import ID_RE
from hass.ops.hikes import MAX_ID_BASE
from hass.tests.test_editor import git
from hass.tests.test_hike_ops import HIKE, HikeTestCase

DAY = HIKE["date"]


class AccentedIdTests(HikeTestCase):
    def create(self, repo, title):
        before = {e["id"] for e in repo.community()["events"]}
        repo.run(("hike.create", {**HIKE, "title": title}))
        (new,) = [e for e in repo.community()["events"] if e["id"] not in before]
        self.assertEqual(new["title"], title)  # the title itself keeps its accents
        return new["id"]

    def test_accents_become_plain_letters(self):
        repo = self.repo()
        cases = (("Montaña de Oro", "montana-de-oro"), ("Café  walk!", "cafe-walk"),
                 ("Cafe\u0301 walk at Ñipomo", "cafe-walk-at-nipomo"), ("ﬁeld trip", "field-trip"),
                 ("ÜBER Peña", "uber-pena"))
        for title, slug in cases:
            with self.subTest(title=title):
                self.assertEqual(self.create(repo, title), f"hike-{DAY}-{slug}")

    def test_decomposed_and_precomposed_give_the_same_id(self):
        repo = self.repo()
        first = self.create(repo, "Caf\u00e9 walk")
        self.assertEqual(first, f"hike-{DAY}-cafe-walk")
        self.assertEqual(self.create(repo, "Cafe\u0301 walk"), first + "-2")  # same base, so the suffix rule applies

    def test_title_without_latin_letters_falls_back_to_date(self):
        repo = self.repo()
        self.assertEqual(self.create(repo, "山歩き"), f"hike-{DAY}")
        self.assertEqual(self.create(repo, "山歩き"), f"hike-{DAY}-2")
        self.assertEqual(self.create(repo, "ß øæ 🥑"), f"hike-{DAY}-3")  # no decomposition: hyphens, as before

    def test_collision_across_accent_forms_gets_a_suffix(self):
        repo = self.repo()
        plain = self.create(repo, "Montana de Oro")
        self.assertEqual(self.create(repo, "Montaña de Oro"), plain + "-2")
        self.assertEqual(self.create(repo, "MONTAÑA DE ORO"), plain + "-3")
        self.assertEqual([e["title"] for e in repo.community()["events"]],
                         ["Montana de Oro", "Montaña de Oro", "MONTAÑA DE ORO"])  # nothing overwritten

    def test_long_accented_title_keeps_the_length_limits(self):
        repo = self.repo()
        title = ("Señal á " * 10).strip()  # cut lands right after a hyphen, which must not stay at the end
        self.assertEqual(len(title), 79)  # within the 80-code-point event title limit (H01 TEXT_LIMITS)
        first = self.create(repo, title)
        self.assertTrue(first.startswith(f"hike-{DAY}-senal-a-senal-a"), first)
        self.assertEqual(len(first), MAX_ID_BASE - 1)  # ≤ 56: the 56th character was a hyphen and is dropped
        self.assertFalse(first.endswith("-"))
        second = self.create(repo, title)
        self.assertEqual(second, first + "-2")
        self.assertLessEqual(len(second), 64)
        self.assertTrue(ID_RE.fullmatch(second))

    def test_existing_slugged_id_is_never_renamed(self):
        repo = self.repo()
        self.create(repo, "Montaña de Oro")
        legacy = f"hike-{DAY}-monta-a-de-oro"  # an id stored by the old slug rule
        path = repo.wt / "hass/content/community.json"
        community = json.loads(path.read_text("utf-8"))
        community["events"][0]["id"] = legacy
        path.write_text(json.dumps(community, ensure_ascii=False, indent=2) + "\n", "utf-8")
        git(repo.wt, "commit", "-q", "-am", "event stored before RF1239-3")
        repo.run(("hike.update", {"id": legacy, "title": "Montaña de Oro bluffs", "meetingPoint": "Second lot"}))
        self.assertEqual([e["id"] for e in repo.community()["events"]], [legacy])
        event = repo.event(legacy)
        self.assertEqual((event["title"], event["meetingPoint"]), ("Montaña de Oro bluffs", "Second lot"))
        self.assertEqual(self.create(repo, "Montaña de Oro"), f"hike-{DAY}-montana-de-oro")  # new ids use the new rule
        self.assertEqual(repo.event(legacy)["title"], "Montaña de Oro bluffs")
