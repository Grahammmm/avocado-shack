"""AV2022-06 (H06/H17): `history` lists only the five newest owner-approved changes (in flight, applied, checked,
failed or undone); questions, proposals, cancelled and expired drafts never push them out.

Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import T0
from hass.tests.test_editor import HOURS, _req
from hass.tests.test_undo import H06TestCase

ALL_STATES = ("needs-details", "approved", "proposed", "applied", "rejected", "verified", "expired", "failed",
              "reverted")


class HistoryTestCase(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping["half"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}  # hours missing: a question

    def history(self):
        self.assertEqual(self.say("history"), "history")
        [reply] = self.replies()
        return reply

    def history_bare(self):
        """History lines without the SHOP-4 where-is-it-now suffix (" - ...")."""
        return [line.rsplit(" - ", 1)[0] for line in self.history().splitlines()]

    def insert(self, code, state, commit=None):
        self.conv.db.execute(
            "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at, \"commit\") "
            "VALUES (?, ?, '[]', ?, 'owner', 'chat', ?, ?, ?)",
            (code, state, f"summary {code}", T0.isoformat(), (T0 + timedelta(days=1)).isoformat(), commit))
        self.conv.db.commit()

    def ask(self, n):
        for _ in range(n):
            self.assertEqual(self.say("half"), "needs-details")
            self.replies()


class AppliedHistoryTests(HistoryTestCase):
    def make_previewer(self):
        return None  # no result check: an approved change stays "applied"

    def test_questions_do_not_push_out_an_applied_change(self):
        a = self.apply("desc")
        self.assertEqual(a["state"], "applied")
        self.ask(6)
        self.assertEqual(sum(d["state"] == "needs-details" for d in self.drafts()), 6)
        self.assertEqual(self.history_bare(), ["Here's what we changed lately:", f"- {a['summary']}, approved Mon Nov 2 9:00 am: saved, but I'm not sure it's on the website"])

    def test_cancelled_and_expired_drafts_do_not_push_out_an_applied_change(self):
        a = self.apply("desc")
        for _ in range(3):
            self.propose("hours")
            self.assertEqual(self.say("no"), "rejected")
            self.replies()
        self.propose("hours")
        self.ask(2)
        self.now += timedelta(seconds=600)  # the proposal and both questions lapse
        self.assertEqual(self.history_bare(), ["Here's what we changed lately:", f"- {a['summary']}, approved Mon Nov 2 9:00 am: saved, but I'm not sure it's on the website"])
        self.assertEqual(sorted({d["state"] for d in self.drafts()}), ["applied", "expired", "rejected"])


class HistoryStateTests(HistoryTestCase):
    def test_only_history_states_newest_first(self):
        for i, state in enumerate(ALL_STATES):
            self.insert(f"S{i}", state)
        lines = self.history_bare()
        self.assertEqual(lines[0], "Here's what we changed lately:")
        self.assertEqual([line.split(", ")[0] for line in lines[1:]],
                         ["- summary S8", "- summary S7", "- summary S5", "- summary S3", "- summary S1"])
        self.assertEqual(conversation.HISTORY_STATES, ("approved", "applied", "verified", "failed", "reverted"))

    def test_seven_verified_changes_show_the_newest_five(self):
        for i in range(1, 8):
            self.insert(f"V{i}", "verified", commit=f"{i:07d}abcdef")
        self.insert("Q1", "needs-details")
        lines = self.history_bare()
        self.assertEqual(len(lines), 1 + conversation.HISTORY_MAX)
        self.assertEqual(lines[1:], [f"- summary V{i}, time unknown: saved, but I'm not sure it's on the website" for i in range(7, 2, -1)])

    def test_only_questions_cancelled_and_expired_drafts(self):
        self.ask(1)
        self.assertEqual(self.say("no"), "rejected")  # cancelled question
        self.replies()
        self.ask(1)
        self.now += timedelta(seconds=600)  # this question lapses when history runs
        self.insert("E1", "expired")
        self.insert("P1", "proposed")
        self.assertEqual(self.history(), "We haven't made any changes yet.")
        self.assertEqual([d["state"] for d in self.drafts()], ["rejected", "expired", "expired", "proposed"])

    def test_empty_history(self):
        self.assertEqual(self.history(), "We haven't made any changes yet.")

    def test_history_while_paused_is_the_same_list(self):
        a, b = self.apply("desc"), self.apply("hours")
        before = self.history_bare()
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.assertEqual(self.history_bare(), before)
        self.assertEqual(before[1:], [f"- {r['summary']}, approved Mon Nov 2 9:00 am: saved, but I'm not sure it's on the website"
                                                   for r in (b, a)])

    def test_undone_change_shows_reverted_and_the_undo_shows_checked(self):
        a = self.apply("desc")
        self.assertEqual(self.say(f"undo {a['code']}"), "proposed")
        self.sent()
        self.ask(5)  # waiting questions alongside the undo proposal are never listed; yes targets the proposal
        rev = [d for d in self.drafts() if d["state"] == "proposed"][0]
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        rev = [d for d in self.drafts() if d["row_id"] == rev["row_id"]][0]
        self.assertEqual(self.history_bare()[1:],
                         [f"- {rev['summary']}, approved Mon Nov 2 9:00 am: saved, but I'm not sure it's on the website",
                          f"- {a['summary']}, approved Mon Nov 2 9:00 am: undone"])
        self.assertTrue(self.history().endswith(f"- {a['summary']}, approved Mon Nov 2 9:00 am: undone"))


if __name__ == "__main__":
    unittest.main()
