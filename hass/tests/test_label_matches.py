"""AVB-10 (H10) tests: a read label's confirm line names the maker on file and an already-listed product, from the
catalog only (never from the model), and never drafts an op.

Unit cases call label_reader.question directly; the conversation case uses the fake LabelReader transport and the
PhotoRepo harness of test_label_reader (no model, no network).
Run: python3 -m unittest hass.tests.test_label_matches -v
"""

import json
import unittest

from hass import conversation
from hass.conversation import PHOTO_QUESTION, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.label_reader import question
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_label_reader import reader, recorded
from hass.tests.test_photo_draft import SHA, FakePhotos, PhotoInterpreter
from hass.tests.test_set_photo import PhotoRepo, _settings

TAIL = ". Is that right? Say which product it is either way."
MAKERS = {"straus": {"name": "Straus Family Creamery", "place": "Marshall"},
          "farwest": {"name": "Far West Fungi", "place": "Moss Landing"}}
PRODUCTS = [{"id": "p-1", "name": "Lion's Mane", "brand": "Far West Fungi", "status": "active"},
            {"id": "p-2", "name": "Whole milk", "brand": "Straus Family Creamery", "status": "hidden"},
            {"id": "p-3", "name": "Raw cream", "brand": "Straus Family Creamery", "status": "held",
             "hold": {"reason": "r", "source": "s"}}]


def listed(pid, name):
    return f" Already listed: {pid} ({name}); reply with that id to update it instead."


class QuestionTests(unittest.TestCase):
    def test_defaults_keep_todays_text_exactly(self):
        found = {"name": "Lion's Mane", "brand": "Far West Fungi", "category": "mushrooms"}
        self.assertEqual(question(found), f"The label looks like: Far West Fungi Lion's Mane (mushrooms){TAIL}")
        self.assertEqual(question(found, None, None), question(found))
        self.assertEqual(question(found, {}, []), question(found))

    def test_maker_matches_by_the_catalog_fold(self):
        found = {"brand": "STRAUS  family creamery", "category": "dairy"}
        self.assertEqual(question(found, MAKERS, PRODUCTS),
                         f"The label looks like: STRAUS  family creamery (dairy){TAIL} Maker on file: Straus Family "
                         "Creamery.")
        for brand in ("Straus", "Straus Family Creamery Co", "Straus-Family Creamery"):  # equality only, no prefix
            with self.subTest(brand):
                self.assertEqual(question({"brand": brand}, MAKERS), f"The label looks like: {brand}{TAIL}")

    def test_two_makers_or_a_hidden_maker_name_nothing(self):
        found = {"brand": "Far West Fungi"}
        today = f"The label looks like: Far West Fungi{TAIL}"
        twins = {**MAKERS, "fw2": {"name": "far west  FUNGI"}}
        self.assertEqual(question(found, twins), today)
        hidden = {"farwest": {**MAKERS["farwest"], "hidden": True}}
        self.assertEqual(question(found, hidden), today)
        both = {"farwest": MAKERS["farwest"], "old": {"name": "Far West Fungi", "hidden": True}}  # hidden one ignored
        self.assertEqual(question(found, both), today + " Maker on file: Far West Fungi.")
        self.assertEqual(question(found, {"x": "Far West Fungi", "y": {"name": 5}, "z": {}}), today)  # malformed

    def test_listed_product_active_or_hidden_but_never_held(self):
        found = {"name": "whole  MILK", "brand": "straus family creamery"}
        self.assertEqual(question(found, None, PRODUCTS),
                         f"The label looks like: straus family creamery whole  MILK{TAIL}" + listed("p-2", "Whole milk"))
        self.assertEqual(question({"name": "Lion's Mane", "brand": "Far West Fungi"}, MAKERS, PRODUCTS),
                         f"The label looks like: Far West Fungi Lion's Mane{TAIL} Maker on file: Far West Fungi."
                         + listed("p-1", "Lion's Mane"))
        held = {"name": "Raw cream", "brand": "Straus Family Creamery"}
        self.assertEqual(question(held, None, PRODUCTS), f"The label looks like: Straus Family Creamery Raw cream{TAIL}")
        other = {"name": "Lion's Mane", "brand": "Other Farm"}  # same name, other brand
        self.assertEqual(question(other, None, PRODUCTS), f"The label looks like: Other Farm Lion's Mane{TAIL}")

    def test_both_name_and_brand_are_needed_for_a_product_line(self):
        self.assertEqual(question({"name": "Lion's Mane"}, None, PRODUCTS), f"The label looks like: Lion's Mane{TAIL}")
        self.assertEqual(question({"name": "Lion's Mane", "category": "mushrooms"}, MAKERS, PRODUCTS),
                         f"The label looks like: Lion's Mane (mushrooms){TAIL}")
        self.assertEqual(question({"category": "dairy"}, MAKERS, PRODUCTS), f"The label looks like: dairy{TAIL}")

    def test_unreadable_makers_give_the_product_line_only(self):
        found = {"name": "Lion's Mane", "brand": "Far West Fungi", "category": "mushrooms"}
        self.assertEqual(question(found, None, PRODUCTS),
                         f"The label looks like: Far West Fungi Lion's Mane (mushrooms){TAIL}" + listed("p-1", "Lion's Mane"))


class LabelMatchConversationTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.out = FixtureAdapter()

    def open(self, answer):
        self.labels, self.transport = reader(recorded(answer))
        self.conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state),
                                              PhotoInterpreter(), lambda: T0, photos=FakePhotos(), labels=self.labels)
        self.addCleanup(self.conv.db.close)

    def photo(self):
        result = self.conv.handle(Inbound("m1", CHAT, OWNER, "", received_at=T0.isoformat(), attachments=1))
        self.conv.flush(self.out)
        [row] = [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts")]
        return result, [r["text"] for r in self.out.sent], row

    def test_photo_label_names_the_maker_and_the_listed_product_without_ops(self):
        straus = [p for p in self.repo.products() if p["name"] == "Straus butter"]
        self.assertEqual([(p["id"], p["brand"], p["status"]) for p in straus], [("photo-product-028", "Straus", "active")])
        self.assertEqual([m["name"] for m in self.repo.makers().values() if m["name"] == "Straus"], ["Straus"])
        self.open({"name": "straus BUTTER", "brand": "STRAUS", "category": "dairy"})
        result, replies, row = self.photo()
        line = (f"The label looks like: straus BUTTER (dairy){TAIL} Maker on file: Straus."
                + listed("photo-product-028", "Straus butter"))
        self.assertEqual(result, "photo-draft")
        self.assertEqual(replies, [f"{PHOTO_QUESTION} Reply with the product and description (draft {SHA[:4]}). {line}"])
        self.assertEqual((row["state"], row["summary"]), ("needs-details", f"{PHOTO_QUESTION} {line}"))
        self.assertEqual(json.loads(row["ops_json"]), [{"op": "product.set_photo", "args": {"photo": SHA}}])
        self.assertEqual(len(self.transport.calls), 1)

    def test_an_unlisted_label_keeps_the_plain_line(self):
        self.open({"name": "Quince paste", "brand": "Nobody Farm", "category": "dairy"})
        _result, replies, row = self.photo()
        line = f"The label looks like: Nobody Farm Quince paste (dairy){TAIL}"
        self.assertEqual((replies[0].endswith(f"). {line}"), row["summary"]), (True, f"{PHOTO_QUESTION} {line}"))
        self.assertEqual(json.loads(row["ops_json"]), [{"op": "product.set_photo", "args": {"photo": SHA}}])


if __name__ == "__main__":
    unittest.main()
