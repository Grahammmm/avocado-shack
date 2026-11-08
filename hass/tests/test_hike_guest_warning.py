"""RF1130-6 tests: hike.cancel and hike.update turning RSVPs off warn how many confirmed guests are not told.

Reuses the test_hike_ops fixture repo and the H06 fixture conversation (throwaway Git repos, private temp state
dirs, placeholder example.invalid RSVP rows only). Nobody is notified; the warning is only a draft line.
Run: python3 -m unittest hass.tests.test_hike_guest_warning -v
"""

import sqlite3
import unittest
from unittest import mock

from hass import editor
from hass.ops import hikes
from hass.tests.test_conversation import SETTINGS, _ops
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, SCHEMA, HikeTestCase, _req
from hass.tests.test_undo import H06TestCase

THREE = f"{HIKE_ID} has 3 confirmed guests; nobody is notified automatically"
UNAVAILABLE = f"{HIKE_ID} guest count unavailable; check RSVPs before approving"
CANCEL = ("hike.cancel", {"id": HIKE_ID})
OFF = ("hike.update", {"id": HIKE_ID, "rsvpEnabled": False})


class GuestWarningTests(HikeTestCase):
    def hike_repo(self, rows=None, **extra):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, **extra}))
        if rows is not None:
            repo.make_db(rows)
        return repo

    def warnings(self, repo, *ops):
        """Warnings of a drafted request, then apply it: the warning never stops the change."""
        draft = repo.prepare(_req(*ops))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
        return draft["draft"]["warnings"]

    def test_cancel_counts_seats_and_still_cancels(self):
        repo = self.hike_repo([(HIKE_ID, 1), (HIKE_ID, 2), ("hike-2026-12-06-other", 4)])
        self.assertEqual(self.warnings(repo, CANCEL), [THREE])
        self.assertEqual(repo.event()["status"], "cancelled")

    def test_one_seat_is_singular_and_no_rsvps_warn_nothing(self):
        repo = self.hike_repo([(HIKE_ID, 1)])
        self.assertEqual(self.warnings(repo, CANCEL),
                         [f"{HIKE_ID} has 1 confirmed guest; nobody is notified automatically"])
        for rows in ([], [("hike-2026-12-06-other", 2)]):  # no RSVPs, or only for another event
            with self.subTest(rows=rows):
                self.assertEqual(self.warnings(self.hike_repo(rows), CANCEL), [])

    def test_unknown_count_still_drafts_with_a_warning(self):
        def unset(repo): pass

        def missing_file(repo): repo.use_db(str(repo.db.parent / "absent.sqlite3"))

        def no_table(repo):
            sqlite3.connect(repo.db).close()
            repo.use_db(str(repo.db))

        for name, setup in (("unset", unset), ("unreadable", missing_file), ("missing table", no_table)):
            with self.subTest(name):
                repo = self.hike_repo()
                setup(repo)
                self.assertEqual(self.warnings(repo, CANCEL), [UNAVAILABLE])
                self.assertEqual(repo.event()["status"], "cancelled")

    def test_rsvps_already_off_never_opens_the_database(self):
        repo = self.hike_repo(rsvpEnabled=False)
        repo.use_db(str(repo.db.parent / "absent.sqlite3"))  # opening it would give the unavailable warning
        with mock.patch.object(hikes, "guest_counts", wraps=hikes.guest_counts) as spy:
            self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": False, "title": "Off"})),
                             [])
            self.assertEqual(self.warnings(repo, CANCEL), [])
        spy.assert_not_called()

    def test_update_turning_rsvps_off(self):
        repo = self.hike_repo([(HIKE_ID, 1), (HIKE_ID, 2)])
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "title": "x"})), [])
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "title": "y"})), [])
        self.assertEqual(self.warnings(repo, OFF), [THREE])
        self.assertFalse(repo.event()["rsvpEnabled"])
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": False, "title": "z"})),
                         [])  # already off: no warning
        self.assertEqual(self.warnings(repo, CANCEL), [])  # off before the cancel: no second warning

    def test_off_then_cancel_in_one_request_warns_once(self):
        repo = self.hike_repo([(HIKE_ID, 1), (HIKE_ID, 2)])
        self.assertEqual(self.warnings(repo, OFF, CANCEL), [THREE])
        self.assertEqual((repo.event()["status"], repo.event()["rsvpEnabled"]), ("cancelled", False))
        self.assertEqual(repo.prepare(_req(CANCEL))["result"], "refused")  # a second cancel stays refused


class ProposalWarningTests(H06TestCase):
    def setUp(self):
        super().setUp()
        draft = editor.prepare(_req(("hike.create", HIKE)), state=str(self.repo.state), now=NOW)
        editor.apply(draft["draft"]["change_id"], draft["draft"]["draft_hash"], state=str(self.repo.state), now=NOW)
        path = self.repo.state.parent / "rsvps.sqlite3"
        db = sqlite3.connect(path)
        db.execute(SCHEMA)
        for n, party in enumerate((1, 2), 1):
            db.execute("INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)",
                       (HIKE_ID, f"walker{n}@example.invalid", f"Walker Name {n}", party, "2026-10-30T00:00:00Z"))
        db.commit()
        db.close()
        self.set_settings({**SETTINGS, "guestCountsDb": str(path)})
        self.interp.mapping.update({"call off the hike": _ops(CANCEL), "rsvps off": _ops(OFF)})
        self.conv = self.open()

    def test_proposal_shows_the_warning_and_no_guest_details(self):
        for text in ("call off the hike", "rsvps off"):
            with self.subTest(text):
                _draft, reply = self.propose(text)
                self.assertIn("\nHeads up: 3 guests have signed up, and nobody is told automatically.\n", reply)
                for secret in ("walker", "Walker Name", "example.invalid"):
                    self.assertNotIn(secret, reply)
                self.assertEqual(self.say("no"), "rejected")
                self.sent()
        draft, _reply = self.propose("call off the hike")  # a repeat of the closed draft: needs its new code
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        replies = " ".join(row["text"] for row in self.sent())
        self.assertNotIn("walker", replies.lower())
        self.assertEqual(self.drafts()[-1]["state"], "verified")


if __name__ == "__main__":
    unittest.main()
