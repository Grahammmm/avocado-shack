"""AV1102-05 (H17/SHOP-1) tests: `status` (and `did it work?`) shows one "Shelf check: <day>" line built from
morning_report.facts, after the Changes / Interpreter lines and before the drafts. Read-only; unreadable content
gives no shelf line and leaves every other line as it was. Same fixtures as test_status_pause (clock T0 =
Mon 2026-11-02 09:00 PST).
Run: python3 -B -m unittest hass.tests.test_status_shelf_check -v
"""

import json
import unittest
from datetime import date, datetime, timedelta, timezone

from hass import conversation, morning_report
from hass.content_model import load_content
from hass.tests.test_conversation import SETTINGS, T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

CALL = " That was more than a week ago, so the website says to call to confirm."
NOT_DONE = "I still need your shelf check."


class ShelfCheckStatusTests(StoreMixin, ConversationTestCase):
    def content_file(self, name):
        return self.repo.wt / "hass" / "content" / name

    def checked(self, day: date):
        path = self.content_file("store.json")
        path.write_text(json.dumps({**json.loads(path.read_text("utf-8")), "selection_checked_on": day.isoformat()}),
                        "utf-8")

    def shelf(self, lines):
        return [line for line in lines if (line == NOT_DONE or line.startswith("Your last shelf check"))]

    def test_not_done_yet(self):  # 1
        self.assertNotIn("selection_checked_on", json.loads(self.content_file("store.json").read_text("utf-8")))
        self.assertEqual(self.status(), ["Everything is ready.", conversation.NOTHING, NOT_DONE])

    def test_today_a_week_and_stale(self):  # 2: STALE_AFTER_DAYS = 7, so day 8 is the first stale day
        for days, line in ((0, "Your last shelf check was Monday, November 2."), (7, "Your last shelf check was Monday, October 26."),
                           (8, "Your last shelf check was Sunday, October 25." + CALL), (40, "Your last shelf check was Wednesday, September 23." + CALL)):
            with self.subTest(days=days):
                self.checked(date(2026, 11, 2) - timedelta(days=days))
                self.assertEqual(self.shelf(self.status()), [line])

    def test_dated_after_today(self):  # 3: a hand-edited store or a wrong clock is never a fresh check
        self.checked(date(2026, 11, 3))
        self.assertEqual(self.shelf(self.status()), ["Your last shelf check is dated Tuesday, November 3, which is still to come. Please check the date on the computer."])
        self.now = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)  # 20:00 PST on 2 Nov: the UTC date is not the shop day
        self.assertEqual(self.shelf(self.status()), ["Your last shelf check is dated Tuesday, November 3, which is still to come. Please check the date on the computer."])
        self.now = datetime(2026, 11, 3, 8, 1, tzinfo=timezone.utc)  # 00:01 PST on 3 Nov: now it is today
        self.assertEqual(self.shelf(self.status()), ["Your last shelf check was Tuesday, November 3."])

    def test_same_words_as_the_morning_report(self):  # 6: one source of facts, only the stale tail differs
        for day in (None, date(2026, 11, 2), date(2026, 10, 20), date(2026, 11, 9)):
            with self.subTest(day=day):
                if day:
                    self.checked(day)
                f = morning_report.facts(load_content(self.repo.wt / "hass" / "content"), date(2026, 11, 2))
                head = morning_report.render(f).splitlines()[0]
                self.assertEqual(self.shelf(self.status()), [head])
                self.assertEqual(head, morning_report.check_line(f))

    def test_unreadable_content_gives_no_shelf_line(self):  # 4
        self.propose("hours")
        self.checked(date(2026, 10, 1))
        valid = self.status()
        self.assertEqual(self.shelf(valid), ["Your last shelf check was Thursday, October 1." + CALL])
        good = {name: self.content_file(name).read_text("utf-8") for name in ("store.json", "products.json")}
        products = json.loads(good["products.json"])
        active = next(p for p in products["products"] if p.get("status") == "active")
        active["name"] = 5  # a product record the morning report cannot read (ValueError)
        for name, text in (("store.json", "{not json"), ("store.json", "[]"), ("products.json", json.dumps(products))):
            with self.subTest(name=name, text=text[:12]):
                self.content_file(name).write_text(text, "utf-8")
                self.assertEqual(self.status(), [line for line in valid if not (line == NOT_DONE or line.startswith("Your last shelf check"))])
                self.content_file(name).write_text(good[name], "utf-8")
        self.content_file("store.json").unlink()  # a missing content file
        self.assertEqual(self.status(), [line for line in valid if not (line == NOT_DONE or line.startswith("Your last shelf check"))])

    def test_paused_still_shows_it_and_sweeps_nothing(self):  # 5
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        draft, _reply = self.propose("hours")
        self.checked(date(2026, 10, 25))
        self.now = T0 + timedelta(seconds=601)  # the proposal lapsed; status must not expire it
        before = self.drafts()
        self.assertEqual(self.status(), ["Changes are paused since today at 9 am. Say resume changes when you're ready.",
                                         conversation.NOTHING, "Your last shelf check was Sunday, October 25." + CALL])
        self.assertEqual((self.drafts(), before[0]["state"], self.commits()), (before, "proposed", 0))
        self.assertEqual(self.say("did it work?"), "status")  # the same reply
        [reply] = self.replies()
        self.assertIn("Your last shelf check was Sunday, October 25." + CALL, reply.splitlines())
        self.assertEqual(self.drafts()[0]["code"], draft["code"])

    def test_once_and_before_the_first_draft(self):  # 7
        self.set_settings({**SETTINGS, "interpreterDailyCap": 5})
        self.conv = self.open()
        one, two = self.propose("hours")[0], self.propose("desc")[0]
        self.checked(date(2026, 11, 1))
        lines = self.status()
        self.assertEqual(lines[:3], ["Everything is ready.", "Waiting for your yes: the opening hours for Avocado Shack (reply yes b299)", "Waiting for your yes: the description for Hass avocado (reply yes 5717)"])
        self.assertEqual(len(self.shelf(lines)), 1)
        self.assertEqual(lines[3:], ["Your last shelf check was Sunday, November 1."])
        self.assertIn(f"reply yes {one['code']}", lines[1])
        self.assertIn(f"reply yes {two['code']}", lines[2])


if __name__ == "__main__":
    unittest.main()
