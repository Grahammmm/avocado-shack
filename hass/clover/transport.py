"""HASS-CLOVER-1: the real HTTP layer for the client, and a replay layer for rehearsals. Neither runs in this card's tests against a network.

UrllibTransport sends one request over HTTPS to an allow-listed Clover host and nothing else: it refuses any other host or scheme before
opening a socket, never follows a redirect (a redirect could carry the Authorization header to another host), has a hard timeout and
reads at most BODY_LIMIT bytes. It never logs. The build card wires it; this card only proves its refusals with sockets disabled.

ReplayTransport answers from recorded fixtures (hand-written from Clover's public docs, fake merchant id) and keeps the requests it saw.
"""
import json
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlsplit

from hass.clover.client import BODY_LIMIT, HOSTS, Request, Response

ALLOWED_NETLOCS = frozenset(urlsplit(u).netloc for u in HOSTS.values())
TIMEOUT_SECONDS = 15


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # the 3xx is returned to the caller as an error status


class UrllibTransport:
    def __init__(self, timeout=TIMEOUT_SECONDS):
        self._timeout = timeout
        # HASS-CLOVER-2: no environment proxy (the Authorization header goes to Clover's host and nowhere else) and no redirect
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)

    def __call__(self, request):
        parts = urlsplit(request.url)
        if parts.scheme != "https" or parts.netloc not in ALLOWED_NETLOCS or parts.username or parts.password:
            raise ValueError("host not allowed")  # the client turns any transport exception into a fixed "could not be reached"
        req = urllib.request.Request(request.url, data=request.body, method=request.method, headers=dict(request.headers))
        try:
            with self._opener.open(req, timeout=self._timeout) as reply:
                return Response(reply.status, _lower(reply.headers), reply.read(BODY_LIMIT + 1))
        except urllib.error.HTTPError as err:  # 4xx/5xx and refused redirects: status and headers only, the body is not read
            try:
                return Response(err.code, _lower(err.headers), b"")
            finally:
                err.close()  # release the error stream deterministically, still without reading it


def _lower(headers):
    return {k.lower(): v for k, v in headers.items()}


class ReplayTransport:
    """Answers `GET` requests from a dict {key: (status, headers, body_object)} or {key: [answer, answer, ...]} (answered in turn, the last
    one repeating). `key` is the request path and query, e.g. `/v3/merchants/FAKEMERCH0001/items?limit=1000`; the order of query
    parameters does not matter. A request with no recorded answer raises, so a test can never pass by accident on a missing fixture."""

    def __init__(self, recorded):
        self.recorded = {_norm(k): list(v) if isinstance(v, list) else [v] for k, v in recorded.items()}
        self.seen = []

    def __call__(self, request):
        self.seen.append(request)
        answers = self.recorded.get(_norm(request.url))
        if not answers:
            raise LookupError("no recorded answer")
        status, headers, body = answers.pop(0) if len(answers) > 1 else answers[0]
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        return Response(status, {k.lower(): v for k, v in headers.items()}, raw)


def _norm(url):
    parts = urlsplit(url)
    return parts.path, tuple(sorted(parse_qsl(parts.query, keep_blank_values=True)))
