"""HASS-POS-1: till summary, price of, low stock, count drops (with Hass's own receipts added back), website vs till and the private
report + pos-totals.json. Synthetic fixtures only (FAKEMERCH0001, FAKE token); sockets are patched, the token and client are never touched.
Run: python3 -B -m unittest hass.tests.test_clover_pos
"""
import json
import sqlite3
import stat
import unittest
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from hass.clover import cache, cli, pos, reads, sync
from hass.clover.journal import Journal
from hass.tests.test_clover_chat import identity
from hass.tests.test_clover_cli import MID, CliCase, T0
from hass.tests.test_clover_client import fixture
from hass.tests.test_clover_reports import CONTENT, LINKS, put_inputs

IDS = [f"FAKEITEM0000{n}" for n in range(1, 7)]    # oil, avocado, eggs, honey (hidden), tomatoes, special (no count)
BASE = ["25", "50", "14", "0", "7.5", None]         # 08:30 Pacific today
NOW_COUNTS = ["11", "40", "0", "0", "7.5", None]    # 12:00 Pacific today (= T0)
EARLIER = ["30", "50", "14", "0", "7.5", None]      # yesterday 06:00 Pacific
NOTE = "(count drops, not exact sales: a recount or a till edit also shows here)"
GONE = "I don't have an earlier till count to compare with yet, so no count drops today"
SUMMARY = ("Till at 12:00 pm: 6 items, 2 sold out, 0 running low, 1 with no count. Website: 2 linked, stock words waiting: not available yet. "
           "Count drops today: 3 items, 33 units.")   # 14 + 14 + 5 (the avocado's 10 less Hass's own 5)


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

    def journal(self, day, item_id, before, after, kind="set_stock", status="applied", at=None):
        with Journal(self.state, SimpleNamespace(environment="production", merchant_id=MID)).locked() as db:
            result = json.dumps({"kind": kind, "item_id": item_id, "before": {"stock": before}, "after": {"stock": after}})
            n = db.execute("SELECT count(*) FROM changes").fetchone()[0]
            db.execute("INSERT INTO changes VALUES(?,?,?,?,?,?,?,?)", (f"c{n}", "{}", "s", "c", ((at or T0 - timedelta(hours=1)).timestamp() + 600), status, day, result))

    def deltas(self):
        return pos.journal_deltas(self.state, identity(), "2026-11-04")


class ViewTests(PosCase):
    def test_summary_word_for_word_with_hass_receipts_added_back(self):
        self.journal("2026-11-10", IDS[1], "50", "45")     # Hass lowered the avocado count itself: not a drop to show
        self.assertEqual(pos.summary(self.snapshot, self.snaps, self.deltas(), T0, CONTENT, LINKS), SUMMARY)
        self.assertEqual(pos.drops(self.snapshot, self.snaps, self.deltas(), T0),
                         f"Biggest count drops today: Eggs, dozen 14, Sunshine olive oil 14, Hass avocado 5 {NOTE}")

    def test_receipt_added_back_the_other_way_and_only_set_stock_applied_in_period(self):
        self.journal("2026-11-10", IDS[0], "25", "31")      # received 6 at the shelf: the drop is 14 + 6
        self.journal("2026-11-10", IDS[2], "14", "99", status="draft")
        self.journal("2026-11-10", IDS[2], "14", "99", kind="set_price")
        self.journal("2026-11-09", IDS[1], "50", "10", at=T0 - timedelta(hours=26))      # yesterday: not in today's reply
        self.assertEqual(pos.drops(self.snapshot, self.snaps, self.deltas(), T0),
                         f"Biggest count drops today: Sunshine olive oil 20, Eggs, dozen 14, Hass avocado 10 {NOTE}")
        self.assertEqual(pos.drops(self.snapshot, self.snaps, self.deltas(), T0, days=7),
                         f"Biggest count drops this week: Sunshine olive oil 25, Eggs, dozen 14 {NOTE}")

    def test_only_changes_strictly_between_the_first_and_last_count_are_added_back(self):
        self.journal("2026-11-10", IDS[0], "25", "35", at=T0 - timedelta(hours=5))   # +10 on the oil before the first count (25 -> 11: drop 14)
        self.assertEqual(pos.drop_rows(self.snapshot, self.snaps, self.deltas(), T0, 1)[1][1], 14)     # already in the first count: no 24
        self.journal("2026-11-10", IDS[0], "25", "35", at=T0 - timedelta(hours=3, minutes=30))     # at the first count: not after it
        self.journal("2026-11-10", IDS[0], "25", "35", at=T0)                                      # at the last count: not before it
        self.journal("2026-11-10", IDS[0], "25", "35", at=T0 + timedelta(hours=1))                 # after the last count
        self.assertEqual([(i.name, n) for i, n in pos.drop_rows(self.snapshot, self.snaps, self.deltas(), T0, 1)][:2],
                         [("Eggs, dozen", 14), ("Sunshine olive oil", 14)])
        self.journal("2026-11-10", IDS[0], "25", "35", at=T0 - timedelta(hours=2))                 # between the two counts: added back
        self.assertEqual(pos.drop_rows(self.snapshot, self.snaps, self.deltas(), T0, 1)[0][1], 24)

    def test_week_and_the_note_is_always_present(self):
        self.assertEqual(pos.drops(self.snapshot, self.snaps, [], T0, days=7),
                         f"Biggest count drops this week: Sunshine olive oil 19, Eggs, dozen 14, Hass avocado 10 {NOTE}")
        flat = [(T0 - timedelta(hours=2), {i: Decimal(c or 0) for i, c in zip(IDS, NOW_COUNTS)})]
        for snaps, text in (([], GONE), (self.snaps[-1:], GONE), (flat, "No count drops today")):
            self.assertEqual(pos.drops(self.snapshot, snaps, [], T0), f"{text} {NOTE}")
        self.assertTrue(pos.summary(self.snapshot, [], [], T0, CONTENT, LINKS).endswith("Count drops today: not enough history yet."))

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
        self.assertTrue(pos.drops(self.snapshot, self.snaps, [], gone, False).startswith("I can't reach the till right now."))
        for text in (pos.price_of("eggs, dozen", self.snapshot, old), pos.drops(self.snapshot, self.snaps, [], old),
                     pos.summary(self.snapshot, self.snaps, [], old, CONTENT, LINKS), pos.low(self.snapshot, old, 5),
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
        self.journal("2026-11-10", IDS[1], "50", "45")
        code, out, stdout = self.run_pos()
        self.assertEqual((code, out), (0, {"result": "ok", "reports": 1, "asOf": "2026-11-10T20:00:00+00:00"}))
        self.assertEqual(stat.S_IMODE(self.folder.stat().st_mode), 0o700)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["2026-11-10-pos.md", "pos-totals.json"])
        for p in self.folder.iterdir():
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        md = (self.folder / "2026-11-10-pos.md").read_text()
        self.assertIn(SUMMARY, md)
        self.assertIn("Biggest count drops this week: Sunshine olive oil 19, Eggs, dozen 14, Hass avocado 5", md.replace("\\", ""))
        for value in ("Olive", "1250", "12.50", str(self.folder)):
            self.assertNotIn(value, stdout)
        self.assertEqual(self.run_pos()[0], 0)    # the same day replaces the files

    def test_pos_totals_hold_no_name_price_or_sku(self):
        self.run_pos()
        text = (self.folder / "pos-totals.json").read_text()
        self.assertEqual(json.loads(text), {
            "asOf": "2026-11-10T20:00:00+00:00", "items": 6, "soldOut": 2, "low": 0, "noCount": 1, "stockWordsWaiting": None,
            "countDropItems": 3, "countDropUnits": "38", "tillReachable": True, "snapshot": "fresh"})
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
        self.assertEqual(pos.journal_deltas(self.state, identity(), "2026-01-01"), [])     # no journal yet


if __name__ == "__main__":
    unittest.main()
