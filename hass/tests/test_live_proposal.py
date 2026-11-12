"""HASS-LIVEPOL-1: live proposals and outcomes using isolated editor/owner fixtures."""
from datetime import timedelta
from unittest import mock

from hass import conversation as conv, owner_answers as answers, voice
from hass.tests import fixture_ops
from hass.tests.test_conversation import ConversationTestCase, SETTINGS, T0, _ops
from hass.tests.test_editor import DESC
from hass.tests.test_live_policy import edit

SITE = "fixture.example.invalid"


class LiveProposalTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        fixture_ops.allow_live(self)
        self.conv.db.close()
        self.set_settings({**SETTINGS, "liveSite": SITE, "approvalNeedsCode": True})
        self.conv = self.open()
        self.addCleanup(lambda: self.conv.db.close())

    def test_live_proposal_line_and_full_before(self):
        before = "A long previous sentence " * 14
        draft = edit(before, "A shorter headline", "headline", "store")
        text = conv.proposal_text("a1b2", draft, "2026-11-02T17:10:00+00:00", live_site=SITE)
        self.assertIn(before, text)
        self.assertIn("Reply yes a1b2 to put it on the website (it should show within a few minutes), or no a1b2 to cancel.", voice.plain(text))
        self.assertNotIn("Reply yes to apply", text)
        row, reply = self.propose("hours")
        self.assertIn(f"Reply yes {row['code']} to put it on the website", reply)

    def test_protected_proposal_says_cannot_go_live(self):
        draft = edit("Organic fruit", "Not organic fruit")
        text = conv.proposal_text("a1b2", draft, "2026-11-02T17:10:00+00:00", live_site=SITE)
        self.assertIn("I can't put this on the website from chat, because it mentions where the food comes from or whether it is organic", text)
        self.assertIn("Nothing will be published. Send it again without that part, and I can put the rest on the website. I've kept it on the list of changes to make by hand", text)
        self.assertNotIn("Reply yes", text)
        # Even an explicitly named yes cannot bypass the content boundary.

        self.interp = conv.FixtureInterpreter({"Organic fruit": _ops((DESC, {
            "id": "photo-product-001", "description": "Organic fruit"}))})
        self.conv.interpreter = self.interp
        row, reply = self.propose("Organic fruit")
        self.assertIn("can't put this on the website", reply)
        self.assertEqual(self.say(f"yes {row['code']}"), "no-target")
        self.assertIn("can't put this on the website", self.replies()[0])
        self.assertEqual((self.editor.applies, self.commits()), (0, 0))
        self.assertEqual(self.conv.db.execute("SELECT count(*) FROM approvals").fetchone()[0], 0)

    def test_bare_yes_refused_named_yes_approves(self):
        row, _ = self.propose("hours")
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), ["To put a change on the website, reply yes and its code, like yes a1b2."])
        self.assertEqual(self.editor.applies, 0)
        self.assertEqual(self.say(f"yes {row['code']}"), "approved")
        self.assertEqual(self.replies(), [voice.plain(answers.applied_text(row["code"], row["summary"], live_site=SITE))])
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.say(f"yes {row['code']}"), "no-target")
        self.assertEqual(self.editor.applies, 1)

    def test_cancelled_expired_duplicate_stale(self):
        row, _ = self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assertEqual(self.say(f"yes {row['code']}"), "no-target")
        self.replies()
        row, _ = self.propose("hours")
        self.now = T0 + timedelta(seconds=601)
        self.assertEqual(self.say(f"yes {row['code']}"), "no-target")
        self.assertIn("timed out", self.replies()[0])
        row, _ = self.propose("hours")
        self.assertEqual(self.say("yes", pid="same"), "no-target")
        self.replies()
        self.assertEqual(self.say(f"yes {row['code']}", pid="same"), "duplicate")
        # Another fixture edit makes the proposal stale; the new proposal also needs its named yes.
        changed = self.repo.prepare({"ops": [{"op": DESC, "args": {
            "id": "photo-product-001", "description": "Soft and creamy."}}]})["draft"]
        self.repo.apply(changed)
        self.assertEqual(self.say(f"yes {row['code']}"), "approved")
        reply = self.replies()[0]
        self.assertIn("website changed while that was waiting", reply)
        new = self.drafts()[-1]
        self.assertNotEqual(new["code"], row["code"])
        self.assertIn(f"Reply yes {new['code']} to put it on the website", reply)
        self.assertEqual(self.drafts()[-2]["reason"], "stale")
        self.assertEqual(self.say("yes"), "no-target")

    def test_live_needs_code_setting(self):
        for extra in ({"liveSite": SITE}, {"liveSite": SITE, "approvalNeedsCode": False},
                      {"liveSite": "https://bad.invalid", "approvalNeedsCode": True},
                      {"liveSite": "nodot", "approvalNeedsCode": True}, {"approvalNeedsCode": 1}):
            with self.subTest(extra=extra):
                self.set_settings({**SETTINGS, **extra})
                with self.assertRaises(conv.ConfigError): conv.load_settings(self.repo.state)
        for extra in ({}, {"liveSite": SITE, "approvalNeedsCode": True}):
            self.set_settings({**SETTINGS, **extra})
            self.assertEqual(conv.load_settings(self.repo.state).get("liveSite"), extra.get("liveSite"))

    def test_live_saved_wording_only(self):
        row, _ = self.propose("hours")
        self.conv.previewer = object()
        with mock.patch.object(self.conv, "verify", return_value=("fixture-result.png", None)):
            self.assertEqual(self.say(f"yes {row['code']}"), "approved")
        replies = self.replies()
        self.assertEqual(replies, [f"Saved: {row['summary']}. I'll send a separate message about the website."])
        self.assertEqual(self.conv.screenshot(row["change_id"]), "fixture-result.png")
        self.assertIsNotNone(self.drafts()[0]["checked_at"])
        self.conv._verify_pending()
        self.assertEqual(self.replies(), [])
        self.assertIsNone(self.conv.screenshot("missing"))
        for checked, error in ((True, None), (False, "private diagnostic")):
            self.assertEqual(voice.plain(answers.applied_text(row["code"], row["summary"], checked, error, SITE)), replies[0])

    def test_recover_applied_and_verify_failure_never_claim_website_outcome(self):
        row, _ = self.propose("hours")
        self.assertEqual(self.conv.handle(conv.Inbound("approval", SETTINGS["ownerChat"],
            SETTINGS["ownerSenders"][0], f"yes {row['code']}", received_at=self.now.isoformat()), apply=False), "approval-held")
        self.replies()
        self.conv.db.execute("UPDATE drafts SET state = 'approved'")
        self.editor.apply(row["change_id"], row["draft_hash"])
        self.conv.previewer = object()
        with mock.patch.object(self.conv, "verify", return_value=(None, "private failure")):
            self.assertEqual(self.conv.recover(), ["applied"])
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Saved:"))
        for text in ("website is unchanged", "Now showing", answers.NOT_LIVE, "private failure"):
            self.assertNotIn(text, reply)
        self.assertIsNotNone(self.drafts()[0]["checked_at"])
        self.assertIsNone(self.conv.screenshot(row["change_id"]))
        self.assertEqual(self.conv.recover(), [])
        self.assertEqual(self.replies(), [])

    def test_live_off_is_byte_identical(self):
        draft = edit("old", "new", "headline", "store")
        self.assertEqual(conv.proposal_text("a1b2", draft, "2026-11-02T17:10:00+00:00"),
            "Here's the change I'd make:\nthe shop details, the headline: from \ue000old\ue001 to \ue000new\ue001\nI'll hold this for you until Monday, Nov 2 at 9:10 am.\nReply \ue000yes\ue001 to save it, or no to cancel. If something's wrong, tell me what to fix.")
        self.assertEqual(answers.applied_text("a1b2", "headline"), "Saved: \ue000headline\ue001\n" + answers.NOT_LIVE)
        self.assertEqual(answers.recovered_text("a1b2"),
            "That change was interrupted and not saved. The website is as it was before. Please send it again.")


class LiveShowAndLongCodes(ConversationTestCase):
    def setUp(self):
        super().setUp()
        fixture_ops.allow_live(self)
        self.conv.db.close()
        self.set_settings({**SETTINGS, "liveSite": SITE, "approvalNeedsCode": True})
        self.conv = self.open()
        self.addCleanup(lambda: self.conv.db.close())

    def test_show_repeats_the_coded_live_instructions(self):
        row, _ = self.propose("hours")
        self.say("show")
        [reply] = self.replies()
        self.assertIn(f"Reply yes {row['code']} to put it on the website", voice.plain(reply))
        self.assertIn(f"no {row['code']} to cancel", voice.plain(reply))
        self.assertNotIn("Reply yes to save it", voice.plain(reply))

    def test_eight_ten_and_twelve_character_codes_survive_status_okay_and_choices(self):
        for code in ("abc12345", "abc1234567", "abc123456789"):
            with self.subTest(code=code):
                self.conv.db.execute("UPDATE drafts SET code = ? WHERE state = 'proposed'", (code,)) if self.drafts() else None
                if not self.drafts():
                    self.propose("hours")
                    self.conv.db.execute("UPDATE drafts SET code = ? WHERE state = 'proposed'", (code,))
                else:
                    self.conv.db.execute("UPDATE drafts SET code = ?", (code,))
                self.say("status")
                [status] = self.replies()
                self.assertIn(f"reply yes {code}", voice.plain(status))
                self.say("okay")
                [near] = self.replies()
                self.assertIn(f"yes {code}", voice.plain(near))
                self.assertNotEqual(voice.plain(near), voice.SAFE_LINE)
