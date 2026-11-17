"""M1: durable photo retry, synthetic transports/clocks/stores only."""
import contextlib
import io
import json
import logging
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from hass import bridge, conversation, relay, relay_photos
from hass.tests import test_forwarder_photo as photo, test_host as host_fixture
from hass.tests.test_forwarder import KEY
from mac import hass_forwarder as fwd


class RetryTests(photo.PhotoCase):
    def setUp(self):
        super().setUp()
        self.hostdir = self.root / "receiver"
        self.hostdir.mkdir(mode=0o700)
        self.source = relay_photos.RelayPhotos(self.hostdir, self.host_clock)
        self.lost, self.accepted = False, []
        self.f.transport = self.f.big = self.receiver
        self.logs = io.StringIO()
        handler = logging.StreamHandler(self.logs)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        for redirect in (contextlib.redirect_stderr, contextlib.redirect_stdout):
            self.enterContext(redirect(self.logs))

    def host_clock(self): return datetime.fromtimestamp(self.now, timezone.utc)

    def receiver(self, url, body=None):
        if url.endswith("/v1/photo"):
            req = relay.unseal_control(body, KEY, now=self.now, seen=set())
            self.source.put(req, self.now)
            self.accepted.append(req)
            if self.lost:
                self.lost = False
                raise OSError("CANARY https://invalid/ SECRET raw-image-bytes")
            return relay.seal_control(dict(op="photo-ok", guid=req["guid"], idx=req["idx"]), KEY,
                                      nonce=fwd.secrets.token_hex(16), now=self.now)
        return self.transport(url, body)

    def restart(self):
        self.spool.db.close()
        self.spool = fwd.Spool(self.root, self.now)
        self.addCleanup(self.spool.db.close)
        self.f = fwd.Forwarder(self.cfg, self.spool, lambda: self.now, self.receiver, self.sender)
        self.source = relay_photos.RelayPhotos(self.hostdir, self.host_clock)

    def tick(self, seconds=301):
        self.now += seconds
        self.f.retry_photos()

    def assert_quiet(self):
        for canary in ("CANARY", "https://invalid/", "SECRET", "raw-image-bytes", "synthetic-not-a-real-password"):
            self.assertNotIn(canary, self.logs.getvalue())

    def test_lost_part_zero_reply_restart_both_ends_and_exactly_once(self):
        self.raw = [b"heic-original", photo.PNG, photo.JPEG, photo.PNG]
        self.lost = True
        self.send("lost-reply", text="CANARY SECRET")
        self.assertEqual([p["idx"] for p in self.accepted], [0])
        self.assertEqual(self.pending(), 0)  # text ack did not erase the independent job
        saved = self.spool.db.execute("SELECT body FROM photo_jobs WHERE idx=0").fetchone()[0]
        self.restart()
        self.converted = photo.PNG  # reconverting part 0 would change its digest and conflict
        self.tick(31)
        self.assertEqual([p["idx"] for p in self.accepted], [0, 0, 1, 2, 3])
        self.assertEqual(self.accepted[0], json.loads(saved))
        self.assertEqual(self.accepted[1], self.accepted[0])
        expected = [photo.JPEG, photo.PNG, photo.JPEG, photo.PNG]
        self.assertEqual(self.source.fetch("lost-reply", 4), expected)
        self.restart()
        self.source.put(self.accepted[0], self.now)  # receipt survives consumption and restart
        with sqlite3.connect(self.source.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM photo_in").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM photo_receipt").fetchone()[0], 4)
        conflict = dict(self.accepted[0])
        conflict.update(sha256=photo.hashlib.sha256(photo.PNG).hexdigest(), b64=photo.base64.b64encode(photo.PNG).decode())
        with self.assertRaises(ValueError): self.source.put(conflict, self.now)
        self.assert_quiet()

    def test_rate_limit_survives_restart_and_all_twelve_arrive(self):
        self.raw = [photo.JPEG] * 4
        for i in range(3): self.send(f"rate-{i}")
        self.assertEqual(len(self.accepted), 8)
        self.restart()
        self.f.retry_photos()
        self.assertEqual(len(self.accepted), 8)
        self.tick(61)
        for i in range(3): self.assertEqual(self.source.fetch(f"rate-{i}", 4), self.raw)
        self.assertEqual(len(self.accepted), 12)
        self.assert_quiet()

    def test_busy_worker_queues_photo_and_unrelated_text_then_retries(self):
        class Busy:
            def is_alive(self): return True
        self.f.photo_worker = Busy()
        self.send("busy", text="CANARY")
        self.raw = []
        self.send("unrelated", text="CANARY SECRET")
        self.assertEqual(len(self.posts), 2)
        self.assertEqual(self.accepted, [])
        self.raw = [photo.JPEG]
        self.f.photo_worker = None
        self.tick(1)
        self.assertEqual(self.source.fetch("busy", 1), self.raw)
        self.assert_quiet()

    def test_conversion_timeout_recovers_or_has_one_durable_refusal(self):
        self.raw = [b"raw-image-bytes"]
        with patch.object(fwd.subprocess, "run", side_effect=subprocess.TimeoutExpired("SECRET", 30)):
            self.send("timeout")
            self.assertEqual(self.spool.db.execute("SELECT code FROM photo_jobs").fetchone()[0], "conversion-timeout")
        self.restart()
        self.tick(31)
        self.assertEqual(self.source.fetch("timeout", 1), [photo.JPEG])
        with patch.object(fwd.subprocess, "run", side_effect=subprocess.TimeoutExpired("SECRET", 30)):
            self.send("permanent")
            for _ in range(3): self.tick()
        for _ in range(3): self.tick(61)
        refused = [p for p in self.accepted if p.get("code") == "fetch-failed"]
        self.assertEqual(len(refused), 1)
        self.assertEqual(self.spool.db.execute("SELECT done,body,code FROM photo_jobs WHERE guid='permanent'").fetchall(), [(1, None, "fetch-failed")])
        self.assert_quiet()

    def test_worker_failure_expires_durably_without_sensitive_logs(self):
        with patch.object(fwd.Forwarder, "_push_photos", side_effect=RuntimeError("CANARY SECRET raw-image-bytes")):
            self.send("worker")
        self.tick(1801)
        self.assertEqual(self.spool.db.execute("SELECT done,body,code FROM photo_jobs").fetchall(), [(1, None, "expired")])
        self.assert_quiet()


class HostFailureTests(host_fixture.HostCase):
    def test_relay_waits_past_two_retries_then_one_truthful_failure_across_restart(self):
        self.conv.photos = relay_photos.RelayPhotos(self.hostdir, self.clock)
        srv = self.server()
        self.inbound(srv, self.seal(self.event_from("new-message", guid="missing", text="", attachments=[{}])))
        for seconds in (0, 31, 121, 121):
            self.now += timedelta(seconds=seconds)
            self.rx.drain()
            self.assertEqual(self.inbox.state("missing"), "pending")
        self.now += timedelta(seconds=3601)
        self.rx.drain()
        self.assertEqual(self.inbox.state("missing"), "done")
        self.assertEqual(self.unsent(), 1)
        self.assertEqual([r["text"] for r in self.conv.db.execute("SELECT text FROM outbox")], [conversation.FETCH_FAILED])
        self.restart()
        self.rx.drain()
        self.assertEqual(self.unsent(), 1)
