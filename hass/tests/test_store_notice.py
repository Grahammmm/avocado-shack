"""AV1322-01 (H13): one dated owner notice on the home page (``store.set_notice`` / ``store.clear_notice``, hass/ops/home.py).

Changes go through editor.prepare + apply on a throwaway repo (test_store_ops.StoreRepo); capture tests need PLAYWRIGHT_MODULE.
Run: python3 -m unittest hass.tests.test_store_notice -v
"""

import os, shutil, tempfile, unittest  # noqa: E401
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from unittest import mock

from hass import editor, preview, sitegen, statebackup
from hass.conversation import Conversation
from hass.content_model import REPO_ROOT, load_content, shop_today, validate_store
from hass.ops import OpContext, Refused, load_registry
from hass.tests.test_editor import git
from hass.tests.test_store_ops import INDEX, REVERT, StoreTestCase, _req

SET, CLEAR, TEXT = "store.set_notice", "store.clear_notice", "Closed Thanksgiving Day"
STORY, NEW_STORY = "store.set_story", "Michael stocks the shelves with fruit from growers he knows by name."
STORE = load_content().store


def day(offset):
    return (shop_today() + timedelta(days=offset)).isoformat()


def result(repo, op, args):
    out = repo.prepare(_req((op, args)))
    return out["result"], out.get("reason")


class NoticeOpTests(StoreTestCase):
    def test_no_notice_renders_todays_page_byte_for_byte(self):
        self.assertNotIn("notice", STORE)
        self.assertEqual(sitegen.main(["--check"]), 0)
        self.assertEqual(sitegen.render(load_content())[INDEX], (REPO_ROOT / INDEX).read_bytes())
        self.assertEqual(sitegen.store_slots(STORE)["store.noticeHtml"], "")

    def test_shown_through_until_and_empty_the_day_after(self):
        content = load_content()
        content.store["notice"] = {"text": TEXT, "until": "2026-11-26"}
        shown = sitegen.render(content, today=date(2026, 11, 26))[INDEX].decode("utf-8")
        self.assertEqual(shown.count('class="home-notice"'), 1)
        self.assertIn(f'<main><p class="home-notice" data-until="2026-11-26" role="status">{TEXT}</p>\n', shown)
        self.assertEqual(shown.count(sitegen.NOTICE_JS + "</body>"), 1)
        after = sitegen.render(content, today=date(2026, 11, 27))[INDEX]
        self.assertEqual(sitegen.store_slots(content.store, date(2026, 11, 27))["store.noticeHtml"], "")
        self.assertEqual(after, (REPO_ROOT / INDEX).read_bytes())

    def test_consistency_across_expiry_and_real_drift(self):
        from types import SimpleNamespace
        repo = self.repo()
        change = repo.run((SET, {"text": TEXT, "until": day(0)}))
        before = repo.read(INDEX)
        tomorrow = shop_today() + timedelta(days=1)
        verifier = SimpleNamespace(sdir=repo.state, editor=SimpleNamespace(show=lambda _: {"change": change}),
                                   previewer=SimpleNamespace(capture=lambda *a: {"ok": True, "png": "checked.png"}))
        with mock.patch.object(sitegen, "shop_today", return_value=tomorrow):
            self.assertEqual(sitegen.main(["--check", "--repo", str(repo.wt)]), 0)
            self.assertEqual(editor._post_checks(repo.wt), [])
            self.assertEqual(Conversation.verify(verifier, {"change_id": change["change_id"]}), ("checked.png", None, [False]))
            self.assertEqual(repo.read(INDEX), before)  # checks must not rewrite history
            (repo.wt / INDEX).write_bytes(before.replace(TEXT.encode(), b"Wrong notice"))
            self.assertEqual(sitegen.main(["--check", "--repo", str(repo.wt)]), 1)
            self.assertTrue(editor._post_checks(repo.wt))
            self.assertIn("out of date", Conversation.verify(verifier, {"change_id": change["change_id"]})[1])
            sitegen.write_files(sitegen.render(load_content(repo.wt / "hass/content"), repo.wt / "hass/templates"), repo.wt)
            self.assertNotIn(b'class="home-notice"', repo.read(INDEX))
            self.assertEqual(editor._post_checks(repo.wt), [])

    def test_historical_checkout_check_after_expiry(self):
        import json
        repo = self.repo()
        content = load_content(repo.wt / "hass/content")
        yesterday = shop_today() - timedelta(days=1)
        content.store["notice"] = {"text": TEXT, "until": yesterday.isoformat()}
        (repo.wt / "hass/content/store.json").write_text(json.dumps(content.store))
        sitegen.write_files(sitegen.render(content, repo.wt / "hass/templates", today=yesterday), repo.wt)
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-qm", "historical notice")
        self.assertEqual(statebackup._site_check(repo.wt), "ok")
        self.assertEqual(repo.status(), "")
        (repo.wt / INDEX).write_bytes(repo.read(INDEX) + b"<!-- corruption -->")
        self.assertEqual(statebackup._site_check(repo.wt), "failed")

    def test_set_then_undo_returns_to_the_identical_default_page(self):
        repo = self.repo()
        original, before = repo.read(INDEX), repo.store()
        change = repo.run((SET, {"text": TEXT, "until": day(0)}))
        self.assertEqual(repo.store(), {**before, "notice": {"text": TEXT, "until": day(0)}})
        self.assertIn(f'role="status">{TEXT}</p>', repo.text(INDEX))
        repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertNotIn("notice", repo.store())
        self.assertEqual((repo.store(), repo.read(INDEX), repo.status()), (before, original, ""))

    def test_until_window_yesterday_refused_sixty_days_ok_sixty_one_refused(self):
        repo = self.repo()
        self.assertEqual(result(repo, SET, {"text": TEXT, "until": day(-1)}),
                         ("refused", f"the last day {day(-1)} is already past"))
        self.assertEqual(result(repo, SET, {"text": TEXT, "until": day(61)}),
                         ("refused", "the last day is more than 60 days ahead"))
        self.assertEqual(result(repo, SET, {"text": TEXT, "until": "2026-02-30"})[0], "invalid")
        self.assertEqual(repo.drafts(), [])
        repo.run((SET, {"text": TEXT, "until": day(60)}))
        self.assertEqual(repo.store()["notice"]["until"], day(60))

    def test_length_markup_dollar_control_and_letters(self):
        repo = self.repo()
        head = repo.head()
        self.assertEqual(result(repo, SET, {"text": "a" * 161, "until": day(1)}),
                         ("refused", "the notice is longer than 160 characters"))
        self.assertEqual(result(repo, SET, {"text": "!!", "until": day(1)}),
                         ("refused", "the notice needs at least 3 letters"))
        for bad in ("<b>Closed</b>", "$5 off", "a\nb", "Closed {{x}}", "Closed\u200b today"):
            with self.subTest(bad=bad):
                self.assertEqual(result(repo, SET, {"text": bad, "until": day(1)})[0], "invalid")
        self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, [], ""))
        repo.run((SET, {"text": "a" * 160, "until": day(1)}))
        self.assertEqual(repo.store()["notice"]["text"], "a" * 160)

    def test_same_notice_refused_new_until_or_text_replaces_the_one_slot(self):
        repo = self.repo()
        repo.run((SET, {"text": TEXT, "until": day(5)}))
        self.assertEqual(result(repo, SET, {"text": "Closed  Thanksgiving   Day", "until": day(5)}),
                         ("refused", "the home page already shows that notice"))
        repo.run((SET, {"text": TEXT, "until": day(6)}))
        repo.run((SET, {"text": "Open late Friday", "until": day(6)}))
        self.assertEqual(repo.store()["notice"], {"text": "Open late Friday", "until": day(6)})
        self.assertEqual(repo.text(INDEX).count('class="home-notice"'), 1)
        self.assertNotIn(TEXT, repo.text(INDEX))

    def test_clear_notice_removes_it_and_is_refused_when_none(self):
        repo = self.repo()
        original = repo.read(INDEX)
        self.assertEqual(result(repo, CLEAR, {}), ("refused", "there is no notice"))
        repo.run((SET, {"text": TEXT, "until": day(2)}))
        repo.run((CLEAR, {}))
        self.assertNotIn("notice", repo.store())
        self.assertEqual(repo.read(INDEX), original)
        self.assertEqual(result(repo, CLEAR, {}), ("refused", "there is no notice"))

    def test_store_edit_after_the_notice_expired_expects_no_notice(self):
        repo = self.repo()
        repo.run((SET, {"text": TEXT, "until": day(0)}))
        record = repo.run((STORY, {"text": NEW_STORY}))["records"][0]
        self.assertEqual(record["after"]["notice"], {"text": TEXT, "until": day(0)})
        self.assertEqual(preview.target_for(record)["notice"], TEXT)  # still its last day
        self.assertIsNone(preview.target_for(record, shop_today() + timedelta(days=1))["notice"])  # sitegen omits it

    def test_ampersand_and_quote_render_escaped(self):
        slot = sitegen.store_slots({**STORE, "notice": {"text": 'Salt & "pepper" day', "until": day(0)}})
        self.assertEqual(slot["store.noticeHtml"],
                         f'<p class="home-notice" data-until="{day(0)}" role="status">Salt &amp; "pepper" day</p>')

    def test_pacific_boundary_late_evening_is_still_today(self):
        apply, content = load_registry()[SET].apply, load_content()
        at = lambda utc: apply(content, {"text": TEXT, "until": "2026-11-26"}, OpContext(utc, REPO_ROOT, {}))  # noqa: E731
        self.assertNotIsInstance(at(datetime(2026, 11, 27, 7, 30, tzinfo=timezone.utc)), Refused)  # 23:30 PST, 26th
        self.assertEqual(content.store["notice"], {"text": TEXT, "until": "2026-11-26"})
        self.assertEqual(at(datetime(2026, 11, 27, 8, 30, tzinfo=timezone.utc)),  # 00:30 PST on the 27th
                         Refused("the last day 2026-11-26 is already past"))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class NoticeClockTests(unittest.TestCase):
    def test_continuously_open_page_expires_at_pacific_midnight(self):
        import subprocess
        result = subprocess.run(["node", str(Path(__file__).with_name("notice_expiry.cjs"))],
                                input=sitegen.NOTICE_JS, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())


class ValidatorTests(unittest.TestCase):
    def problems(self, notice):
        problems = []
        validate_store(problems, {**STORE, "notice": notice})
        return problems

    def test_notice_shape(self):
        self.assertEqual(self.problems({"text": TEXT, "until": "2026-11-26"}), [])
        for bad in ({"text": TEXT, "until": "2026-11-26", "extra": 1}, {"text": TEXT}, "Closed", None,
                    {"text": TEXT, "until": "Nov 26"}, {"text": TEXT, "until": "2026-02-30"},
                    {"text": TEXT, "until": 20261126}, {"text": "<b>Closed</b>", "until": "2026-11-26"},
                    {"text": "a" * 161, "until": "2026-11-26"}, {"text": "!!", "until": "2026-11-26"}):
            with self.subTest(bad=bad):
                problems = self.problems(bad)
                self.assertTrue(problems)
                self.assertTrue(all(p.startswith("store.notice") for p in problems), problems)


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class NoticeCaptureTests(StoreTestCase):
    def setUp(self):  # as test_store_story.StoryCaptureTests: the full site in a throwaway repo
        self.store_repo = repo = self.repo()
        wt = repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "full site")
        self.old_index = repo.read(INDEX)
        self.out = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="hass-av1322-01-"))) / "shot.png"
        self.target = preview.target_for(repo.run((SET, {"text": TEXT, "until": day(0)}))["records"][0])

    def capture(self, files=None, viewports=("phone",)):
        return preview.Previewer(self.store_repo.wt, viewports=viewports).capture(files or {}, self.target, self.out)

    def test_notice_is_shown_on_phone_and_desktop(self):
        self.assertEqual(self.target["notice"], TEXT)
        result = self.capture(viewports=preview.VIEWPORTS)
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        for prefix in ("", "desktop:"):
            self.assertIs(result["checks"][prefix + "noticeShown"], True)

    def test_old_page_and_a_page_past_its_day_fail(self):
        result = self.capture({INDEX: self.old_index})
        self.assertEqual((result["checks"]["noticeShown"], result["error"]), (False, "check failed: noticeShown"))
        stale = self.store_repo.read(INDEX).replace(f'data-until="{day(0)}"'.encode(), f'data-until="{day(-1)}"'.encode())
        self.assertIs(self.capture({INDEX: stale})["checks"]["noticeShown"], False)  # the page script hides it

    def test_store_edit_after_the_notice_expired_passes_without_it(self):
        record = self.store_repo.run((STORY, {"text": NEW_STORY}))["records"][0]
        tomorrow = shop_today() + timedelta(days=1)  # setUp's notice ends today
        self.target = preview.target_for(record, tomorrow)
        page = sitegen.render(load_content(self.store_repo.wt / "hass" / "content"), today=tomorrow)[INDEX]
        self.assertNotIn(b'class="home-notice"', page)
        result = self.capture({INDEX: page})
        self.assertEqual((result["ok"], result["error"], result["checks"]["storyShown"]), (True, None, True), result)
        self.assertNotIn("noticeShown", result["checks"])


if __name__ == "__main__":
    unittest.main()
