"""HASS-ATTACH-1: result screenshots over the sealed relay to the owner's phone. Fixtures only: in-process host, temp dirs, a
fixed clock, a fake loopback BlueBubbles transport recording multipart bodies (shapes UNVERIFIED on a real Mac)."""
import email, json, os, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from hass import bridge, bridge_attach, host, relay
from hass.tests import test_host as ht
from hass.tests.test_bridge import OWNER_CHAT
from hass.tests.test_forwarder import KEY, Sender
from mac import hass_forwarder as fwd

FIX = Path(__file__).resolve().parent / "fixtures" / "bridge"
OTHER = "iMessage;-;other@example.invalid"
PNG = relay.PNG_SIG + b"fixture-picture-one" * 5
PNG2 = relay.PNG_SIG + b"fixture-picture-two" * 7


class AttachCase(ht.HostCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o700)
        for name, data in (("key", KEY.hex()), ("password", "synthetic-not-a-real-password")):
            self.write(self.root / name, data.encode())
        self.shots = Path(self.repo.state) / "screenshots"
        self.shots.mkdir(mode=0o700, exist_ok=True)
        self.cfg = dict(ownerChat=OWNER_CHAT, receiverUrl="http://127.0.0.1:8795", bbPort=1234,
                        bbPasswordFile=str(self.root / "password"), secretFile=str(self.root / "key"))
        self.events, self.attach_fail, self.sent = [], False, []
        self.relay_sender = relay.RelaySender(self.store, OWNER_CHAT, lambda: ht.NOW, self.shots)
        self.srv = self.server()
        self.srv.secret = KEY
        self.text = Sender()
        send = self.text.send
        self.text.send = lambda chat, text, att=(): (self.events.append(("text", text, att)), send(chat, text, att))[1]
        self.attach = bridge_attach.BlueBubblesAttachmentSender("http://127.0.0.1:1234", self.root / "password", OWNER_CHAT, self.bb)
        self.start()

    def start(self):
        self.spool = fwd.Spool(self.root, self.now.timestamp())
        self.addCleanup(self.spool.db.close)
        self.f = fwd.Forwarder(self.cfg, self.spool, lambda: self.now.timestamp(), self.transport, self.text, self.attach)

    def transport(self, url, body=None):
        status, raw = self.post(self.srv, urlsplit(url).path, json.dumps(body).encode())
        if status != 200: raise bridge.BridgeError("transport-error")
        return json.loads(raw)

    def bb(self, url, body, headers, timeout):
        self.assertEqual(parse_qs(urlsplit(url).query)["password"], ["synthetic-not-a-real-password"])
        self.events.append(("png", url, body, headers, timeout))
        if self.attach_fail: raise OSError("secret-url-password-bytes")
        return json.loads((FIX / "bb-attachment-response.json").read_text())["status"]

    def shot(self, name="a.png", data=PNG):
        path = self.shots / name
        path.write_bytes(data)
        return str(path)

    def queue(self, *paths, text="done", chat=OWNER_CHAT):
        return self.relay_sender.send(chat, text, list(paths))

    def pngs(self): return [e for e in self.events if e[0] == "png"]
    def texts(self): return [e[1] for e in self.events if e[0] == "text"]
    def picture_rows(self): return self.store.db.execute("SELECT relay_id, idx, size, data IS NULL FROM picture").fetchall()

    def advance(self, seconds): self.now += timedelta(seconds=seconds)

    def multipart(self, event):
        msg = email.message_from_bytes(b"Content-Type: " + event[3]["Content-Type"].encode() + b"\r\n\r\n" + event[2])
        return {p.get_param("name", header="content-disposition"): (p.get_filename(), p.get_payload(decode=True)) for p in msg.get_payload()}

    def control(self, body, nonce):
        env = relay.seal_control(body, KEY, nonce=nonce, now=self.now)
        status, raw = self.post(self.srv, "/v1/relay", json.dumps(env).encode())
        return status, relay.unseal_control(json.loads(raw), KEY, now=self.now, seen=set()) if status == 200 else None


class HostSideTests(AttachCase):
    def test_pictures_false_is_unchanged(self):
        plain = relay.RelaySender(self.store, OWNER_CHAT, lambda: ht.NOW)
        plain.send(OWNER_CHAT, "done", [self.shot()])
        self.assertEqual((self.picture_rows(), self.store.pull(5, ht.NOW)), ([], [{"id": 1, "chat": OWNER_CHAT, "text": "done", "pictures": 1}]))
        self.assertFalse(host.load_host(self.host_json())["pictures"])
        self.assertTrue(host.load_host(self.host_json(pictures=True))["pictures"])
        with self.assertRaises(host.HostConfigError): host.load_host(self.host_json(pictures="yes"))

    def test_refused_attachments_are_counted_for_the_note(self):
        outside = Path(self.root / "outside.png")
        outside.write_bytes(PNG)
        link = self.shots / "link.png"
        link.symlink_to(outside)
        (self.root / "real").mkdir()
        (self.root / "real" / "a.png").write_bytes(PNG)
        (self.root / "dirlink").symlink_to(self.root / "real")
        for label, sender, paths in (
                ("outside", self.relay_sender, [str(outside)]), ("dotdot", self.relay_sender, [str(self.shots / ".." / "outside.png")]),
                ("symlinked file", self.relay_sender, [str(link)]),
                ("symlinked dir", relay.RelaySender(self.store, OWNER_CHAT, lambda: 1, self.root / "dirlink"), [str(self.root / "dirlink" / "a.png")]),
                ("non-png", self.relay_sender, [self.shot("b.png", b"GIF89a" + b"x" * 20)]), ("empty", self.relay_sender, [self.shot("c.png", b"")]),
                ("too big", self.relay_sender, [self.shot("d.png", relay.PNG_SIG + b"\0" * (relay.MAX_PNG - 7))]),
                ("missing", self.relay_sender, [str(self.shots / "nope.png")])):
            with self.subTest(label):
                before = len(self.picture_rows())
                sender.send(OWNER_CHAT, "t", paths)
                self.assertEqual(len(self.picture_rows()), before)
                self.assertEqual(self.store.db.execute("SELECT pictures FROM relay ORDER BY id DESC").fetchone()[0], 1)
        exact = self.shot("e.png", relay.PNG_SIG + b"\0" * (relay.MAX_PNG - 8))
        self.queue(exact)  # exactly 1.5 MiB is accepted
        self.assertEqual(self.picture_rows()[-1][2], relay.MAX_PNG)
        self.queue(self.shot("1.png"), self.shot("2.png", PNG2), self.shot("3.png"))
        item = self.store.pull(100, ht.NOW)[-1]
        self.assertEqual((item["pictures"], [s["idx"] for s in item["shots"]]), (1, [0, 1]))
        with self.assertRaises(relay.RelayRefused): self.queue(self.shot(), chat=OTHER)

    def test_picture_request_gone_rate_limit_and_retention(self):
        self.queue(self.shot())
        self.store.pull(5, ht.NOW)
        req = lambda n, rid=1, idx=0: self.control({"op": "picture", "id": rid, "idx": idx}, f"{n:032x}")[1]  # noqa: E731
        first = req(1)
        self.assertEqual((first["op"], first["sha256"], req(2, idx=1)["op"], req(3, rid=9)["op"]), ("picture", relay.sha256(PNG).hexdigest(), "gone", "gone"))
        for n in range(4, 11): self.assertEqual(req(n)["op"], "picture")
        self.assertEqual(req(11)["op"], "gone")  # the 11th in a minute: no data
        self.now += timedelta(seconds=61)
        self.assertEqual(req(12)["op"], "picture")  # later it succeeds
        self.assertEqual(self.control({"op": "ack", "ids": [1]}, "ab" * 16)[1], {"op": "acked", "ids": [1]})
        self.assertEqual((req(13)["op"], self.picture_rows()), ("gone", [(1, 0, len(PNG), 1)]))  # acked: data gone, sha256 and size kept
        self.store.ack([5], ht.NOW + 31 * 86400)
        self.assertEqual(self.picture_rows(), [])  # metadata dropped after 30 days

    def test_malformed_wire_is_refused(self):
        item = {"id": 1, "chat": OWNER_CHAT, "text": "t", "pictures": 0}
        sha = "a" * 64
        for shots in ([{"idx": 1, "sha256": sha, "size": 3}], [{"idx": 0, "sha256": "zz", "size": 3}], [{"idx": 0, "sha256": sha, "size": 0}],
                      [{"idx": i, "sha256": sha, "size": 3} for i in range(3)], [{"idx": 0, "sha256": sha, "size": 3, "path": "x"}], []):
            with self.subTest(shots=shots), self.assertRaises(ValueError):
                relay.seal_control({"op": "replies", "items": [{**item, "shots": shots}]}, KEY, nonce="dd" * 16, now=ht.NOW)
        for body in ({"op": "picture", "id": 1, "idx": 2}, {"op": "picture", "id": 1, "idx": 0, "sha256": sha, "b64": "!!"},
                     {"op": "picture", "id": 1, "idx": 0, "sha256": sha, "b64": "A" * (relay.B64_MAX + 4)}):
            with self.subTest(body=body), self.assertRaises(ValueError): relay.seal_control(body, KEY, nonce="dd" * 16, now=ht.NOW)


class MacSideTests(AttachCase):
    def test_happy_path_text_then_picture_then_ack_then_data_cleared(self):
        self.queue(self.shot())
        self.f.pull()
        self.assertEqual([e[0] for e in self.events], ["text", "png"])
        self.assertEqual((self.text.calls, self.events[1][4]), ([(OWNER_CHAT, "done", ())], 30))
        parts = self.multipart(self.events[1])
        fixture = json.loads((FIX / "bb-attachment-request.json").read_text())
        self.assertEqual(urlsplit(self.events[1][1]).path, fixture["path"])
        self.assertEqual(sorted(k for k in parts if k != fixture["file_part"]), sorted(fixture["multipart_fields"]))
        self.assertEqual((parts["chatGuid"][1].decode(), parts["name"][1].decode(), parts["attachment"]), (OWNER_CHAT, "hass-1-0.png", ("hass-1-0.png", PNG)))
        self.assertEqual((self.store.status(), self.picture_rows()), ({"waiting": 0, "total": 1}, [(1, 0, len(PNG), 1)]))
        logged = " ".join(r.getMessage() for r in self.records)
        for secret in (relay.sha256(PNG).hexdigest(), str(self.shots), OWNER_CHAT, "done"): self.assertNotIn(secret, logged)
        self.f.pull()  # nothing new: nothing sent twice
        self.assertEqual((len(self.pngs()), len(self.text.calls)), (1, 1))

    def test_refused_screenshot_gets_the_note_and_two_pictures_go(self):
        self.queue(self.shot("1.png"), self.shot("2.png", PNG2), self.shot("3.png"), text="t")
        self.f.pull()
        self.assertEqual(self.text.calls, [(OWNER_CHAT, "t", (None,))])
        self.assertEqual([self.multipart(e)["attachment"][1] for e in self.pngs()], [PNG, PNG2])

    def test_bad_bytes_are_given_up_once_and_acked(self):
        cases = {"sha mismatch": (PNG[:-1] + b"X", None), "non-png": (b"GIF89a" + b"x" * 24, True)}
        for label, (data, fix) in cases.items():
            with self.subTest(label):
                self.queue(self.shot(f"{label[:3]}.png"))
                rid = self.store.db.execute("SELECT MAX(id) FROM relay").fetchone()[0]
                sha = ", sha256 = '%s'" % relay.sha256(data).hexdigest() if fix else ""
                self.store.db.execute(f"UPDATE picture SET data = ?{sha}, size = ? WHERE relay_id = ?", (data, len(data) if fix else len(PNG), rid))
                self.f.pull()
                self.assertEqual((self.texts()[-1], self.pngs(), self.store.status()["waiting"]), (bridge_fallback(), [], 0))
        self.assertEqual(self.texts().count(bridge_fallback()), 2)

    def test_other_chat_and_replayed_envelope_are_not_sent_or_acked(self):
        self.store.add(OTHER, "not yours", 0, ht.NOW)
        self.f.pull()
        self.queue(self.shot())
        real_post = self.f.post
        def post(path, env, big=False):
            out = real_post(path, env, big)
            if relay.unseal_control(out, KEY, now=self.now, seen=set())["op"] == "picture": self.spool.add(out["nonce"])  # replayed
            return out
        with mock.patch.object(self.f, "post", post), self.assertRaises(bridge.EnvelopeError): self.f.pull()
        self.assertEqual((self.texts(), self.pngs(), self.store.status()["waiting"]), (["done"], [], 2))

    def test_oversize_reply_is_refused_before_parsing(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = lambda n: b"x" * n
        with mock.patch.object(bridge._OPENER, "open", return_value=response), self.assertRaises(bridge.BridgeError):
            fwd.request_json("http://127.0.0.1:8795/v1/relay", {}, limit=fwd.MAX_REPLY)
        self.assertEqual(response.__enter__.return_value.read.call_args.args, (fwd.MAX_REPLY + 1,))
        self.assertEqual(fwd.Forwarder(self.cfg, self.spool, lambda: 0, fwd.request_json, self.text, self.attach).big.keywords, {"limit": fwd.MAX_REPLY})

    def test_gone_row_gives_the_fallback_once(self):
        self.queue(self.shot())
        self.store.db.execute("UPDATE picture SET data = NULL")
        self.f.pull()
        self.assertEqual((self.texts(), self.store.status()["waiting"]), (["done", bridge_fallback()], 0))

    def test_crash_after_text_resumes_with_the_picture_only(self):
        self.queue(self.shot())
        with mock.patch.object(self.attach, "send_png", side_effect=RuntimeError("crash")), self.assertRaises(RuntimeError): self.f.pull()
        self.assertEqual((self.texts(), self.store.status()["waiting"]), (["done"], 1))
        self.advance(61)  # the host hands the unacked row out again
        self.spool.db.close()
        self.start()
        self.f.pull()
        self.assertEqual((self.texts(), len(self.pngs()), self.store.status()["waiting"]), (["done"], 1, 0))

    def test_three_failures_give_one_fallback_and_stop(self):
        self.attach_fail = True
        self.queue(self.shot())
        for _ in range(3):
            self.f.pull()
            self.advance(61)
        self.assertEqual((len(self.pngs()), self.texts(), self.store.status()["waiting"]), (3, ["done", bridge_fallback()], 0))
        self.f.pull()
        self.advance(61)
        self.f.pull()
        self.assertEqual((len(self.pngs()), len(self.texts())), (3, 2))

    def test_send_png_refusals_carry_no_secrets(self):
        with self.assertRaises(ValueError): bridge_attach.BlueBubblesAttachmentSender("http://192.0.2.1:1234", self.root / "password", OWNER_CHAT)
        for chat, data, name in ((OTHER, PNG, "hass-1-0.png"), (OWNER_CHAT, b"GIF89a", "hass-1-0.png"), (OWNER_CHAT, PNG, "../x.png")):
            with self.assertRaises(bridge.BridgeError): self.attach.send_png(chat, data, name)
        self.assertEqual(self.pngs(), [])
        self.attach_fail = True
        with self.assertRaises(bridge.BridgeError) as ctx: self.attach.send_png(OWNER_CHAT, PNG, "hass-1-0.png")
        shown = repr(ctx.exception) + str(ctx.exception) + repr(ctx.exception.args)
        for secret in ("secret-url", "synthetic-not-a-real-password", "fixture-picture", "127.0.0.1"): self.assertNotIn(secret, shown)
        self.assertIsNone(ctx.exception.__cause__)


def bridge_fallback(): return fwd.GAVE_UP


if __name__ == "__main__":
    unittest.main()
