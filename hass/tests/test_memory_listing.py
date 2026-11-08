"""AV0222-05 (H15): `memory` lists saved notes and aliases apart, each with its own cap.

Same temp repo / state dir / fixture setup as test_memory_alias (offline, synthetic).
Run: python3 -B -m unittest hass.tests.test_memory_listing -v
"""

import json
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, memory as memory_mod, voice
from hass.tests.test_conversation import GROUP, STRANGER, T0, ConversationTestCase
from hass.tests.test_editor import HOURS, _req
from hass.tests.test_status_pause import StoreMixin

AVO = "photo-product-001"  # Hass avocado
NOTE = "- {}: v{} (since today at 9 am)"


class MemoryListingTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **kw: (self.calls.append(_n), _r(*a, **kw))[1])

    def listing(self, pid=None):
        self.assertEqual(self.say("memory", pid=pid), "memory-list")
        [reply] = self.replies()
        return reply

    def save(self, key, value):
        if self.conv.memory is None: self.conv.memory = memory_mod.Memory.on_connection(self.conv.db, self.conv.clock)
        self.conv.memory.remember(key, value, "fact", "owner-stated:test")

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")

    def snapshot(self):
        names = [r[0] for r in self.conv.db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        return {n: [tuple(r) for r in self.conv.db.execute(f'SELECT * FROM "{n}"')] for n in names if n not in ("messages", "outbox")}

    def test_notes_and_aliases_have_independent_caps(self):
        for i in range(23): self.save(f"k{i:02d}", f"v{i}")
        for i in range(23): self.save(f"alias.jam-{i:02d}", f"product:{AVO}")
        lines = self.listing().splitlines()
        self.assertEqual(len(lines), 1 + 20 + 1 + 1 + 20 + 1)
        self.assertEqual((lines[0], lines[1], lines[20], lines[21]), ("Notes I'm keeping:", NOTE.format("k00", 0), NOTE.format("k19", 19), "And a few more."))
        self.assertEqual((lines[22], lines[23], lines[42], lines[43]),
                         ("Nicknames:", "- jam 00 means Hass avocado", "- jam 19 means Hass avocado", "And a few more."))

    def test_alias_boundary_counts_and_single_sections(self):
        self.assertEqual(self.listing(), "I'm not keeping any notes.\nI don't have any nicknames.")
        self.save("alias.a", f"product:{AVO}")
        self.assertEqual(self.listing(), "I'm not keeping any notes.\nNicknames:\n- a means Hass avocado")
        for i in range(19): self.save(f"alias.b{i:02d}", f"product:{AVO}")
        self.assertEqual(len(self.listing().splitlines()), 22)  # exactly 20: no "more" line
        self.assertNotIn("more", self.listing())
        self.save("alias.c", f"product:{AVO}")
        self.assertTrue(self.listing().endswith("Nicknames:\n" + "\n".join(
            [f"- {n} means Hass avocado" for n in ["a"] + [f"b{i:02d}" for i in range(19)]]) + "\nAnd a few more."))
        self.save("note", f"product:{AVO}")  # a note whose text starts with product: is still a note
        self.assertTrue(self.listing().startswith(f"Notes I'm keeping:\n- note: product:{AVO} (since"))
        self.say("forget alias.a")
        self.replies()
        self.assertIn("Nicknames:", self.listing())

    def test_product_maker_and_status_targets(self):
        self.save("alias.dairy", "maker:Straus")
        self.save("alias.same", f"product:{AVO}")
        self.save("alias.same-maker", f"maker:{AVO}")  # maker key that is also a product id: resolved by kind
        self.edit("makers.json", lambda d: d["makers"].update({AVO: {**d["makers"]["Straus"], "name": "Same Id Farm"}}))
        out = self.listing()
        self.assertIn("- dairy means Straus", out)
        self.assertIn("- same means Hass avocado", out)
        self.assertIn("- same maker means Same Id Farm", out)
        self.edit("products.json", lambda d: [p.update(name="Renamed avocado", status="hidden") for p in d["products"] if p["id"] == AVO])
        self.edit("makers.json", lambda d: d["makers"]["Straus"].update(hidden=True))
        before = self.snapshot()
        out = self.listing()
        self.assertIn("- same means Renamed avocado (hidden)", out)
        self.assertIn("- dairy means Straus (hidden)", out)
        self.assertEqual(self.snapshot(), before)  # a rename changes the display, never the stored alias
        self.edit("products.json", lambda d: [p.update(status="held", hold="private reason") for p in d["products"] if p["id"] == AVO])
        out = self.listing()
        self.assertIn("- same means Renamed avocado (on hold)", out)
        self.assertNotIn("private reason", out)

    def test_dangling_and_legacy_bad_aliases(self):
        for key, value in (("alias.gone", "product:photo-product-078"), ("alias.gone-maker", "maker:Straus"),
                           ("alias.kind", "thing:x"), ("alias.nocolon", "photo-product-001"), ("alias.empty", "product:"),
                           ("alias.long", "product:" + "x" * 90), ("alias.forgotten", f"product:{AVO}"), ("alias.ok", f"product:{AVO}")):
            self.save(key, value)
        self.conv.memory.forget("alias.forgotten")
        self.edit("products.json", lambda d: d.update(products=[p for p in d["products"] if p["id"] != "photo-product-078"]))
        self.edit("makers.json", lambda d: d["makers"].pop("Straus"))
        out = self.listing()
        self.assertIn("Nicknames:", out)
        self.assertEqual(len(out.splitlines()), 2 + 7)  # seven active nicknames, apart from the note/header lines
        self.assertIn("- gone: it points to something that is no longer on the website. Say forget alias gone to remove it.", out)
        self.assertIn("- gone maker: it points to something that is no longer on the website. Say forget alias gone maker to remove it.", out)
        for slug in ("kind", "nocolon", "empty", "long"):
            self.assertIn(f"- {slug}: I can't read this one. Say forget alias {slug} to remove it.", out)
        self.assertNotIn("thing:x", out)
        self.assertNotIn("xxxxxxxx", out)
        self.assertNotIn("forgotten", out)
        self.assertIn("- ok means Hass avocado", out)
        self.assertEqual(self.conv.aliases().get("gone"), ("product", "photo-product-078"))  # find still ignores via lookup

    def test_catalog_failure_not_false_deletion(self):
        self.listing()  # no aliases: the catalog is never read
        with mock.patch.object(conversation, "load_content", side_effect=AssertionError("catalog read")):
            self.assertEqual(self.listing(), "I'm not keeping any notes.\nI don't have any nicknames.")
        self.save("note", "kept")
        self.save("alias.jam", f"product:{AVO}")
        self.save("alias.bad", "nonsense")
        (self.repo.wt / "hass" / "content" / "products.json").write_text("{not json", "utf-8")
        out = self.listing()
        self.assertIn("Notes I'm keeping:\n- note: kept", out)
        self.assertIn("- jam: I can't look up what it means right now.", out)
        self.assertIn("- bad: I can't read this one. Say forget alias bad to remove it.", out)
        self.assertNotIn("no longer", out)
        self.assertNotIn(str(self.repo.wt), out)
        self.edit("makers.json", lambda d: d["makers"]["Straus"].update(name="bad\nname"))
        self.save("alias.dairy", "maker:Straus")
        (self.repo.wt / "hass" / "content" / "products.json").write_text(json.dumps({"products": [
            {"id": AVO, "name": "ok", "status": "active"}]}), "utf-8")
        with mock.patch.object(conversation, "load_content", side_effect=conversation.editor_mod.UnsafeState("x")):
            self.assertIn("- jam: I can't look up what it means right now.", self.listing())

    def test_listing_is_read_only_and_does_not_expire(self):
        self.interp.mapping["half"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}
        self.assertEqual(self.say("half"), "needs-details")
        self.replies()
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(seconds=601)  # lapsed
        self.calls.clear()
        before, states = self.snapshot(), [d["state"] for d in self.drafts()]
        self.assertEqual(states, ["needs-details"])
        self.assertEqual(self.listing(), "I'm not keeping any notes.\nI don't have any nicknames.")
        self.assertEqual([d["state"] for d in self.drafts()], states)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.calls, [])
        self.say("forget nothing")  # a write still sweeps as before
        self.replies()
        self.assertEqual([d["state"] for d in self.drafts()], ["expired"])

    def test_missing_memory_table_is_not_created_by_listing(self):
        self.assertFalse(self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory'").fetchone())
        self.assertEqual(self.listing(), "I'm not keeping any notes.\nI don't have any nicknames.")
        self.assertFalse(self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory'").fetchone())

    def test_owner_duplicate_caption_and_punctuation(self):
        self.save("alias.jam", f"product:{AVO}")
        self.assertEqual(self.say("memory", sender=STRANGER), "ignored")
        self.assertEqual(self.say("memory", chat=GROUP), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.say("memory", pid="dup"), "memory-list")
        self.assertEqual(self.say("memory", pid="dup"), "duplicate")
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual(self.say("MEMORY!"), "memory-list")
        self.assertIn("Nicknames:", self.replies()[0])
        self.assertNotEqual(self.say("memory of the hike"), "memory-list")
        self.replies()

    def test_alias_cap_doc_and_help_are_tied(self):
        self.assertEqual(conversation.ALIAS_LIST_MAX, 20)
        self.assertEqual(sum(1 for line in conversation.HELP_TEXT.splitlines() if "notes lists them" in voice.plain(line)), 1)
        self.assertIn('notes lists them', voice.plain(conversation.HELP_TEXT))


if __name__ == "__main__":
    unittest.main()
