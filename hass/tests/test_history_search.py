"""AV2152-02 (H06/H17): `history <words>` lists up to 10 owner-approved changes whose summary holds every word.
Run: python3 -B -m unittest hass.tests.test_history_search -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import STRANGER, T0
from hass.tests.test_history_approved import HistoryTestCase
from hass.tests.test_status_pause import StoreMixin

USAGE = "Tell me a word or two to look for, like history opening hours."


class ParserTests(unittest.TestCase):
    def test_parser_examples_and_lookalikes(self):
        parse = conversation.parse_command
        for text in ("history", " HISTORY ", "History.", "history!", "history  "):
            self.assertEqual(parse(text), ("history", None), text)
        self.assertEqual(parse("  History Opening HOURS!  "), ("history", "Opening HOURS"))
        self.assertEqual(parse("history !!!"), ("history", ""))
        self.assertEqual(parse("history a\nb"), ("history", "a\nb"))
        for text in ("historybook", "please history hours", "histories"):
            self.assertIsNone(parse(text), text)
        self.assertEqual(parse("undo a1b2"), ("undo", "a1b2"))
        self.assertEqual(parse("find lions"), ("find", "lions"))
        self.assertEqual(parse("status"), ("status", None))
        self.assertEqual(parse("listing abc"), ("listing", "abc"))
        self.assertEqual(parse("margin 5"), ("margin", "5"))


class SearchTests(StoreMixin, HistoryTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])

    def row(self, code, state, summary, commit=None):
        self.conv.db.execute(
            "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at, \"commit\") "
            "VALUES (?, ?, '[]', ?, 'owner', 'chat', ?, ?, ?)",
            (code, state, summary, T0.isoformat(), (T0 + timedelta(days=1)).isoformat(), commit))
        self.conv.db.commit()

    def search(self, text):
        self.calls.clear()
        self.assertEqual(self.say(text), "history")
        [reply] = self.replies()
        self.assertEqual(self.calls, [])
        return reply.splitlines()

    def test_summary_all_words_case_and_accents(self):
        self.row("c1", "applied", "Open the Café at nine")
        self.row("c2", "applied", "Cafe closed on Monday")
        self.row("c3", "applied", "Hours for the market")
        self.assertEqual(self.search("history CAFÉ")[1:], ["- Cafe closed on Monday: saved, but I'm not sure it's on the website", "- Open the Café at nine: saved, but I'm not sure it's on the website"])
        self.assertEqual(self.search("history cafe\u0301")[1:], self.search("history CAFÉ")[1:])
        self.assertEqual(self.search("history nine CAFE nine")[1:], ["- Open the Café at nine: saved, but I'm not sure it's on the website"])
        self.assertEqual(self.search("history afe clo")[1:], ["- Cafe closed on Monday: saved, but I'm not sure it's on the website"])  # substring-AND
        self.assertEqual(self.search("history cafe market"), ["I found no changes that match cafe market."])

    def test_only_summary_is_searched(self):
        self.row("zebra1", "applied", "Open at nine")
        self.assertEqual(self.search("history zebra1"), ["I found no changes that match zebra1."])
        self.assertEqual(self.search("history applied"), ["I found no changes that match applied."])
        self.assertEqual(self.search("history website"), ["I found no changes that match website."])  # location text

    def test_search_all_history_before_limit(self):
        self.row("old1", "verified", "needle old")
        for i in range(12): self.row(f"n{i:02}", "verified", f"needle {i}")
        for i in range(30): self.row(f"x{i:02}", "verified", f"other {i}")
        got = self.search("history needle")
        self.assertEqual(got[0], "These match:")
        self.assertEqual(got[1:], [f"- needle {i}: saved, but I'm not sure it's on the website" for i in range(11, 1, -1)])
        self.assertEqual(self.search("history OLD")[1:], ["- needle old: saved, but I'm not sure it's on the website"])  # older than five
        self.assertEqual(len(self.search("history other")), 1 + 10)

    def test_states_and_current_location_equal_history(self):
        for i, state in enumerate(("approved", "applied", "verified", "failed", "reverted")):
            self.row(f"s{i}", state, f"zeta {state}")
        for state in ("proposed", "needs-details", "rejected", "expired"): self.row(f"q{state[:2]}", state, "zeta no")
        got = self.search("history zeta")
        self.assertEqual(got[1:], ["- zeta reverted: undone", "- zeta failed: I couldn't save it, so nothing changed",
                                  "- zeta verified: saved, but I'm not sure it's on the website",
                                  "- zeta applied: saved, but I'm not sure it's on the website",
                                  "- zeta approved: you said yes, but it isn't saved yet"])
        self.assertEqual(self.say("history"), "history")
        [bare] = self.replies()
        self.assertEqual(bare.splitlines()[1:], got[1:])  # same line format as bare history
        self.assertEqual(self.calls, [])

    def test_query_bounds_usage_and_no_match(self):
        self.row("a1", "applied", "x" * 60)
        self.assertEqual(self.search("history " + "x" * 60)[0], "These match:")
        self.assertEqual(self.search("history x")[0], "These match:")
        self.assertEqual(self.search("history " + "x" * 61), [USAGE])
        self.assertEqual(self.search("history !!!"), [USAGE])
        self.assertEqual(self.search("history a\nb"), [USAGE])
        self.assertEqual(self.search("history a\x07b"), [USAGE])
        self.assertEqual(self.search("history ' ’"), [USAGE])
        self.assertEqual(self.search("history Nothing Here."), ["I found no changes that match Nothing Here."])

    def test_empty_history_says_no_match(self):
        self.assertEqual(self.search("history hours"), ["I found no changes that match hours."])

    def test_search_is_read_only_paused_and_capped(self):
        self.row("a1", "applied", "hours change")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.assertEqual(self.say("hours"), "proposed")  # a proposal and a question to lapse
        self.replies()
        self.insert("Q1", "needs-details")
        self.now += timedelta(seconds=7 * 24 * 3600)
        before = (self.drafts(), self.conv.db.execute("SELECT * FROM approvals").fetchall(), self.tables())
        for text in ("history hours", "history nomatchword", "history !!!"):
            self.search(text)
        self.assertEqual((self.drafts(), self.conv.db.execute("SELECT * FROM approvals").fetchall(), self.tables()), before)
        self.assertNotIn("expired", [d["state"] for d in self.drafts()])
        self.assertEqual(self.say("history"), "history")  # bare history keeps the legacy expiry sweep
        self.replies()
        self.assertIn("expired", [d["state"] for d in self.drafts()])

    def test_duplicate_echo_stranger_group_and_attachment(self):
        self.row("a1", "applied", "hours change")
        self.assertEqual(self.say("history hours", pid="m1"), "history")
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual((self.say("history hours", pid="m1"), self.replies()), ("duplicate", []))
        self.assertEqual(self.say("history hours", sender=STRANGER), "ignored")
        self.assertEqual(self.replies(), [])

    def test_bare_history_unchanged_and_code_can_draft_undo(self):
        a = self.apply("desc")
        self.assertEqual(self.search("history " + a["summary"].split()[0])[0], "These match:")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.say(f"undo {a['code']}"), "proposed")  # undo only proposes
        self.assertEqual([d["state"] for d in self.drafts()][-1], "proposed")


if __name__ == "__main__":
    unittest.main()
