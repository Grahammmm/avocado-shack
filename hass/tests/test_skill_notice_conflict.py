"""RF2205-11: shop.notice asks before choosing between taking the notice down and replacing it.

Run: python3 -B -m unittest hass.tests.test_skill_notice_conflict -v
"""

import copy
import json
import types
import unittest
from pathlib import Path
from unittest import mock

from hass import editor
from hass.skills import dispatch, shop
from hass.skills.shop import SkillStop

ASK = "Do you want the notice changed, or taken down? I can only do one."
CLEAR_OP = [{"op": "store.clear_notice", "args": {}}]
SET_OP = [{"op": "store.set_notice", "args": {"text": "New notice", "until": "2026-11-15"}}]
HAVE = {"notice": {"text": "Old notice", "until": "2026-11-12"}}
FIXTURE = Path(__file__).parent / "fixtures" / "skills" / "shop" / "shop.notice.jsonl"


def ctx_for(store):
    return types.SimpleNamespace(today="2026-11-09", texts=["take down the notice, new notice"], store=store)


class ConflictAsks(unittest.TestCase):
    def stop(self, slots, ctx):
        with self.assertRaises(SkillStop) as caught:
            shop.plan_notice(slots, ctx)
        return caught.exception

    def test_clear_with_text_or_day_asks_without_ops(self):
        for extra in ({"text": "New notice", "until": "2026-11-15"}, {"text": "New notice"}, {"until": "2026-11-15"}):
            for store in (HAVE, {}, None):
                slots = {"clear": True, **extra}
                before = copy.deepcopy(slots)
                with self.subTest(slots=slots, store=store):
                    got = self.stop(slots, ctx_for(store) if store is not None else None)
                    self.assertEqual((got.kind, got.reply), ("question", ASK))
                    self.assertEqual(slots, before)

    def test_empty_replacement_does_not_turn_clear_into_conflict(self):
        for extra in ({}, {"text": None}, {"text": ""}, {"text": "  "}, {"until": None}, {"until": ""}, {"text": " ", "until": "\t"}):
            slots = {"clear": True, **extra}
            with self.subTest(slots=slots):
                self.assertEqual(shop.plan_notice(slots, ctx_for(HAVE)), CLEAR_OP)
                self.assertEqual(shop.plan_notice(slots, None), CLEAR_OP)
                got = self.stop(slots, ctx_for({}))
                self.assertEqual(got.reply, shop.NO_NOTICE)

    def test_set_only_and_explicit_clear_false_keep_all_guards(self):
        for extra in ({}, {"clear": False}, {"clear": None}):
            with self.subTest(extra=extra):
                self.assertEqual(shop.plan_notice({"text": "New notice", "until": "2026-11-15", **extra}, ctx_for(HAVE)), SET_OP)
        self.assertEqual(self.stop({"clear": False, "until": "2026-11-15"}, ctx_for(HAVE)).reply, shop.NOTICE_ASK)
        self.assertEqual(self.stop({"clear": False, "text": "New notice"}, ctx_for(HAVE)).reply, shop.UNTIL_ASK)
        self.assertEqual(self.stop({"text": "New notice", "until": "2026-11-01"}, ctx_for(HAVE)).reply, shop.NOTICE_PAST)
        self.assertEqual(self.stop({"text": "Old notice", "until": "2026-11-12"}, ctx_for(HAVE)).kind, "question")


class ValidatedConflict(unittest.TestCase):
    def validated(self, new):
        ctx = ctx_for(HAVE)
        filled = dispatch.validate(shop.SHOP_NOTICE, {}, new, ctx.texts, ctx)
        self.assertIsNone(filled.problem)
        return filled.slots, ctx

    def test_validated_conflict_never_reaches_editor_then_explicit_choices_plan(self):
        new = {"clear": True, "text": "New notice", "until": "2026-11-15"}
        slots, ctx = self.validated(new)
        self.assertEqual(slots, new)
        with mock.patch.object(editor, "prepare", side_effect=AssertionError("no draft")) as prepare, \
                mock.patch.object(editor, "apply", side_effect=AssertionError("no write")) as apply:
            with self.assertRaises(SkillStop) as caught:
                shop.SHOP_NOTICE.plan(slots, ctx)
        self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", ASK))
        prepare.assert_not_called()
        apply.assert_not_called()
        slots, ctx = self.validated({"clear": False, "text": "New notice", "until": "2026-11-15"})
        self.assertEqual(shop.SHOP_NOTICE.plan(slots, ctx), SET_OP)
        slots, ctx = self.validated({"clear": True})
        self.assertEqual(shop.SHOP_NOTICE.plan(slots, ctx), CLEAR_OP)


class VersionMigration(unittest.TestCase):
    def test_notice_version_and_legacy_fixture_migration(self):
        self.assertEqual(shop.SHOP_NOTICE.version, 2)
        self.assertEqual((shop.SHOP_HOURS.version, shop.SHOP_CONTACT.version), (1, 1))
        rows = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]
        self.assertTrue(rows)
        self.assertEqual({r["version"] for r in rows}, {2})

    def test_no_other_skills_fixture_replies_as_notice(self):
        # A row that replies as shop.notice is checked against SHOP_NOTICE's version (testkit stale-row), but a
        # skill's own case file must keep that skill's version (lint_cases). So the one shop.hours row that
        # replied as shop.notice ("refuse-holiday-is-notice") lives in shop.notice.jsonl at version 2.
        self.assertIn("refuse-holiday-is-notice", {json.loads(x)["id"] for x in FIXTURE.read_text().splitlines() if x.strip()})
        for path in sorted(FIXTURE.parent.glob("*.jsonl")):
            if path == FIXTURE:
                continue
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                with self.subTest(file=path.name, id=row.get("id")):
                    named = [c.get("skill") for rep in row.get("replies", []) if isinstance(rep, dict)
                             for c in (rep.get("calls") or [rep])]
                    self.assertNotIn("shop.notice", named)


if __name__ == "__main__":
    unittest.main()
