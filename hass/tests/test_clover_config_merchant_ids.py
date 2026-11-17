"""RF1221-10: a non-ASCII Clover merchantId is refused at configuration, not later by the client.
Run: python3 -B -m unittest hass.tests.test_clover_config_merchant_ids
"""
import copy
import unittest
from unittest import mock

from hass import host
from hass.clover.client import CloverClient
from hass.clover.config import ConfigProblem, from_settings

TOKEN_PATH = "/synthetic/not-opened.token"
GOOD = "FAKEMERCH0001"


def settings(**over):
    return {"environment": "sandbox", "merchantId": GOOD, "tokenFile": TOKEN_PATH, **over}


def host_dict(clover=None):
    raw = {"state": "/synthetic/state", "secretFile": "/synthetic/key", "listen": "127.0.0.1:8795", "allowedPeers": ["127.0.0.1"],
           "approvals": "hold", "runtimeCommit": "0" * 40, "interpreter": {"url": "http://127.0.0.1:11434", "model": "m"}}
    if clover is not None:
        raw["clover"] = clover
    return raw


def never(*a, **k):
    raise AssertionError("transport called")


UNICODE_IDS = ("é" * 8, "Ａ" * 8, "١" * 8, "²" * 8, "é" * 20, "FAKEMERCH" + "é" * 2, "Ａ" + "A" * 9)


class MerchantIdTests(unittest.TestCase):
    def test_unicode_merchant_ids_raise_field_only_config_problem(self):
        for mid in UNICODE_IDS:
            raw = settings(merchantId=mid)
            before = copy.deepcopy(raw)
            with self.subTest(mid=mid), self.assertRaises(ConfigProblem) as ctx:
                from_settings(raw)
            self.assertEqual(ctx.exception.fields, ("merchantId",))
            self.assertEqual(str(ctx.exception), "merchantId")
            self.assertEqual(raw, before)

    def test_ascii_merchant_ids_preserve_identity_and_client_admission(self):
        for mid in ("abcdefgh", "ABCDEFGH", "aBcD1234eF", "12345678", "00001234", "Z" * 20, "FAKEMERCH0001"):
            with self.subTest(mid=mid):
                cfg = from_settings(settings(merchantId=mid))
                self.assertEqual(cfg.merchant_id, mid)
                CloverClient(cfg.merchant_id, None, never, cfg.environment)

    def test_invalid_merchant_id_shapes_stay_rejected(self):
        raw = settings()
        del raw["merchantId"]
        with self.assertRaises(ConfigProblem) as ctx:
            from_settings(raw)
        self.assertEqual(ctx.exception.fields, ("merchantId",))
        for mid in (None, True, 12345678, ["ABCDEFGH"], {"a": 1}, "", "A" * 7, "A" * 21, "ABCD EFGH", "ABCD-EFGH", "ABCD/EFGH", "ABCDEFG\n", "ABCDEFGH\n"):
            with self.subTest(mid=mid), self.assertRaises(ConfigProblem) as ctx:
                from_settings(settings(merchantId=mid))
            self.assertEqual(ctx.exception.fields, ("merchantId",))

    def test_host_rejects_unicode_merchant_id_by_prefixed_field(self):
        for mid in ("é" * 8, "Ａ" * 8, "١" * 8):
            with self.subTest(mid=mid), mock.patch.object(host, "_private_json", return_value=host_dict(settings(merchantId=mid))):
                with self.assertRaises(host.HostConfigError) as ctx:
                    host.load_host("/synthetic/host.json")
                self.assertEqual(ctx.exception.fields, ["clover.merchantId"])
                self.assertNotIn(mid, str(ctx.exception))
                self.assertNotIn(TOKEN_PATH, str(ctx.exception))
        for clover in (settings(), None):
            with self.subTest(clover=clover), mock.patch.object(host, "_private_json", return_value=host_dict(clover)):
                cfg = host.load_host("/synthetic/host.json")
                self.assertEqual("clover" in cfg, clover is not None)

    def test_merchant_error_preserves_other_configuration_diagnostics(self):
        from_settings(settings(dailyWriteCap=5))
        with self.assertRaises(ConfigProblem) as ctx:
            from_settings(settings(merchantId="é" * 8, dailyWriteCap=0, maxStock=0))
        self.assertEqual(ctx.exception.fields, ("merchantId", "dailyWriteCap", "maxStock"))
        self.assertNotIn("é", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
