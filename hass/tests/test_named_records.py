"""AV0007-05 (H05/H06): proposal, show and history lines name each record the way the site shows it.

A renamed record shows its new name with `(was <old name>)`; a hike also shows its Pacific day; products.available
reads in the site's words (Available today, Limited, Sold out); the stored summary carries the name.
Run: python3 -B -m unittest hass.tests.test_named_records -v
"""

import copy
import unittest

from hass import conversation, voice

EXPIRES = "2026-11-02T17:10:00+00:00"


def _draft(*records):
    return {"records": [{"collection": c, "key": k, "before": b, "after": a} for c, k, b, a in records], "warnings": []}


def _lines(*records):
    return voice.plain(conversation.proposal_text("ab12", _draft(*records), EXPIRES)).splitlines()[1:-2]


def _eggs(before, after):
    return _draft(("products", "photo-product-024", {"name": "Cal Poly eggs", **before}, {"name": "Cal Poly eggs", **after}))


class NamedRecordTests(unittest.TestCase):
    def test_each_collection_named_in_proposal_and_summary(self):
        cases = (
            (("products", "p1", {"name": "Cal Poly eggs", "description": "a"}, {"name": "Cal Poly eggs", "description": "b"}), "Cal Poly eggs, the description: from a to b"),
            (("makers", "m3", {"name": "Grove Co", "place": "a"}, {"name": "Grove Co", "place": "b"}), "Grove Co, the place: from a to b"),
            (("routeIdeas", "idea-coastal-loop", {"title": "Coastal loop", "distance": "3 mi"}, {"title": "Coastal loop", "distance": "4 mi"}), "Coastal loop, the distance: from 3 mi to 4 mi"),
            (("store", "store", {"hours": "a"}, {"hours": "b"}), "the shop details, the opening hours: from a to b"),
        )
        for record, line in cases:
            with self.subTest(collection=record[0]):
                self.assertEqual(_lines(record), [line])
                self.assertTrue(conversation._summary(_draft(record)).endswith(line.split(",")[0]))

    def test_rename_uses_after_and_was_before(self):
        edit = ("products", "p1", {"name": "Hass", "description": "a"}, {"name": "Reed", "description": "b"})
        self.assertEqual(_lines(edit), ["Reed (was Hass), the description: from a to b", "Reed (was Hass), the name: from Hass to Reed"])
        self.assertEqual(conversation._summary(_draft(edit)), "the description, the name for Reed (was Hass)")
        maker = ("makers", "m1", {"name": "Old Co"}, {"name": "New Co"})
        self.assertEqual(_lines(maker), ["New Co (was Old Co), the name: from Old Co to New Co"])
        route = ("routeIdeas", "r1", {"title": "Bluff"}, {"title": "Bluff Walk"})
        self.assertEqual(_lines(route), ["Bluff Walk (was Bluff), the title: from Bluff to Bluff Walk"])

    def test_no_was_on_add_remove_or_unchanged_name(self):
        added = ("products", "p1", None, {"name": "Reed"})
        self.assertEqual(_lines(added), ["A new product: Reed", "  the name: Reed"])
        removed = ("products", "p1", {"name": "Reed"}, None)
        self.assertEqual(_lines(removed), ["Remove the product Reed."])
        self.assertEqual(_lines(("products", "p1", {"name": "Reed", "description": "a"}, {"name": "Reed", "description": "b"})), ["Reed, the description: from a to b"])
        self.assertEqual(_lines(("products", "p1", {"name": "Hass"}, {"description": "b"}))[0].split(",")[0], "Hass")  # after has no name: the old one

    def test_pacific_day_and_dst(self):
        def hike(start, **extra):
            return ("events", "h1", {"title": "Ridge walk", "startsAt": start}, {"title": "Ridge walk", "startsAt": start, "bring": "x", **extra})
        for start, day in (("2026-11-08T04:30:00+00:00", "Saturday, Nov 7"),  # UTC date is the 8th; Pacific is still the 7th
                           ("2026-07-04T06:30:00+00:00", "Friday, Jul 3"),  # summer, PDT
                           ("2026-01-15T07:59:00+00:00", "Wednesday, Jan 14"),  # winter, PST
                           ("2026-11-01T09:30:00+00:00", "Sunday, Nov 1")):  # the fall-back morning
            with self.subTest(start=start):
                self.assertEqual(_lines(hike(start))[0], f"Ridge walk ({day}), what to bring: from nothing to x")
        for odd in ("2026-11-07T09:00:00", "soon", "", None, 5):  # naive, unreadable, missing, not text: no day, no exception
            with self.subTest(start=odd):
                self.assertEqual(_lines(hike(odd))[0], "Ridge walk, what to bring: from nothing to x")
        self.assertEqual(_lines(("events", "h1", None, {"title": "Dawn", "startsAt": "2026-11-08T17:00:00+00:00"}))[0], "A new hike: Dawn (Sunday, Nov 8)")

    def test_availability_owner_words_only_on_available(self):
        for old, new, shown in (("yes", "limited", "from Available today to Limited"), ("limited", "no", "from Limited to Sold out"),
                                (None, "yes", "from nothing to Available today")):
            with self.subTest(old=old, new=new):
                record = ("products", "photo-product-024", {"name": "Cal Poly eggs", "available": old}, {"name": "Cal Poly eggs", "available": new})
                self.assertEqual(_lines(record), [f"Cal Poly eggs, the shelf word: {shown}"])
        added = ("products", "p1", None, {"name": "Cal Poly eggs", "available": "no"})
        self.assertIn("  the shelf word: Sold out", _lines(added))
        for value, shown in (("maybe", "maybe"), ("No", "No"), (True, "yes"), (["no"], "no")):  # unknown strings and nonstrings keep their formatting
            with self.subTest(value=value):
                self.assertEqual(_lines(("products", "p1", {"name": "A", "available": "yes"}, {"name": "A", "available": value}))[0], f"A, the shelf word: from Available today to {shown}")
        self.assertEqual(_lines(("products", "p1", {"name": "A", "description": "yes"}, {"name": "A", "description": "no"})), ["A, the description: from yes to no"])
        self.assertEqual(_lines(("makers", "m1", {"name": "A", "available": "yes"}, {"name": "A", "available": "no"})), ["A, the shelf word: from yes to no"])  # a maker's field of the same name keeps its raw value

    def test_labels_do_not_mutate_the_draft(self):
        draft = _eggs({"available": "yes"}, {"available": "limited", "name": "Farm eggs"})
        before = copy.deepcopy(draft)
        conversation.proposal_text("ab12", draft, EXPIRES)
        conversation._summary(draft)
        self.assertEqual(draft, before)

    def test_summary_carries_the_name_and_keeps_the_cut(self):
        draft = _eggs({"available": "yes"}, {"available": "no"})
        self.assertEqual(conversation._summary(draft), "the shelf word for Cal Poly eggs")
        long = _draft(*[("products", f"p{i}", {"name": f"Product number {i}", "description": "a"}, {"name": f"Product number {i}", "description": "b"}) for i in range(9)])
        summary = conversation._summary(long)
        self.assertEqual((len(summary), summary[-3:]), (120, "..."))
        self.assertTrue(summary.startswith("the description for Product number 0; "))


if __name__ == "__main__":
    unittest.main()
