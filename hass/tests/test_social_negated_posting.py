"""RF2315-21: a negated posting imperative ("don't post it now") still gets a copy-only caption.

Run: python3 -B -m unittest hass.tests.test_social_negated_posting -q
"""
import unittest
from unittest import mock

from hass.skills import social
from hass.tests.test_skill_dispatch import skill_reply
from hass.tests.test_skills_social import SocialCase

COPY = ("Don't post it now; write a caption for the honey", "Do not publish it; just write a caption",
        "Don't send it to the club; write the announcement", "never publish it", "Please don't post it now",
        "DON\u2019T POST IT NOW; write a caption", "write a caption. Don't email it to the club", "don't post it",
        "write a caption, but never share it", "write a caption and do not schedule it")
STILL_REFUSED = ("Don't post it now; send it to the club", "send it to the club; don't post it now", "don't post it, but send it to everyone",
                 "don't post it and email this", "don't post it, then publish it", "Don't just post it now", "not only post it now",
                 "post it now", "don't post it now. Post it now.")


class Recognizer(unittest.TestCase):
    def test_negated_imperatives_allow_copy(self):
        for text in COPY:
            with self.subTest(text):
                self.assertFalse(social.wants_posting([text]))
                self.assertIsNone(social.preflight("social.item", {}, mock.Mock(texts=[text])))

    def test_positive_delivery_survives_other_negation(self):
        for text in STILL_REFUSED:
            with self.subTest(text):
                self.assertTrue(social.wants_posting([text]))
                self.assertEqual(social.preflight("social.item", {}, mock.Mock(texts=[text])), social.NO_POSTING)
        self.assertTrue(social.wants_posting(["don't post it now", "send it to the club"]))

    def test_non_social_unchanged(self):
        self.assertIsNone(social.preflight("specials.show", {}, mock.Mock(texts=["send it"])))


class Dispatch(SocialCase):
    def test_real_item_caption_with_dont_post(self):
        item = self.product("Hass avocado")
        before = self.snapshot()
        got = self.answered("Don't post it now; write a caption for the Hass avocado", skill_reply("social.item", item="Hass avocado"))
        self.assertEqual(got, ("answer", [self.want("item", item["id"])]))
        self.assert_untouched(before)

    def test_positive_delivery_still_refused_in_dispatch(self):
        self.product("Hass avocado")
        got = self.answered("Don't post it now; send it to the club", skill_reply("social.item", item="Hass avocado"))
        self.assertEqual(got, ("refused", [social.NO_POSTING]))


if __name__ == "__main__":
    unittest.main()
