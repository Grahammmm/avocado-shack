"""HASS-LIVEPOL-1: live proposals and outcomes using isolated editor/owner fixtures."""
from datetime import timedelta
from unittest import mock

from hass import conversation as conv, owner_answers as answers
from hass.tests.test_conversation import ConversationTestCase, SETTINGS, T0, _ops
from hass.tests.test_editor import DESC
from hass.tests.test_live_policy import edit

SITE = "fixture.example.invalid"


class LiveProposalTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.conv.db.close()
        self.set_settings({**SETTINGS, "liveSite": SITE, "approvalNeedsCode": True})
        self.conv = self.open()
        self.addCleanup(lambda: self.conv.db.close())

    def test_live_proposal_line_and_full_before(self):
        before = "A long previous sentence " * 14
        draft = edit(before, "A shorter headline", "headline", "store")
        text = conv.proposal_text("a1b2", draft, "2026-11-02T17:10:00+00:00", live_site=SITE)
        self.assertIn(before, text)
        self.assertIn(f"Reply yes a1b2 and this goes live on {SITE} within a few minutes.", text)
        self.assertNotIn("Reply yes to apply", text)
        row, reply = self.propose("hours")
        self.assertIn(f"Reply yes {row['code']} and this goes live on {SITE}", reply)

    def test_protected_proposal_says_cannot_go_live(self):
        draft = edit("Organic fruit", "Not organic fruit")
        text = conv.proposal_text("a1b2", draft, "2026-11-02T17:10:00+00:00", live_site=SITE)
        self.assertIn("This change can't go live from chat (protected sentences: origin/organic)", text)
        self.assertIn("Nothing will be published; G can do it by hand.", text)
        self.assertNotIn("Reply yes", text)
        # Even an explicitly named yes cannot bypass the content boundary.

        self.interp = conv.FixtureInterpreter({"Organic fruit": _ops((DESC, {
            "id": "photo-product-001", "description": "Organic fruit"}))})
        self.conv.interpreter = self.interp
        row, reply = self.propose("Organic fruit")
        self.assertIn("can't go live", reply)
        self.assertEqual(self.say(f"yes {row['code']}"), "no-target")
        self.assertIn("can't go live", self.replies()[0])
        self.assertEqual((self.editor.applies, self.commits()), (0, 0))
        self.assertEqual(self.conv.db.execute("SELECT count(*) FROM approvals").fetchone()[0], 0)

    def test_bare_yes_refused_named_yes_approves(self):
        row, _ = self.propose("hours")
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), ["To put a change live, reply yes <code>, for example yes a1b2."])
        self.assertEqual(self.editor.applies, 0)
        self.assertEqual(self.say(f"yes {row['code']}"), "approved")
        self.assertEqual(self.replies(), [answers.applied_text(row["code"], row["summary"], live_site=SITE)])
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
        self.assertIn("expired", self.replies()[0])
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
        self.assertIn("site changed since", reply)
        new = self.drafts()[-1]
        self.assertNotEqual(new["code"], row["code"])
        self.assertIn(f"Reply yes {new['code']} and this goes live on {SITE}", reply)
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
            self.assertEqual(conv.load_settings(self.repo.state)["liveSite"], extra.get("liveSite"))

    def test_live_saved_wording_only(self):
        row, _ = self.propose("hours")
        self.conv.previewer = object()
        with mock.patch.object(self.conv, "verify", return_value=("fixture-result.png", None)):
            self.assertEqual(self.say(f"yes {row['code']}"), "approved")
        replies = self.replies()
        self.assertEqual(replies, [f"Saved {row['code']}: {row['summary']}. I'll send a separate message about the website."])
        self.assertEqual(self.conv.screenshot(row["change_id"]), "fixture-result.png")
        self.assertIsNotNone(self.drafts()[0]["checked_at"])
        self.conv._verify_pending()
        self.assertEqual(self.replies(), [])
        self.assertIsNone(self.conv.screenshot("missing"))
        for checked, error in ((True, None), (False, "private diagnostic")):
            self.assertEqual(answers.applied_text(row["code"], row["summary"], checked, error, SITE), replies[0])

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
        self.assertTrue(reply.startswith("Saved "))
        for text in ("website is unchanged", "Now showing", answers.NOT_LIVE, "private failure"):
            self.assertNotIn(text, reply)
        self.assertIsNotNone(self.drafts()[0]["checked_at"])
        self.assertIsNone(self.conv.screenshot(row["change_id"]))
        self.assertEqual(self.conv.recover(), [])
        self.assertEqual(self.replies(), [])

    def test_live_off_is_byte_identical(self):
        draft = edit("old", "new", "headline", "store")
        self.assertEqual(conv.proposal_text("a1b2", draft, "2026-11-02T17:10:00+00:00"),
            "Draft a1b2:\nstore fixture: headline old → new\nExpires 2026-11-02 09:10 PST.\n"
            "Reply yes to apply, no to cancel, or send a correction.")
        self.assertEqual(answers.applied_text("a1b2", "headline"), "Applied a1b2: headline\n" + answers.NOT_LIVE)
        self.assertEqual(answers.recovered_text("a1b2"),
            "a1b2 was interrupted and not saved. The website is as it was before; send the change again to make a new draft.")
