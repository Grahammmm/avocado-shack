"""RF1721-12: a home destination the owner explicitly rejects is not a second photo destination for item.picture.

Run: python3 -B -m unittest hass.tests.test_item_picture_home_rejection -q
"""
import copy
import hashlib
import unittest
from types import SimpleNamespace

from hass.content_model import REPO_ROOT, load_and_validate
from hass.skills import item_picture as ip

CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
JAR = "reports/hass/newitem-1/synthetic/jar-white-sheet.jpg"
SHA = hashlib.sha256((REPO_ROOT / JAR).read_bytes()).hexdigest()
LEMONS, HELD = "photo-product-017", "photo-product-040"
SLOTS = {"item": LEMONS, "photo": SHA, "image_alt": "Lemons in a bowl"}


def ctx(*texts, content=CONTENT):
    return SimpleNamespace(today="2026-11-08", content=content, texts=list(texts))


def plan(*texts, slots=SLOTS, content=CONTENT):
    return ip.plan_picture(dict(slots), ctx(*texts, content=content))


def ask(*texts, slots=SLOTS):
    with unittest.TestCase().assertRaises(ip.Refusal) as caught:
        plan(*texts, slots=slots)
    return caught.exception.reply


def lemon_word():
    return next(p for p in CONTENT.products if p["id"] == LEMONS)["name"].split()[0].lower()


class HomeRejection(unittest.TestCase):
    def setUp(self):
        self.w = lemon_word()
        self.control = plan(f"use this photo for the {self.w}")

    def test_product_request_with_rejected_home_destination_plans_once(self):
        for text in (f"use this photo for the {self.w}, not the home page",
                     f"not the home page; use this photo for the {self.w}",
                     f"use this photo for the {self.w} instead of the home page",
                     f"use this photo for the {self.w} not the home page"):
            with self.subTest(text=text):
                before = copy.deepcopy(SLOTS)
                self.assertEqual(plan(text), self.control)
                self.assertEqual(SLOTS, before)

    def test_rejected_home_destination_alone_is_not_a_product_choice(self):
        for text in ("not the home page", "not the home page, thanks",
                     f"not the {self.w} and not the home page", "use this for plums, not the home page"):
            with self.subTest(text=text):
                self.assertEqual(ask(text), ip.ONE_PLACE)

    def test_home_rejection_is_occurrence_local(self):
        for text in (f"the {self.w}, not the home page, and the home page too",
                     f"not the home page; {self.w} and the home page",
                     f"the {self.w}, not only the home page",
                     f"the {self.w} and the home page",
                     f"use the main picture for the {self.w}"):
            with self.subTest(text=text):
                self.assertEqual(ask(text), ip.ONE_PLACE)

    def test_front_main_and_hyphenated_home_rejections(self):
        for dest in ("the front page", "front page", "home-page", "the home page", "the main picture", "main photo"):
            with self.subTest(dest=dest):
                self.assertEqual(plan(f"the {self.w}, not {dest}"), self.control)

    def test_rejected_home_does_not_hide_two_products(self):
        for text in (f"use this photo for the {self.w} and the plums, not the home page",
                     f"use this photo for the {self.w}, the plums, not the home page"):
            with self.subTest(text=text):
                self.assertEqual(ask(text), ip.ONE_AT_A_TIME)
        self.assertIn(ask("use it for both, not the home page"), (ip.ONE_AT_A_TIME, ip.ONE_PLACE))

    def test_existing_ambiguity_and_other_refusals_unchanged(self):
        self.assertEqual(ask(f"use this for the home page and the {self.w}"), ip.ONE_PLACE)
        self.assertEqual(ask(f"a later no: the {self.w}", f"not the home page, the plums"), ip.ONE_PLACE)
        held = dict(SLOTS, item=HELD)
        with self.assertRaises(ip.Refusal):
            plan(f"the {self.w}, not the home page", slots=held)


if __name__ == "__main__":
    unittest.main()
