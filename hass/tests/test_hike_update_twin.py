"""RF0740-4 tests: hike.update refuses a title/date change that makes a same-day twin of another scheduled hike.

Runs through prepare + apply of the H02 editor on the throwaway repo of test_hike_ops.HikeRepo (temp content,
synthetic titles, injected clock); the unparseable-start case calls the op directly on an in-memory stub.
Run: python3 -B -m unittest hass.tests.test_hike_update_twin -v
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from hass.ops import hikes
from hass.tests.test_editor import git
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, HikeTestCase

OTHER = {**HIKE, "title": "Other hike", "date": "2026-12-06"}
OTHER_ID = "hike-2026-12-06-other-hike"
TWIN = f"{HIKE_ID} is already scheduled with this title on {HIKE['date']}"
PACIFIC = timezone(timedelta(hours=-8))


class HikeUpdateTwinTests(HikeTestCase):
    def pair(self, other=OTHER):
        repo = self.repo()
        repo.run(("hike.create", HIKE), ("hike.create", other))
        return repo

    def refused(self, repo, args):
        return self.assertRejected(repo, "refused", ("hike.update", args))["reason"]

    def test_move_onto_the_day_of_a_same_titled_hike_is_refused(self):
        repo = self.pair({**OTHER, "title": HIKE["title"]})
        other_id = "hike-2026-12-06-test-hike"
        before = repo.community()["events"]
        self.assertEqual(self.refused(repo, {"id": other_id, "date": HIKE["date"]}), TWIN)
        self.assertEqual(self.refused(repo, {"id": other_id, "date": HIKE["date"], "time": "15:00"}), TWIN)
        self.assertEqual(repo.community()["events"], before)  # content unchanged

    def test_rename_on_the_same_day_ignores_case_and_spacing(self):
        repo = self.pair({**OTHER, "date": HIKE["date"]})
        other_id = "hike-2026-12-05-other-hike"
        for title in ("Test hike", "TEST  HIKE", "tEsT   hike"):
            with self.subTest(title=title):
                self.assertEqual(self.refused(repo, {"id": other_id, "title": title}), TWIN)
        self.assertEqual(repo.event(other_id)["title"], "Other hike")

    def test_move_and_rename_together_is_refused(self):
        repo = self.pair()
        self.assertEqual(self.refused(repo, {"id": OTHER_ID, "date": HIKE["date"], "title": "test hike"}), TWIN)
        self.assertEqual((repo.event(OTHER_ID)["title"], repo.event(OTHER_ID)["startsAt"]),
                         ("Other hike", "2026-12-06T09:00:00-08:00"))

    def test_own_title_and_own_date_are_never_a_twin_of_itself(self):
        repo = self.pair()
        repo.run(("hike.update", {"id": HIKE_ID, "title": "TEST  Hike", "date": HIKE["date"]}))
        repo.run(("hike.update", {"id": HIKE_ID, "title": HIKE["title"], "date": HIKE["date"], "time": "10:00"}))
        self.assertEqual((repo.event()["title"], repo.event()["startsAt"]), ("Test hike", "2026-12-05T10:00:00-08:00"))

    def test_cancelled_twin_does_not_count(self):
        repo = self.pair()
        repo.run(("hike.cancel", {"id": HIKE_ID}))
        repo.run(("hike.update", {"id": OTHER_ID, "date": HIKE["date"], "title": HIKE["title"]}))
        self.assertEqual((repo.event(OTHER_ID)["title"], repo.event(OTHER_ID)["startsAt"]),
                         ("Test hike", "2026-12-05T09:00:00-08:00"))

    def test_completed_twin_does_not_count(self):
        repo = self.pair()
        repo.now = datetime(2026, 12, 5, 12, 0, tzinfo=PACIFIC)
        repo.run(("hike.complete", {"id": HIKE_ID, "recap": "Done."}))
        repo.run(("hike.update", {"id": OTHER_ID, "date": HIKE["date"], "time": "17:30", "title": HIKE["title"]}))
        self.assertEqual(repo.event(OTHER_ID)["startsAt"], "2026-12-05T17:30:00-08:00")

    def test_same_title_on_a_different_day_applies(self):
        repo = self.pair()
        repo.run(("hike.update", {"id": OTHER_ID, "title": "TEST hike"}))
        repo.run(("hike.update", {"id": OTHER_ID, "date": "2026-12-07"}))
        self.assertEqual((repo.event(OTHER_ID)["title"], repo.event(OTHER_ID)["startsAt"]),
                         ("TEST hike", "2026-12-07T09:00:00-08:00"))

    def test_time_only_change_is_not_checked(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        path = repo.wt / "hass/content/community.json"
        community = json.loads(path.read_text("utf-8"))  # a same-day twin pair written before this rule existed
        community["events"].append({**community["events"][0], "id": HIKE_ID + "-2",
                                    "startsAt": "2026-12-05T14:00:00-08:00"})
        path.write_text(json.dumps(community, ensure_ascii=False, indent=2) + "\n", "utf-8")
        git(repo.wt, "commit", "-q", "-am", "legacy same-day twin")
        repo.run(("hike.update", {"id": HIKE_ID + "-2", "time": "15:00"}))
        self.assertEqual(repo.event(HIKE_ID + "-2")["startsAt"], "2026-12-05T15:00:00-08:00")
        self.assertEqual(self.refused(repo, {"id": HIKE_ID + "-2", "title": "Test Hike"}), TWIN)

    def test_past_start_refusal_comes_first(self):
        repo = self.pair({**OTHER, "title": HIKE["title"]})
        repo.now = datetime(2026, 12, 5, 8, 0, tzinfo=PACIFIC)  # twin still scheduled at 09:00
        other_id = "hike-2026-12-06-test-hike"
        self.assertEqual(self.refused(repo, {"id": other_id, "date": HIKE["date"], "time": "07:00"}),
                         "start is in the past")
        self.assertEqual(self.refused(repo, {"id": other_id, "date": HIKE["date"]}), TWIN)

    def test_unparseable_start_elsewhere_is_skipped(self):
        broken = [{"id": f"hike-bad-{n}", "title": HIKE["title"], "status": "scheduled", **extra}
                  for n, extra in enumerate(({"startsAt": "not a time"}, {"startsAt": None}, {}))]
        target = {"id": OTHER_ID, "title": "Other hike", "status": "scheduled", "startsAt": "2026-12-05T09:00:00-08:00",
                  "timezone": "America/Los_Angeles", "meetingPoint": "Lot", "rsvpEnabled": False}
        content = SimpleNamespace(community={"events": broken + [target], "routeIdeas": []})
        ctx = SimpleNamespace(now=NOW, warnings=[], settings={})
        touched = hikes._hike_update(content, {"id": OTHER_ID, "title": HIKE["title"], "date": HIKE["date"]}, ctx)
        self.assertIsInstance(touched, list, touched)
        self.assertEqual([t.key for t in touched], [OTHER_ID])
        self.assertEqual(target["title"], HIKE["title"])
