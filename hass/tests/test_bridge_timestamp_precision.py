"""RF1110-12 (H08/H16) tests: bridge timestamps keep provider milliseconds, so a message after a fractional start
point is not history and same-second messages drain by instant. Synthetic fixtures, temp state, no network.
Run: python3 -B -m unittest hass.tests.test_bridge_timestamp_precision -v"""

import json, os, socket, tempfile, unittest  # noqa: E401
from datetime import datetime, timezone
from unittest import mock

from hass.bridge import Drop, EnvelopeError, normalize, seal, unseal
from hass.inbox import Inbox
from hass.tests.test_bridge import KEY, NONCE, NOW, event
from hass.tests.test_bridge_edit_ids import GUID, edit_of

BASE_MS = 1793638800000  # 2026-11-02T17:00:00Z
MAX_MS = 253402300799999  # 9999-12-31T23:59:59.999Z, the last supported instant


def at(ms, name="new-message", guid=None):
    ev = event(name)
    ev["data"]["dateCreated"] = ms
    if guid: ev["data"]["guid"] = guid
    return ev


class Recorder:
    def __init__(self): self.ids = []

    def handle(self, msg, last_try=False):
        self.ids.append(msg.provider_id)
        return "ok"


class PrecisionTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(mock.patch.stopall)
        for name in ("socket", "create_connection"):  # any network attempt fails the test
            mock.patch.object(socket, name, side_effect=AssertionError("network used")).start()
        folder = tempfile.TemporaryDirectory(prefix="hass-ts-")
        self.addCleanup(folder.cleanup)
        self.dir = folder.name
        os.chmod(self.dir, 0o700)

    def inbox(self, start, sub="state"):
        path = os.path.join(self.dir, sub)
        os.makedirs(path, mode=0o700, exist_ok=True)
        box = Inbox(path, start, clock=lambda: datetime(2026, 11, 3, tzinfo=timezone.utc))
        self.addCleanup(box.close)  # closed before the temp dir is removed (cleanups run last-in first)
        return box

    def test_creation_milliseconds_are_exact(self):
        cases = {0: "1970-01-01T00:00:00+00:00", BASE_MS: "2026-11-02T17:00:00+00:00",
                 BASE_MS + 1: "2026-11-02T17:00:00.001+00:00", BASE_MS + 100: "2026-11-02T17:00:00.100+00:00",
                 BASE_MS + 500: "2026-11-02T17:00:00.500+00:00", BASE_MS + 900: "2026-11-02T17:00:00.900+00:00",
                 BASE_MS + 999: "2026-11-02T17:00:00.999+00:00", BASE_MS + 1000: "2026-11-02T17:00:01+00:00",
                 BASE_MS + 7 * 3600000 - 1: "2026-11-02T23:59:59.999+00:00",
                 BASE_MS + 7 * 3600000: "2026-11-03T00:00:00+00:00", 1: "1970-01-01T00:00:00.001+00:00",
                 MAX_MS: "9999-12-31T23:59:59.999+00:00"}
        for ms, want in cases.items():
            with self.subTest(ms=ms):
                ev = at(ms)
                before = json.dumps(ev, sort_keys=True)
                self.assertEqual(normalize(ev).received_at, want)
                self.assertEqual(json.dumps(ev, sort_keys=True), before)
        self.assertEqual(normalize(at(MAX_MS + 1)), Drop("malformed"))  # dropped, never clamped

    def test_edits_and_reactions_use_their_existing_time_source(self):
        ev = edit_of("updated-message", BASE_MS + 70250)
        ev["data"]["dateCreated"] = BASE_MS + 60125
        first = normalize(ev)
        self.assertEqual((first.received_at, first.provider_id), ("2026-11-02T17:01:10.250+00:00",
                                                                  f"{GUID}:edited:{BASE_MS + 70250}"))
        self.assertEqual(normalize(ev), first)  # the same edit twice keeps its identity
        new = at(BASE_MS + 123)
        new["data"]["dateEdited"] = BASE_MS + 999
        self.assertEqual(normalize(new).received_at, "2026-11-02T17:00:00.123+00:00")  # dateEdited ignored
        tap = at(BASE_MS + 456, "reaction")
        self.assertEqual(normalize(tap).received_at, "2026-11-02T17:00:00.456+00:00")
        tap["type"], tap["data"]["dateEdited"] = "updated-message", BASE_MS + 9999
        updated = normalize(tap)
        self.assertEqual((updated.kind, updated.received_at), ("reaction", "2026-11-02T17:00:00.456+00:00"))
        receipt = at(BASE_MS + 5)
        receipt["type"] = "updated-message"
        self.assertEqual(normalize(receipt), Drop("receipt"))

    def test_fractional_start_point_does_not_drop_new_message(self):
        start = "2026-11-02T17:00:00.500+00:00"
        box = self.inbox(start)
        got = {ms: box.enqueue(normalize(at(BASE_MS + ms, guid=f"g{ms}"))) for ms in (499, 500, 501, 900)}
        self.assertEqual(got, {499: "history", 500: "queued", 501: "queued", 900: "queued"})
        self.assertEqual(box.enqueue(normalize(at(BASE_MS + 900, guid="g900"))), "duplicate")
        self.assertIsNone(box.db.execute("SELECT payload FROM inbound WHERE provider_id = 'g499'").fetchone()[0])
        box.close()
        again = self.inbox(None)  # reopened: same start point, history stays history
        self.assertEqual(again.start_at.isoformat(), "2026-11-02T17:00:00.500000+00:00")
        self.assertEqual([again.state(f"g{ms}") for ms in (499, 500, 501, 900)],
                         ["history", "pending", "pending", "pending"])
        self.assertEqual(again.enqueue(normalize(at(BASE_MS + 499, guid="g499"))), "duplicate")

    def test_same_second_messages_drain_by_instant_before_id(self):
        box, rec = self.inbox("2026-11-02T17:00:00+00:00"), Recorder()
        for ms, guid in ((900, "a-later"), (100, "z-earlier"), (500, "m-tie-b"), (500, "m-tie-a")):
            self.assertEqual(box.enqueue(normalize(at(BASE_MS + ms, guid=guid))), "queued")
        for ms in (300, 700):  # two edits of one guid inside one second
            box.enqueue(normalize(edit_of("updated-message", BASE_MS + ms)))
        box.drain(rec)
        self.assertEqual(rec.ids, ["z-earlier", f"{GUID}:edited:{BASE_MS + 300}", "m-tie-a", "m-tie-b",
                                   f"{GUID}:edited:{BASE_MS + 700}", "a-later"])

    def test_fractional_received_time_survives_envelope(self):
        msg, seen = normalize(at(BASE_MS + 901)), set()
        env = json.loads(json.dumps(seal(msg, KEY, nonce=NONCE, now=NOW)))
        self.assertEqual(env["ts"], NOW)
        back = unseal(env, KEY, now=NOW, seen=seen)
        self.assertEqual((back, back.received_at), (msg, "2026-11-02T17:00:00.901+00:00"))
        with self.assertRaises(EnvelopeError):
            unseal(env, KEY, now=NOW, seen=seen)  # replay is still refused

    def test_invalid_dates_still_drop(self):
        for value in (-1, -1000, True, False, "1793638800000", None, 1.5, 10 ** 30, 2 ** 63):
            with self.subTest(created=value):
                self.assertEqual(normalize(at(value)), Drop("malformed"))
        for value in (10 ** 30, 2 ** 63, MAX_MS + 1):
            with self.subTest(edited=value):
                self.assertEqual(normalize(edit_of("updated-message", value)), Drop("malformed"))


if __name__ == "__main__":
    unittest.main()
