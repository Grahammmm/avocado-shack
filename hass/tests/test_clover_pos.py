"""HASS-POS-1: till summary, price of, low stock, "what sold" as count drops between reads (labelled "includes stock edits"), website vs till and the private
report + pos-totals.json. Synthetic fixtures only (FAKEMERCH0001, FAKE token); sockets are patched, the token and client are never touched.
Run: python3 -B -m unittest hass.tests.test_clover_pos
"""
import json
import sqlite3
import os
import stat
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from hass.clover import cache, cli, pos, reads, sync
from hass.tests.test_clover_chat import identity
from hass.tests.test_clover_cli import CliCase, T0
from hass.tests.test_clover_client import fixture
from hass.tests.test_clover_reports import CONTENT, LINKS, put_inputs

IDS = [f"FAKEITEM0000{n}" for n in range(1, 7)]    # oil, avocado, eggs, honey (hidden), tomatoes, special (no count)
BASE = ["25", "50", "14", "0", "7.5", None]         # 08:30 Pacific today
NOW_COUNTS = ["11", "40", "0", "0", "7.5", None]    # 12:00 Pacific today (= T0)
EARLIER = ["30", "50", "14", "0", "7.5", None]      # yesterday 06:00 Pacific
LABEL = "includes stock edits"
NOTE = "(count drops between till reads, not exact sales)"
GONE = f"I don't have an earlier till count to compare with yet, so I can't say what sold today ({LABEL})"
SUMMARY = ("Till at 12:00 pm: 6 items, 2 sold out, 0 running low, 1 with no count. Website: 2 linked, stock words waiting: not available yet. "
           f"Sold today ({LABEL}): 3 items, 38 units.")   # 14 + 14 + 10


def put(state, when, counts):
    rows, _ = sync.rows(fixture("items.json")["elements"], fixture("item_stocks.json")["elements"])
    for row, count in zip(rows, counts):
        row["stock"] = count
    cache.write_items(state, rows, when, identity())


class PosCase(CliCase):
    def setUp(self):
        super().setUp()
        for when, counts in ((T0 - timedelta(hours=30), EARLIER), (T0 - timedelta(hours=3, minutes=30), BASE), (T0, NOW_COUNTS)):
            put(self.state, when, counts)
        self.snaps = cache.history(self.state, identity())
        self.snapshot, self.reachable = cache.read(self.state, identity())

    def with_series(self, *series):
        """Replace the stored reads with (hours before T0, counts) pairs; returns (snapshot, snaps)."""
        for when, counts in series:
            put(self.state, T0 - timedelta(hours=when), counts)
        return cache.read(self.state, identity())[0], cache.history(self.state, identity())


class ViewTests(PosCase):
    def test_summary_word_for_word_and_every_sold_number_carries_the_label(self):
        self.assertEqual(pos.summary(self.snapshot, self.snaps, T0, CONTENT, LINKS), SUMMARY)
        self.assertEqual(pos.drops(self.snapshot, self.snaps, T0),
                         f"Sold today ({LABEL}): Eggs, dozen 14, Sunshine olive oil 14, Hass avocado 10 {NOTE}")

    def test_drops_are_summed_and_increases_are_ignored(self):
        # oil 25 -> 20 (drop 5) -> 30 (restock +10, ignored) -> 24 (drop 6): 11. Net change is a rise of -1, yet the sold number is 11.
        snapshot, snaps = self.with_series((3, ["20", "50", "14", "0", "7.5", None]), (2, ["30", "50", "14", "0", "7.5", None]),
                                           (0.0, ["24", "50", "14", "0", "7.5", None]))
        rows = dict((i.name, n) for i, n in pos.drop_rows(snapshot, snaps, T0, 1))
        self.assertEqual(rows.get("Sunshine olive oil"), 11)

    def test_a_count_that_only_rose_is_never_a_negative_sale(self):
        snapshot, snaps = self.with_series((0.0, ["50", "50", "14", "0", "7.5", None]))     # the oil only went up since the first read: 25 -> 50
        self.assertEqual(pos.drop_rows(snapshot, snaps, T0, 1), [])
        self.assertEqual(pos.drops(snapshot, snaps, T0), f"Sold today ({LABEL}): nothing, no count dropped {NOTE}")

    def test_hass_own_set_stock_between_reads_counts_as_a_drop_and_the_label_says_so(self):
        # Hass lowered the avocado from 50 to 45 itself between two reads: nothing is added back, so it is part of the sold number.
        snapshot, snaps = self.with_series((3, ["25", "50", "14", "0", "7.5", None]), (2, ["25", "45", "14", "0", "7.5", None]),
                                           (0.0, ["11", "40", "0", "0", "7.5", None]))
        text = pos.drops(snapshot, snaps, T0)
        self.assertIn("Hass avocado 10", text)          # 5 (Hass's own edit) + 5
        self.assertIn(f"Sold today ({LABEL})", text)
        self.assertIn("includes stock edits", pos.summary(snapshot, snaps, T0, CONTENT, LINKS))

    def test_an_item_missing_from_a_read_is_left_out_not_guessed(self):
        mid = ["25", "50", "14", "0", None, None]       # tomatoes have no count in the middle read: no row for it
        snapshot, snaps = self.with_series((3, ["25", "50", "14", "0", "9", None]), (2, mid), (0.0, ["11", "40", "0", "0", "7.5", None]))
        left = []
        names = [i.name for i, _ in pos.drop_rows(snapshot, snaps, T0, 1, left)]
        self.assertEqual((left, "Heirloom tomatoes" in names), (["Heirloom tomatoes"], False))
        self.assertIn(" Left out: Heirloom tomatoes (a count was missing in one of the reads).", pos.drops(snapshot, snaps, T0))
        self.assertIn("Sunshine olive oil 14", pos.drops(snapshot, snaps, T0))

    def test_a_read_with_no_counts_at_all_still_counts_as_a_read_so_the_item_is_left_out(self):
        # oil 10 -> a good read where nothing has a count -> 5: the empty read is kept, so the oil is left out (never "5 sold" or "10 -> 5").
        none = [None] * 6
        snapshot, snaps = self.with_series((3, ["10", "50", "14", "0", "7.5", None]), (2, none), (0.0, ["5", "50", "14", "0", "7.5", None]))
        self.assertIn(T0 - timedelta(hours=2), [t for t, _ in snaps])
        left = []
        names = [i.name for i, _ in pos.drop_rows(snapshot, snaps, T0, 1, left)]
        self.assertEqual(("Sunshine olive oil" in names, "Sunshine olive oil" in left), (False, True))
        self.assertNotIn("Sunshine olive oil 5", pos.drops(snapshot, snaps, T0))
        self.assertIn("Sunshine olive oil", pos.drops(snapshot, snaps, T0).split("Left out:")[1])

    def test_an_item_whose_latest_count_is_missing_is_left_out_not_zero_sold(self):
        # oil 10 -> no count in the latest read (terminal): left out and incomplete, never "0 sold" and never a complete total.
        snapshot, snaps = self.with_series((3, ["10", "50", "14", "0", "7.5", None]), (0.0, [None, "50", "14", "0", "7.5", None]))
        left = []
        names = [i.name for i, _ in pos.drop_rows(snapshot, snaps, T0, 1, left)]
        self.assertEqual((left, "Sunshine olive oil" in names), (["Sunshine olive oil"], False))
        self.assertIn("Left out: Sunshine olive oil", pos.drops(snapshot, snaps, T0))
        self.assertIn("incomplete", pos.summary(snapshot, snaps, T0, CONTENT, LINKS))

    def test_an_item_missing_in_the_middle_and_back_later_is_still_left_out(self):
        snapshot, snaps = self.with_series((3, ["10", "50", "14", "0", "7.5", None]), (2, [None, "50", "14", "0", "7.5", None]),
                                           (0.0, ["5", "50", "14", "0", "7.5", None]))
        left = []
        pos.drop_rows(snapshot, snaps, T0, 1, left)
        self.assertEqual(left, ["Sunshine olive oil"])

    def test_summary_and_totals_say_incomplete_when_items_are_left_out(self):
        mid = ["25", "50", "14", "0", None, None]
        snapshot, snaps = self.with_series((3, ["25", "50", "14", "0", "9", None]), (2, mid), (0.0, ["11", "40", "0", "0", "7.5", None]))
        text = pos.summary(snapshot, snaps, T0, CONTENT, LINKS)
        self.assertIn(f"Sold today ({LABEL}): 3 items, 38 units, incomplete: 1 item left out.", text)
        totals = pos.build(snapshot, snaps, T0, CONTENT, LINKS)[1]
        self.assertEqual((totals["countDropLeftOut"], totals["countDropIncomplete"]), (1, "incomplete: 1 item left out"))
        self.assertIn("incomplete: 1 item left out", pos.build(snapshot, snaps, T0, CONTENT, LINKS)[0])
        whole = pos.build(self.snapshot, self.snaps, T0, CONTENT, LINKS)
        self.assertEqual((whole[1]["countDropLeftOut"], whole[1]["countDropIncomplete"]), (0, None))
        self.assertNotIn("incomplete", pos.summary(self.snapshot, self.snaps, T0, CONTENT, LINKS))

    def test_label_in_every_reply_shape(self):
        for snaps, text in (([], GONE), (self.snaps[-1:], GONE), ([(T0 - timedelta(hours=2), {i: Decimal(c) for i, c in zip(IDS, NOW_COUNTS) if c is not None})],
                                                                   f"Sold today ({LABEL}): nothing, no count dropped")):
            self.assertEqual(pos.drops(self.snapshot, snaps, T0), f"{text} {NOTE}")
        self.assertIn(LABEL, GONE)
        self.assertEqual(pos.drops(self.snapshot, self.snaps, T0, days=7),
                         f"Sold this week ({LABEL}): Sunshine olive oil 19, Eggs, dozen 14, Hass avocado 10 {NOTE}")
        self.assertTrue(pos.summary(self.snapshot, [], T0, CONTENT, LINKS).endswith(f"Sold today ({LABEL}): not enough history yet."))

    def test_price_of_and_how_many(self):
        self.assertEqual(pos.price_of("Eggs, dozen", self.snapshot, T0), "Eggs, dozen: $7.00 each, 0 in the till (as of 12:00 pm).")
        self.assertEqual(pos.price_of("sunshine olive oil", self.snapshot, T0 + timedelta(minutes=5)),
                         "Sunshine olive oil: $12.50 each, 11 in the till (as of 12:00 pm).")
        self.assertIn("Old honey jar: $11.00 each, 0 in the till; hidden on the till", pos.price_of("old honey jar", self.snapshot, T0))
        self.assertIn("the till keeps no count", pos.price_of("market special (ring up price)", self.snapshot, T0))
        self.assertEqual(pos.price_of("tomatoe", self.snapshot, T0), "I can't find exactly that. The closest is Heirloom tomatoes: 7.5 in the till.")

    def test_staleness_lines(self):
        stale, gone, old = T0 + timedelta(hours=2), T0 + timedelta(hours=1), T0 + timedelta(hours=25)
        self.assertEqual(pos.price_of("eggs, dozen", self.snapshot, stale), "Eggs, dozen: $7.00 each, 0 in the till (as of 12:00 pm). (till count as of 12:00 pm)")
        self.assertEqual(pos.price_of("eggs, dozen", self.snapshot, gone, False),
                         "I can't reach the till right now. The last count I have is from 12:00 pm, so treat it as old. Eggs, dozen: $7.00 each, 0 in the till.")
        for p in (pos.drops(self.snapshot, self.snaps, gone, False),):
            self.assertTrue(p.startswith("I can't reach the till right now."))
        for text in (pos.price_of("eggs, dozen", self.snapshot, old), pos.drops(self.snapshot, self.snaps, old),
                     pos.summary(self.snapshot, self.snaps, old, CONTENT, LINKS), pos.low(self.snapshot, old, 5),
                     pos.website_vs_till(self.snapshot, CONTENT, LINKS, old)):
            self.assertEqual(text, reads.freshness(self.snapshot, old)[1])
            self.assertTrue(text.startswith("I have not been able to read the till since Tue 12:00 pm"), text)
            self.assertNotIn("$", text)

    def test_low_stock_and_website_vs_till_use_the_existing_reports(self):
        self.assertEqual(pos.low(self.snapshot, T0, 5), "Sold out: Eggs, dozen. 1 item(s) have no count in the till, so I can't tell.")
        text = pos.website_vs_till(self.snapshot, CONTENT, LINKS, T0)
        self.assertTrue(text.startswith("Website vs till. Till items without a site link: "))
        self.assertIn("Stock word disagreements: Eggs, dozen (eggs): site yes; till 0.", text)
        self.assertIn("Broken links: gone / FAKEITEM00002: site item is absent or not active; pears / MISSING: till item is absent", text)


class ReportTests(PosCase):
    def setUp(self):
        super().setUp()
        self.wt = self.root / "writer"
        put_inputs(self.state, self.wt)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.wt)}))
        self.folder = self.state / "clover/reports"

    def run_pos(self):
        with mock.patch.object(cli, "_token", side_effect=AssertionError("token")), mock.patch.object(cli, "_client", side_effect=AssertionError("network")):
            return self.run_cli("report", "pos")

    def test_report_pos_writes_private_files_and_totals_only(self):
        code, out, stdout = self.run_pos()
        self.assertEqual((code, out), (0, {"result": "ok", "reports": 1, "asOf": "2026-11-10T20:00:00+00:00"}))
        self.assertEqual(stat.S_IMODE(self.folder.stat().st_mode), 0o700)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["2026-11-10-pos.md", "pos-totals.json"])
        for p in self.folder.iterdir():
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        md = (self.folder / "2026-11-10-pos.md").read_text()
        self.assertIn(SUMMARY, md)
        self.assertIn(f"## Sold today ({LABEL})", md)
        self.assertIn(f"Sold this week ({LABEL}): Sunshine olive oil 19, Eggs, dozen 14, Hass avocado 10", md.replace("\\", ""))
        for value in ("Olive", "1250", "12.50", str(self.folder)):
            self.assertNotIn(value, stdout)
        self.assertEqual(self.run_pos()[0], 0)    # the same day replaces the files

    def test_pos_totals_hold_no_name_price_or_sku(self):
        self.run_pos()
        text = (self.folder / "pos-totals.json").read_text()
        self.assertEqual(json.loads(text), {
            "asOf": "2026-11-10T20:00:00+00:00", "items": 6, "soldOut": 2, "low": 0, "noCount": 1, "stockWordsWaiting": None,
            "countDropItems": 3, "countDropUnits": "38", "countDropNote": LABEL, "countDropLeftOut": 0, "countDropIncomplete": None, "tillReachable": True, "snapshot": "fresh"})
        rows, _ = sync.rows(fixture("items.json")["elements"], fixture("item_stocks.json")["elements"])
        for row in rows:
            cents = () if row["price_cents"] is None else (str(row["price_cents"]), f"{row['price_cents'] / 100:.2f}")
            for value in (row["name"], row["sku"], row["code"], *cents):
                self.assertTrue(not value or value.casefold() not in text.casefold(), value)
        self.assertNotIn("$", text)

    def test_prune_only_dated_pos_files_at_90_days(self):
        self.folder.mkdir(mode=0o700)
        for name in ("2026-08-12-pos.md", "2026-08-13-pos.md", "2026-08-12-stock.md", "2026-99-99-pos.md", "notes-pos.md"):
            (self.folder / name).write_text("fixture")
        self.assertEqual(self.run_pos()[0], 0)
        self.assertFalse((self.folder / "2026-08-12-pos.md").exists())
        for name in ("2026-08-13-pos.md", "2026-08-12-stock.md", "2026-99-99-pos.md", "notes-pos.md"):
            self.assertTrue((self.folder / name).exists(), name)

    def test_unsafe_folder_or_target_write_nothing(self):
        self.folder.mkdir()
        self.folder.chmod(0o755)
        self.assertEqual(self.run_pos()[0], 1)
        self.folder.chmod(0o700)
        target = self.folder / "pos-totals.json"
        target.write_text("{}")
        target.chmod(0o644)
        self.assertEqual(self.run_pos()[0], 1)
        self.assertEqual(target.read_text(), "{}")


class HistoryTests(PosCase):
    def test_snapshots_are_written_with_the_sync_and_pruned_after_14_days(self):
        self.assertEqual([t for t, _ in self.snaps], [T0 - timedelta(hours=30), T0 - timedelta(hours=3, minutes=30), T0])
        self.assertEqual(self.snaps[-1][1], {i: Decimal(c) for i, c in zip(IDS, NOW_COUNTS) if c})     # no row for an item with no count
        put(self.state, T0 - timedelta(hours=30) + timedelta(days=14), BASE)       # exactly 14 days after the oldest read: it stays
        self.assertEqual(len(cache.history(self.state, identity())), 4)
        put(self.state, T0 - timedelta(hours=29) + timedelta(days=14), BASE)       # now it is over 14 days old: pruned with this sync
        self.assertNotIn(T0 - timedelta(hours=30), [t for t, _ in cache.history(self.state, identity())])
        self.assertEqual(len(cache.history(self.state, identity())), 4)

    def test_a_good_sync_of_another_till_empties_the_history_with_no_failed_sync_between(self):
        other = cache.Identity("production", "FAKEMERCH0002")
        self.assertEqual(len(cache.history(self.state, identity())), 3)
        rows, _ = sync.rows(fixture("items.json")["elements"], fixture("item_stocks.json")["elements"])
        cache.write_items(self.state, rows, T0 + timedelta(hours=1), other)
        self.assertEqual(cache.history(self.state, identity()), [])
        self.assertEqual([t for t, _ in cache.history(self.state, other)], [T0 + timedelta(hours=1)])     # only this till's own read
        cache.write_items(self.state, rows, T0 + timedelta(hours=2), other)       # the same till again keeps its history
        self.assertEqual(len(cache.history(self.state, other)), 2)

    def test_other_till_drops_history_and_an_old_cache_reads_empty(self):
        other = cache.Identity("production", "FAKEMERCH0002")
        self.assertEqual(cache.history(self.state, other), [])
        cache.record_failure(self.state, "unreachable", T0, identity=other)
        db = sqlite3.connect(cache.path_for(self.state))
        self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 0)
        db.execute("DROP TABLE snapshots")
        db.commit()
        db.close()
        self.assertEqual(cache.history(self.state, other), [])


if __name__ == "__main__":
    unittest.main()
