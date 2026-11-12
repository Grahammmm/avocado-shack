"""RF1900-9: repeated ASCII spaces after `per` cannot bypass the item.edit no-price refusal.

Run: python3 -B -m unittest hass.tests.test_item_price_spaces -q
"""

import unittest

from hass.content_model import REPO_ROOT, load_and_validate
from hass.interpret_check import PRICE_REPLY
from hass.skills import items as it
from hass.tests.test_skills_items import CONTENT, SITE, ctx_for

PID = "photo-product-001"
UNITS = ("lb", "pound", "ounce", "oz", "dozen", "each")
SLOTS = ("name", "description", "display_brand", "image_alt")


class PerUnitSpacing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = ctx_for(load_and_validate(CONTENT, SITE))

    def plan(self, **slots):
        return it.plan_edit({"item": PID, **slots}, self.ctx)

    def test_repeated_ascii_spaces_per_unit_refuse_in_all_edit_fields(self):
        for spaces in (" ", "  ", "   "):
            for unit in UNITS:
                for text in (f"Sold per{spaces}{unit}.", f"SOLD PER{spaces}{unit.upper()}"):
                    for slot in SLOTS:
                        with self.subTest(text=text, slot=slot):
                            with self.assertRaises(it.Refusal) as caught:
                                self.plan(**{slot: text})
                            self.assertEqual(caught.exception.reply, PRICE_REPLY)

    def test_zero_spaces_and_nonmatching_words_are_not_prices(self):
        for text in ("Sold perpound.", "Sold per  poundcake.", "A pepper  pound of fun.", "super  pound", "perennial  each"):
            with self.subTest(text=text):
                [op] = self.plan(description=text)
                self.assertEqual(op["args"]["description"], text)

    def test_repeated_spaces_in_ordinary_text_survive_byte_exact(self):
        text = "Sweet  and   juicy, picked  fresh."
        [op] = self.plan(description=text)
        self.assertEqual(op["args"]["description"], text)

    def test_tabs_and_newlines_keep_the_plain_text_reply(self):
        for sep in ("\t", "\n"):
            with self.subTest(sep=repr(sep)):
                with self.assertRaises(it.Refusal) as caught:
                    self.plan(description=f"Sold per{sep}pound.")
                self.assertNotEqual(caught.exception.reply, PRICE_REPLY)
                self.assertIn("plain words", caught.exception.reply)


if __name__ == "__main__":
    unittest.main()
