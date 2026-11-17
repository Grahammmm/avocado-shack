"""RF1025-13 (H10) tests: a standalone fractional package weight is not a product name or brand.

keep() and LabelReader.read() run with literal synthetic model replies and fake transports (no network, no model).
Run: python3 -B -m unittest hass.tests.test_label_reader_fractions -v
"""

import copy
import json
import unittest

from hass.label_reader import LabelReader, keep, question

CATS = ["pantry", "fruit", "1/2 lb"]
FRACTIONS = ["1/2 lb", "1 1/2 oz", "½ lb", "¼ oz", "⅔ lb", "1⁄2 lb", "1 / 2 lb", "1/2 LB.", "3/4 Fl. Oz", "1 ½ lb",
             "  1/2   lb  "]
KEPT = ["1/2 lb Coffee", "Half Moon Honey", "Route 1 Honey", "7 Sisters Salsa", "V8", "Oz Farm", "½ lb Butter",
        "1/2 lb Coffee 1/2 lb"]
JPG = b"\xff\xd8synthetic-bytes"
URL, MODEL = "http://127.0.0.1:11434", "vision-test"


class Fake:
    def __init__(self, reply): self.reply, self.calls = reply, []  # noqa: E704

    def __call__(self, url, body, headers, timeout):
        self.calls.append(url)
        return self.reply


def envelope(api, answer):
    text = json.dumps(answer)
    if api == "openai":
        return 200, json.dumps({"choices": [{"index": 0, "finish_reason": "stop",
                                             "message": {"role": "assistant", "content": text}}]}).encode()
    return 200, json.dumps({"done": True, "message": {"role": "assistant", "content": text}}).encode()


class FractionSizes(unittest.TestCase):
    def test_fractional_sizes_are_not_name_or_brand(self):
        for value in FRACTIONS:
            with self.subTest(value=value):
                self.assertEqual(keep({"name": value, "brand": "Fixture Pantry", "category": "pantry"}, CATS),
                                 {"brand": "Fixture Pantry", "category": "pantry"})
                self.assertEqual(keep({"name": "Fixture Jam", "brand": value}, CATS), {"name": "Fixture Jam"})

    def test_fraction_size_recognition_is_whole_value_only(self):
        for value in KEPT:
            with self.subTest(value=value):
                self.assertEqual(keep({"name": value}, CATS), {"name": value})
                self.assertEqual(keep({"brand": value}, CATS), {"brand": value})

    def test_existing_integer_decimal_and_no_letter_rules_unchanged(self):
        for value in ["12 oz", "1.5 L", "$4.99", "1/2", "½", "1 1/2", "012345678905"]:
            with self.subTest(value=value):
                self.assertEqual(keep({"name": value}, CATS), {})
        self.assertEqual(keep({"name": 5, "brand": None}, CATS), {})
        self.assertEqual(keep({"name": "1/2 lb organic"}, CATS), {"printed_claims": ["1/2 lb organic"]})  # quarantined, never a name

    def test_category_does_not_use_name_amount_filter(self):
        self.assertEqual(keep({"category": " 1/2  LB "}, CATS), {"category": "1/2 lb"})
        self.assertEqual(keep({"category": "1/2 lb"}, ["pantry"]), {})

    def test_input_purity_and_determinism(self):
        result = {"name": "1 1/2 oz", "brand": "Half Moon Honey", "category": "pantry"}
        before, cats = copy.deepcopy(result), list(CATS)
        first = keep(result, CATS)
        self.assertEqual(first, keep(result, CATS))
        self.assertEqual((result, CATS), (before, cats))
        self.assertEqual(first, {"brand": "Half Moon Honey", "category": "pantry"})


class RealReads(unittest.TestCase):
    def read(self, api, answer):
        fake = Fake(envelope(api, answer))
        labels = LabelReader(URL if api == "ollama" else "http://127.0.0.1:8010", MODEL, transport=fake, api=api)
        return labels, labels.read(JPG, CATS), fake

    def test_real_label_reads_filter_fractional_values_on_both_backends(self):
        for api in ("ollama", "openai"):
            with self.subTest(api=api):
                labels, found, fake = self.read(api, {"name": "1/2 lb", "brand": "Fixture Pantry", "category": "pantry"})
                self.assertEqual(found, {"brand": "Fixture Pantry", "category": "pantry"})
                self.assertIsNone(labels.last_error)
                self.assertFalse(labels.last_fallback)
                self.assertEqual(len(fake.calls), 1)
                self.assertNotIn("1/2", question(found))

    def test_all_filtered_label_is_clean_empty_result_not_retry(self):
        for api in ("ollama", "openai"):
            with self.subTest(api=api):
                labels, found, fake = self.read(api, {"name": "1 1/2 oz", "brand": "½ lb", "category": None})
                self.assertEqual(found, {})
                self.assertIsNone(labels.last_error)
                self.assertEqual(len(fake.calls), 1)
        bad = Fake((200, b"not json"))
        labels = LabelReader(URL, MODEL, transport=bad)
        self.assertEqual(labels.read(JPG, CATS), {})
        self.assertIsNotNone(labels.last_error)


if __name__ == "__main__":
    unittest.main()
