"""RF2355-7: the maker no-price rule refuses singular/spelled dollars, cents, the cent sign, bucks and '5 a pound'."""
import unittest

from hass.skills import makers

REFUSED = ["1 dollar a jar", "a dollar a jar", "ten dollars a box", "50 cents each", "50\u00a2 each", "five bucks",
           "a buck each", "5 a pound", "TEN DOLLARS", "1,50 dollars", "$3", "per jar", "20 USD", "5 dollars"]
ALLOWED = ["grows 5 kinds of plums", "bucks county farm", "Dollarhide Ranch", "Cents-ible Farms",
           "family farm since 1952", "open 5 days a week"]


class MakerPriceWords(unittest.TestCase):
    def test_refused(self):
        for text in REFUSED:
            with self.subTest(text=text):
                with self.assertRaises(makers.Refusal) as cm:
                    makers.rule_no_price(text)
                self.assertEqual(cm.exception.reply, makers.PRICE_REPLY)
                with self.assertRaises(makers.Refusal) as cm:
                    makers._text(text, "story")
                self.assertEqual(cm.exception.reply, makers.PRICE_REPLY)

    def test_allowed(self):
        for text in ALLOWED:
            with self.subTest(text=text):
                makers.rule_no_price(text)


if __name__ == "__main__":
    unittest.main()
