"""RF0721-7: hass.maker_site._http_get closes an HTTPError response explicitly, without reading it, and still returns the
same redirect / failure tuple. No network: build_opener is replaced by a fake opener, and sockets are tripwires.
Run: python3 -B -m unittest hass.tests.test_maker_site_http_errors -v
"""
import io
import socket
import unittest
import urllib.error
import urllib.request
from unittest import mock

from hass import maker_site as ms

ADDRESS = "https://harborlane.example/about"
NEXT = "https://harborlane.example/next"


class Body(io.BytesIO):
    """An in-memory response body that counts reads and closes."""

    def __init__(self, data=b"error page body"):
        super().__init__(data)
        self.reads = 0
        self.close_calls = 0

    def read(self, *args):
        self.reads += 1
        return super().read(*args)

    def close(self):
        self.close_calls += 1
        super().close()


class Budget:
    def __init__(self):
        self.releases = 0

    def left(self):
        return 10.0

    def release(self):
        self.releases += 1


class FakeOpener:
    def __init__(self, outcome):
        self.outcome = outcome
        self.opens = 0

    def open(self, request, timeout=None):
        self.opens += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def get(outcome, budget=None):
    """Run the real _http_get against a fake opener; returns (result, opener)."""
    opener = FakeOpener(outcome)
    with mock.patch.object(urllib.request, "build_opener", return_value=opener), \
            mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS")), \
            mock.patch.object(socket, "create_connection", side_effect=AssertionError("socket")):
        return ms._http_get(ADDRESS, {}, 5, budget), opener


class HttpErrorResponsesAreClosed(unittest.TestCase):
    def test_redirect_error_response_is_closed_once_without_reading(self):
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                body = Body()
                exc = urllib.error.HTTPError(ADDRESS, code, "Moved", {"Location": NEXT}, body)
                result, opener = get(exc)
                self.assertEqual(result, (code, "", b"", NEXT))
                self.assertEqual(body.close_calls, 1)
                self.assertTrue(body.closed)
                self.assertEqual(body.reads, 0)
                self.assertEqual(opener.opens, 1)

    def test_nonredirect_error_response_is_closed_and_location_not_forwarded(self):
        for code in (401, 403, 404, 429, 500):
            with self.subTest(code=code):
                body = Body()
                exc = urllib.error.HTTPError(ADDRESS, code, "No", {"Location": "https://canary.example/x"}, body)
                result, opener = get(exc)
                self.assertEqual(result, (code, "", b"", ""))
                self.assertEqual(body.close_calls, 1)
                self.assertEqual(body.reads, 0)
                self.assertEqual(opener.opens, 1)

    def test_http_error_without_fp_or_location_still_has_legacy_tuple(self):
        cases = (
            (302, {"Location": NEXT}, None, NEXT),
            (302, {}, None, ""),
            (302, {"Location": ""}, None, ""),
            (302, None, Body(), ""),
            (404, None, None, ""),
        )
        for code, headers, fp, location in cases:
            with self.subTest(code=code, headers=headers, fp=fp):
                exc = urllib.error.HTTPError(ADDRESS, code, "x", headers, fp)
                result, _ = get(exc)
                self.assertEqual(result, (code, "", b"", location))
                if fp is not None:
                    self.assertEqual(fp.close_calls, 1)

    def test_close_exception_does_not_replace_http_result_and_budget_releases(self):
        class Failing(Body):
            def close(self):
                self.close_calls += 1
                raise OSError("close canary")

        for code, location in ((302, NEXT), (500, "")):
            with self.subTest(code=code):
                body, budget = Failing(), Budget()
                exc = urllib.error.HTTPError(ADDRESS, code, "x", {"Location": NEXT}, body)
                result, opener = get(exc, budget)
                self.assertEqual(result, (code, "", b"", location))
                self.assertNotIn("canary", repr(result))
                self.assertEqual(opener.opens, 1)
                self.assertEqual(body.close_calls, 1)
                self.assertEqual(body.reads, 0)
                self.assertEqual(budget.releases, 1)

    def test_a_base_exception_from_close_is_not_swallowed(self):
        class Interrupt(Body):
            def close(self):
                raise KeyboardInterrupt

        budget = Budget()
        exc = urllib.error.HTTPError(ADDRESS, 404, "x", {}, Interrupt())
        with self.assertRaises(KeyboardInterrupt):
            get(exc, budget)
        self.assertEqual(budget.releases, 1)

    def test_success_and_transport_failure_cleanup_remain_unchanged(self):
        class Resp:
            status = 200
            headers = {"Content-Type": "text/html"}

            def __init__(self):
                self.exits = 0

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.exits += 1

            def read(self, n=-1):
                data, self.data = self.data, b""
                return data

            data = b"hello"

        resp, budget = Resp(), None
        result, _ = get(resp, budget)
        self.assertEqual(result, (200, "text/html", b"hello", ""))
        self.assertEqual(resp.exits, 1)

        for failure in (urllib.error.URLError("down"), OSError("down")):
            with self.subTest(failure=type(failure).__name__):
                budget = Budget()
                result, opener = get(failure, budget)
                self.assertEqual(result, (0, "", b"", ""))
                self.assertEqual(opener.opens, 1)
                self.assertEqual(budget.releases, 1)

        budget = Budget()
        get(Resp(), budget)
        self.assertEqual(budget.releases, 1)


if __name__ == "__main__":
    unittest.main()
