"""RF2325-3: a special's text is refused as a phone or email only for a real phone (10+ digits) or email.

Price ranges, years, date ranges and '2 @ $5' price notation are ordinary special text.
Run: python3 -m unittest hass.tests.test_special_contact_patterns -v
"""
import unittest

from hass.content_model import special_text_problem
from hass.skills import specials as sp

PHONE = "may not contain a phone number"
EMAIL = "may not contain an email address"
WEB = "may not contain a web address"


class SpecialContactPatterns(unittest.TestCase):
    def test_ordinary_text_is_allowed(self):
        for deal, text in ((False, "Honey 10 - 15 - 20 oz jars"), (True, "1.99 - 2.99 off"),
                           (False, "Dates 11-15 - 11-20 only"), (False, "Plums 2026 - 2027 harvest"),
                           (True, "2 @ $5 each"), (True, "Lemons 3 @ $1"), (True, "3 @ 2 for $5")):
            with self.subTest(text=text):
                self.assertIsNone(special_text_problem(text, deal=deal))

    def test_real_phone_is_refused(self):
        for text in ("call 805 555 0100", "call (805) 555-0100 today", "call 805.555.0100",
                     "call +1 805 555 0100", "call 8055550100"):
            with self.subTest(text=text):
                self.assertEqual(special_text_problem(text, deal=True), PHONE)

    def test_real_email_is_refused(self):
        self.assertEqual(special_text_problem("email me@shack.example", deal=True), WEB)
        self.assertEqual(special_text_problem("Figs @ the counter"), EMAIL)
        self.assertEqual(special_text_problem("write mike at shop dot com", deal=True), WEB)
        self.assertIn(special_text_problem("mike @ example.com", deal=True), (EMAIL, WEB))
        self.assertEqual(special_text_problem("me@shack", deal=True), EMAIL)

    def test_fullwidth_digits_pinned_to_main(self):
        # Main refuses fullwidth digits as a phone (\d is Unicode); this unit does not widen or narrow that.
        self.assertEqual(special_text_problem("call ８０５ ５５５ ０１００", deal=True), PHONE)

    def test_skill_rule_follows_the_same_patterns(self):
        for slots in ({"title": "Honey 10 - 15 - 20 oz jars", "deal": "2 @ $5 each"},
                      {"title": "Plums 2026 - 2027", "deal": "1.99 - 2.99 off"}):
            with self.subTest(slots=slots):
                self.assertIsNone(sp.rule_no_links_or_contact(slots, {}, None))
        for slots, plain in (({"title": "Figs", "deal": "call 805 555 0100"}, "a phone number"),
                             ({"title": "Figs", "deal": "me@shack.example for 2"}, "an email address")):
            with self.subTest(slots=slots):
                reply = sp.rule_no_links_or_contact(slots, {}, None)
                self.assertIn(plain, reply[0])
                self.assertEqual(reply[1], "policy")


if __name__ == "__main__":
    unittest.main()
