"""Offline dry-run contracts; no requests other than fixture reads reach transport."""
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict
from unittest import mock

from hass.clover import chat, credential, drafts
from hass.clover.client import HOSTS, CloverClient, CloverRefused, CloverWriteClient, Response
from hass.clover.config import from_settings
from hass.clover.dryrun import DryRunEngine, DryRunWriteClient, make_client_factory
from hass.clover.mapper import parse_item
from hass.tests.test_clover_client import FAKE_TOKEN, MID, NoNetwork


class Owner(TypedDict):
    sender: str
    chat: str


class ApprovalArgs(Owner, total=False):
    edited: bool
    reaction: bool
    group: bool


OWNER: Owner = {"sender": "fixture-owner", "chat": "fixture-private"}
OTHER_OWNER: Owner = {"sender": "fixture-co-owner", "chat": "fixture-other-private"}
ITEM_ID = "FAKEITEM"


class DryRunTests(NoNetwork):
    def setUp(self):
        super().setUp()
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name)
        self.read_path = self.state / "fake-read"
        self.read_path.touch(mode=0o600)
        self.read_path.write_text(FAKE_TOKEN, encoding="ascii")
        self.config = from_settings({"environment": "sandbox", "merchantId": MID, "tokenFile": str(self.read_path),
                                     "dailyWriteCap": 1, "categoryMap": {"pantry": "Fixture category"}})
        self.item = {"id": ITEM_ID, "name": "Fixture item", "price": 123, "priceType": "FIXED",
                     "modifiedTime": 1, "itemStock": {"quantity": 3, "modifiedTime": 1}}
        self.seen = []
        self.now = 1_800_000_000
        self.enterContext(mock.patch.dict(HOSTS, sandbox="https://till.invalid"))

    def transport(self, request):
        path = request.url.split("?", 1)[0].removeprefix(f"https://till.invalid/v3/merchants/{MID}")
        self.seen.append((request.method, path))
        if request.method != "GET":
            self.fail("non-read reached the transport")
        body = self.item if path == f"/items/{ITEM_ID}" else {"elements": []}
        return Response(200, body=json.dumps(body).encode())

    def dry_client(self, token):
        return DryRunWriteClient(CloverClient(MID, token, self.transport, min_interval=0))

    def engine(self, factory=None):
        return DryRunEngine(self.state, self.config, factory or self.dry_client, clock=lambda: self.now,
                            mike=(OWNER["sender"], OWNER["chat"]), g=(OTHER_OWNER["sender"], OTHER_OWNER["chat"]), g_is_owner=True)

    def test_c1_write_never_sent(self):
        # C1: a wrapper could accidentally call the live write path, accept a
        # non-allowlisted path, or simulate reads instead of delegating them.
        client = self.dry_client(credential.Token(FAKE_TOKEN))
        self.assertEqual(client.get_item(ITEM_ID), self.item)
        self.assertEqual(client.list_items(modified_since_ms=1), [])
        requests = [
            ("POST", "/items", {"name": "Fixture item"}),
            ("POST", f"/items/{ITEM_ID}", {"hidden": True}),
            ("POST", "/category_items", {"elements": []}),
            ("PUT", f"/item_stocks/{ITEM_ID}", {"quantity": 7}),
        ]
        for method, path, body in requests:
            with self.subTest(method=method, path=path):
                reply = client.write(method, path, body)
                if path == "/items":
                    self.assertEqual(set(reply), {"id"})
                    self.assertRegex(reply["id"], r"^DRYRUN[0-9]{6}$")
                else:
                    self.assertEqual(reply, {})
        for method, path in (("POST", "/orders"), ("PUT", "/items"), ("GET", "/items"),
                             ("POST", "/items/X/../orders"), ("PUT", "/item_stocks/{newItemId}")):
            with self.subTest(method=method, path=path), self.assertRaises(CloverRefused):
                client.write(method, path, {})
        with self.assertRaises(ValueError):
            client.write("POST", "/items", {"price": float("nan")})
        self.assertEqual(client.requests, [{"method": m, "path": p, "json": b} for m, p, b in requests])
        self.assertEqual(self.seen, [("GET", f"/items/{ITEM_ID}"), ("GET", "/items")])

    def test_c2_engine_dry_run_settles(self):
        # C2: skipping approval/stale checks, classifying rehearsal as applied,
        # or setting a cap day would admit a bad yes, undo, or exhaust the cap.
        engine = self.engine()
        self.assertIsInstance(engine, chat.BundleEngine)
        draft = drafts.build_set_stock(parse_item(self.item), 7, self.config)
        code, preview = engine.offer(draft, **OWNER)
        self.assertEqual(preview, draft.render(code))
        yes = "yes " + code
        rejected: list[tuple[str, ApprovalArgs]] = [
            ("yes", {**OWNER}), ("yes bad-code", {**OWNER}), (yes, {**OWNER, "sender": "fixture-stranger"}),
            (yes, {**OWNER, "chat": "fixture-wrong-private"}), (yes, {**OTHER_OWNER}),
            (yes, {**OWNER, "edited": True}), (yes, {**OWNER, "reaction": True}), (yes, {**OWNER, "group": True}),
        ]
        for text, args in rejected:
            with self.subTest(text=text, args=args), self.assertRaises(drafts.DraftRefused):
                engine.handle(text, **args)
        self.now += 600
        with self.assertRaisesRegex(drafts.DraftRefused, "current till approval code"):
            engine.handle(yes, **OWNER)
        code, _ = engine.offer(draft, **OWNER)
        yes = "yes " + code
        self.assertEqual(engine.handle("stop changes", **OWNER), "Till changes are paused.")
        with self.assertRaisesRegex(drafts.DraftRefused, "paused"):
            engine.handle(yes, **OWNER)
        with engine.journal.locked() as db:
            db.execute("UPDATE meta SET k='fixture-resumed' WHERE k='paused'")
        self.assertEqual(self.seen, [])
        self.assertEqual(engine.handle(yes, **OWNER), "dry-run")
        with engine.journal.locked() as db:
            row = db.execute("SELECT status, day, result FROM changes WHERE code=?", (code,)).fetchone()
        self.assertEqual((row["status"], row["day"], json.loads(row["result"])),
                         ("dry-run", None, [{"method": "PUT", "path": f"/item_stocks/{ITEM_ID}", "json": {"quantity": 7}}]))
        with self.assertRaisesRegex(drafts.DraftRefused, "current till approval code"):
            engine.handle(yes, **OWNER)
        with self.assertRaisesRegex(drafts.DraftRefused, "nothing to undo"):
            engine.undo(code, **OWNER)
        self.assertEqual(self.seen, [("GET", f"/items/{ITEM_ID}")])

        stale, _ = engine.offer(draft, **OWNER)  # same day and cap of one
        self.item["itemStock"]["modifiedTime"] += 1
        with self.assertRaisesRegex(drafts.DraftRefused, "fresh draft"):
            engine.handle("yes " + stale, **OWNER)
        self.assertEqual(self.seen, [("GET", f"/items/{ITEM_ID}")] * 2)
        self.assertEqual(self.item["itemStock"]["quantity"], 3)
        with engine.journal.locked() as db:
            self.assertEqual(tuple(db.execute("SELECT status, result FROM changes WHERE code=?", (stale,)).fetchone()),
                             ("failed", "null"))
        create = drafts.build_create_item("Fixture new item", 432, "pantry", [], self.config,
                                         categories=[("FAKECATEGORY", "Fixture category")])
        new, _ = engine.offer(create, **OTHER_OWNER)
        self.assertEqual(engine.handle("yes " + new, **OTHER_OWNER), "dry-run")
        with engine.journal.locked() as db:
            recorded = json.loads(db.execute("SELECT result FROM changes WHERE code=?", (new,)).fetchone()[0])
        self.assertEqual(recorded[0], create.requests[0])
        self.assertEqual(recorded[1]["path"], "/category_items")
        self.assertRegex(recorded[1]["json"]["elements"][0]["item"]["id"], r"^DRYRUN[0-9]{6}$")
        self.assertEqual(self.seen[-1], ("GET", "/items"))

        waiting, _ = engine.offer(draft, **OWNER)
        with engine.journal.locked() as db:
            db.execute("INSERT INTO changes SELECT 'fixture-live', draft, sender, chat, expires, 'intent', ?, NULL "
                       "FROM changes WHERE code=?", (engine._day(), code))
        before = list(self.seen)
        with self.assertRaisesRegex(drafts.DraftRefused, "daily limit"):
            engine.handle("yes " + waiting, **OWNER)
        with self.assertRaisesRegex(drafts.DraftRefused, "daily limit"):
            engine.offer(draft, **OWNER)
        self.assertEqual(self.seen, before)

    def test_c3_no_write_token(self):
        # C3: inheriting ApplyEngine._client could require live flags or load
        # the write credential instead of passing only the read token.
        token = credential.Token(FAKE_TOKEN)
        factory = mock.Mock(wraps=self.dry_client)
        with (mock.patch.object(credential, "load_write_token", side_effect=AssertionError("write token loaded")) as write,
              mock.patch("hass.clover.apply.load_write_token", side_effect=AssertionError("write token loaded")) as alias,
              mock.patch.object(credential, "load_token", return_value=token) as read):
            engine = self.engine(factory)
            self.assertFalse(self.config.writes_allowed)
            code, _ = engine.offer(drafts.build_set_stock(parse_item(self.item), 7, self.config), **OWNER)
            self.assertEqual(engine.handle("yes " + code, **OWNER), "dry-run")
            read.assert_called_once_with(str(self.read_path))
            factory.assert_called_once_with(token)
            write.assert_not_called()
            alias.assert_not_called()

    def test_c4_default_is_dry_run(self):
        # C4: a factory default could enable a sending client, or explicit
        # live mode could skip one of the three existing write conditions.
        token = credential.Token(FAKE_TOKEN)
        loader = mock.Mock(return_value=token)
        live = replace(self.config, live_approved=True, writes=True, write_token_file=str(self.state / "fake-write"))
        with mock.patch("hass.clover.dryrun.UrllibTransport", return_value=self.transport):
            default = make_client_factory(live, loader)()
            self.assertIsInstance(default, DryRunWriteClient)
            loader.assert_called_once_with(str(self.read_path))
            self.assertRegex(default.write("POST", "/items", {})["id"], r"^DRYRUN[0-9]{6}$")
            for config in (replace(live, writes=False), replace(live, live_approved=False),
                           replace(live, write_token_file=""), replace(live, write_token_file=live.token_file)):
                with self.subTest(config=config.writes_allowed), self.assertRaises(drafts.DraftRefused) as refused:
                    make_client_factory(config, loader, dry_run=False)
                self.assertEqual(str(refused.exception), chat.WRITE_REPLY)
            factory = make_client_factory(live, loader, dry_run=False)
            self.assertIsInstance(factory(credential.Token(FAKE_TOKEN)), CloverWriteClient)
            loader.assert_called_once_with(str(self.read_path))
            self.assertEqual(self.seen, [])
