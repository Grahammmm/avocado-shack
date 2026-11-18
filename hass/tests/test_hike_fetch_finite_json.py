"""RF1831-10: the live hike client refuses non-finite JSON numbers as a ``bad`` answer.

Hermetic: ``opener`` is a fake ``urlopen``; nothing is fetched.
Run: python3 -B -m unittest hass.tests.test_hike_fetch_finite_json -q
"""
import math
import unittest

from hass import hike_fetch, hike_lookup as hl

CONTACT = "mike-shack@example.invalid"


class Resp:
    def __init__(self, body):
        self.body, self.closes = body, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.closes += 1

    def read(self, n=-1):
        out, self.body = (self.body, b"") if n < 0 else (self.body[:n], self.body[n:])
        return out


class FiniteJson(unittest.TestCase):
    def fetch(self, body):
        self.calls, self.resps = 0, []

        def opener(req, timeout=None):
            self.calls += 1
            self.resps.append(Resp(body))
            return self.resps[-1]

        return hike_fetch.LiveFetch(CONTACT, opener=opener)("elevation", {"points": [[1, 2]]})

    def assertBad(self, body):
        with self.assertRaises(hl.TransportError) as ctx:
            self.fetch(body)
        self.assertEqual(ctx.exception.kind, "bad")
        return ctx.exception

    def test_nonstandard_json_constants_are_bad(self):
        for const in (b"NaN", b"Infinity", b"-Infinity"):
            for tpl in (b"%s", b'{"elevation": %s}', b'{"a": [1, {"b": %s}]}'):
                with self.subTest(body=tpl % const):
                    self.assertBad(tpl % const)

    def test_overflowing_json_exponents_are_bad(self):
        for num in (b"1e999", b"-1e999"):
            for tpl in (b"%s", b'{"elevation": %s}', b'[{"a": [%s]}]'):
                with self.subTest(body=tpl % num):
                    self.assertBad(tpl % num)

    def test_finite_numeric_and_string_controls_are_unchanged(self):
        out = self.fetch(b'{"a": 12.5, "b": -0.0, "c": 1e308, "d": 7, "e": ["NaN", "Infinity"], "f": [3]}')
        self.assertEqual(out, {"a": 12.5, "b": -0.0, "c": 1e308, "d": 7, "e": ["NaN", "Infinity"], "f": [3]})
        self.assertEqual(math.copysign(1, out["b"]), -1.0)
        self.assertEqual(self.fetch(b"12.5"), 12.5)

    def test_refused_body_closes_response_without_retry(self):
        exc = self.assertBad(b'{"canary-body": NaN}')
        self.assertEqual((self.calls, self.resps[0].closes), (1, 1))
        self.assertNotIn("canary", str(exc) + repr(exc.args))
        self.assertBad(b"{not json")
