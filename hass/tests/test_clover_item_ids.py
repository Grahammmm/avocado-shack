"""RF1201-9: parse_item admits only string Clover item IDs. Synthetic dictionaries only.
Run: python3 -B -m unittest hass.tests.test_clover_item_ids
"""
import copy
import unittest

from hass.clover import mapper as m
from hass.clover import sku

MSG = "an item from the till has no id or name"


def raw(item_id, name="Thing"):
    return {"id": item_id, "name": name}


class ItemIdTests(unittest.TestCase):
    def test_non_string_ids_raise_content_free_map_error(self):
        for bad in (None, True, False, 0, 123, 1.5, [], ["A1"], {}, {"id": "A1"}):
            with self.subTest(bad=bad), self.assertRaises(m.MapError) as cm:
                m.parse_item(raw(bad))
            self.assertEqual(str(cm.exception), MSG)

    def test_mixed_batch_skips_bad_ids_and_keeps_good_neighbors(self):
        batch = [raw("A1", "One"), raw(None), raw(123), raw(True), raw(["B"]), raw({}), raw("B1", "Two")]
        before = copy.deepcopy(batch)
        items, skipped = m.parse_items(batch)
        self.assertEqual(skipped, 5)
        self.assertEqual([i.id for i in items], ["A1", "B1"])
        self.assertTrue(all(type(i.id) is str for i in items))
        self.assertEqual(batch, before)
        self.assertEqual(m.parse_items([raw(None), raw(5)]), ([], 2))

    def test_string_id_boundaries_are_preserved(self):
        for good in ("a", "A" * 32, "00123", "None", "True", "aB9"):
            with self.subTest(good=good):
                self.assertIs(m.parse_item(raw(good)).id, good)
        bad = (None, "", "A" * 33, " A1", "A1 ", "A/1", "A1\n", "\uff21\uff11")
        for b in bad:
            with self.subTest(bad=b), self.assertRaises(m.MapError):
                m.parse_item(raw(b))
        with self.assertRaises(m.MapError):
            m.parse_item({"name": "Thing"})

    def test_mapped_batch_remains_safe_for_sku_sort(self):
        healthy = [raw("B1", "Alpha"), raw("A1", "Beta")]
        mixed = [healthy[0], raw(None, "Gamma"), raw(7, "Delta"), healthy[1]]
        items, skipped = m.parse_items(mixed)
        self.assertEqual(skipped, 2)
        healthy_items, _ = m.parse_items(healthy)
        self.assertEqual(sku.generate_sku("New item", "pantry", items), "AS-PAN-NEW-ITEM-01")
        self.assertEqual(sku.generate_sku("New item", "pantry", items),
                         sku.generate_sku("New item", "pantry", healthy_items))
        taken = m.parse_item({"id": "C1", "name": "Other", "sku": "AS-PAN-NEW-ITEM-01"})
        self.assertEqual(sku.generate_sku("New item", "pantry", items + [taken]), "AS-PAN-NEW-ITEM-02")


if __name__ == "__main__":
    unittest.main()
