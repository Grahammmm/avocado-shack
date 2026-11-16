"""RF2345-20: answer.site reads written weekday ranges ("Monday to Friday") like dashed ranges (hass/skills/reports.py).

The interior days of a written range count, so a second schedule covering one of them keeps the complete-list fallback.
Run: python3 -B -m unittest hass.tests.test_site_hours_word_ranges -v
"""

import unittest

from hass.tests import test_skills_reports as rep

CANT = "I can't tell which hours apply that day. The site lists:\n"


def hours(lines, day):
    c = rep.site_content()
    c.store["hours"] = lines
    return rep.site("hours", c, day=day)


def listing(lines):
    return CANT + "\n".join(lines)


class WrittenRanges(unittest.TestCase):
    def test_every_word_separator_includes_interior_day(self):
        for sep in (" to ", " through ", " thru ", " till ", " until ", " TO ", " Through ", "  to  ", "\tUntil "):
            for a, b in (("Monday", "Friday"), ("Mon", "Fri"), ("monday", "FRI")):
                line = f"{a}{sep}{b} 9am–6pm"
                with self.subTest(line=line):
                    self.assertEqual(hours([line], "wednesday"), "The site says: " + line)

    def test_range_endpoints_match(self):
        line = "Monday to Friday 9am–6pm"
        for day in ("2026-11-02", "2026-11-06"):
            self.assertEqual(hours([line], day), "The site says: " + line)

    def test_range_plus_separate_wednesday_keeps_full_fallback(self):
        lines = ["Monday to Friday 9am–6pm", "Wednesday 10am–4pm", "Saturday–Sunday closed"]
        self.assertEqual(hours(lines, "wednesday"), listing(lines))
        self.assertEqual(hours(lines, "thursday"), "The site says: Monday to Friday 9am–6pm")

    def test_duplicate_matching_clauses_keep_fallback(self):
        lines = ["Monday to Friday 9am–6pm", "Mon through Fri 9am–6pm"]
        self.assertEqual(hours(lines, "wednesday"), listing(lines))

    def test_wrapping_and_same_day_ranges(self):
        line = "Friday through Monday 8am–2pm"
        for day in ("2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09"):
            self.assertEqual(hours([line], day), "The site says: " + line)
        self.assertEqual(hours([line], "tuesday"), listing([line]))
        same = ["Tuesday to Tuesday 9am–5pm"]
        self.assertEqual(hours(same, "tuesday"), "The site says: " + same[0])
        self.assertEqual(hours(same, "wednesday"), listing(same))

    def test_dash_variants_unchanged(self):
        for dash in ("-", "–", "—", " – "):
            line = f"Monday{dash}Friday 9am–6pm"
            self.assertEqual(hours([line], "wednesday"), "The site says: " + line)

    def test_and_stays_disjoint_and_glued_or_unknown_separator_adds_no_span(self):
        for line in ("Monday and Friday 9am–6pm", "MondaytoFriday 9am–6pm", "Monday toward Friday 9am–6pm",
                     "Monday or Friday 9am–6pm"):
            with self.subTest(line=line):
                self.assertEqual(hours([line], "wednesday"), listing([line]))

    def test_missing_hours_and_opaque_clauses(self):
        self.assertEqual(hours([], "wednesday"), rep.reports.NO_HOURS)
        lines = ["Monday to Friday 9am–6pm", "Ask at the gate"]
        self.assertEqual(hours(lines, "wednesday"), listing(lines))


class RealDispatch(rep.ShelfCase):
    def setUp(self):
        super().setUp()
        self.registry = rep.base.registry_of(rep.reports.ANSWER_SITE)
        self.conv = self.open()
        self.lines = ["Monday to Friday 9am–6pm", "Wednesday 10am–4pm", "Saturday–Sunday closed"]
        self.edit("store.json", lambda d: d.update(hours=self.lines))
        self.baseline = rep.snapshot_of(self)

    def test_conflicting_written_range_answers_full_fallback_without_changes(self):
        self.interp.mapping["when are we open wednesday"] = rep.base.skill_reply("answer.site", kind="hours", day="wednesday")
        self.assertEqual(self.say("when are we open wednesday"), "answer")
        self.assertEqual([rep.PLAIN(r) for r in self.replies()], [listing(self.lines)])
        self.untouched()


if __name__ == "__main__":
    unittest.main()
