"""HASS-INTAKE-2 (G, 2026-11-16): a photo sent to Hass starts a full, routine intake interview for a new item.

One conversation test file for the skill (the existing item.add tests stay as they are). It drives the REAL Conversation, dispatcher,
editor and release path on a throwaway repo (the same Chat harness as test_item_add_dispatch): a fake photo, then every answer
Mike would give, with skips among them. It proves:

* the first question goes out on receipt, BEFORE the (slow) photo is fetched, checked or stored, from fixed words with no model
  call, and a photo that is fetched again is not asked twice;
* one question per turn, in plain words, and no model call for an answer to an intake question;
* ``skip`` and ``don't know`` work for any question, the first public ones (name, maker, town) included, and are never replaced by
  a guess or kept as a maker's name;
* fixed reading takes only complete, unambiguous answers; an odd one costs one interpreter call (first try only), is checked again,
  and is otherwise asked again (a third try is left blank and said so), never cut down to its first part;
* the New label yes/no reaches the listing (and undo restores);
* the draft Mike is shown (the exact change) has no price, cost or quantity, and neither do the files, the draft record or the
  preview the change would publish; a separate "kept private" block holds them;
* nothing is saved before his ``yes <code>``; after it the private record (state folder, ``item-intake.jsonl``, 0600) holds every
  answer, and none of the published files has any of them;
* undo is its own draft, puts the website back, and marks the private record undone;
* with the setting off nothing changes.

Run: python3 -B -m unittest hass.tests.test_item_intake_conversation -v
"""
import json
import time
import unittest
from datetime import date
from unittest import mock

from hass import conversation, media, voice
from hass.skills import item_intake as ii
from hass.skills import testkit
from hass.tests import test_item_add_dispatch as base

JAR = base.JAR
ON = {"itemIntake": True}
PRICE, COST, COUNT, LOW = "9.57", "4.31", "137", "9"
SECRETS = (PRICE, COST, COUNT + " jar")  # none of these may reach the website, a draft record or a preview
NOTE = "Sweet and smooth on warm toast. Also lovely stirred into hot tea."
REPLIES = {  # (what Mike types) -> the question he is then asked (its key); the model is never asked for any of them
    "skip": "qty", "137 jars": "sold_by", "per item": "price", f"${PRICE}": "cost", f"${COST}": "ingredients",
    "Wildflower honey and nothing else": "variety", "8 oz jar": "origin", "don't know": "claims", "raw": "allergens",
    "none": "storage", "Store at room temperature": "best_by", "Dec 20 2027": "received", "today": "low_stock",
    LOW: "customer_note", NOTE: "new_badge",
}


def questions_in(replies):
    return sum(r.count("?") for r in replies)


@unittest.skipUnless(base.HOOKS, "needs the SKILLS-FW-3d dispatcher hooks")
class Interview(unittest.TestCase):
    def chat(self, settings=ON, photo=JAR):
        chat = base.Chat([photo], None, settings)
        chat.base_commits = int(testkit._git(chat.kit.wt, "rev-list", "--count", "HEAD"))
        chat.conv.early_flush = lambda: chat.conv.flush(chat.out)  # what host.Worker does: the first question goes out on receipt
        self.addCleanup(chat.close)
        return chat

    def answer(self, chat, text, key):
        """Send one answer; the reply is exactly ONE question (one question mark), the open request waits on ``key``, and the
        reader (the model) was not asked."""
        asked = len(chat.asked)
        disposition, replies = chat.say(text)
        self.assertEqual((disposition, len(replies), questions_in(replies)), ("question", 1, 1), (text, replies))
        self.assertEqual(chat.live()["asked_slot"], ii.PREFIX + key, (text, replies))
        self.assertEqual(len(chat.asked), asked, f"{text!r} went to the model")
        return replies[0]

    def public_part(self, replies):
        """The exact change Mike is shown, from the line that introduces it to the end."""
        text = "\n".join(replies)
        return text[text.index("Here's the change I'd make:"):]

    def test_a_photo_starts_the_interview_skips_work_and_nothing_private_is_published(self):
        chat = self.chat()
        # the photo: the first question comes at once, from fixed words (no model call), with the whole list in one line
        started = time.monotonic()
        d, start = chat.say("", JAR)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual((d, start, chat.asked), ("question", [ii.START], []))
        self.assertEqual(chat.live()["asked_slot"], "name")
        # then the shop's usual public questions (name, maker, town), each read by fixed code
        self.assertIn("Who makes this wildflower honey?", chat.say("Wildflower honey")[1][0])
        self.assertEqual(chat.say("Bee Happy Farm")[1], ["Where is Bee Happy Farm based (town and state)?"])
        d, first = chat.say("Atascadero, California")
        self.assertEqual((d, len(first), questions_in(first)), ("question", 1, 1))
        self.assertTrue(first[0].startswith(ii.INTRO), first)  # the one introduction, then the first question
        self.assertEqual(chat.live()["asked_slot"], ii.PREFIX + "maker_site")
        self.assertEqual(chat.drafts(), [])  # nothing is drafted while he is being asked

        for text, key in REPLIES.items():
            self.answer(chat, text, key)
        # the last intake answer ("New label": yes) leaves only the maker's story to ask, as before; he skips it
        chat.script("yes", base.reply())
        d, last = chat.say("yes")
        self.assertEqual((d, last), ("question", ["What should we say about Bee Happy Farm? A sentence is enough."]))
        chat.script("skip", base.reply())
        d, replies = chat.say("skip")
        self.assertEqual(d, "proposed")
        proposal = "\n".join(replies)
        self.assertEqual(len(chat.asked), 1)  # the whole interview cost one model call (the maker story); every answer was read by fixed code

        # the draft: public listing only; a separate private block holds the numbers
        public, private = self.public_part(replies), proposal[:proposal.index("Here's the change I'd make:")]
        self.assertIn(ii.PRIVATE_HEAD, private)
        self.assertNotIn("$", public)
        for secret in SECRETS:
            self.assertNotIn(secret, public, secret)
            self.assertIn(secret.replace(" jar", " jars"), private, secret)
        for word in ("Price", "paid", "Bought"):
            self.assertNotIn(word, public)
        self.assertIn("Skipped, so I left them blank: maker's website, origin.", private)  # skips are named, never filled in
        self.assertIn("A new product: Wildflower honey", public)
        self.assertIn("the description: " + NOTE, public)  # his one sentence for customers became the listing text
        self.assertIn("the stock word to in stock, from the count you gave", private)  # worked out from his own count
        self.assertEqual(chat.commits(), 0)  # nothing written before his yes
        self.assertFalse((chat.conv.sdir / ii.STORE).exists())

        # the stored draft, and what the website would show for it, carry none of the private words
        (draft,) = chat.drafts()
        self.assertEqual(draft["state"], "proposed")
        rendered = chat.kit.editor.render_draft(draft["change_id"])
        blob = json.dumps([draft["ops_json"], draft["summary"], rendered], default=str)
        for secret in SECRETS + ("$" + PRICE, "$" + COST):
            self.assertFalse(secret in blob, f"{secret} is in the stored draft or its preview")
        self.assertNotIn("intake", json.dumps(chat.asked, default=str))  # the reader never saw his private answers

        # yes: the listing goes in and the private record is saved
        before = chat.kit.head()
        d, applied = chat.say(f"yes {draft['code']}")
        self.assertEqual(chat.commits(), 1, (d, applied))
        store = chat.conv.sdir / ii.STORE
        self.assertEqual(oct(store.stat().st_mode & 0o777), "0o600")
        rows = [json.loads(line) for line in store.read_text("utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["status"], row["draft"], row["name"], row["maker"], row["shelf"]),
                         ("saved", draft["code"], "Wildflower honey", "Bee Happy Farm", "pantry"))
        self.assertEqual(set(row["answers"]), set(ii.ORDER))  # every question has its answer, or its skip
        self.assertEqual(row["answers"], {
            "maker_site": None, "qty": 137, "qty_unit": "jar", "sold_by": "item", "price": PRICE, "cost": COST,
            "ingredients": "Wildflower honey and nothing else", "variety": "8 oz jar", "origin": None, "claims": "raw",
            "allergens": "none", "storage": "Store at room temperature", "best_by": "2027-12-20", "received": "2026-11-08",
            "low_stock": 9, "customer_note": NOTE, "new_badge": True})
        self.assertEqual(row["skipped"], ["maker_site", "origin"])  # "skip" and "don't know"; never a made-up answer
        self.assertTrue(row["claims_unverified"])
        self.assertRegex(row["product"], r"^photo-product-\d+$")
        # none of the files the change published has a price, a cost or a count
        changed = testkit._git(chat.kit.wt, "diff", "--name-only", before, "HEAD").split()
        self.assertTrue(any(name.endswith("products.json") for name in changed), changed)
        for name in changed:
            data = (chat.kit.wt / name).read_bytes()
            for secret in SECRETS:
                self.assertFalse(secret.encode() in data, f"{secret} in {name}")
        self.assertEqual(chat.kit.dirty(), "")

        # undo is its own draft; with his yes the listing is hidden again and the private record says so
        d, undo = chat.say("undo")
        self.assertEqual(d, "proposed", undo)
        revert = chat.drafts()[-1]
        code = revert["code"]
        self.assertEqual((revert["state"], json.loads(revert["ops_json"])[0]["op"]), ("proposed", "history.revert"), undo)
        self.assertNotEqual(code, draft["code"])
        self.assertEqual(chat.commits(), 1)  # the undo is a draft: nothing changed yet
        chat.say(f"yes {code}")
        self.assertEqual(chat.commits(), 2)
        product = next(p for p in json.loads((chat.kit.wt / "hass/content/products.json").read_text("utf-8"))["products"]
                       if p["name"] == "Wildflower honey")
        self.assertEqual(product["status"], "hidden")
        rows = [json.loads(line) for line in store.read_text("utf-8").splitlines()]
        self.assertEqual([r["status"] for r in rows], ["saved", "undone"])
        self.assertEqual(rows[1]["draft"], draft["code"])
        self.assertEqual(rows[0], row)  # the saved line is never edited
        self.assertEqual(chat.kit.dirty(), "")

    def test_an_unreadable_answer_is_asked_again_then_left_blank_and_cancel_drops_it(self):
        chat = self.chat()
        chat.script("new rigatoni from Etto", base.reply(name="Rigatoni", maker="Etto", shelf="pantry", availability="yes"))
        d, first = chat.say("new rigatoni from Etto", JAR)
        self.assertEqual((d, chat.live()["asked_slot"]), ("question", ii.PREFIX + "qty"))  # a known maker: no website question
        again = self.answer(chat, "lots", "qty")
        self.assertIn("I didn't catch an exact number", again)
        self.answer(chat, "plenty", "qty")  # asked a second time
        self.answer(chat, "tons", "sold_by")  # the third unreadable answer is left blank, never guessed
        self.assertIsNone(chat.live()["slots"]["intake"]["qty"])
        self.answer(chat, "per pound", "price")
        self.assertEqual(chat.live()["slots"]["intake"]["sold_by"], "pound")
        self.assertIn("per pound", chat.live()["question"])
        d, said = chat.say("cancel")
        self.assertEqual((d, said), ("cancelled", ["Okay, I dropped that. Nothing changed."]))
        self.assertIsNone(chat.live())
        self.assertEqual((chat.drafts(), chat.commits()), ([], 0))
        self.assertEqual(len(chat.asked), 1)  # the model read only the first message

    def test_oversized_counts_stay_in_the_private_interview(self):
        for key in ("qty", "low_stock"):
            with self.subTest(key=key):
                chat = self.chat()
                chat.say("", JAR)
                chat.say("Wildflower honey")
                chat.say("don't know")
                while chat.live()["asked_slot"] != ii.PREFIX + key:
                    chat.say("skip")
                texts = list(chat.live()["texts"])
                for answer in ("9" * 400, "1000001"):
                    said = self.answer(chat, answer, key)
                    self.assertIn("I didn't catch an exact number", said)
                    self.assertEqual(chat.live()["texts"], texts)
                    self.assertNotIn(key, chat.live()["slots"].get("intake", {}))
                next_key = "sold_by" if key == "qty" else "customer_note"
                said = self.answer(chat, "9" * 400, next_key)
                self.assertIn("I couldn't read that", said)
                self.assertIsNone(chat.live()["slots"]["intake"][key])
                self.assertEqual(chat.live()["texts"], texts)
                self.assertEqual((chat.asked, chat.drafts(), chat.commits()), ([], [], 0))
                self.doCleanups()

    def test_an_intake_parser_exception_reasks_without_the_general_interpreter(self):
        chat = self.chat()
        chat.say("", JAR)
        chat.say("Wildflower honey")
        chat.say("don't know")
        before = chat.live()
        with mock.patch.object(base.ia, "intake_read", side_effect=ValueError("unreadable")):
            said = self.answer(chat, "private unreadable answer", "qty")
        self.assertEqual(said, voice.plain(before["question"]))
        self.assertEqual(chat.live()["asks"], before["asks"] + 1)
        self.assertEqual(chat.live()["texts"], before["texts"])
        self.assertEqual(chat.live()["slots"], before["slots"])
        self.assertEqual((chat.asked, chat.drafts(), chat.commits()), ([], [], 0))

    def test_zero_cost_is_kept_in_the_private_record(self):
        for answer in ("$0.00", "0 dollars"):
            with self.subTest(answer=answer):
                self.assertEqual(ii.read("cost", answer, {}, today=date(2026, 11, 16))[:2],
                                 ("ok", {"cost": "0.00"}))
                chat = self.chat()
                chat.say("", JAR)
                chat.say("Wildflower honey")
                chat.say("don't know")
                while chat.live()["asked_slot"] != ii.PREFIX + "cost":
                    chat.say("skip")
                self.answer(chat, answer, "ingredients")
                self.assertEqual(chat.live()["slots"]["intake"]["cost"], "0.00")
                while (live := chat.live()) and (live["asked_slot"] or "").startswith(ii.PREFIX):
                    chat.say("skip")
                d, said = chat.say("in stock")
                self.assertEqual(d, "proposed", said)
                self.assertIn("You paid: $0.00 for each one.", "\n".join(said))
                self.assertNotIn("$0.00", self.public_part(said))
                self.assertEqual(chat.asked, [])
                draft, = chat.drafts()
                chat.say(f"yes {draft['code']}")
                row = json.loads((chat.conv.sdir / ii.STORE).read_text("utf-8").splitlines()[0])
                self.assertEqual(row["answers"]["cost"], "0.00")
                self.assertNotIn("cost", row["skipped"])
                self.assertEqual(chat.commits(), 1)
                self.doCleanups()

    # -- the first question is sent before the photo is fetched, checked or stored ---------------------------------------
    def test_the_first_question_is_sent_before_the_slow_photo_work(self):
        chat = self.chat()
        events, delay = [], 0.4
        fetch, send, check = chat.photos.fetch, chat.out.send, media.check_photo

        def slow_fetch(*args):
            events.append(("fetch", time.monotonic()))
            time.sleep(delay)
            return fetch(*args)

        def slow_check(data):
            time.sleep(delay)
            return check(data)

        def timed_send(chat_id, text, attachments=()):
            events.append(("sent", time.monotonic(), text))
            return send(chat_id, text, attachments)

        chat.photos.fetch, chat.out.send = slow_fetch, timed_send
        with mock.patch.object(media, "check_photo", slow_check):
            started = time.monotonic()
            disposition, replies = chat.say("", JAR)
            total = time.monotonic() - started
        self.assertEqual((disposition, replies), ("question", [ii.START]))
        kinds = [e[0] for e in events]
        self.assertEqual(kinds[0], "sent", kinds)  # the question left BEFORE the photo was fetched
        first_send = events[0][1] - started
        self.assertLess(first_send, 0.25, first_send)
        self.assertGreaterEqual(total, 2 * delay)  # the slow work really ran, after the question
        self.assertEqual(sum(1 for e in events if e[0] == "sent"), 1)  # exactly one question
        self.assertEqual(chat.asked, [])  # no model call
        self.assertEqual(chat.live()["asked_slot"], "name")
        for topic in ("name", "maker", "how many", "price", "dates", "customers"):  # the whole list, in one short line
            self.assertIn(topic, ii.START)
        self.assertEqual(ii.START.count("?"), 1)

    def test_a_photo_that_is_tried_again_is_not_asked_twice_and_a_second_photo_message_is_not_either(self):
        chat = self.chat()
        fails = {"left": 1}
        fetch = chat.photos.fetch

        def flaky(*args):
            if fails["left"]:
                fails["left"] -= 1
                raise OSError("not yet")
            return fetch(*args)

        chat.photos.fetch = flaky
        chat.n += 1
        chat.photos.files["again-1"] = JAR
        msg = conversation.Inbound("again-1", base.testkit.CHAT, base.testkit.OWNER, "", False, "new", chat.now.isoformat(), 1)
        with self.assertRaises(conversation.AttachmentPending):
            chat.conv.handle(msg)
        chat.conv.flush(chat.out)
        self.assertEqual([r["text"] for r in chat.out.sent], [ii.START])  # asked once, before the failed fetch
        self.assertEqual(chat.conv.handle(msg, last_try=True), "question")  # the retry fetches the photo and opens the request
        chat.conv.flush(chat.out)
        self.assertEqual([r["text"] for r in chat.out.sent], [ii.START])  # ... without a second question
        self.assertEqual(chat.live()["asked_slot"], "name")

    def test_a_caption_or_a_busy_request_keeps_the_old_path(self):
        chat = self.chat()
        chat.script("new rigatoni from Etto", base.reply(name="Rigatoni", maker="Etto", shelf="pantry", availability="yes"))
        d, replies = chat.say("new rigatoni from Etto", JAR)  # a caption: the model reads it, no early question
        self.assertNotIn(ii.START, replies)
        self.assertEqual(d, "question")
        self.assertEqual(len(chat.asked), 1)

    # -- skip and don't know at the PUBLIC questions --------------------------------------------------------------------
    def test_skip_and_dont_know_at_the_first_questions_never_become_a_name_or_a_maker(self):
        chat = self.chat()
        chat.say("", JAR)
        d, said = chat.say("skip")  # a name is needed: said honestly, asked once more, nothing invented
        self.assertEqual((d, len(said), questions_in(said)), ("question", 1, 1))
        self.assertIn("without a name", said[0])
        self.assertEqual(chat.live()["asked_slot"], "name")
        self.assertIsNone(chat.live()["slots"].get("name"))
        d, said = chat.say("I don't know")
        self.assertEqual((d, chat.live()["asked_slot"]), ("question", "name"))
        self.assertIn("won't make one up", said[0])
        self.assertEqual(chat.asked, [])
        d, said = chat.say("Wildflower honey")
        self.assertIn("Who makes this wildflower honey?", said[0])
        d, said = chat.say("don't know")  # an unknown maker is not a maker's name
        self.assertEqual((d, chat.live()["asked_slot"]), ("question", ii.PREFIX + "qty"))
        self.assertEqual(chat.live()["slots"]["maker"], "unknown")
        self.assertEqual(chat.asked, [])
        while (live := chat.live()) and (live["asked_slot"] or "").startswith(ii.PREFIX):
            d, said = chat.say("skip")
        self.assertEqual(said, ["Is it in stock right now?"])  # no count given: the stock word is asked, never worked out
        d, said = chat.say("in stock")
        self.assertEqual(d, "proposed", said)
        text = "\n".join(said)
        self.assertIn("I couldn't tell who makes it", text)
        self.assertNotIn("don't know", self.public_part(said).replace("I couldn't tell", ""))
        (draft,) = chat.drafts()
        chat.say(f"yes {draft['code']}")
        row = json.loads((chat.conv.sdir / ii.STORE).read_text("utf-8").splitlines()[0])
        self.assertEqual((row["maker"], row["maker_unknown"], row["name"]), (None, True, "Wildflower honey"))
        self.assertEqual(set(row["skipped"]), set(ii.ORDER) - {"qty_unit", "maker_site"})  # every question asked was skipped: all named, none made up

    def test_skipping_the_town_of_a_new_maker_leaves_the_maker_not_identified(self):
        chat = self.chat()
        chat.say("", JAR)
        chat.say("Wildflower honey")
        d, said = chat.say("Bee Happy Farm")
        self.assertEqual(said, ["Where is Bee Happy Farm based (town and state)?"])
        d, said = chat.say("skip")
        self.assertEqual((d, chat.live()["asked_slot"]), ("question", ii.PREFIX + "qty"))  # a new maker with no town is never added
        self.assertEqual(chat.live()["slots"]["maker"], "unknown")
        while (live := chat.live()) and (live["asked_slot"] or "").startswith(ii.PREFIX):
            d, said = chat.say("skip")
        self.assertEqual(said, ["Is it in stock right now?"])  # no count given: the stock word is asked, never worked out
        d, said = chat.say("in stock")
        self.assertEqual(d, "proposed", said)
        self.assertNotIn("is new on the site", "\n".join(said))
        (draft,) = chat.drafts()
        chat.say(f"yes {draft['code']}")
        row = json.loads((chat.conv.sdir / ii.STORE).read_text("utf-8").splitlines()[0])
        self.assertEqual((row["maker"], row["maker_unknown"]), ("Bee Happy Farm", False))  # his word is kept privately, never published
        products = json.loads((chat.kit.wt / "hass/content/products.json").read_text("utf-8"))["products"]
        self.assertNotIn("Bee Happy Farm", json.dumps(products))

    # -- complete, unambiguous fixed reading; anything else goes to the interpreter once, then is asked again -----------
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

    def test_an_odd_answer_in_the_conversation_costs_one_interpreter_call_and_is_never_guessed(self):
        chat = self.chat()
        calls = []

        class Reader:
            def read(self, key, words, today):
                calls.append((key, words))
                return {"value": None}  # "I cannot tell"

        chat.conv.answer_reader = Reader()
        chat.script("new rigatoni from Etto", base.reply(name="Rigatoni", maker="Etto", shelf="pantry", availability="yes"))
        d, first = chat.say("new rigatoni from Etto", JAR)
        self.assertEqual(chat.live()["asked_slot"], ii.PREFIX + "qty")
        self.answer(chat, "12 or maybe 24 jars", "qty")  # asked again; the interpreter said it cannot tell
        self.assertEqual(calls, [("qty", "12 or maybe 24 jars")])
        self.assertNotIn("qty", chat.live()["slots"].get("intake", {}))  # 12 was NOT kept
        self.answer(chat, "24 jars please maybe", "qty")  # a second odd answer: not interpreted again
        self.assertEqual(len(calls), 1)
        reply = self.answer(chat, "24 jars", "sold_by")
        self.assertEqual(chat.live()["slots"]["intake"]["qty"], 24)
        self.answer(chat, "per item", "price")
        self.answer(chat, "9 dollars and 57 cents", "cost")  # exact words: fixed reading, no call
        self.assertEqual(chat.live()["slots"]["intake"]["price"], "9.57")
        self.assertEqual(len(calls), 1)
        for text, key in (("skip", "ingredients"), ("skip", "variety"), ("skip", "origin"), ("skip", "claims"), ("skip", "allergens"),
                          ("skip", "storage"), ("skip", "best_by")):
            self.answer(chat, text, key)
        for tries in range(2):  # an unreadable date twice, then a third time: left blank and said so
            self.answer(chat, "some time in spring", "best_by")
        said = self.answer(chat, "some time in spring", "received")
        self.assertTrue(said.startswith("I couldn't read that, so I left the best-by date blank."), said)
        self.assertIsNone(chat.live()["slots"]["intake"]["best_by"])
        self.assertEqual(len(chat.asked), 1)  # the one model call is the shop's own first read of his caption

    # -- the New label: his yes or no reaches the public listing -------------------------------------------------------
    def _etto_interview(self, chat, new_badge):
        chat.script("new rigatoni from Etto", base.reply(name="Rigatoni", maker="Etto", shelf="pantry", availability="yes"))
        chat.say("new rigatoni from Etto", JAR)
        answers = {"qty": "12 bags", "sold_by": "per bag", "price": "$9.57", "cost": "$4.31",
                   "customer_note": "Lovely with a simple tomato sauce.", "new_badge": new_badge}
        while (live := chat.live()) and (live["asked_slot"] or "").startswith(ii.PREFIX):
            d, said = chat.say(answers.get(live["asked_slot"][len(ii.PREFIX):], "skip"))
        self.assertEqual(d, "proposed", said)
        return said, chat.drafts()[-1]

    def test_the_new_label_answer_is_honored_in_the_listing_and_undo_restores(self):
        for answer, shows in (("no", False), ("yes", True)):
            with self.subTest(answer):
                chat = self.chat()
                said, draft = self._etto_interview(chat, answer)
                public = self.public_part(said)
                self.assertEqual("no New label on it, as you asked" in "\n".join(said), not shows, said)
                self.assertNotIn("New label", public)  # the line is in what I set, not in the listing text itself
                self.assertEqual('"showNew"' in draft["ops_json"], not shows)
                before = chat.kit.head()
                chat.say(f"yes {draft['code']}")
                products = json.loads((chat.kit.wt / "hass/content/products.json").read_text("utf-8"))["products"]
                product = next(p for p in products if p["name"] == "Rigatoni")
                self.assertEqual("addedOn" in product, shows, product)  # with no day the shop shows no New label (shop.js isNew)
                self.assertEqual(product.get("addedOn"), "2026-11-08" if shows else None)
                self.assertNotIn("showNew", json.dumps(products))  # the flag is not itself a public field
                for name in testkit._git(chat.kit.wt, "diff", "--name-only", before, "HEAD").split():
                    data = (chat.kit.wt / name).read_bytes()
                    for secret in ("9.57", "4.31", "12 bags"):
                        self.assertFalse(secret.encode() in data, f"{secret} in {name}")
                d, undo = chat.say("undo")
                self.assertEqual(d, "proposed", undo)
                chat.say(f"yes {chat.drafts()[-1]['code']}")
                products = json.loads((chat.kit.wt / "hass/content/products.json").read_text("utf-8"))["products"]
                self.assertEqual(next(p for p in products if p["name"] == "Rigatoni")["status"], "hidden")
                self.assertEqual(chat.kit.dirty(), "")

    def test_on_the_live_site_a_no_to_the_new_label_is_said_not_hidden(self):
        # G's live table of allowed arguments has no argument for it, so the live draft says so before his yes and writes his no down
        chat = self.chat()
        with mock.patch.object(base.ia, "_live", return_value=True):
            said, draft = self._etto_interview(chat, "no")
        text = "\n".join(said)
        self.assertIn("Left off: your no to the New label", text)
        self.assertIn("I wrote your no down for Graham", text)
        self.assertNotIn("showNew", draft["ops_json"])
        chat.say(f"yes {draft['code']}")
        row = json.loads((chat.conv.sdir / ii.STORE).read_text("utf-8").splitlines()[0])
        self.assertIs(row["answers"]["new_badge"], False)

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
