"""RF0015-19: a rejected home destination keeps a Unicode saved-product-name selection in item.picture.

Synthetic products and photo ids only; nothing is read, written or sent.
Run: python3 -B -m unittest hass.tests.test_item_picture_unicode_home_rejection -q
"""
import copy
import unicodedata
import unittest
from types import SimpleNamespace

from hass.content_model import REPO_ROOT, load_and_validate
from hass.skills import item_picture as ip

CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
LEMONS = "photo-product-017"
PHOTO = "ab" * 32
NFC_ACAI = "A\u00e7a\u00ed"
NFD_ACAI = unicodedata.normalize("NFD", NFC_ACAI)


def named(name, pid=LEMONS, **fields):
    content = copy.deepcopy(CONTENT)
    next(p for p in content.products if p["id"] == pid).update(name=name, **fields)
    return content


def slots(pid=LEMONS):
    return {"item": pid, "photo": PHOTO, "image_alt": "Photo of the product"}


def plan(content, *texts, pid=LEMONS):
    ctx = SimpleNamespace(today="2026-11-08", content=content, texts=list(texts))
    return ip.plan_picture(slots(pid), ctx)


def reply(content, *texts, pid=LEMONS):
    with unittest.TestCase().assertRaises(ip.Refusal) as caught:
        plan(content, *texts, pid=pid)
    return caught.exception.reply


class UnicodeHomeRejection(unittest.TestCase):
    def test_same_turn_unicode_name_with_rejected_home_plans_once(self):
        for name in ("柚子", "茶", NFC_ACAI):
            content = named(name)
            control = plan(content, f"use this photo for {name}")
            self.assertEqual(len(control), 1)
            self.assertEqual(control[0]["op"], "product.set_photo")
            for text in (f"use this photo for {name}, not the home page",
                         f"not the home page; use this photo for {name}",
                         f"use this photo for {name} instead of the home page"):
                with self.subTest(name=name, text=text):
                    self.assertEqual(plan(content, text), control)

    def test_unicode_name_comparison_is_normalized_not_rewritten(self):
        for saved, spoken in ((NFC_ACAI, NFD_ACAI), (NFD_ACAI, NFC_ACAI), (NFC_ACAI, NFC_ACAI.lower())):
            content = named(saved)
            before = copy.deepcopy(content.products)
            with self.subTest(saved=saved, spoken=spoken):
                out = plan(content, f"use this photo for {spoken}, not the home page")
                self.assertEqual(out[0]["args"]["imageAlt"], "Photo of the product")
                self.assertEqual(content.products, before)

    def test_non_choice_and_wrong_name_still_ask(self):
        content = named("茶")
        for text in ("not the home page", "use this photo for 柚子, not the home page",
                     "use this photo for 茶叶, not the home page", "not 茶, not the home page",
                     "yes, not the home page"):
            with self.subTest(text=text):
                self.assertEqual(reply(content, text), ip.ONE_PLACE)

    def test_other_destination_occurrence_still_blocks(self):
        content = named("柚子")
        for text in ("柚子, not the home page, and the home page too",
                     "not the home page; 柚子 and the home page",
                     "柚子, not only the home page",
                     "use this photo for 柚子 and the home page"):
            with self.subTest(text=text):
                self.assertEqual(reply(content, text), ip.ONE_PLACE)

    def test_two_products_not_hidden_by_home_rejection(self):
        content = named("柚子")
        self.assertEqual(reply(content, "photos for 柚子 and plums, not the home page"), ip.ONE_AT_A_TIME)

    def test_ascii_path_unchanged(self):
        content = named("Lemons")
        self.assertEqual(len(plan(content, "use this photo for Lemons, not the home page")), 1)
        self.assertEqual(reply(content, "use this photo for Lemons and the home page"), ip.ONE_PLACE)


if __name__ == "__main__":
    unittest.main()
