"""RF1450-10: malformed or oversized textual Retry-After headers use bounded retry handling, never ValueError.
Run: python3 -B -m unittest hass.tests.test_clover_retry_after_input
"""
import unittest

from hass.clover import client as cl
from hass.tests.test_clover_client import BASE, NoNetwork, fixture, make

KEY = f"{BASE}/categories?limit=1000&offset=0"


class RetryAfterInput(NoNetwork):
    def one_429(self, header, **kw):
        client, transport, clock = make({KEY: [(429, {"Retry-After": header}, {}), (200, {}, fixture("categories.json"))]}, **kw)
        result = client.list_categories()
        return result, len(transport.seen), clock.sleeps

    def test_superscript_retry_after_uses_fallback_and_recovers(self):
        result, requests, sleeps = self.one_429("\u00b2")
        self.assertEqual((len(result), requests, sleeps), (4, 2, [1]))

    def test_oversized_ascii_retry_after_clamps_before_integer_conversion(self):
        for header, wait in (("9" * 5000, 30), ("0" * 5000, 1), ("0" * 5000 + "2", 2)):
            with self.subTest(wait=wait):
                _, requests, sleeps = self.one_429(header)
                self.assertEqual((requests, sleeps), (2, [wait]))

    def test_non_ascii_and_junk_headers_use_exponential_fallback(self):
        for header in ("\u00b2\u00b3", "\u0663", "\uff12", "Wed, 21 Oct 2026 07:28:00 GMT", "+5", "1.5"):
            with self.subTest(header=header):
                _, _, sleeps = self.one_429(header)
                self.assertEqual(sleeps, [1])
        client, transport, clock = make({KEY: [(429, {"Retry-After": "\u00b2"}, {})] * 4})
        with self.assertRaises(cl.RateLimited) as ctx:
            client.list_categories()
        self.assertEqual((len(transport.seen), clock.sleeps, ctx.exception.retry_after), (4, [1, 2, 4], 8))

    def test_ascii_header_controls_and_retry_disabled_stay_compatible(self):
        for header, wait in ((" 2 ", 2), ("0", 1), ("30", 30), ("31", 30), ("999", 30), ("", 1)):
            with self.subTest(header=header):
                self.assertEqual(self.one_429(header)[2], [wait])
        client, transport, clock = make({KEY: [(429, {"Retry-After": "\u00b2"}, {})]}, max_retries=0)
        with self.assertRaises(cl.RateLimited):
            client.list_categories()
        self.assertEqual((len(transport.seen), clock.sleeps), (1, []))


if __name__ == "__main__":
    unittest.main()
