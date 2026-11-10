"""RF1345-10: shop.hours reads independent schedules joined by "and" as separate statements (hass/skills/shop.py).

"Monday 9am–6pm and Monday 10am–4pm" is two statements about Monday, so it is a question, never a draft. "and" between
days ("Mon and Fri 9–5", "Closed Mon and Fri") and "and" before prose ("Mon 9–5 and call ahead") are not boundaries, and the
owner's display lines are never rewritten.
Run: python3 -B -m unittest hass.tests.test_skills_hours_conjunction -v
"""

import json
import types
import unittest

from hass.skills import shop
from hass.tests import test_skill_dispatch as dispatch_fixture

H0 = ["Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday"]


def ctx_for(**kw):
    return types.SimpleNamespace(today="2026-11-08", **kw)


def asks(case, hours, ctx=None):
    with case.assertRaises(shop.SkillStop) as caught:
        shop.plan_hours({"hours": hours}, ctx)
    return caught.exception.kind, caught.exception.reply


class ConjunctionSchedules(unittest.TestCase):
    def test_and_overlapping_day_range_and_closed_schedule_ask(self):
        rows = (("Monday 9am–6pm and Monday 10am–4pm", "Monday"),
                ("Mon 9am–6pm AND Closed Monday", "Monday"),
                ("Mon–Fri 9–5 and Friday 10–4", "Friday"),
                ("Mon to Sun 9 to 6 and Mon to Fri 8 to 5", "Monday"),
                ("Tue 9–5 and Mon and Fri 9–6 and Closed Fri", "Friday"))
        for line, day in rows:
            question = f"I see two different hours for {day}. Which one do you want?"
            for ctx in (None, ctx_for(store={"hours": H0}, texts=["change the hours"])):
                with self.subTest(line=line, context=ctx is not None):
                    stop = shop.check_hours_conflict({"hours": [line]}, [], ctx)
                    self.assertEqual((stop.kind, stop.reply), ("question", question))
                    self.assertEqual(asks(self, [line], ctx), ("question", question))
        # The same statement twice is not a disagreement.
        self.assertIsNone(shop.check_hours_conflict({"hours": ["Mon 9–5 and Mon 9–5"]}, [], None))

    def test_and_disjoint_schedules_expose_both_days_without_rewriting(self):
        rows = (("Mon 9am–6pm and Fri 10am–4pm", {0: ["9am–6pm"], 4: ["10am–4pm"]}),
                ("Mon 9–5 AND Fri 10–4", {0: ["9–5"], 4: ["10–4"]}),
                ("Mon–Wed 9–5, Thu 10–4 and Closed Fri", {0: ["9–5"], 1: ["9–5"], 2: ["9–5"], 3: ["10–4"], 4: ["closed"]}),
                ("Mon 9–5 and Tue 10–4, Wed 11–3", {0: ["9–5"], 1: ["10–4"], 2: ["11–3"]}))
        for line, expected in rows:
            with self.subTest(line=line):
                lines = ["", line]
                self.assertEqual(shop.hours_by_day(lines), (expected, []))
                self.assertEqual(lines, ["", line])
                self.assertTrue(all(n == 1 for n, _piece, _parsed in shop.segments_of(lines)))
                hours = [line]
                self.assertEqual(shop.plan_hours({"hours": hours}, None), [{"op": "store.set_hours", "args": {"hours": [line]}}])
                self.assertEqual(hours, [line])

    def test_grouped_days_and_prose_are_not_split(self):
        rows = (("Mon and Fri 9am–6pm", {0: ["9am–6pm"], 4: ["9am–6pm"]}, []),
                ("Closed Mon and Fri", {0: ["closed"], 4: ["closed"]}, []),
                ("Mon, Wed and Fri 9–5", {0: ["9–5"], 2: ["9–5"], 4: ["9–5"]}, []),
                ("Mon and Tue–Thu 9–5", {d: ["9–5"] for d in range(4)}, []),
                ("Mon 9–5 and call ahead", {0: ["9–5 and call ahead"]}, []),
                ("Mon 9–5 and Fri", {0: ["9–5 and Fri"]}, []),
                ("Open late and call ahead", {}, ["Open late and call ahead"]),
                ("Mondays and Fridays by appointment", {0: ["by appointment"], 4: ["by appointment"]}, []))
        for line, expected, opaque in rows:
            with self.subTest(line=line):
                self.assertEqual(shop.schedule_pieces(line), [line])
                self.assertEqual(shop.hours_by_day([line]), (expected, opaque))
                self.assertIsNone(shop.check_hours_conflict({"hours": [line]}, [], None))
        # comma, semicolon and middle dot still separate as before
        self.assertEqual(shop.schedule_pieces("Mon 9–5, Tue 10–4; Wed 11–3 · Closed Thu"),
                         ["Mon 9–5", "Tue 10–4", "Wed 11–3", "Closed Thu"])
        self.assertEqual(shop.schedule_pieces("Mon, Tue & Wed 9–5, Closed Sun"), ["Mon, Tue & Wed 9–5", "Closed Sun"])

    def test_grouped_closed_days_before_a_comma_schedule_stay_grouped(self):
        rows = (("Closed Mon and Fri, Fri 9–5", ["Closed Mon and Fri", "Fri 9–5"]),
                ("Closed Mon and Fri, Fri 9–5 and Sat 10–4", ["Closed Mon and Fri", "Fri 9–5", "Sat 10–4"]),
                ("Tue 9–5 and Closed Mon and Fri, Fri 9–5", ["Tue 9–5", "Closed Mon and Fri", "Fri 9–5"]))
        question = "I see two different hours for Friday. Which one do you want?"
        for line, pieces in rows:
            with self.subTest(line=line):
                self.assertEqual(shop.schedule_pieces(line), pieces)
                self.assertEqual(shop.hours_by_day([line])[0][4], ["closed", "9–5"])
                for ctx in (None, ctx_for(store={"hours": H0}, texts=["change the hours"])):
                    stop = shop.check_hours_conflict({"hours": [line]}, [], ctx)
                    self.assertEqual((stop.kind, stop.reply), ("question", question))
                    self.assertEqual(asks(self, [line], ctx), ("question", question))
        # Without the contradiction the same shape stays a plain two-part schedule.
        line = "Closed Mon and Fri, Sat 9–5"
        self.assertEqual(shop.schedule_pieces(line), ["Closed Mon and Fri", "Sat 9–5"])
        self.assertIsNone(shop.check_hours_conflict({"hours": [line]}, [], None))

    def test_conjunction_schedule_keeps_unnamed_days(self):
        saved = ["Mon–Thu 9–6 and Fri 9–5", "Sat 9–5 and Closed Sun"]
        said = ["Monday till 7"]
        good = ["Mon 9–7 and Tue–Thu 9–6 and Fri 9–5", "Sat 9–5 and Closed Sun"]
        self.assertTrue(shop.plan_hours({"hours": good}, ctx_for(store={"hours": saved}, texts=said)))
        for hours, question in (([good[0].replace("Fri 9–5", "Fri 9–6"), good[1]], "Do you want Friday to stay 9–5?"),
                                (["Mon 9–7 and Tue–Thu 9–6", good[1]], "Do you want Friday to stay 9–5?"),
                                ([good[0], "Sat 9–5 and Sun 10–4"], "Do you want Sunday to stay closed?"),
                                ([good[0], "Sat 9–5"], "Do you want Sunday to stay closed?")):
            with self.subTest(hours=hours):
                self.assertEqual(asks(self, hours, ctx_for(store={"hours": saved}, texts=said)), ("question", question))

    def test_conjunction_dated_closure_still_routes_to_notice(self):
        old = ["Mon 9–5 and Tue closed November 12"]
        ctx = ctx_for(store={"hours": old}, texts=["Monday 10–4"])
        self.assertTrue(shop.plan_hours({"hours": ["Mon 10–4 and Tue closed November 12"]}, ctx))
        for hours in (["Mon 10–4 and Tue closed November 13"], ["Mon 10–4 and Closed Nov 20"]):
            with self.subTest(hours=hours):
                self.assertEqual(asks(self, hours, ctx), ("question", shop.HOLIDAY_REPLY))
        self.assertEqual(shop.check_hours_holiday({"hours": ["Mon 9–5 and Tue closed November 12"]}, [], None).reply,
                         shop.HOLIDAY_REPLY)


class RealDispatcherConjunctionHours(dispatch_fixture.SkillCase):
    SKILLS = (shop.SHOP_HOURS,)

    def test_real_dispatch_asks_before_draft_and_corrected_request_can_propose(self):
        text = "Monday 9am–6pm and Monday 10am–4pm"
        hours = [text, "Tuesday–Friday 9am–6pm", H0[1]]
        self.script(text, dispatch_fixture.skill_reply("shop.hours", hours=hours))
        self.assertEqual(self.say(text), "question")
        self.assertEqual(self.replies(), ["I see two different hours for Monday. Which one do you want?"])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0], 0)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)
        self.nothing_written()
        corrected = "Monday 10am–4pm and Tuesday–Friday 9am–6pm, Saturday 9am–5pm and Closed Sunday"
        hours = ["Monday 10am–4pm and Tuesday–Friday 9am–6pm", "Saturday 9am–5pm and Closed Sunday"]
        self.script(corrected, dispatch_fixture.skill_reply("shop.hours", hours=hours))
        draft, _reply = self.propose(corrected)
        self.assertEqual(draft["state"], "proposed")
        self.assertEqual(json.loads(draft["ops_json"]), [{"op": "store.set_hours", "args": {"hours": hours}}])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
