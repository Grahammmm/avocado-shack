"""HASS-LINK: exact-name link suggestions, the owner's one-yes `link all`, `link X to <SKU>`, `unlink X` and `stock yes|no <code>`.
Fixtures only: the synthetic #571 till cache, a temp writer folder, a mocked stock_site.approve/decline. No token, network or editor call.
Run: python3 -m unittest discover -s hass/tests -p 'test_clover_links.py' -v
"""
import json
import stat
import types
from datetime import timedelta
from unittest import mock

from hass import conversation, editor, stock_site
from hass.clover import cache, chat, cli, links, reports
from hass.clover.config import from_settings
from hass.tests import test_stock_site as ss
from hass.tests.test_clover_chat import BLOCK, seed, strict
from hass.tests.test_clover_cli import CliCase, T0
from hass.tests.test_conversation import CHAT, OWNER, STRANGER, ConversationTestCase

GROUP = "chat-fixture;+;group"
P = lambda pid, name, status="active": {"id": pid, "name": name, "status": status}  # noqa: E731
PRODUCTS = {"products": [P("avocado", "Hass avocado"), P("oil", "Sunshine  olive OIL"), P("eggs-1", "Eggs, dozen"), P("eggs-2", "eggs, dozen"),
                         P("tomato", "Heirloom tomato"), P("lemons", "Lemons"), P("honey", "Old honey jar", "hidden")]}
STOCK = {"stk-000000000001": "open", "stk-000000000002": "stale"}


class Fixture:
    """A till cache, local products and a TillDesk that can change the till (owners only), all under a temp state."""

    def stage(self, state, wt):
        seed(state)
        (wt / "hass/content").mkdir(parents=True, exist_ok=True)
        (wt / "hass/content/products.json").write_text(json.dumps(PRODUCTS))
        (state / "config.json").write_text(json.dumps({"worktree": str(wt)}))
        engine = chat.BundleEngine(state, from_settings(BLOCK), lambda token: None, mike=(OWNER, CHAT))
        self.desk, self.wt, self.state = chat.TillDesk(str(state), BLOCK, engine=engine), wt, state

    def ask(self, text, sender=OWNER, chat=CHAT):
        intent = self.desk.parse(text)
        self.assertIsNotNone(intent, text)   # claimed by the till desk, never the interpreter
        return strict(self.desk.answer(intent, T0, sender=sender, chat=chat, worktree=lambda: self.wt))

    def links(self):
        path = self.state / "clover/links.json"
        return json.loads(path.read_text()) if path.exists() else None


class LinkTests(Fixture, CliCase):
    def setUp(self):
        super().setUp()
        self.stage(self.state, self.root / "writer")

    def suggest(self):
        code, out, stdout = self.run_cli("link", "suggest")
        self.assertEqual(code, 0)
        return out, stdout

    def test_suggest_links_exact_names_only_and_lists_the_rest_unlinked(self):
        # Contract: a looser (fuzzy, hidden-site or clashing) match is never suggested. Bug: "Heirloom tomato" joins "Heirloom tomatoes".
        snapshot, _ = cache.read(self.state, cache.identity_of(from_settings(BLOCK)))
        pairs, clashes, site_only, till_only = links.suggest(snapshot, PRODUCTS, {})
        self.assertEqual(pairs, {"avocado": {"cloverId": "FAKEITEM00002"}, "oil": {"cloverId": "FAKEITEM00001", "sku": "AS-PAN-SUNSHINE-OLIVE-OIL-01"}})
        self.assertEqual((clashes, site_only), (["Eggs, dozen (eggs-1)", "eggs, dozen (eggs-2)"], ["Heirloom tomato", "Lemons"]))
        self.assertEqual(till_only, ["Heirloom tomatoes", "Market special (ring up price)", "Old honey jar"])
        self.assertEqual(links.suggest(snapshot, PRODUCTS, {"avocado": {"cloverId": "FAKEITEM00002"}})[0].keys(), {"oil"})   # linked ones are left alone

    def test_every_one_sided_item_is_listed_and_same_name_twins_carry_their_ids(self):
        # Contract: nothing left over is silently dropped. Bug: only the first of two same-name unmatched items was listed (ps[0] / its[0]).
        till = lambda i, name, sku="": types.SimpleNamespace(id=i, name=name, sku=sku)   # noqa: E731
        snapshot = types.SimpleNamespace(items=[till("T1", "Quince", "Q-1"), till("T2", "quince"), till("T3", "Plum"), till("T4", "Fig"), till("T5", "fig")])
        content = {"products": [P("s1", "Pear"), P("s2", "pear"), P("s3", "Plum"), P("s4", "Fig"), P("s5", "Kale")]}
        pairs, clashes, site_only, till_only = links.suggest(snapshot, content, {})
        self.assertEqual(pairs, {"s3": {"cloverId": "T3"}})
        self.assertEqual(site_only, ["Kale", "Pear (s1)", "pear (s2)"])             # (a) both site-only twins, each with its product id
        self.assertEqual(till_only, ["Quince (Q-1)", "quince (T2)"])                 # (b) both till-only twins, by SKU or else item id
        self.assertEqual(clashes, ["Fig (s4)", "Fig (T4)", "fig (T5)"])            # one site product, two till items: neither is linked or lost

    def test_cli_saves_one_private_draft_and_a_private_list_and_prints_counts_only(self):
        out, stdout = self.suggest()
        self.assertEqual({k: v for k, v in out.items() if k != "code"}, {"result": "ok", "matches": 2, "sameName": 2, "siteOnly": 2, "tillOnly": 3,
                                                                          "asOf": "2026-11-10T20:00:00+00:00"})
        for name in ("avocado", "Eggs", "tomato", "Hass"):
            self.assertNotIn(name, stdout)
        folder = self.state / "clover"
        self.assertIsNone(self.links())   # a suggestion links nothing
        for path in (folder / links.DRAFT, folder / "reports/link-suggest.md"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn(f"Will link: link all {out['code']} (2)", (folder / "reports/link-suggest.md").read_text())

    def test_one_yes_writes_every_link_and_the_mismatch_report_reads_it_unchanged(self):
        # Contract: all-or-nothing under one code, in the shape reports.read_inputs already reads. Bug: only the first pair is written.
        code = self.suggest()[0]["code"]
        self.assertEqual(self.ask(f"link all {code}"), "Linked 2 website items to till items. No website word was changed.")
        self.assertEqual(sorted(self.links()), ["avocado", "oil"])
        self.assertEqual(stat.S_IMODE((self.state / "clover/links.json").stat().st_mode), 0o600)
        snapshot, _ = cache.read(self.state, cache.identity_of(from_settings(BLOCK)))
        sections = reports.till_vs_site(snapshot, *reports.read_inputs(self.state, self.wt))["sections"]
        self.assertEqual((sections["Broken links"], sections["Different names"]), ([], []))
        self.assertNotIn("Hass avocado (avocado)", sections["Site items without a till link"])
        self.assertIn("Unlinked", self.ask("unlink hass avocado"))
        self.assertEqual(sorted(self.links()), ["oil"])
        self.assertEqual(self.ask(f"link all {code}"), chat.LINK_NO["unknown"])   # the draft is spent: the same code never writes twice

    def test_a_changed_cache_or_a_changed_pair_makes_the_draft_stale_and_writes_nothing(self):
        # Bug: the code is accepted against a till or website that changed after Mike was shown the list.
        code = self.suggest()[0]["code"]
        seed(self.state, now=T0 + timedelta(minutes=15))
        self.assertEqual(self.ask(f"link all {code}"), chat.LINK_NO["stale"])
        self.assertIsNone(self.links())
        self.assertEqual(self.ask("link all 00000000"), chat.LINK_NO["unknown"])
        seed(self.state)
        code = self.suggest()[0]["code"]
        (self.wt / "hass/content/products.json").write_text(json.dumps({"products": [P("avocado", "Hass avocados"), *PRODUCTS["products"][1:]]}))
        self.assertEqual(self.ask(f"link all {code}"), chat.LINK_NO["stale"])
        self.assertIsNone(self.links())

    def test_a_wrong_sender_or_a_group_changes_nothing(self):
        code = self.suggest()[0]["code"]
        for text in (f"link all {code}", "link lemons to egg12", "unlink avocado", "stock yes stk-000000000001"):
            for sender, room in ((STRANGER, CHAT), (OWNER, GROUP), (STRANGER, GROUP)):
                with self.subTest(text=text, sender=sender, room=room), mock.patch.object(stock_site, "approve") as approve:
                    self.assertEqual(self.ask(text, sender, room), chat.NOT_OWNER)
                    approve.assert_not_called()
        self.assertIsNone(self.links())
        self.assertEqual(self.ask(f"link all {code}"), "Linked 2 website items to till items. No website word was changed.")   # the draft was not spent

    def test_link_to_a_sku_and_unlink_are_exact_and_never_touch_the_site(self):
        # Contract: linking sets no website word, so the editor is never called. Bug: a link command also publishes a stock word.
        with mock.patch.object(editor, "prepare", side_effect=AssertionError), mock.patch.object(editor, "apply", side_effect=AssertionError):
            self.assertIn("exactly one website item", self.ask("link eggs, dozen to egg12"))   # two products share that name
            self.assertEqual(self.ask("link eggs-2 to EGG12"), "Linked eggs-2 to SKU EGG12. No website word was changed.")
            self.assertEqual(self.links(), {"eggs-2": {"cloverId": "FAKEITEM00003", "sku": "EGG12"}})
            for text in ("link eggs-1 to EGG12", "link eggs-2 to AS-PAN-SUNSHINE-OLIVE-OIL-01", "link honey to egg12"):
                self.assertIn("nothing was changed", self.ask(text), text)   # a SKU taken, a product already linked, a hidden product
            self.assertIsNone(self.desk.parse("link the lemons to the hike page"))   # not a till SKU: not claimed, the usual handling goes on
            self.assertEqual(self.ask("unlink lemons"), "lemons is not linked, so nothing was changed.")
            self.assertIn("Unlinked", self.ask("unlink eggs-2"))
        self.assertEqual(self.links(), {})

    def test_help_lists_the_link_and_stock_words(self):
        for word in ("link all <code>", "unlink Sunshine olive oil", "stock yes <code>", "stock no <code>"):
            self.assertIn(word, chat.HELP)


class StockWordTests(Fixture, CliCase):
    def setUp(self):
        super().setUp()
        self.stage(self.state, self.root / "writer")
        queue = stock_site.StockSite(self.state, None, None)
        queue.data = dict(counts={}, pending={}, inflight=None, asOf="", itemCount=0, sets={code: dict(
            hash=stock_site.digest({}), words={}, approved_by=None, approved_at=None, state=state, at="2026-11-10", summary="x") for code, state in STOCK.items()})
        queue.save()

    def test_stock_yes_and_no_call_approve_and_decline_once_for_an_open_code_only(self):
        open_code = "stk-000000000001"
        with mock.patch.object(stock_site, "approve", return_value=True) as approve, mock.patch.object(stock_site, "decline", return_value=True) as decline:
            self.assertIn("will go up", self.ask(f"stock yes {open_code}"))
            self.assertIn("dropped", self.ask(f"stock no {open_code}"))
            approve.assert_called_once_with(str(self.state), open_code, "owner")
            decline.assert_called_once_with(str(self.state), open_code, "owner")
            for text in ("stock yes stk-000000000002", "stock no stk-000000000002", "stock yes stk-999999999999", "stock no nonsense"):
                self.assertEqual(self.ask(text), chat.STOCK_NO, text)   # stale and unknown codes make no call
            self.assertEqual((approve.call_count, decline.call_count), (1, 1))

    def test_a_code_already_approved_is_not_approved_twice(self):
        # Bug: a repeated yes calls approve again. The real approve is used, so the file itself shows the first one.
        self.assertIn("will go up", self.ask("stock yes stk-000000000001"))
        self.assertEqual(stock_site.StockSite(self.state, None, None).load()["sets"]["stk-000000000001"]["approved_by"], "owner")
        self.assertEqual(self.ask("stock yes stk-000000000001"), chat.STOCK_NO)


class ChatDispatch(Fixture, ConversationTestCase):
    def test_the_conversation_hands_the_link_words_to_the_desk_not_the_interpreter(self):
        with mock.patch.object(conversation.Outbox, "strict", True):
            self.stage(self.repo.state, self.repo.wt)
            self.conv.till = self.desk
            seen = []
            self.interp.interpret = lambda text, *a, **k: seen.append(text)
            for who, text in ((OWNER, "link all 00000000"), (STRANGER, "link all 00000000")):
                self.say(text, sender=who, chat=CHAT if who == OWNER else "chat-stranger")
            self.assertEqual((seen, self.replies()), ([], [chat.LINK_NO["unknown"]]))


class NewlyLinked(ss.StockCase):
    locals().update({name: None for name in dir(ss.StockCase) if name.startswith("test")})   # only this contract, not StockCase's own tests

    def test_a_link_written_by_links_py_is_new_to_stock_site_and_sets_no_word(self):
        # Contract: LINK writes the table stock_site already reads; the first read after it is "newly linked" (one preview, no release).
        pid, table = self.ids[0], links.table(self.repo.state)
        link = self.links.pop(pid)
        self.write_links()
        self.pull()
        self.runq()
        self.assertNotIn(pid, self.data()["counts"])
        self.links[pid] = link
        links.write(table, self.links)
        self.pull(**{pid: 0})
        self.assertEqual(self.runq(), "held")
        self.assertTrue(self.data()["pending"][pid]["new"])
        summary = next(iter(self.sets().values()))["summary"]
        self.assertTrue(summary.startswith("First stock sync / stock set: 1 words (1 Sold out, 0 Limited, 0 Available today)"), summary)
        self.assertEqual((self.live.calls, json.loads(self.products_path.read_text())["products"][0].get("available")), ([], "yes"))
