"""AV1052-05 (H17/SHOP-1): `shelf <name>` lists one shelf's active products in site order, each with the site's availability word.
Read-only (no interpreter, editor, draft or memory table), works while paused; hidden and held products are left out.
Run: python3 -B -m unittest hass.tests.test_shelf_command -v
"""

import json
import unittest
from datetime import date, timedelta

from hass import conversation
from hass.content_model import SHELF_LABELS
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

TODAY = date(2026, 11, 2)  # T0 is Monday 2026-11-02 09:00 PST
UNAVAILABLE = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"  # voice bans the word catalog
CHOOSE = "Choose a shelf: " + ", ".join(SHELF_LABELS.values()) + "."


def product(pid, name, category="eggs", status="active", **extra):
    record = {"id": pid, "name": name, "brand": "Fixture", "category": category, "image": "assets/products/photo-product-001.webp",
              "description": "A fixture product.", "producerKey": None, "displayBrand": "Fixture", "status": status}
    if status == "held":
        record = {k: record[k] for k in ("id", "name", "brand", "category", "image", "status")}
        record["hold"] = {"reason": "Fixture hold", "source": "https://example.com/"}
    return {**record, **extra}


class ShelfParseTests(unittest.TestCase):
    def test_parse_whole_message_only(self):
        self.assertEqual(conversation.parse_command("  Shelf Dairy & Cheese! "), ("shelf", "dairy & cheese"))
        self.assertEqual(conversation.parse_command("shelf"), ("shelf", ""))
        for text in ("shelf chek done. milk in, cheese out", "shelf report then specials", "please shelf eggs", "shelf eggs\nshelf fruit", "shelves", "shelfeggs"):
            self.assertIsNone(conversation.parse_command(text), text)


class ShelfTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "shelf reached the interpreter/editor"))

    def content(self, name):
        return self.repo.wt / "hass" / "content" / name

    def set_products(self, products, checked: date | None = TODAY):
        path = self.content("products.json")
        doc = json.loads(path.read_text("utf-8"))
        doc["products"] = products
        path.write_text(json.dumps(doc), "utf-8")
        store = self.content("store.json")
        doc = json.loads(store.read_text("utf-8"))
        doc["selection_checked_on"] = checked.isoformat() if checked else None
        if not checked: del doc["selection_checked_on"]
        store.write_text(json.dumps(doc), "utf-8")

    def shelf(self, text):
        self.assertEqual(self.say(text), "shelf")
        self.assertEqual(self.disposition(f"m{self.n}"), "shelf")
        [reply] = self.replies()
        return reply.splitlines()

    def test_names_ids_and_unknown_shelves(self):
        for key, label in SHELF_LABELS.items():
            for text in (f"shelf {key}", f"SHELF  {label.upper()}.", f"shelf {label}!"):
                with self.subTest(text=text):
                    self.assertEqual(self.shelf(text)[0], f"Shelf: {label}")
        for text in ("shelf", "shelf dairy and cheese", "shelf Hass avocado", "shelf veg", "shelf <b>x</b>"):
            with self.subTest(text=text):
                self.assertEqual(self.shelf(text), [CHOOSE])  # never echoes what was typed
        self.assertEqual(self.drafts(), [])

    def test_site_order_words_and_hidden_held_left_out(self):
        self.set_products([
            product("a", "Zucchini", available="yes", available_on="2026-11-02"),
            product("b", "Apples", available="limited", available_on="2026-11-02"),
            product("c", "Hidden eggs", status="hidden"),
            product("d", "Held eggs", status="held"),
            product("e", "Zucchini", available="no", available_on="2026-11-02"),
            product("f", "Plain eggs"),
            product("g", "Old news", available="yes", available_on="2026-10-30"),
            product("h", "Other shelf", category="fruit"),
        ])
        self.assertEqual(self.shelf("shelf eggs"), [
            "Shelf: Eggs", "- Zucchini - Available today", "- Apples - Limited", "- Zucchini - Sold out", "- Plain eggs",
            "- Old news - Last confirmed Friday, October 30"])

    def test_new_products_come_first_newest_first(self):
        day = lambda n: (TODAY - timedelta(days=n)).isoformat()
        self.set_products([product("a", "Old"), product("b", "Day 13", addedOn=day(13)), product("c", "Day 14", addedOn=day(14)),
                           product("d", "Today", addedOn=day(0)), product("e", "Day 13 again", addedOn=day(13)),
                           product("f", "Future-free Plain")], checked=None)
        self.assertEqual(self.shelf("shelf eggs")[1:], ["- Today", "- Day 13", "- Day 13 again", "- Old", "- Day 14", "- Future-free Plain"])

    def test_empty_and_cap(self):
        self.set_products([product("a", "Only hidden", status="hidden")])
        self.assertEqual(self.shelf("shelf eggs"), ["Shelf: Eggs", "No products on this shelf."])
        for total, more in ((59, None), (60, None), (61, 1), (62, 2)):
            with self.subTest(total=total):
                self.set_products([product(f"p{i}", f"Egg {i}") for i in range(total)] + [product("h", "Hidden", status="hidden")])
                lines = self.shelf("shelf eggs")
                self.assertEqual(len(lines) - 1, min(total, 60) + (1 if more else 0))
                self.assertEqual(lines[-1], f"... and {more} more" if more else f"- Egg {total - 1}")
                self.assertNotIn("- Hidden", lines)

    def test_works_while_paused_and_changes_nothing(self):
        draft, _reply = self.propose("hours")
        self.calls.clear()  # the proposal used the interpreter; the shelf read must not
        self.set_products([product("a", "Brown eggs")])
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(days=30)  # the waiting draft is long expired, but a read never sweeps it
        before = (self.drafts(), self.tables(), self.approvals(), self.commits())
        self.assertEqual(self.shelf("shelf eggs"), ["Shelf: Eggs", "- Brown eggs"])
        self.assertEqual((self.drafts(), self.tables(), self.approvals(), self.commits()), before)
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.assertEqual(self.say("shelf eggs", pid="dup"), "shelf")
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual(self.say("shelf eggs", pid="dup"), "duplicate")  # a repeated provider id gets no second reply
        self.assertEqual(self.replies(), [])

    def test_unreadable_content_fails_closed(self):
        self.set_products([product("a", "Brown eggs")])
        self.content("products.json").write_text("{not json", "utf-8")
        self.assertEqual(self.shelf("shelf eggs"), [UNAVAILABLE])
        self.content("products.json").unlink()
        self.assertEqual(self.shelf("shelf eggs"), [UNAVAILABLE])


if __name__ == "__main__":
    unittest.main()
