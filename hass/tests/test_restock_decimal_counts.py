"""RF0721-9: stock.restock treats a leading-point decimal goods quantity (".5 kg") like "0.5 kg": the existing no-count reply.

Synthetic plan and Chat fixtures only: recorded interpreter replies, a throwaway repository, no model, socket or live state.
Run: python3 -B -m unittest hass.tests.test_restock_decimal_counts -q
"""
from __future__ import annotations

import json
import unittest

from hass.content_model import REPO_ROOT
from hass.skills import restock as rs
from hass.tests.test_skills_restock import EGGS, EGGS_NAME, HONEY, HONEY_NAME, Chat, ctx, refusal, set_op

LEADING_POINT = ("restock .5 kg of honey Thursday", "restock .25 lbs of honey Thursday", "restock .75 gallons of honey Thursday",
                 "restock .5 KG of honey Thursday", "restock   .5   Kilos of honey Thursday", "restock .5kg of honey Thursday",
                 "restock .5 x jars of honey Thursday", "restock .5x kg of honey Thursday", ".5 kg honey Thursday")
NOT_COUNTS = ("honey 2026-11-12", "restock the lemons on the 14th", "eggs back in 2 weeks", "restock in forty days",
              "restock honey .5 Thursday", "restock v.5 kg of honey Thursday", "restock ..5 kg of honey Thursday",
              "restock honey. v.5 kg Thursday", "more honey Thursday")
DAY = {"item": HONEY, "day": "2026-11-12"}


class Predicate(unittest.TestCase):
    def test_leading_point_decimal_goods_are_counted(self):
        for text in LEADING_POINT:
            with self.subTest(text=text):
                self.assertTrue(rs.QUANTITY.search(text))
                self.assertEqual(refusal(DAY, text).reply, rs.COUNTS_REFUSED)
        self.assertEqual(refusal(DAY, "restock 0.5 kg of honey Thursday").reply, rs.COUNTS_REFUSED)

    def test_missing_slot_and_followup_keep_quantity_warning(self):
        for text in LEADING_POINT[:3]:
            with self.subTest(text=text):
                self.assertEqual(rs.question("day", {}, ctx(text)), rs.COUNTS + " " + rs.ASK_DAY)
                self.assertEqual(rs.question("item", {}, ctx(text)), rs.COUNTS + " " + rs.ASK_ITEM)
                self.assertEqual(refusal({"item": HONEY}, text).reply, rs.COUNTS + " " + rs.ASK_DAY)
                self.assertEqual(refusal({"day": "2026-11-12"}, text).reply, rs.COUNTS + " " + rs.ASK_ITEM)
        # the quantity was said in an earlier message; the later day answer must not erase it
        self.assertEqual(refusal(DAY, "restock .5 kg of honey", "Thursday").reply, rs.COUNTS_REFUSED)

    def test_clear_with_fractional_goods_and_notes_refuse(self):
        self.assertEqual(refusal({"item": HONEY, "clear": True}, "never mind the .5 kg honey restock").reply, rs.COUNTS_REFUSED)
        for text in LEADING_POINT[:3]:
            with self.subTest(text=text):
                self.assertEqual(rs.notes("stock.restock", dict(DAY), ctx(text)), {})

    def test_date_duration_and_token_boundaries_do_not_become_quantities(self):
        for text in NOT_COUNTS:
            with self.subTest(text=text):
                self.assertIsNone(rs.QUANTITY.search(text))
                self.assertEqual(rs.STOCK_RESTOCK.plan(dict(DAY), ctx(text)), set_op(HONEY, "2026-11-12"))
                self.assertIsNone(rs.question("day", {}, ctx(text)))
        for text in ("restock 40 jars of honey", "2.5 lbs of honey", "1,200 bags", "x40", "restock two dozen eggs"):
            with self.subTest(text=text):
                self.assertEqual(refusal(DAY, text).reply, rs.COUNTS_REFUSED)


class RealDispatch(unittest.TestCase):
    def open(self):
        chat = Chat()
        self.addCleanup(chat.close)
        return chat

    def test_complete_single_and_calls_refuse_without_proposal(self):
        for shape, kwargs in (("single", {"reply": {"item": EGGS_NAME, "day": "Thursday"}}),
                              ("calls", {"calls": [{"item": EGGS_NAME, "day": "Thursday"}]}),
                              ("two calls", {"calls": [{"item": EGGS_NAME, "day": "Thursday"}, {"item": HONEY_NAME, "day": "Thursday"}]})):
            for text in ("restock .5 kg of eggs Thursday", "restock .25 dozen jars of eggs and honey Thursday"):
                with self.subTest(shape=shape, text=text):
                    chat = self.open()
                    d, r = chat.say(text, **kwargs)
                    # the dispatcher says the refusal once per call
                    self.assertEqual((d, r.split("\n")), ("refused", [rs.COUNTS_REFUSED] * len(kwargs.get("calls", [0]))))
                    self.assertEqual((chat.drafts(), chat.head(), chat.product(EGGS).get("restock_on")), ([], chat.base, None))

    def test_missing_day_asks_once_then_refuses(self):
        chat = self.open()
        d, r = chat.say("restock .5 kg of eggs", {"item": EGGS_NAME})
        self.assertEqual((d, r), ("question", rs.COUNTS + " " + rs.ASK_DAY))
        d, r = chat.say("Thursday", {"day": "Thursday"})
        self.assertEqual((d, r), ("refused", rs.COUNTS_REFUSED))
        self.assertEqual((chat.drafts(), chat.head()), ([], chat.base))

    def test_date_only_request_still_prepares_the_date_draft(self):
        chat = self.open()
        d, r = chat.say("eggs back in 2 weeks", {"item": EGGS_NAME, "day": "in 2 weeks"})
        self.assertEqual(d, "proposed")
        self.assertEqual(len(chat.drafts()), 1)
        self.assertEqual((chat.head(), chat.product(EGGS).get("restock_on")), (chat.base, None))


class Versions(unittest.TestCase):
    def test_versioned_fixtures_and_generated_manifest_agree(self):
        self.assertEqual(rs.STOCK_RESTOCK.version, 3)
        rows = [json.loads(line) for line in (REPO_ROOT / rs.STOCK_RESTOCK.cases).read_text("utf-8").splitlines() if line.strip()]
        self.assertTrue(rows)
        self.assertEqual({row["version"] for row in rows}, {3})
        acceptance = [json.loads(line) for line in
                      (REPO_ROOT / "hass/tests/fixtures/skills-acceptance/messages.jsonl").read_text("utf-8").splitlines() if line.strip()]
        self.assertEqual(next(r for r in acceptance if r["id"] == "primary-stock-restock")["skill_version"], 3)
        self.assertEqual(next(r for r in acceptance if r["id"] == "primary-stock-clear")["skill_version"], 1)
        manifest = json.loads((REPO_ROOT / "docs/hass/capabilities.json").read_text("utf-8"))
        versions = {s["name"]: s["version"] for s in manifest["skills"]}
        self.assertEqual(versions["stock.restock"], 3)
        self.assertEqual(versions["stock.clear"], 1)


if __name__ == "__main__":
    unittest.main()
