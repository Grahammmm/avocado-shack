"""AV1222-04 (H13): ``store.set_phone`` / ``store.clear_phone`` - one store phone in the Visit block and the stale line.

Throwaway Git repo as test_store_ops; numbers are in the fictional 555-01xx range. Browser tests need PLAYWRIGHT_MODULE.
Run: python3 -B -m unittest hass.tests.test_store_phone -v
"""

import copy
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from hass import preview, sitegen
from hass.content_model import REPO_ROOT, load_content, validate_store
from hass.tests.test_editor import git
from hass.tests.test_store_ops import INDEX, REVERT, StoreTestCase, _req

SET, CLEAR = "store.set_phone", "store.clear_phone"
SHOWN = "(805) 555-0123"
LINK = '<p class="visit-phone"><a href="tel:+18055550123">(805) 555-0123</a></p>'
STORE = load_content().store


class PhoneOpTests(StoreTestCase):
    def test_every_accepted_shape_is_stored_as_ten_digits(self):
        for text in ("805 555 0123", "(805) 555-0123", "805.555.0123", "+1 805 555 0123", "18055550123"):
            with self.subTest(text=text):
                repo = self.repo()
                repo.run((SET, {"phone": text}))
                self.assertEqual(repo.store()["phone"], "8055550123")

    def test_bad_numbers_are_refused_and_nothing_is_written(self):
        repo = self.repo()
        head = repo.head()
        for text in ("555 0123", "805 555 01234", "105 555 0123", "805 055 0123", "805-CALL-NOW", "+44 805 555 0123"):
            with self.subTest(text=text):
                result = repo.prepare(_req((SET, {"phone": text})))
                self.assertEqual((result["result"], result["reason"]),
                                 ("refused", "the phone number needs 10 digits, like 805 555 0123"), result)
        self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, [], ""))

    def test_markup_is_never_stored(self):
        repo = self.repo()
        result = repo.prepare(_req((SET, {"phone": "<b>805</b> 555 0123"})))
        self.assertIn(result["result"], ("invalid", "refused"), result)
        self.assertNotIn("phone", repo.store())

    def test_same_number_twice_and_clear_with_none_are_refused(self):
        repo = self.repo()
        self.assertEqual(repo.prepare(_req((CLEAR, {})))["reason"], "there is no phone number to remove")
        repo.run((SET, {"phone": "805 555 0123"}))
        again = repo.prepare(_req((SET, {"phone": "(805) 555-0123"})))
        self.assertEqual((again["result"], again["reason"]), ("refused", "the phone number already says that"))

    def test_page_shows_a_tap_to_call_link_and_clear_and_undo_round_trip(self):
        repo = self.repo()
        original = repo.read(INDEX)
        self.assertNotIn(b"visit-phone", original)
        change = repo.run((SET, {"phone": "805 555 0123"}))
        page = repo.text(INDEX)
        self.assertIn(f"</p>{LINK}<a class=\"text-link\"", page)
        repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertNotIn("phone", repo.store())
        self.assertEqual(repo.read(INDEX), original)
        repo.run((SET, {"phone": "805 555 0123"}))
        cleared = repo.run((CLEAR, {}))
        self.assertNotIn("phone", repo.store())
        self.assertEqual(repo.read(INDEX), original)
        repo.run((REVERT, {"changeId": cleared["change_id"]}))  # undo of clear: the phone is back
        self.assertEqual(repo.store()["phone"], "8055550123")
        self.assertIn(LINK, repo.text(INDEX))
        self.assertEqual(repo.status(), "")


class PhoneModelAndPageTests(unittest.TestCase):
    def problems(self, **changes):
        store = copy.deepcopy(STORE)
        store.update(changes)
        out = []
        validate_store(out, store)
        return out

    def test_demo_store_has_no_phone_and_renders_no_slot(self):
        self.assertNotIn("phone", STORE)
        self.assertEqual(sitegen.store_slots(STORE)["store.phoneHtml"], "")
        self.assertEqual(self.problems(), [])

    def test_hand_edited_formats_are_content_errors_naming_the_field(self):
        for bad in ("805-555-0123", "555 0123", "8055550123 ", "105 555 0123", 8055550123, "８０５５５５０１２３"):
            with self.subTest(bad=bad):
                self.assertEqual(self.problems(phone=bad), ["store.phone: must be 10 digits"])
        self.assertEqual(self.problems(phone="8055550123"), [])

    def test_slot_is_text_and_digits_only(self):
        self.assertEqual(sitegen.store_slots({**STORE, "phone": "8055550123"})["store.phoneHtml"], LINK)

    def test_stale_line_names_the_phone_fresh_has_no_tail_stale_without_is_unchanged(self):
        today = date(2026, 11, 4)
        stale = {**STORE, "selection_checked_on": "2026-10-20", "phone": "8055550123"}
        self.assertEqual(sitegen.checked_line(stale, today),
                         "Selection last checked by Michael on Tuesday, October 20 (more than a week ago - call (805) 555-0123 or visit to confirm).")
        fresh = {**stale, "selection_checked_on": "2026-11-04"}
        self.assertEqual(sitegen.checked_line(fresh, today), "Selection last checked by Michael on Wednesday, November 4.")
        plain = {k: v for k, v in stale.items() if k != "phone"}
        self.assertTrue(sitegen.checked_line(plain, today).endswith("(more than a week ago - call or visit to confirm)."))

    def test_preview_target_carries_the_phone_only_when_it_changes(self):
        base = {"collection": "store", "key": None, "before": {}, "after": {"hours": ["Open daily"], "phone": "8055550123"}}
        self.assertEqual(preview.target_for(base)["phone"], SHOWN)
        cleared = {**base, "before": {"phone": "8055550123"}, "after": {"hours": ["Open daily"]}}
        self.assertIsNone(preview.target_for(cleared)["phone"])
        same = {**base, "before": {"phone": "8055550123"}}
        self.assertNotIn("phone", preview.target_for(same))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class PhoneCaptureTests(StoreTestCase):
    def setUp(self):
        self.r = repo = self.repo()
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (repo.wt / rel).exists():
                (repo.wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, repo.wt / rel)
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-q", "-m", "full site")
        self.old_index = repo.read(INDEX)
        holder = tempfile.TemporaryDirectory(prefix="hass-av1222-04-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"

    def shot(self, draft, files=None):
        target = preview.target_for(draft["records"][0])
        return preview.Previewer(self.r.wt, viewports=("phone",)).capture(files or {}, target, self.out)

    def test_phone_found_and_old_page_fails(self):
        draft = self.r.run((SET, {"phone": "805 555 0123"}))
        good = self.shot(draft)
        self.assertEqual((good["ok"], good["checks"]["phoneShown"]), (True, True), good)
        old = self.shot(draft, {INDEX: self.old_index})
        self.assertEqual((old["checks"]["phoneShown"], old["error"]), (False, "check failed: phoneShown"))

    def test_clear_expects_no_phone_line(self):
        self.r.run((SET, {"phone": "805 555 0123"}))
        draft = self.r.run((CLEAR, {}))
        self.assertIs(self.shot(draft)["checks"]["phoneShown"], True)
        with_phone = self.r.read(INDEX).decode().replace('<a class="text-link" href="https://', LINK + '<a class="text-link" href="https://', 1)
        self.assertIs(self.shot(draft, {INDEX: with_phone.encode()})["checks"]["phoneShown"], False)
