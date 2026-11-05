"""RF1720-3 tests (H06/H13): the store preview check also looks for the street address and town (``addressShown``).

Target tests are pure. Capture tests run the real loopback preview server and Chromium against a StoreRepo writer
worktree holding the full tracked site; they are skipped when PLAYWRIGHT_MODULE is unset (as in test_preview).
Run: python3 -m unittest hass.tests.test_preview_store_address -v
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import preview
from hass.content_model import REPO_ROOT
from hass.tests.test_editor import git
from hass.tests.test_store_ops import INDEX, SET_ADDRESS, StoreTestCase, _req

NEW_STREET = "1023 Example Street"


class TargetTests(StoreTestCase):
    def test_store_target_carries_the_new_street_and_town(self):
        repo = self.repo()
        store = repo.store()
        draft = repo.prepare(_req((SET_ADDRESS, {"streetAddress": NEW_STREET})))["draft"]
        self.assertEqual(preview.target_for(draft["records"][0]),
                         {"kind": "store", "hours": store["hours"], "streetAddress": NEW_STREET, "town": store["town"],
                          "headline": [], "story": None, "intro": None, "homeImage": None, "notice": None})
        town = repo.prepare(_req((SET_ADDRESS, {"town": "Cayucos"})))["draft"]
        self.assertEqual(preview.target_for(town["records"][0])["town"], "Cayucos")

    def test_store_record_without_address_gets_empty_strings(self):
        target = preview.target_for({"collection": "store", "after": {"hours": ["Open daily"]}})
        self.assertEqual(target, {"kind": "store", "hours": ["Open daily"], "streetAddress": "", "town": "",
                                  "headline": [], "story": None, "intro": None, "homeImage": None, "notice": None})
        self.assertEqual(preview.target_for({"collection": "store", "after": None})["streetAddress"], "")

    def test_other_targets_are_byte_equal_to_before(self):
        product = {"name": "Avocados", "status": "active", "description": "Ripe.", "streetAddress": "x", "town": "y"}
        cases = [
            ({"collection": "products", "key": "p-1", "after": product},
             {"kind": "product", "id": "p-1", "name": "Avocados", "status": "active", "description": "Ripe."}),
            ({"collection": "makers", "key": "m-1", "after": {"name": "Farm", "town": "Cayucos"}},
             {"kind": "maker", "key": "m-1", "name": "Farm", "place": "", "hidden": False}),
            ({"collection": "events", "after": {"title": "Hike", "status": "scheduled", "town": "Cayucos"}},
             {"kind": "event", "title": "Hike", "status": "scheduled", "id": "", "recap": ""}),
            ({"collection": "community", "after": {"title": "Club"}},
             {"kind": "event", "title": "Club", "status": None, "id": "", "recap": ""}),
        ]
        for record, expected in cases:
            with self.subTest(collection=record["collection"]):
                self.assertEqual(json.dumps(preview.target_for(record)), json.dumps(expected))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class AddressCaptureTests(StoreTestCase):
    def setUp(self):
        self.store_repo = repo = self.repo()
        wt = repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "full site")
        self.old_index = repo.read(INDEX)
        holder = tempfile.TemporaryDirectory(prefix="hass-rf1720-3-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"

    def move(self, **args):
        """Apply one real store.set_address change; return the preview target its record produces."""
        draft = self.store_repo.run((SET_ADDRESS, args))
        return preview.target_for(draft["records"][0])

    def capture(self, target, files=None, viewports=("phone",)):
        return preview.Previewer(self.store_repo.wt, viewports=viewports).capture(files or {}, target, self.out)

    def test_new_address_is_found_on_phone_and_desktop(self):
        target = self.move(streetAddress=NEW_STREET)
        result = self.capture(target, viewports=preview.VIEWPORTS)
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        for prefix in ("", "desktop:"):
            self.assertIs(result["checks"][prefix + "addressShown"], True)
            self.assertIs(result["checks"][prefix + "hoursShown"], True)

    def test_old_page_with_new_target_fails(self):
        target = self.move(streetAddress=NEW_STREET)
        result = self.capture(target, {INDEX: self.old_index})
        self.assertIs(result["checks"]["addressShown"], False)
        self.assertIs(result["checks"]["hoursShown"], True)
        self.assertEqual((result["ok"], result["error"]), (False, "check failed: addressShown"))

    def test_only_one_of_the_two_forms_fails(self):
        target = self.move(streetAddress=NEW_STREET)
        new = self.store_repo.read(INDEX)
        visit_old = new.replace(f"{NEW_STREET} · ".encode(), "2190 Main Street · ".encode())
        self.assertNotEqual(visit_old, new)
        result = self.capture(target, {INDEX: visit_old})
        self.assertEqual((result["ok"], result["checks"]["addressShown"]), (False, False), result)

    def test_ampersand_in_street_is_found_without_page_errors(self):
        target = self.move(streetAddress="12 Main & Pine")
        self.assertIn(b"12 Main &amp; Pine", self.store_repo.read(INDEX))
        result = self.capture(target)
        self.assertEqual((result["ok"], result["checks"]["addressShown"], result["checks"]["noPageErrors"]),
                         (True, True, True), result)

    def test_empty_town_sets_no_address_check(self):
        target = self.move(streetAddress=NEW_STREET)
        for blank in ({"town": ""}, {"streetAddress": ""}):
            with self.subTest(blank=blank):
                result = self.capture({**target, **blank})
                self.assertNotIn("addressShown", result["checks"])
                self.assertEqual((result["ok"], result["checks"]["hoursShown"]), (True, True), result)


if __name__ == "__main__":
    unittest.main()
