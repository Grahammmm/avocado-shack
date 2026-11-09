"""RF0834-11: a special's literal live/coming title is found before bulk and generic words are interpreted.

A special titled 'All Purpose Flour' is valid stored plain text; its 'All' must not read as 'take every special off'. Direct
lookup uses resolve_special; the dispatch tests run the PRODUCTION specials.edit / specials.remove declarations through the
real Conversation on the throwaway writer repo. Nothing is written before the owner's own yes.
Run: python3 -m unittest hass.tests.test_special_title_resolution -v
"""
import copy
import json
import types
import unittest
from datetime import date

from hass.skills import specials as sp
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import SkillCase, skill_reply

TODAY = date(2026, 11, 2)  # the SkillCase clock starts Monday 2026-11-02


def special(id, title, start="2026-11-02", end="2026-11-05", **extra):
    return dict(id=id, title=title, deal="2 for $5", start=start, end=end, **extra)


def ctx(*specials):
    store = {"specials": list(specials)}
    return types.SimpleNamespace(today=TODAY, content=types.SimpleNamespace(store=store, products=[]))


def lookup(query, *specials):
    status, found, reply = sp.resolve_special(ctx(*specials), query)
    return status, (found or {}).get("id"), reply


FLOUR = special("flour-offer", "All Purpose Flour")
JAM = special("jam-offer", "Jam")


class LiteralTitleLookupTests(unittest.TestCase):
    def test_literal_live_titles_win_over_bulk_and_generic_words(self):
        for title in ("All Purpose Flour", "Every Day Honey", "Everything Bagel Mix", "Each Peach", "Both Ways Tea", "The Special", "This One"):
            with self.subTest(title=title):
                item = special("lit-offer", title)
                for query in (title, title.upper(), "  " + title.lower().replace(" ", "   ") + "  "):
                    self.assertEqual(lookup(query, item, JAM)[:2], ("one", "lit-offer"), query)
        coming = special("coming-offer", "All Season Jam", start="2026-11-09", end="2026-11-12")
        self.assertEqual(lookup("all season jam", FLOUR, coming)[:2], ("one", "coming-offer"))

    def test_bulk_phrases_without_literal_match_still_refuse(self):
        for query in ("all of them", "both specials", "everything", "each one", "all"):
            with self.subTest(query=query):
                status, found, reply = lookup(query, FLOUR, JAM)
                self.assertEqual((status, found), ("all", None))
                self.assertIn("one at a time", reply)
        self.assertEqual(lookup("all of them")[0], "none")  # no live special at all: unchanged
        self.assertEqual(lookup("flour-offer", FLOUR, JAM)[:2], ("one", "flour-offer"))  # exact id still wins
        self.assertEqual(lookup("jam", FLOUR, JAM)[:2], ("one", "jam-offer"))  # ordinary term lookup unchanged
        self.assertEqual(lookup("the jam special", FLOUR, JAM)[:2], ("one", "jam-offer"))

    def test_literal_duplicates_and_expired_fallback_keep_safety(self):
        twin = special("flour-two", "all purpose flour")
        status, found, reply = lookup("All Purpose Flour", FLOUR, twin, JAM)
        self.assertEqual((status, found), ("several", None))
        self.assertIn("All Purpose Flour", reply)
        self.assertIn("all purpose flour", reply)
        self.assertNotIn("Jam", reply)
        # a finished special with the literal title is not given early precedence: bulk wording is still refused
        ended = special("old-flour", "All Purpose Flour", start="2026-10-01", end="2026-10-10")
        self.assertEqual(lookup("All Purpose Flour", ended, JAM)[:2], ("all", None))
        # a live literal title beats a finished one with the same title
        self.assertEqual(lookup("All Purpose Flour", ended, FLOUR, JAM)[:2], ("one", "flour-offer"))
        # blank, no content and unknown queries keep their documented results
        for blank in ("", "   ", None):
            self.assertEqual(lookup(blank, FLOUR, JAM)[0], "several")
        self.assertEqual(lookup("Quinoa", FLOUR, JAM)[0], "none")
        bare = types.SimpleNamespace(today=TODAY)
        self.assertEqual(sp.resolve_special(bare, "All Purpose Flour")[0], "none")
        self.assertEqual(sp.resolve_special(bare, "flour-offer")[:2], ("one", {"id": "flour-offer"}))

    def test_input_records_are_not_changed(self):
        specials = [copy.deepcopy(FLOUR), copy.deepcopy(JAM)]
        before = copy.deepcopy(specials)
        sp.resolve_special(ctx(*specials), "All Purpose Flour")
        self.assertEqual(specials, before)


class ProductionDispatchTests(SkillCase):
    SKILLS = (sp.SPECIALS_EDIT, sp.SPECIALS_REMOVE)

    def setUp(self):
        super().setUp()
        path = self.repo.wt / "hass/content/store.json"
        store = json.loads(path.read_text())
        store["specials"] = [dict(FLOUR, order=0), dict(JAM, order=1)]
        path.write_text(json.dumps(store) + "\n")
        git(self.repo.wt, "add", "hass/content/store.json")
        git(self.repo.wt, "commit", "-q", "-s", "-m", "synthetic specials seed")
        self.base = self.count()

    def ops(self, draft):
        return json.loads(draft["ops_json"])

    def backlog_rows(self):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'backlog'").fetchone():
            return 0
        return self.conv.db.execute("SELECT COUNT(*) FROM backlog").fetchone()[0]

    def test_production_remove_and_extend_literal_title_target_one_record(self):
        text = "take All Purpose Flour off the specials"
        self.script(text, skill_reply("specials.remove", special="All Purpose Flour"))
        draft, reply = self.propose(text)
        self.assertEqual(self.ops(draft), [{"op": "specials.remove", "args": {"id": "flour-offer"}}])
        self.assertNotIn("one at a time", reply)
        self.assertEqual(self.backlog_rows(), 0)  # not logged as an unsupported request
        self.nothing_written()
        self.assertEqual(self.say("no"), "rejected")
        self.replies()  # drain the cancel reply
        text = "extend the All Purpose Flour special to Saturday"
        self.script(text, skill_reply("specials.edit", special="All Purpose Flour", end="2026-11-07"))
        draft, reply = self.propose(text)
        self.assertEqual(self.ops(draft), [{"op": "specials.edit", "args": {"id": "flour-offer", "end": "2026-11-07"}}])
        self.nothing_written()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        specials = {s["id"]: s for s in json.loads((self.repo.wt / "hass/content/store.json").read_text())["specials"]}
        self.assertEqual(specials["flour-offer"]["end"], "2026-11-07")
        self.assertEqual(specials["flour-offer"]["title"], "All Purpose Flour")
        self.assertEqual(specials["jam-offer"], dict(JAM, order=1))

    def test_true_bulk_remove_is_still_refused_without_a_draft(self):
        text = "take all the specials off"
        self.script(text, skill_reply("specials.remove", special="all of them"))
        before = len(self.drafts())
        self.assertNotEqual(self.say(text), "proposed")
        self.assertEqual(len(self.drafts()), before)
        self.assertIn("one at a time", " ".join(self.replies()))
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
