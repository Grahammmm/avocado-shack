"""AV1537-04 (H03): `find <words>` replies up to 10 matching products and makers (id, name, status) from catalog.lookup on
the writer worktree; read-only (no interpreter, editor, draft, expiry or memory table), works while paused.
Run: python3 -B -m unittest hass.tests.test_find -v
"""

import json
import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

DRIED, FRESH = "photo-product-046", "photo-product-150"
UNAVAILABLE = "Catalog unavailable right now; nothing changed."


class FindParseTests(unittest.TestCase):
    def test_query_keeps_case_and_lookalikes_are_not_find(self):
        self.assertEqual(conversation.parse_command("  FIND Lion's Mane!  "), ("find", "Lion's Mane"))
        self.assertEqual(conversation.parse_command("find"), ("find", ""))  # refused with the usage reply
        for text in ("please find lions mane", "finder", "findlions", "find lions\nmane"):
            self.assertIsNone(conversation.parse_command(text), text)


class FindTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "find reached the interpreter/editor"))

    def find(self, text):
        self.assertEqual(self.say(text), "find")
        self.assertEqual(self.disposition(f"m{self.n}"), "find")
        [reply] = self.replies()
        return reply.splitlines()

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")

    def rename(self, word, products=0, makers=0):
        """Prefix `word` to the names of the first N products (by id) and the first M makers (by key)."""
        def prods(doc):
            for p in sorted(doc["products"], key=lambda p: p["id"])[:products]: p["name"] = f"{word} {p['name']}"
        def maks(doc):
            for k in sorted(doc["makers"])[:makers]: doc["makers"][k]["name"] = f"{word} {doc['makers'][k]['name']}"
        self.edit("products.json", prods)
        self.edit("makers.json", maks)

    def test_one_match_and_folded_query(self):
        self.assertEqual(self.find("find DRIED LION'S MANE"), ["Dried lion’s mane mushrooms (on the website)"])
        self.assertEqual(self.find("find LIONS MANE."), ["Dried lion’s mane mushrooms (on the website)",
                                                         "Lion’s mane mushrooms (on the website)"])
        self.assertEqual(self.drafts(), [])

    def test_seven_products_six_makers_gives_ten_lines_and_count(self):
        self.rename("Zzqx", products=7, makers=6)
        lines = self.find("find zzqx")
        self.assertEqual(len(lines), 11)
        self.assertEqual([ln.split()[0] for ln in lines[:10]], ["product"] * 7 + ["maker"] * 3)  # products first
        self.assertEqual(lines[10], "… 3 more; add a word.")
        ids = [ln.split(":")[0].split(" ", 1)[1] for ln in lines[:7]]
        self.assertEqual(ids, sorted(ids))

    def test_lookup_cap_is_never_shown_as_an_exact_count(self):
        self.rename("Qwvx", products=12)  # lookup returns only its first 10
        lines = self.find("find qwvx")
        self.assertEqual((len(lines), lines[-1]), (11, "There are more. Add a word to narrow it down."))
        self.rename("Pzzt", products=12, makers=12)
        lines = self.find("find pzzt")
        self.assertEqual((len(lines), lines[-1]), (11, "There are more. Add a word to narrow it down."))

    def test_no_match_and_usage(self):
        self.assertEqual(self.find("find Zzqx Nothing"), ["I couldn't find anything called Zzqx Nothing."])
        for text in ("find", "Find.", "find    ", "find " + "x" * 61):
            with self.subTest(text=text[:12]):
                self.assertEqual(self.find(text), [conversation.FIND_USAGE])
        self.assertEqual(self.find("find " + "x" * 60), [f"I couldn't find anything called {"x" * 60}."])

    def test_hidden_and_held_records_show_their_status(self):
        def prods(doc):
            for p in doc["products"]:
                if p["id"] == FRESH: p["name"], p["status"] = "Zzhid mushrooms", "hidden"
                if p.get("producerKey") == "Etto": p["status"] = "hidden"
        self.edit("products.json", prods)
        self.edit("makers.json", lambda doc: doc["makers"]["Etto"].update(name="Etto Zzhid", hidden=True))
        self.assertEqual(self.find("find zzhid"), ["Zzhid mushrooms (hidden)",
                                                   "Etto Zzhid (hidden)"])
        self.assertEqual(self.find("find raw milk white cheddar"),
                         ["Raw milk white cheddar (on hold)"])

    def test_broken_or_invalid_content_is_unavailable(self):
        path = self.repo.wt / "hass" / "content" / "products.json"
        good = path.read_text("utf-8")
        path.write_text("{not json", "utf-8")
        self.assertEqual(self.find("find lions mane"), [UNAVAILABLE])
        path.write_text(good, "utf-8")
        self.edit("products.json", lambda doc: doc["products"][0].update(status="bogus"))  # fails validation
        self.assertEqual(self.find("find lions mane"), [UNAVAILABLE])
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_find_while_paused_and_with_a_lapsed_proposal(self):
        draft, _reply = self.propose("hours")
        self.calls.clear()  # that proposal is the only allowed interpreter/editor use
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        control = [dict(r) for r in self.conv.db.execute("SELECT * FROM control")]
        self.now = T0 + timedelta(seconds=601)  # lapsed; no other message has swept it yet
        self.assertEqual(len(self.find("find lions mane")), 2)
        self.assertEqual([dict(r) for r in self.conv.db.execute("SELECT * FROM control")], control)
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.editor.applies), ("proposed", 0, 0))
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_reply_has_only_id_name_status_and_no_memory_table(self):
        lines = self.find("find etto")
        self.assertIn("maker Etto: Etto (visible)", lines)
        text = "\n".join(lines)
        for leak in ("https", "Paso Robles", "Pasta is", "assets/"):
            self.assertNotIn(leak, text)
        self.assertNotIn("memory", self.tables())

    def test_alias_match_is_marked(self):
        self.assertEqual(self.say(f"alias green jam: {DRIED}"), "memory-saved")
        self.replies()
        self.assertEqual(self.find("find Green Jam"),
                         ["Dried lion’s mane mushrooms (on the website, your nickname)"])


if __name__ == "__main__":
    unittest.main()
