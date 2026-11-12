"""Screenshot ordinals must be exact JSON integers, matching the picture-request validator; pure fixtures only."""
import copy
import json
import unittest
from unittest import mock

from hass import bridge, relay
from hass.tests import test_host as host_fixture

SECRET = host_fixture.SECRET
NOW = host_fixture.NOW
DIGEST = "a" * 64


def shot(idx):
    return {"idx": idx, "sha256": DIGEST, "size": 1}


def announce(*idxs):
    return {"op": "replies", "items": [{"id": 1, "chat": "fixture", "text": "hello", "pictures": 0,
                                        "shots": [shot(i) for i in idxs]}]}


def envelope(body, n):
    return {"v": 2, "ts": NOW, "nonce": f"{n:032x}", "body": body, "mac": "0" * 64}


class ShotIndexTypeTests(unittest.TestCase):
    def test_one_shot_boolean_and_float_ordinals_are_not_integer_zero(self):
        for idx in (False, 0.0, -0.0, None, "0", [0], {"0": 0}):
            with self.subTest(idx=idx):
                self.assertIs(relay._shots([shot(idx)]), False)
                self.assertIs(relay._body_ok(announce(idx)), False)
        self.assertIs(relay._shots([shot(0)]), True)
        self.assertIs(relay._body_ok(announce(0)), True)

    def test_two_shot_numeric_aliases_refuse_in_either_position(self):
        for idxs in ([False, True], [0.0, 1.0], [0, True], [False, 1], [0, 1.0], [0.0, 1]):
            with self.subTest(idxs=idxs):
                self.assertIs(relay._shots([shot(i) for i in idxs]), False)
                self.assertIs(relay._body_ok(announce(*idxs)), False)
        shots = [shot(0), shot(1)]
        before = copy.deepcopy(shots)
        self.assertIs(relay._shots(shots), True)
        self.assertEqual(shots, before)

    def test_closed_shot_shapes_order_and_bounds_remain_unchanged(self):
        for idxs in ([], [1], [1, 0], [0, 0], [0, 2], [-1], [0, 1, 2]):
            with self.subTest(idxs=idxs):
                self.assertIs(relay._shots([shot(i) for i in idxs]), False)
        for bad in ([{"idx": 0, "sha256": DIGEST}], [{"sha256": DIGEST, "size": 1}],
                    [{"idx": 0, "sha256": DIGEST, "size": 1, "x": 1}],
                    [{"idx": 0, "sha256": "A" * 3, "size": 1}], [{"idx": 0, "sha256": DIGEST, "size": 0}],
                    [{"idx": 0, "sha256": DIGEST, "size": True}], [{"idx": 0, "sha256": DIGEST, "size": 1.0}],
                    [{"idx": 0, "sha256": DIGEST, "size": relay.MAX_PNG + 1}],
                    [None], ["x"], [[0]], [0], "x", None, {}):
            with self.subTest(bad=bad):
                self.assertIs(relay._shots(bad), False)
        self.assertIs(relay._shots([{"idx": 0, "sha256": DIGEST, "size": relay.MAX_PNG}]), True)

    def test_seal_refuses_noninteger_shot_idx_without_mutating_body(self):
        for n, idxs in enumerate(([False], [0.0], [False, True], [0.0, 1.0]), 1):
            body = announce(*idxs)
            before = json.dumps(body, sort_keys=True)
            with self.subTest(idxs=idxs):
                with self.assertRaisesRegex(ValueError, "^control body is not in a known form$"):
                    relay.seal_control(body, SECRET, nonce=f"{n:032x}", now=NOW)
                self.assertEqual(json.dumps(body, sort_keys=True), before)
        for n, idxs in enumerate(([0], [0, 1]), 10):
            body = announce(*idxs)
            env = relay.seal_control(body, SECRET, nonce=f"{n:032x}", now=NOW)
            self.assertEqual(relay.unseal_control(env, SECRET, now=NOW, seen=set()), body)

    def test_unseal_rejects_shape_before_consuming_nonce(self):
        for n, idxs in enumerate(([False], [0.0], [False, True], [0.0, 1.0], [0, True]), 1):
            seen = mock.MagicMock()
            with self.subTest(idxs=idxs), mock.patch.object(bridge, "_mac") as mac:
                with self.assertRaises(bridge.EnvelopeError) as caught:
                    relay.unseal_control(envelope(announce(*idxs), n), SECRET, now=NOW, seen=seen)
                self.assertEqual(caught.exception.code, "shape")
                mac.assert_not_called()
                seen.__contains__.assert_not_called()
                seen.add.assert_not_called()

    def test_announced_indices_are_usable_by_picture_request_shape(self):
        for idxs in ([0], [0, 1]):
            body = announce(*idxs)
            self.assertIs(relay._body_ok(body), True)
            for s in body["items"][0]["shots"]:
                self.assertIs(relay._body_ok({"op": "picture", "id": 1, "idx": s["idx"]}), True)


if __name__ == "__main__":
    unittest.main()
