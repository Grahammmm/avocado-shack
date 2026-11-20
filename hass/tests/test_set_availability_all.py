"""AV1052-04 tests: product.set_availability_all sets one availability word on a whole shelf and/or maker in one change.

Ops run through editor.prepare + editor.apply on a throwaway Git repo; the proposal text is built from the recorded draft.
Run: python3 -B -m unittest hass.tests.test_set_availability_all -v
"""

import json
import unittest
from datetime import datetime, timezone

from hass import auto_policy, editor, interpreter_prompt
from hass.chat import wording
from hass.ops import load_registry
from hass.tests.test_catalog_ops import CatalogTestCase, _req
from hass.tests.test_editor import git
from hass.tests.test_selection_checked import DatedRepo

ALL, SET, CLEAR, REVERT = "product.set_availability_all", "product.set_availability", "product.clear_availability", "history.revert"


class SetAvailabilityAllTests(CatalogTestCase):
    def setUp(self):
        self.r = DatedRepo()
        self.addCleanup(self.r.cleanup)
        self.r.now = datetime(2026, 11, 17, 20, tzinfo=timezone.utc)
        self.r.run(("store.confirm_selection", {"date": "2026-11-16"}))  # AV1922-02: the first recorded full check; words then carry their own day
        self.active = [p for p in self.r.products() if p["status"] == "active"]
        self.veg = [p for p in self.active if p["category"] == "vegetables"]
        self.maker = next(m for m in sorted({p.get("producerKey") for p in self.veg} - {None})
                          if sum(1 for p in self.active if p.get("producerKey") == m) >= 2)

    def product(self, pid):
        return next(p for p in self.r.products() if p["id"] == pid)

    def refused(self, *ops):
        before = (self.r.products(), self.r.store())
        reason = self.assertRejected(self.r, "refused", *ops)["reason"]
        self.assertEqual((self.r.products(), self.r.store()), before)
        return reason

    def test_registry_prompt_rule_and_closed_arguments(self):
        op = load_registry()[ALL]
        self.assertEqual(list(op.args), ["available", "shelf", "maker"])
        self.assertEqual([op.args[k].required for k in op.args], [True, False, False])
        rules = [r for r in interpreter_prompt.RULES if ALL in r]
        self.assertEqual(len(rules), 1)
        self.assertEqual(interpreter_prompt.RULES[interpreter_prompt.RULES.index(rules[0]) - 1][:25], "One message may hold seve")
        self.assertIn("Never expand it into one op per product.", rules[0])
        self.assertEqual(self.r.prepare(_req((ALL, {"shelf": "vegetables"})))["result"], "needs-details")  # available is required
        for args in ({"available": "maybe", "shelf": "vegetables"}, {"available": "yes", "shelf": "gadgets"},
                     {"available": "yes", "maker": "No Such Maker"}, {"available": "yes", "shelf": None},
                     {"available": "yes", "shelf": "vegetables", "ids": ["a"]}, {"available": "yes", "shelf": 3}):
            with self.subTest(args=args):
                self.assertEqual(self.r.prepare(_req((ALL, args)))["result"], "invalid")
        asked = self.r.prepare(_req((ALL, {"available": "yes"})))
        self.assertEqual(asked["result"], "needs-details")
        self.assertEqual(asked["missing"], ["shelf", "maker"])
        self.assertIn("Which shelf or maker should change?", str(asked))

    def test_shelf_maker_and_intersection_touch_only_changing_active_products(self):
        self.assertGreater(len(self.veg), 20)  # more than one 20-op message would hold
        hidden_id, held_id = self.veg[0]["id"], next(p["id"] for p in self.r.products() if p["status"] == "held")
        self.r.run(("product.hide", {"id": hidden_id}))
        keep = self.veg[1]
        self.r.run((ALL, {"available": "limited", "shelf": "vegetables", "maker": keep.get("producerKey")}) if keep.get("producerKey")
                   else (ALL, {"available": "limited", "shelf": "vegetables"}))
        before, store = self.r.products(), self.r.store()
        draft = self.r.run((ALL, {"available": "yes", "shelf": "vegetables"}))
        after = {p["id"]: p for p in self.r.products()}
        want = sorted(p["id"] for p in before if p["category"] == "vegetables" and p["status"] == "active" and p.get("available") != "yes")
        self.assertGreater(len(want), 20)
        self.assertEqual([r["key"] for r in draft["records"]], want)
        for p in before:
            if p["id"] in want:
                self.assertEqual(after[p["id"]], {**p, "available": "yes", "available_on": "2026-11-17"})
            else:
                self.assertEqual(after[p["id"]], p)  # hidden, held, already yes, other shelves: byte-identical
        self.assertEqual(after[hidden_id]["status"], "hidden")
        self.assertEqual(after[held_id], next(p for p in before if p["id"] == held_id))
        self.assertEqual(self.r.store(), store)  # the full-check day does not move
        self.assertEqual(self.r.store()["selection_checked_on"], "2026-11-16")
        # maker alone, and shelf + maker together (intersection)
        draft = self.r.run((ALL, {"available": "no", "maker": self.maker}))
        mine = {p["id"] for p in self.r.products() if p["status"] == "active" and p.get("producerKey") == self.maker}
        self.assertTrue({r["key"] for r in draft["records"]} <= mine)
        self.assertTrue(all(self.product(i)["available"] == "no" for i in mine))
        mixed = [p for p in self.r.products() if p["status"] == "active" and p["category"] != "vegetables" and p.get("producerKey") == self.maker]
        if mixed:
            self.r.run((ALL, {"available": "limited", "shelf": "vegetables", "maker": self.maker}))
            self.assertEqual({self.product(p["id"])["available"] for p in mixed}, {"no"})

    def test_no_change_is_refused_and_one_call_covers_many_records(self):
        self.r.run((ALL, {"available": "yes", "shelf": "vegetables"}))
        head, drafts = self.r.head(), self.r.drafts()
        self.assertIn("nothing to change", self.refused((ALL, {"available": "yes", "shelf": "vegetables"})))
        self.assertIn("No active products would change", self.refused((ALL, {"available": "no", "shelf": "flowers", "maker": self.maker})))
        self.assertEqual((self.r.head(), self.r.drafts()), (head, drafts))
        # a later refused op leaves the whole request unapplied
        self.assertEqual(self.r.prepare(_req((ALL, {"available": "no", "shelf": "vegetables"}), (SET, {"id": "no-such", "available": "yes"})))["result"], "not-found")
        self.assertEqual(self.r.head(), head)
        # 21 ops are still rejected before the editor; the bulk op is one call
        self.assertEqual(self.r.prepare(_req(*[(ALL, {"available": "limited", "shelf": "vegetables"})] * (editor.MAX_OPS + 1)))["result"], "invalid")

    def test_cancel_expire_stale_then_apply_and_undo_exact(self):
        before = self.r.products()
        draft = self.r.prepare(_req((ALL, {"available": "no", "shelf": "vegetables"})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(self.r.products(), before)  # prepare writes nothing; an unapproved draft changes nothing
        self.assertEqual(auto_policy.qualifies(draft["draft"]["ops"], [SET, "store.confirm_selection"], False), (False, "needs approval"))
        head = self.r.head()
        self.r.run(("product.edit", {"id": self.veg[0]["id"], "description": "Changed after the draft."}))
        stale = self.r.apply(draft["draft"])  # the base moved since prepare
        self.assertNotEqual(stale["result"], "applied", stale)
        self.assertNotEqual(self.r.head(), head)
        before = self.r.products()
        done = self.r.run((ALL, {"available": "no", "shelf": "vegetables"}))
        self.assertTrue(all(self.product(r["key"])["available"] == "no" for r in done["records"]))
        self.r.run(("product.edit", {"id": "photo-product-001", "description": "Later unrelated edit."}))
        self.r.run((REVERT, {"changeId": done["change_id"]}))
        after = {p["id"]: p for p in self.r.products()}
        for p in before:
            if p["id"] == "photo-product-001":
                self.assertEqual(after[p["id"]]["description"], "Later unrelated edit.")
            else:
                self.assertEqual(after[p["id"]], p)  # each product's word (or none) and available_on exactly as before
        # a later change to one touched product makes the undo conflict, and nothing is undone
        done = self.r.run((ALL, {"available": "limited", "shelf": "vegetables"}))
        self.r.run(("product.edit", {"id": done["records"][0]["key"], "description": "Edited after."}))
        state = self.r.products()
        self.assertEqual(self.r.prepare(_req((REVERT, {"changeId": done["change_id"]})))["result"], "refused")
        self.assertEqual(self.r.products(), state)

    def test_changed_words_get_their_own_day_and_the_full_check_stays(self):
        target = self.veg[0]["id"]
        path = self.r.wt / "hass/content/products.json"
        data = json.loads(path.read_text("utf-8"))
        rows = {p["id"]: p for p in data["products"]}
        rows[target].update({"available": "no", "available_on": "2026-01-02"})
        rows[self.veg[1]["id"]].pop("available_on", None)
        rows[self.veg[1]["id"]]["available"] = "limited"
        path.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        store_path = self.r.wt / "hass/content/store.json"
        store_data = json.loads(store_path.read_text("utf-8"))
        store_data["selection_checked_on"] = "2026-11-10"  # an older shelf check than today (2026-11-17)
        store_path.write_text(json.dumps(store_data, indent=2) + "\n", "utf-8")
        git(self.r.wt, "commit", "-qam", "stale words")
        store = self.r.store()
        draft = self.r.run((ALL, {"available": "yes", "shelf": "vegetables"}))
        self.assertEqual(self.product(target), {**rows[target], "available": "yes", "available_on": "2026-11-17"})
        self.assertEqual(self.product(self.veg[1]["id"])["available_on"], "2026-11-17")
        self.assertEqual(self.r.store(), store)
        self.assertIn("Available from today (your last full shelf check was Tuesday, November 10)", draft["warnings"])
        self.assertIn("nothing to change", self.refused((ALL, {"available": "yes", "shelf": "vegetables"})))  # same word is not refreshed


def _draft(n, word="yes", ops=(ALL,), warnings=()):
    records = [{"collection": "products", "key": f"p{i:03d}", "before": {"name": f"Item {i}", "available": "no"},
                "after": {"name": f"Item {i}", "available": word}} for i in range(n)]
    return {"ops": [{"op": o, "args": {}} for o in ops], "records": records, "warnings": list(warnings)}


class ProposalTests(unittest.TestCase):
    def lines(self, draft):
        return wording._record_lines(draft)

    def test_zero_one_ten_eleven_and_sixty_one(self):
        self.assertEqual(self.lines(_draft(0)), [])
        one = self.lines(_draft(1))
        self.assertEqual(one, ["1 product marked available=yes:", "  Item 0 (p000)"])
        ten = self.lines(_draft(10))
        self.assertEqual(len(ten), 11)
        self.assertNotIn("more", " ".join(ten))
        eleven = self.lines(_draft(11))
        self.assertEqual(eleven[0], "11 products marked available=yes:")
        self.assertEqual(eleven[-1], "  ... and 1 more")
        self.assertEqual(len(eleven), 12)
        sixty = self.lines(_draft(61))
        self.assertEqual((sixty[0], sixty[-1], len(sixty)), ("61 products marked available=yes:", "  ... and 51 more", 12))
        self.assertEqual(wording._summary(_draft(61)), "61 products marked available=yes")

    def test_names_ids_sorted_unicode_newlines_and_footer(self):
        draft = _draft(3, warnings=["adds Organic badge to p001"])
        for r, name in zip(draft["records"], ("Zucchini\nsquash", "Crème   fraîche — “A”", "Zucchini\nsquash")):
            r["before"]["name"] = r["after"]["name"] = name
        draft["records"].reverse()
        lines = self.lines(draft)
        self.assertEqual(lines[1:4], ["  Zucchini squash (p000)", "  Crème fraîche — “A” (p001)", "  Zucchini squash (p002)"])  # id order; ids tell twins apart
        self.assertTrue(lines[-1].startswith("Heads up:"))
        text = wording.proposal_text("abcd1234", draft, "2026-11-18T20:00:00+00:00")
        self.assertIn("3 products marked available=yes:", text)
        self.assertIn("yes", text.splitlines()[-1])

    def test_mixed_words_other_fields_and_ordinary_drafts_unchanged(self):
        draft = _draft(2, "no")
        draft["records"][1]["after"]["available"] = "limited"
        draft["records"][0]["after"]["description"] = "New words."
        draft["records"][0]["before"]["description"] = "Old words."
        draft["records"][0]["before"]["available"] = "yes"
        lines = self.lines(draft)
        self.assertEqual(lines[0], "1 product marked available=limited:")  # AVAILABILITY order
        self.assertIn("1 product marked available=no:", lines)
        self.assertEqual(len([ln for ln in lines if "description" in ln]), 1)
        self.assertFalse([ln for ln in lines if ln.startswith("Item") and "available" in ln])
        plain = _draft(2, ops=(SET,))
        full = self.lines(plain)
        self.assertEqual(len(full), 2)
        self.assertTrue(all("from" in ln for ln in full))  # no bulk op: every record keeps its full detail
        undo = {**_draft(2), "ops": [{"op": REVERT, "args": {}}]}
        self.assertEqual(len(self.lines(undo)), 2)
        net_same = _draft(1)
        net_same["records"][0]["before"]["available"] = "yes"  # touched twice, net no change: no group
        self.assertEqual(self.lines(net_same), [])


if __name__ == "__main__":
    unittest.main()
