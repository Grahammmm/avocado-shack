"""AV1537-07 tests: `status` names every scheduled hike whose start is at or before now, after the upcoming-hike
lines, and says to complete or cancel it (the site already hides it from the upcoming list and the journal).
Same setup as test_status_pause.py (fixture repo, clock T0 = 2026-11-02 09:00 PST, placeholder RSVP rows only).
Run: python3 -B -m unittest hass.tests.test_status_past_hikes -v
"""

import json
import unittest
from unittest import mock

from hass import conversation, editor
from hass.tests import test_status_pause as sp
from hass.tests.test_conversation import T0
from hass.tests.test_hike_ops import HIKE, NOW, _req
from hass.tests.test_undo import H06TestCase

UPCOMING = "Hike Test hike 2026-12-05 09:00 PST: guest count unavailable"


def passed(title, start):
    return (f"Hike {title} {start} has passed but is still scheduled; "
            f'send "complete {title}" or "cancel {title}" in your own words.')


class PastHikeStatusTests(sp.StoreMixin, H06TestCase):
    rsvp_db, use = sp.GuestTotalTests.rsvp_db, sp.GuestTotalTests.use

    def hike(self, *ops, now=NOW):  # hikes are created before the clock; completing one needs a later `now`
        draft = editor.prepare(_req(*ops), state=str(self.repo.state), now=now)
        self.assertEqual(draft["result"], "ok", draft)
        out = editor.apply(draft["draft"]["change_id"], draft["draft"]["draft_hash"], state=str(self.repo.state), now=now)
        self.assertEqual(out["result"], "applied", out)

    def past(self, title, day="2026-11-01", clock="09:00"):
        self.hike(("hike.create", {**HIKE, "title": title, "date": day, "time": clock}))

    def hike_lines(self):
        return [line for line in self.status() if line.startswith(("Hike", "…"))]

    def test_started_an_hour_ago_follows_the_upcoming_line(self):
        self.past("Morning hike", "2026-11-02", "08:00")  # created first, still listed after the upcoming hike
        self.hike(("hike.create", HIKE))
        self.use(None)
        self.assertEqual(self.hike_lines(), [UPCOMING, passed("Morning hike", "2026-11-02 08:00 PST")])

    def test_start_exactly_now_has_passed(self):
        self.past("Now hike", "2026-11-02", "09:00")  # == T0: the site's `startsAt > now` rule hides it too
        self.past("Later hike", "2026-11-02", "09:01")
        self.assertEqual(self.hike_lines(), ["Hike Later hike 2026-11-02 09:01 PST: guest count unavailable",
                                             passed("Now hike", "2026-11-02 09:00 PST")])

    def test_completed_and_cancelled_past_hikes_have_no_line(self):
        for title in ("Done hike", "Called off", "Forgotten hike"):
            self.past(title)
        self.hike(("hike.complete", {"id": "hike-2026-11-01-done-hike", "recap": "Clear skies."}), now=T0)
        self.hike(("hike.cancel", {"id": "hike-2026-11-01-called-off"}))
        lines = self.status()
        self.assertEqual([line for line in lines if line.startswith(("Hike", "…"))],
                         [passed("Forgotten hike", "2026-11-01 09:00 PST")])
        for absent in ("Done hike", "Called off"):
            self.assertNotIn(absent, "\n".join(lines))

    def test_seven_passed_show_the_oldest_five_and_a_count(self):
        for n in range(7, 0, -1):  # created newest first; listed oldest first
            self.past(f"Past {n}", clock=f"{n + 9:02d}:00")
        expected = [passed(f"Past {n}", f"2026-11-01 {n + 9:02d}:00 PST") for n in range(1, 6)]
        self.assertEqual(self.hike_lines(), expected + ["… and 2 more past hikes still scheduled."])
        for n in (1, 2):  # exactly five left: all named, no count line
            self.hike(("hike.cancel", {"id": f"hike-2026-11-01-past-{n}"}))
        self.assertEqual(self.hike_lines(), [passed(f"Past {n}", f"2026-11-01 {n + 9:02d}:00 PST") for n in range(3, 8)])

    def test_rsvp_on_passed_hike_never_opens_the_database(self):
        self.past("Busy hike")  # RSVPs on, capacity 12
        line = passed("Busy hike", "2026-11-01 09:00 PST")
        readable = self.rsvp_db("rsvps.sqlite3", [("hike-2026-11-01-busy-hike", 4)])
        wrong = self.rsvp_db("wrong.sqlite3", [], schema="CREATE TABLE other(id INTEGER)")
        for path in (None, "", str(self.repo.state.parent / "missing.sqlite3"), wrong, readable):
            with self.subTest(path=path), mock.patch.object(conversation.hikes, "guest_counts") as counts:
                self.use(path)
                lines = self.status()
                self.assertEqual([x for x in lines if x.startswith("Hike")], [line])
                for absent in ("guest count unavailable", "confirmed", "of 12"):
                    self.assertNotIn(absent, "\n".join(lines))
                counts.assert_not_called()
        self.assertFalse((self.repo.state.parent / "missing.sqlite3").exists())

    def test_broken_content_is_unavailable(self):
        self.past("Past hike")
        content = self.repo.wt / "hass/content/community.json"
        good = json.loads(content.read_text("utf-8"))
        content.write_text("{", "utf-8")
        self.assertEqual(self.hike_lines(), ["Hikes: unavailable"])
        bad = {**good["events"][-1], "id": "hike-bad", "startsAt": "not a date"}
        content.write_text(json.dumps({**good, "events": good["events"] + [bad]}), "utf-8")
        self.assertEqual(self.hike_lines(), ["Hikes: unavailable"])  # one unparseable start: whole block

    def test_read_only_and_shown_while_paused(self):
        self.past("Past hike")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        content = self.repo.wt / "hass/content/community.json"
        before = (self.drafts(), self.approvals(), self.tables(), self.commits(), content.read_bytes())
        lines = self.status()
        self.assertEqual(lines[0], "Changes: paused since 2026-11-02 09:00 PST")
        self.assertEqual(lines[-1], passed("Past hike", "2026-11-01 09:00 PST"))
        self.assertEqual((self.drafts(), self.approvals(), self.tables(), self.commits(), content.read_bytes()),
                         before)


if __name__ == "__main__":
    unittest.main()
