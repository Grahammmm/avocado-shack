"""AV2007-06: a bare yes to a repeat of a closed draft says what happened to the earlier one, and still needs the new code."""

import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, voice
from hass.tests.test_conversation import T0, ConversationTestCase

WARN = "That is the same change that %s earlier, so I want to be sure. Reply yes %s if you still want it."


class RepeatOutcomeTests(ConversationTestCase):
    def repeat_and_bare_yes(self):
        new, _reply = self.propose("hours")
        self.assertEqual(self.say("yes"), "no-target")
        [reply] = self.replies()
        return new, reply

    def assert_nothing_written(self, new):
        self.assertEqual((self.drafts()[-1]["state"], self.commits(), self.editor.applies), ("proposed", 0, 0))
        self.assertEqual(self.say(f"yes {new['code']}"), "approved")
        self.assertEqual((self.commits(), self.editor.applies), (1, 1))

    def test_expired_repeat_says_timed_out_and_still_requires_new_code(self):
        old, _r = self.propose("hours")
        self.now = T0 + timedelta(seconds=601)
        new, reply = self.repeat_and_bare_yes()
        self.assertEqual(reply, WARN % ("timed out", new["code"]))
        self.assertEqual(self.say(f"yes {old['code']}"), "no-target")
        self.replies()
        self.assert_nothing_written(new)

    def test_owner_rejected_repeat_says_you_cancelled(self):
        self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        new, reply = self.repeat_and_bare_yes()
        self.assertEqual(reply, WARN % ("you cancelled", new["code"]))
        self.assert_nothing_written(new)

    def test_failed_repeat_says_could_not_save(self):
        self.propose("hours")
        self.editor.crash = True
        with self.assertRaises(RuntimeError):
            self.say("yes")
        self.editor.crash = False
        self.conv = self.open()  # reopening turns the interrupted approval into a failed draft, without reapplying
        self.assertEqual(self.drafts()[0]["state"], "failed")
        self.replies()
        applies = self.editor.applies
        new, reply = self.repeat_and_bare_yes()
        self.assertEqual(reply, WARN % ("I couldn't save", new["code"]))
        self.assertEqual((self.drafts()[-1]["state"], self.commits(), self.editor.applies), ("proposed", 0, applies))

    def test_latest_matching_predecessor_wins(self):
        self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.now = T0 + timedelta(seconds=10)
        self.propose("hours")
        self.now = T0 + timedelta(seconds=700)
        self.assertEqual(self.say("desc"), "proposed")  # unrelated newer hash: ignored
        self.replies()
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assertEqual([d["state"] for d in self.drafts()], ["rejected", "expired", "rejected"])
        new, reply = self.repeat_and_bare_yes()
        self.assertEqual(reply, WARN % ("timed out", new["code"]))

    def test_replaced_repeat_does_not_blame_owner(self):
        self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.conv.db.execute("UPDATE drafts SET reason = 'revised', replaced_by = 'abcd' WHERE row_id = ?", (self.drafts()[0]["row_id"],))
        new, reply = self.repeat_and_bare_yes()
        self.assertEqual(reply, WARN % ("was replaced", new["code"]))

    def test_missing_hash_and_first_proposal_keep_legacy_admission(self):
        first, _r = self.propose("hours")
        self.assertFalse(self.conv._named(first))
        self.conv.db.execute("UPDATE drafts SET draft_hash = NULL")
        row = self.conv._row(first["row_id"])
        self.assertEqual((self.conv._repeat(row), self.conv._earlier_outcome(row)), (False, "was written up"))
        self.assertEqual(self.commits(), 0)

    def test_unexpected_predecessor_state_is_neutral_and_still_named(self):
        self.propose("hours")
        self.conv.db.execute("UPDATE drafts SET state = 'superseded-by-test'")
        new, reply = self.repeat_and_bare_yes()
        self.assertEqual(reply, WARN % ("I wrote up", new["code"]))

    def test_again_priority_and_voice(self):
        old, _r = self.propose("hours")
        self.now = T0 + timedelta(seconds=601)
        new, reply = self.repeat_and_bare_yes()
        self.assertEqual(voice.check(reply), [])
        self.conv.db.execute("UPDATE drafts SET reason = ? WHERE row_id = ?", (f"again:{old['code']}", self.drafts()[-1]["row_id"]))
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), [f"That change was written up again from an expired one, so I want to be sure. Reply yes {new['code']} if you still want it."])
        self.assertEqual((self.commits(), self.editor.applies), (0, 0))


if __name__ == "__main__":
    unittest.main()
