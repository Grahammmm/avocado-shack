"""AV1622-06 tests: product.add records the Pacific day it was added (addedOn); the browser shows New for 14 days.

Ops run on a throwaway Git repo with a linked writer worktree (test_catalog_ops.CatalogRepo) at a supplied clock; the
real storefront-mockup/shop.js runs under Node (hass/tests/fixtures/shop_new_driver.cjs) at supplied instants, with the
visitor's own time zone set far from Pacific. Nothing touches the checkout, the live service or the network.
Run: python3 -B -m unittest hass.tests.test_product_new -v
"""

import copy
import json
import os
import subprocess
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from hass import editor
from hass.content_model import SITE_DIR, Content, load_and_validate, shop_today, validate_products
from hass.tests.test_catalog_ops import NEW, CatalogRepo, CatalogTestCase, _req

DRIVER = Path(__file__).with_name("fixtures") / "shop_new_driver.cjs"
UTC = timezone.utc


def at(*ymdhm):
    return datetime(*ymdhm, tzinfo=UTC)


def run_at(repo, now, *ops):
    draft = editor.prepare(_req(*ops), state=str(repo.state), now=now)
    assert draft["result"] == "ok", draft
    result = editor.apply(draft["draft"]["change_id"], draft["draft"]["draft_hash"], state=str(repo.state), now=now)
    assert result["result"] == "applied", result
    return draft["draft"]


def badges(cases):
    env = {**os.environ, "TZ": "Pacific/Kiritimati"}  # the visitor's own zone must never matter
    done = subprocess.run(["node", str(DRIVER)], input=json.dumps(cases), capture_output=True, text=True, env=env,
                          timeout=60)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


def seen(product, instant):
    return badges([{"product": product, "now": instant.isoformat()}])[0]


class AddedOnTests(CatalogTestCase):
    def test_add_pacific_boundary(self):
        for instant, day in ((at(2026, 1, 15, 7, 59), "2026-01-14"), (at(2026, 1, 15, 8, 0), "2026-01-15"),
                             (at(2026, 7, 15, 6, 59), "2026-07-14"), (at(2026, 7, 15, 7, 0), "2026-07-15")):
            with self.subTest(instant=instant.isoformat()):
                repo = self.repo()
                draft = editor.prepare(_req(("product.add", NEW)), state=str(repo.state), now=instant)
                self.assertEqual(draft["result"], "ok", draft)
                self.assertEqual(draft["draft"]["records"][0]["after"]["addedOn"], day)

    def test_add_image_and_photo(self):
        repo = self.repo()
        run_at(repo, at(2026, 3, 1, 20), ("product.add", NEW))
        self.assertEqual(repo.products()[-1]["addedOn"], "2026-03-01")
        head, drafts = repo.head(), repo.drafts()
        for name, args in (("owner date", {**NEW, "name": "Dated quince", "addedOn": "2026-03-01"}),
                           ("duplicate", NEW), ("no picture", {k: v for k, v in NEW.items() if k != "image"})):
            with self.subTest(case=name):
                result = repo.prepare(_req(("product.add", args)))
                self.assertNotEqual(result["result"], "ok", result)
        self.assertEqual((repo.head(), repo.drafts()), (head, drafts))
        self.assertEqual(sum("addedOn" in p for p in repo.products()), 1)  # failed adds wrote none

    def test_migration_unchanged(self):
        content = load_and_validate(SITE_DIR.parent / "hass" / "content", SITE_DIR)
        active = [p for p in content.products if p["status"] == "active"]
        self.assertEqual(len(active), 170)
        self.assertFalse([p["id"] for p in content.products if "addedOn" in p])
        catalog = (SITE_DIR / "catalog-products.js").read_bytes()
        self.assertNotIn(b"addedOn", catalog)
        self.assertEqual(subprocess.run(["python3", "hass/sitegen.py", "--check"], cwd=SITE_DIR.parent,
                                        capture_output=True, text=True).returncode, 0)

    def test_edit_restore_undo_keep_date(self):
        repo = self.repo()
        old = "photo-product-001"
        repo.run(("product.hide", {"id": old}))
        repo.run(("product.restore", {"id": old}))
        repo.run(("product.edit", {"id": old, "description": "Still old, still no date."}))
        self.assertNotIn("addedOn", [p for p in repo.products() if p["id"] == old][0])
        draft = run_at(repo, at(2026, 3, 1, 20), ("product.add", NEW))
        new = "photo-product-175"
        repo.run(("history.revert", {"changeId": draft["change_id"]}))
        last = repo.products()[-1]
        self.assertEqual((last["status"], last["addedOn"]), ("hidden", "2026-03-01"))  # undo hides, keeps the date
        for op, args in (("product.restore", {}), ("product.edit", {"description": "Sweet when baked."}),
                         ("product.hide", {}), ("product.restore", {})):
            run_at(repo, at(2026, 9, 1, 20), (op, {"id": new, **args}))
            self.assertEqual(repo.products()[-1]["addedOn"], "2026-03-01", op)  # nothing restarts the clock
        self.assertNotIn("addedOn", repo.products()[0])


class DateValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content: Content = load_and_validate(SITE_DIR.parent / "hass" / "content", SITE_DIR)

    def problems(self, record):
        out = []
        validate_products(out, [record], self.content.makers, SITE_DIR)
        return [p for p in out if "addedOn" in p]

    def test_date_validation(self):
        base = copy.deepcopy(self.content.products[0])
        held = next((p for p in self.content.products if p["status"] == "held"), None)
        self.assertIsNotNone(held)
        tomorrow = (shop_today() + timedelta(days=1)).isoformat()
        for rec in (base, held):
            for good in ("2024-02-29", shop_today().isoformat()):
                self.assertEqual(self.problems({**rec, "addedOn": good}), [], good)
            self.assertEqual(self.problems(rec), [])  # absent is valid for every status
            for bad in ("2025-02-29", "2026-13-01", "2026-3-1", "20260301", "2026-03-01 ", "", None, 20260301, tomorrow):
                with self.subTest(status=rec["status"], value=bad):
                    self.assertTrue(self.problems({**rec, "addedOn": bad}))


class NewWindowTests(unittest.TestCase):
    def test_new_window(self):
        for added, name in (("2026-03-01", "winter into DST"), ("2026-10-25", "DST ending")):
            day = date.fromisoformat(added)
            for age, expect in ((-1, False), (0, True), (13, True), (14, False)):
                with self.subTest(case=name, age=age):
                    # noon Pacific on that day, as a UTC instant (UTC and Pacific dates agree at 20:00Z)
                    instant = datetime.combine(day + timedelta(days=age), datetime.min.time(), tzinfo=UTC) + timedelta(hours=20)
                    self.assertEqual("<span>New</span>" in seen({"name": "x", "addedOn": added}, instant), expect)

    def test_utc_and_pacific_disagree(self):
        product = {"name": "x", "addedOn": "2026-03-01"}
        for instant, expect in ((at(2026, 3, 2, 3, 0), True),    # 19:00 Pacific on 03-01, already 03-02 in UTC
                                (at(2026, 3, 15, 6, 59), True),  # 23:59 PDT on 03-14 (age 13)
                                (at(2026, 3, 15, 7, 0), False),  # 00:00 PDT on 03-15: age 14
                                (at(2026, 2, 28, 23, 0), False)):  # 15:00 Pacific on 02-28: before the add
            with self.subTest(instant=instant.isoformat()):
                self.assertEqual("<span>New</span>" in seen(product, instant), expect)

    def test_missing_invalid_future_fail_closed(self):
        now = at(2026, 3, 5, 20)
        for value in (None, "", "2026-02-30", "2026-3-1", 20260301, "2026-03-06"):
            with self.subTest(value=value):
                product = {"name": "x"} if value is None else {"name": "x", "addedOn": value}
                self.assertEqual(seen(product, now), "")


class BadgeCompositionTests(CatalogTestCase):
    def test_badge_composition_and_render_paths(self):
        now = at(2026, 3, 5, 20)
        plain, organic = {"name": "Quince"}, {"name": "Organic quince"}
        new = {"addedOn": "2026-03-01"}
        cases = [({**plain}, ""), ({**organic}, '<div class="food-badges"><span>Organic</span></div>'),
                 ({**plain, **new}, '<div class="food-badges"><span>New</span></div>'),
                 ({**organic, **new}, '<div class="food-badges"><span>Organic</span><span>New</span></div>')]
        got = badges([{"product": p, "now": now.isoformat()} for p, _ in cases])
        for (product, want), html in zip(cases, got):
            with self.subTest(product=product):
                self.assertEqual(html, want)
        # generator output -> shop.js: a product added through the op, read from the published catalog
        repo = self.repo()
        run_at(repo, at(2026, 3, 1, 20), ("product.add", {**NEW, "name": "Organic Test quince"}))
        record = [p for p in repo.catalog() if p["id"] == "photo-product-175"][0]
        self.assertEqual(record["addedOn"], "2026-03-01")
        self.assertNotIn("isNew", record)
        old = [p for p in repo.catalog() if p["id"] != "photo-product-175"]
        self.assertTrue(old and all("addedOn" not in p for p in old))
        self.assertEqual(seen(record, at(2026, 3, 14, 20)), '<div class="food-badges"><span>Organic</span><span>New</span></div>')
        self.assertEqual(seen(record, at(2026, 3, 15, 20)), '<div class="food-badges"><span>Organic</span></div>')
        self.assertEqual(seen(old[0], at(2026, 3, 2, 20)).count("New"), 0)
        # every render path (initial, filter, append) draws cards through card(), which draws badges() once
        source = (SITE_DIR / "shop.js").read_text("utf-8")
        self.assertEqual(source.count("food-badges"), 1)
        self.assertEqual(source.count("${badges(p)}"), 1)
        self.assertEqual(source.count("isNew("), 3)  # its definition, the call inside badges() and the one in orderedProducts() (AV0222-09)
