"""AV1109-03 tests: product.set_restock keeps one active product's private restock day (restock_on), reversibly.

Window and argument cases call the op on a loaded copy of the real content with an explicit ``ctx.now``; draft, apply
and undo cases go through editor.prepare + editor.apply on a throwaway Git repo (DatedRepo). Nothing is published.
Run: python3 -B -m unittest hass.tests.test_restock_op -v
"""

import copy
import json
import unittest
from datetime import date, datetime, timedelta, timezone

from hass import sitegen
from hass.content_model import REPO_ROOT, SITE_DIR, ContentError, load_and_validate, load_content, shop_today, validate
from hass.ops import NeedsDetails, NotFound, OpContext, Refused, check_args, load_registry
from hass.tests.test_catalog_ops import CatalogTestCase, _req
from hass.tests.test_editor import git
from hass.tests.test_selection_checked import DatedRepo

SET, REVERT = "product.set_restock", "history.revert"
SENTINEL = "2031-07-19"  # a day no baseline public file contains (asserted below)
FIXED = date(2026, 11, 9)


def _ctx(now):
    return OpContext(now=now, site_dir=SITE_DIR, settings={})


def _midday(day):
    return datetime(day.year, day.month, day.day, 20, tzinfo=timezone.utc)  # midday Pacific (PST or PDT)


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.content = load_content()

    def problems(self, value=None, *, status=None, key="restock_on"):
        content = copy.deepcopy(self.content)
        product = next(p for p in content.products if p["status"] == ("held" if status == "held" else "active"))
        product["status"] = product["status"] if status is None else status  # an active record hidden here
        product[key] = value
        try:
            validate(content, SITE_DIR)
        except ContentError as exc:
            return str(exc)
        return ""

    def test_schema_optional_iso_only_and_unknown_still_refused(self):
        self.assertFalse(any("restock_on" in p for p in self.content.products))  # absent is the committed state
        validate(copy.deepcopy(self.content), SITE_DIR)
        for status in ("active", "hidden", "held"):
            with self.subTest(status=status):
                self.assertEqual(self.problems("2026-11-20", status=status), "")
        for day in ("2001-01-01", "2099-12-31", "2028-02-29"):  # persisted days are shape-checked only: past and far load
            with self.subTest(day=day):
                self.assertEqual(self.problems(day), "")
        for bad in (None, "", "20261120", "2026-W47-1", " 2026-11-20", "2026-11-20 ", "2026-11-20T00:00", "2027-02-29",
                    "2026-13-01", 20261120, True, ["2026-11-20"], {"day": "2026-11-20"}):
            with self.subTest(bad=bad):
                self.assertIn("restock_on: must be a real date YYYY-MM-DD", self.problems(bad))
        self.assertIn("restock", self.problems("2026-11-20", key="restock"))  # unknown keys are still refused
        self.assertIn("restock_onn", self.problems("2026-11-20", key="restock_onn"))


class DirectOpTests(unittest.TestCase):
    """The op on a loaded content copy: refusals leave the content exactly as it was."""

    def setUp(self):
        self.content = load_content()
        self.op = load_registry()[SET]
        active = [p for p in self.content.products if p["status"] == "active"]
        self.pid = active[0]["id"]

    def call(self, now, **args):
        before = copy.deepcopy(self.content)
        problems, missing = check_args(self.op, {"id": self.pid, **args}, self.content.makers, SITE_DIR)
        self.assertEqual((problems, missing), ([], []))
        result = self.op.apply(self.content, {"id": self.pid, **args}, _ctx(now))
        if not isinstance(result, list):
            self.assertEqual(self.content, before)  # no partial write on any refusal
        return result

    def product(self):
        return next(p for p in self.content.products if p["id"] == self.pid)

    def test_set_window_uses_pacific_ctx_today(self):
        cases = (  # (now, Pacific today)
            (datetime(2026, 11, 10, 7, 30, tzinfo=timezone.utc), date(2026, 11, 9)),  # 23:30 PST the day before in UTC
            (datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc), date(2026, 11, 10)),  # Pacific midnight
            (datetime(2026, 3, 8, 9, 59, tzinfo=timezone.utc), date(2026, 3, 8)),  # 01:59 PST, DST starts at 02:00
            (datetime(2026, 11, 1, 7, 59, tzinfo=timezone.utc), date(2026, 11, 1)),  # 00:59 PDT, DST ends that day
            (datetime(2026, 11, 1, 6, 59, tzinfo=timezone.utc), date(2026, 10, 31)),  # 23:59 PDT
        )
        for now, today in cases:
            with self.subTest(now=now):
                for day in (today, today + timedelta(days=60)):
                    self.content = load_content()
                    [touched] = self.call(now, restock_on=day.isoformat())
                    self.assertEqual((touched.collection, touched.key, touched.after["restock_on"]),
                                     ("products", self.pid, day.isoformat()))
                    self.assertNotIn("restock_on", touched.before)
                self.content = load_content()
                past = self.call(now, restock_on=(today - timedelta(days=1)).isoformat())
                self.assertIsInstance(past, Refused)
                self.assertIn("in the past", past.reason)
                far = self.call(now, restock_on=(today + timedelta(days=61)).isoformat())
                self.assertIsInstance(far, Refused)
                self.assertIn("more than 60 days ahead", far.reason)

    def test_clear_modes_and_no_change(self):
        now = _midday(FIXED)
        self.assertEqual(self.call(now), NeedsDetails(["restock_on"], "What day is more coming?"))
        self.assertEqual(self.call(now, clear=False), NeedsDetails(["restock_on"], "What day is more coming?"))
        nothing = self.call(now, clear=True)
        self.assertIsInstance(nothing, Refused)
        self.assertIn("no restock day set", nothing.reason)
        [set_] = self.call(now, restock_on="2026-11-20", clear=False)  # clear=False with a day is a plain set
        self.assertEqual(self.product()["restock_on"], "2026-11-20")
        for args in ({"restock_on": "2026-11-20"}, {"restock_on": "2026-11-21", "clear": True}):
            with self.subTest(args=args):
                self.assertIsInstance(self.call(now, **args), Refused)
                self.assertEqual(self.product()["restock_on"], "2026-11-20")
        [cleared] = self.call(now, clear=True)
        self.assertEqual(cleared.before, set_.after)
        self.assertNotIn("restock_on", self.product())  # removed: never null, false or blank
        self.assertEqual(self.product(), set_.before)

    def test_active_only_and_no_shelf_side_effects(self):
        now = _midday(FIXED)
        product = self.product()
        product.update(available="limited", available_on="2026-11-02")
        expected = {**copy.deepcopy(product), "restock_on": "2026-11-12"}
        store = copy.deepcopy(self.content.store)
        result = self.call(now, restock_on="2026-11-12")
        self.assertEqual([(t.collection, t.key) for t in result], [("products", self.pid)])
        self.assertEqual(list(self.product().items()), list(expected.items()))  # only restock_on added, order kept
        self.assertEqual(self.content.store, store)  # no shelf check implied
        self.product()["status"] = "hidden"
        hidden = self.call(now, restock_on="2026-11-13")
        self.assertIsInstance(hidden, Refused)
        self.assertIn("restore it", hidden.reason)
        self.assertIsInstance(self.call(now, clear=True), Refused)  # hidden: clearing is refused too
        held = next(p["id"] for p in self.content.products if p["status"] == "held")
        result = self.op.apply(self.content, {"id": held, "restock_on": "2026-11-13"}, _ctx(now))
        self.assertIsInstance(result, Refused)
        self.assertIn("held", result.reason)
        self.assertEqual(self.op.apply(self.content, {"id": "no-such-product", "restock_on": "2026-11-13"}, _ctx(now)),
                         NotFound("no-such-product"))


class EditorTests(CatalogTestCase):
    def setUp(self):
        self.r = DatedRepo()
        self.addCleanup(self.r.cleanup)
        self.today = shop_today()
        self.r.now = _midday(self.today)
        active = [p for p in self.r.products() if p["status"] == "active"]
        self.a, self.b = active[0]["id"], active[1]["id"]
        self.day = (self.today + timedelta(days=5)).isoformat()

    def product(self, pid):
        return next(p for p in self.r.products() if p["id"] == pid)

    def test_prepare_is_read_only_and_apply_changes_only_products_json(self):
        head, products = self.r.head(), self.r.products()
        site = {rel: self.r.read(rel) for rel in sitegen.render(self.r.content())}
        draft = self.r.prepare(_req((SET, {"id": self.a, "restock_on": self.day})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual((self.r.head(), self.r.products()), (head, products))
        self.assertEqual(self.r.apply(draft["draft"])["result"], "applied")
        self.assertEqual(self.product(self.a)["restock_on"], self.day)
        changed = git(self.r.wt, "diff", "--name-only", head, "HEAD").splitlines()
        self.assertEqual(changed, ["hass/content/products.json"])  # no generated or published file changes
        self.assertEqual({rel: self.r.read(rel) for rel in site}, site)

    def test_refusals_and_invalid_args_write_nothing(self):
        held = next(p["id"] for p in self.r.products() if p["status"] == "held")
        cases = {
            "refused": ((SET, {"id": self.a, "restock_on": (self.today - timedelta(days=1)).isoformat()}),
                        (SET, {"id": self.a, "restock_on": (self.today + timedelta(days=61)).isoformat()}),
                        (SET, {"id": self.a, "clear": True}), (SET, {"id": held, "restock_on": self.day}),
                        (SET, {"id": self.a, "restock_on": self.day, "clear": True})),
            "needs-details": ((SET, {"id": self.a}), (SET, {"id": self.a, "clear": False}), (SET, {"restock_on": self.day})),
            "invalid": ((SET, {"id": self.a, "restock_on": "2026-02-30"}), (SET, {"id": self.a, "restock_on": "next week"}),
                        (SET, {"id": self.a, "restock_on": None}), (SET, {"id": self.a, "clear": "yes"}),
                        (SET, {"id": self.a, "restock_on": self.day, "quantity": 4})),
            "not-found": ((SET, {"id": "no-such-product", "restock_on": self.day}),),
        }
        for name, ops in cases.items():
            for call in ops:
                with self.subTest(result=name, args=call[1]):
                    products = self.r.products()
                    self.assertRejected(self.r, name, call)
                    self.assertEqual(self.r.products(), products)

    def test_undo_preserves_absence_value_and_conflict(self):
        before = self.product(self.a)
        first = self.r.run((SET, {"id": self.a, "restock_on": self.day}))
        self.r.run((REVERT, {"changeId": first["change_id"]}))
        self.assertEqual(self.product(self.a), before)  # absent again, not null or blank
        self.assertNotIn("restock_on", self.product(self.a))

        old = (self.today - timedelta(days=4)).isoformat()  # set while it was ahead; it is past by the time of the undo
        self.r.now = _midday(self.today - timedelta(days=6))
        self.r.run((SET, {"id": self.a, "restock_on": old}))
        self.r.now = _midday(self.today)
        with_old = self.product(self.a)
        replace = self.r.run((SET, {"id": self.a, "restock_on": self.day}))
        self.r.run((REVERT, {"changeId": replace["change_id"]}))
        self.assertEqual(self.product(self.a), with_old)  # the old, now past, day comes back exactly
        clear = self.r.run((SET, {"id": self.a, "clear": True}))
        self.assertNotIn("restock_on", self.product(self.a))
        self.r.run((REVERT, {"changeId": clear["change_id"]}))
        self.assertEqual(self.product(self.a), with_old)

        later = self.r.run((SET, {"id": self.a, "restock_on": self.day}))
        self.r.run((SET, {"id": self.b, "restock_on": self.day}))  # an unrelated product's edit
        b_after = self.product(self.b)
        self.r.run((REVERT, {"changeId": later["change_id"]}))
        self.assertEqual((self.product(self.a), self.product(self.b)), (with_old, b_after))  # b's edit is kept

        drift = self.r.run((SET, {"id": self.a, "restock_on": self.day}))
        self.r.run(("product.edit", {"id": self.a, "description": "Picked ripe and packed by hand."}))
        reason = self.assertRejected(self.r, "refused", (REVERT, {"changeId": drift["change_id"]}))["reason"]
        self.assertIn("conflict", reason)

    def test_two_sets_in_one_change_undo_to_the_first_before(self):
        before = self.product(self.b)
        later = (self.today + timedelta(days=9)).isoformat()
        both = self.r.run((SET, {"id": self.b, "restock_on": self.day}), (SET, {"id": self.b, "restock_on": later}))
        self.assertEqual(self.product(self.b)["restock_on"], later)
        self.r.run((REVERT, {"changeId": both["change_id"]}))
        self.assertEqual(self.product(self.b), before)


class PublishTests(unittest.TestCase):
    def test_all_generated_and_publish_bytes_stay_identical(self):
        content = load_and_validate()
        rendered = sitegen.render(content, today=FIXED)
        published = sitegen.publish_files(content, REPO_ROOT, today=FIXED)
        for rel in ("catalog-products.js", "producers.js", "producers.json", "community.json"):
            self.assertIn(sitegen.SITE_PREFIX + rel, rendered)
        for rel in ("catalog-products.js", "producers.js", "community.json"):
            self.assertIn(rel, published)
        for files in (rendered, published):
            for rel, data in files.items():
                self.assertNotIn(SENTINEL.encode(), data, rel)  # the sentinel is new to the public files
        private = copy.deepcopy(content)
        for i, product in enumerate(private.products):  # every status, and a different day for some
            product["restock_on"] = SENTINEL if i % 2 == 0 else "2031-07-20"
        validate(private, SITE_DIR)
        after_render = sitegen.render(private, today=FIXED)
        after_publish = sitegen.publish_files(private, REPO_ROOT, today=FIXED)
        self.assertEqual(sorted(after_render), sorted(rendered))
        self.assertEqual(sorted(after_publish), sorted(published))
        for before, after in ((rendered, after_render), (published, after_publish)):
            for rel in before:
                with self.subTest(rel=rel):
                    self.assertTrue(before[rel] == after[rel], f"{rel} changed")
                    self.assertNotIn(b"restock_on", after[rel])
                    self.assertNotIn(SENTINEL.encode(), after[rel])
                    self.assertNotIn(b"2031-07-20", after[rel])

    def test_committed_content_has_no_restock_day(self):
        """test_content pins every generated file byte-for-byte to this content, which carries no restock_on."""
        products = json.loads((REPO_ROOT / "hass/content/products.json").read_text("utf-8"))["products"]
        self.assertFalse(any("restock_on" in p for p in products))
        self.assertEqual(load_registry()[SET].args.keys(), {"id", "restock_on", "clear"})


if __name__ == "__main__":
    unittest.main()
