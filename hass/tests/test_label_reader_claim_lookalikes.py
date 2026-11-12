"""RF2210-11 (H10) tests: a claim word hidden behind a lookalike letter is dropped from a label read, field by field,
and nothing offered is transliterated. Synthetic fake transports only; no model, no network.
Run: python3 -B -m unittest hass.tests.test_label_reader_claim_lookalikes -q
"""

import json
import unittest

from hass.label_reader import LabelReader, keep, question
from hass.tests.test_photo_draft import JPG

CATS = ["tea", "eggs", "organic tea"]
A, O = "\u0430", "\u043e"  # Cyrillic a, o
LOOKALIKES = ("Org" + A + "nic Tea", "C" + A + "ge-Free Eggs", "Pr" + O + "biotic Tea",
              "Org\u03b1nic Tea".replace("\u03b1", A), "\u1d0frganic Tea")  # last: small-cap o (claims.skeleton map)
URL = "http://127.0.0.1:11434"


class Fake:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, url, body, headers, timeout):
        self.calls.append(json.loads(body))
        return self.reply


def ollama(found):
    return 200, json.dumps({"done": True, "message": {"role": "assistant", "content": json.dumps(found)}}).encode()


def openai(found):
    return 200, json.dumps({"choices": [{"index": 0, "finish_reason": "stop",
                                         "message": {"role": "assistant", "content": json.dumps(found)}}]}).encode()


class LookalikeTests(unittest.TestCase):
    def test_claim_lookalikes_are_dropped_in_all_fields(self):
        for bad in LOOKALIKES:
            with self.subTest(bad=bad):
                self.assertEqual(keep({"name": bad, "brand": "Etto", "category": "tea"}, CATS),
                                 {"brand": "Etto", "category": "tea"})
                self.assertEqual(keep({"name": "Plain Tea", "brand": bad}, CATS), {"name": "Plain Tea"})
                self.assertEqual(keep({"name": "Plain Tea", "category": bad}, [bad, "tea"]), {"name": "Plain Tea"})

    def test_clean_unicode_names_are_not_transliterated(self):
        names = ("Cuv\u00e9e Tea", "\u0427\u0430\u0439 \u0414\u043e\u043c", "Pl" + A + "in  Tea", "\u65e5\u672c\u8336")
        want = ("Cuv\u00e9e Tea", "\u0427\u0430\u0439 \u0414\u043e\u043c", "Pl" + A + "in Tea", "\u65e5\u672c\u8336")
        for raw, expected in zip(names, want):
            with self.subTest(raw=raw):
                row = {"name": raw, "brand": "Etto", "category": "Tea"}
                self.assertEqual(keep(row, CATS), {"name": expected, "brand": "Etto", "category": "tea"})
                self.assertEqual(row["name"], raw)  # input untouched

    def test_old_guards_remain(self):
        for bad in ("Organic Tea", "\uff2f\uff52\uff47\uff41\uff4e\uff49\uff43 Tea", "Org\u00e0nic Tea", "Cage\u2010Free Eggs",
                    "Org\u200banic Tea", "Org\u2028anic Tea"):
            with self.subTest(bad=bad):
                self.assertEqual(keep({"name": bad, "brand": "Etto"}, CATS), {"brand": "Etto"})

    def test_real_reads_drop_lookalikes_for_both_apis(self):
        for api, wrap, url in (("ollama", ollama, URL), ("openai", openai, "http://127.0.0.1:8010")):
            with self.subTest(api=api):
                fake = Fake(wrap({"name": LOOKALIKES[0], "brand": "Etto", "category": "tea", "origin": "X"}))
                labels = LabelReader(url, "m", transport=fake, api=api)
                found = labels.read(JPG, CATS)
                self.assertEqual((found, labels.last_error, len(fake.calls)), ({"brand": "Etto", "category": "tea"}, None, 1))
                self.assertIn("Etto (tea)", question(found))
                self.assertNotIn(A, question(found))

    def test_all_claim_fields_filter_cleanly_without_fallback(self):
        every = {"name": LOOKALIKES[0], "brand": LOOKALIKES[1], "category": LOOKALIKES[2]}
        spare = Fake(ollama({"name": "Spare Tea"}))
        labels = LabelReader("http://127.0.0.1:8010", "m", transport=Fake(openai(every)), api="openai",
                             fallback=LabelReader(URL, "m2", transport=spare))
        self.assertEqual((labels.read(JPG, [LOOKALIKES[2]]), labels.last_error, labels.last_fallback, spare.calls),
                         ({}, None, False, []))
        failing = LabelReader("http://127.0.0.1:8010", "m", transport=Fake((500, b"")), api="openai",
                              fallback=LabelReader(URL, "m2", transport=Fake(ollama(every | {"brand": "Etto"}))))
        self.assertEqual((failing.read(JPG, CATS), failing.last_fallback), ({"brand": "Etto"}, True))

    def test_dropping_claim_does_not_rewrite_or_add_facts(self):
        row = {"name": LOOKALIKES[0], "brand": "Etto"}
        found = keep(row, CATS)
        self.assertEqual(found, {"brand": "Etto"})
        self.assertNotIn("name", found)
        self.assertEqual(row, {"name": LOOKALIKES[0], "brand": "Etto"})
        self.assertNotIn(LOOKALIKES[0], question(found))
        self.assertNotIn("Organic", question(found))


if __name__ == "__main__":
    unittest.main()
