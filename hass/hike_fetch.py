"""HIKE-LOOKUP-2: the one place that makes the live map calls for the hike lookup (OpenStreetMap and USGS 3DEP).

``hass/hike_lookup.py`` has no network code; it is given a ``fetch(service, request) -> body``. This is that function for the
running Hass and for ``scripts/hike_lookup_manual.py``. Rules (docs/hass/HIKE-LOOKUP.md, question 6):

* plain HTTPS with the standard library only; no account, key or credential; no third-party client library;
* a User-Agent that names the app and a CONTACT ADDRESS THE OPERATOR CHOOSES (the ``hikeLookup.contact`` setting, or ``--contact``
  of the manual script). None is built in: ``LiveFetch`` refuses to be made without one;
* only what ``hike_lookup`` puts in a request leaves: the hike name as a search pattern and public trail coordinates;
* nothing here counts, spaces or saves: ``hike_lookup.CachedTransport`` wraps this function and does that.

Nothing in the tests calls this module's network path: they pass ``opener`` (a fake ``urlopen``) or never reach it.
"""
from __future__ import annotations

import json
import http.client
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from hass import hike_lookup as hl

ENDPOINTS = {
    "overpass": "https://overpass-api.de/api/interpreter",
    "nominatim_search": "https://nominatim.openstreetmap.org/search",
    "nominatim_reverse": "https://nominatim.openstreetmap.org/reverse",
    "elevation": "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples",
}
TIMEOUT_S = 60
CHUNK_BYTES = 65_536
MAX_BODY_BYTES = 8_000_000  # a county search is well under this; an answer past it is not read
valid_contact = hl.valid_contact


def _close(resp):
    try:
        resp.close()
    except Exception:
        pass


class LiveFetch:
    accepts_timeout = True  # ``CachedTransport`` hands it the time left of the lookup's total limit (``timeout=``)

    def __init__(self, contact, opener=urllib.request.urlopen, clock=time.monotonic):
        if valid_contact(contact) is None:
            raise ValueError("a contact address (an e-mail address or an https link) is required for the User-Agent")
        self.agent = f"avocado-shack-hass-hike-lookup/0.1 (contact: {contact})"
        self.opener = opener
        self.clock = clock

    def __call__(self, service, request, timeout=None):
        """One request. ``timeout`` (seconds, optional) is what is left of the whole lookup's limit: the request waits that long at
        most, never more than ``TIMEOUT_S``, and is not made at all when nothing is left."""
        wait = TIMEOUT_S if timeout is None else min(TIMEOUT_S, timeout)
        if wait <= 0:
            raise hl.TransportError("slow", "no time left")
        url = ENDPOINTS[service]
        data = None
        if service == "overpass":
            data = urllib.parse.urlencode({"data": request["query"]}).encode()
        elif service == "elevation":
            geometry = json.dumps({"points": request["points"], "spatialReference": {"wkid": 4326}})
            data = urllib.parse.urlencode({"geometry": geometry, "geometryType": "esriGeometryMultipoint",
                                           "returnFirstValueOnly": "true", "interpolation": "RSP_BilinearInterpolation",
                                           "f": "json"}).encode()
        else:
            url += "?" + urllib.parse.urlencode({**request, "format": "jsonv2"})
        req = urllib.request.Request(url, data=data, headers={"User-Agent": self.agent})
        deadline = self.clock() + wait  # one elapsed-time limit over connect, headers and body: a trickle cannot outlast it
        box, done, opened = {}, threading.Event(), []

        def work():  # the blocking socket work runs here so the caller can stop waiting at the deadline whatever the peer does
            try:
                with self.opener(req, timeout=wait) as resp:
                    opened.append(resp)
                    parts, size = [], 0
                    while size <= MAX_BODY_BYTES:
                        if self.clock() >= deadline:
                            raise hl.TransportError("slow", "time limit")
                        chunk = resp.read(min(CHUNK_BYTES, MAX_BODY_BYTES + 1 - size))
                        if not chunk:
                            break
                        parts.append(chunk)
                        size += len(chunk)
                    box["raw"] = b"".join(parts)
            except BaseException as exc:  # handed to the caller, which maps it below
                box["exc"] = exc
            finally:
                done.set()

        try:
            threading.Thread(target=work, daemon=True).start()
            if not done.wait(wait):  # real elapsed time: a peer that trickles bytes inside one read or one header cannot hold the chat
                for resp in opened:  # close can wait behind the worker's blocked read, so it never runs on the caller
                    threading.Thread(target=_close, args=(resp,), daemon=True).start()
                raise hl.TransportError("slow", "time limit")
            if "exc" in box:
                raise box["exc"]
            raw = box["raw"]
            if len(raw) > MAX_BODY_BYTES:
                raise hl.TransportError("bad", "answer too large")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise hl.TransportError("busy" if exc.code in (429, 503, 504) else "network", str(exc.code))
        except TimeoutError:
            raise hl.TransportError("slow")
        except urllib.error.URLError as exc:
            raise hl.TransportError("slow" if "timed out" in str(exc.reason) else "network", str(exc.reason))
        except (ValueError, RecursionError, http.client.HTTPException):
            raise hl.TransportError("bad")
        except OSError as exc:
            raise hl.TransportError("network", type(exc).__name__)
