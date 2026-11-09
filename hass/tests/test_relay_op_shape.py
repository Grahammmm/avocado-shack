"""Malformed relay operation tags refuse at the shape boundary; fixtures only."""
import json
import unittest
from unittest import mock

from hass import bridge, relay
from hass.tests import test_host as host_fixture

SECRET = host_fixture.SECRET
NOW = host_fixture.NOW
BAD_BODIES = [{"op": op} for op in ([], {}, ["pull"], 0, 1, 1.5, True, False, None)] + [{}, None, [], "state"]


def envelope(body, n):
    return {"v": 2, "ts": NOW, "nonce": f"{n:032x}", "body": body, "mac": "0" * 64}


class OperationShapeTests(unittest.TestCase):
    def test_non_string_op_returns_false_and_seal_refuses(self):
        class StringSubclass(str):
            pass

        for n, body in enumerate([*BAD_BODIES, {"op": StringSubclass("state")}], 1):
            with self.subTest(body=body):
                self.assertIs(relay._body_ok(body), False)
                with self.assertRaisesRegex(ValueError, "^control body is not in a known form$"):
                    relay.seal_control(body, SECRET, nonce=f"{n:032x}", now=NOW)

    def test_unseal_bad_op_is_shape_before_mac_or_nonce(self):
        for n, body in enumerate(BAD_BODIES, 1):
            seen = mock.MagicMock()
            with self.subTest(body=body), mock.patch.object(bridge, "_mac") as mac:
                with self.assertRaises(bridge.EnvelopeError) as caught:
                    relay.unseal_control(envelope(body, n), SECRET, now=NOW, seen=seen)
                self.assertEqual(caught.exception.code, "shape")
                mac.assert_not_called()
                seen.__contains__.assert_not_called()
                seen.add.assert_not_called()

    def test_known_operations_preserve_shapes_and_authentication(self):
        valid = [
            {"op": "pull", "max": 1}, {"op": "ack", "ids": [1]},
            {"op": "replies", "items": [{"id": 1, "chat": "fixture", "text": "hello", "pictures": 0}]},
            {"op": "acked", "ids": []}, {"op": "picture", "id": 1, "idx": 0},
            {"op": "picture", "id": 1, "idx": 1, "sha256": "a" * 64, "b64": "eA=="},
            {"op": "gone", "id": 1, "idx": 0}, {"op": "state"}, {"op": "state", "paused": True},
        ]
        for n, body in enumerate(valid, 100):
            with self.subTest(body=body):
                self.assertTrue(relay._body_ok(body))
                env = relay.seal_control(body, SECRET, nonce=f"{n:032x}", now=NOW)
                seen = set()
                self.assertEqual(relay.unseal_control(env, SECRET, now=NOW, seen=seen), body)
                self.assertEqual(seen, {env["nonce"]})
                for bad, now, used, code in (
                    ({**env, "mac": "0" * 64}, NOW, set(), "mac"),
                    (env, NOW + bridge.MAX_SKEW + 1, set(), "stale"),
                    (env, NOW - bridge.MAX_SKEW - 1, set(), "stale"),
                    (env, NOW, seen.copy(), "replay"),
                ):
                    before = used.copy()
                    with self.subTest(code=code, now=now), self.assertRaises(bridge.EnvelopeError) as caught:
                        relay.unseal_control(bad, SECRET, now=now, seen=used)
                    self.assertEqual(caught.exception.code, code)
                    self.assertEqual(used, before)
        invalid = [
            {"op": "unknown"}, {"op": "pull", "max": True}, {"op": "ack", "ids": []},
            {"op": "replies", "items": [{}]}, {"op": "acked", "ids": [0]},
            {"op": "picture", "id": 1, "idx": 2},
            {"op": "picture", "id": 1, "idx": 0, "sha256": "bad", "b64": "eA=="},
            {"op": "gone", "id": 1, "idx": False}, {"op": "state", "paused": 1},
            {"op": "state", "extra": True},
        ]
        for body in invalid:
            with self.subTest(body=body):
                self.assertFalse(relay._body_ok(body))
                with self.assertRaises(ValueError):
                    relay.seal_control(body, SECRET, nonce="ff" * 16, now=NOW)


class OperationHTTPTests(host_fixture.HostCase):
    def snapshot(self):
        return [list(self.inbox.db.iterdump()), list(self.store.db.iterdump())]

    def test_http_bad_op_is_400_then_valid_control_still_works(self):
        # Keep a real pending reply and picture: a refusal must not hand off or erase either.
        self.store.add("fixture", "pending", 0, NOW, shots=(relay.PNG_SIG + b"fixture",))
        srv = self.server()
        before = self.snapshot()
        for n, body in enumerate(BAD_BODIES, 1):
            with self.subTest(body=body):
                status, raw = self.post(srv, "/v1/relay", json.dumps(envelope(body, n)).encode())
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(raw), {"result": "rejected"})
                self.assertEqual(self.snapshot(), before)
        self.assertFalse(any("request failed" in record.getMessage() for record in self.records))
        env = relay.seal_control({"op": "state"}, SECRET, nonce="fe" * 16, now=NOW)
        status, raw = self.post(srv, "/v1/relay", json.dumps(env).encode())
        self.assertEqual(status, 200)
        self.assertEqual(relay.unseal_control(json.loads(raw), SECRET, now=NOW, seen=set()),
                         {"op": "state", "paused": True})
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 1)
        rows = list(self.store.db.iterdump())
        for n, (bad, code) in enumerate((({**env, "mac": "0" * 64}, "mac"), (env, "replay")), 1):
            with self.subTest(code=code):
                self.assertEqual(self.post(srv, "/v1/relay", json.dumps(bad).encode())[0], 400)
                self.assertEqual(list(self.store.db.iterdump()), rows)
                self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 1)
        stale = relay.seal_control({"op": "pull", "max": 1}, SECRET, nonce="fd" * 16,
                                   now=NOW - bridge.MAX_SKEW - 1)
        self.assertEqual(self.post(srv, "/v1/relay", json.dumps(stale).encode())[0], 400)
        self.assertEqual(list(self.store.db.iterdump()), rows)
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 1)
