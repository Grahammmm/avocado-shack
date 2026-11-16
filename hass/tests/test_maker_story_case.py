"""RF0005-2: a sentence-leading maker pronoun is replaced whatever its capitalization (synthetic text only)."""
import copy
import unittest

from hass.skills import makers as m
from hass.tests.test_skills_makers import ctx

N = "Synthetic Apiary"


class StoryWords(unittest.TestCase):
    def test_single_pronoun_any_case(self):
        for said, want in [
            ("they keep bees.", f"{N} keeps bees."), ("They keep bees.", f"{N} keeps bees."),
            ("THEY keep bees.", f"{N} keeps bees."), ("tHeY keep bees.", f"{N} keeps bees."),
            ("she keeps Bees 3 ways.", f"{N} keeps Bees 3 ways."), ("HE keeps café bees.", f"{N} keeps café bees."),
            ("their honey is dark.", f"{N}\u2019s honey is dark."), ("his honey is dark.", f"{N}\u2019s honey is dark."),
            ("HER honey is dark.", f"{N}\u2019s honey is dark."),
            ("they're small.", f"{N} is small."), ("they\u2019ve grown.", f"{N} has grown."),
            ("THEY'LL grow.", f"{N} will grow."), ("They\u2019Re small.", f"{N} is small."),
        ]:
            with self.subTest(said=said):
                self.assertEqual(m.story_words(said, N), want)

    def test_later_lowercase_sentences(self):
        self.assertEqual(m.story_words("they keep bees. their honey is dark.", N), f"{N} keeps bees. {N}\u2019s honey is dark.")
        self.assertEqual(m.story_words("They keep bees! their honey is dark? they sell it", N),
                         f"{N} keeps bees! {N}\u2019s honey is dark? {N} sells it.")
        self.assertEqual(m.story_words("  they keep   bees.  their honey is dark  ", N), f"{N} keeps bees. {N}\u2019s honey is dark.")

    def test_negative_controls_unchanged(self):
        for said, want in [
            ("Theywatch the hive.", "Theywatch the hive."), ("theirloom honey.", "theirloom honey."), ("theirs is nice.", "theirs is nice."),
            ("Honey and bread, they make both.", "Honey and bread, they make both."), ("It is dark.", "It is dark."),
            ("they watch the weather", "they watch the weather."),
            ("Honey, est. 1990. bees stay home.", "Honey, est. 1990. bees stay home."),
            ("Dr. smith keeps bees.", "Dr. smith keeps bees."),
            ('They keep bees. "they" is a word.', f'{N} keeps bees. "they" is a word.'),
        ]:
            with self.subTest(said=said):
                self.assertEqual(m.story_words(said, N), want)

    def test_titlecase_clause_limits_unchanged(self):
        self.assertEqual(m.story_words("They want to bake and sell bread.", N), f"{N} wants to bake and sell bread.")
        self.assertEqual(m.story_words("They bake and sell bread.", N), f"{N} bakes and sells bread.")


class PlanAddEdit(unittest.TestCase):
    def test_add_rewrites_lowercase_story(self):
        ops = m.plan_add({"name": N, "place": "Atascadero, California", "story": "they keep bees. their honey is dark."}, ctx())
        self.assertEqual([o["op"] for o in ops], ["maker.add"])
        self.assertEqual(ops[0]["args"]["story"], f"{N} keeps bees. {N}\u2019s honey is dark.")
        self.assertEqual(ops[0]["args"]["name"], N)

    def test_edit_rewrites_lowercase_story(self):
        ops = m.plan_edit({"maker": "Etto", "story": "they started in a small kitchen and now dry pasta slowly"}, ctx())
        self.assertEqual(ops, [{"op": "maker.edit", "args": {"key": "Etto", "story": "Etto started in a small kitchen and now dries pasta slowly."}}])

    def test_edit_noop_when_stored_story_equals_result(self):
        said = "they started in a small kitchen and now dry pasta slowly"
        done = {"maker": "Etto", "story": said}
        content = copy.deepcopy(ctx().content)
        content.makers["Etto"]["story"] = "Etto started in a small kitchen and now dries pasta slowly."
        with self.assertRaises(m.Refusal):
            m.plan_edit(done, ctx(content=content))

    def test_no_price_check_runs_on_rewritten_story(self):
        with self.assertRaises(m.Refusal):
            m.plan_add({"name": N, "place": "Atascadero, California", "story": "they sell honey for $5 a jar."}, ctx())


if __name__ == "__main__":
    unittest.main()
