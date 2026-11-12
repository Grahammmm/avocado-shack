#!/usr/bin/env python3
"""MANUAL SCRIPT. MAKES LIVE NETWORK CALLS. NEVER RUN BY THE TESTS OR BY CI.

HASS-HIKE-LOOKUP-1. Looks a hike name up on OpenStreetMap (Overpass, Nominatim) and USGS 3DEP elevation using
hass/hike_lookup.py, and can RECORD the answers as the offline test fixtures.

  python3 scripts/hike_lookup_manual.py --contact ADDRESS "Bishop Peak"
  python3 scripts/hike_lookup_manual.py --contact ADDRESS --record hass/tests/fixtures/hike_lookup/bishop_peak.json "Bishop Peak"

Rules it keeps (docs/hass/HIKE-LOOKUP.md, question 6):
  * plain HTTPS with the standard library only; no accounts, keys or credentials; no third-party client library;
  * a User-Agent that names the app and a contact address YOU give with --contact (none is built in);
  * a local saved-answer folder (--cache, default a private folder under ~/.cache), request spacing and per-lookup and
    per-day limits from CachedTransport;
  * only the hike name (as a search pattern) and public map coordinates are sent. No owner message, date, place or phone.
It refuses to run when CI or GITHUB_ACTIONS is set, or when it is imported by a test runner.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hass import hike_lookup as hl  # noqa: E402

ENDPOINTS = {
    "overpass": "https://overpass-api.de/api/interpreter",
    "nominatim_search": "https://nominatim.openstreetmap.org/search",
    "nominatim_reverse": "https://nominatim.openstreetmap.org/reverse",
    "elevation": "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples",
}
TIMEOUT_S = 60
KEEP_TAGS = {"name", "highway", "route", "access", "surface", "natural", "ele", "note", "description", "fixme", "warning",
             "construction", "disused:highway", "abandoned:highway", "access:note", "roundtrip", "distance", "length"}


class LiveFetch:
    def __init__(self, contact):
        self.agent = f"avocado-shack-hass-hike-lookup/0.1 (contact: {contact})"

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
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise hl.TransportError("busy" if exc.code in (429, 503, 504) else "network", str(exc.code))
        except TimeoutError:
            raise hl.TransportError("slow")
        except urllib.error.URLError as exc:
            raise hl.TransportError("slow" if "timed out" in str(exc.reason) else "network", str(exc.reason))
        except ValueError:
            raise hl.TransportError("bad")


def trim(service, body):
    """Fixtures keep only what the code reads: the named tags and geometry, the elevation values."""
    if service == "overpass" and isinstance(body, dict):
        keep = []
        for el in body.get("elements", []):
            slim = {k: el[k] for k in ("type", "id", "lat", "lon", "geometry") if k in el}
            slim["tags"] = {k: v for k, v in (el.get("tags") or {}).items() if k in KEEP_TAGS}
            if "members" in el:
                slim["members"] = [{"type": m["type"], "ref": m["ref"], "geometry": m.get("geometry", [])} for m in el["members"]]
            keep.append(slim)
        return {"elements": keep}
    if service == "elevation" and isinstance(body, dict):
        return {"samples": [{"locationId": s["locationId"], "value": s["value"]} for s in body.get("samples", [])]}
    if service == "nominatim_reverse" and isinstance(body, dict):
        return {"address": body.get("address", {}), "name": body.get("name", "")}
    return body


class Recorder:
    """Wraps a transport and remembers every answer in the fixture format."""

    def __init__(self, inner):
        self.inner, self.responses = inner, {}

    def get(self, service, request):
        resp = self.inner.get(service, request)
        self.responses[hl.request_key(service, request)] = {"retrieved": resp.retrieved.isoformat(), "request": request if service != "overpass" else {"query": request["query"]},
                                                           "body": trim(service, resp.body)}
        return resp


def main(argv=None):
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        sys.exit("hike_lookup_manual.py makes live calls and must not run in CI.")
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("name")
    ap.add_argument("--contact", required=True, help="an address the map services can reach you on (put in the User-Agent)")
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "hass-hike-lookup"))
    ap.add_argument("--record", help="write the answers as a fixture file")
    ap.add_argument("--note", default="", help="fixture note (why this name)")
    args = ap.parse_args(argv)
    cached = hl.CachedTransport(LiveFetch(args.contact), args.cache,
                                log=lambda row: print("request:", json.dumps(row), file=sys.stderr))
    cached.begin_lookup()
    recorder = Recorder(cached) if args.record else None
    transport = recorder or cached
    result = hl.lookup(args.name, transport, today=datetime.now(timezone.utc).date())
    print(voice_plain(result.reply))
    print(json.dumps({"status": result.status, "candidates": [c.record for c in result.candidates]}, indent=1, default=str))
    if args.record and recorder:
        out = {"meta": {"name": args.name, "recorded": datetime.now(timezone.utc).date().isoformat(), "provenance": "recorded live",
                        "tool": "scripts/hike_lookup_manual.py", "note": args.note, "status": result.status},
               "responses": recorder.responses}
        Path(args.record).parent.mkdir(parents=True, exist_ok=True)
        Path(args.record).write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True) + "\n", "utf-8")
        print("recorded", len(recorder.responses), "answers to", args.record, file=sys.stderr)
    return 0


def voice_plain(text):
    from hass import voice
    return voice.plain(text)


if __name__ == "__main__":
    sys.exit(main())
