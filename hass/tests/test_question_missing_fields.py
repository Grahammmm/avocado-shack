"""AV0007-03 (H05): questions name fields in owner words while the interpreter's pending entry carries the ids.
Throwaway Git repos and a fake photo source; no network. Run: python3 -B -m unittest hass.tests.test_question_missing_fields -v
"""

import json
import unittest
from datetime import timedelta

from hass import conversation, interpreter_prompt, voice
from hass.ops.catalog import PRODUCT_EDITABLE
from hass.conversation import Inbound, _missing_ids
from hass.field_words import field_list
from hass.fixture_chat import FixtureAdapter
from hass.tests import test_photo_draft as pd
from hass.tests.test_catalog_ops import NEW
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase
from hass.tests.test_set_photo import ALT, PID, PhotoRepo, _settings

ALT_WORDS = "a few words saying what the photo shows"
RULE = ('A pending question\'s "missing" list contains argument ids; fill those arguments from the owner\'s answer, '
        "not from the wording of the question. Never invent a missing value.")


class QuestionWordsTests(HikeTestCase):
    def missing_of(self, repo, op, args):
        result = self.assertRejected(repo, "needs-details", (op, args))
        return result["missing"], result["question"]

    def test_required_and_one_of_questions_keep_ids(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        cases = [
            (("route.add", {"title": "T", "place": "P", "sourceUrl": "https://trails.example.org/x", "sourceName": "N"}),
             "Please provide: "),
            (("maker.edit", {"key": "Etto"}), "What would you like to change about Etto? You can change: "),
            (("hike.update", {"id": HIKE_ID}), f"What would you like to change about the hike {HIKE['title']}? You can change: "),
        ]
        for (op, args), prefix in cases:
            with self.subTest(op=op):
                missing, question = self.missing_of(repo, op, args)
                self.assertTrue(voice.plain(question).startswith(prefix), question)
                self.assertEqual(voice.plain(question)[len(prefix):], field_list(missing))  # prose mapped, ids untouched
                self.assertEqual(voice.check(question), [], question)  # and nothing a person would not say
                self.assertTrue(missing and all(isinstance(m, str) for m in missing))
        missing, question = self.missing_of(repo, "product.edit", {"id": "photo-product-001"})
        self.assertEqual(missing, list(PRODUCT_EDITABLE) + ["producerKey", "clearProducer", "clearImageAlt"])
        products = json.loads((repo.wt / "hass/content/products.json").read_text())["products"]
        product = next(p for p in products if p["id"] == "photo-product-001")
        self.assertEqual(voice.plain(question), f"What would you like to change about {product['name']}?")
        self.assertEqual(voice.check(question), [])
        missing, question = self.missing_of(repo, "maker.edit", {"key": "Etto"})
        self.assertIn("clearUrl", missing)
        self.assertTrue(question.endswith("remove the website link"), question)
        missing, question = self.missing_of(repo, "hike.update", {"id": HIKE_ID})
        self.assertIn("noCapacityLimit", missing)
        self.assertIn("no guest limit", question)
        self.assertNotIn("noCapacityLimit", question)

    def test_editor_missing_args_are_mapped_but_ids_kept(self):
        repo = self.repo()
        result = self.assertRejected(repo, "needs-details", ("product.set_photo", {"id": PID, "photo": pd.SHA}))
        self.assertEqual(result["missing"], ["imageAlt"])
        self.assertEqual(result["question"], f"Please provide: {ALT_WORDS}")
        result = self.assertRejected(repo, "needs-details", ("maker.add", {"key": "K", "name": "K", "place": "P"}))
        self.assertEqual(result["missing"], ["story"])
        self.assertEqual(result["question"], "Please provide: the story")

    def test_no_photo_guides_caption_without_writes(self):
        repo = self.repo()
        fields = {k: v for k, v in NEW.items() if k != "image"}
        for extra in ({}, {"imageAlt": ALT}):
            with self.subTest(extra=extra):
                result = self.assertRejected(repo, "refused", ("product.add", {**fields, **extra}))
                self.assertEqual(result["reason"], "Send the photo with the product name as its caption.")
        result = self.assertRejected(repo, "refused", ("product.add", {**fields, "photo": pd.SHA}))
        self.assertEqual(result["reason"], "imageAlt is required with photo")  # unchanged


class RecordingInterpreter:
    """Fills a pending question's `missing` ids from the owner's answer (never from the question wording)."""

    def __init__(self):
        self.pendings, self.answers = [], {}

    def interpret(self, text, pending, *, sent_at=None):
        self.pendings.append(json.loads(json.dumps(pending)))
        if text not in self.answers: return {"unsupported": "Sorry, I can't do that yet."}
        waiting = [p for p in pending if p["state"] == "needs-details"]
        entry = waiting[-1]
        args = {"photo": entry["ops"][0]["args"]["photo"], **{k: v for k, v in self.answers[text].items()
                                                              if k in entry["missing"] + ["id"]}}
        return {"ops": [{"op": "product.set_photo", "args": args}], "revises": entry["code"]}


class ConversationBase(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.photos, self.interp, self.out, self.n, self.now = pd.FakePhotos(), RecordingInterpreter(), FixtureAdapter(), 0, T0
        self.conv = self.open()

    def open(self):
        return conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                         lambda: self.now, photos=self.photos)

    def say(self, text="", attachments=0):
        self.n += 1
        return self.conv.handle(Inbound(f"m{self.n}", CHAT, OWNER, text, received_at=self.now.isoformat(),
                                        attachments=attachments))

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def waiting(self):  # what the interpreter is shown for a harmless message
        self.assertEqual(self.say("hello there"), "unsupported")
        self.replies()
        return self.interp.pendings[-1]


class PhotoMissingTests(ConversationBase):
    def test_photo_answer_missing_alt_round_trip(self):
        self.interp.answers["lion's mane"] = {"id": PID}
        self.interp.answers["Ripe avocados"] = {"id": PID, "imageAlt": ALT}
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        [entry] = self.waiting()
        self.assertEqual(entry["missing"], ["id", "imageAlt"])
        self.assertEqual(self.say("lion's mane"), "needs-details")
        self.assertEqual(self.replies(), [f"Please provide: {ALT_WORDS}"])
        [entry] = self.waiting()
        self.assertEqual((entry["missing"], entry["question"]), (["imageAlt"], f"Please provide: {ALT_WORDS}"))
        self.assertEqual(self.say("Ripe avocados"), "proposed")  # the fixture fills imageAlt from pending.missing
        [row] = self.drafts()
        self.assertEqual((row["state"], row["missing_json"]), ("proposed", None))  # the proposal needs an explicit yes
        self.assertEqual(json.loads(row["ops_json"])[0]["args"]["imageAlt"], ALT)
        [entry] = self.waiting()
        self.assertNotIn("missing", entry)  # proposed entries keep their shape
        self.assertEqual(list(entry), ["code", "state", "summary", "ops"])

    def test_missing_metadata_refresh_restart_and_legacy(self):
        self.interp.answers["lion's mane"] = {"id": PID}
        self.say(attachments=1)
        self.say("lion's mane")
        self.replies()
        self.conv.db.close()
        self.conv = self.open()  # restart: the ids come from the database, not from the question prose
        [entry] = self.waiting()
        self.assertEqual(entry["missing"], ["imageAlt"])
        db = self.conv.db  # an old database (no column) reopens without data loss and shows an empty list
        db.execute("ALTER TABLE drafts DROP COLUMN missing_json")
        db.close()
        self.conv = self.open()
        [row] = self.drafts()
        self.assertEqual((row["state"], row["missing_json"]), ("needs-details", None))
        self.assertEqual(self.waiting()[0]["missing"], [])
        self.assertEqual(self.waiting()[0]["question"], f"Please provide: {ALT_WORDS}")

    def test_malformed_metadata_is_an_empty_list_never_parsed_from_prose(self):
        for bad in (None, "", "nope", "{}", '"id"', "5", '["a", 1]', '["a", null]', "[[]]"):
            with self.subTest(bad=bad):
                self.assertEqual(_missing_ids(bad), [])
        self.assertEqual(_missing_ids('["a", "", "b", "a"]'), ["a", "b"])  # unique, non-empty, original order
        self.say(attachments=1)
        self.conv.db.execute("UPDATE drafts SET missing_json = ?", ('{"imageAlt": 1}',))
        self.assertEqual(self.waiting()[0]["missing"], [])

    def test_cancelled_and_expired_questions_are_not_pending(self):
        self.say(attachments=1)
        code = self.drafts()[0]["code"]
        self.assertEqual(self.say(f"no {code}"), "rejected")
        self.assertEqual(self.waiting(), [])
        self.say(attachments=1)  # a fresh photo question... (same photo, new code is not issued: it is a duplicate)
        self.now += timedelta(seconds=SETTINGS["approvalTtlSeconds"] + 1)
        self.assertEqual(self.waiting(), [])


class PromptRuleTests(unittest.TestCase):
    def test_prompt_missing_rule_and_snapshot(self):
        from hass.tests.test_interpreter_prompt import FIXTURE
        text = FIXTURE.read_text("utf-8")
        self.assertEqual((text.count(RULE), interpreter_prompt.RULES.count(RULE)), (1, 1))
        self.assertLess(len(text.encode("utf-8")), interpreter_prompt.PROMPT_MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
