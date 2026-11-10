"""HASS-CLOVER-2: `hass/clover/cli.py check | sync | status` against recorded fixtures only. No network: every socket entry point is
patched, and the one test that uses the REAL transport proves it tried to connect to the allow-listed host and was stopped by the patch.
Only a FAKE token and the fake merchant FAKEMERCH0001 are used.
Run: python3 -B -m unittest hass.tests.test_clover_cli
"""
import contextlib
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass.clover import cache, cli
from hass.clover import client as cl
from hass.clover.credential import Token
from hass.clover.transport import ReplayTransport
from hass.tests.test_clover_client import FAKE_TOKEN, FakeClock, NoNetwork, fixture

MID = "FAKEMERCH0001"
BASE = f"/v3/merchants/{MID}"
ITEMS = f"{BASE}/items?expand=itemStock,categories,tags&limit=1000&offset=0"
STOCKS = f"{BASE}/item_stocks?limit=1000&offset=0"
T0 = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)
FORBIDDEN = ("order", "payment", "customer", "employee", "refund", "credit", "cash", "shift", "device", "tender", "discount", "line_item")
ALLOWED_PATH = re.compile(rf"/v3/merchants/{MID}(?:/items(?:/[A-Za-z0-9]{{1,32}})?|/item_stocks(?:/[A-Za-z0-9]{{1,32}})?|/categories)?")


def good():
    return {BASE: (200, {}, fixture("merchant.json")), f"{BASE}/items?limit=1": (200, {}, {"elements": [fixture("items.json")["elements"][0]]}),
            ITEMS: (200, {}, fixture("items.json")), STOCKS: (200, {}, fixture("item_stocks.json"))}


class CliCase(NoNetwork):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp(prefix="clover-cli-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        os.chmod(self.root, 0o700)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        self.secret_dir = self.root / "clover"
        self.secret_dir.mkdir(mode=0o700)
        self.token_file = self.secret_dir / "production-read.token"
        self.put_token()
        self.clock, self.now = FakeClock(), T0
        self.write_host()

    def put_token(self, mode=0o600):
        fd = os.open(self.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, (FAKE_TOKEN + "\n").encode())
        os.close(fd)
        os.chmod(self.token_file, mode)

    def block(self, **over):
        return {"environment": "production", "merchantId": MID, "tokenFile": str(self.token_file), "liveApproved": False, **over}

    def write_host(self, clover="default", **over):
        cfg = {"state": str(self.state), "secretFile": str(self.root / "envelope.key"), "listen": "127.0.0.1:8795", "allowedPeers": ["127.0.0.1"],
               "approvals": "hold", "runtimeCommit": "0" * 40, "interpreter": {"url": "http://127.0.0.1:11434", "model": "m"}, **over}
        if clover == "default":
            cfg["clover"] = self.block()
        elif clover is not None:
            cfg["clover"] = clover
        self.host = self.root / "host.json"
        fd = os.open(self.host, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, json.dumps(cfg).encode())
        os.close(fd)
        os.chmod(self.host, 0o600)

    def run_cli(self, *argv, transport=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv) + ["--host", str(self.host)], transport=transport, sleep=self.clock.sleep,
                            monotonic=self.clock.monotonic, clock=lambda: self.now)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, "exactly one JSON line")
        self.assertEqual(err.getvalue(), "")
        return code, json.loads(lines[0]), out.getvalue()


class CheckTests(CliCase):
    def test_check_makes_exactly_two_reads_and_prints_redacted_facts(self):
        transport = ReplayTransport(good())
        code, doc, text = self.run_cli("check", transport=transport)
        self.assertEqual(code, 0)
        self.assertEqual(doc, {"result": "ok", "environment": "production", "merchantId": MID, "readOnly": True, "tokenFileOk": True,
                               "merchant": "2xx", "merchantMatches": True, "items": "2xx", "itemsOnPage": 1, "itemCount": None,
                               "elapsedMs": doc["elapsedMs"], "tokenAccepted": True})
        self.assertIsInstance(doc["elapsedMs"], int)
        self.assertEqual([r.url for r in transport.seen], [f"https://api.clover.com{BASE}", f"https://api.clover.com{BASE}/items?limit=1"])
        self.assertTrue(all(r.method == "GET" and r.body is None for r in transport.seen))
        self.assertEqual(transport.seen[0].headers["Authorization"], "Bearer " + FAKE_TOKEN)    # only the transport ever sees it
        for secret in (FAKE_TOKEN, "Bearer", "Authorization", "Sunshine", "1250", "12.50", "Fake Test Shop", str(self.token_file), "AS-PAN"):
            self.assertNotIn(secret, text)
        self.assertFalse(cache.path_for(self.state).exists())          # check writes nothing

    def test_a_reported_item_count_is_shown(self):
        recorded = {**good(), f"{BASE}/items?limit=1": (200, {}, {"elements": [{"id": "FAKEITEM00001"}], "count": 6})}
        self.assertEqual(self.run_cli("check", transport=ReplayTransport(recorded))[1]["itemCount"], 6)

    def test_refused_key_unreachable_and_a_merchant_read_without_permission(self):
        auth = {BASE: (401, {}, {"message": "x"}), f"{BASE}/items?limit=1": (401, {}, {"message": "x"})}
        code, doc, _ = self.run_cli("check", transport=ReplayTransport(auth))
        self.assertEqual((code, doc["result"], doc["merchant"], doc["items"], doc["tokenAccepted"]), (1, "failed", "4xx", "4xx", False))
        partial = {**good(), BASE: (403, {}, {"message": "x"})}
        code, doc, _ = self.run_cli("check", transport=ReplayTransport(partial))
        self.assertEqual((code, doc["result"], doc["merchant"], doc["merchantMatches"], doc["tokenAccepted"]), (0, "ok", "4xx", None, True))

        def down(request):
            raise OSError(f"connect failed with {request.headers['Authorization']}")
        code, doc, text = self.run_cli("check", transport=down)
        self.assertEqual((code, doc["merchant"], doc["items"], doc["tokenAccepted"]), (1, "unreachable", "unreachable", None))
        self.assertNotIn(FAKE_TOKEN, text)

    def test_token_file_problems_are_one_word_and_never_the_path(self):
        for mode, word in ((0o644, "mode"), (0o640, "mode")):
            self.put_token(mode)
            code, doc, text = self.run_cli("check", transport=ReplayTransport(good()))
            self.assertEqual((code, doc), (2, {"result": "token", "problem": word, "tokenFileOk": False}))
            self.assertNotIn(str(self.secret_dir), text)
        os.unlink(self.token_file)
        self.assertEqual(self.run_cli("check", transport=ReplayTransport(good()))[1]["problem"], "missing")

    def test_not_configured_and_a_bad_block(self):
        self.write_host(clover=None)
        self.assertEqual(self.run_cli("check")[:2], (2, {"result": "not-configured"}))
        self.write_host(clover=self.block(merchantId="../x", tokenFile="relative"))
        code, doc, text = self.run_cli("check")
        self.assertEqual((code, doc), (2, {"result": "config", "fields": ["clover.merchantId", "clover.tokenFile"]}))
        self.assertNotIn("relative", text)

    def test_the_real_transport_is_used_and_stopped_by_the_socket_patch(self):
        """No fixture: the default UrllibTransport tries api.clover.com:443 and the patched socket refuses; nothing leaves the box."""
        self.net[1].side_effect = OSError("blocked by the test")
        self.addCleanup(setattr, self, "net", [m for m in self.net if m is not self.net[1]])   # this one is meant to be called
        code, doc, text = self.run_cli("check")
        self.assertEqual((code, doc["merchant"], doc["items"]), (1, "unreachable", "unreachable"))
        hosts = {c.args[0] for c in self.net[1].call_args_list}
        self.assertEqual(hosts, {("api.clover.com", 443)})
        self.assertNotIn(FAKE_TOKEN, text)


class SyncTests(CliCase):
    def rows(self):
        db = sqlite3.connect(cache.path_for(self.state))
        self.addCleanup(db.close)
        return {r[0]: r for r in db.execute("SELECT id, name, sku, code, price_cents, category_ids, hidden, stock FROM items")}

    def test_sync_fills_the_private_cache_from_items_and_item_stocks(self):
        transport = ReplayTransport(good())
        code, doc, text = self.run_cli("sync", transport=transport)
        self.assertEqual(code, 0)
        self.assertEqual({k: doc[k] for k in ("result", "items", "counted", "skipped", "asOf")},
                         {"result": "ok", "items": 6, "counted": 5, "skipped": 0, "asOf": "2026-11-10T20:00:00+00:00"})
        self.assertEqual([r.url.split("?")[0] for r in transport.seen], [f"https://api.clover.com{BASE}/items", f"https://api.clover.com{BASE}/item_stocks"])
        rows = self.rows()
        self.assertEqual(rows["FAKEITEM00001"], ("FAKEITEM00001", "Sunshine olive oil", "AS-PAN-SUNSHINE-OLIVE-OIL-01", "0123456789012", 1250,
                                                 '["FAKECAT000001"]', 0, "11"))          # 11 from item_stocks, not the expanded 12
        self.assertEqual(rows["FAKEITEM00003"][7], "0")
        self.assertEqual(rows["FAKEITEM00004"][6], 1)
        self.assertIsNone(rows["FAKEITEM00006"][7])                                       # not counted by the merchant
        self.assertIsNone(rows["FAKEITEM00006"][4])                                       # variable price
        folder, path = cache.path_for(self.state).parent, cache.path_for(self.state)
        self.assertEqual((stat.S_IMODE(os.stat(folder).st_mode), stat.S_IMODE(os.stat(path).st_mode)), (0o700, 0o600))
        blob = path.read_bytes()
        for secret in (FAKE_TOKEN.encode(), b"Bearer", b"cost", b"defaultTaxRates"):
            self.assertNotIn(secret, blob)
        for leak in ("Sunshine", "1250", FAKE_TOKEN):
            self.assertNotIn(leak, text)
        self.assertEqual(self.run_cli("status")[1], {"result": "ok", "asOf": "2026-11-10T20:00:00+00:00", "lastAttempt": "2026-11-10T20:00:00+00:00",
                                                     "lastResult": "ok", "failures": 0, "nextAttempt": None, "itemCount": 6})

    def test_a_failing_till_keeps_the_old_items_records_the_failure_and_backs_off(self):
        self.run_cli("sync", transport=ReplayTransport(good()))
        self.now = T0 + timedelta(minutes=15)
        down = ReplayTransport({ITEMS: (503, {}, {}), STOCKS: (503, {}, {})})
        code, doc, _ = self.run_cli("sync", transport=down)
        self.assertEqual((code, doc), (1, {"result": "unreachable", "status": "5xx", "failures": 1}))
        self.assertEqual(len(down.seen), 4)                                 # the first try plus three retries, then gives up
        self.assertEqual(len(self.rows()), 6)                               # the last good pull is kept
        facts = cache.facts(self.state)
        self.assertEqual((facts["asOf"], facts["lastResult"], facts["nextAttempt"]), ("2026-11-10T20:00:00+00:00", "unreachable", "2026-11-10T20:30:00+00:00"))
        self.now = T0 + timedelta(minutes=20)
        self.assertEqual(self.run_cli("sync", transport=down)[:2], (0, {"result": "skipped", "reason": "backoff",
                                                                        "nextAttempt": "2026-11-10T20:30:00+00:00", "failures": 1}))
        self.assertEqual(len(down.seen), 4)                                 # skipped: nothing asked
        code, doc, _ = self.run_cli("sync", "--force", transport=down)
        self.assertEqual((code, doc["failures"]), (1, 2))
        self.assertEqual(cache.facts(self.state)["nextAttempt"], "2026-11-10T20:50:00+00:00")   # 30 minutes after the second failure
        self.now = T0 + timedelta(hours=1)
        self.assertEqual(self.run_cli("sync", transport=ReplayTransport(good()))[1]["result"], "ok")
        self.assertEqual(cache.facts(self.state)["failures"], 0)

    def test_rate_limit_refused_key_and_token_problems_are_recorded_as_fixed_words(self):
        limited = ReplayTransport({ITEMS: (429, {"Retry-After": "30"}, {})})
        code, doc, _ = self.run_cli("sync", transport=limited)
        self.assertEqual((code, doc["result"], doc["status"]), (1, "rate-limited", "4xx"))
        self.now += timedelta(hours=5)
        code, doc, _ = self.run_cli("sync", transport=ReplayTransport({ITEMS: (401, {}, {})}))
        self.assertEqual((code, doc["result"]), (1, "refused-key"))
        self.now += timedelta(hours=5)
        self.put_token(0o644)
        code, doc, _ = self.run_cli("sync", transport=ReplayTransport(good()))
        self.assertEqual((code, doc), (2, {"result": "token", "problem": "mode", "tokenFileOk": False, "failures": 3}))
        self.assertEqual(cache.facts(self.state)["lastResult"], "token")

    def test_the_cache_never_lands_in_the_repository_or_an_unsafe_folder(self):
        self.write_host(state=str(cli.REPO_ROOT / "hass"))
        self.assertEqual(self.run_cli("sync", transport=ReplayTransport(good()))[:2], (2, {"result": "state", "problem": "unsafe"})
                         if os.stat(cli.REPO_ROOT / "hass").st_mode & 0o077 else (2, {"result": "state", "problem": "inside-repo"}))
        self.write_host()
        os.chmod(self.state, 0o750)
        self.assertEqual(self.run_cli("sync", transport=ReplayTransport(good()))[:2], (2, {"result": "state", "problem": "unsafe"}))
        os.chmod(self.state, 0o700)
        (self.state / "clover").mkdir(mode=0o755)
        os.chmod(self.state / "clover", 0o755)
        self.assertEqual(self.run_cli("sync", transport=ReplayTransport(good()))[:2], (2, {"result": "cache", "problem": "unsafe"}))

    def test_status_with_no_cache(self):
        self.assertEqual(self.run_cli("status")[:2], (0, {"result": "no-cache"}))


class AllowListTests(CliCase):
    """The hard rule: only the merchant's basic record, items, item stocks and categories can ever be asked for."""

    def test_the_allow_list_is_exactly_the_four_read_families(self):
        self.assertEqual(cl.READ_PATH_TEXT, ("", "/items", rf"/items/{cl.ID}", "/item_stocks", rf"/item_stocks/{cl.ID}", "/categories"))
        self.assertEqual(cl.READ_METHODS, frozenset({"GET"}))
        for pattern in cl.READ_PATH_TEXT:
            for word in FORBIDDEN:
                self.assertNotIn(word, pattern)
        client = cl.CloverClient(MID, Token(FAKE_TOKEN), ReplayTransport({}), "production")
        for path in ("/orders", "/orders/A1", "/payments", "/customers", "/customers/A1", "/employees", "/employees/A1/shifts", "/refunds",
                     "/credits", "/cash_events", "/devices", "/tenders", "/discounts", "/line_items", "/opportunities", "/tags", "/properties",
                     "/address", "/items/A1/orders", "/item_stocks/A1/history", "/categories/A1/items", "/v3/merchants/OTHER0001/items"):
            with self.subTest(path=path), self.assertRaises(cl.CloverRefused):
                client.build("GET", path, {})
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            with self.assertRaises(cl.CloverRefused):
                client.build(method, "/items", {})

    def test_check_and_sync_never_call_a_forbidden_path(self):
        seen = []

        def recording(request):
            seen.append(request)
            return ReplayTransport(good())(request)
        self.run_cli("check", transport=recording)
        self.run_cli("sync", "--force", transport=recording)
        self.assertEqual(len(seen), 4)
        for request in seen:
            path = request.url.split("?")[0].removeprefix("https://api.clover.com")
            self.assertRegex(path, ALLOWED_PATH)
            self.assertEqual((request.method, request.body), ("GET", None))
            for word in FORBIDDEN:
                self.assertNotIn(word, request.url.lower())

    def test_a_client_asked_for_a_forbidden_path_sends_nothing(self):
        seen = []
        client = cl.CloverClient(MID, Token(FAKE_TOKEN), seen.append, "production", min_interval=0)
        with self.assertRaises(cl.CloverRefused):
            client._get("/orders", {})
        self.assertEqual(seen, [])


class LeakTests(CliCase):
    """The fake token never appears in any log record, error, repr or output, on every path, including a transport whose error names it."""

    def test_the_token_never_appears_anywhere(self):
        records = []
        handler = logging.Handler(logging.DEBUG)
        handler.emit = lambda r: records.append(r.getMessage() + repr(r.args) + str(r.exc_info))
        root = logging.getLogger()
        old = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.removeHandler, handler)
        self.addCleanup(root.setLevel, old)

        def hostile(request):
            raise RuntimeError(f"failed: Authorization: {request.headers['Authorization']} url={request.url}")
        texts = []
        for argv, transport in ((("check",), ReplayTransport(good())), (("sync",), ReplayTransport(good())), (("check",), hostile),
                                (("sync", "--force"), hostile), (("check",), ReplayTransport({BASE: (401, {}, {}), f"{BASE}/items?limit=1": (401, {}, {})})),
                                (("sync", "--force"), ReplayTransport({ITEMS: (500, {}, {"message": FAKE_TOKEN})})), (("status",), None)):
            texts.append(self.run_cli(*argv, transport=transport)[2])
        token = cli._token(cli.from_settings(self.block()))
        client = cli._client(cli.from_settings(self.block()), token, hostile, self.clock.sleep, self.clock.monotonic)
        texts += [repr(token), str(token), f"{token}", repr(client), repr(client.build("GET", "/items", {})),
                  repr(cli.from_settings(self.block()))]
        try:
            client.list_items()
        except cl.CloverError as exc:
            texts += [str(exc), repr(exc), repr(exc.args)]
        blob = "\n".join(texts + records) + cache.path_for(self.state).read_bytes().decode("latin-1")
        self.assertGreater(len(records), 0)
        self.assertNotIn(FAKE_TOKEN, blob)
        self.assertNotIn("Bearer FAKE", blob)


if __name__ == "__main__":
    unittest.main()
