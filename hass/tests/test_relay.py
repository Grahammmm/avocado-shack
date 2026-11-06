"""HASS-RCV-1 tests: hass/relay.py (key file, control envelopes, pull relay store, reply sender). Fixtures only.
Run: python3 -B -m unittest hass.tests.test_relay"""

import os, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import bridge, relay

KEY_HEX = "ab" * 32
SECRET = bytes.fromhex(KEY_HEX)


class KeyFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="hass-relay-")
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def write(self, name, data, mode=0o600):
        path = self.dir / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, mode)
        os.write(fd, data)
        os.close(fd)
        os.chmod(path, mode)
        return path

    def test_key_file_refusals(self):
        (self.dir / "folder").mkdir()
        (self.dir / "link").symlink_to(self.write("real", KEY_HEX.encode()))
        cases = {"missing": self.dir / "none", "not-regular": self.dir / "folder", "symlink": self.dir / "link",
                 "mode": self.write("open", KEY_HEX.encode(), 0o644), "size": self.write("big", b"a" * 129),
                 "format": self.write("short", b"a" * 63), }
        cases["format+long"] = self.write("long", b"a" * 65)
        cases["format+hex"] = self.write("nothex", b"g" * 64)
        for code, path in cases.items():
            with self.subTest(code=code), self.assertRaises(relay.KeyFileError) as ctx:
                relay.read_key(path)
            self.assertEqual(ctx.exception.code, code.split("+")[0])
            self.assertNotIn(self.dir.name, str(ctx.exception))
            self.assertNotIn("gggg", str(ctx.exception))
        with mock.patch("hass.relay.os.getuid", return_value=os.getuid() + 1), self.assertRaises(relay.KeyFileError) as ctx:
            relay.read_key(self.dir / "real")
        self.assertEqual(ctx.exception.code, "owner")
        self.assertEqual(relay.read_key(self.dir / "real"), SECRET)
        self.assertEqual(relay.read_key(self.write("nl", KEY_HEX.encode() + b"\n")), SECRET)


class ControlTests(unittest.TestCase):
    NOW = 1793638800

    def seal(self, body, nonce=None):
        return relay.seal_control(body, SECRET, nonce=nonce or os.urandom(16).hex(), now=self.NOW)

    def test_relay_pull_ack_rehand(self):
        with tempfile.TemporaryDirectory(prefix="hass-relay-") as tmp:
            store = relay.RelayStore(Path(tmp))
            a, b = store.add("c", "one", 0, 100), store.add("c", "two", 2, 100)
            self.assertEqual([r["id"] for r in store.pull(5, 100)], [a, b])
            self.assertEqual(store.pull(5, 160), [])  # 60 s is not more than 60 s
            self.assertEqual([r["text"] for r in store.pull(1, 161)], ["one"])  # re-handed, oldest first, max honoured
            self.assertEqual(store.ack([a, 999], 162), 1)
            self.assertEqual(store.ack([a], 163), 0)  # idempotent
            self.assertEqual([r["id"] for r in store.pull(5, 300)], [b])
            self.assertEqual(store.status(), {"waiting": 1, "total": 2})
            self.assertEqual(store.db.execute("SELECT value FROM meta WHERE name = 'last_pull_at'").fetchone()[0], "300")
        env, seen = self.seal({"op": "pull", "max": 3}, "cd" * 16), set()
        self.assertEqual(relay.unseal_control(env, SECRET, now=self.NOW, seen=seen), {"op": "pull", "max": 3})
        with self.assertRaises(bridge.EnvelopeError) as ctx:
            relay.unseal_control(env, SECRET, now=self.NOW, seen=seen)
        self.assertEqual(ctx.exception.code, "replay")

    def test_envelope_key_stale_and_closed_shapes(self):
        env = self.seal({"op": "replies", "items": [{"id": 1, "chat": "c", "text": "t", "pictures": 0}]})
        self.assertEqual(env["mac"], bridge._mac(relay.control_key(SECRET), {k: v for k, v in env.items() if k != "mac"}))
        self.assertNotEqual(env["mac"], bridge._mac(SECRET, {k: v for k, v in env.items() if k != "mac"}))  # not the raw key
        self.assertEqual(relay.unseal_control(env, SECRET, now=self.NOW, seen=set())["op"], "replies")
        for bad, now, want in ((env, self.NOW + 301, "stale"), ({**env, "v": 1}, self.NOW, "version"),
                               ({**env, "mac": "0" * 64}, self.NOW, "mac"), ({**env, "extra": 1}, self.NOW, "shape"),
                               ({**env, "body": {"op": "pull", "max": 6}}, self.NOW, "shape")):
            with self.subTest(want=want), self.assertRaises(bridge.EnvelopeError) as ctx:
                relay.unseal_control(bad, SECRET, now=now, seen=set())
            self.assertEqual(ctx.exception.code, want)
        for body in ({"op": "ack", "ids": []}, {"op": "ack", "ids": [0]}, {"op": "pull", "max": 1, "x": 1},
                     {"op": "replies", "items": [{"id": 1, "chat": "c", "text": "x" * 8193, "pictures": 0}]},
                     {"op": "replies", "items": [{"id": 1, "chat": "c", "text": "t", "pictures": 11}]}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.seal(body)
        v1 = bridge.seal(bridge.Inbound("p", "c", "s", "t", received_at="x"), SECRET, nonce="ef" * 16, now=self.NOW)
        with self.assertRaises(bridge.EnvelopeError):
            relay.unseal_control(v1, SECRET, now=self.NOW, seen=set())  # an inbound envelope is not a control one

    def test_relay_sender_refuses_other_chat_and_long_text(self):
        with tempfile.TemporaryDirectory(prefix="hass-relay-") as tmp:
            store = relay.RelayStore(Path(tmp))
            sender = relay.RelaySender(store, "owner-chat", lambda: 100)
            for chat, text, pics in (("other", "hi", ()), ("owner-chat", "x" * 8193, ()), ("owner-chat", "hi", ["p"] * 11)):
                with self.subTest(chat=chat, n=len(text)), self.assertRaises(relay.RelayRefused):
                    sender.send(chat, text, pics)
            self.assertEqual(store.status()["total"], 0)
            sender.send("owner-chat", "hi", ["/private/path.png"])
            self.assertEqual([tuple(r) for r in store.db.execute("SELECT chat, text, pictures FROM relay")],
                             [("owner-chat", "hi", 1)])  # a count, never a path
