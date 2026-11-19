"""AV1052-07 (F07/H17): `post <name or alias>` acts as `post <id>` when exactly one ACTIVE product fits; several reply find-style
lines (up to 10, with ids); none says to use find. Exact ids, `post hike` and `post maker` keep their meaning. Read-only.
Synthetic fixtures only (the conversation test store). Run: python3 -B -m unittest hass.tests.test_post_by_name -v
"""

import hashlib
import json
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, voice
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

NONE = 'No active product matches "{}"; send find <words> for ids.'
MORE = "There are more. Add a word to narrow it down."
UNAVAILABLE = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"


class NameFixture(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.cdir = self.repo.wt / "hass" / "content"
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "reached the interpreter/editor"))

    def photos(self):  # every product gets a real photo, so a post by id is a full caption + attachment to compare against
        site = self.repo.wt / "storefront-mockup" / "post-test"
        site.mkdir(parents=True)
        (site / "real.jpg").write_bytes(b"jpeg")
        self.edit(lambda doc: [p.update(image="post-test/real.jpg") for p in doc["products"]])

    def edit(self, change):
        path = self.cdir / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")

    def set_status(self, pid, status):
        extra = {"hold": {"reason": "fixture", "source": "https://example.com/"}} if status == "held" else {}
        self.edit(lambda doc: next(p for p in doc["products"] if p["id"] == pid).update(status=status, **extra))

    def active_ids(self, word):  # the plain rule the lookup follows, written out independently
        doc = json.loads((self.cdir / "products.json").read_text("utf-8"))
        return sorted(p["id"] for p in doc["products"] if p["status"] == "active"
                      and any(word in p.get(f, "").lower() for f in ("name", "brand", "displayBrand")))

    def ask(self, text):
        n = self.n
        self.assertEqual(self.say(text), self.verb)
        self.assertEqual(self.disposition(f"m{n + 1}"), self.verb)
        [row] = self.conv.db.execute("SELECT text, attachments FROM outbox ORDER BY id DESC LIMIT 1").fetchall()
        self.assertEqual(len(self.replies()), 1)
        return row["text"], json.loads(row["attachments"] or "[]")

    verb = "post"

    def sentence(self, text):
        """A sentence that names no product is not a command: it goes to the interpreter, as on main (HASS-VOICE-1)."""
        self.assertNotEqual(self.say(text), self.verb)
        self.assertEqual(self.calls[:1], ["interpret"], text)
        self.calls.clear()
        self.replies()

    def digest(self):
        return hashlib.sha256(b"".join(p.read_bytes() for p in sorted(self.cdir.glob("*.json")))).hexdigest()


class PostByNameTests(NameFixture):
    def test_name_alias_equals_exact_id(self):
        # Contract: a unique name or alias is the id. Bug caught: a reply or attachment that differs from sending the id.
        self.photos()
        self.assertNotIn("memory", self.tables())
        for query, pid in (("Figs", "photo-product-097"), ("BRIAN’S SOURDOUGH BREAD!", "photo-product-015"),
                           ("brians sourdough bread", "photo-product-015"), ("chevre", "photo-product-035"),
                           ("lobster MUSHROOMS", "photo-product-155"), ("Hass avocado", "photo-product-001")):
            with self.subTest(query=query):
                want = self.ask(f"post {pid}")
                self.assertTrue(want[0].startswith("This picture is an illustration") and want[1], want)
                self.assertEqual(self.ask(f"post {query}"), want)
        self.assertNotIn("memory", self.tables(), "a read created the memory table")
        self.assertEqual(self.say("alias green jam: photo-product-010"), "memory-saved")
        self.replies()
        for query in ("green jam", "Green-Jam", "GREEN  JAM."):
            with self.subTest(alias=query):
                self.assertEqual(self.ask(f"post {query}"), self.ask("post photo-product-010"))
        self.assertEqual(self.say("alias etto: Etto"), "memory-saved")  # a maker alias never selects a product
        self.replies()
        text, files = self.ask("post etto")
        self.assertEqual(files, [])
        self.assertTrue(text.startswith("product photo-product-"), text)

    def test_ambiguity_and_cap_use_find_lines(self):
        # Contract: several active matches are listed, never guessed. Bug caught: a held or hidden row taking one of the 10 slots.
        self.photos()
        names = {p["id"]: p["name"] for p in json.loads((self.cdir / "products.json").read_text("utf-8"))["products"]}
        for query in ("yogurt", "sourdough"):
            ids = self.active_ids(query)
            self.assertIn(len(ids), (2, 3))
            self.assertEqual(self.ask(f"post {query}"), ("\n".join(f"product {i}: {names[i]} (active)" for i in ids), []))
        ids = self.active_ids("cal poly")  # a brand match fills the lookup's 10
        self.assertGreaterEqual(len(ids), 13)
        text, files = self.ask("post cal poly")
        self.assertEqual((text.splitlines()[:-1], text.splitlines()[-1], files), (
            [f"product {i}: {names[i]} (active)" for i in ids[:10]], MORE, []))
        for pid in ids[:3]:
            self.set_status(pid, "hidden")  # the first three ids can no longer use up slots
        text, _ = self.ask("post cal poly")
        self.assertEqual(text.splitlines()[:-1], [f"product {i}: {names[i]} (active)" for i in self.active_ids("cal poly")[:10]])
        self.assertEqual(len(text.splitlines()), 11)

    def test_inactive_name_is_not_selected(self):
        # Contract: names act only on active products; exact ids keep their old answers. Bug caught: a held product posted by name.
        self.photos()
        self.assertEqual(self.ask("post raw milk goat cheddar"), (NONE.format("raw milk goat cheddar"), []))  # held only
        self.assertEqual(self.ask("post white cheddar"), self.ask("post photo-product-038"))  # held twin ignored: one active
        self.assertEqual(self.ask("post photo-product-040")[0], "photo-product-040 isn't on the website right now.")
        self.set_status("photo-product-097", "hidden")
        self.assertEqual(self.ask("post Figs")[0], "I don't know a product called Figs. Try find and a word from its name.")
        self.assertEqual(self.say("alias fig tree: photo-product-097"), "memory-saved")
        self.replies()
        self.set_status("photo-product-097", "held")  # a saved alias cannot authorize an inactive product
        self.assertEqual(self.ask("post fig tree")[0], NONE.format("fig tree"))  # it still names a product, so it is answered here
        for text in ("post PHOTO-PRODUCT-001", "post Photo-Product-001", "post photo-product-001x"):  # id-shaped: not repaired
            self.assertEqual(self.ask(text)[0], f"I don't know a product called {text[5:]}. Try find and a word from its name.")

    def test_reserved_modes_keep_precedence(self):
        # Contract: hike and maker words are dispatched first. Bug caught: `post hike boots` read as a product called "hike boots".
        self.photos()
        self.edit(lambda doc: doc["products"][0].update(name="hike boots"))
        self.edit(lambda doc: doc["products"][1].update(name="maker mix"))
        self.edit(lambda doc: doc["products"][2].update(name="makers rest"))
        self.assertEqual(self.ask("post hike boots")[0], "I don't know a hike called boots. Try find and a word from its name.")
        self.assertEqual(self.ask("Post Maker Mix")[0], "No maker Mix; send find <words> for keys.")
        self.assertTrue(self.ask("post makers rest")[0].startswith("This picture is an illustration"))  # a lookalike word is a name
        self.assertEqual(self.ask("post hike boots")[0], self.ask("post hike  boots")[0])
        self.assertTrue(self.ask("post boots")[0].startswith("This picture is an illustration"))  # the name itself works

    def test_usage_unavailable_and_sentences(self):
        # Contract: a bare or over-long word is the usage; a sentence naming no product stays with the interpreter (HASS-VOICE-1, which
        # the social skills rely on); an unreadable catalog is one fixed line. Bug caught: "post about the porch walk recap" answered
        # here, or a path leaking into the unavailable reply.
        self.photos()
        self.assertEqual(self.ask("post")[0], voice.plain(conversation.POST_USAGE))
        self.assertEqual(self.ask("post " + "a" * 61), (voice.plain(conversation.POST_USAGE), []))
        self.assertTrue(self.ask("post " + "a" * 60)[0].startswith("I don't know a product called"))
        for text in ("post a sale on social media", "post about the porch walk recap", "post green\njam", "post " + "a b " * 16):
            with self.subTest(text=text):
                self.sentence(text)
        self.assertEqual(self.ask("post   BRIAN’S   sourdough bread. ")[0][:20], "This picture is an i")
        (self.cdir / "products.json").write_text("{not json", "utf-8")
        self.assertEqual(self.ask("post green jam"), (UNAVAILABLE, []))

    def test_read_only_all_outcomes(self):
        # Contract: post by name writes nothing but the reply. Bug caught: a lapsed draft swept, a memory table created or a count used.
        draft, _ = self.propose("hours")
        self.calls.clear()  # the proposal is the only allowed interpreter/editor use
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        before = (self.tables(), [dict(r) for r in self.conv.db.execute("SELECT * FROM control")], self.digest(), self.drafts())
        self.now += timedelta(seconds=601)  # the draft has lapsed; no other message has swept it yet
        with mock.patch("socket.socket", side_effect=AssertionError("network")):
            for text in ("post Figs", "post yogurt", "post nonesuch", "post", "post " + "a" * 61):
                self.ask(text)
        self.assertEqual((self.tables(), [dict(r) for r in self.conv.db.execute("SELECT * FROM control")], self.digest(), self.drafts()), before)
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.editor.applies), ("proposed", 0, 0))
        self.say("post Figs", pid="dup1")  # a repeated provider id sends no second reply
        self.say("post Figs", pid="dup1")
        self.assertEqual(len(self.replies()), 1)
        self.say("post Figs", sender="stranger@example.com", pid="s1")  # owner only
        self.assertEqual(self.replies(), [])
        self.assertEqual(draft["code"], self.drafts()[0]["code"])


if __name__ == "__main__":
    unittest.main()
