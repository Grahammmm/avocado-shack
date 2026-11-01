"""AV1737-09 tests: hike.create refuses a second scheduled hike with the same title on the same local day.

Runs through prepare + apply of the H02 editor on the throwaway repo of test_hike_ops.HikeRepo (temp content,
synthetic titles, injected clock); the unparseable-start case calls the op directly on an in-memory stub.
Run: python3 -m unittest hass.tests.test_hike_twin -v
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from hass.ops import hikes
from hass.tests.test_editor import git
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, HikeTestCase

TWIN = f"{HIKE_ID} is already scheduled with this title on {HIKE['date']}; update it instead"


class HikeTwinTests(HikeTestCase):
    def ids(self, repo):
        return [e["id"] for e in repo.community()["events"]]

    def refused(self, repo, args):
        return self.assertRejected(repo, "refused", ("hike.create", args))["reason"]

    def test_same_title_same_day_is_refused_naming_the_first(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        self.assertEqual(self.refused(repo, {**HIKE, "time": "14:00", "capacity": 8}), TWIN)
        self.assertEqual(self.ids(repo), [HIKE_ID])  # nothing appended

    def test_case_and_whitespace_do_not_bypass(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        for title in ("TEST HIKE", "test   Hike", "tEsT  hIkE"):
            with self.subTest(title=title):
                self.assertEqual(self.refused(repo, {**HIKE, "title": title}), TWIN)
        self.assertEqual(self.ids(repo), [HIKE_ID])
        content = SimpleNamespace(community={"events": repo.community()["events"]})
        for title in ("  test hike ", "Test\thike\n"):  # outer whitespace and tabs never reach the op; the rule still folds them
            with self.subTest(title=title):
                self.assertEqual(hikes._hike_twin(content, HIKE["date"], title)["id"], HIKE_ID)
        self.assertIsNone(hikes._hike_twin(content, HIKE["date"], "Test hikes"))

    def test_different_day_creates(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.run(("hike.create", {**HIKE, "date": "2026-12-06"}))
        self.assertEqual(self.ids(repo), [HIKE_ID, "hike-2026-12-06-test-hike"])

    def test_cancelled_twin_does_not_count(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.run(("hike.cancel", {"id": HIKE_ID}))
        repo.run(("hike.create", HIKE))
        self.assertEqual(self.ids(repo), [HIKE_ID, HIKE_ID + "-2"])
        self.assertEqual(repo.event(HIKE_ID + "-2")["status"], "scheduled")

    def test_completed_twin_does_not_count(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.now = datetime(2026, 12, 5, 12, 0, tzinfo=timezone(timedelta(hours=-8)))
        repo.run(("hike.complete", {"id": HIKE_ID, "recap": "Done."}))
        repo.run(("hike.create", {**HIKE, "time": "17:30"}))  # later the same local day
        self.assertEqual(self.ids(repo), [HIKE_ID, HIKE_ID + "-2"])

    def test_local_day_not_utc_day(self):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "time": "17:30"}))  # 2026-12-06T01:30Z, still 2026-12-05 Pacific
        self.assertEqual(repo.event()["startsAt"], "2026-12-05T17:30:00-08:00")
        self.assertEqual(self.refused(repo, HIKE), TWIN)
        repo.run(("hike.create", {**HIKE, "date": "2026-12-06", "time": "00:30"}))  # same UTC day, next local day
        self.assertEqual(self.ids(repo), [HIKE_ID, "hike-2026-12-06-test-hike"])

    def test_capacity_question_and_past_start_come_first(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        no_capacity = {k: v for k, v in HIKE.items() if k != "capacity"}
        result = self.assertRejected(repo, "needs-details", ("hike.create", no_capacity))
        self.assertEqual(result["missing"], ["capacity", "noCapacityLimit"])
        repo.now = datetime(2026, 12, 5, 8, 0, tzinfo=timezone(timedelta(hours=-8)))  # twin still scheduled at 09:00
        self.assertEqual(self.refused(repo, {**HIKE, "time": "07:00"}), "start is in the past")
        self.assertEqual(self.refused(repo, {**HIKE, "time": "10:00"}), TWIN)

    def test_route_idea_with_the_base_id_is_not_a_twin(self):
        repo = self.repo()
        path = repo.wt / "hass/content/community.json"
        community = json.loads(path.read_text("utf-8"))
        community["routeIdeas"].append({**community["routeIdeas"][0], "id": HIKE_ID, "title": HIKE["title"]})
        path.write_text(json.dumps(community, ensure_ascii=False, indent=2) + "\n", "utf-8")
        git(repo.wt, "commit", "-q", "-am", "route idea holding the base id")
        repo.run(("hike.create", HIKE))
        self.assertEqual(self.ids(repo), [HIKE_ID + "-2"])

    def test_unparseable_start_is_skipped(self):
        broken = [{"id": f"hike-bad-{n}", "title": HIKE["title"], "status": "scheduled", **extra}
                  for n, extra in enumerate(({"startsAt": "not a time"}, {"startsAt": None}, {}))]
        content = SimpleNamespace(community={"events": list(broken), "routeIdeas": []})
        ctx = SimpleNamespace(now=NOW, warnings=[], settings={})
        touched = hikes._hike_create(content, dict(HIKE), ctx)
        self.assertIsInstance(touched, list, touched)
        self.assertEqual([t.key for t in touched], [HIKE_ID])
        self.assertEqual([e["id"] for e in content.community["events"]], [e["id"] for e in broken] + [HIKE_ID])
