"""H10: BlueBubblesPhotos, a photo source for Conversation(photos=...). Fixtures only: nothing here runs on its own.

fetch(guid, n) asks loopback BlueBubbles for one message's attachment list, then downloads the first n attachments and
returns their bytes. Same safety rules as bridge.BlueBubblesSender: loopback base URL only, no proxy, no redirect, the
password read fresh per call from a private file and sent only in the documented `password` query parameter, and no
error raised here ever carries the URL, the query, the password or a response body.
REST (docs.bluebubbles.app): GET /api/v1/message/{guid}?with=attachment -> {"data": {"attachments": [{"guid", ...}]}};
GET /api/v1/attachment/{guid}/download -> raw bytes.
"""
import json, sys, urllib.error, urllib.parse, urllib.request  # noqa: E401
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import media  # noqa: E402
from hass.bridge import LOOPBACK, BridgeError, _NoRedirect, _private_file  # noqa: E402

META_LIMIT, MAX_GUID, MAX_COUNT = 256 * 1024, 200, 10
MESSAGE_PATH, DOWNLOAD_PATH = "/api/v1/message/{}?with=attachment&", "/api/v1/attachment/{}/download?"

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)  # no proxy, no redirect


def _urllib_transport(url, headers, timeout, limit):
    """(status, body) for one GET; reads at most limit + 1 bytes so an oversized body is seen, never held whole."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status, response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, b""


def _quote(value):
    return urllib.parse.quote(value, safe="")  # one path segment: "/" and "?" never add a segment or a query


class BlueBubblesPhotos:
    """Photo source: fetch(guid, n) -> list of exactly n attachment byte strings, or BridgeError(code, status)."""
    def __init__(self, base_url, password_file, transport=None, timeout=20):
        try:  # URL rules copied from BlueBubblesSender.__init__ (bridge.py is not edited)
            parts = urllib.parse.urlsplit(base_url)
            port = parts.port
        except (TypeError, ValueError, AttributeError):
            parts, port = None, None
        if parts is None or parts.scheme not in ("http", "https") or parts.hostname not in LOOPBACK \
                or port is None or parts.username is not None or parts.password is not None \
                or parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError("base_url must be http(s)://127.0.0.1:<port> or http(s)://localhost:<port>")
        self._base = f"{parts.scheme}://{parts.hostname}:{port}"
        self._password_file = _private_file(str(password_file))
        if not (type(timeout) is int and 1 <= timeout <= 120):  # checked last: URL/password messages keep priority
            raise ValueError("timeout must be a whole number of seconds from 1 to 120")
        self._transport, self._timeout = transport or _urllib_transport, timeout

    def __repr__(self):
        return f"BlueBubblesPhotos({self._base!r})"

    def _get(self, path, accept, limit):
        """(code, status, body): code None on a 2xx within limit; the transport's error text is dropped."""
        try:
            status, body = self._transport(self._base + path, {"Accept": accept}, self._timeout, limit)
        except Exception:  # noqa: BLE001 - any transport failure; its text may hold the URL, so it is dropped
            return "transport-error", None, b""
        if not (type(status) is int and 200 <= status < 300):
            return "http-error", status if type(status) is int else None, b""
        if not isinstance(body, (bytes, bytearray)): return "transport-error", status, b""
        return ("too-large", status, b"") if len(body) > limit else (None, status, bytes(body))

    @staticmethod
    def _attachment_ids(meta, n):
        """(code, ids): the first n attachment guids from the metadata body, or a failure code."""
        try:
            doc = json.loads(meta.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            return "not-json", []
        data = doc.get("data") if isinstance(doc, dict) else None
        items = data.get("attachments") if isinstance(data, dict) else None
        if not isinstance(items, list) or not all(isinstance(a, dict) and isinstance(a.get("guid"), str)
                                                  and a["guid"] for a in items):
            return "shape", []
        head = items[:n]  # H10: only these are downloaded; each guid bounded like the message guid, and unique
        if len({a["guid"] for a in head}) < len(head) or any(
                len(a["guid"]) > MAX_GUID or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in a["guid"])
                or not (a.get("totalBytes") is None or type(a["totalBytes"]) is int and a["totalBytes"] >= 0)
                for a in head):
            return "shape", []  # a non-int (bool, str, float) or negative totalBytes is a shape error too
        if len(items) < n: return "attachment-count", []
        if any(type(a.get("totalBytes")) is int and a["totalBytes"] > media.MAX_BYTES for a in items[:n]):
            return "too-large", []  # declared too big: refused before any download
        return None, [a["guid"] for a in items[:n]]

    def fetch(self, guid, n):
        if not (isinstance(guid, str) and 0 < len(guid) <= MAX_GUID):
            raise ValueError(f"guid must be a non-empty str of at most {MAX_GUID} chars")
        if type(n) is not int or not 1 <= n <= MAX_COUNT: raise ValueError(f"n must be an int from 1 to {MAX_COUNT}")
        code, status, out = None, None, []
        try:
            password = Path(_private_file(self._password_file)).read_text("utf-8").strip()
        except (OSError, ValueError, UnicodeDecodeError):
            password = ""
        if not password:
            code = "password-unreadable"
        else:
            query = urllib.parse.urlencode({"password": password})
            code, status, meta = self._get(MESSAGE_PATH.format(_quote(guid)) + query, "application/json", META_LIMIT)
            code, ids = (code, []) if code else self._attachment_ids(meta, n)
            for aid in ids:
                code, status, data = self._get(DOWNLOAD_PATH.format(_quote(aid)) + query, "*/*", media.MAX_BYTES)
                code = code or (None if data else "empty")
                if code: break
                out.append(data)
        if code is not None:  # raised outside any except block: no __cause__ or __context__
            raise BridgeError(code, status if code == "http-error" else None)
        return out
