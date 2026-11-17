"""RF1450-12: UrllibTransport closes caught HTTPError streams without reading them. Injected opener only; no sockets."""
import io
import unittest
import urllib.error
from email.message import Message
from unittest import mock

from hass.clover.client import BODY_LIMIT, HOSTS, Request
from hass.clover.transport import UrllibTransport

URL = next(iter(HOSTS.values())) + "/v3/merchants/FAKEMERCH0001/items"


class Stream(io.BytesIO):
    def __init__(self, data=b"secret body"):
        super().__init__(data)
        self.reads = 0
        self.close_calls = 0

    def read(self, *a):
        self.reads += 1
        return super().read(*a)

    def close(self):
        self.close_calls += 1
        super().close()


def http_error(code, stream, headers=None):
    msg = Message()
    for k, v in (headers or {"Location": "https://other.example/x", "X-Thing": "v"}).items():
        msg[k] = v
    return urllib.error.HTTPError(URL, code, "refused", msg, stream)


def call(opener_open):
    t = UrllibTransport()
    with mock.patch.object(t._opener, "open", side_effect=opener_open) as m:
        return t(Request("GET", URL, {"Authorization": "Bearer x"}, None)), m


class TransportCloseTests(unittest.TestCase):
    def test_http_error_stream_closed_without_body_read(self):
        for code in (302, 401, 429, 503):
            stream = Stream()
            err = http_error(code, stream)
            resp, _ = call(err_raiser(err))
            self.assertTrue(stream.closed, code)
            self.assertEqual(stream.reads, 0)
            self.assertEqual((resp.status, resp.body), (code, b""))
            self.assertEqual(resp.headers, {"location": "https://other.example/x", "x-thing": "v"})

    def test_header_conversion_failure_still_closes_error_stream(self):
        class Boom(Exception):
            pass

        stream = Stream()
        err = http_error(500, stream)
        err.headers = mock.Mock()
        err.headers.items.side_effect = Boom
        with self.assertRaises(Boom):
            call(err_raiser(err))
        self.assertTrue(stream.closed)
        self.assertEqual((stream.reads, stream.close_calls), (0, 1))

    def test_success_stream_stays_context_managed_and_bounded(self):
        stream = Stream(b"x" * (BODY_LIMIT + 50))
        reply = mock.MagicMock()
        reply.__enter__.return_value = reply
        reply.status = 200
        reply.headers = {"Content-Type": "application/json"}
        reply.read.side_effect = stream.read
        reply.__exit__.side_effect = lambda *a: stream.close()
        resp, _ = call(lambda *a, **k: reply)
        reply.read.assert_called_once_with(BODY_LIMIT + 1)
        self.assertEqual(len(resp.body), BODY_LIMIT + 1)
        self.assertEqual((resp.status, resp.headers), (200, {"content-type": "application/json"}))
        self.assertEqual(stream.close_calls, 1)

    def test_sequential_errors_release_each_retained_stream(self):
        kept = []
        t = UrllibTransport()
        for code in (429, 503, 401):
            stream = Stream()
            err = http_error(code, stream)
            kept.append((err, stream))
            with mock.patch.object(t._opener, "open", side_effect=err_raiser(err)) as m:
                t(Request("GET", URL, {}, None))
            self.assertEqual(m.call_count, 1)
            self.assertTrue(all(s.closed and s.reads == 0 for _, s in kept))


def err_raiser(err):
    def _open(*a, **k):
        raise err

    return _open


if __name__ == "__main__":
    unittest.main()
