"""RF0005-5: page.photo asks "home page or a product?" when one request names both, even without "main picture".

Run: python3 -B -m unittest hass.tests.test_page_photo_dual_destination -v
"""

import copy
import types
import unittest
from unittest import mock

from hass import editor
from hass.skills import dispatch, pages
from hass.skills.shop import SkillStop
from hass.tests.test_set_photo import FIXTURES, PhotoRepo

ALT = "the shop front on a sunny morning"
SHA = "b" * 64
ASK = "Is it for the home page or for a product?"
SET_OP = [{"op": "store.set_home_image", "args": {"photo": SHA, "imageAlt": ALT}}]
SLOTS = {"photo": SHA, "image_alt": ALT}
DUAL = "use this for the home page and the product"


def ctx_for(*texts, **kw):
    return types.SimpleNamespace(today="2026-11-09", texts=list(texts), **kw)


class DualDestination(unittest.TestCase):
    def asks(self, *texts):
        with self.assertRaises(SkillStop) as caught:
            pages.plan_photo(dict(SLOTS), ctx_for(*texts))
        self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", ASK))

    def test_initial_dual_request_asks_in_either_order(self):
        for text in (DUAL, "use this for the product and the home page", "Use this for the HOME   PAGE and the PRODUCTS",
                     "use this for the products and the homepage"):
            with self.subTest(text=text):
                self.asks(text)

    def test_non_answers_keep_asking(self):
        for later in ("yes", "no", ALT, "the product", "for a product", "not the home page"):
            with self.subTest(later=later):
                self.asks(DUAL, later)

    def test_home_choice_then_caption_gives_exact_op(self):
        self.assertEqual(pages.plan_photo(dict(SLOTS), ctx_for(DUAL, "the home page")), SET_OP)
        self.assertEqual(pages.plan_photo(dict(SLOTS), ctx_for(DUAL, "the home page", ALT)), SET_OP)

    def test_home_choice_then_new_dual_request_reopens(self):
        self.asks(DUAL, "the home page", "also use this for the product and the home page")

    def test_home_only_and_contextless_unchanged(self):
        for ctx in (None, ctx_for(), ctx_for("use this for the home page")):
            self.assertEqual(pages.plan_photo(dict(SLOTS), ctx), SET_OP)

    def test_model_caption_with_product_words_is_not_owner_evidence(self):
        slots = {"photo": SHA, "image_alt": "the home page and the product shelf"}
        ops = pages.plan_photo(slots, ctx_for("use this for the home page"))
        self.assertEqual(ops[0]["args"]["imageAlt"], "the home page and the product shelf")

    def test_inputs_not_mutated(self):
        slots, ctx = copy.deepcopy(SLOTS), ctx_for(DUAL)
        texts = list(ctx.texts)
        with self.assertRaises(SkillStop):
            pages.plan_photo(slots, ctx)
        self.assertEqual((slots, ctx.texts), (SLOTS, texts))


class StoredAttachment(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.sha = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())

    def plan(self, *texts):
        ctx = ctx_for(*texts, store={})
        filled = dispatch.validate(pages.PAGE_PHOTO, {}, dict(photo=self.sha, image_alt=ALT), ctx.texts, ctx, attachments=(self.sha,))
        self.assertIsNone(filled.problem)
        return pages.PAGE_PHOTO.plan(filled.slots, ctx)

    def test_dual_request_asks_without_editor_calls_then_home_op(self):
        before = (self.repo.status(), self.repo.drafts())
        with mock.patch.object(editor, "prepare", side_effect=AssertionError("no draft")) as prepare, \
                mock.patch.object(editor, "apply", side_effect=AssertionError("no write")) as apply:
            with self.assertRaises(SkillStop) as caught:
                self.plan(DUAL)
            self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", ASK))
            ops = self.plan(DUAL, "the home page", ALT)
        prepare.assert_not_called()
        apply.assert_not_called()
        self.assertEqual(ops, [{"op": "store.set_home_image", "args": {"photo": self.sha, "imageAlt": ALT}}])
        self.assertEqual((self.repo.status(), self.repo.drafts()), before)


if __name__ == "__main__":
    unittest.main()
