"""AV2007-01 (QA1-01) tests: a new item by chat in ops-only mode. A photo's own caption, a photo then its name and a name then a
captioned photo all reach the one product.add with the right original; the photo question is asked only when the caption
did not answer it. Same PhotoRepo harness as test_photo_new_product; nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_qa1_new_item_chat -v
"""

import json
import unittest

from hass.conversation import PHOTO_QUESTION
from hass.tests import test_photo_new_product as base
from hass.tests.test_photo_draft import SHA
from hass.tests.test_set_photo import ALT

ADD, _op = base.ADD, base._op


class RawInterpreter:
    """Fixture: a mapped text gets its raw reply exactly as given (a recorded reply, or a synthetic one); anything else is unsupported."""

    def __init__(self):
        self.mapping = {}

    def interpret(self, text, pending, **kw):
        return json.loads(json.dumps(self.mapping.get(text, {"unsupported": "Sorry, I can't do that yet."})))


class NewItemChatTests(unittest.TestCase):
    say, replies, drafts, added = (base.PhotoNewProductTests.__dict__[n] for n in ("say", "replies", "drafts", "added"))

    def setUp(self):  # the shared harness, then the raw-reply interpreter
        base.PhotoNewProductTests.setUp(self)
        self.conv.interpreter = self.raw = RawInterpreter()

    def reply(self, text, raw):
        self.raw.mapping[text] = raw

    def photo_ops(self):
        return [json.loads(d["ops_json"]) for d in self.drafts()]

    def test_caption_add_inherits_only_its_message_photo(self):
        self.reply("add Test quince", {"ops": [_op("product.add", **ADD)], "revises": None})  # the recorded shape: revises null
        self.assertEqual(self.say("add Test quince", attachments=1), "proposed")
        [reply] = self.replies()  # one reply: the proposal, no generic photo question
        self.assertTrue(reply.startswith("Here's the change I'd make:"), reply)
        [row] = self.drafts()
        self.assertEqual((row["state"], json.loads(row["ops_json"])[0]["args"]["photo"]), ("proposed", SHA))
        self.assertEqual(self.added(), [])  # nothing is written before the yes
        self.assertEqual(self.say("yes"), "approved")
        [product] = self.added()
        self.assertIn(SHA[:16], product["image"])

    def test_caption_with_missing_alt_asks_only_that_and_keeps_the_photo(self):
        bare = {k: v for k, v in ADD.items() if k != "imageAlt"}
        self.reply("new product Test quince", {"ops": [_op("product.add", **bare)], "revises": None})
        self.assertEqual(self.say("new product Test quince", attachments=1), "needs-details")
        [reply] = self.replies()
        self.assertNotIn(PHOTO_QUESTION, reply)
        [row] = self.drafts()
        args = json.loads(row["ops_json"])[0]["args"]
        self.assertEqual((args["photo"], args["name"], "imageAlt" in args), (SHA, bare["name"], False))
        answer = f"it's a new product: Test quince. {ALT}"  # as in test_photo_new_product: the answer states what the draft claims
        self.reply(answer, {"ops": [_op("product.add", **bare, imageAlt=ALT)], "revises": row["code"]})
        self.assertEqual(self.say(answer), "proposed")  # the same row, filled: no second photo, no re-send
        self.assertEqual([r["state"] for r in self.drafts()], ["proposed"])

    def test_photo_first_and_text_first_keep_the_same_original(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.assertEqual(self.replies(), [PHOTO_QUESTION])
        [row] = self.drafts()
        self.reply("new product Test quince", {"ops": [_op("product.add", **ADD)], "revises": row["code"]})
        self.assertEqual(self.say("new product Test quince"), "proposed")
        self.assertEqual(self.photo_ops()[0][0]["args"]["photo"], SHA)
        self.assertEqual(len(self.drafts()), 1)

    def test_text_first_then_captioned_photo_has_no_repeated_question(self):
        self.reply("I have a new quince", {"question": "What should I call it?"})
        self.assertEqual(self.say("I have a new quince"), "question")
        self.replies()
        self.reply("Test quince", {"ops": [_op("product.add", **ADD)], "revises": None})
        self.assertEqual(self.say("Test quince", attachments=1), "proposed")
        [reply] = self.replies()
        self.assertNotIn(PHOTO_QUESTION, reply)
        [row] = self.drafts()
        self.assertEqual(json.loads(row["ops_json"])[0]["args"]["photo"], SHA)

    def test_unrelated_null_revision_does_not_steal_a_waiting_photo(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        before = self.drafts()
        self.reply("add Test quince", {"ops": [_op("product.add", **ADD)], "revises": None})
        self.assertEqual(self.say("add Test quince"), "not-drafted")  # a text with no photo of its own gets none
        self.assertEqual(self.drafts(), before)
        self.assertEqual(self.added(), [])

    def test_hike_caption_is_not_a_new_product(self):
        hike = _op("hike.create", title="Mill Creek hike", date="2026-11-21", time="09:00", meetingPoint="Mill Creek")
        self.reply("hike Saturday at 9 Mill Creek", {"ops": [hike], "revises": None})
        self.say("hike Saturday at 9 Mill Creek", attachments=1)
        for ops in self.photo_ops():
            self.assertNotIn("product.add", [c["op"] for c in ops])
        self.assertEqual(self.added(), [])
        self.assertTrue(any(d["state"] == "needs-details" and json.loads(d["ops_json"])[0]["op"] == "product.set_photo"
                            for d in self.drafts()))  # the photo stays its own waiting question

    def test_unreadable_caption_and_repeat_delivery_keep_one_waiting_photo(self):
        self.assertEqual(self.say("what is this", attachments=1), "unsupported")  # nothing answered the photo: the question is asked, once
        self.assertEqual(self.replies().count(PHOTO_QUESTION), 1)
        self.assertEqual(self.say("again", attachments=1), "photo-duplicate")  # the same bytes again: no second draft
        self.assertEqual(len(self.drafts()), 1)

    def test_recorded_question_only_reply_stays_a_question_and_yes_does_not_approve(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        asked = "Is this a new olive oil to add to the shop, or a photo for one of the olive oils we already list?"
        self.reply("its a new olive oil from Cambria Olive Co in Cambria", {"question": asked})  # recorded it-add-photo-only
        self.assertEqual(self.say("its a new olive oil from Cambria Olive Co in Cambria"), "question")
        self.assertEqual(self.replies(), [asked])
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual([r["state"] for r in self.drafts()], ["needs-details"])
        self.assertEqual(self.added(), [])


if __name__ == "__main__":
    unittest.main()
