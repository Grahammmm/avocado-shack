"""AV1222-11 (F07): `post hike <id>` replies social_draft.build_hike's announcement draft in chat.
Read-only: nothing is posted, scheduled, stored or drafted; works while paused. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_post_hike_command -v
"""

import json
import unittest
from pathlib import Path
from unittest import mock

from hass import conversation, social_draft
from hass.content_model import load_content
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

UNAVAILABLE = "Catalog unavailable right now; nothing changed."
USAGE = "Send post hike and a hike id, e.g. post hike hike-2026-11-14-point-buchon (find <words> gives ids)."


def hike(hid, **changes):
    return {"id": hid, "title": "Bluff Walk", "startsAt": "2026-11-14T16:00:00Z", "timezone": "America/Los_Angeles",
            "status": "scheduled", "meetingPoint": "the Shack porch", "trailId": "idea-point-buchon", **changes}


class ParseTests(unittest.TestCase):
    def test_hike_group_keeps_the_id_case_and_lookalikes_are_not_the_command(self):
        self.assertEqual(conversation.parse_command("POST HIKE Hike-A!"), ("post", "HIKE Hike-A"))
        self.assertEqual(conversation.parse_command("post hike"), ("post", "hike"))
        self.assertEqual(conversation.parse_command("post photo-product-001"), ("post", "photo-product-001"))
        for text in ("post hike a b", "post hikes a b", "please post hike a"):
            self.assertIsNone(verb(text), text)

    def test_no_product_id_is_hike(self):
        ids = [p["id"] for p in json.loads(Path("hass/content/products.json").read_text("utf-8"))["products"]]
        self.assertNotIn("hike", [i.lower() for i in ids])


class PostHikeTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.repo.wt / "hass" / "content" / "community.json"
        doc = json.loads(self.path.read_text("utf-8"))
        doc["events"] = [hike("h-ok"), hike("h-cancelled", status="cancelled"), hike("h-done", status="completed"),
                         hike("h-past", startsAt="2026-11-01T16:00:00Z"), hike("h-draft", status="draft"),
                         hike("h-tag", meetingPoint="the #porch")]
        self.path.write_text(json.dumps(doc), "utf-8")
        self.want = social_draft.build_hike(load_content(self.repo.wt / "hass" / "content"), "h-ok", T0)

    def post(self, text):
        self.assertEqual(self.say(text), "post")
        [row] = self.conv.db.execute("SELECT text, attachments FROM outbox ORDER BY id DESC LIMIT 1").fetchall()
        self.assertEqual(len(self.replies()), 1)
        return row["text"], json.loads(row["attachments"] or "[]")

    def test_scheduled_future_hike_replies_the_caption_without_attachment(self):
        self.assertTrue(self.want["draft"], self.want)
        with mock.patch("socket.socket", side_effect=AssertionError("network")):
            text, files = self.post("post hike h-ok")
        self.assertEqual((text, files), (f"Draft post (not posted; copy it yourself):\n{self.want['caption']}", []))
        self.assertEqual((self.drafts(), self.commits(), self.approvals()), ([], 0, 0))

    def test_refusals_are_plain_words(self):
        for send, words in (("post hike nope", "No hike nope; send find <words> for ids."),
                            ("post hike h-cancelled", "h-cancelled is cancelled; nothing to announce."),
                            ("post hike h-done", "h-done has already happened."),
                            ("post hike h-past", "h-past has already happened."),
                            ("post hike h-draft", "h-draft is not scheduled yet."),
                            ("post hike h-tag", "Cannot draft a post for h-tag: free text has a hashtag or account name.")):
            with self.subTest(send=send):
                self.assertEqual(self.post(send), (words, []))
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_usage_and_case(self):
        self.assertEqual(self.post("post hike"), (USAGE, []))
        self.assertEqual(self.post("POST HIKE H-OK"), ("No hike H-OK; send find <words> for ids.", []))
        self.assertTrue(self.post("Post Hike h-ok")[0].startswith("Draft post (not posted"))

    def test_works_while_paused_and_keeps_a_waiting_draft(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        tables = self.tables()
        text, _ = self.post("post hike h-ok")
        self.assertTrue(text.startswith("Draft post (not posted") and "paused" not in text.lower(), text)
        self.assertEqual((self.drafts(), self.tables(), self.commits(), self.approvals()), ([], tables, 0, 0))

    def test_product_post_still_works(self):
        pid = json.loads((self.repo.wt / "hass" / "content" / "products.json").read_text("utf-8"))["products"][0]["id"]
        self.assertEqual(self.post(f"post {pid}x")[0], f"No product {pid}x; send find <words> for ids.")

    def test_unreadable_catalog_gives_the_fixed_line(self):
        self.path.write_text("{not json", "utf-8")
        self.assertEqual(self.post("post hike h-ok"), (UNAVAILABLE, []))


if __name__ == "__main__":
    unittest.main()
