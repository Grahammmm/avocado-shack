"""AV1622-05 tests: product.clear_availability removes one product's stock word and its own check day, reversibly.
Ops run through editor.prepare + editor.apply on a throwaway Git repo (DatedRepo); rendering uses an explicit date.
Run: python3 -B -m unittest hass.tests.test_clear_availability -v
"""

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

from hass import auto_policy, conversation, interpreter_prompt, sitegen
from hass.content_model import shop_today
from hass.ops import load_registry
from hass.tests.test_editor import git
from hass.tests.test_catalog_ops import CatalogTestCase, _req
from hass.tests.test_selection_checked import DatedRepo, _catalog

CHECK, SET, CLEAR, REVERT = \
    "store.confirm_selection", "product.set_availability", "product.clear_availability", "history.revert"


class ClearAvailabilityTests(CatalogTestCase):
    def setUp(self):
        self.r = DatedRepo()
        self.addCleanup(self.r.cleanup)
        self.today = shop_today()
        active = [p for p in self.r.products() if p["status"] == "active"]
        self.a, self.b, self.c, self.d = (p["id"] for p in active[:4])
        self.hidden = active[4]["id"]
        self.held = next(p["id"] for p in self.r.products() if p["status"] == "held")

    def at(self, day):
        self.r.now = datetime(day.year, day.month, day.day, 20, tzinfo=timezone.utc)  # midday Pacific

    def product(self, pid):
        return next(p for p in self.r.products() if p["id"] == pid)

    def words(self):
        files = sitegen.render(self.r.content(), today=self.today)
        return {p["id"]: p.get("availability") for p in _catalog(files) if p["id"] in (self.a, self.b, self.c, self.d)}

    def check(self, **groups):
        self.r.run((CHECK, groups))

    def refused(self, *ops):
        state = (self.r.products(), self.r.store())
        reason = self.assertRejected(self.r, "refused", *ops)["reason"]
        self.assertEqual((self.r.products(), self.r.store()), state)
        return reason

    def test_clear_yes_limited_no(self):
        for word in ("yes", "limited", "no"):
            with self.subTest(word=word):
                self.at(self.today)
                self.check(**{word: [self.a], "yes": [self.b]} if word != "yes" else {"yes": [self.a, self.b]})
                before, others, store = self.product(self.a), self.product(self.b), self.r.store()
                self.assertEqual(before["available"], word)
                self.r.run((CLEAR, {"id": self.a}))
                after = self.product(self.a)
                self.assertEqual(after, {k: v for k, v in before.items() if k not in ("available", "available_on")})
                self.assertEqual((self.product(self.b), self.r.store()), (others, store))  # others + store check untouched
                self.assertIsNone(self.words()[self.a])
                self.assertNotEqual(self.words()[self.b], None)

    def test_prepare_is_read_only_then_approval_applies(self):
        self.at(self.today)
        self.check(no=[self.a])
        self.assertEqual(self.words()[self.a], "Sold out")
        head, products = self.r.head(), self.r.products()
        draft = self.r.prepare(_req((CLEAR, {"id": self.a})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual((self.r.head(), self.r.products()), (head, products))
        self.assertEqual(self.words()[self.a], "Sold out")
        self.assertEqual(self.r.apply(draft["draft"])["result"], "applied")
        self.assertIsNone(self.words()[self.a])  # no word at all, not "Sold out"
        self.assertNotIn("available", self.product(self.a))

    def test_no_word_refused_without_write(self):
        reason = self.refused((CLEAR, {"id": self.a}))
        self.assertIn(self.a, reason)
        self.assertIn("no availability word", reason)
        self.at(self.today)
        self.check(yes=[self.a])
        self.r.run((CLEAR, {"id": self.a}))
        head, drafts = self.r.head(), self.r.drafts()
        self.assertIn("no availability word", self.refused((CLEAR, {"id": self.a})))  # a repeated clear
        self.assertEqual((self.r.head(), self.r.drafts()), (head, drafts))
        self.assertNotIn("available", self.product(self.a))  # never turned into 'no' or a blank

    def test_held_hidden_unknown_and_bad_args(self):
        self.at(self.today)
        self.check(yes=[self.hidden])
        self.r.run(("product.hide", {"id": self.hidden}))
        hidden_before = self.product(self.hidden)
        self.assertIn("restore it", self.refused((CLEAR, {"id": self.hidden})))
        self.assertEqual(self.product(self.hidden), hidden_before)  # still hidden, word kept
        self.assertIn("held", self.refused((CLEAR, {"id": self.held})))
        self.assertEqual(self.assertRejected(self.r, "not-found", (CLEAR, {"id": "no-such-product"}))["result"],
                         "not-found")
        self.assertEqual(self.r.prepare(_req((CLEAR, {})))["result"], "needs-details")  # missing id
        for args in ({"id": self.a, "available": "no"}, {"id": self.a, "clear": True}, {"id": self.a, "day": "x"}):
            with self.subTest(args=args):
                self.assertEqual(self.r.prepare(_req((CLEAR, args)))["result"], "invalid")

    def test_undo_restores_word_and_day(self):
        old = self.today - timedelta(days=3)
        self.at(old)
        self.check(limited=[self.a], yes=[self.b])
        self.at(self.today)
        self.check(yes=[self.c])  # a and b keep their older day: Last confirmed
        before = self.product(self.a)
        self.assertEqual(before["available_on"], old.isoformat())
        shown = self.words()[self.a]
        self.assertTrue(shown.startswith("Last confirmed"), shown)
        draft = self.r.run((CLEAR, {"id": self.a}))
        self.assertIsNone(self.words()[self.a])
        self.r.run((REVERT, {"changeId": draft["change_id"]}))
        self.assertEqual(self.product(self.a), before)
        self.assertEqual(self.words()[self.a], shown)  # not a newly fresh claim

    def test_clear_legacy_word_without_day(self):
        self.at(self.today)
        self.check(yes=[self.b])
        path = self.r.wt / "hass/content/products.json"
        data = json.loads(path.read_text("utf-8"))
        next(p for p in data["products"] if p["id"] == self.a)["available"] = "yes"  # set before per-product days
        path.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        git(self.r.wt, "commit", "-qam", "legacy word")
        before = self.product(self.a)
        self.assertNotIn("available_on", before)
        draft = self.r.run((CLEAR, {"id": self.a}))
        self.assertNotIn("available", self.product(self.a))
        self.assertNotIn("available_on", self.product(self.a))
        self.r.run((REVERT, {"changeId": draft["change_id"]}))
        self.assertEqual(self.product(self.a), before)
        self.assertNotIn("available_on", self.product(self.a))  # no date invented

    def test_registry_prompt_and_help(self):
        registry = load_registry()
        op = registry[CLEAR]
        self.assertEqual({name: (arg.kind, arg.required) for name, arg in op.args.items()}, {"id": ("id", True)})
        prompt = interpreter_prompt.build(registry, self.r.content())
        self.assertIn(CLEAR, prompt)
        first = conversation.HELP_TEXT.splitlines()[0]
        self.assertIn("Stop showing the eggs as sold out", first)
        self.assertIsNone(conversation.parse_command("Stop showing the eggs as sold out"))  # a change, not a command

    def test_not_auto_eligible(self):
        self.assertNotIn(CLEAR, auto_policy.ELIGIBLE)
        op = {"op": CLEAR, "args": {"id": self.a}}
        self.assertEqual(auto_policy.qualifies([op], list(auto_policy.ELIGIBLE), False), (False, "needs approval"))


if __name__ == "__main__":
    unittest.main()
