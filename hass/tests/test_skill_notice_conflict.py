"""RF2205-11: shop.notice asks before choosing between taking the notice down and replacing it.

Run: python3 -B -m unittest hass.tests.test_skill_notice_conflict -v
"""

import copy
import json
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import editor
from hass.skills import dispatch, shop
from hass.skills.shop import SkillStop
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import HIKE_ADD, LIVE1, MILL, SkillCase, skill_reply

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


SAY = "take down the notice, and say we are closed Friday until Nov 15"
CLEAR_SAY = "take down the notice"
SLOTS = {"clear": True, "text": "Closed Friday", "until": "2026-11-15"}


class DispatchConflict(SkillCase):
    """The real Conversation and Dispatcher: the conflict is a question, never a draft, and the owner's explicit choice continues it."""

    SKILLS = (shop.SHOP_NOTICE, HIKE_ADD)

    def put_notice(self):
        path = self.repo.wt / "hass" / "content" / "store.json"
        data = json.loads(path.read_text("utf-8"))
        data["notice"] = {"text": "Old notice", "until": "2026-11-12"}
        path.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
        git(self.repo.wt, "commit", "-qam", "notice up")
        self.base = self.count()

    def spy(self):
        prepare = mock.patch.object(self.editor, "prepare", wraps=self.editor.prepare)
        apply = mock.patch.object(self.editor, "apply", wraps=self.editor.apply)
        self.addCleanup(prepare.stop)
        self.addCleanup(apply.stop)
        return prepare.start(), apply.start()

    def reply_for(self, shape, slots, text=SAY):
        self.script(text, {"calls": [{"skill": "shop.notice", "slots": slots}], "revises": None} if shape == "calls" else skill_reply("shop.notice", **slots))

    def test_production_dispatch_conflict_never_prepares_a_draft(self):
        for shape in ("single", "calls"):
            for present in (False, True):
                with self.subTest(shape=shape, present=present):
                    self.setUp()
                    if present:
                        self.put_notice()
                    prepare, apply = self.spy()
                    self.reply_for(shape, SLOTS)
                    self.assertEqual(self.say(SAY), "question")
                    self.assertEqual(self.replies(), [ASK])
                    prepare.assert_not_called()
                    apply.assert_not_called()
                    self.assertEqual(self.drafts(), [])
                    self.nothing_written()
                    req = self.live()
                    self.assertEqual((req["skill"], req["question"], req["asked_slot"]), ("shop.notice", ASK, None))
                    self.assertEqual({k: req["slots"][k] for k in SLOTS}, SLOTS)

    def test_a_pending_draft_for_another_request_is_preserved(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, _ = self.propose(LIVE1)
        before = [dict(d) for d in self.drafts()]
        self.reply_for("single", SLOTS)
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say(SAY), "question")
        self.assertEqual(self.replies(), [ASK])
        self.assertEqual(self.drafts(), before)
        self.assertEqual(self.drafts()[-1]["state"], "proposed")
        self.nothing_written()

    def test_explicit_set_choice_continues_and_clear_only_remains_supported(self):
        for shape in ("single", "calls"):
            with self.subTest(shape=shape):
                self.setUp()
                self.put_notice()
                self.reply_for(shape, SLOTS)
                self.assertEqual(self.say(SAY), "question")
                self.replies()
                self.assertEqual(self.live()["question"], ASK)
                self.now += timedelta(minutes=1)
                choice = "change it, don't take it down"
                self.reply_for(shape, {"clear": False, "text": "Closed Friday", "until": "2026-11-15"}, choice)
                self.assertEqual(self.say(choice), "proposed")
                ops = json.loads(self.drafts()[-1]["ops_json"])
                self.assertEqual(ops, [{"op": "store.set_notice", "args": {"text": "Closed Friday", "until": "2026-11-15"}}])
                self.nothing_written()
        self.setUp()
        self.put_notice()
        self.reply_for("single", {"clear": True}, CLEAR_SAY)
        self.assertEqual(self.say(CLEAR_SAY), "proposed")
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"]), CLEAR_OP)
        self.nothing_written()


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
