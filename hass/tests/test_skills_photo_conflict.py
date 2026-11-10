"""RF1345-11: page.photo asks before choosing between putting the shop's own photo back and a replacement photo.

A request that both asks to put the old photo back (clear) and gives a replacement (a photo or a description) gets one
question and no operations; a clear-only or a replacement-only request keeps its exact op. Real dispatcher slot
validation with a bound attachment, the real plan, and a synthetic writer repository (PhotoRepo) for the corrected choices.
Run: python3 -B -m unittest hass.tests.test_skills_photo_conflict -v
"""

import copy
import json
import types
import unittest
from unittest import mock

from hass import editor
from hass.skills import dispatch, pages
from hass.skills.shop import SkillStop
from hass.tests.test_set_photo import FIXTURES, PhotoRepo, _req

ALT = "the shop front on a sunny morning"
SHA = "b" * 64
ASK = "Do you want the home page photo changed, or put back the way it was? I can only do one."
CLEAR_OP = [{"op": "store.clear_home_image", "args": {}}]
HOME = {"image": "assets/products/photo-bbbbbbbbbbbbbbbb.jpg", "imageAlt": ALT}


def ctx_for(**kw):
    return types.SimpleNamespace(today="2026-11-09", texts=[f"use this for the home page, {ALT}, and put the old photo back"], **kw)


class ConflictAsks(unittest.TestCase):
    def asks(self, slots, ctx):
        with self.assertRaises(SkillStop) as caught:
            pages.plan_photo(slots, ctx)
        self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", ASK))

    def test_clear_and_bound_photo_asks_before_any_operation(self):
        for slots in ({"clear": True, "photo": SHA}, {"clear": True, "photo": SHA, "image_alt": ALT}):
            with self.subTest(slots=slots):
                self.asks(slots, ctx_for(store={"homeImage": HOME}))

    def test_clear_and_caption_alone_also_asks(self):
        self.asks({"clear": True, "image_alt": ALT}, ctx_for(store={"homeImage": HOME}))

    def test_conflict_precedes_missing_custom_photo(self):
        for ctx in (None, ctx_for(store={}), ctx_for(store={"homeImage": HOME})):
            with self.subTest(ctx=ctx):
                self.asks({"clear": True, "photo": SHA, "image_alt": ALT}, ctx)
                self.asks({"clear": True, "image_alt": ALT}, ctx)

    def test_clear_only_and_empty_replacement_values_keep_existing_behavior(self):
        for extra in ({}, {"photo": None}, {"photo": ""}, {"image_alt": None}, {"image_alt": ""}, {"image_alt": "  \t "},
                      {"photo": "", "image_alt": " "}):
            slots = {"clear": True, **extra}
            with self.subTest(slots=slots):
                self.assertEqual(pages.plan_photo(slots, ctx_for(store={"homeImage": HOME})), CLEAR_OP)
                self.assertEqual(pages.plan_photo(slots, None), CLEAR_OP)
                with self.assertRaises(SkillStop) as caught:
                    pages.plan_photo(slots, ctx_for(store={}))
                self.assertEqual((caught.exception.kind, caught.exception.reply), ("refused", pages.NO_OWN_PHOTO))

    def test_replacement_only_or_explicit_clear_false_uses_exact_set_op(self):
        want = [{"op": "store.set_home_image", "args": {"photo": SHA, "imageAlt": ALT}}]
        for extra in ({}, {"clear": False}, {"clear": None}):
            with self.subTest(extra=extra):
                self.assertEqual(pages.plan_photo({"photo": SHA, "image_alt": ALT, **extra}, ctx_for(store={})), want)
        for slots, reply in (({"clear": False, "image_alt": ALT}, pages.PHOTO_ASK), ({"clear": False, "photo": SHA}, pages.ALT_ASK)):
            with self.subTest(slots=slots), self.assertRaises(SkillStop) as caught:
                pages.plan_photo(slots, ctx_for(store={}))
            self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", reply))
        with self.assertRaises(SkillStop) as caught:  # a camera name is still refused by the alt rule
            pages.plan_photo({"clear": False, "photo": SHA, "image_alt": "IMG_1234.jpg"}, ctx_for(store={}))
        self.assertEqual(caught.exception.reply, pages.ALT_REPLY)

    def test_slots_and_context_are_not_mutated(self):
        for slots in ({"clear": True, "photo": SHA, "image_alt": ALT}, {"clear": True}, {"photo": SHA, "image_alt": ALT}):
            ctx = ctx_for(store={"homeImage": dict(HOME)})
            before_slots, before_ctx = copy.deepcopy(slots), copy.deepcopy(vars(ctx))
            with self.subTest(slots=slots):
                try:
                    pages.plan_photo(slots, ctx)
                except SkillStop:
                    pass
                self.assertEqual(slots, before_slots)
                self.assertEqual(vars(ctx), before_ctx)


class ValidatedConflict(unittest.TestCase):
    """The owner's photo stored privately, a custom home photo already set, the real slot validation, then the plan."""

    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.sha = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())
        self.run_ops(pages.plan_photo({"photo": self.sha, "image_alt": "the stand outside"}, None))

    def store(self):
        return json.loads(self.repo.read("hass/content/store.json"))

    def run_ops(self, ops):
        return self.repo.run(*[(o["op"], o["args"]) for o in ops])

    def validated(self, new):
        ctx = ctx_for(store=self.store())
        filled = dispatch.validate(pages.PAGE_PHOTO, {}, new, ctx.texts, ctx, attachments=(self.sha,))
        self.assertIsNone(filled.problem)
        self.assertEqual(filled.left_off, [])
        return filled.slots, ctx

    def test_validated_conflict_never_reaches_editor_then_each_explicit_choice_can_prepare(self):
        start, before = self.store(), (self.repo.status(), self.repo.drafts())
        new = {"clear": True, "photo": self.sha, "image_alt": ALT}
        slots, ctx = self.validated(new)
        self.assertEqual(slots, new)
        with mock.patch.object(editor, "prepare", side_effect=AssertionError("no draft")) as prepare, \
                mock.patch.object(editor, "apply", side_effect=AssertionError("no write")) as apply:
            with self.assertRaises(SkillStop) as caught:
                pages.PAGE_PHOTO.plan(slots, ctx)
        self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", ASK))
        prepare.assert_not_called()
        apply.assert_not_called()
        self.assertEqual((self.store(), (self.repo.status(), self.repo.drafts())), (start, before))

        reset, ctx = self.validated({"clear": True})
        ops = pages.PAGE_PHOTO.plan(reset, ctx)
        self.assertEqual(ops, CLEAR_OP)
        self.assertEqual(self.repo.prepare(_req(*[(o["op"], o["args"]) for o in ops]))["result"], "ok")
        self.run_ops(ops)
        self.assertEqual(self.store(), {k: v for k, v in start.items() if k != "homeImage"})

        replace, ctx = self.validated({"photo": self.sha, "image_alt": ALT})
        ops = pages.PAGE_PHOTO.plan(replace, ctx)
        self.assertEqual(ops, [{"op": "store.set_home_image", "args": {"photo": self.sha, "imageAlt": ALT}}])
        self.assertEqual(self.repo.prepare(_req(*[(o["op"], o["args"]) for o in ops]))["result"], "ok")
        self.run_ops(ops)
        after = self.store()
        self.assertEqual(after["homeImage"], {**start["homeImage"], "imageAlt": ALT})
        self.assertEqual({k: v for k, v in after.items() if k != "homeImage"}, {k: v for k, v in start.items() if k != "homeImage"})


if __name__ == "__main__":
    unittest.main()
