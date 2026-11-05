"""AV0022-04 (H12) tests: a photo question answered with "it's a new product: ..." becomes product.add with the draft's
photo, kept exactly as a product.set_photo fill keeps it; two photo ops in one answer change nothing.

PhotoRepo harness of test_photo_draft (temp Git repo + writer worktree, private media root outside the repo), a fake
photo source and a fixture interpreter. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_photo_new_product -v
"""

import unittest

from hass import conversation
from hass.content_model import SITE_DIR
from hass.conversation import Inbound
from hass.fixture_chat import FixtureAdapter
from hass.interpreter_prompt import build
from hass.tests.test_catalog_ops import IMAGE, NEW
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_editor import git
from hass.tests.test_interpreter_prompt import FIXTURE, TEST_REGISTRY, tiny_content
from hass.tests.test_photo_draft import PNG_SHA, SHA, FakePhotos
from hass.tests.test_set_photo import ALT, ASSETS, PID, PhotoRepo, _settings

ADD = {**{k: v for k, v in NEW.items() if k != "image"}, "imageAlt": ALT}  # no photo: the draft supplies it
WEB = f"assets/products/photo-{SHA[:16]}.jpg"


def _op(op, /, **args):
    return {"op": op, "args": args}


class NewProductInterpreter:
    """Fixture: a mapped text answers the waiting photo draft (or, with revises False, names no draft)."""

    def __init__(self):
        self.mapping = {}

    def interpret(self, text, pending):
        if text not in self.mapping: return {"unsupported": "Sorry, I can't do that yet."}
        ops, revises = self.mapping[text]
        waiting = [p["code"] for p in pending if p["state"] == "needs-details"]
        return {"ops": ops, "revises": (waiting[-1] if waiting else None) if revises else None}


class PhotoNewProductTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.interp, self.out, self.n = NewProductInterpreter(), FixtureAdapter(), 0
        self.conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                              lambda: T0, photos=FakePhotos())

    def say(self, text="", attachments=0, ops=None, revises=True):
        if ops is not None: self.interp.mapping[text] = (ops, revises)
        self.n += 1
        return self.conv.handle(Inbound(f"m{self.n}", CHAT, OWNER, text, received_at=T0.isoformat(),
                                        attachments=attachments))

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def photo_draft(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        [row] = self.drafts()
        return row

    def added(self):
        return [p for p in self.repo.products() if p["name"] == NEW["name"]]

    def test_new_product_answer_adds_the_product_with_the_photo(self):
        self.photo_draft()
        self.assertEqual(self.say("it's a new product: Test quince", ops=[_op("product.add", **ADD)]), "proposed")
        [row] = self.drafts()
        self.assertEqual((row["state"], row["code"]), ("proposed", SHA[:4]))
        [reply] = self.replies()
        self.assertTrue(reply.startswith(f"Draft {SHA[:4]}:"), reply)
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.drafts()[0]["state"], "applied")
        [product] = self.added()
        self.assertEqual((product["image"], product["imageAlt"], product["status"]), (WEB, ALT, "active"))
        self.assertNotIn("photo", product)
        self.assertIn(f"{ASSETS}photo-{SHA[:16]}.jpg", self.repo.committed())

    def assertRefused(self, text, ops, disposition, reply, before, revises=True):
        self.assertEqual(self.say(text, ops=ops, revises=revises), disposition)
        self.assertEqual(self.replies(), [reply])
        self.assertEqual(self.drafts(), [before])  # the photo question still waits, unchanged
        self.assertEqual(self.added(), [])

    def test_new_product_naming_another_photo_is_refused(self):
        before = self.photo_draft()
        self.assertRefused("new product, other photo", [_op("product.add", **ADD, photo=PNG_SHA)], "photo-mismatch",
                           "That draft is for another photo.", before)

    def test_new_product_with_an_image_too_gets_the_photo_and_is_not_drafted(self):
        real = "assets/products/real-quince.webp"  # PhotoRepo links other images; image args need a real file
        (self.repo.wt / "storefront-mockup" / real).write_bytes((SITE_DIR / IMAGE).read_bytes())
        git(self.repo.wt, "add", "-A")
        git(self.repo.wt, "commit", "-q", "-s", "-m", "real image")
        before = self.photo_draft()
        self.assertRefused("new product with image", [_op("product.add", **ADD, image=real)], "not-drafted",
                           "Not drafted: give image or photo, not both", before)

    def test_two_photo_ops_in_one_answer_change_nothing(self):
        before = self.photo_draft()
        cases = {"set_photo + add": [_op("product.set_photo", id=PID, imageAlt=ALT), _op("product.add", **ADD)],
                 "add + set_photo": [_op("product.add", **ADD), _op("product.set_photo", id=PID, imageAlt=ALT)],
                 "two set_photo": [_op("product.set_photo", id=PID, imageAlt=ALT),
                                   _op("product.set_photo", id="photo-product-002", imageAlt=ALT)],
                 "two add": [_op("product.add", **ADD), _op("product.add", **{**ADD, "name": "Test medlar"})]}
        for name, ops in cases.items():
            with self.subTest(name):
                self.assertRefused(name, ops, "photo-many-ops", "One photo can go on one product; say which.", before)
        self.assertEqual(self.repo.product(PID)["image"], IMAGE)

    def test_add_that_revises_no_photo_draft_gets_no_photo(self):
        self.assertEqual(self.say("add Test quince", ops=[_op("product.add", **ADD)]), "not-drafted")
        self.assertEqual(self.replies(), ["Not drafted: Send the photo with the product name as its caption."])
        self.assertEqual(self.drafts(), [])
        before = self.photo_draft()  # a waiting photo question is not filled by an add that does not revise it
        self.assertRefused("add Test quince again", [_op("product.add", **ADD)], "not-drafted",
                           "Not drafted: Send the photo with the product name as its caption.", before, revises=False)

    def test_prompt_snapshot_holds_the_new_vs_existing_rule_once(self):
        rule = ("- When a pending draft is a photo question (product.set_photo), answer with product.set_photo for a "
                "listed product, or product.add with imageAlt when the owner says it is a new product; never both.\n")
        self.assertEqual(FIXTURE.read_text("utf-8").count(rule), 1)
        self.assertEqual(build(TEST_REGISTRY, tiny_content()).count(rule), 1)


if __name__ == "__main__":
    unittest.main()
