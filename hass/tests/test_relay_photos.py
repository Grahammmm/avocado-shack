"""Host photo ingress on private fixture stores and loopback sockets only."""
import base64
import json
import sqlite3
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from hass.content_model import REPO_ROOT
from unittest import mock

from hass import bridge, conversation, host, inbox, media, receiver, relay, relay_photos
from hass.skills import item_intake as ii, testkit
from hass.tests import test_host as harness, test_item_add_dispatch as item
from hass.tests.test_receiver import SECRET


class PhotoTests(harness.HostCase):
    def source(self):
        return relay_photos.RelayPhotos(self.hostdir, self.clock, self.inbox.db.execute("PRAGMA database_list").fetchone()[2])

    def body(self, guid="photo-1", idx=0, count=1, data=b"photo"):
        return dict(op="photo", guid=guid, idx=idx, count=count, sha256=sha256(data).hexdigest(),
                    b64=base64.b64encode(data).decode())

    def sealed(self, body, **kw):
        self.nonce += 1
        return json.dumps(relay.seal_control(body, SECRET, nonce=f"{self.nonce:032x}", now=self.now, **kw)).encode()

    def photo_server(self, **extra):
        cfg = host.load_host(self.host_json(listen="127.0.0.1:0", photos=True, **extra), allow_port_zero=True)
        srv = host.Server(cfg, SECRET, receiver.Receiver(state=self.inbox, settings=None), self.store, self.clock)
        self.addCleanup(srv.server_close)
        return srv, cfg

    def test_shapes_integrity_bounds_and_closed_keys(self):
        good = self.body()
        for delta in ({"guid": ".."}, {"guid": "x\ud800"}, {"idx": True}, {"count": 5}, {"idx": -1},
                      {"count": 0}, {"count": 1.0}, {"b64": "!"}, {"b64": ""}, {"sha256": "0" * 64}, {"extra": 1}):
            with self.subTest(delta=delta), self.assertRaises(ValueError): self.sealed({**good, **delta})
        for size, valid in ((relay.PHOTO_MAX, True), (relay.PHOTO_MAX + 1, False)):
            self.assertEqual(relay._body_ok(self.body(data=b"x" * size)), valid)
        self.assertFalse(relay._body_ok(dict(op="photo-refused", guid="g", idx=0, count=1, code="unknown")))
        self.assertFalse(relay._body_ok(dict(op="photo-ok", guid="g", idx=4)))

    def test_http_auth_replay_duplicate_caps_route_separation_and_rate(self):
        srv, _ = self.photo_server()
        raw = self.sealed(self.body(data=b"x" * 65537))
        status, response = self.post(srv, "/v1/photo", raw)
        self.assertEqual((status, relay.unseal_control(json.loads(response), SECRET, now=self.now, seen=set())),
                         (200, dict(op="photo-ok", guid="photo-1", idx=0)))
        self.assertEqual(self.post(srv, "/v1/photo", raw)[0], 400)
        self.assertEqual(self.post(srv, "/v1/photo", self.sealed(self.body()))[0], 400)
        bad = json.loads(self.sealed(self.body(guid="bad"))); bad["mac"] = "0" * 64
        self.assertEqual(self.post(srv, "/v1/photo", json.dumps(bad).encode())[0], 400)
        stale = json.loads(self.sealed(self.body(guid="stale"))); stale["ts"] -= 301
        stale["mac"] = bridge._mac(relay.control_key(SECRET), stale)
        self.assertEqual(self.post(srv, "/v1/photo", json.dumps(stale).encode())[0], 400)
        for path, cap in (("/v1/photo", host.PHOTO_BODY), ("/v1/inbound", host.MAX_BODY), ("/v1/relay", host.MAX_BODY)):
            self.assertEqual(self.post(srv, path, b"", headers={"Content-Length": str(cap + 1)})[0], 413)
        self.assertEqual(self.post(srv, "/v1/relay", self.sealed(self.body(guid="wrong")))[0], 400)
        self.assertEqual(self.post(srv, "/v1/photo", self.sealed(dict(op="pull", max=1)))[0], 400)
        for i in range(6): self.assertEqual(self.post(srv, "/v1/photo", self.sealed(self.body(guid=f"g{i}")))[0], 200)
        self.assertEqual(self.post(srv, "/v1/photo", self.sealed(self.body(guid="limited")))[0], 429)
        self.now += timedelta(seconds=60)
        self.assertEqual(self.post(srv, "/v1/photo", self.sealed(self.body(guid="later")))[0], 200)
        self.assertEqual(self.source().fetch("photo-1", 1), [b"x" * 65537])
        with self.assertRaises(ValueError): self.source().fetch("bad", 1)

    def test_store_order_missing_mismatch_tamper_expiry_and_one_use(self):
        src, now = self.source(), int(self.now.timestamp())
        src.put(self.body(idx=1, count=2, data=b"second"), now)
        with self.assertRaisesRegex(ValueError, "photo pending"): src.fetch("photo-1", 2)
        with self.assertRaises(ValueError): src.put(self.body(count=1), now)
        src.put(self.body(idx=0, count=2), now)
        self.assertEqual(src.fetch("photo-1", 2), [b"photo", b"second"])
        with self.assertRaises(ValueError): src.fetch("photo-1", 2)
        src.put(self.body(guid="tampered"), now)
        with sqlite3.connect(src.path) as db: db.execute("UPDATE photo_in SET data = ?", (b"changed",))
        with self.assertRaises(ValueError): src.fetch("tampered", 1)
        self.assertEqual(src.path.stat().st_mode & 0o777, 0o600)
        self.now += timedelta(days=1)
        with self.assertRaises(ValueError): src.fetch("tampered", 1)
        with sqlite3.connect(src.path) as db: self.assertEqual(db.execute("SELECT * FROM photo_in").fetchall(), [])
        src.put(self.body(guid="fresh"), int(self.now.timestamp()))
        with sqlite3.connect(src.path) as db:
            self.assertEqual(db.execute("SELECT guid FROM photo_in").fetchall(), [("fresh",)])

    def test_refusals_reply_without_retry_and_consume_entire_message(self):
        srv, _ = self.photo_server()
        self.conv.photos = self.source()
        work = self.worker(False)
        for i, code in enumerate(("too-large", "unsupported-type", "fetch-failed")):
            guid = f"refused-{i}"
            body = dict(op="photo-refused", guid=guid, idx=0, count=1, code=code)
            self.assertEqual(self.post(srv, "/v1/photo", self.sealed(body))[0], 200)
            self.inbound(srv, self.seal(self.event_from("new-message", guid=guid, text="", attachments=[{}])))
            work.cycle()
            self.assertEqual(self.relay_rows()[-1], conversation.FETCH_FAILED if code == "fetch-failed" else media.REPLIES[code])
        self.assertTrue(all(r["state"] == "done" for r in self.inbound_rows()))
        with sqlite3.connect(self.source().path) as db: self.assertEqual(db.execute("SELECT * FROM photo_in").fetchall(), [])
        src = self.source(); now = int(self.now.timestamp())
        src.put(self.body(guid="batch", idx=0, count=2), now)
        src.put(dict(op="photo-refused", guid="batch", idx=1, count=2, code="too-large"), now)
        with self.assertRaises(relay_photos.PhotoRefused) as ctx: src.fetch("batch", 2)
        self.assertEqual(ctx.exception.position, 2)
        with self.assertRaises(ValueError): src.fetch("batch", 2)

    def test_storage_failure_then_restart_retries_the_same_arrival(self):
        import tempfile
        directory = tempfile.TemporaryDirectory(prefix="relay-retry-")
        self.addCleanup(directory.cleanup)
        self.conv.settings["mediaRoot"] = directory.name
        self.conv.photos = self.source()
        data = (REPO_ROOT / item.JAR).read_bytes()
        self.conv.photos.put(self.body(data=data), int(self.now.timestamp()))
        raw = self.seal(self.event_from("new-message", guid="photo-1", text="", attachments=[{}]))
        self.assertEqual(self.rx.accept(raw, secret=SECRET, now=self.now)["result"], "queued")
        with mock.patch.object(media, "store_original", side_effect=OSError("temporary")):
            with self.assertRaises(OSError): self.rx.drain()
        self.assertEqual(self.inbox.state("photo-1"), "pending")
        self.assertEqual(self.drafts(), [])
        self.conv.photos.put(self.body(guid="orphan"), int(self.now.timestamp()))
        self.now += timedelta(days=1)
        # Both fetch and another upload run expiry before the worker restarts.
        self.assertEqual(self.conv.photos.fetch_for_inbox("photo-1", 1), [data])
        self.conv.photos.put(self.body(guid="fresh"), int(self.now.timestamp()))
        self.restart()
        self.conv.photos = self.source()
        self.rx.drain()
        self.assertEqual(self.inbox.state("photo-1"), "done")
        with sqlite3.connect(self.conv.photos.path) as db:
            self.assertEqual(db.execute("SELECT guid FROM photo_in").fetchall(), [("fresh",)])
        self.assertEqual([r["state"] for r in self.drafts()], ["needs-details"])
        digest = sha256(data).hexdigest()
        self.assertEqual((Path(directory.name) / "originals" / digest[:2] / (digest + ".jpg")).read_bytes(), data)
        with self.assertRaises(ValueError): self.source().fetch("photo-1", 1)

    def test_restart_across_mark_and_cleanup_keeps_one_use(self):
        import tempfile
        directory = tempfile.TemporaryDirectory(prefix="relay-mark-")
        self.addCleanup(directory.cleanup)
        self.conv.settings["mediaRoot"] = directory.name
        self.conv.photos = self.source()
        data = (REPO_ROOT / item.JAR).read_bytes()
        self.conv.photos.put(self.body(data=data), int(self.now.timestamp()))
        raw = self.seal(self.event_from("new-message", guid="photo-1", text="", attachments=[{}]))
        self.assertEqual(self.rx.accept(raw, secret=SECRET, now=self.now)["result"], "queued")
        with mock.patch.object(self.inbox, "_mark", side_effect=OSError("mark failed")):
            with self.assertRaises(OSError): self.rx.drain()
        self.assertEqual(self.inbox.state("photo-1"), "pending")
        self.assertEqual(len(self.drafts()), 1)
        self.restart()
        self.conv.photos = self.source()
        with mock.patch.object(self.conv.photos, "reconcile", side_effect=[None, OSError("crash after mark")]):
            with self.assertRaises(OSError): self.rx.drain()
        self.assertEqual(self.inbox.state("photo-1"), "done")
        with sqlite3.connect(self.conv.photos.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM photo_in").fetchone()[0], 1)
        self.restart()
        self.conv.photos = self.source()
        self.rx.drain()
        self.assertEqual(len(self.drafts()), 1)
        with self.assertRaises(ValueError): self.source().fetch("photo-1", 1)
        self.assertEqual(self.inbox.enqueue(bridge.Inbound("photo-1", testkit.CHAT, testkit.OWNER, "",
                         received_at=self.now.isoformat(), attachments=1)), "duplicate")

    def test_refusal_survives_failure_before_inbox_mark(self):
        self.conv.photos = self.source()
        body = dict(op="photo-refused", guid="photo-1", idx=0, count=1, code="too-large")
        self.conv.photos.put(body, int(self.now.timestamp()))
        raw = self.seal(self.event_from("new-message", guid="photo-1", text="", attachments=[{}]))
        self.assertEqual(self.rx.accept(raw, secret=SECRET, now=self.now)["result"], "queued")
        with mock.patch.object(self.inbox, "_mark", side_effect=OSError("mark failed")):
            with self.assertRaises(OSError): self.rx.drain()
        self.assertEqual(self.inbox.state("photo-1"), "pending")
        self.restart()
        self.conv.photos = self.source()
        self.rx.drain()
        self.assertEqual(self.inbox.state("photo-1"), "done")
        with sqlite3.connect(self.conv.photos.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM photo_in").fetchone()[0], 0)
        self.assertEqual(self.unsent(), 1)

    def test_photos_false_preserves_attachment_reply_and_config_is_boolean(self):
        self.assertFalse(host.load_host(self.host_json())["photos"])
        with self.assertRaises(host.HostConfigError): host.load_host(self.host_json(photos=1))
        srv = self.server()
        work = host.make_worker(host.load_host(self.host_json()), self.store, editor=self.editor, build=lambda: self.interp, clock=self.clock)
        self.assertIsNone(work.conv.photos)
        self.inbound(srv, self.seal(self.event_from("new-message", text="", attachments=[{}])))
        work.cycle()
        self.assertEqual(self.relay_rows(), [conversation.ATTACHMENT_REPLY])

    def test_late_photo_retries_then_opens_legacy_needs_details_draft(self):
        import tempfile
        directory = tempfile.TemporaryDirectory(prefix="relay-originals-")
        self.addCleanup(directory.cleanup)
        self.conv.settings["mediaRoot"] = directory.name
        self.conv.photos = self.source()
        srv, _ = self.photo_server()
        work = self.worker(False)
        self.inbound(srv, self.seal(self.event_from("new-message", guid="late-photo", text="", attachments=[{}])))
        work.cycle()
        self.assertEqual([r["state"] for r in self.inbound_rows()], ["pending"])
        self.assertEqual(self.drafts(), [])
        data = (REPO_ROOT / item.JAR).read_bytes()
        self.assertEqual(self.post(srv, "/v1/photo", self.sealed(self.body(guid="late-photo", data=data)))[0], 200)
        self.now += timedelta(seconds=31)
        work.cycle()
        self.assertEqual([r["state"] for r in self.inbound_rows()], ["done"])
        self.assertEqual([r["state"] for r in self.drafts()], ["needs-details"])
        self.assertEqual(self.relay_rows(), [conversation.PHOTO_QUESTION])

    def test_photo_post_to_real_worker_interview_and_one_coded_proposal(self):
        import tempfile
        media_dir = tempfile.TemporaryDirectory(prefix="relay-media-")
        self.addCleanup(media_dir.cleanup)
        chat = item.Chat([], settings={"itemIntake": True, "mediaRoot": media_dir.name})
        self.addCleanup(chat.close)
        chat.kit._real_assets()  # fixture writer must not write into symlinked assets
        self.now = chat.now
        srv, cfg = self.photo_server(state=str(chat.kit.repo.state))
        srv.receiver = receiver.Receiver(state=inbox.Inbox(cfg["state"], self.now.isoformat(), clock=self.clock), settings=None)
        self.addCleanup(srv.receiver.inbox.close)
        work = host.make_worker(cfg, self.store, editor=chat.kit.editor, build=lambda: chat.interp, clock=self.clock)
        self.addCleanup(work.conv.db.close)
        work.conv.answer_reader = None  # no network: interview answers here use the fixed reader
        self.assertIsInstance(work.conv.labels, host.label_reader.LabelReader)
        data = (REPO_ROOT / item.JAR).read_bytes()
        self.assertEqual(self.post(srv, "/v1/photo", self.sealed(self.body(data=data)))[0], 200)
        def say(text, guid, count=0):
            msg = bridge.Inbound(guid, testkit.CHAT, testkit.OWNER, text, received_at=self.now.isoformat(), attachments=count)
            self.nonce += 1
            raw = json.dumps(bridge.seal(msg, SECRET, nonce=f"{self.nonce:032x}", now=self.now)).encode()
            self.assertEqual(self.inbound(srv, raw), (200, "queued"))
            work.cycle()
        original = media.store_original
        def store(*args, **kw):
            self.assertEqual(self.relay_rows(), [ii.START])  # sent BEFORE storing the original
            return original(*args, **kw)
        with mock.patch.object(media, "store_original", side_effect=store): say("", "photo-1", 1)
        digest = sha256(data).hexdigest()
        self.assertEqual((Path(media_dir.name) / "originals" / digest[:2] / (digest + ".jpg")).read_bytes(), data)
        pending = work.conv.requests.get(testkit.CHAT, self.now)
        self.assertEqual(pending["asked_slot"], "name")
        say("Wildflower honey", "name")
        say("Bee Happy Farm", "maker")
        say("Atascadero, California", "town")
        self.assertEqual(work.conv.requests.get(testkit.CHAT, self.now)["asked_slot"], ii.PREFIX + "maker_site")
        from hass.tests.test_item_intake_conversation import REPLIES
        for i, text in enumerate(REPLIES): say(text, f"answer-{i}")
        chat.script("yes", item.reply())
        say("yes", "badge")
        chat.script("skip", item.reply())
        say("skip", "story")
        drafts = [dict(r) for r in work.conv.db.execute("SELECT * FROM drafts")]
        self.assertEqual(len(drafts), 1, self.relay_rows())
        self.assertEqual(drafts[0]["state"], "proposed")
        self.assertTrue(drafts[0]["code"])
        self.assertIn("Here's the change I'd make:", self.relay_rows()[-1])
