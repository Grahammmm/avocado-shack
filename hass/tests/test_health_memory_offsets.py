"""RF2345-18: health compares owner-memory forget/create times as instants, not ISO text (offsets differ)."""
import unittest
from datetime import datetime, timedelta, timezone

from hass import health, memory
from hass.tests import test_health_memory as thm

SOURCE, VALUE, Base = thm.SOURCE, thm.VALUE, thm.HealthMemoryTest

UTC = timezone.utc
FORGET = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)


class Seq:
    def __init__(self, *times):
        self.times = list(times)

    def __call__(self):
        return self.times.pop(0)


class OffsetsTest(unittest.TestCase):
    setUp, mem, sql, run_raw, run_health, broken = (Base.setUp, Base.mem, Base.sql, Base.run_raw, Base.run_health,
                                                    Base.broken)  # fixtures only, not the inherited tests

    def forgotten(self, *times):
        mem = memory.Memory(str(self.state), Seq(*times))
        self.addCleanup(mem.close)
        return mem

    def leftover(self, created, forget="2026-05-01T10:00:00+00:00"):
        mem = self.forgotten(FORGET - timedelta(hours=1), FORGET)
        mem.remember("gone.key", "x", "fact", SOURCE)
        mem.forget("gone.key")
        self.sql("UPDATE memory SET forgotten_at = ?", (forget,))
        self.sql("INSERT INTO memory(key, value, kind, source, created_at) VALUES ('gone.key', ?, 'fact', ?, ?)",
                 (VALUE, SOURCE, created))

    def test_real_reremember_in_earlier_offset_is_ok(self):
        tz = timezone(timedelta(hours=-8))
        mem = self.forgotten(datetime(2026, 5, 1, 9, 0, tzinfo=UTC), FORGET, datetime(2026, 5, 1, 4, 0, tzinfo=tz))
        mem.remember("gone.key", VALUE, "fact", SOURCE)
        mem.forget("gone.key")
        mem.remember("gone.key", VALUE + "-back", "fact", SOURCE)
        self.assertEqual(self.run_health(), (0, []))

    def test_leftover_text_with_later_offset_is_counted(self):
        self.leftover("2026-05-01T11:00:00+02:00")  # 09:00Z, before the 10:00Z forget
        self.assertEqual(self.run_health(), self.broken("1 row(s)"))

    def test_instant_boundaries(self):
        # forget is 10:00Z: the same instant counts, 1 microsecond later does not, 1 before does
        for created, code in (("2026-05-01T12:00:00+02:00", 1), ("2026-05-01T12:00:00.000001+02:00", 0),
                              ("2026-05-01T11:59:59.999999+02:00", 1), ("2026-05-01T05:00:00-05:00", 1)):
            self.assertEqual(health._at_or_after("2026-05-01T10:00:00Z", created), code, created)

    def test_equal_instant_leftover_is_counted_end_to_end(self):
        self.leftover("2026-05-01T12:00:00+02:00")
        self.assertEqual(self.run_health(), self.broken("1 row(s)"))

    def test_zoneless_operand_is_unreadable_without_text(self):
        self.leftover("2026-05-01T09:00:00")
        self.assertEqual(self.run_health(), self.broken("memory table unreadable"))

    def test_null_forget_never_matches(self):
        self.assertEqual(health._at_or_after(None, "garbage"), 0)


if __name__ == "__main__":
    unittest.main()
