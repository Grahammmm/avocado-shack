"""AV1322-04 (H04/H17): `find <words>` also lists hikes (id, Pacific weekday/date/time, status) by start and route ideas
(id, status) by title whose title holds every folded query word; the 10-line cap and tail cover the merged list; read-only
and the same while paused. Synthetic titles in the throwaway writer worktree only.
Run: python3 -B -m unittest hass.tests.test_find_hikes -v
"""

import copy
import json
from unittest import mock

from hass import conversation
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_find import FindTests
from hass.tests.test_status_pause import StoreMixin

NONE = 'No product, maker, hike or route idea matches "{}".'


def event(eid, title, starts, status="scheduled"):
    return {"id": eid, "title": title, "startsAt": starts, "timezone": "America/Los_Angeles", "status": status}


class FindHikeTests(StoreMixin, ConversationTestCase):
    find, edit, rename = FindTests.find, FindTests.edit, FindTests.rename

    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name: (self.calls.append(_n), _r(*a))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "find reached the interpreter/editor"))

    def community(self, events=(), ideas=()):
        """Set the worktree's events and append route ideas (a copy of the first real idea with a new id and title)."""
        def change(doc):
            doc["events"] = list(events)
            doc["routeIdeas"] += [{**doc["routeIdeas"][0], "id": i, "title": t} for i, t in ideas]
        self.edit("community.json", change)

    def test_hike_and_idea_with_pacific_weekday_across_dst(self):
        self.community([event("hike-2026-12-05", "Cerro Cabrillo winter loop", "2026-12-05T13:30:00-08:00"),
                        event("hike-2026-10-17", "Cerro Cabrillo sunrise", "2026-10-17T07:05:00-07:00")],
                       [("idea-cerro-cabrillo", "Cerro Cabrillo summit")])
        self.assertEqual(self.find("find CERRO cabrillo"), [
            "hike hike-2026-10-17: Cerro Cabrillo sunrise (Saturday Oct 17, 7:05 am, scheduled)",
            "hike hike-2026-12-05: Cerro Cabrillo winter loop (Saturday Dec 5, 1:30 pm, scheduled)",
            "route idea-cerro-cabrillo: Cerro Cabrillo summit (idea)"])
        self.assertEqual(self.find("find cerro summit"), ["route idea-cerro-cabrillo: Cerro Cabrillo summit (idea)"])
        self.community([event("hike-2026-12-05", "Peña Zzridge bluffs", "2026-12-05T12:00:00-08:00")])
        self.assertEqual(self.find("find PENA zzridge"), [  # accents folded; noon is pm
            "hike hike-2026-12-05: Peña Zzridge bluffs (Saturday Dec 5, 12:00 pm, scheduled)"])

    def test_eight_products_and_five_hikes_share_the_cap(self):
        self.rename("Zzqx", products=8)
        self.community([event(f"hike-2026-12-0{d}", f"Zzqx walk {d}", f"2026-12-0{d}T09:00:00-08:00") for d in range(1, 6)])
        lines = self.find("find zzqx")
        self.assertEqual(len(lines), 11)
        self.assertEqual([ln.split()[0] for ln in lines[:10]], ["product"] * 8 + ["hike"] * 2)
        self.assertEqual(lines[8:], ["hike hike-2026-12-01: Zzqx walk 1 (Tuesday Dec 1, 9:00 am, scheduled)",
                                     "hike hike-2026-12-02: Zzqx walk 2 (Wednesday Dec 2, 9:00 am, scheduled)",
                                     "… 3 more; add a word."])

    def test_cancelled_and_completed_hikes_show_their_status(self):
        self.community([event("hike-2026-10-03", "Zzst coast", "2026-10-03T08:00:00-07:00", "completed"),
                        event("hike-2026-10-10", "Zzst coast", "2026-10-10T08:00:00-07:00", "cancelled")])
        self.assertEqual(self.find("find zzst"), [
            "hike hike-2026-10-03: Zzst coast (Saturday Oct 3, 8:00 am, completed)",
            "hike hike-2026-10-10: Zzst coast (Saturday Oct 10, 8:00 am, cancelled)"])

    def test_unreadable_start_untitled_event_and_hidden_idea(self):
        """Content that validation would refuse is still never raised on: a bad start is worded, no title is skipped."""
        real = conversation.load_and_validate

        def loaded(*args):
            content = copy.deepcopy(real(*args))
            untitled = event("hike-untitled", "Zzbd", "2026-12-05T09:00:00-08:00")
            content.community["events"] = [event("hike-bad", "Zzbd ridge", "bad"), {**untitled, "title": None},
                                           {k: v for k, v in untitled.items() if k != "title"},
                                           event("hike-naive", "Zzbd naive", "2026-12-05T09:00:00"),
                                           event("hike-utc", "Zzbd utc", "2026-12-05T17:00:00Z")]
            content.community["routeIdeas"].append({"id": "idea-zzbd", "title": "Zzbd hidden", "status": "hidden"})
            return content
        with mock.patch.object(conversation, "load_and_validate", loaded):
            self.assertEqual(self.find("find zzbd"), [  # the two untitled events are skipped
                "hike hike-utc: Zzbd utc (Saturday Dec 5, 9:00 am, scheduled)",
                "hike hike-bad: Zzbd ridge (date unreadable, scheduled)",
                "hike hike-naive: Zzbd naive (date unreadable, scheduled)",
                "route idea-zzbd: Zzbd hidden (hidden)"])

    def test_paused_gives_the_same_answer_and_changes_nothing(self):
        self.community([event("hike-2026-12-05", "Zzps walk", "2026-12-05T09:00:00-08:00")], [("idea-zzps", "Zzps loop")])
        draft, _reply = self.propose("hours")
        self.calls.clear()  # that proposal is the only allowed interpreter/editor use
        before = self.find("find zzps")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        state = ([dict(r) for r in self.conv.db.execute("SELECT * FROM control")], self.drafts(), self.approvals())
        self.assertEqual(self.find("find zzps"), before)
        self.assertNotIn(conversation.PAUSED_LINE, before)
        self.assertEqual(([dict(r) for r in self.conv.db.execute("SELECT * FROM control")], self.drafts(),
                          self.approvals()), state)
        self.assertEqual((len(self.drafts()), self.editor.applies), (1, 0))

    def test_every_word_must_match_and_punctuation_only_matches_nothing(self):
        self.community([event("hike-2026-12-05", "Cerro Cabrillo", "2026-12-05T09:00:00-08:00")],
                       [("idea-cerro-alto", "Cerro Alto")])
        self.assertEqual(self.find("find cerro zzqx"), [NONE.format("cerro zzqx")])
        self.assertEqual(self.find("find alto cerro"), ["route idea-cerro-alto: Cerro Alto (idea)"])
        self.assertEqual(self.find("find ''"), [NONE.format("''")])


if __name__ == "__main__":
    import unittest
    unittest.main()
