"""RF1810-10: till snapshot age is elapsed UTC time across DST changes. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_clover_reads_elapsed
"""
import unittest
from datetime import datetime, timedelta, timezone

from hass.clover import reads
from hass.tests.test_clover_mapper import items

PT = reads.PACIFIC
FALL_THEN = datetime(2026, 11, 1, 1, 5, tzinfo=PT)                      # 01:05 PDT (fold=0)
FALL_NOW = datetime(2026, 11, 1, 1, 15, fold=1, tzinfo=PT)              # 01:15 PST, 70 elapsed minutes later
SPRING_THEN = datetime(2026, 3, 8, 1, 55, tzinfo=PT)                    # 01:55 PST
SPRING_NOW = datetime(2026, 3, 8, 3, 5, tzinfo=PT)                      # 03:05 PDT, 10 elapsed minutes later


def snap(fetched_at):
    return reads.Snapshot(tuple(items().values()), fetched_at)


def state(then, now, **kw):
    return reads.freshness(snap(then), now, **kw)[0]


class ElapsedAgeTests(unittest.TestCase):
    def test_fall_back_age_is_elapsed(self):
        self.assertEqual((FALL_NOW.astimezone(timezone.utc) - FALL_THEN.astimezone(timezone.utc)), timedelta(minutes=70))
        self.assertEqual(state(FALL_THEN, FALL_NOW), "stale")

    def test_spring_forward_age_is_elapsed(self):
        self.assertEqual(state(SPRING_THEN, SPRING_NOW), "fresh")

    def test_same_instants_same_state_across_representations(self):
        pst, pdt = timezone(timedelta(hours=-8)), timezone(timedelta(hours=-7))
        for name, then, now, want in (("fall", FALL_THEN, FALL_NOW, "stale"), ("spring", SPRING_THEN, SPRING_NOW, "fresh")):
            for label, conv in (("utc", lambda d: d.astimezone(timezone.utc)), ("fixed", lambda d: d.astimezone(pdt if d.utcoffset() == timedelta(hours=-7) else pst))):
                with self.subTest(name=name, rep=label):
                    self.assertEqual(state(conv(then), conv(now)), want)
            self.assertEqual(state(then.astimezone(timezone.utc), now), want)

    def test_elapsed_thresholds_and_public_answer(self):
        now = datetime(2026, 11, 9, 15, 30, tzinfo=PT)
        sec = timedelta(seconds=1)
        for age, want in ((reads.FRESH, "fresh"), (reads.FRESH + sec, "stale"), (reads.TOO_OLD, "stale"), (reads.TOO_OLD + sec, "too-old")):
            with self.subTest(age=age):
                self.assertEqual(state(now - age, now), want)
        # 24 hours elapsed spanning fall-back is 25 wall hours: exactly at cutoff stays quotable, one second more does not.
        end = datetime(2026, 11, 2, 12, 0, tzinfo=PT)
        start = (end.astimezone(timezone.utc) - reads.TOO_OLD).astimezone(PT)
        self.assertEqual(state(start, end), "stale")
        self.assertEqual(state(start - sec, end), "too-old")
        # public answer: stale label after the repeated hour, healthy text unchanged
        self.assertEqual(reads.how_many("hass avocado", snap(FALL_THEN), FALL_NOW),
                         "Hass avocado: 40 in the till. (till count as of 1:05 am)")
        self.assertEqual(reads.how_many("hass avocado", snap(now - timedelta(minutes=5)), now), "Hass avocado: 40 in the till.")


if __name__ == "__main__":
    unittest.main()
