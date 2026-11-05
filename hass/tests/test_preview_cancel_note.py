"""AV2152-07 tests (H04/H14): a cancelled hike's cancel note in the preview target and on the cancelled card.

Target tests are pure; the capture tests run the real loopback preview server and Chromium (skipped when PLAYWRIGHT_MODULE
is unset) on phone and desktop. Run: PLAYWRIGHT_MODULE=... python3 -B -m unittest hass.tests.test_preview_cancel_note -v
"""

import os
import unittest

from hass import preview
from hass.tests import test_preview_hike_results as base
from hass.tests.test_hike_ops import HikeTestCase

COMMUNITY, HikeTargetMixin = base.COMMUNITY, base.HikeTargetMixin

NOTE = "Rained out - we will pick a new date soon"
TRICKY = 'Wet & windy: "stay home" <soon> it\'s off'.replace("<soon>", "soon")


class NoteTargetTests(HikeTargetMixin, HikeTestCase):
    def test_note_target_shapes(self):
        repo = self.repo()
        hid = self.create(repo)
        noted = self.target(repo, "hike.cancel", {"id": hid, "note": NOTE})
        self.assertEqual(noted, {"kind": "event", "title": "Cass Hill", "status": "cancelled", "id": hid, "recap": "",
                                 "cancelNote": NOTE})
        self.assertEqual(list(noted), ["kind", "title", "status", "id", "recap", "cancelNote"])
        plain = self.create(repo, "Other walk")
        self.assertEqual(list(self.target(repo, "hike.cancel", {"id": plain})), ["kind", "title", "status", "id", "recap"])
        for bad in (None, 5, True, ["x"], {"a": 1}):
            with self.subTest(bad=bad):
                record = {"collection": "events", "key": "x", "after": {"title": "T", "status": "cancelled", "cancelNote": bad}}
                self.assertEqual(preview.target_for(record), {"kind": "unreadable"})


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class NoteCaptureTests(HikeTargetMixin, HikeTestCase):
    def setUp(self):
        base.HikeCaptureTests.setUp(self)
        self.viewports = ("phone", "desktop")

    def capture(self, target, files=None):
        result = preview.Previewer(self.r.wt, viewports=self.viewports).capture(files or {}, target, self.out)
        self.assertIs(result["checks"].get("noPageErrors"), True, result)
        return result

    def note_check(self, result):
        return {k: v for k, v in result["checks"].items() if k in ("rsvpGone", "cancelNoteShown")}

    def cancel(self, hid, note):
        return self.target(self.r, "hike.cancel", {"id": hid, "note": note})

    def card(self, hid):
        import json
        events = json.loads((self.r.wt / COMMUNITY).read_text("utf-8"))["events"]
        return next(e for e in events if e["id"] == hid)

    def test_cancel_note_phone_desktop_and_escape(self):
        hid, other = self.create(self.r), self.create(self.r, "Cass Hill", "2030-06-08")  # same title, another date
        target = self.cancel(hid, TRICKY)
        self.assertEqual(self.card(hid)["cancelNote"], TRICKY)
        result = self.capture(target)
        self.assertEqual((result["ok"], self.note_check(result)), (True, {"rsvpGone": True, "cancelNoteShown": True}), result)
        self.assertIsNone(self.card(other).get("cancelNote"))
        # the other same-title hike is cancelled with a different note: neither id can match the other's note
        second = self.cancel(other, NOTE)
        self.assertEqual(self.note_check(self.capture(second)), {"rsvpGone": True, "cancelNoteShown": True})
        self.assertEqual(self.note_check(self.capture(target)), {"rsvpGone": True, "cancelNoteShown": True})
        wrong = self.capture({**target, "id": other})  # the other card's note is NOTE, not TRICKY
        self.assertEqual(self.note_check(wrong), {"rsvpGone": True, "cancelNoteShown": False})
        self.assertEqual(wrong["error"], "check failed: cancelNoteShown")

    def test_no_note_cancelled_card_has_no_note_check(self):
        hid = self.create(self.r)
        target = self.target(self.r, "hike.cancel", {"id": hid})
        result = self.capture(target)
        self.assertEqual((result["ok"], self.note_check(result)), (True, {"rsvpGone": True}), result)

    def test_note_stale_missing_wrong_and_hidden_fail(self):
        hid, other = self.create(self.r), self.create(self.r, "Other walk")
        old = (self.r.wt / COMMUNITY).read_bytes()
        self.cancel(other, NOTE)
        only_other = (self.r.wt / COMMUNITY).read_bytes()  # the note is on another card only
        target = self.cancel(hid, NOTE)
        self.assertTrue(self.capture(target)["ok"])
        for name, t, files in (("stale (still scheduled)", target, {COMMUNITY: old}),
                               ("note only on another card", target, {COMMUNITY: only_other}),
                               ("wrong text", {**target, "cancelNote": "Rained out"}, None),
                               ("absent card", {**target, "id": "hike-nope", "title": "Nope"}, None),
                               ("empty note", {**target, "cancelNote": ""}, None)):
            with self.subTest(name):
                result = self.capture(t, files)
                self.assertIs(result["checks"].get("cancelNoteShown"), False, result)
                self.assertFalse(result["ok"])

    def test_hidden_note_fails(self):
        hid = self.create(self.r)
        target = self.cancel(hid, NOTE)
        js = (self.r.wt / "storefront-mockup/community.js").read_text("utf-8")
        self.assertIn('class="club-small hike-cancel-note"', js)
        hidden = js.replace('class="club-small hike-cancel-note"', 'class="club-small hike-cancel-note" hidden')
        result = self.capture(target, {"storefront-mockup/community.js": hidden.encode()})
        self.assertEqual(self.note_check(result), {"rsvpGone": True, "cancelNoteShown": False})
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
