"""RF0015-11: a short complete send/email/text imperative ("send it") gets the social no-posting answer.

Run: python3 -B -m unittest hass.tests.test_social_send_short -q
"""
import unittest
from unittest import mock

from hass.skills import social
from hass.tests.test_skill_dispatch import skill_reply
from hass.tests.test_skills_social import SocialCase

SHORT = ("send it", "email this", "text that", "please send the caption", "send it now", "Send It.", "  EMAIL them please!  ",
         "text the announcement now please?", "send the post", "please text those")
ALLOWED = ("I will send it", "I'll send it", "write a caption so I can send it", "write a post for the honey", "post about the avocado",
           "don't send it", "resend it", "sender it", "write a post")


class RecognizerTests(unittest.TestCase):
    def test_short_send_imperatives(self):
        for text in SHORT:
            with self.subTest(text):
                self.assertTrue(social.wants_posting([text]))
                self.assertEqual(social.preflight("social.item", {}, mock.Mock(texts=[text])), social.NO_POSTING)

    def test_first_person_and_caption_prose_stay_allowed(self):
        for text in ALLOWED:
            with self.subTest(text):
                self.assertFalse(social.wants_posting([text]))

    def test_non_social_preflight_is_unchanged(self):
        self.assertIsNone(social.preflight("specials.show", {}, mock.Mock(texts=["send it"])))


class DispatchTests(SocialCase):
    def test_all_social_targets_and_slotless_requests(self):
        before = self.snapshot()
        with mock.patch("socket.socket", side_effect=AssertionError("network")):
            for text in ("send it", "email this", "text that"):
                for reply in (skill_reply("social.item"), skill_reply("social.hike"), skill_reply("social.maker"),
                              skill_reply("social.item", item="Hass avocado"), skill_reply("social.recap")):
                    with self.subTest(text=text, skill=reply["skill"], slots=reply["slots"]):
                        self.assertEqual(self.answered(text, reply), ("refused", [social.NO_POSTING]))
                        self.assertIsNone(self.live())
        self.assert_untouched(before)

    def test_social_batch_stops_before_caption_generation(self):
        before = self.snapshot()
        reply = {"calls": [{"skill": "social.item", "slots": {"item": "Hass avocado"}},
                           {"skill": "social.maker", "slots": {"maker": "Linn's"}}]}
        self.assertEqual(self.answered("please send the caption", reply), ("refused", [social.NO_POSTING]))
        self.assert_untouched(before)

    def test_ordinary_caption_still_answers(self):
        item = self.product("Hass avocado")
        self.assertEqual(self.answered("write a caption so I can send it", skill_reply("social.item", item="Hass avocado")),
                         ("answer", [self.want("item", item["id"])]))


if __name__ == "__main__":
    unittest.main()
