"""AVB-12 (H12) tests: a photo that is already an active or hidden product's picture opens no draft.

Same harness as test_photo_draft (temp Git repo + writer worktree, fake photo source, fixture interpreter). Each test
points a product's image at the photo's web-copy name in the worktree, then sends the photo. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_photo_on_product -v
"""

import json
import unittest

from hass import conversation
from hass.content_model import SCHEMA_VERSION
from hass.conversation import PHOTO_QUESTION, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_editor import git
from hass.tests.test_photo_draft import JPG, PNG, PNG_SHA, SHA, FakePhotos, PhotoInterpreter
from hass.tests.test_set_photo import OTHER, PID, PhotoRepo, _settings

NAMED = f"assets/products/photo-{SHA[:16]}.jpg"
CAPTION = "make the description shorter"
UNSUPPORTED = "Sorry, I can't do that yet."


class PhotoOnProductTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.photos, self.interp, self.out, self.n = FakePhotos(), PhotoInterpreter(), FixtureAdapter(), 0
        self.conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                              lambda: T0, photos=self.photos)

    def say(self, text="", attachments=0, pid=None):
        self.n += 1
        return self.conv.handle(Inbound(pid or f"m{self.n}", CHAT, OWNER, text, received_at=T0.isoformat(),
                                        attachments=attachments))

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def point(self, *ids, status="active", image=NAMED):  # commit these products' status and image in the worktree
        path = self.repo.wt / "hass" / "content" / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        for product in doc["products"]:
            if product["id"] in ids: product.update(status=status, image=image)
        path.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        git(self.repo.wt, "commit", "-q", "-s", "-am", "point images")

    def reply_for(self, pid):
        return f"That photo is already on {pid} ({self.repo.product(pid)['name']}). To change that product, say what to change."

    def test_photo_on_an_active_product_is_named_and_opens_no_draft(self):
        self.point(OTHER, PID)  # two products use it: the first id is named
        self.assertEqual(self.say(attachments=1), "photo-on-product")
        self.assertEqual(self.replies(), [self.reply_for(PID)])
        self.assertEqual((self.drafts(), self.interp.texts), ([], []))
        self.assertEqual(self.say(attachments=1, pid="m1"), "duplicate")  # a re-delivery stays silent
        self.assertEqual((self.replies(), self.drafts()), ([], []))

    def test_hidden_is_named_and_held_is_not_matched(self):
        self.point(PID, status="hidden")
        self.assertEqual(self.say(attachments=1), "photo-on-product")
        self.assertEqual((self.replies(), self.drafts()), ([self.reply_for(PID)], []))
        self.point(PID, status="held")
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.assertEqual(self.replies(), [f"{PHOTO_QUESTION} Reply with the product and description (draft {SHA[:4]})."])
        self.assertEqual([d["state"] for d in self.drafts()], ["needs-details"])

    def test_caption_is_still_handled_as_the_next_text(self):
        self.point(PID)
        self.assertEqual(self.say(CAPTION, attachments=1), "unsupported")
        self.assertEqual(self.replies(), [self.reply_for(PID), UNSUPPORTED])
        self.assertEqual((self.interp.texts, self.drafts()), ([CAPTION], []))
        self.assertEqual(self.say("\ufffc", attachments=1), "photo-on-product")  # an empty caption is no text
        self.assertEqual((self.replies(), self.interp.texts), ([self.reply_for(PID)], [CAPTION]))

    def test_other_photo_or_other_image_name_opens_a_draft(self):
        self.point(PID)
        self.photos.data = PNG  # shares no prefix with the product's photo
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.assertEqual([d["code"] for d in self.drafts()], [PNG_SHA[:4]])
        self.assertEqual(self.say("no"), "rejected")
        self.photos.data = JPG
        for image in (f"assets/products/photo-{SHA[:15]}.jpg", f"assets/products/photo-{SHA[:16]}.webp",
                      f"storefront/assets/products/photo-{SHA[:16]}.jpg", f"assets/products/photo-{SHA[:16]}.jpg.bak"):
            with self.subTest(image):
                self.point(PID, image=image)
                self.assertEqual(self.say(attachments=1), "photo-draft")
                self.assertEqual(self.say("no"), "rejected")

    def test_unreadable_content_opens_a_draft_as_today(self):
        for broken in ("{not json", "[]", json.dumps({"schemaVersion": SCHEMA_VERSION, "products": 7}), ""):
            with self.subTest(broken):
                (self.repo.wt / "hass" / "content" / "products.json").write_text(broken, "utf-8")
                self.assertEqual(self.say(attachments=1), "photo-draft")
                self.assertEqual(self.say("no"), "rejected")
        self.assertEqual([d["state"] for d in self.drafts()], ["rejected"] * 4)

    def test_open_draft_duplicate_is_still_answered_first(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        self.point(PID)
        self.assertEqual(self.say(attachments=1), "photo-duplicate")
        self.assertEqual(self.replies(), [f"That photo is already in draft {SHA[:4]}. {PHOTO_QUESTION}"])
        self.assertEqual(len(self.drafts()), 1)


if __name__ == "__main__":
    unittest.main()
