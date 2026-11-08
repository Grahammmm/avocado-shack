"""AV1322-07 (F07): `post <product id>` replies social_draft's caption with the product's site photo attached.
Read-only: nothing is posted, scheduled, written or drafted; works while paused. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_post_command -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import conversation, social_draft
from hass.content_model import load_content
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

UNAVAILABLE = "Catalog unavailable right now; nothing changed."


class PostParseTests(unittest.TestCase):
    def test_post_keeps_the_id_case_and_lookalikes_are_not_the_command(self):
        for text, want in (("post photo-product-001", "photo-product-001"), ("Post  ABC-Mixed.", "ABC-Mixed"),
                           ("POST x!", "x")):
            self.assertEqual(conversation.parse_command(text), ("post", want), text)
        self.assertEqual(conversation.parse_command("post"), ("post", ""))
        for text in ("post a b", "posts a", "please post a", "post\na b", "postit a"):
            self.assertIsNone(verb(text), text)


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
        self.assertEqual(text, f"Here's a post you can copy. I haven't posted anything.\n{want['caption']}\nWhat the photo shows: {want['alt']}")
        self.assertEqual(files, [str(self.site / "post-test" / "real.jpg")])
        self.assertEqual((self.drafts(), self.commits(), self.approvals()), ([], 0, 0))

    def test_refusals_are_plain_words_and_attach_nothing(self):
        for send, words in ((f"post {self.ids[0]}x", f"No product {self.ids[0]}x; send find <words> for ids."),
                            (f"post {self.ids[2]}", f"{self.ids[2]} is not on the site."),
                            (f"post {self.ids[3]}", f"{self.ids[3]} is not on the site."),
                            (f"post {self.ids[1]}", f"{self.ids[1]} has no photo on the site."),
                            (f"post {self.ids[4]}", f"{self.ids[4]} has no photo on the site."),  # link to a file outside
                            (f"post {self.ids[5]}", f"{self.ids[5]} has no photo on the site."),  # a link is not a regular file
                            (f"post {self.ids[6]}", f"Cannot draft a post for {self.ids[6]}: free text has a hashtag or account name.")):
            with self.subTest(send=send):
                self.assertEqual(self.post(send), (words, []))
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_no_id_gets_usage_and_two_words_fall_through(self):
        self.assertEqual(self.post("post"), ("Which product is the post for? Say it like post Hass avocado.", []))
        self.interp.mapping["post a b"] = {"question": "Which?"}
        self.assertNotEqual(self.say("post a b"), "post")
        self.assertNotIn("Draft post", "\n".join(self.replies()))

    def test_id_is_matched_as_typed(self):
        upper = self.ids[0].upper()
        self.assertNotEqual(upper, self.ids[0])
        self.assertEqual(self.post(f"post {upper}")[0], f"I don't know a product called {upper}. Try find and a word from its name.")
        self.assertTrue(self.post(f"post {self.ids[0]}")[0].startswith("Draft post (not posted):"))

    def test_works_while_paused_and_changes_nothing(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        tables, control = self.tables(), [dict(r) for r in self.conv.db.execute("SELECT * FROM control")]
        text, files = self.post(f"post {self.ids[0]}")
        self.assertTrue(text.startswith("Draft post (not posted):") and "paused" not in text.lower(), text)
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
