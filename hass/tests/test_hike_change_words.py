"""AV2007-17: a hike draft says cancelled / rescheduled / scheduled again in words, not 'whether it shows: from ...'.
Products and makers keep the generic status line. Run: python3 -B -m unittest hass.tests.test_hike_change_words -v
"""
import copy
import unittest

from hass import voice
from hass.chat import wording

EXPIRES = "2026-11-02T17:10:00+00:00"
SAT, SUN = "2026-11-14T08:00:00-08:00", "2026-11-15T08:00:00-08:00"


def _rec(collection, before, after, key="k1"):
    return {"collection": collection, "key": key, "before": before, "after": after}


def _text(*records, undo=False):
    draft = {"records": list(records), "warnings": []}
    return voice.plain(wording.proposal_text("ab12", draft, EXPIRES, undo=undo)).splitlines()


def _hike(**kw):
    return {"id": "h1", "title": "Cass Hill sunrise", "startsAt": SAT, "status": "scheduled", **kw}


class HikeChangeWordsTests(unittest.TestCase):
    def test_cancelled_says_cancelled_and_keeps_the_note(self):
        lines = _text(_rec("events", _hike(), _hike(status="cancelled", cancelNote="Rain")))
        self.assertIn("Cass Hill sunrise (Saturday, Nov 14): cancelled", lines)
        self.assertTrue(any("the cancellation note: from nothing to Rain" in l for l in lines))
        self.assertNotIn("whether it shows", "\n".join(lines))

    def test_reschedule_keeps_both_pacific_times(self):
        lines = _text(_rec("events", _hike(), _hike(startsAt=SUN)))
        i = lines.index("Cass Hill sunrise (Sunday, Nov 15): rescheduled")
        self.assertEqual(lines[i + 1:i + 4], ["Cass Hill sunrise (Sunday, Nov 15), the start time:",
                                              "  was: Saturday, Nov 14 at 8 am (Pacific time)", "  now: Sunday, Nov 15 at 8 am (Pacific time)"])

    def test_undo_cancel_says_scheduled_again(self):
        lines = _text(_rec("events", _hike(status="cancelled"), _hike()), undo=True)
        self.assertIn("Cass Hill sunrise (Saturday, Nov 14): scheduled again", lines)
        self.assertNotIn("rescheduled", "\n".join(lines))
        self.assertNotIn("cancelled", "\n".join(lines))

    def test_other_status_change_keeps_generic_line(self):
        lines = _text(_rec("events", _hike(), _hike(status="completed")))
        self.assertIn("Cass Hill sunrise (Saturday, Nov 14), whether it shows: from scheduled to done", lines)

    def test_product_and_maker_status_lines_unchanged(self):
        for coll, a, b in (("products", "active", "hidden"), ("makers", "active", "cancelled")):
            with self.subTest(coll=coll):
                lines = _text(_rec(coll, {"id": "p", "name": "Thing", "status": a}, {"id": "p", "name": "Thing", "status": b}))
                self.assertTrue(any("whether it shows: from" in l for l in lines), lines)
                self.assertFalse(any(l.endswith(": cancelled") for l in lines), lines)

    def test_bad_naive_missing_time_has_no_reschedule_prefix(self):
        for bad in ("soon", "2026-11-15T08:00:00", None, "", 5):
            with self.subTest(bad=bad):
                lines = _text(_rec("events", _hike(), _hike(startsAt=bad)))
                self.assertFalse(any("rescheduled" in l for l in lines), lines)
                self.assertTrue(any("the start time" in l for l in lines), lines)

    def test_same_time_and_added_hike_do_not_claim_reschedule(self):
        same = _text(_rec("events", _hike(startsAt="2026-11-14T16:00:00+00:00"), _hike(startsAt=SAT)))
        self.assertFalse(any("rescheduled" in l for l in same), same)
        before = _hike()
        snapshot = copy.deepcopy(before)
        added = _text(_rec("events", None, before))
        self.assertTrue(any(l.startswith("A new hike") for l in added))
        self.assertFalse(any("rescheduled" in l for l in added), added)
        rec = _rec("events", _hike(), _hike(startsAt=SUN))
        self.assertEqual(_text(rec), _text(rec))
        self.assertEqual(before, snapshot)

    def test_owner_title_is_quoted_and_strict_voice_passes(self):
        title = "Ünï <b>HIKE</b> “x”"
        text = "\n".join(_text(_rec("events", _hike(title=title), _hike(title=title, status="cancelled"))))
        self.assertIn(": cancelled", text)
        self.assertNotIn("h1", text.replace("which", ""))  # no internal id


if __name__ == "__main__":
    unittest.main()
