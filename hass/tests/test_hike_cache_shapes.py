"""RF1201-13: a saved map answer with the wrong envelope shape is a cache miss, not a crash."""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import hike_lookup as hl

FIX = Path(__file__).resolve().parent / "fixtures" / "hike_lookup"
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
BODY = {"elements": []}
REQ = {"query": "x"}
KEY = hl.request_key("overpass", REQ)

BAD_ENVELOPES = {
    "null-root": "null", "list-root": "[]", "array-root": '[{"body": 1, "retrieved": "2026-11-09"}]',
    "number-root": "7", "bool-root": "true", "string-root": '"saved"',
    "null-date": json.dumps({"body": BODY, "retrieved": None}), "list-date": json.dumps({"body": BODY, "retrieved": ["2026-11-09"]}),
    "object-date": json.dumps({"body": BODY, "retrieved": {}}), "number-date": json.dumps({"body": BODY, "retrieved": 20261109}),
    "bool-date": json.dumps({"body": BODY, "retrieved": True}),
}


class Base(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket.connect", "socket.create_connection", "socket.getaddrinfo"):
            p = mock.patch(target, mock.Mock(side_effect=AssertionError("network")))
            p.start()
            self.addCleanup(p.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.calls = []

    def fetch(self, service, request):
        self.calls.append(service)
        return {"fetched": True}

    def transport(self, fetch=None, **kw):
        return hl.CachedTransport(fetch or self.fetch, self.folder, now=lambda: NOW, sleep=lambda s: None, **kw)

    def seed(self, text, key=KEY):
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / (key.replace(":", "-") + ".json")
        path.write_text(text, "utf-8")
        return path

    def count(self):
        return json.loads((self.folder / hl.COUNT_FILE).read_text("utf-8"))["counts"].get("2026-11-09", 0)


class Shapes(Base):
    def test_wrong_root_and_date_types_are_cache_misses(self):
        t = self.transport()
        for name, text in BAD_ENVELOPES.items():
            self.seed(text)
            self.assertIsNone(t._read(KEY), name)
        for name, text in {"missing-key": '{"retrieved": "2026-11-09"}', "bad-date": '{"body": 1, "retrieved": "nope"}',
                           "syntax": "{not json"}.items():
            self.seed(text)
            self.assertIsNone(t._read(KEY), name)
        self.seed(json.dumps({"body": BODY, "retrieved": "2026-11-09"}))
        self.assertEqual(t._read(KEY), (BODY, date(2026, 11, 9)))

    def test_bad_envelope_refreshes_and_then_reuses_saved_answer(self):
        other = self.seed('{"keep": "me"}', "overpass:other")
        other_bytes = other.read_bytes()
        for name, text in BAD_ENVELOPES.items():
            with self.subTest(name):
                self.calls.clear()
                path = self.seed(text)
                t = self.transport()
                before = t.day_count(NOW.date())
                got = t.get("overpass", REQ)
                self.assertEqual((got.body, got.retrieved, got.stale), ({"fetched": True}, NOW.date(), False))
                self.assertEqual(self.calls, ["overpass"])
                self.assertEqual(json.loads(path.read_text("utf-8"))["body"], {"fetched": True})
                self.assertEqual(t.day_count(NOW.date()), before + 1)
                again = t.get("overpass", REQ)
                self.assertEqual((again.body, again.stale), ({"fetched": True}, False))
                self.assertEqual(self.calls, ["overpass"])
                self.assertEqual(other.read_bytes(), other_bytes)

    def test_bad_saved_answer_cannot_be_used_as_stale_fallback(self):
        for kind in ("network", "slow", "busy"):
            for name in ("null-root", "null-date"):
                with self.subTest(kind=kind, name=name):
                    text = BAD_ENVELOPES[name]
                    path = self.seed(text)

                    def down(service, request, kind=kind):
                        raise hl.TransportError(kind, "down")
                    with self.assertRaises(hl.TransportError) as ctx:
                        self.transport(down).get("overpass", REQ)
                    self.assertEqual(ctx.exception.kind, kind)
                    self.assertEqual(path.read_text("utf-8"), text)

    def test_real_lookup_failure_with_bad_cache_is_the_unavailable_reply(self):
        self.seed(BAD_ENVELOPES["list-root"], hl.request_key("overpass", {"query": hl.overpass_query(hl.name_tokens("Bishop Peak"))}))

        def down(service, request):
            raise hl.TransportError("network", "down")
        result = hl.lookup("Bishop Peak", self.transport(down), today=date(2026, 11, 9))
        self.assertEqual((result.status, result.candidates), ("unavailable", ()))

    def test_bad_cache_does_not_bypass_budget(self):
        path = self.seed(BAD_ENVELOPES["number-root"])
        t = self.transport(per_day=0)
        with self.assertRaises(hl.TransportError) as ctx:
            t.get("overpass", REQ)
        self.assertEqual(ctx.exception.kind, "budget")
        self.assertEqual((self.calls, path.read_text("utf-8")), ([], BAD_ENVELOPES["number-root"]))
        t2 = self.transport(per_lookup=1)  # permitted control
        t2.begin_lookup()
        self.assertEqual(t2.get("overpass", REQ).body, {"fetched": True})
        self.assertEqual(self.calls, ["overpass"])

    def test_healthy_saved_and_expired_fallback_unchanged(self):
        self.seed(json.dumps({"body": [1, 2], "retrieved": "2026-11-09"}))
        got = self.transport().get("overpass", REQ)
        self.assertEqual((got.body, got.stale, self.calls), ([1, 2], False, []))
        old = (NOW.date() - timedelta(days=hl.LIFETIME_DAYS["overpass"] + 5)).isoformat()
        self.seed(json.dumps({"body": None, "retrieved": old}))

        def down(service, request):
            raise hl.TransportError("network", "down")
        got = self.transport(down).get("overpass", REQ)
        self.assertEqual((got.body, got.retrieved.isoformat(), got.stale), (None, old, True))


class RealLookup(Base):
    def test_real_lookup_recovers_from_bad_overpass_cache(self):
        fx = hl.FixtureTransport(FIX / "bishop_peak.json")

        def raw(service, request):
            self.calls.append(service)
            return fx.get(service, request).body
        tokens = hl.name_tokens("Bishop Peak")
        key = hl.request_key("overpass", {"query": hl.overpass_query(tokens)})
        today = date(2026, 11, 9)
        clean = hl.lookup("Bishop Peak", hl.CachedTransport(raw, self.folder / "clean", now=lambda: NOW, sleep=lambda s: None), today=today)
        for name in ("null-root", "list-date"):
            with self.subTest(name):
                self.calls.clear()
                folder = self.folder / name
                self.folder = folder
                self.seed(BAD_ENVELOPES[name], key)
                t = hl.CachedTransport(raw, folder, now=lambda: NOW, sleep=lambda s: None)
                result = hl.lookup("Bishop Peak", t, today=today)
                self.assertEqual((result.status, len(result.candidates)), ("one", 1))
                self.assertEqual(result.reply, clean.reply)
                a, b = result.candidates[0], clean.candidates[0]
                self.assertEqual((a.miles, a.gain_ft, a.retrieved), (b.miles, b.gain_ft, b.retrieved))
                n = len(self.calls)
                self.assertEqual(self.calls.count("overpass"), 1)
                hl.lookup("Bishop Peak", hl.CachedTransport(raw, folder, now=lambda: NOW, sleep=lambda s: None), today=today)
                self.assertEqual(len(self.calls), n)


if __name__ == "__main__":
    unittest.main()
