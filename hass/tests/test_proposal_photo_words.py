"""AV0022-09: readable photo proposals; stored paths and approval lifecycle stay unchanged."""
import copy
import unittest
from datetime import timedelta

from hass import conversation
from hass.tests import test_photo_draft as photos
from hass.tests.test_conversation import T0

PHOTO = "assets/products/photo-0123456789abcdef.jpg"
EXPIRES = "2026-11-02T17:10:00+00:00"
PREFIX = "products photo-product-001: "


def draft(before, after):
    return {"records": [{"collection": "products", "key": "photo-product-001", "before": before, "after": after}]}


class PhotoWordsTests(unittest.TestCase):
    def test_photo_and_alt_summary_and_stored_records(self):
        for ext in ("jpg", "png"):
            d = draft({"image": "assets/products/old.webp", "imageAlt": "Old"},
                      {"image": PHOTO.replace("jpg", ext), "imageAlt": "New"})
            before = copy.deepcopy(d)
            text = conversation.proposal_text("ab12", d, EXPIRES)
            self.assertIn(PREFIX + "photo: the photo from your message", text.splitlines())
            self.assertNotIn("assets/products/", text)
            self.assertIn(PREFIX + "imageAlt Old → New", text)
            self.assertEqual(conversation._summary(d), PREFIX + "image, imageAlt")
            self.assertEqual(d, before)

    def test_undo_and_normal_photo_to_plain_file(self):
        for old, new in ((PHOTO, "assets/products/old.webp"), ("assets/products/old.webp", PHOTO),
                         (PHOTO, PHOTO.replace("jpg", "png"))):
            d = draft({"image": old}, {"image": new})
            text = conversation.proposal_text("ab12", d, EXPIRES, undo=True)
            self.assertIn(PREFIX + "photo: the previous photo", text.splitlines())
            self.assertNotIn("assets/products/", text)
        text = conversation.proposal_text("ab12", draft({"image": PHOTO}, {"image": "old.webp"}), EXPIRES)
        self.assertIn(PREFIX + f"image {PHOTO} → old.webp", text)

    def test_added_photo_keeps_sorted_place_and_alt(self):
        text = conversation.proposal_text("ab12", draft(None, {"id": "p", "image": PHOTO, "imageAlt": "Crate"}), EXPIRES)
        self.assertEqual(text.splitlines()[2:5], ["  id: p", "  photo: the photo from your message", "  imageAlt: Crate"])
        self.assertNotIn("  image:", text)
        self.assertNotIn("assets/products/", text)

    def test_plain_and_near_miss_paths_stay_literal(self):
        for path in ("assets/products/old.jpg", PHOTO.replace("0123456789abcdef", "0123456789abcde"),
                     PHOTO.replace("0123456789abcdef", "0123456789abcdef0"), PHOTO.upper(),
                     PHOTO.replace("abcdef", "ABCDEF"), PHOTO.replace(".jpg", ".webp"),
                     PHOTO.replace("products", "makers"), PHOTO + "\n"):
            with self.subTest(path=path):
                d = draft({"image": "old.webp"}, {"image": path})
                self.assertIn(PREFIX + "image old.webp " + conversation._arrow(path),
                              conversation.proposal_text("ab12", d, EXPIRES))
                added = conversation.proposal_text("ab12", draft(None, {"image": path}), EXPIRES)
                self.assertIn("  image:", added)


class PhotoConversationTests(unittest.TestCase):
    setUp = photos.PhotoDraftTests.setUp
    open = photos.PhotoDraftTests.open
    say = photos.PhotoDraftTests.say
    replies = photos.PhotoDraftTests.replies
    drafts = photos.PhotoDraftTests.drafts

    def propose(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        self.assertEqual(self.say(photos.ANSWER), "proposed")
        [text] = self.replies()
        self.assertIn(PREFIX + "photo: the photo from your message", text)
        self.assertNotIn("assets/products/", text)
        return self.drafts()[-1]

    def test_proposal_show_undo_and_summary_commands(self):
        row = self.propose()
        self.assertEqual(self.say("status"), "status")
        self.assertIn(PREFIX + "image, imageAlt", self.replies()[0])
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.assertEqual(self.say("history"), "history")
        self.assertIn(PREFIX + "image, imageAlt", self.replies()[0])
        self.assertEqual(self.say(f"undo {row['code']}"), "proposed")
        self.assertIn("photo: the previous photo", self.replies()[0])
        undo = self.drafts()[-1]
        self.assertEqual(self.say(f"show {undo['code']}"), "show")
        text = self.replies()[0]
        self.assertIn("photo: the previous photo", text)
        self.assertNotIn("assets/products/", text)

    def test_cancelled_expired_duplicate_and_stale_do_not_apply(self):
        row = self.propose()
        self.assertEqual(self.say(photos.ANSWER, attachments=1, pid="m1"), "duplicate")
        self.assertEqual(self.replies(), [])
        self.assertEqual(len(self.drafts()), 1)
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assertEqual(self.say(f"yes {row['code']}"), "no-target")
        self.assertIn("cancelled", self.replies()[0])
        row = self.propose()
        self.conv.clock = lambda: T0 + timedelta(seconds=601)
        msg = conversation.Inbound("expired-yes", photos.CHAT, photos.OWNER, f"yes {row['code']}",
                                   received_at=self.conv.clock().isoformat())
        self.assertEqual(self.conv.handle(msg), "no-target")
        self.assertIn("expired", self.replies()[0])
        self.assertFalse(any(r["commit"] for r in self.drafts()))

    def test_stale_photo_redrafts_without_applying_old_photo(self):
        self.propose()
        self.repo.run(("product.edit", {"id": photos.PID, "description": "Picked this week."}))
        self.assertEqual(self.say("yes"), "approved")
        old, new = self.drafts()
        self.assertEqual((old["state"], old["reason"], new["state"]), ("rejected", "stale", "proposed"))
        text = self.replies()[0]
        self.assertIn("photo: the photo from your message", text)
        self.assertNotIn("assets/products/", text)


if __name__ == "__main__":
    unittest.main()
