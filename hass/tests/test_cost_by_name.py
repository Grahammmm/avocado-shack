"""AV2137-05 (F03/H17): `cost <name or alias>: <pack> for <units>` and `margin <name or alias> at <M>%` act as the product's id when
exactly one product of ANY status fits; several reply the find lines (up to 10, with ids); none says to use find. A numeric pack
form is never read as a name. Replies name the product by name and id. Synthetic fixtures only (the conversation test store).
Run: python3 -B -m unittest hass.tests.test_cost_by_name -v
"""

import json
import unittest
from datetime import timedelta

from hass import conversation, margins, voice
from hass.tests.test_post_by_name import MORE, NameFixture

FIGS, SOURDOUGH, GOAT = "photo-product-097", "photo-product-015", "photo-product-133"  # Figs; Brian's sourdough bread; held "Raw Milk Goat Cheddar"
PRIVATE = "That stays private and is never on the website."
UNKNOWN = "I don't know a product called {}. Try find and a word from its name."


class CostByNameFixture(NameFixture):
    def go(self, text, disposition, **kw):
        self.assertEqual(self.say(text, **kw), disposition, text)
        [reply] = self.replies()
        return reply

    def cost(self, pid):
        row = self.conv.db.execute("SELECT value FROM memory WHERE key = ? AND superseded_at IS NULL", (f"cost.{pid}",)).fetchone() if "memory" in self.tables() else None
        return row and row[0]

    def products(self):
        return json.loads((self.cdir / "products.json").read_text("utf-8"))["products"]

    def any_status_ids(self, word):  # the plain rule written out independently: every status counts for a private cost
        return sorted(p["id"] for p in self.products() if any(word in p.get(f, "").lower() for f in ("name", "brand", "displayBrand")))

    def lines(self, ids):
        names = {p["id"]: (p["name"], p["status"]) for p in self.products()}
        return [f"product {i}: {names[i][0]} ({names[i][1]})" for i in ids]


class NameAndAliasTests(CostByNameFixture):
    def test_name_and_alias_equal_id_all_statuses(self):
        # Contract: a unique name or alias acts as that id for cost (save, update, unchanged) and for the saved-cost margin, whatever
        # the product's status, and the reply names it by name and id. Bug caught: a name that saves under the wrong key, a reply
        # without the id, or a hidden/held product refused when named.
        who = f"Figs ({FIGS})"
        self.assertEqual(self.go("cost FIGS: $24 for 12", "memory-saved"),
                         f"Saved. {who} costs you 24.00 for 12. {PRIVATE} Say forget cost.{FIGS} to remove it.")
        self.assertEqual(self.go("cost figs: 24.00 for 12.0", "memory-unchanged"), f"I already have that cost for {who}, so nothing changed.")
        self.assertEqual(self.go("cost Figs: 30 for 12", "memory-updated"),
                         f"Updated. {who} now costs you 30.00 for 12. {PRIVATE} Say forget cost.{FIGS} to remove it.")
        self.assertEqual(self.cost(FIGS), "30.00 for 12")
        want = margins.say(margins.compute("30", "12", "0", "35"))
        self.assertEqual(self.go("margin figs at 35%", "margin"), f"For {who}, using the cost you gave me today at 9 am.\n" + want)
        self.assertEqual(self.go(f"margin {FIGS} at 35%", "margin"), self.go("margin Figs at 35%", "margin"))  # name and id: the same answer
        self.assertEqual(self.go("margin Figs price 3.49 shrink 5%", "margin").splitlines()[0], f"For {who}, using the cost you gave me today at 9 am.")
        self.assertEqual(self.go("alias fig tree: " + FIGS, "memory-saved"), "Saved. fig tree now means Figs. Say forget alias fig tree to remove it.")
        self.assertEqual(self.go("cost Fig-Tree: 12 for 6", "memory-updated"),  # a saved nickname is a name too
                         f"Updated. {who} now costs you 12.00 for 6. {PRIVATE} Say forget cost.{FIGS} to remove it.")
        self.assertTrue(self.go("margin fig tree at 35%", "margin").startswith(f"For {who}, using"))
        self.assertEqual(self.go("alias etto: Etto", "memory-saved"), "Saved. etto now means Etto. Say forget alias etto to remove it.")
        self.assertEqual(self.go("cost etto: 1 for 1", "memory-ambiguous").splitlines()[0][:16], "product photo-pr")  # a maker nickname selects no product
        self.set_status(FIGS, "hidden")  # any status: hidden and held products keep a private cost
        self.assertEqual(self.go("cost figs: 31 for 12", "memory-updated").split(" costs")[0].split(" now")[0], f"Updated. {who}")
        self.assertEqual(self.go("cost raw milk goat cheddar: 8 for 4", "memory-saved"),
                         f"Saved. Raw Milk Goat Cheddar ({GOAT}) costs you 8.00 for 4. {PRIVATE} Say forget cost.{GOAT} to remove it.")
        self.assertTrue(self.go("margin raw milk goat cheddar at 35%", "margin").startswith(f"For Raw Milk Goat Cheddar ({GOAT}), using"))

    def test_many_lists_ids_and_never_changes_cost(self):
        # Contract: several matches list up to 10 find lines with ids and change/calculate nothing. Bug caught: a guessed first
        # match saved or used, or the 10-line cap dropped.
        self.assertEqual(self.go(f"cost {SOURDOUGH}: 24 for 12", "memory-saved").split(" costs")[0], f"Saved. Brian's sourdough bread ({SOURDOUGH})")
        before = self.digest(), self.conv.db.execute("SELECT * FROM memory").fetchall()
        sour = self.any_status_ids("sourdough")
        self.assertEqual(len(sour), 3)
        for text, disposition in (("cost sourdough: 99 for 1", "memory-ambiguous"), ("margin SOURDOUGH at 35%", "margin"),
                                  ("margin sourdough price 3.49", "margin")):
            self.assertEqual(self.go(text, disposition), "\n".join(self.lines(sour)), text)
        self.assertEqual(self.go("cost cheddar: 5 for 1", "memory-ambiguous"), "\n".join(self.lines(self.any_status_ids("cheddar"))))
        self.assertIn("held", self.go("cost cheddar: 5 for 1", "memory-ambiguous"))  # a held product is listed too, with its status
        cap = self.any_status_ids("cal poly")  # a brand match: more than the 10 the lookup returns
        self.assertGreater(len(cap), 10)
        for text, disposition in (("cost cal poly: 5 for 1", "memory-ambiguous"), ("margin cal poly at 20%", "margin")):
            self.assertEqual(self.go(text, disposition), "\n".join(self.lines(cap[:10]) + [MORE]), text)
        self.assertEqual((self.digest(), self.conv.db.execute("SELECT * FROM memory").fetchall()), before)
        self.assertEqual(self.cost(SOURDOUGH), "24.00 for 12")

    def test_none_vs_known_without_cost(self):
        # Contract: an unknown name says to use find; a known product without a cost says so by name and id. Bug caught: the two
        # answers swapped, or an unknown name reported as a missing cost.
        self.assertEqual(self.go("margin nonesuch at 35%", "margin"), UNKNOWN.format("nonesuch"))
        self.assertEqual(self.go("margin nonesuch price 3.49", "margin"), UNKNOWN.format("nonesuch"))
        self.assertEqual(self.go("cost nonesuch: 24 for 12", "memory-invalid"), UNKNOWN.format("nonesuch"))
        self.assertEqual(self.go("margin Figs at 35%", "margin"),
                         f"I don't have a cost saved for Figs ({FIGS}). Tell me first, like cost {FIGS}: 24 for 12.")
        self.assertNotIn("memory", self.tables(), "a margin read created the memory table")
        self.assertEqual(self.go("margin photo-product-999 at 35%", "margin"), UNKNOWN.format("photo-product-999"))
        self.assertIsNone(self.cost(FIGS))


class NumericFormTests(CostByNameFixture):
    def test_numeric_forms_win_without_catalog(self):
        # Contract: a pack form is the numbers even when it is invalid or a product is named like it, and never reads the catalog.
        # Bug caught: "24 for twelve" looked up as a name, or a product called "24 for 12" hijacking the arithmetic.
        self.edit(lambda doc: doc["products"][0].update(name="24 for 12"))
        self.edit(lambda doc: doc["products"][1].update(name="24 for twelve"))
        want = margins.say(margins.compute("24", "12", "0", "35"))
        self.assertEqual(self.go("margin 24 for 12 at 35%", "margin"), want)
        self.assertEqual(self.go("margin $24 for 12 at 35% shrink 5% ending .99", "margin"), margins.say(margins.compute("24", "12", "5", "35", ".99")))
        self.assertTrue(self.go("margin 24 for 0 at 35%", "margin").startswith("I couldn't work that out. Please check how many are in a pack"))
        self.assertTrue(self.go("margin 24 for 12 at 95%", "margin").startswith("I couldn't work that out. Please check the margin"))
        self.assertTrue(self.go("margin 24 for 12 price 3.49", "margin").startswith("Each one costs you: 24.00 / 12 = 2.00"))
        for text in ("margin 24 for twelve at 35%", "margin 24 for twelve price 3.49", "margin 24 for 12 at 35"):
            self.assertEqual(self.go(text, "margin"), voice.plain(conversation.MARGIN_USAGE), text)
        self.assertEqual(self.go("cost 24 for 12: 24 for 12", "memory-invalid"), voice.plain(conversation.COST_USAGE))  # a pack form is never a name
        self.assertNotIn("memory", self.tables())
        (self.cdir / "products.json").write_text("{not json", "utf-8")  # the numeric forms never open the catalog
        self.assertEqual(self.go("margin 24 for 12 at 35%", "margin"), want)
        self.assertEqual(self.go("margin 24 for twelve at 35%", "margin"), voice.plain(conversation.MARGIN_USAGE))


class UnavailableAndGateTests(CostByNameFixture):
    def test_unavailable_catalog_not_false_missing(self):
        # Contract: an unreadable catalog is the one "can't look that up" line, never "unknown product" or "no cost saved".
        # Bug caught: a read failure reported as a missing cost, or a cost saved under an unresolved name.
        self.assertEqual(self.go("cost Figs: 24 for 12", "memory-saved").split(" costs")[0], f"Saved. Figs ({FIGS})")
        (self.cdir / "products.json").write_text("{not json", "utf-8")
        unavailable = voice.plain(conversation.CANT_READ)
        self.assertEqual(self.go("cost Figs: 30 for 12", "memory-invalid"), unavailable)
        self.assertEqual(self.go("margin Figs at 35%", "margin"), unavailable)
        self.assertEqual(self.go("margin Figs price 3.49", "margin"), unavailable)
        self.assertEqual(self.cost(FIGS), "24.00 for 12")

    def test_paused_cap_replay_owner_and_privacy(self):
        # Contract: by-name cost and margin are private bookkeeping that works while paused, answers a repeated message once, ignores
        # other senders and leaves drafts alone. Bug caught: a margin that swept a lapsed draft, created memory or reached the
        # interpreter (the fixture's cleanup fails on any interpreter or editor call).
        draft, _ = self.propose("hours")
        self.calls.clear()  # the proposal is the only allowed interpreter/editor use
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.assertEqual(self.go("margin Figs at 35%", "margin"), f"I don't have a cost saved for Figs ({FIGS}). Tell me first, like cost {FIGS}: 24 for 12.")
        self.assertNotIn("cost.", json.dumps(self.drafts(), default=str))
        self.now += timedelta(seconds=601)  # the draft has lapsed; a margin read has not swept it
        self.go("margin sourdough at 35%", "margin")
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.assertEqual(self.go("cost Figs: 73.19 for 7", "memory-saved").split(" costs")[0], f"Saved. Figs ({FIGS})")  # saves while paused
        self.say("margin Figs at 35%", pid="dup1")
        self.say("margin Figs at 35%", pid="dup1")
        self.assertEqual(len(self.replies()), 1)
        for text in ("cost Figs: 1 for 1", "margin Figs at 35%"):
            self.say(text, sender="stranger@example.com", pid="s1")
            self.assertEqual(self.replies(), [])
        self.assertEqual((self.cost(FIGS), self.approvals(), self.editor.applies, draft["code"]), ("73.19 for 7", 0, 0, self.drafts()[0]["code"]))
        self.assertNotIn("73.19", json.dumps(self.drafts(), default=str))


if __name__ == "__main__":
    unittest.main()
