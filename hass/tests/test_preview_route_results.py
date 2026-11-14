"""AV1222-06 tests (H06): a route idea change is "checked" only when every place /hike shows the route reads the new
title (a linked scheduled hike's "Route:" line, the sample invitation); a route shown nowhere is reported as not
checked. Target and reply tests are pure; capture tests run the real loopback preview and Chromium over the tracked
site with a community.json overlay, and are skipped when PLAYWRIGHT_MODULE is unset.
Run: python3 -B -m unittest hass.tests.test_preview_route_results -v
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import conversation, owner_answers, preview
from hass.content_model import REPO_ROOT

COMMUNITY = "storefront-mockup/community.json"
ROUTE_CHECKS = ("routeShown", "routeGone")
CASS, BUCHON = "idea-cass-hill", "idea-point-buchon"


def record(key=CASS, title="Cass Hill", **after):
    return {"collection": "routeIdeas", "key": key, "after": {"title": title, "status": "idea", **after}}


class TargetTests(unittest.TestCase):
    def test_route_target_shape(self):
        self.assertEqual(preview.target_for(record("r-1", "Coast walk")),
                         {"kind": "route", "id": "r-1", "title": "Coast walk", "hidden": False})

    def test_hidden_route_target(self):
        self.assertIs(preview.target_for(record(status="hidden"))["hidden"], True)

    def test_events_target_is_unchanged(self):
        event = {"collection": "events", "key": "h-1", "after": {"title": "Hike", "status": "completed", "recap": "Calm."}}
        self.assertEqual(preview.target_for(event),
                         {"kind": "event", "title": "Hike", "status": "completed", "id": "h-1", "recap": "Calm."})


class ReplyTests(unittest.TestCase):
    def reply(self, unshown):
        said = []
        fake = mock.MagicMock()
        fake.settings = {}  # live mode is absent in this existing offline reply fixture
        fake._row_live_site.return_value = None  # a private-mode row has no live site (Conversation._row_live_site is mocked here)
        fake.previewer = object()
        fake._drafts.return_value = [{"code": "C1", "summary": "renamed the route"}]
        fake.verify.return_value = ("/tmp/shot.png", None, unshown)
        fake._reply.side_effect = lambda text, files=None: said.append(text)
        conversation.Conversation._verify_pending(fake)
        return said[0]

    def test_unshown_route_is_not_reported_as_checked(self):
        text = self.reply([True])
        self.assertNotIn("checked", text.split("\n")[0])
        self.assertIn(owner_answers.ROUTE_UNSHOWN, text)
        self.assertIn("nothing to check", text)

    def test_shown_route_is_checked(self):
        text = self.reply([False])
        self.assertTrue(text.startswith("Saved and checked: "))
        self.assertNotIn("nothing to check", text)


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class CaptureTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory(prefix="hass-av1222-06-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"
        self.base = json.loads((REPO_ROOT / COMMUNITY).read_text())

    def site(self, events=(), renames=None, drop=()):
        data = json.loads(json.dumps(self.base))
        data["events"] = list(events)
        data["routeIdeas"] = [{**r, **({"title": renames[r["id"]]} if r["id"] in (renames or {}) else {})}
                              for r in data["routeIdeas"] if r["id"] not in drop]
        return {COMMUNITY: json.dumps(data).encode()}

    @staticmethod
    def hike(n, trail=CASS, status="scheduled"):
        return {"id": f"h-{n}", "title": f"Walk {n}", "status": status, "startsAt": f"2030-06-0{n}T09:00:00-07:00",
                "trailId": trail, "meetingPoint": "Lot", "rsvpEnabled": False, "timezone": "America/Los_Angeles"}

    def run_check(self, files, title, key=CASS, **after):
        target = preview.target_for(record(key, title, **after))
        result = preview.Previewer(REPO_ROOT, viewports=("phone",)).capture(files, target, self.out)
        self.assertIs(result["checks"].get("noPageErrors"), True, result)
        return result, {k: v for k, v in result["checks"].items() if k in ROUTE_CHECKS}

    def test_linked_hike_route_line_reads_the_new_title_and_old_page_fails(self):
        old = self.site([self.hike(1)])
        new = self.site([self.hike(1)], {CASS: "Cass Hill Loop"})
        result, checks = self.run_check(new, "Cass Hill Loop")
        self.assertEqual((result["ok"], checks, "unshown" in result), (True, {"routeShown": True}, False), result)
        stale, checks = self.run_check(old, "Cass Hill Loop")
        self.assertEqual((stale["ok"], checks), (False, {"routeShown": False}), stale)

    def test_two_linked_hikes_both_read_the_new_title(self):
        events = [self.hike(1), self.hike(2)]
        result, checks = self.run_check(self.site(events, {CASS: "Cass Hill Loop"}), "Cass Hill Loop")
        self.assertEqual((result["ok"], checks), (True, {"routeShown": True}), result)
        stale, checks = self.run_check(self.site(events), "Cass Hill Loop")
        self.assertEqual(checks, {"routeShown": False}, stale)

    def test_sample_invitation_title_is_checked(self):
        result, checks = self.run_check(self.site([], {BUCHON: "Point Buchon North"}), "Point Buchon North", BUCHON)
        self.assertEqual((result["ok"], checks), (True, {"routeShown": True}), result)
        stale, checks = self.run_check(self.site([]), "Point Buchon North", BUCHON)
        self.assertEqual(checks, {"routeShown": False}, stale)

    def test_route_shown_nowhere_is_unshown_not_checked(self):
        files = self.site([self.hike(1, status="completed"), self.hike(2, status="cancelled")], {CASS: "Cass Hill Loop"})
        files = {COMMUNITY: files[COMMUNITY]}
        data = json.loads(files[COMMUNITY])
        data["events"][1]["startsAt"] = "2020-01-01T09:00:00-08:00"
        result, checks = self.run_check({COMMUNITY: json.dumps(data).encode()}, "Cass Hill Loop")
        self.assertEqual((result["ok"], checks, result.get("unshown")), (True, {}, True), result)

    def test_sample_archive_title_is_checked(self):
        # no real completed hikes: the sample archive shows idea-cass-hill and idea-fiscalini-bluff
        fisc = "idea-fiscalini-bluff"
        for key, name in ((CASS, "Cass Hill Loop"), (fisc, "Fiscalini Bluff Walk")):
            result, checks = self.run_check(self.site([], {key: name}), name, key)
            self.assertEqual((result["ok"], checks, "unshown" in result), (True, {"routeShown": True}, False), result)
            stale, checks = self.run_check(self.site([]), name, key)
            self.assertEqual((stale["ok"], checks), (False, {"routeShown": False}), stale)

    def test_archive_and_linked_hike_must_both_read_the_new_title(self):
        result, checks = self.run_check(self.site([self.hike(1)], {CASS: "Cass Hill Loop"}), "Cass Hill Loop")
        self.assertEqual((result["ok"], checks), (True, {"routeShown": True}), result)

    def test_hidden_archive_route_is_gone(self):
        result, checks = self.run_check(self.site([], drop=(CASS,)), "Cass Hill", status="hidden")
        self.assertEqual((result["ok"], checks), (True, {"routeGone": True}), result)
        stale, checks = self.run_check(self.site([]), "Cass Hill", status="hidden")
        self.assertEqual((stale["ok"], checks), (False, {"routeGone": False}), stale)

    def test_hidden_route_is_gone_and_a_card_still_showing_it_fails(self):
        events = [self.hike(1)]
        result, checks = self.run_check(self.site(events, drop=(CASS,)), "Cass Hill", status="hidden")
        self.assertEqual((result["ok"], checks), (True, {"routeGone": True}), result)
        stale, checks = self.run_check(self.site(events), "Cass Hill", status="hidden")
        self.assertEqual((stale["ok"], checks), (False, {"routeGone": False}), stale)

    def test_title_with_markup_and_quotes_is_compared_as_text(self):
        title = 'Cass <b>"Ridge"</b> \'loop\''
        result, checks = self.run_check(self.site([self.hike(1)], {CASS: title}), title)
        self.assertEqual((result["ok"], checks), (True, {"routeShown": True}), result)

    def test_one_card_without_its_route_line_fails_among_several(self):
        events = [self.hike(1), self.hike(2)]
        files = self.site(events, {CASS: "Cass Hill Loop"})
        ok, checks = self.run_check(files, "Cass Hill Loop")
        self.assertEqual((ok["ok"], checks), (True, {"routeShown": True}), ok)
        # the first card loses its Route line; the second card and the sample archive still read the title
        js = (REPO_ROOT / "storefront-mockup/community.js").read_text()
        self.assertIn("function route(e){", js)
        files["storefront-mockup/community.js"] = js.replace("function route(e){", "function route(e){if(e.id==='h-1')return '';", 1).encode()
        bad, checks = self.run_check(files, "Cass Hill Loop")
        self.assertEqual((bad["ok"], checks), (False, {"routeShown": False}), bad)

    def test_stale_title_containing_the_separator_fails(self):
        # a real past hike switches the sample archive off, so only the linked card's Route line is left to read
        past = {**self.hike(2, trail=BUCHON, status="completed"), "startsAt": "2020-01-01T09:00:00-08:00"}
        files = self.site([self.hike(1), past], {CASS: "Cass Hill Loop \u00b7 Wrong"})
        stale, checks = self.run_check(files, "Cass Hill Loop")
        self.assertEqual((stale["ok"], checks), (False, {"routeShown": False}), stale)


if __name__ == "__main__":
    unittest.main()
