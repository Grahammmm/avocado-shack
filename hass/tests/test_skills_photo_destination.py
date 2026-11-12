"""RF2345-11: page.photo asks "home page or a product?" for a vague "main picture" request, even when the slots are filled.

Pure plan cases, plus the real slot validation with a stored synthetic attachment and the real PAGE_PHOTO plan.
Run: python3 -B -m unittest hass.tests.test_skills_photo_destination -v
"""

import copy
import types
import unittest
from unittest import mock

from hass import editor, voice
from hass.skills import dispatch, pages
from hass.skills.shop import SkillStop
from hass.tests.test_set_photo import FIXTURES, PhotoRepo

ALT = "the shop front on a sunny morning"
SHA = "b" * 64
ASK = "Is it for the home page or for a product?"
SET_OP = [{"op": "store.set_home_image", "args": {"photo": SHA, "imageAlt": ALT}}]
SLOTS = {"photo": SHA, "image_alt": ALT}


def ctx_for(*texts, **kw):
    return types.SimpleNamespace(today="2026-11-09", texts=list(texts), **kw)


class DestinationGuard(unittest.TestCase):
    def asks(self, slots, ctx):
        with self.assertRaises(SkillStop) as caught:
            pages.plan_photo(slots, ctx)
        self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", ASK))

    def test_main_picture_slots_do_not_choose_home(self):
        for text in ("make this the main picture", "Make this the MAIN   PICTURE", "make this the main photo", "main\tphoto please"):
            with self.subTest(text=text):
                self.asks(dict(SLOTS), ctx_for(text))

    def test_home_choice_then_caption_continuation(self):
        self.assertEqual(pages.plan_photo(dict(SLOTS), ctx_for("make this the main picture", "for the home page")), SET_OP)
        self.assertEqual(pages.plan_photo(dict(SLOTS), ctx_for("make this the main picture", "home page", ALT)), SET_OP)
        self.assertEqual(pages.plan_photo(dict(SLOTS), ctx_for("make this the main picture for the home page")), SET_OP)

    def test_product_choice_never_installs_home(self):
        for later in (["for a product"], ["the product"], ["yes"], ["no"], [""], [ALT], ["home page or product"]):
            with self.subTest(later=later):
                self.asks(dict(SLOTS), ctx_for("make this the main picture", *later))

    def test_negated_home_page_is_not_a_choice(self):
        for later in ("not the home page", "Not the home page.", "no, not the home page", "don't put it on the home page",
                      "never the home page", "anywhere but the home page", "instead of the home page", "not for the home page",
                      "it isn't for the home page", "no home page", "don\u2019t put it on the home page", "do not put it on the home page",
                      "dont put it on the home page", "the home page is not where I want it", "the home page isn\u2019t where I want it",
                      "the home page is not for this", "THE HOME PAGE IS NOT WHERE I WANT IT", "I do not want it on the home page"):
            with self.subTest(later=later):
                self.asks(dict(SLOTS), ctx_for("make this the main picture", later))
        self.asks(dict(SLOTS), ctx_for("make this the main picture", "the home page is not where I want it", ALT))
        self.asks(dict(SLOTS), ctx_for("make this the main picture", "don\u2019t put it on the home page", ALT))
        self.asks(dict(SLOTS), ctx_for("make this the main picture for the home page", "actually the home page is not where I want it"))
        self.asks(dict(SLOTS), ctx_for("make this the main picture, don\u2019t put it on the home page"))
        self.asks(dict(SLOTS), ctx_for("make this the main picture", "not the home page", ALT))
        self.asks(dict(SLOTS), ctx_for("make this the main picture for the home page", "actually not the home page"))
        self.asks(dict(SLOTS), ctx_for("make this the main picture, not the home page"))

    def test_affirmative_home_page_still_chooses_after_a_denial_elsewhere(self):
        for later in ("no, the home page", "no - the home page please", "not that one, the home page",
                      "the home page", "the home page without a caption", "put it on the home page", "yes, the home page is where I want it",
                      "I don\u2019t mind, the home page"):
            with self.subTest(later=later):
                self.assertEqual(pages.plan_photo(dict(SLOTS), ctx_for("make this the main picture", later)), SET_OP)

    def test_new_ambiguous_request_reopens_destination(self):
        self.asks(dict(SLOTS), ctx_for("use this for the home page", "make this the main photo"))
        self.asks(dict(SLOTS), ctx_for("make this the main picture", "the home page", "now make this the main picture"))

    def test_explicit_home_and_contextless_plans_keep_exact_ops(self):
        for ctx in (None, ctx_for(), ctx_for("use this for the home page"), ctx_for("put it on the home page", ALT)):
            self.assertEqual(pages.plan_photo(dict(SLOTS), ctx), SET_OP)
        slots = {"photo": SHA, "image_alt": "the main picture window"}  # a caption is not an owner request
        self.assertEqual(pages.plan_photo(slots, ctx_for("use this for the home page"))[0]["args"]["imageAlt"], "the main picture window")
        before = copy.deepcopy(SLOTS)
        ctx = ctx_for("make this the main picture")
        texts = list(ctx.texts)
        self.asks(SLOTS, ctx)
        self.assertEqual((SLOTS, ctx.texts), (before, texts))

    def test_reset_conflict_and_photo_refusals_unchanged(self):
        ctx = ctx_for("make this the main picture")
        with self.assertRaises(SkillStop) as caught:  # RF1345-11 conflict stays first
            pages.plan_photo({"clear": True, "photo": SHA}, ctx)
        self.assertEqual(caught.exception.reply, pages.PHOTO_OR_RESET)
        with self.assertRaises(SkillStop) as caught:  # clear-only is unchanged
            pages.plan_photo({"clear": True}, ctx_for("make this the main picture", store={}))
        self.assertEqual(caught.exception.reply, pages.NO_OWN_PHOTO)
        self.assertEqual(pages.plan_photo({"clear": True}, ctx_for("make this the main picture")), [{"op": "store.clear_home_image", "args": {}}])
        with self.assertRaises(SkillStop) as caught:  # lower layers still refuse
            pages.plan_photo({"photo": SHA, "image_alt": "IMG_1234"}, ctx_for("use this for the home page"))
        self.assertEqual(caught.exception.reply, pages.ALT_REPLY)
        self.assertEqual(voice.check(ASK), [])


class StoredAttachment(unittest.TestCase):
    """A genuinely stored synthetic photo, the real slot validation and the real PAGE_PHOTO plan."""

    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.sha = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())

    def plan(self, *texts):
        ctx = ctx_for(*texts, store={})
        filled = dispatch.validate(pages.PAGE_PHOTO, {}, dict(photo=self.sha, image_alt=ALT), ctx.texts, ctx, attachments=(self.sha,))
        self.assertIsNone(filled.problem)
        self.assertEqual(filled.slots["photo"], self.sha)
        return pages.PAGE_PHOTO.plan(filled.slots, ctx)

    def test_no_editor_call_until_home_is_chosen(self):
        before = (self.repo.status(), self.repo.drafts())
        with mock.patch.object(editor, "prepare", side_effect=AssertionError("no draft")) as prepare, \
                mock.patch.object(editor, "apply", side_effect=AssertionError("no write")) as apply:
            for texts in (("make this the main picture",), ("make this the main picture", "for a product"), ("make this the main picture", "yes")):
                with self.subTest(texts=texts), self.assertRaises(SkillStop) as caught:
                    self.plan(*texts)
                self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", ASK))
            ops = self.plan("make this the main picture", "the home page", ALT)
        prepare.assert_not_called()
        apply.assert_not_called()
        self.assertEqual(ops, [{"op": "store.set_home_image", "args": {"photo": self.sha, "imageAlt": ALT}}])
        self.assertEqual((self.repo.status(), self.repo.drafts()), before)


if __name__ == "__main__":
    unittest.main()
