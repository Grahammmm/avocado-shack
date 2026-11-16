"""AV2007-07 (H05/H06): a store phone draft, show and history line spell the number as the site does.

Stored value stays ten digits; set, change, clear and undo lines read '(805) 555-0142'.
Run: python3 -B -m unittest hass.tests.test_phone_wording -v
"""

import copy
import unittest

from hass import conversation, sitegen, voice
from hass.chat import wording

EXPIRES = "2026-11-02T17:10:00+00:00"
STORE = {"name": "Avocado Shack"}


def _draft(before, after, collection="store", key="store"):
    return {"records": [{"collection": collection, "key": key, "before": before, "after": after}], "warnings": []}


def _phone(old, new):
    return _draft({**STORE, **({"phone": old} if old else {})}, {**STORE, **({"phone": new} if new else {})})


def _lines(draft, undo=False):
    return [voice.plain(x) for x in wording._record_lines(draft, undo=undo)]


class PhoneWordingTests(unittest.TestCase):
    def test_phone_set_change_clear_and_undo_lines_match_site(self):
        site = sitegen.phone_text
        self.assertEqual(site("8055550142"), "(805) 555-0142")
        cases = ((None, "8055550142", "nothing", "(805) 555-0142"),
                 ("8055550142", "8055550100", "(805) 555-0142", "(805) 555-0100"),
                 ("8055550142", None, "(805) 555-0142", "nothing"))
        for old, new, shown_old, shown_new in cases:
            with self.subTest(old=old, new=new):
                line = f"Avocado Shack, the phone number: from {shown_old} to {shown_new}"
                self.assertEqual(_lines(_phone(old, new)), [line])
                self.assertIn(line, voice.plain(conversation.proposal_text("ab12", _phone(old, new), EXPIRES)))
                undo = _lines(_phone(new, old), undo=True)  # the undo draft runs the other way
                self.assertEqual(undo, [f"Avocado Shack, the phone number: from {shown_new} to {shown_old}"])
                for text in [line, *undo]:
                    self.assertNotRegex(text, r"\d{10}")

    def test_new_phone_history_summary_contains_formatted_values(self):
        self.assertEqual(conversation._summary(_phone(None, "8055550142")),
                         "the phone number from nothing to (805) 555-0142 for Avocado Shack")
        self.assertEqual(conversation._summary(_phone("8055550142", "8055550100")),
                         "the phone number from (805) 555-0142 to (805) 555-0100 for Avocado Shack")
        self.assertEqual(conversation._summary(_phone("8055550142", None)),
                         "the phone number from (805) 555-0142 to nothing for Avocado Shack")
        # a non-phone store change and a non-store record keep the old label-only summary
        self.assertEqual(conversation._summary(_draft({"hours": "a"}, {"hours": "b"})), "the opening hours for the shop details")
        self.assertEqual(conversation._summary(_draft({"name": "A", "phone": "8055550142"}, {"name": "A", "phone": "8055550100"}, "makers", "m1")),
                         "the phone number for A")
        long = _draft({"name": "N" * 150, "phone": "8055550142"}, {"name": "N" * 150, "phone": "8055550100"})
        self.assertEqual(len(conversation._summary(long)), 120)

    def test_formatting_is_store_phone_only_and_pure(self):
        digits = "8055550142"
        for coll, field in (("products", "description"), ("products", "name"), ("makers", "phone"), ("store", "hours"), ("store", "fax")):
            with self.subTest(coll=coll, field=field):
                line = _lines(_draft({"name": "A", field: "x"}, {"name": "A", field: digits}, coll, "k"))[0]
                self.assertTrue(line.endswith(f"to {digits}"), line)
        draft = _phone("8055550142", "8055550100")
        before = copy.deepcopy(draft)
        first = _lines(draft)
        self.assertEqual(_lines(draft), first)
        conversation._summary(draft)
        self.assertEqual(draft, before)

    def test_missing_and_malformed_phone_values_use_existing_fallback(self):
        for bad in ("", "805555", "(805) 555-0142", "1055550142", "８０５５５５０１４２", 8055550142, ["8055550142"]):
            with self.subTest(bad=bad):
                self.assertIsNone(wording._phone_site(bad))
                lines = _lines(_phone(None, None) | {"records": [{"collection": "store", "key": "store", "before": STORE, "after": {**STORE, "phone": bad}}]})
                self.assertEqual(len(lines), 1)
                self.assertNotIn("(805) 555-0142 (805)", lines[0])
                conversation._summary(_draft(STORE, {**STORE, "phone": bad}))

    def test_historical_summary_is_not_backfilled(self):
        # readable old draft records (digits stored) show the site spelling without being altered
        draft = _phone(None, "8055550142")
        self.assertEqual(draft["records"][0]["after"]["phone"], "8055550142")
        self.assertIn("(805) 555-0142", _lines(draft)[0])
        self.assertEqual(draft["records"][0]["after"]["phone"], "8055550142")

    def test_strict_voice_accepts_phone_lines(self):
        text = conversation.proposal_text("ab12", _phone("8055550142", "8055550100"), EXPIRES)
        self.assertIn("(805) 555-0100", text)


if __name__ == "__main__":
    unittest.main()
