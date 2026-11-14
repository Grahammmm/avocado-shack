"""AVB-14: real cache/CLI and Conversation, synthetic #571 inventory only."""
import json
import os
import stat
import sqlite3
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from hass import conversation, voice
from hass.clover import cache, chat, cli, reports
from hass.clover.reads import Snapshot
from hass.tests.test_clover_chat import BLOCK, identity, seed
from hass.tests.test_clover_cli import CliCase, T0
from hass.tests.test_conversation import CHAT, OWNER, STRANGER, SETTINGS, ConversationTestCase

CONTENT = {"products": [
    {"id": "oil", "name": "Olive oil", "status": "active", "available": "yes"},
    {"id": "eggs", "name": "Eggs, dozen", "status": "active", "available": "yes"},
    {"id": "pears", "name": "Pears", "status": "active", "available": "no"},
    {"id": "hidden", "name": "Hidden", "status": "hidden"},
    {"id": "held", "name": "Held", "status": "held"},
]}
LINKS = {"oil": {"cloverId": "FAKEITEM00001", "sku": "AS-PAN-SUNSHINE-OLIVE-OIL-01"},
         "eggs": {"cloverId": "FAKEITEM00003", "sku": "EGG12"},
         "pears": {"cloverId": "MISSING"}, "gone": {"cloverId": "FAKEITEM00002"}}


def put_inputs(state, worktree):
    folder = worktree / "hass/content"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "products.json").write_text(json.dumps(CONTENT))
    path = state / "clover/links.json"
    path.write_text(json.dumps(LINKS))
    path.chmod(0o600)


class ReportTests(CliCase):
    def setUp(self):
        super().setUp()
        seed(self.state)
        self.snapshot, _ = cache.read(self.state, identity())
        self.wt = self.root / "writer"
        put_inputs(self.state, self.wt)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.wt)}))

    def test_stock_groups_unknown_zero_negative_fraction_and_inclusive_threshold(self):
        items = self.snapshot.items
        stock = reports.low_stock(self.snapshot)["sections"]
        self.assertEqual([[i.name for i in rows] for rows in stock.values()],
                         [["Eggs, dozen", "Old honey jar"], [], ["Market special (ring up price)"]])
        adjusted = Snapshot(tuple(replace(items[0], id=str(n), stock=q) for n, q in enumerate(
            [Decimal(-1), Decimal(0), Decimal("0.5"), Decimal(5), Decimal("5.01"), None])), T0)
        self.assertEqual([len(r) for r in reports.low_stock(adjusted)["sections"].values()], [2, 2, 1])
        self.assertEqual([len(r) for r in reports.low_stock(adjusted, 0)["sections"].values()], [2, 0, 1])

    def test_mismatch_has_both_gaps_names_broken_links_and_stock_word(self):
        sections = reports.till_vs_site(self.snapshot, CONTENT, LINKS)["sections"]
        self.assertEqual([len(r) for r in sections.values()], [4, 1, 1, 2, 1])
        self.assertIn("Pears (pears)", sections["Site items without a till link"])
        self.assertIn("site yes; till 0", sections["Stock word disagreements"][0])
        self.assertTrue(any("Olive oil / Sunshine olive oil" in r for r in sections["Different names"]))
        self.assertNotIn("Hidden", str(sections))
        self.assertNotIn("Held", str(sections))
        changed = {**LINKS, "oil": {"cloverId": "FAKEITEM00001", "sku": "stale"}, "bad": {}}
        self.assertEqual(len(reports.till_vs_site(self.snapshot, CONTENT, changed)["sections"]["Broken links"]), 4)
        sold = {"products": [{"id": "oil", "name": "Sunshine olive oil", "status": "active", "available": "no"}]}
        self.assertIn("site no; till 11", reports.till_vs_site(self.snapshot, sold, {"oil": LINKS["oil"]})[
            "sections"]["Stock word disagreements"][0])

    def test_cli_writes_both_private_files_with_no_token_or_network_and_redacted_stdout(self):
        before = cache.path_for(self.state).read_bytes()
        with mock.patch.object(cli, "_token", side_effect=AssertionError("token")), \
                mock.patch.object(cli, "_client", side_effect=AssertionError("network")):
            code, out, stdout = self.run_cli("report", "--all")
        self.assertEqual((code, out["result"], out["reports"]), (0, "ok", 2))
        folder = self.state / "clover/reports"
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["2026-11-10-mismatch.md", "2026-11-10-stock.md"])
        for p in folder.iterdir():
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
            self.assertIn("Last sync: 2026-11-10T20:00:00+00:00", p.read_text())
        self.assertIn("Stock word disagreements (1)", (folder / "2026-11-10-mismatch.md").read_text())
        self.assertEqual(cache.path_for(self.state).read_bytes(), before)
        for value in ("Olive", "1250", "12.50", str(folder)):
            self.assertNotIn(value, stdout)
        self.assertEqual(self.run_cli("report", "stock")[0], 0)  # same-day atomic replacement

    def test_no_cache_wrong_identity_legacy_and_unsafe_cache_write_nothing(self):
        for block in ({**BLOCK, "merchantId": "FAKEMERCH0002"}, {**BLOCK, "environment": "sandbox"}):
            seed(self.state, block=block)
            self.assertEqual(self.run_cli("report", "stock")[:2], (2, {"result": "no-cache"}))
        cache.path_for(self.state).unlink()
        self.assertEqual(self.run_cli("report", "stock")[0], 2)
        seed(self.state)
        db = sqlite3.connect(cache.path_for(self.state))
        db.execute("DELETE FROM meta WHERE key IN ('environment', 'merchantId', 'schema')")
        db.commit()
        db.close()
        self.assertEqual(self.run_cli("report", "stock")[0], 2)
        seed(self.state)
        cache.path_for(self.state).chmod(0o644)
        self.assertEqual(self.run_cli("report", "stock")[0], 2)
        self.assertFalse((self.state / "clover/reports").exists())

    def test_prune_only_report_dates_at_90_days_and_pacific_filename(self):
        self.run_cli("report", "stock")
        folder = self.state / "clover/reports"
        for name in ("2026-08-12-stock.md", "2026-08-13-mismatch.md", "2026-08-11-notes.md", "2026-99-99-stock.md"):
            (folder / name).write_text("fixture")
        outside = self.root / "keep.md"
        outside.write_text("preserve")
        (folder / "2026-08-11-stock.md").symlink_to(outside)
        self.now = T0.replace(hour=7)  # UTC Tuesday, Pacific Monday
        self.run_cli("report", "stock")
        self.assertTrue((folder / "2026-11-09-stock.md").exists())
        self.now = T0
        self.run_cli("report", "stock")
        self.assertFalse((folder / "2026-08-12-stock.md").exists())
        for name in ("2026-08-13-mismatch.md", "2026-08-11-notes.md", "2026-99-99-stock.md", "2026-08-11-stock.md"):
            self.assertTrue((folder / name).exists(), name)
        self.assertEqual(outside.read_text(), "preserve")

    def test_output_refuses_symlink_unsafe_dir_target_and_repo(self):
        folder = self.root / "out"
        folder.mkdir(mode=0o700)
        self.assertEqual(self.run_cli("report", "stock", "--out", str(folder))[0], 0)
        target = folder / "2026-11-10-stock.md"
        target.chmod(0o644)
        self.assertNotEqual(self.run_cli("report", "stock", "--out", str(folder))[0], 0)
        target.unlink()
        victim = self.root / "victim"
        victim.write_text("do not touch")
        target.symlink_to(victim)
        self.assertNotEqual(self.run_cli("report", "stock", "--out", str(folder))[0], 0)
        self.assertEqual(victim.read_text(), "do not touch")
        alias = self.root / "alias"
        alias.symlink_to(folder, target_is_directory=True)
        self.assertNotEqual(self.run_cli("report", "stock", "--out", str(alias))[0], 0)
        folder.chmod(0o755)
        self.assertNotEqual(self.run_cli("report", "stock", "--out", str(folder))[0], 0)
        self.assertEqual(self.run_cli("report", "stock", "--out", str(cli.REPO_ROOT))[1]["problem"], "inside-repo")
        self.assertEqual(self.run_cli("report", "stock", "--out", str(self.wt))[1]["problem"], "inside-repo")

    def test_missing_links_are_explicit_gaps_malformed_links_refused(self):
        path = self.state / "clover/links.json"
        path.unlink()
        self.assertEqual(self.run_cli("report", "mismatch")[0], 0)
        text = (self.state / "clover/reports/2026-11-10-mismatch.md").read_text()
        self.assertIn("Site items without a till link (3)", text)
        path.write_text("[]")
        path.chmod(0o600)
        self.assertEqual(self.run_cli("report", "mismatch")[0], 1)

    def test_render_labels_stale_outage_and_escapes_imported_names(self):
        sample = Snapshot((replace(self.snapshot.items[0], name="[click](https://bad)\n# heading", stock=Decimal(0)),), T0)
        doc = reports.low_stock(sample)
        self.assertIn("Snapshot: stale", reports.render_md(doc, T0 + timedelta(hours=1)))
        self.assertIn("Snapshot: unreachable", reports.render_md(doc, T0, False))
        self.assertIn("Snapshot: too-old", reports.render_md(doc, T0 + timedelta(days=2)))
        text = reports.render_md(doc, T0)
        self.assertIn(r"\[click\]\(https://bad\) \# heading", text)
        self.assertNotIn("\n# heading", text)


class ReportChatTests(ConversationTestCase):
    G, GCHAT = "+15555550199", "iMessage;-;+15555550199"

    def setUp(self):
        super().setUp()
        self.now = T0
        self.conv.db.close()
        self.set_settings({**SETTINGS, "gSenders": [self.G], "gChat": self.GCHAT})
        self.conv = self.open()
        self.conv.outbox.strict = True
        self.conv.till = chat.TillDesk(str(self.repo.state), BLOCK)
        seed(self.repo.state)
        put_inputs(self.repo.state, self.repo.wt)
        self.interp.interpret = mock.Mock(side_effect=AssertionError("model"))

    def test_only_g_gets_headlines_not_prices_names_or_files(self):
        self.say("pause changes")
        self.replies()
        with mock.patch.object(cli, "_token", side_effect=AssertionError("token")), \
                mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            self.assertEqual(self.say("till report", sender=self.G, chat=self.GCHAT), "g-till-report")
            [text] = self.replies()
        self.assertEqual(voice.check(text, long_ok=True), [])
        self.assertIn("2 sold out, 0 running low, 1 with no count", text)
        self.assertIn("9 things to check", text)
        for value in ("1250", "12.50", "$", "Olive", "FAKE", ".md"):
            self.assertNotIn(value, text)
        self.assertEqual(self.out.sent[-1]["chat"], self.GCHAT)
        self.assertFalse((self.repo.state / "clover/reports").exists())
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_non_g_report_preserves_normal_owner_stranger_echo_and_edit_handling(self):
        self.interp.interpret = mock.Mock(return_value={"unsupported": "Sorry, I can't do that yet."})
        cases = (
            (OWNER, CHAT, False, "new", "unsupported", ["Sorry, I can't do that yet."], True),
            (OWNER, CHAT, False, "edited", "not-read", [conversation.NOT_READ_REPLY], True),
            (OWNER, CHAT, True, "new", "echo", [], False),
            (STRANGER, self.GCHAT, False, "new", "ignored", [], False),
            (self.G, CHAT, False, "new", "ignored", [], False),
            (self.G, self.GCHAT, True, "new", "echo", [], False),
            (self.G, self.GCHAT, False, "edited", "edited-ignored", [], False),
        )
        with mock.patch.object(self.conv.till, "report") as report:
            for sender, dest, from_me, kind, expected, replies, owner in cases:
                with self.subTest(sender=sender, chat=dest, from_me=from_me, kind=kind):
                    self.assertEqual(self.say("till report", sender=sender, chat=dest, from_me=from_me, kind=kind), expected)
                    self.assertEqual(self.replies(), replies)
                    row = self.conv.db.execute("SELECT disposition, received_at FROM messages WHERE provider_id = ?",
                                               (f"m{self.n}",)).fetchone()
                    self.assertEqual(tuple(row), (expected, self.now.isoformat() if owner else None))
                    chat_row = self.conv.db.execute("SELECT chat FROM message_chats WHERE provider_id = ?",
                                                    (f"m{self.n}",)).fetchone()
                    self.assertEqual(tuple(chat_row) if chat_row else None, (dest,) if owner else None)
            report.assert_not_called()
        self.interp.interpret.assert_called_once()
        self.assertEqual(self.interp.interpret.call_args.args[0], "till report")
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_chat_preserves_age_outage_identity_and_unavailable_content(self):
        self.now += timedelta(hours=1)
        self.say("till report", sender=self.G, chat=self.GCHAT)
        self.assertIn("as of", self.replies()[0])
        cache.record_failure(self.repo.state, "unreachable", self.now, identity=identity())
        self.say("till report", sender=self.G, chat=self.GCHAT)
        self.assertIn("I can't reach the till", self.replies()[0])
        self.now += timedelta(days=2)
        self.say("till report", sender=self.G, chat=self.GCHAT)
        text = self.replies()[0]
        self.assertIn("will not quote a count that old", text)
        self.assertNotIn("sold out", text)
        seed(self.repo.state, block={**BLOCK, "merchantId": "FAKEMERCH0002"})
        self.say("till report", sender=self.G, chat=self.GCHAT)
        self.assertIn("haven't been able to read", self.replies()[0])
        seed(self.repo.state, now=self.now)
        (self.repo.wt / "hass/content/products.json").write_text("bad")
        self.say("till report", sender=self.G, chat=self.GCHAT)
        self.assertEqual(self.replies(), ["I couldn't compare the till with the website. Nothing changed."])


if __name__ == "__main__":
    unittest.main()
