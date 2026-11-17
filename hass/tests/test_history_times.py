"""AV0222-06 (H06/H17): `history` and `history <words>` say when each change was approved, in Pacific time, from the
approval row bound to the draft; no usable row says `time unknown`.

Run: python3 -B -m unittest hass.tests.test_history_times -v
"""

import unittest
from datetime import timedelta

from hass.tests.test_conversation import T0
from hass.tests.test_history_approved import HistoryTestCase

EXP = (T0 + timedelta(days=1)).isoformat()


class HistoryTimeTests(HistoryTestCase):
    def draft(self, code, summary=None, change: str | None = "c1", digest="h1", base="b1", expires=EXP, chat="chat", state="applied"):
        self.conv.db.execute(
            "INSERT INTO drafts(code, state, ops_json, summary, sender, chat, created_at, expires_at, change_id, draft_hash, base) "
            "VALUES (?, ?, '[]', ?, 'owner', ?, ?, ?, ?, ?, ?)",
            (code, state, summary or f"summary {code}", chat, T0.isoformat(), expires, change, digest, base))
        self.conv.db.commit()

    def approve(self, at, change="c1", digest="h1", base="b1", expires=EXP, chat="chat", sender="someone-else"):
        self.conv.db.execute(
            "INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, approved_at) "
            "VALUES (?, ?, 'p', ?, ?, ?, ?, ?)", (sender, chat, change, digest, base, expires, at))
        self.conv.db.commit()

    def when(self, code="A1"):
        row = self.conv.db.execute("SELECT * FROM drafts WHERE code = ?", (code,)).fetchone()
        return self.conv._history_when(row)

    def test_bare_and_search_share_exact_timestamp_line(self):
        self.draft("A1", "Open the cafe at nine")
        self.approve("2026-11-03T22:14:00Z")
        want = "- Open the cafe at nine, approved Tue Nov 3 2:14 pm: saved, but I'm not sure it's on the website"
        self.assertEqual(self.history().splitlines()[1:], [want])
        self.assertEqual(self.say("history cafe"), "history")
        self.assertEqual(self.replies(), ["These match:\n" + want])

    def test_pacific_midnight_noon_day_dst_and_leap_day(self):
        for at, want in (("2026-11-04T08:05:00+00:00", "Wed Nov 4 12:05 am"),      # PST: 00:05 local
                         ("2026-11-03T20:00:00Z", "Tue Nov 3 12:00 pm"),           # noon
                         ("2026-07-01T06:59:00Z", "Tue Jun 30 11:59 pm"),          # PDT, UTC day later
                         ("2026-12-25T07:00:00Z", "Thu Dec 24 11:00 pm"),
                         ("2027-01-01T08:00:00Z", "Fri Jan 1 12:00 am"),
                         ("2026-11-01T08:30:00Z", "Sun Nov 1 1:30 am"),            # first 1:30 (PDT)
                         ("2026-11-01T09:30:00Z", "Sun Nov 1 1:30 am"),            # repeated 1:30 (PST)
                         ("2028-02-29T23:59:00Z", "Tue Feb 29 3:59 pm")):
            self.conv.db.execute("DELETE FROM approvals")
            self.conv.db.execute("DELETE FROM drafts")
            self.draft("A1")
            self.approve(at)
            self.assertEqual(self.when(), want, at)

    def test_missing_bad_naive_or_retained_approval_is_unknown(self):
        self.draft("A1")
        self.assertEqual(self.when(), "time unknown")  # no approval row at all
        for bad in ("", b"2026-11-03T22:14:00Z", 12345, "not a time", "2026-11-03T22:14:00", "0001-01-01T00:00:00+23:00"):
            self.conv.db.execute("DELETE FROM approvals")
            self.conv.db.execute("INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, approved_at) "
                                 "VALUES ('s', 'chat', 'p', 'c1', 'h1', 'b1', ?, ?)", (EXP, bad))
            self.assertEqual(self.when(), "time unknown", repr(bad))
        before = self.conv.db.execute("SELECT * FROM drafts").fetchall()
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in self.conv.db.execute("SELECT * FROM drafts")])
        self.conv.db.execute("DELETE FROM approvals")
        self.approve("2026-11-03T22:14:00Z")
        for col in ("change_id", "draft_hash", "base", "expires_at"):  # a missing draft binding never falls back to a broad match
            self.conv.db.execute(f"UPDATE drafts SET {col} = NULL WHERE code = 'A1'")
            self.assertEqual(self.when(), "time unknown", col)
            self.conv.db.execute(f"UPDATE drafts SET {col} = '' WHERE code = 'A1'")
            self.assertEqual(self.when(), "time unknown", col)

    def test_exact_approval_binding_prevents_reissued_time_leak(self):
        self.draft("A1", expires=EXP, base="b1")
        self.draft("A2", expires=EXP, base="b2", chat="other")
        self.approve("2026-11-03T22:14:00Z", base="b1")
        self.assertEqual(self.when("A1"), "Tue Nov 3 2:14 pm")  # an approval by a different owner still counts
        self.assertEqual(self.when("A2"), "time unknown")  # same change id and hash, other base and chat
        self.approve("2026-11-04T22:14:00Z", base="b1", chat="other")  # a newer row that is not bound exactly cannot win
        self.assertEqual(self.when("A1"), "Tue Nov 3 2:14 pm")
        self.approve("2026-11-05T22:14:00Z", base="b1")  # the newest exact row wins
        self.assertEqual(self.when("A1"), "Thu Nov 5 2:14 pm")
        self.approve("garbage", base="b1")  # the newest exact row is invalid: unknown, not the older time
        self.assertEqual(self.when("A1"), "time unknown")

    def test_caps_order_and_search_do_not_see_the_time(self):
        for i in range(7):
            self.draft(f"A{i}", f"edit {i}", change=f"c{i}", digest=f"h{i}")
            self.approve("2026-11-03T22:14:00Z", change=f"c{i}", digest=f"h{i}")
            self.approve("2026-11-03T22:15:00Z", change=f"c{i}", digest=f"h{i}")  # duplicate approvals: still one line each
        lines = self.history().splitlines()
        self.assertEqual(len(lines), 6)
        self.assertEqual([ln.split(", ")[0] for ln in lines[1:]], [f"- edit {i}" for i in range(6, 1, -1)])
        self.assertTrue(all(", approved Tue Nov 3 2:15 pm: " in ln for ln in lines[1:]))
        for word in ("Tue", "Nov", "unknown", "approved", "2:15"):
            self.assertEqual(self.say(f"history {word}"), "history")
            self.assertEqual(self.replies(), [f"I found no changes that match {word}."])

    def test_a_draft_with_no_approval_says_time_unknown(self):
        self.draft("A1", "Cafe closed", change=None)
        self.assertEqual(self.history().splitlines()[1:],
                         ["- Cafe closed, time unknown: saved, but I'm not sure it's on the website"])


if __name__ == "__main__":
    unittest.main()
