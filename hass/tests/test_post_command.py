"""AV1322-07 (F07): `post <product id>` replies social_draft's caption with the product's site photo attached.
Read-only: nothing is posted, scheduled, written or drafted; works while paused. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_post_command -v
"""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import conversation, social_draft
from hass.content_model import load_content
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

WARNING = "This picture is an illustration made from a shelf photo, not a photo of the product. Send a photo with the product name as its caption to post a real one."
UNAVAILABLE = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"


class PostParseTests(unittest.TestCase):
    def test_post_keeps_the_id_case_and_lookalikes_are_not_the_command(self):
        for text, want in (("post photo-product-001", "photo-product-001"), ("Post  ABC-Mixed.", "ABC-Mixed"),
                           ("POST x!", "x")):
            self.assertEqual(conversation.parse_command(text), ("post", want), text)
        self.assertEqual(conversation.parse_command("post"), ("post", ""))
        for text in ("posts a", "please post a", "postit a"):
            self.assertIsNone(verb(text), text)
        # AV1052-07: several words are one name or alias; the whole rest is read, up to the end of the line
        self.assertEqual(conversation.parse_command("post a b c d e f g h"), ("post", "a b c d e f g h"))
        self.assertEqual(conversation.parse_command("post Hass avocado"), ("post", "Hass avocado"))


class PostTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.site = self.repo.wt / "storefront-mockup"
        (self.site / "post-test").mkdir()
        self.outside = tempfile.TemporaryDirectory()
        self.addCleanup(self.outside.cleanup)
        (self.site / "post-test" / "real.jpg").write_bytes(b"jpeg")
        (Path(self.outside.name) / "far.jpg").write_bytes(b"jpeg")
        (self.site / "post-test" / "out.jpg").symlink_to(Path(self.outside.name) / "far.jpg")
        (self.site / "post-test" / "in.jpg").symlink_to(self.site / "post-test" / "real.jpg")
        path = self.repo.wt / "hass" / "content" / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        self.ids = [p["id"] for p in doc["products"][:6]]
        for p, (image, status) in zip(doc["products"], (("post-test/real.jpg", "active"), ("post-test/missing.jpg", "active"),
                                                        ("post-test/real.jpg", "held"), ("post-test/real.jpg", "hidden"),
                                                        ("post-test/out.jpg", "active"), ("post-test/in.jpg", "active"))):
            p.update(image=image, status=status)
        doc["products"][6].update(image="post-test/real.jpg", status="active", name="Tagged #jam")
        self.ids.append(doc["products"][6]["id"])
        path.write_text(json.dumps(doc), "utf-8")

    def post(self, text):
        self.assertEqual(self.say(text), "post")
        self.assertEqual(self.disposition(f"m{self.n}"), "post")
        [row] = self.conv.db.execute("SELECT text, attachments FROM outbox ORDER BY id DESC LIMIT 1").fetchall()
        self.assertEqual(len(self.replies()), 1)
        return row["text"], json.loads(row["attachments"] or "[]")

    def test_active_product_replies_the_caption_with_its_photo(self):
        want = social_draft.build(load_content(self.repo.wt / "hass" / "content"), self.ids[0], self.site)
        self.assertTrue(want["draft"], want)
        with mock.patch("socket.socket", side_effect=AssertionError("network")):
            text, files = self.post(f"post {self.ids[0]}")
        self.assertTrue(want["illustration"])
        self.assertEqual(text, f"{WARNING}\nHere's a post you can copy. I haven't posted anything.\n{want['caption']}\nWhat the photo shows: {want['alt']}")
        self.assertEqual(files, [str(self.site / "post-test" / "real.jpg")])
        self.assertEqual((self.drafts(), self.commits(), self.approvals()), ([], 0, 0))

    def test_owner_photo_gets_no_warning_and_refusals_never_do(self):
        path = self.repo.wt / "hass" / "content" / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        image = "post-test/real.jpg"  # the fixture's assets/ is a link out of the tree, so the owner-photo form is stood in by the shared rule
        owner = mock.patch.object(social_draft, "HOME_IMAGE_RE", re.compile(r"post-test/real\.jpg"))
        owner.start()
        self.addCleanup(owner.stop)
        want = social_draft.build(load_content(self.repo.wt / "hass" / "content"), self.ids[0], self.site)
        self.assertIs(want.get("illustration"), False, want)
        text, files = self.post(f"post {self.ids[0]}")
        self.assertEqual(text, f"Here's a post you can copy. I haven't posted anything.\n{want['caption']}\nWhat the photo shows: {want['alt']}")
        self.assertEqual(files, [str(self.site / image)])
        for pid in (self.ids[1], self.ids[5]):  # missing photo, symlinked photo: refusal, no warning, no attachment
            text, files = self.post(f"post {pid}")
            self.assertNotIn("illustration", text)
            self.assertEqual(files, [])

    def test_refusals_are_plain_words_and_attach_nothing(self):
        for send, words in ((f"post {self.ids[0]}x", f"I don't know a product called {self.ids[0]}x. Try find and a word from its name."),
                            (f"post {self.ids[2]}", f"{self.ids[2]} isn't on the website right now."),
                            (f"post {self.ids[3]}", f"{self.ids[3]} isn't on the website right now."),
                            (f"post {self.ids[1]}", f"{self.ids[1]} has no photo on the website yet, so I can't make a post for it."),
                            (f"post {self.ids[4]}", f"{self.ids[4]} has no photo on the website yet, so I can't make a post for it."),  # link to a file outside
                            (f"post {self.ids[5]}", f"{self.ids[5]} has no photo on the website yet, so I can't make a post for it."),  # a link is not a regular file
                            (f"post {self.ids[6]}", f"I can't make a post for {self.ids[6]} right now. Nothing was posted.")):
            with self.subTest(send=send):
                self.assertEqual(self.post(send), (words, []))
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_no_id_gets_usage_and_two_words_are_a_name(self):
        self.assertEqual(self.post("post"), (conversation.POST_USAGE, []))
        self.assertIn("find <words>", conversation.POST_USAGE)
        self.assertEqual(self.post("post x y"), ('No active product matches "x y"; send find <words> for ids.', []))  # AV1052-07: no longer the interpreter

    def test_id_is_matched_as_typed(self):
        upper = self.ids[0].upper()
        self.assertNotEqual(upper, self.ids[0])
        self.assertEqual(self.post(f"post {upper}")[0], f"I don't know a product called {upper}. Try find and a word from its name.")
        self.assertTrue(self.post(f"post {self.ids[0]}")[0].startswith(WARNING + "\nHere's a post you can copy. I haven't posted anything."))

    def test_works_while_paused_and_changes_nothing(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        tables, control = self.tables(), [dict(r) for r in self.conv.db.execute("SELECT * FROM control")]
        text, files = self.post(f"post {self.ids[0]}")
        self.assertTrue(text.startswith(WARNING + "\nHere's a post you can copy. I haven't posted anything.") and "paused" not in text.lower(), text)
        self.assertEqual(files, [str(self.site / "post-test" / "real.jpg")])
        self.assertEqual((self.drafts(), self.tables(), self.commits(), self.approvals()), ([], tables, 0, 0))
        self.assertEqual([dict(r) for r in self.conv.db.execute("SELECT * FROM control")], control)

    def test_unreadable_catalog_gives_the_fixed_line(self):
        (self.repo.wt / "hass" / "content" / "products.json").write_text("{not json", "utf-8")
        self.assertEqual(self.post(f"post {self.ids[0]}"), (UNAVAILABLE, []))
        moved = self.repo.wt.with_name(self.repo.wt.name + "-moved")
        self.repo.wt.rename(moved)
        self.addCleanup(moved.rename, self.repo.wt)
        self.assertEqual(self.post(f"post {self.ids[0]}"), (UNAVAILABLE, []))


if __name__ == "__main__":
    unittest.main()
