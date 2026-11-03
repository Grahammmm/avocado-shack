"""AV1322-08 tests: social_draft --hike prints a local hike announcement draft. Run:
python3 -m unittest hass.tests.test_social_draft_hike -v

Synthetic events only; CLI cases write a temporary content dir. Nothing is posted.
"""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import social_draft
from hass.content_model import Content

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
TAGS = "\n\n#AvocadoShack #NorthCoastHikingClub"
IDEA = {"id": "pismo-bluffs", "title": "Pismo Bluffs Loop", "status": "idea"}


def hike(hid="h1", **changes):
    return {"id": hid, "title": "Bluff Walk", "startsAt": "2026-10-17T16:00:00Z", "timezone": "America/Los_Angeles",
            "status": "scheduled", "meetingPoint": "the Shack porch", "trailId": "pismo-bluffs", **changes}


def content(*events, ideas=(IDEA,)):
    return Content(products=[{"id": "p1", "name": "Sourdough"}], makers={},
                   community={"club": {}, "events": list(events), "routeIdeas": list(ideas)}, store={})


def draft(*events, hid="h1", now=NOW, **kw):
    return social_draft.build_hike(content(*events, **kw), hid, now)


def refused(reason):
    return {"draft": False, "reason": reason}


class HikeDraftTests(unittest.TestCase):
    def test_scheduled_hike_with_route(self):
        self.assertEqual(draft(hike()), {"draft": True, "caption": "Bluff Walk\nSaturday, October 17 at 9:00 am (Pacific)\n"
                                                                    "Meet at the Shack porch.\nRoute: Pismo Bluffs Loop." + TAGS})

    def test_time_is_pacific_across_dst(self):
        for starts, when in (("2026-10-17T16:00:00Z", "Saturday, October 17 at 9:00 am"),
                             ("2026-12-05T16:00:00Z", "Saturday, December 5 at 8:00 am"),
                             ("2026-12-05T13:30:00-08:00", "Saturday, December 5 at 1:30 pm"),
                             ("2026-12-06T08:05:00Z", "Sunday, December 6 at 12:05 am")):
            self.assertEqual(draft(hike(startsAt=starts))["caption"].split("\n")[1], when + " (Pacific)", starts)

    def test_cancelled_is_refused_even_when_past(self):
        for starts in ("2026-10-17T16:00:00Z", "2026-09-01T16:00:00Z"):
            self.assertEqual(draft(hike(status="cancelled", startsAt=starts)), refused("hike is cancelled"))

    def test_completed_or_started_is_already_happened(self):
        self.assertEqual(draft(hike(status="completed")), refused("hike already happened"))
        start = "2026-10-17T16:00:00Z"
        minute_after = datetime(2026, 10, 17, 16, 1, tzinfo=timezone.utc)
        self.assertEqual(draft(hike(startsAt=start), now=minute_after), refused("hike already happened"))
        self.assertTrue(draft(hike(startsAt=start), now=datetime(2026, 10, 17, 15, 59, tzinfo=timezone.utc))["draft"])

    def test_other_status_is_not_scheduled(self):
        for status in ("draft", "idea", None, "Scheduled"):
            self.assertEqual(draft(hike(status=status)), refused("not scheduled"))

    def test_unknown_idea_and_product_ids_are_no_such_hike(self):
        for hid in ("nope", "pismo-bluffs", "p1", "H1", ""):
            self.assertEqual(draft(hike(), hid=hid), refused("no such hike"))

    def test_missing_or_unusable_idea_drops_route_line(self):
        for event, ideas in ((hike(trailId="gone"), (IDEA,)), (hike(trailId=None), (IDEA,)), (hike(), ()),
                             (hike(), ({**IDEA, "title": "Two\nlines"},)), (hike(), ("pismo-bluffs",))):
            caption = draft(event, ideas=ideas)["caption"]
            self.assertEqual(caption, "Bluff Walk\nSaturday, October 17 at 9:00 am (Pacific)\nMeet at the Shack porch." + TAGS)
        no_trail = hike()
        del no_trail["trailId"]
        self.assertNotIn("Route:", draft(no_trail)["caption"])

    def test_hashtag_or_account_in_free_text_is_refused(self):
        bad = refused("free text has a hashtag or account name")
        for event, ideas in ((hike(title="Sunset #sunset"), (IDEA,)), (hike(title="With @trailclub"), (IDEA,)),
                             (hike(meetingPoint="@shack porch"), (IDEA,)), (hike(title="Walk \uff03sunset"), (IDEA,)),
                             (hike(), ({**IDEA, "title": "Loop #bluffs"},))):
            self.assertEqual(draft(event, ideas=ideas), bad)

    def test_incomplete_record(self):
        bad = refused("hike record incomplete")
        for changes in ({"meetingPoint": "Shack\nporch"}, {"meetingPoint": None}, {"meetingPoint": "  "},
                        {"title": "Bluff\rWalk"}, {"title": 5}, {"startsAt": "soon"}, {"startsAt": None},
                        {"startsAt": "2026-10-17T09:00:00"}):
            self.assertEqual(draft(hike(**changes)), bad, changes)

    def test_unreadable_events_and_long_caption(self):
        for events in ("h1", None, [hike(), "h2"]):
            c = content()
            c.community["events"] = events
            self.assertEqual(social_draft.build_hike(c, "h1", NOW), refused("cannot read content"))
        base = len(draft(hike(title="x"))["caption"]) - 1
        self.assertTrue(draft(hike(title="x" * (2200 - base)))["draft"])
        self.assertEqual(draft(hike(title="x" * (2201 - base))), refused("caption too long"))


class HikeCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        community = {"club": {}, "events": [hike(), hike("h2", status="cancelled")], "routeIdeas": [IDEA]}
        for name, doc in (("products", {"products": []}), ("makers", {"makers": {}}), ("community", community), ("store", {})):
            (self.dir / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **doc}), "utf-8")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = social_draft.main(list(argv), self.dir, self.dir)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def test_hike_draft_and_refusal_exit_codes(self):
        code, out = self.run_cli("--hike", "h1", "--now", "2026-10-01T00:00:00Z")
        self.assertEqual((code, json.loads(out)["caption"].split("\n")[0]), (0, "Bluff Walk"))
        code, out = self.run_cli("--hike", "h2", "--now", "2026-10-01T00:00:00Z")
        self.assertEqual((code, json.loads(out)), (1, refused("hike is cancelled")))
        code, out = self.run_cli("--hike", "h1", "--now", "2026-10-17T16:01:00+00:00")
        self.assertEqual((code, json.loads(out)), (1, refused("hike already happened")))

    def test_both_or_neither_is_usage_error(self):
        for argv in (("p1", "--hike", "h1"), ("--hike", "h1", "p1"), (), ("--now", "2026-10-01T00:00:00Z")):
            self.assertEqual(self.run_cli(*argv), (2, ""), argv)


if __name__ == "__main__":
    unittest.main()
