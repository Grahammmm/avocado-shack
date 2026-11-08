"""AV1737-07 (H04/H05): a hike start reads `Sat 2026-11-07 09:00 PST` (weekday + Pacific date/time) in proposals
(both sides of a startsAt edit, an added hike's field line) and in `status` hike lines. A bad or naive value is shown
raw and never raises; expiry and pause times keep their old format; other fields are never reformatted.
Run: python3 -B -m unittest hass.tests.test_hike_time_text -v
"""

import unittest

from hass import conversation
from hass.tests import test_status_pause as sp
from hass.tests.test_hike_ops import HIKE
from hass.tests.test_undo import H06TestCase

EXPIRES = "2026-11-02T17:10:00+00:00"
TAIL = ["Expires 2026-11-02 09:10 PST.", "Reply yes to apply, no to cancel, or send a correction."]


def _lines(*records):
    draft = {"records": [{"collection": c, "key": k, "before": b, "after": a} for c, k, b, a in records],
             "warnings": []}
    return conversation.proposal_text("ab12", draft, EXPIRES).splitlines()


def _edit(field, before, after):
    return _lines(("events", "h1", {"id": "h1", field: before}, {"id": "h1", field: after}))


class ProposalHikeTimeTests(unittest.TestCase):
    def test_edit_shows_both_sides_with_weekday(self):
        self.assertEqual(_edit("startsAt", "2026-11-07T09:00:00-08:00", "2026-11-14T10:30:00-08:00"),
                         ["Draft ab12:", "events h1: startsAt Sat 2026-11-07 09:00 PST → Sat 2026-11-14 10:30 PST"]
                         + TAIL)

    def test_dst_fall_back_hour_keeps_its_zone(self):
        self.assertEqual(conversation._hike_time("2026-11-01T01:30:00-07:00"), "Sun 2026-11-01 01:30 PDT")
        self.assertEqual(conversation._hike_time("2026-11-01T01:30:00-08:00"), "Sun 2026-11-01 01:30 PST")
        line = _edit("startsAt", "2026-11-01T01:30:00-07:00", "2026-11-01T01:30:00-08:00")[1]
        self.assertEqual(line, "this, the start time: from \ue000Sunday, Nov 1 at 1:30 am\ue001 to \ue000Sunday, Nov 1 at 1:30 am\ue001")

    def test_utc_value_reads_pacific(self):
        self.assertEqual(_edit("startsAt", "2026-07-04T16:00:00+00:00", "2026-07-04T17:00:00Z")[1],
                         "this, the start time: from \ue000Saturday, Jul 4 at 9 am\ue001 to \ue000Saturday, Jul 4 at 10 am\ue001")

    def test_naive_or_garbage_shown_raw_and_proposal_complete(self):
        for bad in ("soon", "2026-11-07T09:00", "", "2026-13-40T09:00:00-08:00"):
            with self.subTest(bad=bad):
                self.assertEqual(conversation._hike_time(bad), bad)
                self.assertEqual(_edit("startsAt", "2026-11-07T09:00:00-08:00", bad),
                                 ["Draft ab12:", f"events h1: startsAt Sat 2026-11-07 09:00 PST → {bad}"]
                                 + TAIL)
        for odd in (None, 5, ["2026-11-07T09:00:00-08:00"]):  # not a string: returned unchanged, no exception
            self.assertIs(conversation._hike_time(odd), odd)
        self.assertEqual(_edit("startsAt", 900, "soon")[1], "this, the start time: from \ue000900\ue001 to \ue000at a time I can't read\ue001")

    def test_added_from_none(self):
        self.assertEqual(_edit("startsAt", None, "2026-11-07T09:00:00-08:00")[1],
                         "this, the start time: from \ue000nothing\ue001 to \ue000Saturday, Nov 7 at 9 am\ue001")
        self.assertEqual(_edit("startsAt", "2026-11-07T09:00:00-08:00", None)[1],
                         "this, the start time: from \ue000Saturday, Nov 7 at 9 am\ue001 to \ue000nothing\ue001")

    def test_added_hike_field_line(self):
        after = {"id": "h1", "startsAt": "2026-11-07T09:00:00-08:00", "title": "Ridge walk"}
        self.assertEqual(_lines(("events", "h1", None, after)),
                         ["Draft ab12:", "events h1: new", "  id: h1", "  startsAt: Sat 2026-11-07 09:00 PST",
                          "  title: Ridge walk"] + TAIL)
        self.assertIn("  startsAt: soon", _lines(("events", "h1", None, {**after, "startsAt": "soon"})))

    def test_other_date_like_fields_untouched(self):
        iso = "2026-11-07T09:00:00-08:00"
        self.assertEqual(_edit("recap", "old", iso)[1], f"this, the recap: from \ue000old\ue001 to \ue000{iso}\ue001")
        self.assertEqual(_edit("startsat", iso, "x")[1], f"this, a detail: from \ue000{iso}\ue001 to \ue000x\ue001")  # exact field name only
        self.assertIn(f"  endsAt: {iso}", _lines(("events", "h1", None, {"endsAt": iso, "recap": iso})))
        self.assertIn(f"  recap: {iso}", _lines(("events", "h1", None, {"endsAt": iso, "recap": iso})))


class StatusHikeTimeTests(sp.StoreMixin, H06TestCase):
    hike = sp.GuestTotalTests.hike

    def test_hike_line_weekday_while_expiry_and_pause_keep_old_format(self):
        self.hike(("hike.create", HIKE))
        self.hike(("hike.create", {**HIKE, "title": "Past hike", "date": "2026-11-01"}))
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        waiting, reply = self.propose("desc")
        self.assertIn("\nExpires 2026-11-02 09:10 PST.\n", reply)
        lines = self.status()
        self.assertEqual(lines[0], "Changes: paused since 2026-11-02 09:00 PST")
        self.assertIn(f"{waiting['code']} waiting (expires 2026-11-02 09:10 PST): {waiting['summary']}", lines)
        self.assertEqual(lines[-2:], ["Hike Test hike Sat 2026-12-05 09:00 PST: guest count unavailable", sp.PAST])


if __name__ == "__main__":
    unittest.main()
