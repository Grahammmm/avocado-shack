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
MAX_BODY_BYTES = 8_000_000  # a county search is well under this; an answer past it is not read
valid_contact = hl.valid_contact


class LiveFetch:
    def __init__(self, contact, opener=urllib.request.urlopen):
        if valid_contact(contact) is None:
            raise ValueError("a contact address (an e-mail address or an https link) is required for the User-Agent")
        self.agent = f"avocado-shack-hass-hike-lookup/0.1 (contact: {contact})"
        self.opener = opener

    def __call__(self, service, request):
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
        try:
            with self.opener(req, timeout=TIMEOUT_S) as resp:
                raw = resp.read(MAX_BODY_BYTES + 1)
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
