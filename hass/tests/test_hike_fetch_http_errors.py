"""RF1045-10: the live hike client closes the response body of an HTTPError, on the worker and inside the caller's deadline.

Hermetic: ``opener`` is a fake ``urlopen`` raising real ``urllib.error.HTTPError`` objects with instrumented bodies; every test
blocks sockets, so nothing is fetched.
Run: python3 -B -m unittest hass.tests.test_hike_fetch_http_errors -q
"""
import io
import json
import threading
import unittest
import urllib.error
from email.message import Message
from unittest import mock

from hass import hike_fetch, hike_lookup as hl

CONTACT = "mike-shack@example.invalid"
REQUEST = {"q": "Bishop Peak"}
BOUND = 30  # generous: an event wait only ever takes this long when the code under test is broken


class Body(io.BytesIO):
    """An error body that records every close and read."""

    def __init__(self, on_close=None):
        super().__init__(b"canary-body")
        self.close_calls, self.read_calls, self.close_threads = 0, 0, []
        self.on_close, self.entered, self.closed_event = on_close, threading.Event(), threading.Event()

    def read(self, *a):
        self.read_calls += 1
        return super().read(*a)

    def close(self):
        self.close_calls += 1
        self.close_threads.append(threading.current_thread())
        self.entered.set()
        try:
            if self.on_close:
                self.on_close()
        finally:
            self.closed_event.set()
            super().close()


def http_error(code, body):
    return urllib.error.HTTPError("https://example.invalid/x", code, "synthetic", Message(), body)


class Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        out, self.body = (self.body, b"") if n < 0 else (self.body[:n], self.body[n:])
        return out


class HttpErrors(unittest.TestCase):
    def setUp(self):
        def refuse(*_a, **_k):
            raise AssertionError("a test tried to use the network")
        for target in ("socket.socket.connect", "socket.create_connection", "socket.getaddrinfo"):
            patcher = mock.patch(target, refuse)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.release = threading.Event()
        self.addCleanup(self.release.set)  # no blocked worker outlives its test

    def client(self, opener):
        return hike_fetch.LiveFetch(CONTACT, opener=opener)

    def test_http_error_body_closed_before_busy_or_network_result(self):
        for code, kind in ((429, "busy"), (503, "busy"), (504, "busy"), (400, "network"), (500, "network")):
            with self.subTest(code=code):
                body, calls, seen = Body(), [], []

                def opener(req, timeout=None):
                    calls.append(req)
                    raise http_error(code, body)
                with self.assertRaises(hl.TransportError) as caught:
                    try:
                        self.client(opener)("nominatim_search", REQUEST)
                    finally:
                        seen.append(body.close_calls)  # state when the caller gets its answer
                self.assertEqual((caught.exception.kind, str(caught.exception)), (kind, f"{kind}: {code}"))
                self.assertEqual((seen, body.close_calls, body.read_calls, len(calls)), ([1], 1, 0, 1))

    def test_close_exception_preserves_original_http_failure(self):
        for code, kind in ((503, "busy"), (404, "network")):
            with self.subTest(code=code):
                body, calls = Body(on_close=self._raise_canary), []

                def opener(req, timeout=None):
                    calls.append(req)
                    raise http_error(code, body)
                with self.assertRaises(hl.TransportError) as caught:
                    self.client(opener)("nominatim_search", REQUEST)
                self.assertEqual((caught.exception.kind, str(caught.exception)), (kind, f"{kind}: {code}"))
                self.assertNotIn("canary", str(caught.exception))
                self.assertEqual((body.close_calls, body.read_calls, len(calls)), (1, 0, 1))

    @staticmethod
    def _raise_canary():
        raise OSError("canary-close-failure")

    def test_blocked_error_close_cannot_extend_caller_deadline(self):
        body = Body(on_close=lambda: self.release.wait(BOUND))

        def opener(req, timeout=None):
            raise http_error(500, body)
        with self.assertRaises(hl.TransportError) as caught:  # the caller's limit is 0.5 s; the close blocks until released
            self.client(opener)("nominatim_search", REQUEST, timeout=0.5)
        self.assertEqual(caught.exception.kind, "slow")
        self.assertTrue(body.entered.is_set())
        self.assertFalse(body.closed_event.is_set())  # the close is still blocked when the caller has its answer
        self.release.set()
        self.assertTrue(body.closed_event.wait(BOUND))
        self.assertEqual((body.close_calls, body.read_calls), (1, 0))
        self.assertNotIn(threading.current_thread(), body.close_threads)  # off the caller thread

    def test_http_error_arriving_after_timeout_is_still_closed(self):
        body, calls = Body(), []
        gate = threading.Event()

        def opener(req, timeout=None):
            calls.append(req)
            gate.wait(BOUND)
            raise http_error(503, body)
        self.addCleanup(gate.set)
        with self.assertRaises(hl.TransportError) as caught:
            self.client(opener)("nominatim_search", REQUEST, timeout=0.05)
        self.assertEqual(caught.exception.kind, "slow")
        self.assertEqual(body.close_calls, 0)  # the error has not arrived yet
        gate.set()
        self.assertTrue(body.closed_event.wait(BOUND))
        self.assertEqual((body.close_calls, body.read_calls, len(calls)), (1, 0, 1))
        self.assertNotIn(threading.current_thread(), body.close_threads)

    def test_success_and_non_http_failures_keep_existing_contract(self):
        ok = self.client(lambda req, timeout=None: Resp(json.dumps({"a": 1}).encode()))
        self.assertEqual(ok("nominatim_search", REQUEST), {"a": 1})
        bad = self.client(lambda req, timeout=None: Resp(b"not json"))
        with self.assertRaises(hl.TransportError) as caught:
            bad("nominatim_search", REQUEST)
        self.assertEqual(caught.exception.kind, "bad")
        big = self.client(lambda req, timeout=None: Resp(b"x" * (hike_fetch.MAX_BODY_BYTES + 1)))
        with self.assertRaises(hl.TransportError) as caught:
            big("nominatim_search", REQUEST)
        self.assertEqual(caught.exception.kind, "bad")
        for exc, kind in ((TimeoutError(), "slow"), (urllib.error.URLError("refused"), "network"),
                          (urllib.error.URLError(TimeoutError("timed out")), "slow")):
            with self.subTest(exc=type(exc).__name__):
                def opener(req, timeout=None, exc=exc):
                    raise exc
                with self.assertRaises(hl.TransportError) as caught:
                    self.client(opener)("nominatim_search", REQUEST)
                self.assertEqual(caught.exception.kind, kind)

    def test_non_http_exception_is_not_closed_as_a_response(self):
        closed = []

        class Boom(OSError):
            def close(self):
                closed.append(1)
        with self.assertRaises(hl.TransportError):
            self.client(mock.Mock(side_effect=Boom("x")))("nominatim_search", REQUEST)
        self.assertEqual(closed, [])


if __name__ == "__main__":
    unittest.main()
