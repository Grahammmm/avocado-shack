"""AV2152-08 (H13): a home notice may start on a later Pacific day (``store.set_notice`` optional ``from``).

Saved first/last days decide visibility (both inclusive); the generated page carries a not-yet-started notice hidden with
``data-from`` and the page script shows it on that day. Capture tests need PLAYWRIGHT_MODULE.
Run: PLAYWRIGHT_MODULE=... python3 -B -m unittest hass.tests.test_notice_start -v
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from hass import editor, preview, sitegen
from hass.content_model import REPO_ROOT, load_content, shop_today, validate_store
from hass.tests.test_editor import git
from hass.tests.test_store_notice import CLEAR, INDEX, SET, STORE, TEXT, day, result
from hass.tests.test_store_ops import REVERT, StoreTestCase, _req

STORY, NEW_STORY = "store.set_story", "Michael stocks the shelves with fruit from growers he knows by name."


def legacy(repo, notice):
    """Commit a legacy {text, until} notice and its generated pages in the throwaway repo."""
    content = load_content(repo.wt / "hass/content")
    content.store["notice"] = notice
    (repo.wt / "hass/content/store.json").write_text(json.dumps(content.store))
    sitegen.write_files(sitegen.render(content, repo.wt / "hass/templates"), repo.wt)
    git(repo.wt, "add", "-A")
    git(repo.wt, "commit", "-qm", "legacy notice")


class SetFirstDayTests(StoreTestCase):
    def test_default_today_explicit_range_and_replacement(self):
        repo = self.repo()
        repo.run((SET, {"text": TEXT, "until": day(3)}))  # no from = today, saved
        self.assertEqual(repo.store()["notice"], {"text": TEXT, "from": day(0), "until": day(3)})
        for first, until in ((day(0), day(0)), (day(2), day(2)), (day(60), day(60)), (day(1), day(60))):
            repo.run((SET, {"text": "Open late Friday", "from": first, "until": until}))
            self.assertEqual(repo.store()["notice"], {"text": "Open late Friday", "from": first, "until": until})
        self.assertEqual(repo.text(INDEX).count('class="home-notice"'), 1)
        # replacement: only the first day differs -> a real change, once; the identical call is refused
        repo.run((SET, {"text": TEXT, "from": day(1), "until": day(5)}))
        commits = repo.commits()
        self.assertEqual(result(repo, SET, {"text": "Closed  Thanksgiving   Day", "from": day(1), "until": day(5)}),
                         ("refused", "the home page already shows that notice"))
        repo.run((SET, {"text": TEXT, "from": day(2), "until": day(5)}))
        self.assertEqual((repo.commits(), repo.store()["notice"]), (commits + 1, {"text": TEXT, "from": day(2), "until": day(5)}))
        repo.run((SET, {"text": TEXT, "until": day(5)}))  # no from now means today: also a different first day
        self.assertEqual(repo.store()["notice"], {"text": TEXT, "from": day(0), "until": day(5)})
        self.assertEqual(result(repo, SET, {"text": TEXT, "until": day(5)}), ("refused", "the home page already shows that notice"))

    def test_legacy_record_set_clear_and_undo_restore_the_exact_shape(self):
        repo = self.repo()
        old = {"text": TEXT, "until": day(4)}
        legacy(repo, old)
        before, head = repo.store(), repo.head()
        self.assertEqual(result(repo, SET, {"text": TEXT, "until": day(4)}), ("refused", "the home page already shows that notice"))
        self.assertEqual(repo.head(), head)  # a legacy record started already: its effective first day is today
        change = repo.run((SET, {"text": TEXT, "from": day(1), "until": day(4)}))
        self.assertEqual(repo.store()["notice"], {"text": TEXT, "from": day(1), "until": day(4)})
        repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertEqual((repo.store(), repo.status()), (before, ""))
        self.assertEqual(repo.store()["notice"], old)
        change = repo.run((CLEAR, {}))
        self.assertNotIn("notice", repo.store())
        repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertEqual(repo.store(), before)

    def test_first_day_invalid_and_historical_validation(self):
        repo = self.repo()
        head = repo.head()
        self.assertEqual(result(repo, SET, {"text": TEXT, "from": day(-1), "until": day(3)}),
                         ("refused", f"the first day {day(-1)} is already past"))
        self.assertEqual(result(repo, SET, {"text": TEXT, "from": day(3), "until": day(2)}),
                         ("refused", f"the first day {day(3)} is after the last day {day(2)}"))
        for bad in ("2026-02-30", "2026-02-29", "next week", None, 20261126, ["2026-11-20"]):
            with self.subTest(bad=bad):
                self.assertEqual(result(repo, SET, {"text": TEXT, "from": bad, "until": day(3)})[0], "invalid")
        self.assertEqual(result(repo, SET, {"text": TEXT, "start": day(1), "until": day(3)})[0], "invalid")
        for bad in ("<b>Closed</b>", "$5 off", "a\nb"):
            self.assertEqual(result(repo, SET, {"text": bad, "from": day(1), "until": day(3)})[0], "invalid")
        self.assertEqual(result(repo, SET, {"text": "a" * 161, "from": day(1), "until": day(3)}),
                         ("refused", "the notice is longer than 160 characters"))
        self.assertEqual(result(repo, SET, {"text": TEXT, "from": day(1), "until": day(61)}),
                         ("refused", "the last day is more than 60 days ahead"))
        self.assertEqual((repo.head(), repo.drafts(), repo.status(), "notice" in repo.store()), (head, [], "", False))

    def test_stored_shape_is_validated_without_todays_clock(self):
        def problems(notice):
            found = []
            validate_store(found, {**STORE, "notice": notice})
            return found
        for ok in ({"text": TEXT, "until": "2020-01-05"}, {"text": TEXT, "from": "2020-01-01", "until": "2020-01-05"},
                   {"text": TEXT, "from": "2020-01-05", "until": "2020-01-05"}, {"text": TEXT, "from": "2099-01-01", "until": "2099-01-02"}):
            self.assertEqual(problems(ok), [], ok)
        for bad in ({"text": TEXT, "from": "2020-01-06", "until": "2020-01-05"}, {"text": TEXT, "from": None, "until": "2020-01-05"},
                    {"text": TEXT, "from": 20200101, "until": "2020-01-05"}, {"text": TEXT, "from": "2020-02-30", "until": "2020-03-05"},
                    {"text": TEXT, "from": "2020-01-01"}, {"text": TEXT, "from": "2020-01-01", "until": "2020-01-05", "extra": 1}):
            found = problems(bad)
            self.assertTrue(found and all(p.startswith("store.notice") for p in found), (bad, found))


class DraftWordsTests(unittest.TestCase):
    def test_owner_reads_the_first_day_of_a_notice_set_ahead(self):
        from hass.voice import value_words
        notice = {"text": TEXT, "from": "2026-11-20", "until": "2026-11-26"}
        self.assertEqual(value_words(notice, "notice"), f"{TEXT} (from November 20 until November 26)")
        self.assertEqual(value_words({"text": TEXT, "until": "2026-11-26"}, "notice"), f"{TEXT} (until November 26)")
        self.assertEqual(value_words({**notice, "extra": 1}, "notice"), "more than I can show here")


class RenderTests(unittest.TestCase):
    def render(self, notice, today):
        content = load_content()
        content.store["notice"] = notice
        return sitegen.render(content, today=today)[INDEX].decode("utf-8")

    def test_hidden_before_start_active_through_until_then_omitted(self):
        notice = {"text": 'Salt & "pepper" day', "from": "2026-11-20", "until": "2026-11-26"}
        attrs = 'data-from="2026-11-20" data-until="2026-11-26" role="status">Salt &amp; "pepper" day</p>\n'
        before, first, last = (self.render(notice, date(2026, 11, d)) for d in (19, 20, 26))
        self.assertIn(f'<main><p class="home-notice" hidden {attrs}', before)
        for page in (first, last):
            self.assertIn(f'<main><p class="home-notice" {attrs}', page)
            self.assertNotIn("hidden data-from", page)
        for page in (before, first, last):
            self.assertEqual((page.count('class="home-notice"'), page.count(sitegen.NOTICE_JS + "</body>")), (1, 1))
        after = self.render(notice, date(2026, 11, 27))
        self.assertEqual(after.encode(), (REPO_ROOT / INDEX).read_bytes())  # the unchanged no-notice page
        self.assertEqual(sitegen.store_slots({**STORE, "notice": notice}, date(2026, 11, 27))["store.noticeScript"], "")

    def test_legacy_notice_renders_as_before(self):
        page = self.render({"text": "Closed", "until": "2026-11-26"}, date(2026, 11, 26))
        self.assertIn('<main><p class="home-notice" data-until="2026-11-26" role="status">Closed</p>\n', page)


class PhaseCheckTests(StoreTestCase):
    """The generated-file check accepts the exact earlier notice-phase renders and nothing else."""

    def setUp(self):
        self.repo_ = repo = self.repo()
        repo.run((SET, {"text": TEXT, "from": day(3), "until": day(5)}))
        self.hidden = repo.read(INDEX)
        self.assertIn(b"home-notice\" hidden data-from", self.hidden)

    def check(self, today, repo=None):
        repo = repo or self.repo_
        with mock.patch.object(sitegen, "shop_today", return_value=today):
            return sitegen.main(["--check", "--repo", str(repo.wt)]), editor._post_checks(repo.wt)

    def render_at(self, offset):
        content = load_content(self.repo_.wt / "hass/content")
        return sitegen.render(content, self.repo_.wt / "hass/templates", today=shop_today() + timedelta(days=offset))[INDEX]

    def test_before_start_render_is_accepted_during_and_after_the_window(self):
        for offset in (0, 3, 4, 5, 6, 30):
            with self.subTest(offset=offset):
                self.assertEqual(self.check(shop_today() + timedelta(days=offset)), (0, []))
        self.assertEqual(self.repo_.read(INDEX), self.hidden)  # checks write nothing
        self.assertEqual(self.repo_.status(), "")

    def test_active_render_is_accepted_only_after_the_last_day(self):
        active = self.render_at(4)
        self.assertNotIn(b"hidden data-from", active)
        (self.repo_.wt / INDEX).write_bytes(active)
        self.assertEqual(self.check(shop_today() + timedelta(days=6))[0], 0)  # generated on a day it was active
        self.assertEqual(self.check(shop_today() + timedelta(days=5))[0], 0)  # its last day: the current render
        self.assertEqual(self.check(shop_today() + timedelta(days=2))[0], 1)  # a future active render before its first day
        self.assertEqual(self.check(shop_today())[0], 1)
        self.assertEqual(self.repo_.read(INDEX), active)

    def test_wrong_dates_text_script_and_unrelated_drift_are_rejected(self):
        today = shop_today() + timedelta(days=6)
        for name, edit in (("first day", lambda b: b.replace(f'data-from="{day(3)}"'.encode(), f'data-from="{day(2)}"'.encode())),
                           ("last day", lambda b: b.replace(f'data-until="{day(5)}"'.encode(), f'data-until="{day(6)}"'.encode())),
                           ("text", lambda b: b.replace(TEXT.encode(), b"Wrong notice")),
                           ("script", lambda b: b.replace(b"day<f", b"day<g")),
                           ("unrelated", lambda b: b + b"<!-- drift -->")):
            with self.subTest(name):
                (self.repo_.wt / INDEX).write_bytes(edit(self.hidden))
                self.assertEqual(self.check(today)[0], 1)
                self.assertTrue(self.check(today)[1])
        (self.repo_.wt / INDEX).write_bytes(self.hidden)
        catalog = self.repo_.wt / "storefront-mockup/catalog-products.js"
        original = catalog.read_bytes()
        catalog.write_bytes(original + b"\n// drift")
        self.assertEqual(self.check(today)[0], 1)  # a notice phase never hides other drift
        catalog.write_bytes(original)
        (self.repo_.wt / INDEX).unlink()
        self.assertEqual(self.check(today)[0], 1)
        (self.repo_.wt / INDEX).symlink_to(self.repo_.wt / "storefront-mockup/hike/index.html")
        self.assertEqual(self.check(today)[0], 1)

    def test_historical_checkout_keeps_checking_and_the_story_edit_keeps_the_phase(self):
        record = self.repo_.run((STORY, {"text": NEW_STORY}))["records"][0]
        self.assertEqual(record["after"]["notice"], {"text": TEXT, "from": day(3), "until": day(5)})
        self.assertEqual(self.check(shop_today() + timedelta(days=6)), (0, []))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class NoticeClockTests(unittest.TestCase):
    def test_open_page_enters_and_leaves_window_pacific(self):
        import subprocess
        out = subprocess.run(["node", str(Path(__file__).with_name("notice_expiry.cjs"))], input="<script>" + (REPO_ROOT / "storefront-mockup/notice.js").read_text("utf-8") + "</script>",
                             text=True, capture_output=True, timeout=180)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        for phrase in ("appears at its first Pacific midnight", "first and last day are inclusive", "both directions on load",
                       "background and pageshow recovery"):
            self.assertIn(phrase, out.stdout)


class TargetTests(StoreTestCase):
    def target(self, repo, today=None, notice=None):
        record = repo.run((SET, notice or {"text": TEXT, "from": day(3), "until": day(5)}))["records"][0]
        return preview.target_for(record, today), record

    def test_scheduled_active_ended_names_the_first_day(self):
        repo = self.repo()
        window = {"text": TEXT, "from": day(3), "until": day(5)}
        _, record = self.target(repo)
        for offset, state, notice in ((0, "scheduled", None), (3, "active", TEXT), (5, "active", TEXT), (6, "ended", None)):
            target = preview.target_for(record, shop_today() + timedelta(days=offset))
            with self.subTest(state=state, offset=offset):
                self.assertEqual((target["noticeWindow"], target["notice"]), ({**window, "state": state}, notice))

    def test_legacy_and_malformed_targets(self):
        repo = self.repo()
        _, record = self.target(repo)
        legacy_record = {**record, "after": {**record["after"], "notice": {"text": TEXT, "until": day(5)}}}
        self.assertNotIn("noticeWindow", preview.target_for(legacy_record))
        for bad in ({"text": TEXT, "from": "2026-02-30", "until": day(5)}, {"text": TEXT, "from": day(6), "until": day(5)},
                    {"text": TEXT, "from": None, "until": day(5)}, {"text": TEXT, "from": 5, "until": day(5)},
                    {"text": TEXT, "from": day(1)}, {"text": None, "from": day(1), "until": day(5)}):
            with self.subTest(bad=bad):
                target = preview.target_for({**record, "after": {**record["after"], "notice": bad}})
                self.assertEqual(target, {"kind": "unreadable"})


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class ScheduledCaptureTests(StoreTestCase):
    def setUp(self):  # as test_store_notice.NoticeCaptureTests: the full site in a throwaway repo
        self.store_repo = repo = self.repo()
        wt = repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "full site")
        self.old_index = repo.read(INDEX)
        self.out = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="hass-av2152-08-"))) / "shot.png"

    def capture(self, target, files=None, viewports=preview.VIEWPORTS):
        return preview.Previewer(self.store_repo.wt, viewports=viewports).capture(files or {}, target, self.out)

    def scheduled(self):
        record = self.store_repo.run((SET, {"text": TEXT, "from": day(3), "until": day(5)}))["records"][0]
        return preview.target_for(record)

    def test_scheduled_preview_phone_desktop(self):
        target = self.scheduled()
        self.assertEqual((target["notice"], target["noticeWindow"]["state"], target["noticeWindow"]["from"]), (None, "scheduled", day(3)))
        result = self.capture(target)
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        for prefix in ("", "desktop:"):
            self.assertIs(result["checks"][prefix + "noticeWindow"], True)
        index = self.store_repo.read(INDEX)
        early = index.replace(b'home-notice" hidden', b'home-notice"').replace(sitegen.NOTICE_JS.encode(), b"")  # visible, no script
        for name, page in (("early visible", early), ("missing node", self.old_index),
                           ("wrong first day", index.replace(f'data-from="{day(3)}"'.encode(), f'data-from="{day(2)}"'.encode())),
                           ("wrong last day", index.replace(f'data-until="{day(5)}"'.encode(), f'data-until="{day(6)}"'.encode())),
                           ("wrong text", index.replace(TEXT.encode(), b"Other words"))):
            with self.subTest(name):
                got = self.capture(target, {INDEX: page}, ("phone",))
                self.assertEqual((got["ok"], got["checks"]["noticeWindow"]), (False, False), got)

    def test_active_and_ended_windows(self):
        record = self.store_repo.run((SET, {"text": TEXT, "from": day(0), "until": day(1)}))["records"][0]
        active = preview.target_for(record)
        self.assertEqual(active["noticeWindow"]["state"], "active")
        result = self.capture(active)
        self.assertEqual((result["ok"], result["error"], result["checks"]["noticeShown"], result["checks"]["noticeWindow"]),
                         (True, None, True, True), result)
        hidden = self.store_repo.read(INDEX).replace(b'home-notice"', b'home-notice" hidden').replace(sitegen.NOTICE_JS.encode(), b"")
        self.assertEqual(self.capture(active, {INDEX: hidden}, ("phone",))["checks"]["noticeWindow"], False)
        later = shop_today() + timedelta(days=2)
        ended = preview.target_for(record, later)
        self.assertEqual((ended["noticeWindow"]["state"], ended["notice"]), ("ended", None))
        gone = sitegen.render(load_content(self.store_repo.wt / "hass" / "content"), today=later)[INDEX]
        self.assertNotIn(b'class="home-notice"', gone)
        self.assertEqual(self.capture(ended, {INDEX: gone}, ("phone",))["ok"], True)  # absent is valid
        visible = self.capture(ended, {INDEX: self.store_repo.read(INDEX)}, ("phone",))  # the page still shows it after its last day
        self.assertEqual((visible["ok"], visible["checks"]["noticeWindow"]), (False, False), visible)


if __name__ == "__main__":
    unittest.main()
