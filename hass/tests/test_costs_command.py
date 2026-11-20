"""AV2137-06 (F03/H15): `costs` lists the saved purchase costs, newest first, apart from the notes `memory` lists.

Each test names the contract it protects and the believable bug that fails it. Same temp repo / state dir / fixture setup as
test_memory_listing (offline, synthetic products and costs). Run: python3 -B -m unittest hass.tests.test_costs_command -v
"""

import json
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, margins, memory as memory_mod, voice
from hass.chat import commands, core_pack
from hass.tests.test_conversation import GROUP, SETTINGS, STRANGER, T0, ConversationTestCase
from hass.tests.test_editor import HOURS, _req
from hass.tests.test_status_pause import StoreMixin

AVO, JAM, CHEESE = "photo-product-001", "photo-product-002", "photo-product-040"  # Hass avocado, Linn's triple berry preserves, hidden cheddar
ROW = "INSERT INTO memory(key, value, kind, source, created_at) VALUES (?, ?, 'fact', 'owner-stated:raw', ?)"


class CostsTestCase(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **kw: (self.calls.append(_n), _r(*a, **kw))[1])

    def costs(self, text="costs", pid=None):
        self.assertEqual(self.say(text, pid=pid), "costs")
        [reply] = self.replies()
        return reply

    def memory_list(self):
        self.assertEqual(self.say("memory"), "memory-list")
        [reply] = self.replies()
        return reply

    def raw(self, key, value, created="2026-11-03T20:00:00+00:00"):
        """A stored row exactly as given (a legacy or hand-made one the handler would never write)."""
        if self.conv.memory is None: self.conv.memory = memory_mod.Memory.on_connection(self.conv.db, self.conv.clock)
        self.conv.db.execute(ROW, (key, value, created))

    def save(self, text, pid=None):
        self.assertEqual(self.say(text, pid=pid), "memory-saved")
        self.replies()

    def edit_products(self, change):
        path = self.repo.wt / "hass" / "content" / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        change(doc["products"])
        path.write_text(json.dumps(doc), "utf-8")

    def snapshot(self):
        names = [r[0] for r in self.conv.db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        return {n: [tuple(r) for r in self.conv.db.execute(f'SELECT * FROM "{n}"')] for n in names if n not in ("messages", "message_chats", "outbox")}


class ListingTests(CostsTestCase):
    def test_zero_and_missing_table_make_no_table_and_read_no_catalog(self):
        # Bug caught: answering an empty `costs` by building the memory table or loading the site content.
        with mock.patch.object(conversation, "load_content", side_effect=AssertionError("catalog read")):
            self.assertEqual(self.costs(), "No purchase costs saved.")
            self.assertNotIn("memory", self.tables())
            self.save("remember tone: short")  # the table exists now, with a note but no cost
            self.assertEqual(self.costs(), "No purchase costs saved.")

    def test_lines_are_newest_first_and_each_is_the_calculators_figure(self):
        # Bug caught: the each figure divided or rounded in the list (10 for 3 must keep its repeating decimals) or the list in key order.
        self.save(f"cost {AVO}: 24 for 12")
        self.now = T0 + timedelta(days=1)
        self.save(f"cost {JAM}: 10 for 3")
        self.assertEqual(self.costs(), f"Linn's triple berry preserves ({JAM}): $10.00 for 3 = $3.333333... each, saved Tue Nov 3\n"
                                       f"Hass avocado ({AVO}): $24.00 for 12 = $2.00 each, saved Mon Nov 2")
        with mock.patch.object(margins, "compute", return_value={"inputs": {"pack_cost": "1.00", "units": "2"}, "unit_cost": "7.77"}) as calc:
            self.assertIn(f"Hass avocado ({AVO}): $1.00 for 2 = $7.77 each, saved", self.costs().splitlines()[1])  # shown, not recomputed
        self.assertEqual(calc.call_args.args, ("24.00", "12", "0", "0"))

    def test_newest_instant_ties_corrections_and_forgotten_rows(self):
        # Bug caught: sorting the stored text (offsets differ), a correction keeping its old date, a forgotten cost still listed.
        self.raw("cost.aaa-late-text", "5.00 for 1", "2026-11-03T05:00:00-08:00")  # 13:00Z: newer than the next, though the text sorts lower
        self.raw("cost.bbb-tie-b", "5.00 for 1", "2026-11-03T10:00:00+00:00")
        self.raw("cost.aaa-tie-a", "5.00 for 1", "2026-11-03T02:00:00-08:00")  # the same instant as the line above
        order = [line.split(" (")[0] for line in self.costs().splitlines()]
        self.assertEqual(order, ["Product no longer listed"] * 3)
        ids = [line.split("(")[1].split(")")[0] for line in self.costs().splitlines()]
        self.assertEqual(ids, ["aaa-late-text", "aaa-tie-a", "bbb-tie-b"])
        self.save(f"cost {AVO}: 24 for 12")
        self.now = T0 + timedelta(days=3)  # Thu Nov 5
        self.assertEqual(self.say(f"cost {AVO}: 30 for 12"), "memory-updated")
        self.replies()
        lines = self.costs().splitlines()
        self.assertEqual(lines[0], f"Hass avocado ({AVO}): $30.00 for 12 = $2.50 each, saved Thu Nov 5")  # the correction's day; one row
        self.assertEqual(len(lines), 4)
        self.assertEqual(self.say(f"forget cost.{AVO}"), "memory-forgot")
        self.replies()
        self.assertNotIn(AVO, self.costs())

    def test_saved_day_is_pacific_across_midnight_and_the_clock_change(self):
        # Bug caught: the day taken from the UTC date, or from the server's own zone.
        for key, created in (("a", "2026-11-03T07:59:00+00:00"), ("b", "2026-11-03T08:00:00+00:00"),
                             ("c", "2026-11-01T07:30:00+00:00"), ("d", "2026-11-01T08:30:00+00:00"), ("e", "2026-11-01T10:30:00Z")):
            self.raw(f"cost.{key}", "5 for 1", created)
        days = {line.split("(")[1].split(")")[0]: line.rsplit("saved ", 1)[1] for line in self.costs().splitlines()}
        self.assertEqual(days, {"a": "Mon Nov 2", "b": "Tue Nov 3", "c": "Sun Nov 1", "d": "Sun Nov 1", "e": "Sun Nov 1"})

    def test_twenty_and_twenty_one_and_independent_notes(self):
        # Bug caught: costs sharing the notes' 20 lines (the original defect) or a wrong omitted count.
        self.assertEqual(conversation.COSTS_LIST_MAX, 20)
        self.save("remember zz-owner-note: keep")
        for i in range(20): self.raw(f"cost.p{i:02d}", "5 for 1", f"2026-11-03T10:{i:02d}:00+00:00")
        self.assertEqual(len(self.costs().splitlines()), 20)
        self.assertNotIn("more", self.costs())
        self.raw("cost.p20", "5 for 1", "2026-11-03T11:30:00+00:00")
        lines = self.costs().splitlines()
        self.assertEqual((len(lines), lines[-1], lines[0].split("(")[1][:3]), (21, "... and 1 more", "p20"))
        for i in range(21, 26): self.raw(f"cost.p{i:02d}", "5 for 1", f"2026-11-03T12:{i:02d}:00+00:00")
        self.assertEqual(self.costs().splitlines()[-1], "... and 6 more")
        listing = self.memory_list()
        self.assertIn("- zz-owner-note: keep (since", listing)  # 26 costs do not push the note out
        self.assertNotIn("cost.p", listing)
        self.assertEqual(listing.splitlines()[-1], "Costs saved: 26 (send costs)")


class StatusAndErrorTests(CostsTestCase):
    def test_hidden_held_missing_and_unreadable_catalog_keep_the_cost(self):
        # Bug caught: a vanished product called hidden, a held reason leaking, a catalog failure reported as deleted costs.
        for ident, pack in ((AVO, "24 for 12"), (CHEESE, "8 for 4"), (JAM, "6 for 2"), ("gone-product", "9 for 3")):
            self.raw(f"cost.{ident}", pack, "2026-11-03T20:00:00+00:00" if ident != "gone-product" else "2026-11-03T19:00:00+00:00")
        self.edit_products(lambda ps: [p.update(status="held", hold="private reason") if p["id"] == JAM else p.update(status="hidden") if p["id"] == CHEESE else None for p in ps])
        out = self.costs()
        self.assertIn(f"Hass avocado ({AVO}): $24.00", out)  # active: no suffix
        self.assertIn(f"Raw milk white cheddar ({CHEESE}) (hidden): $8.00 for 4 = $2.00 each", out)
        self.assertIn(f"Linn's triple berry preserves ({JAM}) (held): $6.00 for 2 = $3.00 each", out)
        self.assertIn("Product no longer listed (gone-product): $9.00 for 3 = $3.00 each, saved Tue Nov 3", out)
        self.assertNotIn("private reason", out)
        (self.repo.wt / "hass" / "content" / "products.json").write_text("{not json", "utf-8")
        out = self.costs()
        self.assertIn(f"Product name unavailable ({AVO}): $24.00 for 12 = $2.00 each", out)
        self.assertEqual(out.count("Product name unavailable"), 4)
        self.assertNotIn("no longer listed", out)
        self.assertIn("I can't look up the product names right now", out)
        self.assertNotIn(str(self.repo.wt), out)
        (self.repo.wt / "hass" / "content" / "products.json").write_text(json.dumps({"products": [
            {"id": AVO, "name": "bad\nname", "status": "active"}]}), "utf-8")
        self.assertIn(f"Product name unavailable ({AVO}): $24.00", self.costs())  # unsafe text is never echoed

    def test_malformed_cost_and_date_stay_listed_and_leak_nothing(self):
        # Bug caught: an unreadable row dropped, repaired, echoed raw, or a bad date raising a traceback / guessed.
        self.raw(f"cost.{AVO}", "24 for 12", "not a date")
        self.raw("cost.bad-value", "banana <script>", "2026-11-03T20:00:00+00:00")
        self.raw("cost.bad-units", "24 for 0", "2026-11-03T19:00:00+00:00")
        self.raw("cost.naive", "5 for 1", "2026-11-03T10:00:00")  # no zone: never guessed as local time
        self.raw("cost.BAD KEY!", "5 for 1", "2026-11-03T18:00:00+00:00")
        self.raw("cost.overflow", "5 for 1", "0001-01-01T00:00:00+14:00")
        before = self.snapshot()
        out = self.costs()
        self.assertEqual(self.snapshot(), before)
        lines = out.splitlines()
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[0], "bad-value: I can't read this saved cost. Send forget cost.bad-value to remove it.")
        self.assertIn("bad-units: I can't read this saved cost.", out)
        self.assertIn("One saved cost has a name I can't show, so I can't read it.", out)
        self.assertIn(f"Hass avocado ({AVO}): $24.00 for 12 = $2.00 each, saved date unavailable", out)
        self.assertIn("Product no longer listed (naive): $5.00 for 1 = $5.00 each, saved date unavailable", out)
        for text in ("banana", "script", "BAD KEY", "Traceback", str(self.repo.wt)): self.assertNotIn(text, out)

    def test_invalid_rows_count_toward_the_cap_and_a_read_failure_is_not_empty(self):
        # Bug caught: unreadable rows hidden from the count, and a failing read answered "No purchase costs saved."
        for i in range(21): self.raw(f"cost.q{i:02d}", "nonsense", "2026-11-03T20:00:00+00:00")
        lines = self.costs().splitlines()
        self.assertEqual((len(lines), lines[-1]), (21, "... and 1 more"))
        self.conv.db.execute("ALTER TABLE memory RENAME COLUMN created_at TO created_x")  # the read itself now fails
        self.assertEqual(self.say("costs"), "costs")
        self.assertEqual(self.replies(), [core_pack.COSTS_UNAVAILABLE])


class ReadOnlyAndParserTests(CostsTestCase):
    def test_paused_capped_and_lapsed_draft_change_nothing(self):
        # Bug caught: costs sweeping a lapsed draft, calling the interpreter/editor, writing usage rows, or refusing while paused or at the cap.
        self.set_settings({**SETTINGS, "interpreterDailyCap": 1})
        self.conv = self.open()
        self.save(f"cost {AVO}: 24 for 12")
        self.assertEqual(self.say("hours"), "proposed")
        self.replies()
        self.assertEqual(self.say("desc"), "daily-limit")  # the cap is reached
        self.replies()
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(seconds=601)  # the waiting draft has lapsed
        self.calls.clear()
        before, states = self.snapshot(), [d["state"] for d in self.drafts()]
        self.assertEqual(states, ["proposed"])
        self.assertEqual(self.costs(), f"Hass avocado ({AVO}): $24.00 for 12 = $2.00 each, saved Mon Nov 2")
        self.assertEqual(([d["state"] for d in self.drafts()], self.calls, self.snapshot()), (states, [], before))

    def test_parser_questions_lookalikes_owner_replay_and_attachment(self):
        # Bug caught: costs read as the mutating `cost`, a sentence starting with costs eaten as a command, strangers or replays answered.
        for text in ("costs", "Costs.", "COSTS!", "costs?", "  costs  "): self.assertEqual(conversation.read_command(text), ("costs", None), text)
        for text in ("costs are up", "costs avocado", "costly", "cost", "cost: 5 for 1"):
            self.assertIsNone(conversation.read_command(text), text)
        self.assertEqual(conversation.parse_memory("cost"), ("cost", "", ""))  # the save command is still its own verb
        self.assertNotEqual(self.say("costs are up", pid="x1"), "costs")
        self.replies()
        self.assertEqual(self.say("costs", sender=STRANGER), "ignored")
        self.assertEqual(self.say("costs", chat=GROUP), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.say("costs", pid="dup"), "costs")
        self.assertEqual(self.say("costs", pid="dup"), "duplicate")
        self.assertEqual(len(self.replies()), 1)
        self.assertNotEqual(self.conv.handle(conversation.Inbound("cap1", "chat-fixture-owner", "owner@example.invalid", "costs", attachments=1))[0], "costs")
        self.replies()

    def test_help_line_and_reply_voice(self):
        # Bug caught: the new command missing from help, or a reply the voice rules would refuse (long list, ids quoted).
        self.assertEqual(voice.plain(commands.help_detail("costs")), "costs - the purchase costs you've saved")
        self.assertIn("costs", voice.plain(conversation.HELP_TEXT))
        for i in range(21): self.raw(f"cost.v{i:02d}", "5 for 1", "2026-11-03T20:00:00+00:00")
        self.assertEqual(self.say("costs"), "costs")
        [reply] = self.replies()
        self.assertNotEqual(reply, voice.SAFE_LINE)  # the outbox swaps a reply the voice rules refuse for the safe line
        self.assertEqual(len(reply.splitlines()), 21)


if __name__ == "__main__":
    unittest.main()
