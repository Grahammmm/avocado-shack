"""AV1537-15 (H10) tests: a label read from a stored photo becomes a question to confirm, never ops or a claim.

Recorded replies through a fake transport (no model, no network) and the NB-AV-09 PhotoRepo harness.
Run: python3 -m unittest hass.tests.test_label_reader -v
"""

import base64
import hashlib
import json
import unittest
import urllib.error
from pathlib import Path

from hass import voice, conversation, media
from hass.conversation import PHOTO_QUESTION, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.label_reader import LabelReader
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_media_web import exif, jpeg, seg
from hass.tests.test_photo_draft import ANSWER, JPG, SHA, FakePhotos, PhotoInterpreter
from hass.tests.test_set_photo import PhotoRepo, _settings

URL, MODEL, CATS = "http://127.0.0.1:11434", "vision-test", ["fruit", "mushrooms", "vegetables"]
LION = {"name": "Lion's Mane", "brand": "Far West Fungi", "category": "mushrooms"}


def recorded(content, status=200):
    """An Ollama /api/chat reply envelope around the model's content."""
    text = content if isinstance(content, str) else json.dumps(content)
    return status, json.dumps({"done": True, "message": {"role": "assistant", "content": text}}).encode()


class Transport:
    def __init__(self, answer=None, probe=None):
        self.answer, self.probe, self.calls = answer if answer is not None else recorded(LION), probe, []

    def __call__(self, url, body, headers, timeout):
        self.calls.append((url, json.loads(body), timeout))
        if self.probe: self.probe()
        if isinstance(self.answer, BaseException): raise self.answer
        return self.answer


def reader(answer=None, probe=None):
    transport = Transport(answer, probe)
    return LabelReader(URL, MODEL, transport=transport), transport


class LabelReaderTests(unittest.TestCase):
    def read(self, content):
        labels, _ = reader(recorded(content))
        return labels.read(JPG, CATS)

    def test_reads_name_brand_and_category_only(self):
        self.assertEqual(self.read(LION), LION)
        extra = {**LION, "maker": "Far West Fungi", "origin": "Moss Landing", "organic": True, "place": "CA",
                 "producerKey": "far-west"}
        self.assertEqual(self.read(extra), LION)
        self.assertEqual(self.read({**LION, "category": "MUSHROOMS"})["category"], "mushrooms")  # the catalog's value

    def test_claim_terms_drop_that_value_only(self):
        for name in ("Organic Lion's Mane", "ORGANICALLY grown mane", "Pesticide free mane", "Lion's Mane, grown in CA",
                     "Non‑GMO mane", "Locally foraged", "Certified Lion's Mane"):
            with self.subTest(name):
                self.assertEqual(self.read({**LION, "name": name}), {"brand": LION["brand"], "category": "mushrooms"})
        self.assertEqual(self.read({**LION, "brand": "Organic Valley"}), {"name": LION["name"], "category": "mushrooms"})

    def test_bad_values_are_dropped_one_by_one(self):
        for bad, keep in (({"category": "gadgets"}, ("name", "brand")), ({"brand": "B" * 61}, ("name", "category")),
                          ({"name": "Lion's\x00Mane"}, ("brand", "category")), ({"name": "Lion\u202eMane"}, ("brand", "category")),
                          ({"name": "N" * 81}, ("brand", "category")), ({"brand": "  "}, ("name", "category")),
                          ({"name": 5, "brand": None}, ("category",)), ({"category": ["mushrooms"]}, ("name", "brand"))):
            with self.subTest(bad):
                self.assertEqual(self.read({**LION, **bad}), {k: LION[k] for k in keep})
        self.assertEqual(self.read({**LION, "brand": "B" * 60})["brand"], "B" * 60)  # the limit itself is fine

    def test_every_failure_is_empty_with_a_code_and_no_log(self):
        cases = ((TimeoutError(), "timeout"), (urllib.error.URLError(TimeoutError()), "timeout"),
                 (urllib.error.URLError(ConnectionRefusedError()), "connect"), (ConnectionRefusedError(), "connect"),
                 ((500, b""), "http-500"), ((200, b" " * (300 * 1024)), "too-large"), ((200, b"not json"), "not-json"),
                 (recorded("not json"), "shape"), (recorded([LION]), "shape"), ((200, b"[]"), "shape"))
        for answer, code in cases:
            with self.subTest(code=code, answer=type(answer).__name__):
                labels, transport = reader(answer)
                with self.assertNoLogs(level="DEBUG"):
                    self.assertEqual(labels.read(JPG, CATS), {})
                self.assertEqual((labels.last_error, len(transport.calls)), (code, 1))
        labels, transport = reader()
        self.assertEqual((labels.read(b"", CATS), labels.last_error, transport.calls), ({}, "shape", []))
        labels.read(JPG, CATS)
        self.assertIsNone(labels.last_error)

    def test_only_loopback_http_and_a_named_model(self):
        for url in ("http://10.0.0.5:11434", "https://localhost", "http://localhost.evil:1", "http://u@127.0.0.1"):
            with self.subTest(url), self.assertRaises(ValueError):
                LabelReader(url, MODEL)
        for model in ("", None, "two words"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                LabelReader(URL, model)

    def test_request_is_one_json_chat_with_the_image(self):
        labels, transport = reader()
        labels.read(JPG, CATS)
        [(url, body, timeout)] = transport.calls
        self.assertEqual((url, timeout, body["model"], body["stream"], body["format"]), (URL + "/api/chat", 30, MODEL,
                                                                                         False, "json"))
        [message] = body["messages"]
        self.assertEqual((message["role"], base64.b64decode(message["images"][0])), ("user", JPG))
        self.assertNotIn("maker", message["content"].lower())


    def test_rf1500_11_placeholder_answers_are_dropped_per_field(self):
        for word in ("null", "NULL", "None", "nil", " N/A ", "na", "Unknown.", "not  printed", "Not visible", "not shown",
                     "-", "--", "?", "No brand", "no name", "Unbranded", "N/A."):
            for field in ("name", "brand", "category"):
                with self.subTest(word=word, field=field):
                    self.assertEqual(self.read({**LION, field: word}), {k: v for k, v in LION.items() if k != field})

    def test_rf1500_11_a_placeholder_word_inside_a_real_name_is_kept(self):
        for name in ("Nil's Honey", "Unknown Mortal Jam", "NA Beer Co", "None Such Mincemeat", "Null Island Tea"):
            with self.subTest(name):
                self.assertEqual(self.read({**LION, "name": name}), {**LION, "name": name})
        self.assertEqual(self.read({**LION, "brand": "No Brand Foods"})["brand"], "No Brand Foods")

    def test_rf1500_11_a_brand_that_echoes_the_name_is_offered_once(self):
        from hass.label_reader import question
        for brand in ("lion's  mane", "Lion's Mane", "LION\u2019S MANE", "Lion's Mane."):
            with self.subTest(brand):
                found = self.read({**LION, "brand": brand})
                self.assertEqual(found, {"name": "Lion's Mane", "category": "mushrooms"})
                self.assertEqual(question(found), "The label looks like \ue000Lion's Mane (mushrooms)\ue001. Is that right? Either way, tell me which product it is.")
        self.assertEqual(self.read({**LION, "brand": "Lion's Mane Co"})["brand"], "Lion's Mane Co")  # not an echo
        self.assertEqual(self.read({**LION, "name": "N/A", "brand": "Lion's Mane"}), {"brand": "Lion's Mane",
                                                                                       "category": "mushrooms"})


class LabelConversationTests(unittest.TestCase):
    def setUp(self):
        self.fresh()

    def fresh(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.photos, self.interp, self.out, self.n = FakePhotos(), PhotoInterpreter(), FixtureAdapter(), 0
        self.categories = sorted({p["category"] for p in self.repo.products()})
        self.open(recorded({**LION, "category": self.categories[0]}))

    def open(self, answer=None, probe=None):
        self.labels, self.transport = reader(answer, probe)
        self.conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                              lambda: T0, photos=self.photos, labels=self.labels)
        self.addCleanup(self.conv.db.close)

    def say(self, text="", attachments=1, pid=None):
        self.n += 1
        return self.conv.handle(Inbound(pid or f"m{self.n}", CHAT, OWNER, text, received_at=T0.isoformat(),
                                        attachments=attachments))

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def asked(self):
        return PHOTO_QUESTION

    def test_label_becomes_a_question_never_ops(self):
        self.assertEqual(self.say(), "photo-draft")
        line = (f"The label looks like \ue000Far West Fungi Lion's Mane ({self.categories[0]})\ue001. Is that right? "
                "Either way, tell me which product it is.")
        self.assertEqual(self.replies(), [f"{self.asked()} {line}"])
        [row] = self.drafts()
        self.assertEqual((row["state"], row["summary"]), ("needs-details", f"{PHOTO_QUESTION} {line}"))
        self.assertEqual(json.loads(row["ops_json"]), [{"op": "product.set_photo", "args": {"photo": SHA}}])
        self.assertEqual((self.interp.texts, len(self.transport.calls)), ([], 1))
        self.assertEqual(self.say(attachments=1), "photo-duplicate")  # the waiting question names the label
        self.assertEqual(self.replies(), [voice.plain(f"I already have that photo, and I'm waiting on you. {PHOTO_QUESTION} {line}")])
        self.assertEqual(len(self.transport.calls), 1)

    def test_extra_keys_never_reach_the_question_or_ops(self):
        self.open(recorded({"name": "Lion's Mane", "maker": "Secret Farm", "origin": "Marin", "organic": True}))
        self.say()
        [reply] = self.replies()
        [row] = self.drafts()
        self.assertTrue(voice.plain(reply).endswith("The label looks like Lion's Mane. Is that right? Either way, tell me which product it is."), reply)
        for text in (reply, row["summary"], row["ops_json"]):
            for word in ("Secret Farm", "Marin", "organic", "True"):
                self.assertNotIn(word, text)

    def test_failed_or_empty_read_keeps_todays_reply_exactly(self):
        for answer in (TimeoutError(), urllib.error.URLError(ConnectionRefusedError()), (500, b""),
                       (200, b"x" * (300 * 1024)), (200, b"{"), recorded([LION]), recorded({"maker": "Farm"}),
                       recorded({"name": "Organic"})):
            with self.subTest(answer=repr(answer)[:40]):
                self.fresh()
                self.open(answer)
                with self.assertNoLogs(level="DEBUG"):
                    self.assertEqual(self.say(), "photo-draft")
                self.assertEqual(self.replies(), [self.asked()])
                self.assertEqual(self.drafts()[0]["summary"], PHOTO_QUESTION)
                self.assertEqual(len(self.transport.calls), 1)

    def test_read_is_outside_the_transaction_and_sends_the_web_copy(self):
        held, self.photos.data = [], jpeg(exif("II", 1), seg(0xFE, b"shot at the fake spot"))  # EXIF + comment
        self.open(recorded(LION), probe=lambda: held.append(self.conv.db.in_transaction))
        self.assertEqual(self.say(), "photo-draft")
        self.assertEqual(held, [False])
        web = Path(media.web_copy(self.repo.media, hashlib.sha256(self.photos.data).hexdigest())["path"]).read_bytes()
        [(_url, body, _timeout)] = self.transport.calls
        self.assertEqual(base64.b64decode(body["messages"][0]["images"][0]), web)
        self.assertNotEqual(web, self.photos.data)  # never the original bytes
        self.assertNotIn(b"fake spot", web)

    def test_refused_duplicate_and_redelivered_photos_are_never_read(self):
        for data in (b"", JPG[:-2], b"GIF89a\x01\x00\x01\x00"):
            self.photos.data = data
            self.assertTrue(self.say().startswith("photo-refused:"))
        self.assertEqual(self.say(attachments=5), "attachment-many")
        self.assertEqual(self.transport.calls, [])
        self.photos.data = JPG
        self.assertEqual(self.say(pid="p1"), "photo-draft")
        self.assertEqual(self.say(pid="p1"), "duplicate")
        self.assertEqual(self.say(), "photo-duplicate")
        self.assertEqual(len(self.transport.calls), 1)

    def test_a_caption_proposal_never_carries_the_label(self):
        self.assertEqual(self.say(ANSWER), "proposed")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Here's the change I'd make:"), reply)
        self.assertEqual(self.transport.calls, [])  # the caption already answered the question
        [row] = self.drafts()
        self.assertEqual(row["state"], "proposed")
        for text in (reply, row["summary"], row["ops_json"]):
            self.assertNotIn("Far West Fungi", text)

    def test_no_reader_is_never_called(self):
        conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                         lambda: T0, photos=self.photos)
        self.addCleanup(conv.db.close)
        conv.handle(Inbound("x1", CHAT, OWNER, "", received_at=T0.isoformat(), attachments=1))
        self.assertEqual((conv.labels, self.transport.calls), (None, []))


    def test_rf1500_11_all_placeholders_keep_todays_reply(self):
        for answer in ({"name": "null", "brand": "N/A", "category": "unknown"}, {"name": "Not printed.", "brand": "--"}):
            with self.subTest(answer):
                self.fresh()
                self.open(recorded(answer))
                self.assertEqual(self.say(), "photo-draft")
                self.assertEqual(self.replies(), [self.asked()])
                self.assertEqual(self.drafts()[0]["summary"], PHOTO_QUESTION)


if __name__ == "__main__":
    unittest.main()
