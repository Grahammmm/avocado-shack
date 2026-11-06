"""AV2152-07 tests (H04/H14): hike.cancel takes an optional one-line public note (event cancelNote, at most 160 characters).

Ops run through the real editor on the HikeRepo fixture; claims use pure drafts. Run: python3 -B -m unittest hass.tests.test_hike_cancel_note -v
"""

import copy
import json
import unittest

from hass import claims, content_model
from hass.content_model import EVENT_TEXT_FIELDS, TEXT_LIMITS
from hass.claims import REPEAT_FIELDS
from hass.tests.test_claims import MAKERS
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase, _req

NOTE = "Rained out - we will pick a new date soon"


def cancel(**extra):
    return (("hike.cancel", {"id": HIKE_ID, **extra}),)


class CancelNoteOpTests(HikeTestCase):
    def test_cancel_note_prepare_apply_undo(self):
        repo = self.repo()
        repo.make_db([])
        repo.run(("hike.create", HIKE))
        before = repo.event()
        head = repo.head()
        draft = repo.prepare(_req(*cancel(note=NOTE)))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.head(), head)  # prepare writes nothing
        self.assertEqual(repo.event(), before)
        (record,) = draft["draft"]["records"]
        self.assertEqual((record["after"]["status"], record["after"]["cancelNote"]), ("cancelled", NOTE))
        self.assertNotIn("cancelNote", record["before"])
        applied = repo.apply(draft["draft"])
        self.assertEqual(applied["result"], "applied", applied)
        self.assertEqual(repo.event()["cancelNote"], NOTE)
        site = json.loads((repo.wt / "storefront-mockup/community.json").read_text("utf-8"))
        self.assertEqual(site["events"][0]["cancelNote"], NOTE)
        repo.run(("history.revert", {"changeId": draft["draft"]["change_id"]}))
        self.assertEqual(repo.event(), before)
        self.assertNotIn("cancelNote", repo.event())
        site = json.loads((repo.wt / "storefront-mockup/community.json").read_text("utf-8"))
        self.assertNotIn("cancelNote", site["events"][0])

    def test_cancel_note_later_edit_conflicts_with_undo(self):
        repo = self.repo()
        repo.make_db([])
        repo.run(("hike.create", HIKE))
        change = repo.run(*cancel(note=NOTE))["change_id"]
        # a later change to the same record (a second hike.create is unrelated and survives the undo)
        repo.run(("hike.create", {**HIKE, "title": "Other walk"}))
        repo.run(("history.revert", {"changeId": change}))
        self.assertNotIn("cancelNote", repo.event())
        self.assertEqual(repo.event("hike-2026-12-05-other-walk")["status"], "scheduled")

    def test_cancel_note_absent_and_boundaries(self):
        repo = self.repo()
        repo.make_db([])
        repo.run(("hike.create", HIKE))
        plain = repo.prepare(_req(*cancel()))["draft"]["records"][0]["after"]
        self.assertNotIn("cancelNote", plain)
        self.assertEqual(plain["status"], "cancelled")
        for note in ("a", "x" * 160, "😀" * 160, "e\u0301" * 80):
            with self.subTest(len=len(note)):
                self.assertEqual(repo.prepare(_req(*cancel(note=note)))["result"], "ok")
        for note in ("x" * 161, "😀" * 161, "e\u0301" * 81):
            with self.subTest(len=len(note)):
                result = self.assertRejected(repo, "refused", *cancel(note=note))
                self.assertEqual(result["reason"], "note is longer than 160 characters")

    def test_note_invalid_text(self):
        repo = self.repo()
        repo.make_db([])
        repo.run(("hike.create", HIKE))
        for bad in ("", "   ", None, True, ["x"], 5, "a\nb", "a\rb", "a\u2028b", "a\u2029b", "a\tb", "a\u200bb",
                    "<b>no</b>", "costs $5", " lead", "trail ", "{{x}}"):
            with self.subTest(bad=bad):
                result = repo.prepare(_req(*cancel(note=bad)))
                self.assertNotEqual(result["result"], "ok", result)
                self.assertEqual(repo.event()["status"], "scheduled")
        self.assertEqual(self.assertRejected(repo, "refused", *cancel(note="a\u2028b"))["reason"], "note must be one line")
        self.assertEqual(self.assertRejected(repo, "refused", *cancel(note="a\u2029b"))["reason"], "note must be one line")

    def test_cancel_note_state_and_guest_warnings(self):
        repo = self.repo()
        repo.make_db([(HIKE_ID, 2)])
        repo.run(("hike.create", HIKE))
        draft = repo.prepare(_req(*cancel(note=NOTE)))
        self.assertEqual(draft["result"], "ok")
        self.assertTrue(draft["draft"]["warnings"], draft)  # confirmed guests: the existing warning stays
        self.assertEqual(repo.prepare(_req(("hike.cancel", {"id": "hike-nope", "note": NOTE})))["result"], "not-found")
        self.assertEqual(repo.prepare(_req(("hike.cancel", {"id": "idea-x", "note": NOTE})))["result"], "not-found")
        repo.run(*cancel(note=NOTE))
        again = self.assertRejected(repo, "refused", *cancel(note="Another"))
        self.assertIn("cancelled, not scheduled", again["reason"])

    def test_note_only_cancel_argument_and_repeat_omits_it(self):
        repo = self.repo()
        repo.make_db([])
        repo.run(("hike.create", HIKE))
        for op, args in (("hike.update", {"id": HIKE_ID, "note": NOTE}), ("hike.update", {"id": HIKE_ID, "cancelNote": NOTE}),
                         ("hike.create", {**HIKE, "cancelNote": NOTE}), ("hike.complete", {"id": HIKE_ID, "note": NOTE})):
            with self.subTest(op=op, args=sorted(args)):
                self.assertNotEqual(repo.prepare(_req((op, args)))["result"], "ok")
        self.assertNotIn("cancelNote", EVENT_TEXT_FIELDS)
        self.assertNotIn("cancelNote", REPEAT_FIELDS)
        self.assertEqual(TEXT_LIMITS["event"]["cancelNote"], 160)


class ValidatorTests(HikeTestCase):
    def problems(self, **event):
        repo = self.repo()
        repo.make_db([])
        repo.run(("hike.create", HIKE))
        repo.run(*cancel())
        community = copy.deepcopy(repo.community())
        community["events"][0].update(event)
        out = []
        community.pop("schemaVersion", None)
        content_model.validate_community(out, community)
        return out

    def test_stored_note_is_validated(self):
        self.assertEqual(self.problems(cancelNote=NOTE), [])
        self.assertEqual(self.problems(cancelNote="x" * 160), [])
        self.assertTrue(any("events[0].cancelNote: longer than 160" in p for p in self.problems(cancelNote="x" * 161)))
        for bad in ("a\u2028b", "a\u2029b"):
            self.assertIn("events[0].cancelNote: must be one line", self.problems(cancelNote=bad))
        for bad in ("a\nb", "", "  ", " x", "<i>x</i>", "$5", None, 5, True, ["x"]):
            with self.subTest(bad=bad):
                self.assertTrue(any("cancelNote" in p for p in self.problems(cancelNote=bad)), bad)


class ClaimTests(unittest.TestCase):
    EVENT = {"id": HIKE_ID, "title": "Test hike", "startsAt": "2026-12-05T09:00:00-08:00", "status": "scheduled",
             "timezone": "America/Los_Angeles", "meetingPoint": "Test trailhead lot", "rsvpEnabled": True, "capacity": 12}

    def draft(self, note, op="hike.cancel"):
        after = {**self.EVENT, "status": "cancelled", "cancelNote": note}
        return {"ops": [{"op": op, "args": {"id": HIKE_ID, "note": note}}],
                "records": [{"collection": "events", "key": HIKE_ID, "before": dict(self.EVENT), "after": after}]}

    def found(self, note, owner):
        return claims.unstated(self.draft(note), owner, MAKERS, {}, {})

    def test_cancel_note_claims(self):
        field = "events %s cancelNote" % HIKE_ID
        self.assertIn((field, "organic"), self.found("Rained out - organic snacks later", "cancel the hike"))
        self.assertEqual(self.found("Rained out - organic snacks later", "cancel the hike, organic snacks later"), [])
        self.assertIn((field, "organic"), self.found("Rained out - organic snacks later", "cancel the hike, not organic"))
        self.assertEqual(self.found(NOTE, "cancel the hike, rained out"), [])
        self.assertIn((field, "6 miles"), self.found("Moved to the 6 miles loop", "cancel the hike"))
        self.assertEqual(self.found("Moved to the 6 miles loop", "cancel the hike, 6 miles loop instead"), [])

    def test_cancel_note_is_not_trusted_as_a_repeat_copy(self):
        field = "events %s cancelNote" % HIKE_ID
        new = {**self.EVENT, "id": "hike-2027-03-13-test-hike", "cancelNote": "Organic snacks"}
        source = {**self.EVENT, "cancelNote": "Organic snacks"}
        draft = {"ops": [{"op": "hike.repeat", "args": {"id": HIKE_ID, "date": "2027-03-13", "time": "09:00"}}],
                 "records": [{"collection": "events", "key": new["id"], "before": None, "after": new}]}
        found = claims.unstated(draft, "same hike again", MAKERS, {}, {HIKE_ID: source})
        self.assertIn(("events %s cancelNote" % new["id"], "organic"), found)
        self.assertNotIn(field, [w for w, _ in found])


if __name__ == "__main__":
    unittest.main()
