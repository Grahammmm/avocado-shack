"""AV1937-03 tests: ``maker.hide`` with ``withProducts: true`` hides a maker and its active products in one change.

Real ops on a throwaway CatalogRepo (see test_catalog_ops); approval/undo run through the H06 conversation setup.
Fixture: Etto (5 active products) gets one hidden product and one held product added to it, so the cascade must
leave those two exactly as they were.
Run: python3 -m unittest hass.tests.test_maker_hide_products -v
"""

import copy
import json
import os
import shutil
import unittest

from hass import auto_policy, conversation
from hass.content_model import SITE_DIR
from hass.interpreter_prompt import build
from hass.ops import load_registry
from hass.tests.test_catalog_ops import CatalogTestCase
from hass.tests.test_conversation import _ops
from hass.tests.test_editor import git
from hass.tests.test_interpreter_prompt import tiny_content
from hass.tests.test_undo import H06TestCase

KEY, BIG = "Etto", "Stepladder"  # BIG has more than five active products
HIDDEN, HELD = "photo-product-001", "photo-product-040"
REVERT = "history.revert"
PRODUCTS, MAKERS = "hass/content/products.json", "hass/content/makers.json"


def seed(repo):
    """Commit a fixture where HIDDEN (hidden) and HELD (held, with a hold) both name KEY besides its active products."""
    path = repo.wt / PRODUCTS
    data = json.loads(path.read_text("utf-8"))
    for p in data["products"]:
        if p["id"] in (HIDDEN, HELD):
            p["producerKey"] = KEY
        if p["id"] == HIDDEN:
            p["status"] = "hidden"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    git(repo.wt, "add", "-A")
    git(repo.wt, "commit", "-q", "-m", "fixture: hidden and held products of " + KEY)


def by_id(repo):
    return {p["id"]: p for p in repo.products()}


def active_ids(repo, key):
    products = json.loads((repo.wt / PRODUCTS).read_text("utf-8"))["products"]
    return sorted(p["id"] for p in products if p.get("producerKey") == key and p["status"] == "active")


def hide(key, **extra):
    return ("maker.hide", {"key": key, **extra})


class MakerHideProductsTests(CatalogTestCase):
    def test_true_hides_maker_and_only_its_active_products(self):
        repo = self.repo()
        seed(repo)
        ids, before = active_ids(repo, KEY), by_id(repo)
        self.assertEqual(len(ids), 5)
        others = {k: v for k, v in before.items() if k not in ids}
        makers_before = copy.deepcopy(repo.makers())
        draft = repo.prepare({"ops": [{"op": "maker.hide", "args": {"key": KEY, "withProducts": True}}]})["draft"]
        records = [(r["collection"], r["key"]) for r in draft["records"]]
        self.assertEqual(records, [("makers", KEY)] + [("products", i) for i in ids])  # maker first, then by id
        self.assertEqual(repo.apply(draft)["result"], "applied")
        after = by_id(repo)
        for pid in ids:
            self.assertEqual(after[pid], dict(before[pid], status="hidden"), pid)
        self.assertEqual({k: v for k, v in after.items() if k not in ids}, others)  # hidden, held, other makers' kept
        self.assertEqual(after[HELD]["status"], "held")
        self.assertEqual(after[HELD]["hold"], before[HELD]["hold"])
        self.assertEqual(repo.makers(), dict(makers_before, **{KEY: dict(makers_before[KEY], hidden=True)}))
        catalog = {p["id"] for p in repo.catalog()}
        self.assertTrue(catalog.isdisjoint(ids))

    def test_omitted_and_false_keep_active_product_refusal(self):
        repo = self.repo()
        seed(repo)
        ids = active_ids(repo, KEY)
        for extra in ({}, {"withProducts": False}):
            with self.subTest(extra=extra):
                result = self.assertRejected(repo, "refused", hide(KEY, **extra))
                self.assertTrue(all(pid in result["reason"] for pid in ids), result)
                self.assertNotIn(HIDDEN, result["reason"])  # hidden/held products are not "active"
                self.assertNotIn(HELD, result["reason"])

    def test_zero_active_products_and_repeat(self):
        repo = self.repo()
        repo.run(("maker.add", {"key": "Test Farm", "name": "Test Farm", "place": "Somewhere, California",
                                "story": "Grows things.", "url": "https://example.com/"}))
        repo.run(hide("Test Farm", withProducts=True))
        self.assertIs(repo.makers()["Test Farm"]["hidden"], True)
        result = self.assertRejected(repo, "refused", hide("Test Farm", withProducts=True))
        self.assertIn("already hidden", result["reason"])
        repo.run(("maker.restore", {"key": "Test Farm"}))
        self.assertNotIn("hidden", repo.makers()["Test Farm"])

    def test_unknown_missing_key_bad_flag_and_extra_args(self):
        repo = self.repo()
        result = self.assertRejected(repo, "not-found", hide("No Such Maker", withProducts=True))
        self.assertEqual(result["key"], "No Such Maker")
        self.assertRejected(repo, "needs-details", ("maker.hide", {"withProducts": True}))
        for bad in ("true", None, 1, 0):
            with self.subTest(bad=bad):
                self.assertRejected(repo, "invalid", hide(KEY, withProducts=bad))
        self.assertRejected(repo, "invalid", hide(KEY, withProducts=True, extra="x"))


class MakerHideConversationTests(H06TestCase):
    def setUp(self):
        super().setUp()
        seed(self.repo)
        self.ids = active_ids(self.repo, KEY)
        self.big = active_ids(self.repo, BIG)
        self.interp.mapping.update({
            "stop etto": _ops(hide(KEY, withProducts=True)),
            "stop big": _ops(hide(BIG, withProducts=True)),
            "edit etto": _ops(("product.edit", {"id": self.ids[0], "description": "Later edit."})),
            "edit other": _ops(("product.edit", {"id": "photo-product-002", "description": "Unrelated edit."}))})
        self.base = self.count()

    def statuses(self):
        return {p["id"]: p["status"] for p in self.content("products")["products"]}

    def generated(self):
        site = self.repo.wt / "storefront-mockup"
        read = lambda name, head: json.loads((site / name).read_text("utf-8").split("\n", 1)[0][len(head):].rstrip(";\n"))  # noqa: E731
        return (read("catalog-products.js", "const catalog="), read("producers.js", "const producers="),
                json.loads((site / "producers.json").read_text("utf-8")))

    def test_prepare_proposal_cancel_then_approve(self):
        self.assertGreater(len(self.big), 5)
        draft, reply = self.propose("stop big")
        self.assertIn(BIG, reply)
        self.assertTrue(all(pid in reply for pid in self.big), reply)  # every id, past the short summary
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assertEqual((self.commits(), self.drafts()[-1]["state"]), (0, "rejected"))
        self.assertTrue(all(self.statuses()[pid] == "active" for pid in self.big))
        self.assertEqual(self.say("yes"), "no-target")  # the cancelled draft cannot be approved
        self.replies()
        self.assertEqual(self.commits(), 0)
        draft, reply = self.propose("stop etto")
        self.assertTrue(all(pid in reply for pid in self.ids) and KEY in reply, reply)
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.assertEqual(self.commits(), 1)
        self.assertTrue(all(self.statuses()[pid] == "hidden" for pid in self.ids))
        self.assertEqual(self.statuses()[HELD], "held")
        catalog = (self.repo.wt / "storefront-mockup/catalog-products.js").read_text("utf-8")
        self.assertFalse(any(f'"{pid}"' in catalog for pid in self.ids))
        self.assertEqual(self.drafts()[-1]["state"], "verified")

    def test_undo_restores_maker_before_products(self):
        self.apply("edit other")  # regenerates the site files once, so they are the baseline
        products_before = self.content("products")
        makers_before = self.content("makers")
        generated = self.generated()
        self.apply("stop etto")
        self.assertEqual(self.say("undo"), "proposed")
        self.replies()
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.assertEqual(self.content("products"), products_before)  # hidden/held kept exactly
        self.assertEqual(self.content("makers"), makers_before)
        self.assertEqual(self.generated(), generated)  # same site output (the undo may order a record's keys differently)
        self.assertEqual(self.statuses()[HIDDEN], "hidden")
        self.assertEqual(self.statuses()[HELD], "held")

    def test_undo_conflict_and_missing_image_are_atomic(self):
        first = self.apply("stop etto")
        self.apply("edit etto")  # touches a product the change touched
        self.assertEqual(self.say(f"undo {first['code']}"), "not-drafted")
        [reply] = self.replies()
        self.assertIn("conflict", reply)
        self.assertTrue(all(self.statuses()[pid] == "hidden" for pid in self.ids))
        self.assertEqual(self.product(self.ids[0])["description"], "Later edit.")

    def test_unrelated_later_edit_survives_undo_and_maker_restore_alone_leaves_products(self):
        first = self.apply("stop etto")
        self.apply("edit other")
        self.assertEqual(self.say(f"undo {first['code']}"), "proposed")
        self.replies()
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.assertEqual(self.product("photo-product-002")["description"], "Unrelated edit.")
        self.assertTrue(all(self.statuses()[pid] == "active" for pid in self.ids))
        # maker.restore alone: hide again, then restore only the maker
        self.interp.mapping["restore maker"] = _ops(("maker.restore", {"key": KEY}))
        self.apply("stop etto")
        self.apply("restore maker")
        self.assertNotIn("hidden", self.content("makers")["makers"][KEY])
        self.assertTrue(all(self.statuses()[pid] == "hidden" for pid in self.ids))

    def test_missing_restored_image_refuses_the_whole_undo(self):
        first = self.apply("stop etto")
        site = self.repo.wt / "storefront-mockup"
        (site / "assets").unlink()  # replace the link to the real assets by links to each file
        shutil.copytree(SITE_DIR / "assets", site / "assets", copy_function=os.symlink)
        image = self.product(self.ids[0])["image"]
        (site / image).unlink()
        git(self.repo.wt, "add", "-A")
        git(self.repo.wt, "commit", "-q", "-m", "fixture: image file removed")
        self.assertEqual(self.say(f"undo {first['code']}"), "not-drafted")
        [reply] = self.replies()
        self.assertEqual(reply, "I can't find that photo. Could you send it again?")
        self.assertTrue(all(self.statuses()[pid] == "hidden" for pid in self.ids))
        self.assertEqual(self.product(self.ids[0])["status"], "hidden")


class RegistryAndPolicyTests(unittest.TestCase):
    def test_real_registry_prompt_and_no_auto_eligibility(self):
        registry = load_registry()
        self.assertEqual(list(registry["maker.hide"].args), ["key", "withProducts"])
        self.assertFalse(registry["maker.hide"].args["withProducts"].required)
        line = next(x for x in build(registry, tiny_content()).splitlines() if x.startswith("maker.hide("))
        self.assertEqual(line, "maker.hide(key: text, required; withProducts: bool)")
        self.assertNotIn("maker.hide", auto_policy.ELIGIBLE)
        call = {"op": "maker.hide", "args": {"key": KEY, "withProducts": True}}
        self.assertEqual(auto_policy.qualifies([call], list(auto_policy.ELIGIBLE) + ["maker.hide"], False),
                         (False, "needs approval"))


if __name__ == "__main__":
    unittest.main()
