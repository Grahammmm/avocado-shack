"""RF2355-9: answer.site reads Tues/Weds/Thur/Thurs as weekdays in the hours lines.

Run: python3 -B -m unittest hass.tests.test_site_hours_abbreviations -v
"""
import unittest

from hass.tests import test_skills_reports as rep

CANT = "I can't tell which hours apply"
DATES = {d: "2026-11-%02d" % (2 + i) for i, d in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}


def hours(lines, day):
    c = rep.site_content()
    c.store["hours"] = lines
    return rep.site("hours", c, day=DATES[day])


class HoursAbbreviations(unittest.TestCase):
    def test_probe_lines_now_answer(self):
        for lines, day, want in ((["Tues-Sat 9am-5pm", "Sun 10am-2pm"], "tuesday", "Tues-Sat 9am-5pm"),
                                 (["Mon-Weds 9-5", "Thurs-Sun 10-4"], "thursday", "Thurs-Sun 10-4"),
                                 (["Mon-Weds 9-5", "Thur-Sun 10-4"], "thursday", "Thur-Sun 10-4"),
                                 (["Weds 9-5"], "wednesday", "Weds 9-5")):
            with self.subTest(lines=lines, day=day):
                self.assertEqual(hours(lines, day), "The site says: " + want)

    def test_wrap_and_uncovered_days(self):
        lines = ["Tues-Sat 9am-5pm", "Sun 10am-2pm"]
        self.assertEqual(hours(lines, "sunday"), "The site says: Sun 10am-2pm")
        self.assertTrue(hours(lines, "monday").startswith(CANT))
        self.assertTrue(hours(["Tues-Sat 9am-5pm"], "sunday").startswith(CANT))

    def test_thurs_mon_wrap(self):
        for day in ("thursday", "friday", "saturday", "sunday", "monday"):
            with self.subTest(day=day):
                self.assertEqual(hours(["Thurs-Mon 9-5"], day), "The site says: Thurs-Mon 9-5")
        self.assertTrue(hours(["Thurs-Mon 9-5"], "tuesday").startswith(CANT))
        self.assertTrue(hours(["Thurs-Mon 9-5"], "wednesday").startswith(CANT))

    def test_words_that_only_start_with_a_day_token_do_not_count(self):
        for line in ("Thursdays only", "Monument trail"):
            with self.subTest(line=line):
                self.assertTrue(hours([line], "thursday").startswith(CANT))
                self.assertTrue(hours([line], "monday").startswith(CANT))


if __name__ == "__main__":
    unittest.main()
