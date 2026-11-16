"""Synthetic Mac photos; no real BlueBubbles, sips, receiver or messages."""
import base64, hashlib, json, os, subprocess, threading, time, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from hass import bridge, media, relay
from hass.tests.test_forwarder import ForwarderCase, KEY
from mac import hass_forwarder as fwd

JPEG = b"\xff\xd8\xffsynthetic\xff\xd9"
PNG = media.KINDS["png"] + b"synthetic" + media.PNG_END


class PhotoTests(ForwarderCase):
    def setUp(self):
        super().setUp()
        self.raw, self.photos, self.order, self.downloads = [JPEG], [], [], []
        self.sips_paths, self.converted, self.photo_error = [], JPEG, None
        self.f.transport = self.f.big = self.receiver
        p = patch.object(fwd.bridge_photos, "_urllib_transport", self.bluebubbles)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(fwd.subprocess, "run", self.sips)
        p.start(); self.addCleanup(p.stop)

    def bluebubbles(self, url, headers, timeout, limit):
        self.assertLessEqual(timeout, 30)
        path = urlsplit(url).path
        if "/message/" in path:
            return 200, json.dumps({"data": {"attachments": [{"guid": f"a{i}", "totalBytes": len(v)} for i, v in enumerate(self.raw)]}}).encode()
        self.downloads.append(path)
        return 200, self.raw[int(path.split("/")[-2][1:])]

    def sips(self, args, **kw):
        self.assertEqual(args[:9], ["/usr/bin/sips", "-s", "format", "jpeg", "-s", "formatOptions", "85", "-Z", "4096"])
        self.assertTrue(0 < kw["timeout"] <= 30)
        src, dst = Path(args[9]), Path(args[11])
        self.assertEqual(src.parent.stat().st_mode & 0o777, 0o700)
        self.sips_paths.append(src.parent)
        dst.write_bytes(self.converted)

    def receiver(self, url, body=None):
        path = urlsplit(url).path
        if path == "/v1/photo":
            req = relay.unseal_control(body, KEY, now=self.now, seen=set())
            self.order.append("photo"); self.photos.append(req)
            if self.photo_error: raise self.photo_error
            return relay.seal_control({"op": "photo-ok", "guid": req["guid"], "idx": req["idx"]}, KEY,
                                      nonce=os.urandom(16).hex(), now=self.now)
        if path == "/v1/inbound": self.order.append("text")
        return self.transport(url, body)

    def send(self, guid="m1", **kw):
        self.enqueue(guid, attachments=[{}] * len(self.raw), **kw)
        self.f.deliver()
        self.assertEqual(self.pending(), 0)

    def test_one_through_four_sniffed_photos_before_text(self):
        for n in range(1, 5):
            self.f.photo_posts.clear(); self.photos.clear(); self.order.clear()
            self.raw = [JPEG, PNG, JPEG, PNG][:n]
            self.send(f"m{n}")
            self.assertEqual(self.order, ["photo"] * n + ["text"])
            for i, req in enumerate(self.photos):
                self.assertEqual((req["guid"], req["idx"], req["count"]), (f"m{n}", i, n))
                self.assertEqual(base64.b64decode(req["b64"]), self.raw[i])
                self.assertEqual(req["sha256"], hashlib.sha256(self.raw[i]).hexdigest())
        self.assertEqual(self.sips_paths, [])

    def test_heic_and_oversize_convert_and_cleanup(self):
        for raw in (b"heic-original", JPEG + b"x" * relay.PHOTO_MAX):
            self.raw = [raw]; self.send(str(len(raw)))
            self.assertEqual(base64.b64decode(self.photos[-1]["b64"]), JPEG)
        self.assertEqual(len(self.sips_paths), 2)
        self.assertTrue(all(not p.exists() for p in self.sips_paths))

    def test_refusals_and_transport_failure_keep_text(self):
        for i, (raw, converted, code) in enumerate(((b"heic", b"bad", "unsupported-type"),
                (b"heic", JPEG + b"x" * relay.PHOTO_MAX, "too-large"),
                (b"x" * (media.MAX_BYTES + 1), JPEG, "too-large"))):
            self.raw, self.converted = [raw], converted
            self.send(f"refused{i}")
            self.assertEqual(self.photos[-1]["code"], code)
        self.photo_error = bridge.BridgeError("http-error", 404)
        self.raw = [JPEG]; self.send("oldhost")
        self.photo_error = RuntimeError("synthetic-failure"); self.send("failed")
        with patch.object(fwd.bridge_photos.BlueBubblesPhotos, "fetch", side_effect=OSError):
            self.photo_error = None; self.send("fetchfailed")
            self.assertEqual(self.photos[-1]["code"], "fetch-failed")
        with patch.object(fwd.subprocess, "run", side_effect=subprocess.TimeoutExpired("sips", 30)):
            self.raw = [b"heic"]; self.send("sipstimeout")

    def test_g_group_echo_edit_stranger_and_invalid_counts_send_no_photos(self):
        self.cfg["gChat"] = "iMessage;-;g@example.invalid"
        for i, kw in enumerate((dict(chats=[{"guid": self.cfg["gChat"]}]),
                dict(chats=[{"guid": "iMessage;+;group"}]), dict(isFromMe=True),
                dict(handle={"address": "stranger@example.invalid"}))):
            self.send(f"excluded{i}", **kw)
        self.raw = [JPEG] * 5; self.send("five")
        self.raw = []; self.send("none")
        msg = bridge.Inbound(**self.posts[0]["body"])
        from dataclasses import replace
        self.f.push_photos(replace(msg, kind="edit", attachments=1, chat=self.cfg["ownerChat"]))
        self.assertEqual((self.photos, self.downloads), ([], []))

    def test_eight_posts_per_minute_including_refusals(self):
        self.raw = [JPEG] * 4
        for i in range(3):
            if i == 1: self.raw, self.converted = [b"heic"] * 4, b"bad"
            self.send(f"rate{i}")
        self.assertEqual(len(self.photos), 8)
        self.assertEqual(len(self.posts), 3)

    def test_stalled_photo_stops_waiting_at_thirty_seconds_and_ack_is_independent(self):
        entered, release, reacted = threading.Event(), threading.Event(), threading.Event()
        original = self.bluebubbles
        def slow(*args):
            entered.set(); release.wait(35)
            return original(*args)
        self.f.host_paused = lambda spool: False
        self.f.tapback_blocker = lambda: None
        self.f.reactor.react = lambda *args: reacted.set()
        self.f.start_ack(); self.addCleanup(self.f.stop_ack)
        self.enqueue(attachments=[{}])
        self.f.ack_kick()
        try:
            with patch.object(fwd.bridge_photos, "_urllib_transport", slow):
                start = time.monotonic(); self.f.deliver(); elapsed = time.monotonic() - start
                self.assertTrue(entered.is_set()); self.assertTrue(reacted.is_set())
                self.assertTrue(29 <= elapsed < 32, elapsed)
                self.assertEqual((len(self.posts), self.photos), (1, []))
                release.set(); self.f.photo_worker.join(2)
                self.assertFalse(self.f.photo_worker.is_alive())
                self.assertEqual(self.downloads, [])
        finally: release.set()
