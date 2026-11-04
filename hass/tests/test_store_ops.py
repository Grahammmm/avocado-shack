"""H13 tests: store hours and address ops (hass/ops/store.py).

Every change goes through ``editor.prepare`` + ``editor.apply`` on a throwaway Git repo with a linked writer worktree
and a private temp state dir (see test_editor.WriterRepo), using the production op registry. Nothing touches the
checkout, the live service or its database.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import unittest
from urllib.parse import quote_plus

from hass import editor, migration_check, sitegen
from hass.content_model import load_and_validate
from hass.tests.test_editor import WriterRepo, git

NEW_HOURS = ["Monday–Saturday 9am–6pm", "Closed Sunday"]
SET_HOURS, SET_ADDRESS, REVERT = "store.set_hours", "store.set_address", "history.revert"
INDEX, HIKE = "storefront-mockup/index.html", "storefront-mockup/hike/index.html"


def _req(*ops):
    return {"ops": [{"op": name, "args": args} for name, args in ops]}


class StoreRepo(WriterRepo):
    """WriterRepo using the production op registry (hass.ops.store, hass.ops.history)."""

    def prepare(self, request):
        return editor.prepare(request, state=str(self.state))

    def apply(self, draft):
        return editor.apply(draft["change_id"], draft["draft_hash"], state=str(self.state))

    def run(self, *ops):
        draft = self.prepare(_req(*ops))
        assert draft["result"] == "ok", draft
        assert self.apply(draft["draft"])["result"] == "applied"
        return draft["draft"]

    def read(self, rel):
        return (self.wt / rel).read_bytes()

    def text(self, rel):
        return self.read(rel).decode("utf-8")

    def store(self):
        return json.loads(self.read("hass/content/store.json"))

    def commits(self):
        return int(git(self.wt, "rev-list", "--count", "HEAD"))


class StoreTestCase(unittest.TestCase):
    def repo(self):
        repo = StoreRepo()
        self.addCleanup(repo.cleanup)
        return repo


def maps_url(store):
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(
        f"{store['name']} {store['streetAddress']} {store['town']}")


class HoursAndAddressTests(StoreTestCase):
    def test_set_hours_changes_only_the_hours_slot(self):
        repo = self.repo()
        before, hike, commits = repo.store(), repo.read(HIKE), repo.commits()
        repo.run((SET_HOURS, {"hours": NEW_HOURS}))
        self.assertEqual(repo.commits(), commits + 1)
        self.assertEqual(repo.store(), {**before, "hours": NEW_HOURS})
        self.assertIn("Monday–Saturday 9am–6pm<br>Closed Sunday", repo.text(INDEX))
        self.assertEqual(repo.read(HIKE), hike)
        content = load_and_validate(repo.wt / "hass" / "content", repo.wt / "storefront-mockup")
        self.assertEqual(sitegen.diff_paths(sitegen.render(content, repo.wt / "hass" / "templates"), repo.wt), [])
        self.assertEqual(migration_check.run_checks(repo.wt)[0], [])
        self.assertEqual(repo.status(), "")

    def test_set_address_keeps_town_and_hours_and_moves_the_maps_link(self):
        repo = self.repo()
        before = repo.store()
        self.assertIn(maps_url(before).replace("&", "&amp;"), repo.text(INDEX))
        repo.run((SET_ADDRESS, {"streetAddress": "1023 Example Street"}))
        after = repo.store()
        self.assertEqual(after, {**before, "streetAddress": "1023 Example Street"})
        for page in (INDEX, HIKE):
            self.assertIn("1023 Example Street, Morro Bay <span>", repo.text(page))
            self.assertNotIn("2190 Main Street", repo.text(page))
        self.assertIn(maps_url(after).replace("&", "&amp;"), repo.text(INDEX))
        self.assertNotIn(maps_url(before).replace("&", "&amp;"), repo.text(INDEX))
        repo.run((SET_ADDRESS, {"town": "Cayucos"}))
        self.assertEqual(repo.store(), {**after, "town": "Cayucos"})
        self.assertEqual(repo.status(), "")

    def test_rejected_input_writes_nothing(self):
        repo = self.repo()
        current = repo.store()
        cases = [
            ("markup line", "invalid", (SET_HOURS, {"hours": ["<b>Open</b>"]})),
            ("dollar line", "invalid", (SET_HOURS, {"hours": ["Free $0 coffee"]})),
            ("NUL character", "invalid", (SET_HOURS, {"hours": ["9am\x00"]})),
            ("empty list", "invalid", (SET_HOURS, {"hours": []})),
            ("string not list", "invalid", (SET_HOURS, {"hours": "9am-6pm"})),
            ("unknown arg", "invalid", (SET_HOURS, {"hours": NEW_HOURS, "name": "Other"})),
            ("8 lines", "refused", (SET_HOURS, {"hours": [f"Day {i} 9am" for i in range(8)]})),
            ("61 characters", "refused", (SET_HOURS, {"hours": ["x" * 61]})),
            ("duplicate lines", "refused", (SET_HOURS, {"hours": ["Open daily", "Open daily"]})),
            ("same hours", "refused", (SET_HOURS, {"hours": current["hours"]})),
            ("no address args", "needs-details", (SET_ADDRESS, {})),
            ("81-char town", "refused", (SET_ADDRESS, {"town": "t" * 81})),
            ("81-char street", "refused", (SET_ADDRESS, {"streetAddress": "s" * 81})),
            ("same address", "refused", (SET_ADDRESS, {"streetAddress": current["streetAddress"], "town": current["town"]})),
            ("markup street", "invalid", (SET_ADDRESS, {"streetAddress": "1 <i>Main</i>"})),
            ("padded town", "invalid", (SET_ADDRESS, {"town": " Cayucos"})),
            ("name via address", "invalid", (SET_ADDRESS, {"name": "Other Shack"})),
            ("name beside address", "invalid", (SET_ADDRESS, {"town": "Cayucos", "name": "Other Shack"})),
            ("schemaVersion", "invalid", (SET_ADDRESS, {"schemaVersion": 2})),
        ]
        for label, expected, call in cases:
            with self.subTest(case=label):
                head, drafts = repo.head(), repo.drafts()
                result = repo.prepare(_req(call))
                self.assertEqual(result["result"], expected, result)
                if expected == "needs-details":
                    self.assertEqual(result["missing"], ["streetAddress", "town"])
                self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, drafts, ""))
        self.assertEqual(repo.drafts(), [])
        self.assertEqual(repo.store(), current)

    def test_refusal_messages(self):
        repo = self.repo()
        current = repo.store()
        self.assertEqual(repo.prepare(_req((SET_HOURS, {"hours": ["a"] * 8})))["reason"], "at most 7 hours lines (you sent 8)")
        self.assertEqual(repo.prepare(_req((SET_HOURS, {"hours": ["ok", "y" * 61]})))["reason"],
                         "hours line 2 is longer than 60 characters")
        self.assertEqual(repo.prepare(_req((SET_HOURS, {"hours": current["hours"]})))["reason"],
                         "store hours are already " + " / ".join(current["hours"]))
        self.assertEqual(repo.prepare(_req((SET_ADDRESS, {"town": "Morro Bay"})))["reason"],
                         "store address is already 2190 Main Street, Morro Bay")
        self.assertEqual(repo.prepare(_req((SET_ADDRESS, {})))["question"],
                         "Which street address or town should the site show?")

    def test_boundary_sizes_are_accepted(self):
        repo = self.repo()
        seven = [f"Line {i}" for i in range(7)]
        repo.run((SET_HOURS, {"hours": seven}))
        self.assertEqual(repo.store()["hours"], seven)
        repo.run((SET_HOURS, {"hours": ["x" * 60]}))
        repo.run((SET_ADDRESS, {"town": "t" * 80}))
        self.assertEqual(len(repo.store()["town"]), 80)
        self.assertEqual(repo.status(), "")


class StoreUndoAndPreviewTests(StoreTestCase):
    def test_undo_restores_hours_and_marks_the_original(self):
        repo = self.repo()
        original = repo.store()["hours"]
        first = repo.run((SET_HOURS, {"hours": NEW_HOURS}))
        commits = repo.commits()
        undo = repo.run((REVERT, {"changeId": first["change_id"]}))
        self.assertEqual(repo.store()["hours"], original)
        self.assertEqual(repo.commits(), commits + 1)
        shown = editor.show(first["change_id"], state=str(repo.state))["change"]
        self.assertEqual(shown["revertedBy"], undo["change_id"])
        again = repo.prepare(_req((REVERT, {"changeId": first["change_id"]})))
        self.assertEqual(again["result"], "refused")
        self.assertIn("already undone", again["reason"])
        self.assertEqual(repo.status(), "")

    def test_older_store_change_cannot_be_undone_after_a_later_one(self):
        repo = self.repo()
        original = repo.store()
        a = repo.run((SET_HOURS, {"hours": NEW_HOURS}))
        b = repo.run((SET_ADDRESS, {"streetAddress": "1023 Example Street"}))
        head, drafts = repo.head(), repo.drafts()
        result = repo.prepare(_req((REVERT, {"changeId": a["change_id"]})))
        self.assertEqual(result["result"], "refused", result)
        self.assertEqual(result["reason"], f"conflict: store store changed after {a['change_id']}")
        self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, drafts, ""))
        repo.run((REVERT, {"changeId": b["change_id"]}))
        self.assertEqual(repo.store(), {**original, "hours": NEW_HOURS})
        self.assertEqual(repo.status(), "")
        # newest-first order works all the way back
        repo.run((REVERT, {"changeId": a["change_id"]}))
        self.assertEqual(repo.store(), original)

    def test_preview_target_is_the_new_hours(self):
        from hass import preview
        repo = self.repo()
        draft = repo.prepare(_req((SET_HOURS, {"hours": NEW_HOURS})))["draft"]
        self.assertEqual(preview.target_for(draft["records"][0]), {"kind": "store", "hours": NEW_HOURS,
                         "streetAddress": "2190 Main Street", "town": "Morro Bay", "headline": [], "story": None, "homeImage": None, "notice": None})
        address = repo.prepare(_req((SET_ADDRESS, {"town": "Cayucos"})))["draft"]
        self.assertEqual(preview.target_for(address["records"][0])["kind"], "store")


if __name__ == "__main__":
    unittest.main()
