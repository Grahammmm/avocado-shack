"""RF1530-18 (H10) tests: a whole-value multiplied package size is not a product name or brand.

keep() and LabelReader.read() run with literal synthetic model replies and fake transports (no network, no model).
Run: python3 -B -m unittest hass.tests.test_label_reader_multiplied_sizes -v
"""

import json
import unittest

from hass.label_reader import LabelReader, keep, question

CATS = ["pantry", "fruit", "2 x 500 ml"]
SIZES = ["2 x 500 ml", "2x500ml", "2 X 0.5 L", "6 \u00d7 12 oz", "3 x 1,5 l", "2 x 500 ML.", "  2 x\t500   ml  ", "2 x 500\u00a0ml",
         "4 x 8 Fl. Oz"]
KEPT = ["2 x 500 ml Lemonade", "Lemonade 2x500ml", "Route 1 Honey", "7 Sisters Salsa", "V8", "X Farm", "12 oz Coffee",
        "2 x 500", "2 x 500 mls", "2 x 3 x 500 ml", "6-pack", "2 x 1/2 lb"]
JPG = b"\xff\xd8synthetic-bytes"
URL, MODEL = "http://127.0.0.1:11434", "vision-test"


class Fake:
    def __init__(self, *replies): self.replies, self.calls = list(replies), []  # noqa: E704

    def __call__(self, url, body, headers, timeout):
        self.calls.append(url)
        return self.replies.pop(0)


def envelope(api, answer):
    text = json.dumps(answer)
    if api == "openai":
        return 200, json.dumps({"choices": [{"index": 0, "finish_reason": "stop",
                                             "message": {"role": "assistant", "content": text}}]}).encode()
    return 200, json.dumps({"done": True, "message": {"role": "assistant", "content": text}}).encode()


class MultipliedSizes(unittest.TestCase):
    def test_multiplied_sizes_drop_independently_as_name_and_brand(self):
        for value in SIZES:
            with self.subTest(value=value):
                self.assertEqual(keep({"name": value, "brand": "Fixture Pantry", "category": "pantry"}, CATS),
                                 {"brand": "Fixture Pantry", "category": "pantry"})
                self.assertEqual(keep({"name": "Fixture Jam", "brand": value}, CATS), {"name": "Fixture Jam"})
                self.assertEqual(keep({"name": value, "brand": value}, CATS), {})

    def test_whole_value_boundary_keeps_real_names(self):
        for value in KEPT:
            with self.subTest(value=value):
                self.assertEqual(keep({"name": value}, CATS), {"name": value})
                self.assertEqual(keep({"brand": value}, CATS), {"brand": value})

    def test_spacing_and_previous_guard_precedence(self):
        self.assertEqual(keep({"name": "2 x 500\u2028ml"}, CATS), {})
        self.assertEqual(keep({"name": "2 x 500 ml organic"}, CATS), {})
        self.assertEqual(keep({"name": "2 x 500 ml", "brand": "null"}, CATS), {})
        for value in ["12 oz", "1.5 L", "1/2 lb", "$4.99"]:
            self.assertEqual(keep({"name": value}, CATS), {})

    def test_category_uses_only_its_existing_matching_rule(self):
        self.assertEqual(keep({"category": " 2 X 500  ML "}, CATS), {"category": "2 x 500 ml"})
        self.assertEqual(keep({"category": "6 x 12 oz"}, CATS), {})

    def test_both_api_decoders_filter_without_triggering_fallback(self):
        for api in ("ollama", "openai"):
            with self.subTest(api=api):
                spare = Fake(envelope(api, {"name": "Spare"}))
                fake = Fake(envelope(api, {"name": "2 x 500 ml", "brand": "Fixture Pantry", "category": "pantry"}))
                url = URL if api == "ollama" else "http://127.0.0.1:8010"
                labels = LabelReader(url, MODEL, transport=fake, api=api, fallback=LabelReader(url, "m2", transport=spare, api=api))
                found = labels.read(JPG, CATS)
                self.assertEqual(found, {"brand": "Fixture Pantry", "category": "pantry"})
                self.assertIsNone(labels.last_error)
                self.assertFalse(labels.last_fallback)
                self.assertEqual((len(fake.calls), len(spare.calls)), (1, 0))
                self.assertNotIn("500", question(found))
                fake = Fake(envelope(api, {"name": "2x500ml", "brand": "6 \u00d7 12 oz", "category": None}))
                labels = LabelReader(url, MODEL, transport=fake, api=api)
                self.assertEqual(labels.read(JPG, CATS), {})
                self.assertIsNone(labels.last_error)
                self.assertEqual(len(fake.calls), 1)

    def test_real_failed_primary_then_filtered_fallback_preserves_metadata(self):
        primary, spare = Fake((500, b"{}")), Fake(envelope("ollama", {"name": "2 x 500 ml", "brand": "Fixture Pantry"}))
        labels = LabelReader(URL, MODEL, transport=primary, fallback=LabelReader(URL, "m2", transport=spare))
        self.assertEqual(labels.read(JPG, CATS), {"brand": "Fixture Pantry"})
        self.assertEqual((len(primary.calls), len(spare.calls)), (1, 1))
        self.assertTrue(labels.last_fallback)
        self.assertIsNotNone(labels.last_primary_error)
        self.assertIsNone(labels.last_error)


if __name__ == "__main__":
    unittest.main()
