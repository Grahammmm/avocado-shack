"""RF0111-13: the shared natural-time helpers give their unreadable-time words when a real time cannot be shown in
Pacific time (the far calendar edges), instead of crashing; ordinary wording stays byte-identical.
Synthetic only: real stdlib datetime/ZoneInfo conversions, no clock patch, no state, nothing sent.
Run: python3 -B -m unittest hass.tests.test_voice_time_edges -q
"""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation, voice

UNREADABLE = "at a time I can't read"
EDGES = ("0001-01-01T00:00:00+00:00", "0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00")
NOW = datetime(2026, 11, 11, 17, 0, tzinfo=timezone.utc)  # Wednesday, Nov 11 at 9 am Pacific


class CalendarEdges(unittest.TestCase):
    def test_public_helpers_contain_real_calendar_underflow_and_overflow(self):
        for stamp in EDGES:
            at = datetime.fromisoformat(stamp)
            with self.subTest(stamp=stamp):
                with self.assertRaises(OverflowError):
                    at.astimezone(voice.LOCAL_TZ)  # the real stdlib conversion cannot represent it
                for now in (None, NOW):
                    self.assertEqual(voice.natural(at, now), UNREADABLE)
                    self.assertEqual(voice.natural_iso(stamp, now), UNREADABLE)

    def test_optional_aware_now_conversion_is_also_contained(self):
        target = datetime(2026, 11, 11, 17, 5, tzinfo=timezone.utc)
        bad_now = datetime.min.replace(tzinfo=timezone.utc)
        self.assertEqual(voice.natural(target, bad_now), UNREADABLE)
        self.assertEqual(voice.natural_iso(target.isoformat(), bad_now), UNREADABLE)
        self.assertEqual(voice.natural(target, NOW), "today at 9:05 am")
        for now in (None, datetime(2026, 11, 11, 9, 0), "2026-11-11T17:00:00+00:00", 5):
            with self.subTest(now=now):
                self.assertEqual(voice.natural(target, now), "Wednesday, Nov 11 at 9:05 am")

    def test_representable_calendar_neighbors_are_not_blanket_refused(self):
        for at in (datetime(1, 1, 2, tzinfo=timezone.utc), datetime(1, 1, 1, 12, tzinfo=timezone.utc),
                   datetime(9999, 12, 31, 12, tzinfo=timezone.utc), datetime(9999, 12, 31, 23, 59, tzinfo=timezone.utc)):
            with self.subTest(at=at):
                local = at.astimezone(voice.LOCAL_TZ)  # verified representable here, not assumed
                expected = f"{local:%A}, {local:%b} {local.day} at {voice.clock_words(local)}"
                self.assertEqual(voice.natural(at), expected)
                self.assertEqual(voice.natural_iso(at.isoformat()), expected)
                self.assertNotEqual(expected, UNREADABLE)


class OrdinaryWords(unittest.TestCase):
    def test_existing_relative_absolute_and_dst_words_are_byte_identical(self):
        utc = timezone.utc
        cases = [
            (datetime(2026, 11, 11, 22, 5, tzinfo=utc), NOW, "today at 2:05 pm"),
            (datetime(2026, 11, 12, 17, 0, tzinfo=utc), NOW, "tomorrow at 9 am"),
            (datetime(2026, 11, 10, 17, 30, tzinfo=utc), NOW, "yesterday at 9:30 am"),
            (datetime(2026, 11, 13, 17, 0, tzinfo=utc), NOW, "Friday at 9 am"),
            (datetime(2026, 11, 17, 17, 0, tzinfo=utc), NOW, "Tuesday at 9 am"),
            (datetime(2026, 11, 18, 17, 0, tzinfo=utc), NOW, "Wednesday, Nov 18 at 9 am"),
            (datetime(2026, 11, 12, 8, 0, tzinfo=utc), NOW, "tomorrow at 12 am"),
            (datetime(2026, 11, 11, 20, 0, tzinfo=utc), NOW, "today at 12 pm"),
            (datetime(2026, 11, 14, 17, 0, tzinfo=timezone(timedelta(hours=2))), None, "Saturday, Nov 14 at 7 am"),
            (datetime(2026, 11, 1, 8, 30, tzinfo=utc), datetime(2026, 11, 1, 15, tzinfo=utc), "today at 1:30 am"),  # PDT
            (datetime(2026, 11, 1, 9, 30, tzinfo=utc), datetime(2026, 11, 1, 15, tzinfo=utc), "today at 1:30 am"),  # PST
            (datetime(2026, 7, 4, 16, 0, tzinfo=utc), None, "Saturday, Jul 4 at 9 am"),
        ]
        for at, now, expected in cases:
            with self.subTest(at=at, now=now):
                self.assertEqual(voice.natural(at, now), expected)
                self.assertEqual(voice.natural_iso(at.isoformat(), now), expected)

    def test_bad_iso_and_zone_less_targets_keep_existing_result(self):
        for value in (None, "", "soon", "2026-13-01T00:00:00+00:00", 5):
            with self.subTest(value=value):
                self.assertEqual(voice.natural_iso(value), UNREADABLE)
        self.assertEqual(voice.natural_iso("2026-11-11T09:00:00"), UNREADABLE)
        self.assertEqual(voice.natural(datetime(2026, 11, 11, 9, 0), NOW), UNREADABLE)
        self.assertEqual(voice.natural("2026-11-11T17:00:00+00:00"), UNREADABLE)
        self.assertEqual(voice.check(UNREADABLE), [])


class ConversationFields(unittest.TestCase):
    def test_conversation_start_end_fields_inherit_fallback_without_zone_suffix(self):
        self.assertEqual(conversation.UNREADABLE_TIME, UNREADABLE)
        record = {"collection": "events", "after": {"title": "Hike"}}
        before = copy.deepcopy(record)
        for stamp in EDGES:
            with self.subTest(stamp=stamp):
                for field in ("startsAt", "endsAt"):
                    self.assertEqual(conversation._shown(field, stamp), UNREADABLE)
                    self.assertEqual(conversation._shown_in(record, field, stamp), UNREADABLE)
        good = "2026-11-14T17:00:00+00:00"
        self.assertEqual(conversation._shown_in(record, "startsAt", good), "Saturday, Nov 14 at 9 am (Pacific time)")
        self.assertEqual(conversation._shown_in(record, "endsAt", good), "Saturday, Nov 14 at 9 am")
        self.assertEqual(conversation._shown_in(record, "title", "0001-01-01T00:00:00+00:00"), "0001-01-01T00:00:00+00:00")
        self.assertEqual(conversation._shown("startsAt", None), "nothing")
        self.assertEqual(record, before)


if __name__ == "__main__":
    unittest.main()
