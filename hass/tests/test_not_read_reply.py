"""AV1737-03 (H08/H17) tests: an owner reaction or edited message gets one fixed NOT_READ_REPLY.

A reaction never approves or cancels, an edit is never read by the interpreter, no draft/approval/usage row is written
and nobody else gets a reply. Same H05 setup (temp Git repo, private state dir, injected clock, fixture interpreter).
Run: python3 -m unittest hass.tests.test_not_read_reply -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import GROUP, SETTINGS, STRANGER, ConversationTestCase
from hass.tests.test_interpreter_cap import CountingInterpreter
from hass.tests.test_status_pause import StoreMixin

NOT_READ = conversation.NOT_READ_REPLY


class NotReadTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "interpreterDailyCap": 5})
        self.interp = CountingInterpreter(self.interp.mapping)
        self.conv = self.open()
        self.draft, _reply = self.propose("desc")

    def usage(self):
        return [tuple(r) for r in self.conv.db.execute("SELECT day, calls FROM usage ORDER BY day")]

    def snapshot(self):
        return self.drafts(), self.approvals(), self.usage(), self.interp.calls, self.commits()

    def not_read(self, text, kind, pid=None):
        before = self.snapshot()
        self.assertEqual(self.say(text, kind=kind, pid=pid), "not-read")
        self.assertEqual(self.replies(), [NOT_READ])
        self.assertEqual(self.snapshot(), before)  # no draft, approval, usage count, interpreter call or commit

    def test_owner_edit_no_and_reaction_change_nothing(self):
        self.assertEqual((self.interp.calls, self.usage()[0][1]), (1, 1))
        self.not_read("no", "edited", pid="e1")
        self.not_read(f"Liked \u201cDraft {self.draft['code']} ready\u201d", "reaction", pid="r1")
        self.assertEqual((self.disposition("e1"), self.disposition("r1")), ("not-read", "not-read"))
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.interp.calls), ("proposed", 0, 1))

    def test_no_wording_bypasses_it(self):
        for kind in ("edited", "reaction"):
            for text in ("yes", f"yes {self.draft['code']}", "cancel", "undo", "status", "pause changes",
                         "remember hours: 9-5", "hours", ""):
                with self.subTest(kind=kind, text=text):
                    self.not_read(text, kind)
        self.assertEqual((self.conv._paused(), self.drafts()[0]["state"]), (None, "proposed"))
        self.assertNotIn("memory", self.tables())

    def test_duplicate_reaction_gets_one_reply(self):
        self.assertEqual(self.say("Liked", kind="reaction", pid="r1"), "not-read")
        self.assertEqual(self.say("Liked", kind="reaction", pid="r1"), "duplicate")
        self.assertEqual(self.replies(), [NOT_READ])
        self.assertEqual(self.disposition("r1"), "not-read")

    def test_strangers_echoes_and_unknown_kinds_get_no_reply(self):
        cases = [(dict(sender=STRANGER), "edited-ignored"), (dict(chat=GROUP), "edited-ignored"),
                 (dict(from_me=True), "echo")]
        for kind in ("edited", "reaction"):
            for kwargs, disposition in cases:
                with self.subTest(kind=kind, **kwargs):
                    self.assertEqual(self.say("yes", kind=kind, **kwargs), disposition)
                    self.assertEqual(self.replies(), [])
        self.assertEqual(self.say("yes", kind="deleted"), "edited-ignored")  # any other kind: silent as before
        self.assertEqual(self.replies(), [])
        received = self.conv.db.execute("SELECT received_at FROM messages WHERE disposition != 'proposed'").fetchall()
        self.assertEqual({r[0] for r in received}, {None})
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.interp.calls), ("proposed", 0, 1))

    def test_new_yes_after_a_reaction_still_approves(self):
        self.not_read("Liked", "reaction")
        self.assertEqual(self.say("yes"), "approved")
        [reply] = self.replies()
        self.assertTrue(reply.startswith(f"Applied {self.draft['code']}"), reply)
        self.assertEqual((self.drafts()[0]["state"], self.commits()), ("applied", 1))

    def test_reaction_does_not_sweep_an_expired_draft(self):
        self.now += timedelta(seconds=SETTINGS["approvalTtlSeconds"] + 1)
        self.not_read("Liked", "reaction")
        self.assertEqual(self.drafts()[0]["state"], "proposed")  # only a new owner message expires it
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_paused_reaction_gets_not_read_not_the_paused_text(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        paused = self.conv._paused()
        self.not_read("Liked", "reaction")
        self.not_read("yes", "edited")
        self.assertEqual(self.conv._paused(), paused)


if __name__ == "__main__":
    unittest.main()
