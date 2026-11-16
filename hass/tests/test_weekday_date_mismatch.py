"""AV2007-10 (QA2-02): a weekday that disagrees with the date beside it ('friday nov 14') is asked, never drafted as a Saturday.

Fixed clocks only (T0 is Monday 2026-11-02, so Friday reads as Nov 6 or Oct 30): no wall clock, no socket, no model call. Scripted replies are labelled synthetic.
Run: python3 -B -m unittest hass.tests.test_weekday_date_mismatch -q
"""

import unittest
from datetime import date

from hass import conversation, nl_prep
from hass.skills import kinds
from hass.tests.test_conversation import _ops
from hass.tests.test_hike_flow import LIVE1, MILL, FlowCase

TODAY = date(2026, 11, 9)
ASK_FRI = "You said Friday, but November 14 is a Saturday. Which day?"
ASK_SAT = "You said Saturday, but November 20 is a Friday. Which day?"


def rows(text, today=TODAY):
    return nl_prep.date_hints(text, today)[0]


class PairingTests(unittest.TestCase):
    def test_both_orders_and_both_readings(self):
        for text, ask, readings in (("friday nov 14", ASK_FRI, ["2026-11-13", "2026-11-06"]), ("nov 14 friday", ASK_FRI, ["2026-11-13", "2026-11-06"]),
                                    ("Sat the 20th", ASK_SAT, ["2026-11-14", "2026-11-07"]), ("the 20th Sat", ASK_SAT, ["2026-11-14", "2026-11-07"])):
            with self.subTest(text=text):
                [row] = rows(text)  # one paired row, no second standalone weekday row
                self.assertTrue(row["weekday_mismatch"])
                self.assertEqual(row["weekday_dates"], readings)
                self.assertEqual(nl_prep.weekday_mismatch_question(row), ask)
                self.assertEqual(kinds.day(text, TODAY).reply, ask)  # never a picked day

    def test_matching_explicit_pair_is_not_a_mismatch(self):
        for text in ("saturday nov 14", "nov 14 saturday", "Sat the 14th"):
            with self.subTest(text=text):
                [row] = rows(text)
                self.assertEqual((row["date"], "weekday_mismatch" in row), ("2026-11-14", False))
                self.assertEqual(kinds.day(text, TODAY).value, "2026-11-14")
        self.assertEqual(kinds.day("next saturday the 21st", TODAY).value, "2026-11-21")
        self.assertEqual(len(rows("next saturday")[0].get("unclear")), 2)  # bare next Saturday keeps both readings

    def test_invalid_or_unrelated_mentions_do_not_pair(self):
        for text in ("friday feb 30", "friday and nov 14", "friday. we close early. nov 14", "nov 14 friday nov 15"):
            with self.subTest(text=text):
                self.assertFalse(any(r.get("weekday_mismatch") for r in rows(text)), text)
        self.assertEqual(len(rows("friday and nov 14")), 2)  # independent mentions stay independent

    def test_pacific_day_and_hint_cap(self):
        self.assertEqual(nl_prep.weekday_mismatches("friday dec 31", date(2026, 12, 31))[0]["date"], "2026-12-31")
        self.assertEqual(nl_prep.weekday_mismatches("friday dec 31", date(2027, 1, 1)), [])  # Pacific New Year: Dec 31 is now 2027's Friday
        text = "friday nov 14, also " + ", ".join(f"2026-12-{d:02d}" for d in range(1, 11))
        self.assertTrue(rows(text)[0]["weekday_mismatch"])  # the contradiction is not cut by the eight-hint cap
        self.assertEqual(len(nl_prep.weekday_mismatches(text, TODAY)), 1)


class DraftTests(FlowCase):
    def setUp(self):
        super().setUp()
        self.prepared = 0
        real = self.editor.prepare

        def counted(ops):
            self.prepared += 1
            return real(ops)
        self.editor.prepare = counted

    def script(self, text, reply):
        self.interp.mapping[text] = reply

    def test_three_protected_ops_and_mixed_batch_stop_before_prepare(self):
        notice = {"text": "Closed early", "from": "2026-11-06", "until": "2026-11-14"}
        for n, (said, op) in enumerate((("add a hike friday nov 14 at 8am cass hill gate", ("hike.create", {**MILL, "date": "2026-11-14"})),
                                        ("add a hike friday nov 14 at 8am cass hill gate", ("hike.create", {**MILL, "date": "2026-11-06"})),
                                        ("notice: closed friday nov 14", ("store.set_notice", notice)),
                                        ("notice: closed friday nov 14", ("store.set_notice", {**notice, "from": "2026-11-06", "until": "2026-11-20"})))):
            with self.subTest(n=n):
                self.script(said, _ops(op))
                self.assertEqual(self.say(said, pid=f"x{n}"), "question")
                self.assertEqual(self.replies(), [ASK_FRI])
        mixed = "friday nov 14 hike and a notice"
        self.script(mixed, _ops(("hike.create", {**MILL, "date": "2026-11-14"}), ("store.set_notice", {**notice, "from": "2026-11-20", "until": "2026-11-21"})))
        self.assertEqual(self.say(mixed), "question")
        self.assertEqual(self.replies(), [ASK_FRI])
        self.assertEqual((self.prepared, self.drafts()), (0, []))
        self.nothing_written()
        update = _ops(("hike.update", {"id": "x", "date": "2026-11-06"}))
        self.assertEqual(self.conv._weekday_conflict(conversation.Inbound("u", "c", "o", "move it to friday nov 14", False, "new", self.now.isoformat()), self.now, update, []), ASK_FRI)

    def test_matching_and_unrelated_dates_still_draft_and_keep_other_proposals(self):
        self.script("add a hike saturday nov 14 at 8am", _ops(("hike.create", {**MILL, "date": "2026-11-14"})))
        self.script("add a hike friday nov 14 at 8am", _ops(("hike.create", {**MILL, "date": "2026-11-21"})))  # a date outside both readings
        before, _reply = self.propose("add a hike saturday nov 14 at 8am")
        self.assertEqual(self.say("add a hike friday nov 14 at 8am"), "proposed")
        self.assertEqual(self.drafts()[0]["code"], before["code"])

    def test_question_leaves_existing_proposal_alone(self):
        self.propose(LIVE1)
        before, count = self.drafts(), self.prepared
        self.script("friday nov 14", _ops(("hike.update", {"id": "none", "date": "2026-11-14"})))
        self.script("change it to friday nov 14", _ops(("hike.update", {"id": "none", "date": "2026-11-14"})))
        self.assertEqual(self.say("change it to friday nov 14"), "question")
        self.assertEqual((self.drafts(), self.prepared, self.replies()[-1]), (before, count, ASK_FRI))
        self.assertEqual(self.say("friday nov 14", pid="dup"), "question")
        self.replies()
        self.assertEqual(self.say("friday nov 14", pid="dup"), "duplicate")  # a duplicate delivery changes nothing
        self.assertEqual((self.replies(), self.drafts(), self.prepared), ([], before, count))

    def test_continuation_can_choose_either_day(self):
        first = "add a hike friday nov 14 at cass hill gate"
        self.script(first, {"question": "What time?"})
        self.script("8am", _ops(("hike.create", {**MILL, "date": "2026-11-14"})))  # synthetic: the model keeps the Saturday
        self.script("friday the 13th at 8am", _ops(("hike.create", {**MILL, "date": "2026-11-13"})))
        self.assertEqual(self.say(first), "question")
        self.assertEqual(self.say("8am"), "question")  # a time-only answer does not erase the conflict
        self.assertEqual(self.replies()[-1], ASK_FRI)
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.say("friday the 13th at 8am"), "proposed")  # a clear day answer: ordinary approval, nothing applied
        self.assertEqual((len(self.drafts()), self.commits()), (1, 0))


if __name__ == "__main__":
    unittest.main()
