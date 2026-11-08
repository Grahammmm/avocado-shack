"""AV0222-09: products the browser shows as New come first (newest first); everything else keeps catalog order.
Runs the real storefront-mockup/shop.js in node:vm with synthetic catalogs and a fixed Pacific clock."""

import copy, json, shutil, subprocess, unittest  # noqa: E401
from pathlib import Path

DRIVER = Path(__file__).resolve().parent / "fixtures" / "shop_order_driver.cjs"
NODE = shutil.which("node")
NOW = "2026-11-07T20:00:00Z"  # Pacific day 2026-11-07


def rec(pid, added=None, **kw):
    p = {"id": pid, "name": f"Item {pid}", "brand": "Brand A", "producerKey": "a", "category": "pantry",
         "description": "d", "image": "assets/x.png"}
    if added is not None:
        p["addedOn"] = added
    p.update(kw)
    return p


def drive(catalog, **kw):
    before = copy.deepcopy(catalog)
    out = subprocess.run([NODE, str(DRIVER), json.dumps({"catalog": catalog, "now": NOW, **kw})],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert catalog == before  # the catalog is never mutated
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node not installed")
class NewOrderTests(unittest.TestCase):
    def test_new_first_newest_first_and_stable_ties(self):
        cat = [rec("o1", "2026-01-01"), rec("n1", "2026-11-01"), rec("o2"), rec("n2", "2026-11-05"),
               rec("n3", "2026-11-01"), rec("o3", "2026-10-01")]
        self.assertEqual(drive(cat)["ids"], ["n2", "n1", "n3", "o1", "o2", "o3"])

    def test_no_new_preserves_every_position(self):
        bad = [None, 20261107, "2026-02-30", "2026-1-5", "2026-11-08", "2026-10-24", "2026-10-25x", ""]
        cat = [rec(f"p{i}", b) for i, b in enumerate(bad)] + [rec("z", "2020-01-01"), rec("a", "2025-01-01")]
        for c in (cat, [], cat[:1]):
            self.assertEqual(drive(c)["ids"], [p["id"] for p in c])

    def test_pacific_boundary_matches_badge(self):
        # Pacific day is 2026-11-07: age 14 and a future date are not New; ages 0 and 13 are.
        cat = [rec("age14", "2026-10-24"), rec("age13", "2026-10-25"), rec("age0", "2026-11-07"), rec("future", "2026-11-08")]
        self.assertEqual(drive(cat)["ids"], ["age0", "age13", "age14", "future"])
        # UTC is already 2026-11-08 but Pacific is still 2026-11-07, so "2026-11-08" is still not New.
        self.assertEqual(drive(cat, now="2026-11-08T05:00:00Z")["ids"], ["age0", "age13", "age14", "future"])
        # A leap day inside the window.
        r = drive([rec("x"), rec("leap", "2028-02-29"), rec("mar", "2028-03-01")], now="2028-03-10T20:00:00Z")
        self.assertEqual(r["ids"], ["mar", "leap", "x"])

    def test_filters_keep_order(self):
        cat = [rec("o1", brand="Brand B", producerKey="b"), rec("n1", "2026-11-01", brand="Brand B", producerKey="b"),
               rec("o2", category="dairy"), rec("n2", "2026-11-05", category="dairy"),
               rec("n3", "2026-11-03", brand="Brand B", producerKey="b", category="dairy")]
        self.assertEqual(drive(cat)["ids"], ["n2", "n3", "n1", "o1", "o2"])
        self.assertEqual(drive(cat, category="dairy")["ids"], ["n2", "n3", "o2"])
        self.assertEqual(drive(cat, brand="Brand B")["ids"], ["n3", "n1", "o1"])
        self.assertEqual(drive(cat, q="item n")["ids"], ["n2", "n3", "n1"])
        self.assertEqual(drive(cat, q="zzz")["ids"], [])
        self.assertEqual(drive(cat, **{"from": "b"}, producers={"b": {}})["ids"], ["n3", "n1", "o1"])

    def test_available_filter_keeps_order(self):
        av = {"availabilityState": "yes", "availabilityCheckedOn": "2026-11-07"}
        cat = [rec("o1", **av), rec("o2"), rec("n1", "2026-11-01"), rec("n2", "2026-11-05", **av)]
        fr = {"selectionCheckedOn": "2026-11-07"}
        self.assertEqual(drive(cat, freshness=fr, avail=True)["ids"], ["n2", "o1"])
        self.assertEqual(drive(cat, freshness=fr)["ids"], ["n2", "n1", "o1", "o2"])

    def test_append_after_many_new_records_has_no_duplicates(self):
        for n in (0, 1, 12, 13, 25):
            cat = [rec(f"o{i}") for i in range(30)] + [rec(f"n{i:02d}", f"2026-11-0{1 + i % 7}") for i in range(n)]
            r = drive(cat, loads=1)
            self.assertEqual(r["rendered"], r["ids"][:24], n)
            self.assertEqual(len(set(r["rendered"])), len(r["rendered"]))
            r = drive(cat, loads=9)
            self.assertEqual(r["rendered"], r["ids"], n)
            self.assertEqual(len(r["ids"]), 30 + n)

    def test_pacific_day_rollover_repaints_without_duplicates(self):
        # n_old is New on 11-07 (age 13) but not on 11-08: the append repaints from the top in the new order.
        cat = [rec(f"o{i}") for i in range(20)] + [rec("n_old", "2026-10-25"), rec("n_new", "2026-11-06")]
        r = drive(cat, loads=1, nowAfter="2026-11-08T20:00:00Z")
        self.assertEqual(r["ids"][:3], ["n_new", "o0", "o1"])
        self.assertEqual(r["rendered"], r["ids"][:24])
        self.assertEqual(len(set(r["rendered"])), len(r["rendered"]))
        self.assertEqual(r["newBadges"], 1)

    def test_item_uses_sorted_index(self):
        cat = [rec(f"o{i}") for i in range(30)] + [rec(f"n{i:02d}", f"2026-11-0{1 + i % 7}") for i in range(14)]
        # o0 is pushed to sorted index 14, o29 to 43; n13 is promoted from the source tail to index 1.
        for item, limit in (("o0", 24), ("n13", 12), ("o29", 48), ("o%C3%A9", 12), ("missing", 12), ("", 12)):
            r = drive(cat, search=f"?item={item}")
            self.assertEqual(r["limit"], limit, item)
            if item in ("o0", "n13", "o29"):
                self.assertIn(item, r["rendered"])


if __name__ == "__main__":
    unittest.main()
