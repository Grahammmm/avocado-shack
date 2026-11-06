"""HASS-RCV-1 tests: hass/host.py (serve, work, start-point, check) on fixtures: loopback sockets on port 0, temp state and
host dirs, a throwaway key, FixtureInterpreter. Run: python3 -B -m unittest hass.tests.test_host"""

import contextlib, http.client, io, json, logging, os, shutil, tempfile, threading, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import bridge, host, inbox as inbox_mod, receiver, relay
from hass.tests.test_bridge import OWNER_CHAT, event
from hass.tests.test_conversation import GROUP, OWNER, T0
from hass.tests.test_editor import DESC, _req, git
from hass.tests.test_receiver import NOW, SECRET, ReceiverTestCase

KEY_HEX = "cd" * 32


class Stop:  # a stop flag that lets Worker.run make `n` cycles
    def __init__(self, n):
        self.n, self.waits = n, []

    def is_set(self): return len(self.waits) >= self.n

    def wait(self, t): self.waits.append(t)


class HostCase(ReceiverTestCase):
    def setUp(self):
        super().setUp()
        self.hostdir = Path(tempfile.mkdtemp(prefix="hass-host-"))
        self.addCleanup(lambda: shutil.rmtree(self.hostdir, ignore_errors=True))
        self.keyfile = self.write(self.hostdir / "key", KEY_HEX.encode())
        self.store = relay.RelayStore(self.hostdir)
        self.clock = lambda: self.now
        self.builds = 0
        self.records = []
        handler = logging.Handler()
        handler.emit = self.records.append
        host.LOG.addHandler(handler)
        host.LOG.setLevel(logging.DEBUG)
        self.addCleanup(host.LOG.removeHandler, handler)

    def write(self, path, data, mode=0o600):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        os.write(fd, data)
        os.close(fd)
        os.chmod(path, mode)
        return path

    def host_json(self, **over):
        cfg = {"state": str(self.repo.state), "secretFile": str(self.keyfile), "listen": "127.0.0.1:8795",
               "allowedPeers": ["127.0.0.1"], "approvals": "hold", "runtimeCommit": "0" * 40,
               "interpreter": {"url": "http://127.0.0.1:11434", "model": "m"}, **over}
        return self.write(self.hostdir / "host.json", json.dumps({k: v for k, v in cfg.items() if v is not None}).encode())

    def server(self, peers=("127.0.0.1",), rx=None):
        cfg = host.load_host(self.host_json(listen="127.0.0.1:0", allowedPeers=list(peers)), allow_port_zero=True)
        srv = host.Server(cfg, SECRET, rx or receiver.Receiver(state=self.inbox, settings=None), self.store, self.clock)
        self.addCleanup(srv.server_close)
        return srv

    def post(self, srv, path, body=b"", method="POST", headers=None):
        box = {}

        def go():
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            box["r"] = (resp.status, resp.read())
            conn.close()
        thread = threading.Thread(target=go)
        thread.start()
        srv.handle_request()
        thread.join()
        return box["r"]

    def inbound(self, srv, raw):
        status, body = self.post(srv, "/v1/inbound", raw.encode() if isinstance(raw, str) else raw)
        return status, json.loads(body)["result"] if body else None

    def worker(self, private, build=None):
        rx = receiver.Receiver(state=self.inbox, settings=self.conv, apply=private)

        def make():
            self.builds += 1
            return self.interp
        return host.Worker(self.conv, rx, self.store, self.repo.wt, build or make, self.clock)

    def owner_says(self, text, guid, t):
        return self.seal(self.event_from("new-message", guid=guid, text=text, dateCreated=t * 1000), now=t)

    def relay_rows(self):
        return [r[0] for r in self.store.db.execute("SELECT text FROM relay ORDER BY id")]

    def draft_then_yes(self, srv, work, t, yes_guid="FAKE-YES"):
        self.inbound(srv, self.seal(self.event_from("new-message", text="hours")))
        work.cycle()
        code = self.drafts()[0]["code"]
        self.now = T0 + timedelta(seconds=t - NOW)
        out = self.inbound(srv, self.owner_says(f"yes {code}", yes_guid, t))
        work.cycle()
        return code, out


class ConfigTests(HostCase):
    def test_listen_address_policy(self):
        for listen in ("0.0.0.0:8795", "[::]:8795", "192.168.1.5:8795", "10.0.0.1:8795", "8.8.8.8:8795", "localhost:8795",
                       "127.0.0.1:0", "127.0.0.1:70000"):
            with self.subTest(listen=listen), self.assertRaises(host.HostConfigError) as ctx:
                host.load_host(self.host_json(listen=listen))
            self.assertEqual(ctx.exception.fields, ["listen"])
        for listen in ("127.0.0.1:8795", "[::1]:8795", "100.64.0.9:8795", "[fd7a:115c:a1e0::1]:8795"):
            with self.subTest(listen=listen):
                self.assertEqual(host.load_host(self.host_json(listen=listen, allowedPeers=["100.64.0.2"]))["addr"][1], 8795)
        with self.assertRaises(host.HostConfigError) as ctx:  # no peers on a Tailscale address
            host.load_host(self.host_json(listen="100.64.0.9:8795", allowedPeers=[]))
        self.assertEqual(ctx.exception.fields, ["allowedPeers"])
        self.assertEqual(host.load_host(self.host_json(allowedPeers=[]))["peers"], frozenset())  # loopback may be empty
        for bad in ({"extra": 1}, {"approvals": "yolo"}, {"runtimeCommit": "abc"}, {"previewer": "yes"}, {"interpreter": {"url": "http://8.8.8.8", "model": "m"}}):
            with self.subTest(bad=bad), self.assertRaises(host.HostConfigError):
                host.load_host(self.host_json(**bad))
        os.chmod(self.host_json(), 0o644)
        with self.assertRaises(host.HostConfigError):
            host.load_host(self.hostdir / "host.json")

    def test_live_mode_not_installed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = host.main(["check", "--host", str(self.host_json(approvals="live"))])
        self.assertEqual((code, json.loads(out.getvalue())), (2, {"result": "refused", "reason": "live release is not installed"}))

    def test_runtime_identity(self):
        ck = Path(tempfile.mkdtemp(prefix="hass-ck-"))
        self.addCleanup(lambda: shutil.rmtree(ck, ignore_errors=True))
        for args in (("init", "-q"), ("config", "user.name", "t"), ("config", "user.email", "t@example.invalid")):
            git(ck, *args)
        (ck / "f").write_text("x")
        git(ck, "add", "f")
        git(ck, "commit", "-q", "-m", "c")
        head = git(ck, "rev-parse", "HEAD")

        def run(cmd, sha, root):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = host.main([cmd, "--host", str(self.host_json(runtimeCommit=sha))], root=root)
            return code, json.loads(out.getvalue())
        self.assertEqual(run("check", head, ck), (0, {"result": "ok"}))
        for cmd in ("serve", "work", "check"):
            with self.subTest(cmd=cmd):
                self.assertEqual(run(cmd, "1" * 40, ck), (2, {"result": "runtime-mismatch"}))  # another commit
                self.assertEqual(run(cmd, git(self.repo.wt, "rev-parse", "HEAD"), self.repo.wt), (2, {"result": "runtime-mismatch"}))
        (ck / "dirty").write_text("x")
        self.assertEqual(run("check", head, ck), (2, {"result": "runtime-mismatch"}))
        os.chmod(self.keyfile, 0o644)  # the key check runs after the identity check
        (ck / "dirty").unlink()
        self.assertEqual(run("check", head, ck), (2, {"result": "secret", "code": "mode"}))

    def test_start_point_once_and_serve_work_need_it(self):
        fresh = Path(tempfile.mkdtemp(prefix="hass-state-"))
        self.addCleanup(lambda: shutil.rmtree(fresh, ignore_errors=True))
        os.chmod(fresh, 0o700)
        (fresh / "config.json").write_bytes((self.repo.state / "config.json").read_bytes())
        path = self.host_json(state=str(fresh))
        outs = []
        for argv in (["serve"], ["work"], ["start-point", "--at", "2026-11-02T17:00:00+00:00"],
                     ["start-point", "--at", "2026-11-02T17:00:00+00:00"], ["start-point", "--at", "2026-11-03T17:00:00+00:00"]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch.object(host, "runtime_problem", return_value=False):
                outs.append((host.main([*argv[:1], "--host", str(path), *argv[1:]]), json.loads(out.getvalue())["result"]))
        self.assertEqual(outs, [(2, "no-start-point")] * 2 + [(0, "ok")] * 2 + [(2, "start-point-refused")])


class ServeTests(HostCase):
    def test_inbound_queues_only_and_work_drafts(self):
        srv, work = self.server(), self.worker(False)
        self.assertEqual(self.inbound(srv, self.seal(event("new-message"))), (200, "queued"))
        self.assertEqual((self.drafts(), [r["state"] for r in self.inbound_rows()]), ([], ["pending"]))  # serve drained nothing
        work.cycle()
        self.assertEqual(len(self.drafts()), 1)
        rows = self.store.db.execute("SELECT chat, text FROM relay").fetchall()
        self.assertEqual((len(rows), rows[0][0]), (1, OWNER_CHAT))
        self.assertIn(self.drafts()[0]["code"], rows[0][1])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0], 0)

    def test_replay_bad_mac_stale_oversize_wrong_path_peer(self):
        srv, raw = self.server(), self.seal(event("new-message"))
        self.assertEqual(self.inbound(srv, raw), (200, "queued"))
        self.assertEqual(self.inbound(srv, raw), (200, "duplicate"))
        env = json.loads(self.seal(self.event_from("new-message", guid="FAKE-B")))
        env["mac"] = ("0" if env["mac"][0] != "0" else "1") + env["mac"][1:]
        self.assertEqual(self.inbound(srv, json.dumps(env)), (200, "rejected"))
        for skew in (-301, 301):
            self.assertEqual(self.inbound(srv, self.seal(self.event_from("new-message", guid="FAKE-C"), now=NOW + skew)), (200, "rejected"))
        self.assertEqual(self.post(srv, "/v1/inbound", b"x", headers={"Content-Length": str(64 * 1024 + 1)})[0], 413)
        self.assertEqual(self.post(srv, "/v1/inbound", method="GET")[0], 404)
        self.assertEqual(self.post(srv, "/v1/other", b"{}")[0], 404)
        self.assertEqual(self.post(self.server(peers=("10.0.0.9",)), "/v1/inbound", raw.encode()), (403, b""))
        self.assertEqual([r["state"] for r in self.inbound_rows()], ["pending"])  # only the first valid envelope was stored

    def test_stranger_and_group_make_no_draft_and_no_reply(self):
        srv, work = self.server(), self.worker(True)
        stranger = bridge.Inbound(provider_id="FAKE-S", chat=OWNER_CHAT, sender="stranger@example.invalid", text="desc",
                                  received_at=T0.isoformat())
        group = bridge.Inbound(provider_id="FAKE-G", chat=GROUP, sender=OWNER, text="desc", received_at=T0.isoformat())
        for n, msg in enumerate((stranger, group)):
            self.assertEqual(self.inbound(srv, json.dumps(bridge.seal(msg, SECRET, nonce=f"{n + 1:032x}", now=NOW))), (200, "queued"))
        work.cycle()
        self.assertEqual((self.drafts(), self.relay_rows()), ([], []))

    def test_relay_over_http_pulls_acks_and_refuses_replay(self):
        srv, store_id = self.server(), self.store.add(OWNER_CHAT, "hello", 0, NOW)
        pull = relay.seal_control({"type": "pull", "max": 5}, SECRET, nonce="aa" * 16, now=NOW)
        status, body = self.post(srv, "/v1/relay", json.dumps(pull).encode())
        reply = relay.unseal_control(json.loads(body), SECRET, now=NOW, seen=set())
        self.assertEqual((status, reply["items"]), (200, [{"id": store_id, "chat": OWNER_CHAT, "text": "hello", "pictures": 0}]))
        self.assertEqual(self.post(srv, "/v1/relay", json.dumps(pull).encode())[0], 400)  # replayed
        ack = relay.seal_control({"type": "ack", "ids": [store_id]}, SECRET, nonce="bb" * 16, now=NOW)
        status, body = self.post(srv, "/v1/relay", json.dumps(ack).encode())
        self.assertEqual((status, relay.unseal_control(json.loads(body), SECRET, now=NOW, seen=set())["count"]), (200, 1))
        v1 = bridge.seal(bridge.Inbound("p", "c", "s", "t", received_at="x"), SECRET, nonce="cc" * 16, now=NOW)
        self.assertEqual(self.post(srv, "/v1/relay", json.dumps(v1).encode())[0], 400)
        self.assertEqual(self.store.status(), {"waiting": 0, "total": 1})


class WorkTests(HostCase):
    def test_hold_mode_yes_is_held(self):
        srv, work = self.server(), self.worker(False)
        code, _ = self.draft_then_yes(srv, work, NOW + 5)
        self.assertEqual((self.editor.applies, self.commits(), [d["state"] for d in self.drafts()]), (0, 0, ["proposed"]))
        self.assertEqual(sum(f"{code} was not applied" in t for t in self.relay_rows()), 1)

    def test_private_mode_yes_applies_once(self):
        srv, work = self.server(), self.worker(True)
        code, out = self.draft_then_yes(srv, work, NOW + 5)
        draft = self.drafts()[0]
        self.assertEqual((out, self.editor.applies, draft["state"]), ((200, "queued"), 1, "applied"))
        self.assertEqual(git(self.repo.wt, "log", "-1", "--format=%s"), f"hass content: {draft['change_id']}")
        self.assertTrue(any(t.startswith(f"Applied {code}") for t in self.relay_rows()))
        self.assertEqual(self.inbound(srv, self.owner_says(f"yes {code}", "FAKE-YES", NOW + 5)), (200, "duplicate"))  # same provider id
        work.cycle()
        self.assertEqual((self.editor.applies, self.commits()), (1, 1))
        self.assertEqual(self.builds, 1)  # the interpreter prompt was rebuilt only when the content revision changed
        work.cycle()
        self.assertEqual(self.builds, 1)

    def test_interpreter_rebuilt_when_content_revision_changes(self):
        work = self.worker(True)
        work.cycle()
        self.assertEqual(self.builds, 0)
        self.assertEqual(self.repo.apply(self.repo.prepare(_hours())["draft"])["result"], "applied")
        work.cycle()
        work.cycle()
        self.assertEqual(self.builds, 1)

    def test_private_mode_expired_and_stale_refused(self):
        srv, work = self.server(), self.worker(True)
        code, _ = self.draft_then_yes(srv, work, NOW + 601)
        self.assertEqual((self.editor.applies, self.commits(), self.drafts()[0]["state"]), (0, 0, "expired"))
        self.assertTrue(any("expired" in t for t in self.relay_rows()))
        # stale: a hand edit lands between the proposal and the yes
        self.inbound(srv, self.owner_says("desc", "FAKE-D", NOW + 602))
        work.cycle()
        self.assertEqual(self.repo.apply(self.repo.prepare(_hours())["draft"])["result"], "applied")
        base = self.count()
        self.inbound(srv, self.owner_says("yes", "FAKE-Y2", NOW + 603))
        work.cycle()
        old, new = self.drafts()[1:]
        self.assertEqual((old["state"], old["reason"], new["state"], self.count() - base), ("rejected", "stale", "proposed", 0))
        self.assertNotEqual(old["code"], new["code"])

    def test_relay_refusal_leaves_the_outbox_row_unsent(self):
        srv, work = self.server(), self.worker(False)
        self.inbound(srv, self.seal(event("new-message")))
        work.sender.owner_chat = "someone-else"
        with self.assertRaises(relay.RelayRefused):
            work.cycle()
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0], 1)
        self.assertEqual(self.store.status()["total"], 0)

    def test_crash_between_accept_and_work_drains_once(self):
        srv, work = self.server(), self.worker(False)
        self.inbound(srv, self.seal(event("new-message")))
        with mock.patch.object(work.rx, "drain", side_effect=RuntimeError("crash")), self.assertRaises(RuntimeError):
            work.cycle()
        self.assertEqual((self.drafts(), [r["state"] for r in self.inbound_rows()]), ([], ["pending"]))
        restarted = self.worker(False)
        restarted.cycle()
        restarted.cycle()
        self.assertEqual((len(self.drafts()), len(self.relay_rows()), [r["state"] for r in self.inbound_rows()]), (1, 1, ["done"]))

    def test_logs_and_outputs_carry_no_private_text(self):
        srv, work = self.server(), self.worker(True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.inbound(srv, self.seal(event("new-message")))
            self.post(srv, "/v1/other?token=" + KEY_HEX, b"{}")
            self.post(self.server(peers=("10.0.0.9",)), "/v1/inbound", b"{}")
            with mock.patch.object(work.rx, "drain", side_effect=RuntimeError(f"{OWNER} {OWNER_CHAT} {KEY_HEX}")):
                work.run(Stop(2))
            host.main(["check", "--host", str(self.host_json(secretFile=str(self.hostdir / "nokey")))])
        seen = "\n".join([out.getvalue(), *(r.getMessage() for r in self.records)])
        for private in (OWNER, OWNER_CHAT, KEY_HEX, str(self.repo.state), str(self.hostdir), "desc", "token"):
            self.assertNotIn(private, seen)
        self.assertIn("cycle failed: RuntimeError", seen)

    def test_worker_backs_off_and_resets(self):
        work, stop = self.worker(False), Stop(4)
        with mock.patch.object(work, "cycle", side_effect=[RuntimeError(), RuntimeError(), None, RuntimeError()]):
            work.run(stop)
        self.assertEqual(stop.waits, [2, 4, 1, 2])


def _hours():
    return _req((DESC, {"id": "photo-product-001", "description": "Picked this week."}))


if __name__ == "__main__":
    unittest.main()
