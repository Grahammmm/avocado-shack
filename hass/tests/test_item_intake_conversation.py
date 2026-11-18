"""The single-preview contract supersedes the intake interview. Offline real editor journeys.

Parser and setting-off regressions remain; approval/privacy/undo coverage is in test_intake_simple.
"""
import json
import unittest
from datetime import date
from unittest import mock

from hass import conversation
from hass.skills import item_intake as ii
from hass.tests import test_item_add_dispatch as base

JAR = base.JAR


class IntakeConversation(unittest.TestCase):
    def chat(self, settings=None):
        chat = base.Chat([JAR], None, {"itemIntake": True} if settings is None else settings)
        chat.base_commits = int(base.testkit._git(chat.kit.wt, "rev-list", "--count", "HEAD"))
        self.addCleanup(chat.close)
        return chat

    def test_text_before_photo_is_combined_without_an_interview(self):
        chat = self.chat()
        text = "new rigatoni from Etto"
        chat.script(text, base.reply(name="Rigatoni", maker="Etto", shelf="pantry"))
        d, said = chat.say(text + "; bought 100 at $1; sell for $2")
        self.assertEqual(d, "question", said)
        self.assertEqual(chat.live()["asked_slot"], ii.PREFIX + "photo")
        d, said = chat.say("", JAR)
        self.assertEqual(d, "proposed", said)
        self.assertEqual(chat.live()["slots"]["name"], "Rigatoni")
        self.assertEqual(chat.live()["slots"]["intake"]["qty"], 100)
        self.assertEqual([t[0] for t in chat.asked], [text])
        self.assertNotIn("$", chat.drafts()[0]["ops_json"])
        self.assertIn("$1.00", said[0])
        self.assertEqual(chat.commits(), 0)

    def test_no_reader_and_skipped_unknown_name_never_become_fake_identity(self):
        chat = self.chat()
        chat.say("sell for $2", JAR)
        self.assertEqual(chat.live()["asked_slot"], ii.PREFIX + "name")
        for words in ("skip", "What's next", "?"):
            _, said = chat.say(words)
            self.assertNotIn("?", said[0])
            self.assertNotIn("name", chat.live()["slots"])
        d, said = chat.say("Wildflower honey")
        self.assertEqual(d, "proposed", said)
        self.assertEqual(chat.live()["slots"]["maker"], "Producer not identified")
        chat.say("yes " + chat.live()["draft_code"])
        saved = json.loads((chat.conv.sdir / ii.STORE).read_text().splitlines()[0])
        self.assertTrue(saved["maker_unknown"])
        self.assertIsNone(saved["maker"])

    def test_zero_cost_is_retained_without_an_optional_cost_question(self):
        chat = self.chat()
        chat.say("bought 12 at $0; price 2", JAR)
        d, said = chat.say("Honey")
        self.assertEqual(d, "proposed", said)
        self.assertEqual(chat.live()["slots"]["intake"]["cost"], "0.00")
        self.assertIn("$0.00", said[0])
        self.assertNotIn("$", chat.drafts()[0]["ops_json"])

    def test_fetch_retry_still_has_no_duplicate_preview_or_first_question(self):
        chat = self.chat()
        fetch = chat.photos.fetch
        chat.photos.files["retry-1"] = JAR
        msg = conversation.Inbound("retry-1", base.testkit.CHAT, base.testkit.OWNER,
                                   "sell for $2", False, "new", chat.now.isoformat(), 1)
        with mock.patch.object(chat.photos, "fetch", side_effect=OSError("not yet")):
            with self.assertRaises(conversation.AttachmentPending): chat.conv.handle(msg)
        chat.conv.flush(chat.out)
        self.assertEqual(chat.out.sent, [])
        chat.photos.fetch = fetch
        self.assertEqual(chat.conv.handle(msg, last_try=True), "question")
        chat.conv.flush(chat.out)
        self.assertEqual(len(chat.out.sent), 1)
        self.assertEqual(chat.conv.handle(msg), "duplicate")
        self.assertEqual(chat.live()["slots"]["intake"]["price"], "2.00")

    def test_cancel_never_leaves_an_approvable_listing(self):
        chat = self.chat()
        chat.say("price 2", JAR)
        chat.say("Honey")
        code = chat.live()["draft_code"]
        d, _ = chat.say("cancel")
        self.assertEqual(d, "cancelled")
        self.assertIsNone(chat.live())
        chat.say("yes " + code)
        self.assertEqual(chat.commits(), 0)
        self.assertEqual(chat.drafts()[0]["state"], "rejected")

    def test_fixed_reading_takes_only_complete_answers(self):
        today = date(2026, 11, 16)
        ok = lambda key, text: ii.read(key, text, {}, today=today)[:2]  # noqa: E731
        self.assertEqual(ok("price", "9 dollars and 57 cents"), ("ok", {"price": "9.57"}))
        self.assertEqual(ok("price", "nine dollars"), ("ok", {"price": "9.00"}))
        self.assertEqual(ok("price", "$9.5"), ("ok", {"price": "9.50"}))
        self.assertEqual(ok("price", "nine dollars and fifty seven cents"), ("ok", {"price": "9.57"}))
        self.assertEqual(ok("qty", "12 jars"), ("ok", {"qty": 12, "qty_unit": "jar"}))
        self.assertEqual(ok("qty", "twelve"), ("ok", {"qty": 12}))
        self.assertEqual(ok("qty", "a dozen"), ("ok", {"qty": 12, "qty_unit": "each"}))
        self.assertEqual(ok("new_badge", "no"), ("ok", {"new_badge": False}))
        self.assertEqual(ok("sold_by", "by the pound"), ("ok", {"sold_by": "pound"}))
        for key, text in (("price", "9.575"), ("price", "9 dollars and a bit"), ("price", "$9 or $12"), ("qty", "12 or maybe 24 jars"),
                          ("qty", "about 12"), ("qty", "12 jars of honey"), ("qty", "lots"), ("new_badge", "yes, actually no"),
                          ("new_badge", "yes but no"), ("sold_by", "per pound or per bag"), ("best_by", "sometime next spring"),
                          ("low_stock", "5 or 6"), ("received", "last tuesday or so")):
            got = ii.read(key, text, {}, today=today)
            self.assertEqual(got[0], "again", (key, text, got))  # never cut down to its first part
        # the interpreter: asked once, on the first try only, and its value is checked again
        calls = []

        def reader(answer):
            def read(key, words):
                calls.append((key, words))
                return answer
            return read

        got = ii.read("price", "about nine fifty", {}, today=today, reader=reader({"value": "9.50"}))
        self.assertEqual((got[0], got[1], len(calls)), ("ok", {"price": "9.50"}, 1))
        calls.clear()
        for bad in ({"value": None}, {"value": "lots"}, {"value": -3}, {"value": "9.5.5"}, {"value": [9, 12]}, {}, None, "x"):
            got = ii.read("price", "about nine fifty", {}, today=today, reader=reader(bad))
            self.assertEqual(got[0], "again", bad)
        self.assertEqual(len(calls), 8)  # one call each, never more
        calls.clear()
        self.assertEqual(ii.read("price", "about nine fifty", {}, today=today, asks=2, reader=reader({"value": "9.50"}))[0], "again")
        self.assertEqual(calls, [])  # only the first try is interpreted
        self.assertEqual(ii.read("price", "9.57", {}, today=today, reader=reader({"value": "1.00"}))[1], {"price": "9.57"})
        self.assertEqual(calls, [])  # an exact answer never costs a model call
        self.assertEqual(ii.read("qty", "12 or maybe 24 jars", {}, today=today, reader=reader({"value": {"number": 12, "unit": "jar"}}))[1],
                         {"qty": 12, "qty_unit": "jar"})  # an exact value from the interpreter is taken after the same checks
        raising = mock.Mock(side_effect=RuntimeError("down"))
        self.assertEqual(ii.read("price", "about nine fifty", {}, today=today, reader=raising)[0], "again")
        # the third unreadable answer is left blank, and he is told so
        third = ii.read("price", "about nine fifty", {}, today=today, asks=3)
        self.assertEqual(third, ("ok", {"price": None}, {}, "I couldn't read that, so I left the price blank."))


    def test_with_the_setting_off_nothing_changes(self):
        chat = self.chat(settings={})
        text = "new hot sauce from Cal Poly, in stock"
        chat.script(text, base.reply(name="Hot sauce", maker="Cal Poly", shelf="pantry", availability="yes"))
        d, replies = chat.say(text, JAR)
        self.assertEqual(d, "proposed")
        text = "\n".join(replies)
        self.assertNotIn(ii.PRIVATE_HEAD, text)
        self.assertNotIn(ii.INTRO, text)
        self.assertFalse((chat.conv.sdir / ii.STORE).exists())



if __name__ == "__main__":
    unittest.main()
