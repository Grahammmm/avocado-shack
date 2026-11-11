"""HASS-SEC-2 (finding L5 of reports/hass/SEC-1.md): a late-delivered yes.

A yes is judged at the time the owner sent it (AV0022-06), so a yes sent in time but handled late (the service was down) still
counts. A yes that reached Hass (was forwarded into the inbox) long after it was sent is different: the Mac may have held it for
hours. It is accepted only when it was forwarded within the approval time plus a few minutes of its send time; otherwise nothing
is saved and the owner is asked to send it again. End to end through the receiver and the inbox (the forwarding time is the
inbox's own enqueue time), real Conversation, fixture editor, injected clocks.
Run: python3 -B -m unittest hass.tests.test_sec2_late_yes -v
"""
import unittest
from datetime import datetime, timezone

from hass import receiver, voice
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_receiver import NOW, SECRET, ReceiverTestCase
from hass.tests.test_bridge import event

TTL = SETTINGS["approvalTtlSeconds"]  # 600 s


class LateForwardTests(ReceiverTestCase):
    def setUp(self):
        super().setUp()
        self.rx = receiver.Receiver(state=self.inbox, settings=self.conv, reply=self.reply, apply=True)
        self.code = self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)["draft_id"]
        self.assertIsNotNone(self.code)

    def yes(self, sent, forwarded, guid="FAKE-LATE-YES"):
        """A `yes <code>` the owner sent at `sent` (epoch s) that the Mac forwarded at `forwarded`."""
        self.now = datetime.fromtimestamp(forwarded, timezone.utc)
        ev = self.event_from("new-message", guid=guid, text=f"yes {self.code}", dateCreated=sent * 1000)
        return self.rx.receive(self.seal(ev, now=forwarded), secret=SECRET, now=forwarded)

    def state(self):
        return self.drafts()[0]["state"]

    def test_a_yes_forwarded_hours_after_it_was_sent_saves_nothing(self):
        out = self.yes(NOW + 30, NOW + 30 + 6 * 3600)
        self.assertEqual(out["disposition"], "no-target")
        self.assertNotEqual(self.state(), "applied")
        self.assertEqual((self.editor.applies, self.commits()), (0, 0))
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)
        texts = [r["text"] for r in self.conv.db.execute("SELECT text FROM outbox WHERE sent_at IS NULL ORDER BY id")]
        self.assertIn("reached me", texts[-1])
        self.assertEqual(voice.check(texts[-1]), [], texts[-1])

    def test_a_yes_forwarded_just_past_the_window_saves_nothing(self):
        out = self.yes(NOW + 30, NOW + 30 + TTL + 6 * 60)
        self.assertEqual((out["disposition"], self.editor.applies), ("no-target", 0))

    def test_a_yes_sent_in_time_and_forwarded_in_the_window_still_counts(self):
        out = self.yes(NOW + TTL - 10, NOW + TTL - 10 + TTL + 4 * 60)  # handled after the draft expired, forwarded in the window
        self.assertEqual(out["disposition"], "approved")
        self.assertEqual((self.state(), self.editor.applies), ("applied", 1))

    def test_a_prompt_yes_is_unchanged(self):
        out = self.yes(NOW + 30, NOW + 31)
        self.assertEqual((out["disposition"], self.editor.applies), ("approved", 1))


if __name__ == "__main__":
    unittest.main()
