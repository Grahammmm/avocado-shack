"""HASS-INTAKE-2 (G, 2026-11-16): a photo sent to Hass starts a full, routine intake interview for a new item.

One conversation test file for the skill (the existing item.add tests stay as they are). It drives the REAL Conversation, dispatcher,
editor and release path on a throwaway repo (the same Chat harness as test_item_add_dispatch): a fake photo, then every answer
Mike would give, with skips among them. It proves:

* one question per turn, in plain words, and no model call for an answer to an intake question;
* ``skip`` and ``don't know`` work for any question and are never replaced by a guess;
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
        self.assertIn("I didn't catch a number", again)
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
