"""AV2137-04 (H04) tests: ``route.edit`` names each real hike card on the site whose shown route text the edit changes.

A scheduled or cancelled card shows the route title on its Route line through its Pacific day; a completed hike's
trail-journal entry shows the route's place and stats (community.js pastEntry). The warning never refuses an edit.
Direct-helper tests use synthetic events and an injected clock; the rest run prepare/apply on test_hike_ops.HikeRepo.
Run: python3 -m unittest hass.tests.test_route_link_warning -v
"""

import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from hass import voice
from hass.conversation import _record_lines, proposal_text
from hass.ops import OpContext, Refused, Touched
from hass.ops.routes import ROUTE_EDITABLE, _route_edit
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

PDT, PST = timezone(timedelta(hours=-7)), timezone(timedelta(hours=-8))
NOW = datetime(2026, 11, 9, 10, 0, tzinfo=PST)  # Monday, November 9, 2026, 10 am Pacific
IDEA = "idea-cass-hill"
JOURNAL = ("place", "distance", "difficulty", "elevationLabel", "elevation", "duration")


def _idea(**extra):
    return {"id": IDEA, "title": "Cass Hill", **{f: f"old {f}" for f in ROUTE_EDITABLE if f != "title"},
            "sourceUrl": "https://example.invalid/cass", "sourceName": "Guide", "status": "idea", "rsvpEnabled": False,
            **extra}


def _event(n, status, starts, title=None, trail=IDEA):
    return {"id": f"hike-{n}", "title": title or f"Hike {n}", "startsAt": starts, "status": status,
            **({"trailId": trail} if trail else {})}


def _edit(events, args, now=NOW, ideas=None):
    content = SimpleNamespace(community={"events": events, "routeIdeas": ideas or [_idea()]})
    ctx = OpContext(now=now, site_dir=Path("."), settings={})
    return _route_edit(content, {"id": IDEA, **args}, ctx), ctx.warnings


def _line(title, day):
    return f"{title} ({day}) shows this route; its Route line changes"


class LinkWarningHelperTests(unittest.TestCase):
    def test_scheduled_and_cancelled_title_only_visible_cards(self):
        events = [_event(1, "scheduled", "2026-11-14T09:00:00-08:00"),  # future
                  _event(2, "scheduled", "2026-11-09T11:00:00-08:00"),  # today, not started
                  _event(3, "scheduled", "2026-11-09T08:00:00-08:00"),  # today, already started: still shown
                  _event(4, "scheduled", "2026-11-08T09:00:00-08:00"),  # yesterday: not shown
                  _event(5, "cancelled", "2026-11-09T07:00:00-08:00"),  # cancelled today: shown
                  _event(6, "cancelled", "2026-11-08T09:00:00-08:00"),  # cancelled yesterday: not shown
                  _event(7, "cancelled", "2026-12-01T09:00:00-08:00")]
        shown = [_line("Hike 1", "Saturday, November 14, 2026"), _line("Hike 2", "Monday, November 9, 2026"),
                 _line("Hike 3", "Monday, November 9, 2026"), _line("Hike 5", "Monday, November 9, 2026"),
                 _line("Hike 7", "Tuesday, December 1, 2026")]
        result, warnings = _edit(events, {"title": "Cass Hill Loop"})
        self.assertIsInstance(result, list)
        self.assertEqual(warnings, shown)
        _, warnings = _edit(events, {"title": "Cass Hill Loop", "distance": "3 miles", "place": "Cayucos"})
        self.assertEqual(warnings, shown, "one warning per card, however many fields change")
        for field in ROUTE_EDITABLE:
            if field != "title":
                with self.subTest(field=field):  # the card's own stats are the hike's, not the route's
                    result, warnings = _edit(events, {field: "new text"})
                    self.assertEqual((type(result[0]), warnings), (Touched, []))

    def test_pacific_day_rollover_and_dst(self):
        old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Tokyo"  # the host zone must not matter
        time.tzset()
        self.addCleanup(lambda: (os.environ.__setitem__("TZ", old_tz) if old_tz else os.environ.pop("TZ", None),
                                 time.tzset()))
        late = datetime(2026, 11, 10, 7, 30, tzinfo=timezone.utc)  # 11:30 pm Monday Pacific (PST), Tuesday in UTC
        for starts in ("2026-11-10T07:00:00Z", "2026-11-09T23:00:00-08:00", "2026-11-10T16:00:00+09:00"):
            with self.subTest(starts=starts):
                _, warnings = _edit([_event(1, "scheduled", starts)], {"title": "New"}, now=late)
                self.assertEqual(warnings, [_line("Hike 1", "Monday, November 9, 2026")])
        _, warnings = _edit([_event(1, "cancelled", "2026-11-10T08:00:00Z")], {"title": "New"}, now=late)
        self.assertEqual(warnings, [_line("Hike 1", "Tuesday, November 10, 2026")])  # Pacific midnight
        after_midnight = datetime(2026, 11, 10, 8, 30, tzinfo=timezone.utc)  # 12:30 am Tuesday Pacific
        for status in ("scheduled", "cancelled"):  # same UTC date, but yesterday in Pacific: the card is gone
            _, warnings = _edit([_event(1, status, "2026-11-10T07:00:00Z")], {"title": "New"}, now=after_midnight)
            self.assertEqual(warnings, [], status)
        summer = datetime(2026, 6, 30, 23, 30, tzinfo=PDT)
        for starts in ("2026-06-30T22:00:00-07:00", "2026-07-01T05:00:00Z"):
            _, warnings = _edit([_event(1, "scheduled", starts)], {"title": "New"}, now=summer)
            self.assertEqual(warnings, [_line("Hike 1", "Tuesday, June 30, 2026")], starts)
        _, warnings = _edit([_event(1, "scheduled", "2026-06-30T22:00:00-07:00")], {"title": "New"},
                            now=summer + timedelta(hours=1))
        self.assertEqual(warnings, [])

    def test_completed_field_matrix_matches_past_entry(self):
        events = [_event(1, "completed", "2025-03-01T09:00:00-08:00", title="Spring Walk")]  # no date cutoff
        for field in ROUTE_EDITABLE:
            with self.subTest(field=field):
                result, warnings = _edit(events, {field: "new text"})
                self.assertIsInstance(result[0], Touched)
                expected = ["the trail journal entry for Spring Walk changes too"] if field in JOURNAL else []
                self.assertEqual(warnings, expected)
        _, warnings = _edit(events, {"title": "New", "description": "New words", "distance": "9 miles",
                                     "duration": "All day"})
        self.assertEqual(warnings, ["the trail journal entry for Spring Walk changes too"])
        self.assertEqual(events[0]["title"], "Spring Walk")
        self.assertNotIn("recap", events[0])

    def test_no_link_hidden_idea_and_other_routes_stay_silent(self):
        future = "2026-11-14T09:00:00-08:00"
        for events in ([], [_event(1, "scheduled", future, trail=None)],
                       [_event(1, "scheduled", future, trail="idea-point-buchon"),
                        _event(2, "completed", "2026-01-01T09:00:00-08:00", trail="idea-point-buchon")],
                       [_event(1, "scheduled", future, title="Cass Hill", trail=None)]):  # no title matching
            with self.subTest(events=events):
                self.assertEqual(_edit(events, {"title": "New", "distance": "3 miles"})[1], [])
        linked = [_event(1, "scheduled", future), _event(2, "completed", "2026-01-01T09:00:00-08:00")]
        result, warnings = _edit(linked, {"title": "New", "distance": "3 miles"}, ideas=[_idea(status="hidden")])
        self.assertEqual((type(result[0]), warnings), (Touched, []))
        twins = [_event(1, "scheduled", future, title="Saturday Walk"), _event(2, "scheduled", future, title="Saturday Walk")]
        self.assertEqual(_edit(twins, {"title": "New"})[1], [_line("Saturday Walk", "Saturday, November 14, 2026")] * 2)

    def test_unchanged_or_refused_changes_do_not_warn(self):
        events = [_event(1, "scheduled", "2026-11-14T09:00:00-08:00", title="Moon Walk"),
                  _event(2, "completed", "2026-01-01T09:00:00-08:00")]
        cases = (({"title": "  Cass   Hill "}, f"route idea {IDEA} already says that"),
                 ({"title": "moon walk"}, "hike-1 is already called Moon Walk"),
                 ({"distance": "x" * 601}, "distance is longer than 600 characters"))
        for args, reason in cases:
            with self.subTest(args=args):
                result, warnings = _edit(events, args)
                self.assertEqual((result, warnings), (Refused(reason), []))
        result, warnings = _edit(events, {"title": "Cass Hill", "character": "Windy"})
        self.assertEqual((type(result[0]), warnings), (Touched, []), "unchanged title is dropped, character not shown")
        content = SimpleNamespace(community={"events": events, "routeIdeas": [_idea()]})
        for route_id, reason in (("idea-nowhere", "unknown route idea idea-nowhere"),
                                 ("hike-1", "hike-1 is a hike, not a route idea; use hike.update")):
            ctx = OpContext(now=NOW, site_dir=Path("."), settings={})
            self.assertEqual(_route_edit(content, {"id": route_id, "title": "New"}, ctx), Refused(reason))
            self.assertEqual(ctx.warnings, [])


class LinkWarningDraftTests(HikeTestCase):
    def hikes(self, repo, title=HIKE["title"]):
        """One scheduled (Dec 12) and one completed (Dec 5) hike linking Cass Hill; the clock is Dec 6."""
        repo.run(("hike.create", {**HIKE, "title": title, "trailId": IDEA}),
                 ("hike.create", {**HIKE, "title": "Second walk", "date": "2026-12-12", "trailId": IDEA}))
        repo.now = datetime(2026, 12, 5, 12, 0, tzinfo=PST)
        repo.run(("hike.complete", {"id": repo.community()["events"][0]["id"], "recap": "We walked."}))
        repo.now = datetime(2026, 12, 6, 9, 0, tzinfo=PST)

    def test_prepare_apply_undo_touch_only_route(self):
        repo = self.repo()
        self.hikes(repo)
        community, head = repo.community(), repo.head()
        prepared = repo.prepare({"ops": [{"op": "route.edit", "args": {"id": IDEA, "title": "Cass Hill Loop",
                                                                       "distance": "3.5 miles"}}]})
        self.assertEqual(prepared["result"], "ok", prepared)
        draft = prepared["draft"]
        self.assertEqual(draft["warnings"], [f"the trail journal entry for {HIKE['title']} changes too",
                                             _line("Second walk", "Saturday, December 12, 2026")])
        self.assertEqual([(r["collection"], r["key"]) for r in draft["records"]], [("routeIdeas", IDEA)])
        self.assertEqual((repo.head(), repo.community()), (head, community), "nothing is written before yes")
        self.assertEqual(repo.apply(draft)["result"], "applied")
        after = repo.community()
        self.assertEqual(json.dumps(after["events"]), json.dumps(community["events"]))
        others = [i for i in community["routeIdeas"] if i["id"] != IDEA]
        self.assertEqual(json.dumps([i for i in after["routeIdeas"] if i["id"] != IDEA]), json.dumps(others))
        repo.run(("history.revert", {"changeId": draft["change_id"]}))
        self.assertEqual(repo.community(), community)  # undo restores the route text (key order aside)

    def test_owner_projection_preserves_hike_identity(self):
        repo = self.repo()
        title = "Ève's (Sunset) walk; Bluffs"
        self.hikes(repo, title=title)
        prepared = repo.prepare({"ops": [{"op": "route.edit", "args": {"id": IDEA, "title": "Cass Hill Loop",
                                                                       "elevation": "500 ft"}}]})
        draft = prepared["draft"]
        lines = _record_lines(draft)[-2:]
        self.assertEqual([voice.plain(x) for x in lines],
                         [f"Heads up: The trail journal entry for {title} changes too.",
                          "Heads up: The Route line on Second walk (Saturday, December 12, 2026) changes too."])
        text = proposal_text("abc123", draft, "2026-12-06T10:00:00-08:00", now=repo.now)
        for line in lines:
            self.assertIn(line, text)
            self.assertEqual(voice.check(line), [], line)
        self.assertNotIn("hike-", voice.plain(text))
        self.assertNotIn("double-check", text)
        self.assertEqual(voice.explain_warning(_line("Café (Été)", "Monday, November 9, 2026")),
                         f"The Route line on {voice.quote('Café (Été)')} (Monday, November 9, 2026) changes too.")
        for old in ("something unknown", "shows this route; its Route line changes", "trail journal entry changes"):
            self.assertEqual(voice.explain_warning(old), "There is one thing to double-check before you say yes.")
        self.assertEqual(voice.explain_warning("adds Organic badge to p-1"), "This adds the Organic badge.")


if __name__ == "__main__":
    unittest.main()
