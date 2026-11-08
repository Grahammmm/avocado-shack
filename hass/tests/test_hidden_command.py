"""AV1222-13 (H03/H17): `hidden` lists hidden products then hidden makers (held products never), up to 20 lines, read-only,
works while paused.
Run: python3 -B -m unittest hass.tests.test_hidden_command -v
"""

import json
import unittest
from datetime import timedelta

from hass import conversation, voice
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

UNAVAILABLE = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"
RESTORE = 'To bring one back, tell me, like Bring back {}.'


class HiddenParseTests(unittest.TestCase):
    def test_whole_message_only(self):
        for text in ("hidden", "Hidden.", "HIDDEN!", "  hidden  "):
            self.assertEqual(conversation.parse_command(text), ("hidden", None), text)
        for text in ("hidden products please", "hidden photo-product-001", "not hidden", "hiddens", "hidden\nx"):
            self.assertIsNone(conversation.parse_command(text), text)

    def test_help_line_and_read_only_verb(self):
        self.assertIn('hidden lists what is hidden', voice.plain(conversation.HELP_TEXT))


class HiddenTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "hidden reached the interpreter/editor"))

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")

    def set_state(self, hidden=(), held=(), makers=(), names=None):
        def prods(doc):
            for p in doc["products"]:
                if p["id"] in hidden: p["status"] = "hidden"
                if p["id"] in held: p["status"] = "held"
                if names and p["id"] in names: p["name"] = names[p["id"]]
        def maks(doc):
            for k in makers: doc["makers"][k]["hidden"] = True
        self.edit("products.json", prods)
        self.edit("makers.json", maks)

    def ids(self):
        with open(self.repo.wt / "hass" / "content" / "products.json", encoding="utf-8") as f:
            return sorted(p["id"] for p in json.load(f)["products"])

    def maker_keys(self):
        with open(self.repo.wt / "hass" / "content" / "makers.json", encoding="utf-8") as f:
            return sorted(json.load(f)["makers"])

    def hidden(self, text="hidden"):
        self.assertEqual(self.say(text), "hidden")
        self.assertEqual(self.disposition(f"m{self.n}"), "hidden")
        [reply] = self.replies()
        return reply.splitlines()

    def names(self):
        with open(self.repo.wt / "hass" / "content" / "products.json", encoding="utf-8") as f:
            return {p["id"]: p["name"] for p in json.load(f)["products"]}

    def test_products_then_makers_held_absent(self):
        a, b, c = self.ids()[:3]
        key = self.maker_keys()[0]
        self.set_state(hidden=(b, a), held=(c,), makers=(key,))
        with open(self.repo.wt / "hass" / "content" / "makers.json", encoding="utf-8") as f:
            maker_name = json.load(f)["makers"][key]["name"]
        names = self.names()
        self.assertEqual(self.hidden(), ["These are hidden right now:", f"- {names[a]}", f"- {names[b]}",
                                         f"- {maker_name} (maker)", RESTORE.format(names[a])])
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_more_than_twenty_products(self):
        ids = self.ids()
        if len(ids) < 23: self.skipTest("fixture has fewer than 23 products")
        self.set_state(hidden=ids[:23])
        lines = self.hidden()
        self.assertEqual(len(lines), 23)
        self.assertTrue(lines[1].startswith(f"- {self.names()[ids[0]]}"))
        self.assertEqual(lines[-2:], ["And a few more.", RESTORE.format(self.names()[ids[0]])])

    def test_makers_fill_after_products_and_share_the_cap(self):
        ids, keys = self.ids(), self.maker_keys()
        self.set_state(hidden=ids[:19], makers=keys[:3])
        lines = self.hidden()
        self.assertEqual(len(lines), 23)
        self.assertEqual(lines[19:21], [f"- {self.names()[ids[18]]}", f"- {keys[0]} (maker)"])
        self.assertEqual(lines[-2:], ["And a few more.", RESTORE.format(self.names()[ids[0]])])

    def test_nothing_hidden(self):
        self.assertEqual(self.hidden(), ["Nothing is hidden right now."])
        self.set_state(held=(self.ids()[0],))  # held alone is not hidden
        self.assertEqual(self.hidden("Hidden."), ["Nothing is hidden right now."])

    def test_paused_and_lapsed_draft_keep_state(self):
        draft, _reply = self.propose("hours")
        self.calls.clear()  # the proposal is the only allowed interpreter/editor use
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.set_state(hidden=(self.ids()[0],))
        control = [dict(r) for r in self.conv.db.execute("SELECT * FROM control")]
        self.now = T0 + timedelta(seconds=601)  # lapsed; no other message has swept it yet
        self.assertEqual(len(self.hidden("HIDDEN")), 3)
        self.assertEqual([dict(r) for r in self.conv.db.execute("SELECT * FROM control")], control)
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.editor.applies), ("proposed", 0, 0))
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_sentence_is_not_the_command(self):
        self.calls.clear()
        self.say("hidden products please")
        self.assertEqual(self.calls, ["interpret"])
        self.calls.clear()

    def test_unreadable_content(self):
        path = self.repo.wt / "hass" / "content" / "products.json"
        good = path.read_text("utf-8")
        path.write_text("{not json", "utf-8")
        self.assertEqual(self.hidden(), [UNAVAILABLE])
        path.write_text(good, "utf-8")

    def test_name_with_markup_or_newline_is_one_stored_line(self):
        pid = self.ids()[0]
        self.set_state(hidden=(pid,), names={pid: "<b>Jam</b>\nsecond   line"})
        self.assertEqual(self.hidden(), ["These are hidden right now:", "- <b>Jam</b> second line", RESTORE.format("<b>Jam</b> second line")])


if __name__ == "__main__":
    unittest.main()
