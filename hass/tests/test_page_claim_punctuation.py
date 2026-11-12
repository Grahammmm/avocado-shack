"""RF0145-13: a negator attached to a dash cannot hide a rejected page boast (hass/skills/pages.py).
Run: python3 -B -m unittest hass.tests.test_page_claim_punctuation -q
"""

import types
import unittest

from hass.skills import pages, shop

HEADLINE = {"headline": ["Best produce", "Come on in"]}
STORY = {"story": "We are the best at finding good food for everyone."}


def ctx(*texts):
    return types.SimpleNamespace(today="2026-11-08", store={}, texts=list(texts))


class DashAttachedNegators(unittest.TestCase):
    def test_attached_dash_negator_blocks_intro_headline_and_story(self):
        for dash in ("-", "\u2013", "\u2014"):
            for gap in ("", " "):
                d = gap + dash + gap
                for tail in ("not what we are", "never true", "don't say it", "dont say it", "isn't us", "isnt us"):
                    source = f"Best produce for everyone{d}{tail}"
                    lead = f"We are not{d}the best"
                    for text in (source, lead):
                        with self.subTest(text=text):
                            for plan, slots in ((pages.plan_home, HEADLINE), (pages.plan_about, STORY)):
                                with self.assertRaises(shop.SkillStop) as caught:
                                    plan(slots, ctx(text))
                                self.assertEqual(caught.exception.kind, "question")
                                self.assertIn("best", caught.exception.reply.casefold())
                            with self.assertRaises(shop.SkillStop):
                                pages.plan_home({"intro": "Best produce for everyone"}, ctx(text))

    def test_negator_tokens_do_not_match_inside_ordinary_words(self):
        for source in ("Say the best notable-produce", "the best northern-grown fruit", "the best cannotaloupe-stand"):
            with self.subTest(source=source):
                self.assertEqual([o["op"] for o in pages.plan_home(HEADLINE, ctx(source))], ["store.set_headline"])

    def test_independent_clauses_keep_existing_scope(self):
        ops = pages.plan_home(HEADLINE, ctx("We are the best. Do not-say organic."))
        self.assertEqual([o["op"] for o in ops], ["store.set_headline"])
        with self.assertRaises(shop.SkillStop):
            pages.plan_home(HEADLINE, ctx("Don't say: best"))

    def test_accepted_dash_text_is_not_rewritten(self):
        story = {"story": "We are the best\u2014friendly\u2014market for everyone."}
        ops = pages.plan_about(story, ctx("Say we are the best\u2014friendly\u2014market for everyone"))
        self.assertEqual(ops[0]["op"], "store.set_story")
        self.assertEqual(ops[0]["args"]["text"], story["story"])


if __name__ == "__main__":
    unittest.main()
