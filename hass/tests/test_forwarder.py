"""HASS-FWD-1: synthetic UNVERIFIED BlueBubbles REST fixtures; no real Mac or messages."""
import contextlib, copy, http.client, io, json, os, plistlib, subprocess, sys, tempfile, threading, unittest  # noqa: E401
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from hass import bridge, relay
from hass.tests import test_host as host_tests
from hass.tests.test_bridge import OWNER_CHAT, event
from mac import hass_forwarder as fwd

ROOT = Path(__file__).resolve().parents[2]
NOW = 1793638800
KEY = b"c" * 32


class Sender:
    def __init__(self): self.calls, self.fail = [], False
    def send(self, chat, text, attachments=()):
        if self.fail: raise bridge.BridgeError("transport-error")
        self.calls.append((chat, text, attachments))


class ForwarderCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o700)
        for name, data in (("key", KEY.hex()), ("token", "ab" * 32), ("password", "synthetic-not-a-real-password")):
            p = self.root / name
            p.write_text(data)
            p.chmod(0o600)
        self.cfg = dict(ownerChat=OWNER_CHAT, receiverUrl="http://127.0.0.1:8795", bbPort=1234,
                        bbPasswordFile=str(self.root / "password"), secretFile=str(self.root / "key"),
                        webhookTokenFile=str(self.root / "token"), spoolDir=str(self.root), webhookPort=8796)
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps(self.cfg))
        self.config.chmod(0o600)
        self.now = NOW
        self.spool = fwd.Spool(self.root, self.now)
        self.addCleanup(self.spool.db.close)
        self.sender, self.calls, self.posts, self.acks = Sender(), [], [], []
        self.messages, self.query, self.items = {}, [], []
        self.result, self.offline, self.fetch_fail, self.ack_fail = "queued", False, False, False
        self.f = fwd.Forwarder(self.cfg, self.spool, lambda: self.now, self.transport, self.sender)

    def transport(self, url, body=None):
        u = urlsplit(url)
        self.calls.append((u.path, body))
        if u.path.startswith("/api/v1/"):
            self.assertEqual(parse_qs(u.query)["password"], ["synthetic-not-a-real-password"])
            if self.fetch_fail: raise bridge.BridgeError("transport-error")
            if u.path.endswith("/query"): return {"data": copy.deepcopy(self.query)}
            self.assertEqual(parse_qs(u.query)["with"], ["chats,handle,attachment"])
            return {"data": copy.deepcopy(self.messages[u.path.rsplit("/", 1)[1]])}
        if self.offline: raise bridge.BridgeError("transport-error")
        if u.path == "/v1/inbound":
            self.posts.append(body)
            bridge.unseal(body, KEY, now=self.now, seen=set())
            return {"result": self.result}
        req = relay.unseal_control(body, KEY, now=self.now, seen=set())
        if req["op"] == "ack":
            if self.ack_fail: raise bridge.BridgeError("transport-error")
            self.acks.extend(req["ids"])
            out = {"op": "acked", "ids": req["ids"]}
        else: out = {"op": "replies", "items": self.items}
        return relay.seal_control(out, KEY, nonce=os.urandom(16).hex(), now=self.now)

    def message(self, guid="m1", **over):
        msg = json.loads((ROOT / "hass/tests/fixtures/bridge/bb-message-refetch.json").read_text())["data"]
        msg.update(guid=guid, dateCreated=int(self.now * 1000), **over)
        self.messages[guid] = msg
        return msg

    def enqueue(self, guid="m1", **over):
        self.message(guid, **over)
        self.spool.doorbell({"type": "new-message", "data": {"guid": guid, "text": "untrusted"}}, self.now)
        self.f.fetch()

    def pending(self): return self.spool.status()["pending"]


class DeliveryTests(ForwarderCase):
    def test_refetch_wins_dedupe_and_payload_erased(self):
        self.enqueue(text="trusted refetch")
        self.f.deliver()
        self.enqueue(text="trusted refetch")
        self.f.deliver()
        self.assertEqual([e["body"]["text"] for e in self.posts], ["trusted refetch"])
        self.assertEqual(self.spool.db.execute("SELECT state,payload FROM inbound").fetchall(), [("done", None)])
        self.assertEqual(self.spool.status()["done"], 1)

    def test_stranger_group_receipt_and_malformed_never_stored_or_posted(self):
        self.enqueue("stranger", chats=[{"guid": "iMessage;-;stranger@example.invalid"}], text="private stranger")
        self.enqueue("group", chats=[{"guid": "iMessage;+;group"}], text="private group")
        self.message("receipt")
        self.spool.doorbell({"type": "updated-message", "data": {"guid": "receipt"}}, self.now)
        self.f.fetch()
        self.messages["bad"] = {"guid": "bad", "text": "private malformed"}
        self.spool.doorbell({"type": "new-message", "data": {"guid": "bad"}}, self.now)
        self.f.fetch()
        self.f.deliver()
        self.assertEqual((self.pending(), self.posts, self.spool.status()["dropped_events"]), (0, [], 4))
        dump = "\n".join(self.spool.db.iterdump())
        for private in ("private stranger", "private group", "private malformed"):
            self.assertNotIn(private, dump)

    def test_fetch_retries_without_blocking_doorbell_and_preserves_fifo(self):
        self.message("first")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "first"}}, self.now)
        self.fetch_fail = True
        self.f.fetch()
        self.assertEqual(self.spool.status()["pending_fetch"], 1)
        self.now += 1
        self.message("second")
        self.spool.accept({"type": "new-message", "data": self.messages["second"]}, OWNER_CHAT, self.now)
        self.f.deliver()
        self.assertEqual(self.posts, [])
        self.now += 5
        self.fetch_fail = False
        self.f.fetch()
        self.f.deliver()
        self.f.deliver()
        self.assertEqual([e["body"]["provider_id"] for e in self.posts], ["first", "second"])

    def test_receiver_outage_fifo_one_notice_and_reset(self):
        self.enqueue("first")
        self.now += 1
        self.enqueue("second")
        self.offline = True
        for seconds in (1, 10, 40, 100, 301, 601, 901):
            self.now = NOW + seconds
            self.f.deliver()
        self.assertEqual((self.pending(), len(self.sender.calls)), (2, 1))
        self.assertEqual(self.sender.calls[0], (OWNER_CHAT, fwd.NOTICE, ()))
        self.offline = False
        self.now += 301
        self.f.deliver()
        self.f.deliver()
        self.assertEqual([e["body"]["provider_id"] for e in self.posts], ["first", "second"])
        self.assertEqual((self.pending(), self.spool.get("outage_notified")), (0, 0))
        self.enqueue("third")
        self.offline = True
        self.now += 601
        self.f.deliver()
        self.assertEqual(len(self.sender.calls), 2)

    def test_rejected_retries_fresh_seal_and_keeps_provider_time(self):
        self.enqueue()
        self.result = "rejected"
        self.f.deliver()
        self.assertEqual((self.pending(), self.spool.get("last_rejected")), (1, NOW))
        self.now += 59
        self.f.deliver()
        self.assertEqual(len(self.posts), 1)
        self.now += 3601
        self.result = "duplicate"
        self.f.deliver()
        self.assertEqual((self.pending(), len(self.posts)), (0, 2))
        self.assertNotEqual(self.posts[0]["nonce"], self.posts[1]["nonce"])
        self.assertEqual(self.posts[0]["body"]["received_at"], self.posts[1]["body"]["received_at"])
        self.assertEqual(self.posts[1]["ts"], self.now)
        for result in ("queued", "duplicate", "history"):
            self.enqueue(result)
            self.result = result
            self.f.deliver()
            self.assertEqual(self.pending(), 0)

    def test_catch_up_sleep_dedupe_no_history_and_persistent_start(self):
        self.query = [self.message("old", dateEdited=0), *json.loads((ROOT / "hass/tests/fixtures/bridge/bb-message-query.json").read_text())["data"]]
        self.message("missed")
        self.query[0]["dateCreated"] = (NOW - 1) * 1000
        self.now += 3600
        self.f.catch_up()
        query = self.calls[0][1]
        self.assertEqual((query["after"], query["limit"], query["chatGuid"]), (NOW * 1000, 50, OWNER_CHAT))
        self.spool.doorbell({"type": "new-message", "data": {"guid": "missed"}}, self.now)
        self.f.fetch()
        self.f.deliver()
        self.assertEqual([e["body"]["provider_id"] for e in self.posts], ["missed"])
        restarted = fwd.Spool(self.root, self.now)
        self.addCleanup(restarted.db.close)
        self.assertEqual(restarted.get("start_ms"), NOW * 1000)
        self.assertEqual(restarted.status()["done"], 1)

    def test_catch_up_paginates_timestamp_ties_without_advancing_on_failure(self):
        self.query = [self.message(str(n)) for n in range(50)]
        self.f.catch_up()
        self.assertEqual(self.f.query_offset, 50)
        self.fetch_fail = True
        with self.assertRaises(bridge.BridgeError): self.f.catch_up()
        self.assertEqual(self.spool.get("last_seen_ms"), NOW * 1000)
        self.fetch_fail = False
        self.query = [self.message("last")]
        self.f.catch_up()
        self.assertEqual(self.calls[-1][1]["offset"], 50)
        self.assertEqual((self.pending(), self.f.query_offset), (51, 0))

    def test_reply_lost_ack_reopen_wrong_chat_and_send_failure(self):
        self.items = [{"id": 1, "chat": OWNER_CHAT, "text": "reply", "pictures": 1},
                      {"id": 2, "chat": "iMessage;-;other@example.invalid", "text": "refuse", "pictures": 0}]
        self.ack_fail = True
        with self.assertRaises(bridge.BridgeError): self.f.pull()
        self.assertEqual(len(self.sender.calls), 1)
        self.ack_fail = False
        reopened = fwd.Spool(self.root, self.now)
        self.addCleanup(reopened.db.close)
        restarted = fwd.Forwarder(self.cfg, reopened, lambda: self.now, self.transport, self.sender)
        restarted.pull()
        self.assertEqual((len(self.sender.calls), self.acks), (1, [1]))
        self.assertEqual(self.sender.calls[0], (OWNER_CHAT, "reply", (None,)))
        self.items = [{"id": 3, "chat": OWNER_CHAT, "text": "retry", "pictures": 0}]
        self.sender.fail = True
        with self.assertRaises(bridge.BridgeError): restarted.pull()
        self.assertEqual(self.acks, [1])
        self.sender.fail = False
        restarted.pull()
        self.assertEqual(self.acks, [1, 3])

    def test_relay_bad_mac_expired_replayed_are_not_sent(self):
        for kind in ("mac", "stale", "replay"):
            env = relay.seal_control({"op": "replies", "items": [{"id": 1, "chat": OWNER_CHAT, "text": "private", "pictures": 0}]},
                                     KEY, nonce="ee" * 16, now=self.now - (301 if kind == "stale" else 0))
            if kind == "mac": env["mac"] = "0" * 64
            if kind == "replay": self.spool.add(env["nonce"])
            with self.subTest(kind=kind), mock.patch.object(self.f, "post", return_value=env), self.assertRaises(bridge.EnvelopeError):
                self.f.pull()
        self.assertEqual((self.sender.calls, self.acks), ([], []))


class InterfaceTests(ForwarderCase):
    def test_serve_doorbell_during_network_cycle_and_graceful_cancel(self):
        old_umask = os.umask(0o077)
        os.umask(old_umask)
        self.addCleanup(os.umask, old_umask)
        actual, callbacks, servers = fwd.Server, {}, []
        def server(cfg, spool):
            srv = actual({**cfg, "webhookPort": 0}, spool, lambda: self.now)
            servers.append(srv)
            return srv
        def cycle(ack=True):
            c = http.client.HTTPConnection(*servers[0].server_address, timeout=2)
            c.request("POST", "/bb/" + "ab" * 32, json.dumps({"type": "new-message", "data": {"guid": "queued-before-stop"}}))
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            r.read()
            c.close()
            callbacks[fwd.signal.SIGTERM]()
        worker = mock.Mock()
        worker.cycle.side_effect = cycle
        with mock.patch.object(fwd, "Server", side_effect=server), mock.patch.object(fwd, "Forwarder", return_value=worker), \
             mock.patch.object(fwd.signal, "signal", side_effect=lambda sig, cb: callbacks.update({sig: cb})):
            self.assertEqual(fwd.main(["serve", "--config", str(self.config)]), 0)
        self.assertEqual(self.spool.status()["pending_fetch"], 1)
        self.assertFalse(servers[0].socket.fileno() >= 0)

    def test_doorbell_token_size_and_unsupported(self):
        cfg = {**self.cfg, "webhookPort": 0}
        with fwd.Server(cfg, self.spool, lambda: self.now) as srv:
            self.assertEqual(srv.server_address[0], "127.0.0.1")
            srv.timeout = 2
            for path, data, expected in (("wrong", b"{}", 404), ("ab" * 32, b"x" * (fwd.MAX_BODY + 1), 413),
                                         ("ab" * 32, b"{", 400), ("ab" * 32, b'{"type":"typing"}', 200),
                                         ("ab" * 32, json.dumps({"type": "new-message", "data": {"guid": "m1", "text": "never stored"}}).encode(), 200)):
                box = []
                def post():
                    c = http.client.HTTPConnection(*srv.server_address, timeout=5)
                    c.request("POST", "/bb/" + path, data)
                    r = c.getresponse()
                    box.append(r.status)
                    r.read()
                    c.close()
                thread = threading.Thread(target=post)
                thread.start()
                srv.handle_request()
                thread.join()
                self.assertEqual(box, [expected])
            self.assertEqual(self.spool.status()["pending_fetch"], 1)
            self.assertNotIn("never stored", "\n".join(self.spool.db.iterdump()))

    def test_config_private_files_closed_keys_and_status_counts_only(self):
        self.assertEqual(fwd.load_config(self.config), self.cfg)
        for change in ({"extra": True}, {"receiverUrl": "http://example.com:8795"}, {"bbPort": True}, {"ownerChat": "iMessage;+;group"}):
            self.config.write_text(json.dumps({**self.cfg, **change}))
            with self.assertRaises(ValueError): fwd.load_config(self.config)
        self.config.write_text(json.dumps(self.cfg))
        for path in (self.config, self.root / "key", self.root / "token", self.root / "password"):
            path.chmod(0o644)
            with self.assertRaises(ValueError): fwd.load_config(self.config)
            path.chmod(0o600)
        self.enqueue()
        out = io.StringIO()
        with contextlib.redirect_stdout(out): self.assertEqual(fwd.main(["status", "--config", str(self.config)]), 0)
        self.assertTrue(all(type(v) in (int, float) for v in json.loads(out.getvalue()).values()))
        self.assertEqual(json.loads(out.getvalue())["pending"], 1)
        self.assertEqual((self.root / "spool.sqlite3").stat().st_mode & 0o777, 0o600)
        link = self.root / "link"
        link.symlink_to(self.root / "key")
        with self.assertRaises(ValueError): fwd.key_read(link)

    def test_json_transport_method_timeout_and_sanitized_failure(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data":{}}'
        with mock.patch.object(bridge._OPENER, "open", return_value=response) as op:
            fwd.request_json("http://127.0.0.1:1234/refetch")
            self.assertEqual(op.call_args.args[0].get_method(), "GET")
            fwd.request_json("http://127.0.0.1:1234/query", {"limit": 50})
            self.assertEqual((op.call_args.args[0].get_method(), op.call_args.kwargs["timeout"]), ("POST", 10))
        with mock.patch.object(bridge._OPENER, "open", side_effect=OSError("private-url-password")), self.assertRaises(bridge.BridgeError) as ctx:
            fwd.request_json("http://127.0.0.1:1234/query", {})
        self.assertNotIn("private-url-password", str(ctx.exception))

    def test_check_only_get_and_sanitized_failure(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        out = io.StringIO()
        with mock.patch.object(bridge._OPENER, "open", return_value=response) as op, contextlib.redirect_stdout(out):
            self.assertEqual(fwd.main(["check", "--config", str(self.config)]), 0)
        self.assertEqual(op.call_count, 2)
        self.assertTrue(all(isinstance(c.args[0], str) for c in op.call_args_list))  # URL-only open is GET
        with mock.patch.object(bridge._OPENER, "open", side_effect=OSError("private-url-password")), contextlib.redirect_stdout(out):
            self.assertEqual(fwd.main(["check", "--config", str(self.config)]), 2)
        self.assertNotIn("private-url-password", out.getvalue())

    def test_stdlib_only(self):
        # Inspect a fresh interpreter, not the test runner's preloaded modules.
        probe = self.root / "imports.py"
        # Linux's generated sysconfig data is stdlib but absent from stdlib_module_names.
        probe.write_text("import sys, sysconfig\nsys.path.insert(0, " + repr(str(ROOT)) + ")\nfrom mac import hass_forwarder\n"
                         "stdlib = sys.stdlib_module_names | {sysconfig._get_sysconfigdata_name()}\n"
                         "bad = [n for n in sys.modules if n.split('.')[0] not in stdlib and not n.startswith(('hass', 'mac')) and n != '__main__']\n"
                         "assert not bad, bad\n")
        p = subprocess.run([sys.executable, "-B", "-S", str(probe)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_plist_template_renders(self):
        raw = (ROOT / "mac/com.avocadoshack.hass-forwarder.plist.template").read_text()
        for key, value in (("PYTHON", "/usr/bin/python3"), ("REPO", "/private/repo"), ("CONFIG", "/private/config.json"), ("LOGDIR", "/private/log")):
            raw = raw.replace("@" + key + "@", value)
        p = plistlib.loads(raw.encode())
        self.assertEqual((p["KeepAlive"], p["Umask"], p["ThrottleInterval"]), (True, 63, 10))
        self.assertEqual(p["ProgramArguments"][1:], ["-B", "/private/repo/mac/hass_forwarder.py", "serve", "--config", "/private/config.json"])
        self.assertNotIn("password", raw.lower())


class EndToEndTests(host_tests.HostCase):
    def test_owner_webhook_to_host_draft_relay_to_bluebubbles(self):
        # Reuse fixture state/worker, not any running host or real configuration.
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name)
        path.chmod(0o700)
        key = path / "key"
        key.write_text(KEY.hex())
        key.chmod(0o600)
        spool = fwd.Spool(path, host_tests.NOW)
        self.addCleanup(spool.db.close)
        srv, work, sender = self.server(), self.worker(False), Sender()
        srv.secret = KEY
        def transport(url, body=None):
            if "/api/v1/" in url: return {"data": event("new-message")["data"]}
            status, raw = self.post(srv, urlsplit(url).path, json.dumps(body).encode())
            self.assertEqual(status, 200)
            return json.loads(raw)
        cfg = {"secretFile": key, "receiverUrl": "http://127.0.0.1:8795", "ownerChat": OWNER_CHAT, "bbPort": 1234, "bbPasswordFile": key}
        fw = fwd.Forwarder(cfg, spool, lambda: host_tests.NOW, transport, sender)
        spool.doorbell(event("new-message"), host_tests.NOW)
        fw.fetch()
        fw.deliver()
        self.assertEqual(len(self.drafts()), 0)
        work.cycle()
        fw.pull()
        self.assertEqual((len(self.drafts()), len(sender.calls), self.store.status()["waiting"]), (1, 1, 0))
        self.assertEqual(sender.calls[0][0], OWNER_CHAT)
        self.assertIn("Here's the change I'd make:", sender.calls[0][1])
        self.assertIn("Hass avocado, the description", sender.calls[0][1])


if __name__ == "__main__": unittest.main()
