"""RF0620-4 (H10) tests: the label reader never offers a value containing text the catalog refuses (<, >, $, {{, }}).

The value is dropped like a claim term (nothing stripped or rewritten); the other fields are still offered and a
dropped field is not a failure (last_error stays None). Fake transport only: no model, no network.
Run: python3 -B -m unittest hass.tests.test_label_reader_forbidden -v
"""

import unittest

from hass.content_model import FORBIDDEN_TEXT
from hass.label_reader import keep, question
from hass.tests.test_label_reader import reader, recorded
from hass.tests.test_photo_draft import JPG

CATS = ["fruit", "honey", "oils"]


class ForbiddenTextTests(unittest.TestCase):
    def test_markup_name_is_dropped_other_fields_kept(self):
        self.assertEqual(keep({"name": "Avocado <b>Oil</b>", "brand": "Etto"}, CATS), {"brand": "Etto"})
        self.assertEqual(keep({"name": "Avocado Oil", "brand": "Etto > Co"}, CATS), {"name": "Avocado Oil"})

    def test_a_price_inside_a_name_is_dropped(self):
        self.assertEqual(keep({"name": "Ranch Honey $12", "category": "honey"}, CATS), {"category": "honey"})
        self.assertEqual(keep({"name": "$12", "category": "honey"}, CATS), {"category": "honey"})  # existing price rule
        self.assertEqual(keep({"name": "Ranch Honey", "category": "honey"}, CATS),
                         {"name": "Ranch Honey", "category": "honey"})

    def test_template_braces_in_a_brand_are_dropped(self):
        for brand in ("{{brand}}", "Acme }}", "{{ Acme"):
            with self.subTest(brand):
                self.assertEqual(keep({"name": "Ranch Honey", "brand": brand}, CATS), {"name": "Ranch Honey"})

    def test_every_forbidden_item_drops_every_field(self):
        for bad in FORBIDDEN_TEXT:
            for field, value in (("name", f"Ranch {bad} Honey"), ("brand", f"Acme{bad}"), ("category", f"oils{bad}")):
                with self.subTest(bad=bad, field=field):
                    found = keep({"name": "Ranch Honey", "brand": "Acme", "category": "oils", field: value}, CATS)
                    self.assertNotIn(field, found)
                    self.assertEqual(len(found), 2)

    def test_a_category_with_forbidden_text_never_matches(self):
        for category in ("oils<", "<oils>", "OILS>", "{{oils}}", "$oils"):
            with self.subTest(category):
                self.assertEqual(keep({"name": "Avocado Oil", "category": category}, CATS), {"name": "Avocado Oil"})
        self.assertEqual(keep({"category": "OILS"}, CATS), {"category": "oils"})  # the plain value still matches

    def test_ampersand_hash_and_single_brace_are_kept_exactly(self):
        found = keep({"name": "Honey & Comb #2", "brand": "Smith & Sons {Est}"}, CATS)
        self.assertEqual(found, {"name": "Honey & Comb #2", "brand": "Smith & Sons {Est}"})

    def test_every_field_forbidden_is_empty(self):
        self.assertEqual(keep({"name": "<Honey>", "brand": "$Acme", "category": "honey}}"}, CATS), {})


class ForbiddenReadTests(unittest.TestCase):
    def test_read_offers_only_the_clean_category(self):
        labels, transport = reader(recorded({"name": "Avocado <b>Oil</b>", "brand": None, "category": "Oils"}))
        found = labels.read(JPG, CATS)
        self.assertEqual((found, labels.last_error, len(transport.calls)), ({"category": "oils"}, None, 1))
        self.assertEqual(question(found), "The label looks like \ue000oils\ue001. Is that right? Either way, tell me which product it is.")
        self.assertNotIn("Avocado", question(found))

    def test_read_with_every_field_forbidden_is_empty_without_an_error(self):
        labels, _ = reader(recorded({"name": "Ranch Honey $12", "brand": "{{brand}}", "category": "honey<"}))
        self.assertEqual((labels.read(JPG, CATS), labels.last_error), ({}, None))


if __name__ == "__main__":
    unittest.main()
