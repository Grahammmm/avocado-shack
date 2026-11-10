"""RF0844-12: the community server refuses ASCII control characters inside email addresses.

The real request handler runs in-process on an OS-assigned loopback port with a scratch config and
SQLite database. Every refusal is checked against full row snapshots, not only the HTTP status.
"""
import datetime
import http.client
import importlib.util
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("community_server_rf0844_12", REPO / "storefront-mockup/community-server.py")
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

EMAIL_ERROR = "Please enter a valid email address."
CONTROLS = [chr(c) for c in range(0x20)] + ["\x7f"]
JSON_CONTROLS = ["\x00", "\x01", "\x1b", "\x7f"]


def _future(days=7):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)).isoformat()


class HelperTests(unittest.TestCase):
    def test_email_rejects_embedded_ascii_controls(self):
        for ch in CONTROLS:
            for raw in (f"gu{ch}est@example.invalid", f"guest@exa{ch}mple.invalid", f"guest@example.inv{ch}alid"):
                with self.subTest(control=f"U+{ord(ch):04X}", raw=repr(raw)):
                    with self.assertRaises(server.FormError) as caught:
                        server.email_address(raw)
                    self.assertEqual(str(caught.exception), EMAIL_ERROR)
        # Edge controls that are not whitespace are refused, never stripped into a clean address.
        for ch in ("\x00", "\x01", "\x1b", "\x7f"):
            for raw in (f"{ch}guest@example.invalid", f"guest@example.invalid{ch}"):
                with self.subTest(edge=repr(raw)), self.assertRaises(server.FormError):
                    server.email_address(raw)


class LiveHandlerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="rf0844-12-")
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "community.sqlite3"
        cfg = Path(tmp.name) / "community.json"
        cfg.write_text(json.dumps({"clubName": "Test Club", "events": [
            {"id": "open-hike", "title": "Open", "status": "scheduled", "startsAt": _future(), "meetingPoint": "Lot",
             "rsvpEnabled": True, "capacity": 10},
            {"id": "done-hike", "title": "Done", "status": "completed", "startsAt": _future(), "meetingPoint": "Lot",
             "rsvpEnabled": True, "capacity": 10},
            {"id": "closed-hike", "title": "Closed", "status": "scheduled", "startsAt": _future(), "meetingPoint": "Lot",
             "rsvpEnabled": False, "capacity": 10},
        ], "routeIdeas": []}), "utf-8")
        saved = (server.DB, server.CONFIG)
        server.DB, server.CONFIG = self.db_path, cfg
        self.addCleanup(lambda: (setattr(server, "DB", saved[0]), setattr(server, "CONFIG", saved[1])))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = httpd.server_port
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        server.connect().close()

    def post(self, path, payload):
        body = json.dumps(payload).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", path, body, {"Content-Type": "application/json",
                                              "Origin": f"http://127.0.0.1:{self.port}"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def snapshot(self):
        with sqlite3.connect(self.db_path) as db:
            return (db.execute("SELECT * FROM subscriptions ORDER BY email").fetchall(),
                    db.execute("SELECT * FROM rsvps ORDER BY id").fetchall(),
                    db.execute("SELECT event_id, SUM(party_size) FROM rsvps GROUP BY event_id ORDER BY event_id").fetchall())

    def subscribe(self, email, newsletter=True, hikes=False):
        return self.post("/api/community/subscriptions", {"email": email, "newsletter": newsletter, "hikes": hikes})

    def rsvp(self, email, event="open-hike", party=2, name="Guest"):
        return self.post("/api/community/rsvps", {"eventId": event, "email": email, "name": name, "partySize": party})

    def test_subscription_control_email_never_writes(self):
        self.assertEqual(self.subscribe("guest@example.invalid")[0], 200)
        before = self.snapshot()
        for ch in JSON_CONTROLS:
            for choice in ({"newsletter": True, "hikes": False}, {"newsletter": False, "hikes": True}):
                with self.subTest(control=f"U+{ord(ch):04X}", choice=choice):
                    status, reply = self.subscribe(f"gue{ch}st@example.invalid", **choice)
                    self.assertEqual((status, reply), (400, {"error": EMAIL_ERROR}))
                    status, reply = self.subscribe(f"guest@example.invalid{ch}", **choice)
                    self.assertEqual((status, reply), (400, {"error": EMAIL_ERROR}))
                    self.assertEqual(self.snapshot(), before)

    def test_rsvp_control_email_never_claims_places(self):
        self.assertEqual(self.rsvp("first@example.invalid", party=4)[0], 200)
        before = self.snapshot()
        for ch in JSON_CONTROLS:
            with self.subTest(control=f"U+{ord(ch):04X}"):
                self.assertEqual(self.rsvp(f"sec{ch}ond@example.invalid"), (400, {"error": EMAIL_ERROR}))
                self.assertEqual(self.rsvp(f"first@example.invalid{ch}"), (400, {"error": EMAIL_ERROR}))
                self.assertEqual(self.snapshot(), before)
        # A valid group still books, a duplicate adds nothing, and capacity still holds.
        self.assertEqual(self.rsvp("second@example.invalid", party=6)[0], 200)
        status, reply = self.rsvp(" Second@Example.Invalid ", party=1)
        self.assertEqual(status, 200)
        self.assertIs(reply.get("alreadyRegistered"), True)
        self.assertEqual(self.rsvp("third@example.invalid", party=1)[0], 409)
        self.assertEqual(self.snapshot()[2], [("open-hike", 10)])

    def test_closed_event_precedence_unchanged(self):
        before = self.snapshot()
        for event in ("no-such-hike", "done-hike", "closed-hike"):
            for email in ("bad\x00@example.invalid", "bad\x7f@example.invalid", 42):
                with self.subTest(event=event, email=repr(email)):
                    self.assertEqual(self.rsvp(email, event=event), (409, {"error": "This hike is not accepting RSVPs."}))
        self.assertEqual(self.snapshot(), before)

    def test_valid_normalization_and_boundaries_unchanged(self):
        self.assertEqual(self.subscribe("guest@example.invalid", newsletter=True, hikes=False)[0], 200)
        self.assertEqual(self.subscribe("\t  Guest@EXAMPLE.invalid \n", newsletter=False, hikes=True)[0], 200)
        rows = self.snapshot()[0]
        self.assertEqual([(r[0], r[1], r[2]) for r in rows], [("guest@example.invalid", 1, 1)])
        self.assertEqual(server.email_address(" José@Example.Invalid "), "josé@example.invalid")
        self.assertEqual(self.subscribe("josé@example.invalid")[0], 200)
        at_limit = "a" * (254 - len("@example.invalid")) + "@example.invalid"
        self.assertEqual(server.email_address(at_limit), at_limit)
        self.assertEqual(self.subscribe(at_limit)[0], 200)
        before = self.snapshot()
        for bad in ("b" + at_limit, "not-an-email", "two@@example.invalid", "", 42, None, ["guest@example.invalid"]):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(self.subscribe(bad), (400, {"error": EMAIL_ERROR}))
        # A control never maps onto the existing valid identity.
        self.assertEqual(self.subscribe("guest\x00@example.invalid"), (400, {"error": EMAIL_ERROR}))
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
