"""NB-AV-14 (H15) tests: `alias <name>: <id>` saves an owner alias that catalog.lookup(aliases=...) resolves with a
`via`; `forget alias.<slug>` stops it. Same temp repo / state dir / fixture setup as test_memory_chat (offline).
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import unittest

from hass.content_model import load_content
from hass.ops.catalog import lookup
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

AVO = "photo-product-001"  # Hass avocado
SEND = "Send forget alias.green-jam to remove it."


class MemoryAliasTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "an alias command reached the interpreter/editor"))

    def chat(self, text, disposition, reply=None):
        self.assertEqual(self.say(text), disposition)
        replies = self.replies()
        if reply is not None: self.assertEqual(replies, [reply])
        return replies

    def content(self):
        return load_content(self.repo.wt / "hass" / "content")

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")

    def find(self, query, kind="product"):
        return lookup(self.content(), kind, query, aliases=self.conv.aliases())

    def rows(self, key):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM memory WHERE key = ? ORDER BY id", (key,))]

    def test_save_resolves_lookup_with_via(self):
        self.assertEqual(self.find("Green Jam"), {"candidates": []})
        self.chat(f"Alias green jam: {AVO}", "memory-saved",
                  f"Saved alias green jam → product {AVO} (Hass avocado). {SEND}")
        self.assertEqual(self.conv.aliases(), {"green jam": ("product", AVO)})
        for query in ("Green Jam", "  green   JAM ", "green-jam"):
            self.assertEqual(self.find(query), {"match": AVO, "via": "alias green jam"})
        self.assertNotIn("via", self.find("green"), "only the whole alias matches")
        self.assertNotIn("via", self.find("Hass avocado"), "names without an alias keep the old shape")
        [row] = self.rows("alias.green-jam")
        self.assertEqual((row["value"], row["kind"], row["source"]), (f"product:{AVO}", "fact", "owner-stated:m1"))
        self.assertIn(f"green jam -> Hass avocado ({AVO})", self.chat("memory", "memory-list")[0])

    def test_maker_alias_and_kind_mismatch(self):
        self.chat("alias the dairy: Straus", "memory-saved",
                  "Saved alias the dairy → maker Straus (Straus). Send forget alias.the-dairy to remove it.")
        self.assertEqual(self.find("The Dairy", "maker"), {"match": "Straus", "via": "alias the dairy"})
        self.assertEqual(self.find("the dairy", "product"), {"candidates": []}, "a maker alias is not a product alias")

    def test_unknown_hidden_held_and_ambiguous_ids(self):
        self.chat("alias green jam: photo-product-999", "memory-invalid",
                  "Not saved: no product or maker photo-product-999.")
        self.chat("alias green jam: PHOTO-PRODUCT-001", "memory-invalid",
                  "Not saved: no product or maker PHOTO-PRODUCT-001.")
        self.chat("alias green jam:", "memory-invalid", "Not saved: send alias <name>: <product id or maker key>.")
        self.chat("alias green jam", "memory-invalid", "Not saved: send alias <name>: <product id or maker key>.")
        self.chat("alias cheese: photo-product-040", "memory-saved", "Saved alias cheese → product photo-product-040 "
                  "(Raw milk white cheddar, held). Send forget alias.cheese to remove it.")
        self.edit("products.json", lambda d: next(p for p in d["products"] if p["id"] == AVO).update(status="hidden"))
        self.chat(f"alias green jam: {AVO}", "memory-saved",
                  f"Saved alias green jam → product {AVO} (Hass avocado, hidden). {SEND}")
        self.chat("forget alias.green-jam", "memory-forgot")
        self.edit("makers.json", lambda d: d["makers"].update({AVO: dict(d["makers"]["Straus"])}))
        self.chat(f"alias green jam: {AVO}", "memory-invalid", f"Not saved: {AVO} is both a product and a maker.")
        self.assertIsNone(self.conv.memory.get("alias.green-jam"))

    def test_catalog_unavailable_is_not_saved(self):
        (self.repo.wt / "hass" / "content" / "makers.json").write_text("{", "utf-8")
        self.chat(f"alias green jam: {AVO}", "memory-invalid", "Not saved: the catalog is unavailable.")
        self.assertEqual(self.rows("alias.green-jam"), [])

    def test_update_keeps_one_active_row(self):
        self.chat(f"alias green jam: {AVO}", "memory-saved")
        self.chat("alias Green Jam: photo-product-016", "memory-updated", f"Updated alias Green Jam (was: product:{AVO})"
                  f" → product photo-product-016 (Oranges). {SEND}")
        self.assertEqual(self.find("green jam"), {"match": "photo-product-016", "via": "alias green jam"})
        rows = self.rows("alias.green-jam")
        self.assertEqual([r["superseded_at"] is None and r["forgotten_at"] is None for r in rows], [False, True])
        self.chat("alias green jam: photo-product-999", "memory-invalid")  # a bad update leaves the alias alone
        self.assertEqual(self.find("green jam"), {"match": "photo-product-016", "via": "alias green jam"})

    def test_forget_stops_alias_and_name_matching_returns(self):
        self.chat(f"alias oranges: {AVO}", "memory-saved")
        self.assertEqual(self.find("Oranges"), {"match": AVO, "via": "alias oranges"})
        self.chat("forget alias.oranges", "memory-forgot", "Forgot alias.oranges.")
        self.assertEqual(self.conv.aliases(), {})
        self.assertEqual(self.find("Oranges"), {"match": "photo-product-016"})
        self.chat("forget alias.oranges", "memory-none", "Nothing saved as alias.oranges.")

    def test_dangling_alias_falls_back_to_names(self):
        self.chat("alias melon: photo-product-078", "memory-saved")
        self.chat("alias jam maker: Straus", "memory-saved")
        self.edit("products.json", lambda d: d.update(products=[p for p in d["products"] if p["id"] != "photo-product-078"]))
        self.edit("makers.json", lambda d: d["makers"].pop("Straus"))
        self.assertEqual(self.find("melon"), {"match": "photo-product-080"})  # Honeydew-type melon, by name
        self.assertEqual(self.find("jam maker", "maker"), {"candidates": []})
        self.assertEqual(lookup(self.content(), "product", "melon",
                                aliases={"melon": ("product", None)}), {"match": "photo-product-080"})

    def test_bad_names_and_remember_bypass_store_nothing(self):
        bad = "Not saved: alias name must be 1–60 plain letters, digits, spaces, . or -."
        for text in ("alias <b>jam</b>: " + AVO, "alias $jam: " + AVO, "alias ja\x07m: " + AVO, "alias two\nlines: " + AVO,
                     "alias " + "j" * 61 + ": " + AVO, "alias : " + AVO, "alias '': " + AVO, "alias -jam: " + AVO,
                     "alias jam/2: " + AVO, "ALIAS"):
            with self.subTest(text=text):
                self.chat(text, "memory-invalid", bad)
        self.chat("remember alias.green-jam: product:photo-product-999", "memory-invalid",
                  "Not saved: send alias <name>: <id> to save an alias.")
        self.chat(f"alias jam: {AVO} please", "memory-invalid", f"Not saved: no product or maker {AVO} please.")
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 0)
        self.assertEqual(self.conv.aliases(), {})
        self.chat("alias Lion’s Måne: " + AVO, "memory-saved")  # lookup's fold: accents and curly apostrophes
        self.assertEqual(self.find("lions mane"), {"match": AVO, "via": "alias lions mane"})

    def test_forget_alias_by_spaced_name(self):
        """AV1352-07: `forget alias green jam` removes alias.green-jam, even dangling; a plain note is untouched."""
        self.chat(f"alias Green Jam: {AVO}", "memory-saved")
        self.chat("remember green jam: a note", "memory-saved")
        self.chat("forget ALIAS  green jam", "memory-forgot", "Forgot alias.green-jam.")
        self.assertEqual(self.conv.aliases(), {})
        self.chat("forget alias green jam", "memory-none", "Nothing saved as alias.green-jam.")
        self.chat(f"alias green jam: {AVO}", "memory-saved")
        self.chat("forget alias.green-jam", "memory-forgot", "Forgot alias.green-jam.")
        self.chat("alias melon: photo-product-078", "memory-saved")
        self.edit("products.json", lambda d: d.update(products=[p for p in d["products"] if p["id"] != "photo-product-078"]))
        self.chat("forget alias melon", "memory-forgot", "Forgot alias.melon.")
        self.chat("forget alias $jam", "memory-none")
        self.chat("forget alias " + "j" * 61, "memory-none")
        self.chat("remember alias.green jam: product:" + AVO, "memory-invalid",
                  "Not saved: send alias <name>: <id> to save an alias.")
        self.chat("forget green jam", "memory-forgot", "Forgot green-jam.")

    def test_forget_alias_name_collision_with_note(self):
        """AV1352-07 review: note alias-green-jam and alias.green-jam both saved: forget alias green jam deletes neither."""
        self.chat(f"alias green jam: {AVO}", "memory-saved")
        self.chat("remember alias green jam: note", "memory-saved")
        self.chat("forget alias green jam", "memory-ambiguous",
                  "Both alias.green-jam (an alias) and alias-green-jam (a note) are saved; nothing was forgotten. "
                  "Send forget alias.green-jam for the alias or forget alias-green-jam for the note.")
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 2)
        self.chat("forget alias-green-jam", "memory-forgot", "Forgot alias-green-jam.")
        self.assertEqual(len(self.conv.aliases()), 1)
        self.chat("remember alias green jam: note", "memory-saved")
        self.chat("forget alias.green-jam", "memory-forgot", "Forgot alias.green-jam.")
        self.chat("forget alias green jam", "memory-forgot", "Forgot alias-green-jam.")  # only the note exists: it goes
        self.assertEqual(self.conv.memory.list(), [])

    def test_plain_notes_are_not_aliases(self):
        self.chat("remember aliases: product:" + AVO, "memory-saved")
        self.assertEqual(self.conv.aliases(), {})


if __name__ == "__main__":
    unittest.main()
