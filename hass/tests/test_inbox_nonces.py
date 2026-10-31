"""H16/H21 tests: the bridge nonce table keeps one day and is pruned when a nonce is recorded; replay stays refused.

Uses the H16 InboxTestCase harness; `self.now` is the injected inbox clock. Fixtures only.
Run: python3 -m unittest hass.tests.test_inbox_nonces -v
"""

import unittest
from datetime import timedelta

from hass import bridge
from hass import inbox as inbox_mod
from hass.bridge import EnvelopeError, seal, unseal
from hass.tests.test_conversation import T0
from hass.tests.test_inbox import InboxTestCase

A, B, C = "aa" * 16, "bb" * 16, "cc" * 16
KEY = b"k" * 32


class NoncePruneTests(InboxTestCase):
    def nonce_rows(self, box=None):
        return (box or self.inbox).db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0]

    def add_at(self, nonce, at):
        self.now = at
        self.inbox.seen().add(nonce)

    def test_keep_window_covers_twice_the_bridge_skew(self):
        self.assertGreaterEqual(inbox_mod.NONCE_KEEP_S, 2 * bridge.MAX_SKEW)

    def test_nonce_inside_the_window_is_kept(self):
        self.add_at(A, T0)
        self.add_at(B, T0 + timedelta(hours=23))
        seen = self.inbox.seen()
        self.assertIn(A, seen)
        self.assertIn(B, seen)
        self.assertEqual(self.nonce_rows(), 2)

    def test_nonce_older_than_the_window_is_pruned_on_add(self):
        self.add_at(A, T0)
        self.add_at(B, T0 + timedelta(hours=25))
        seen = self.inbox.seen()
        self.assertNotIn(A, seen)
        self.assertIn(B, seen)
        self.assertEqual(self.nonce_rows(), 1)

    def test_boundary_exactly_keep_seconds_is_kept_one_microsecond_more_is_pruned(self):
        keep = timedelta(seconds=inbox_mod.NONCE_KEEP_S)
        self.add_at(A, T0)
        self.add_at(B, T0 + keep)
        self.assertIn(A, self.inbox.seen())  # strict <
        self.add_at(C, T0 + keep + timedelta(microseconds=1))
        self.assertNotIn(A, self.inbox.seen())
        self.assertEqual(self.nonce_rows(), 2)

    def test_clock_moved_back_never_prunes_a_future_dated_row_early(self):
        self.add_at(A, T0 + timedelta(hours=2))
        self.add_at(B, T0)
        self.assertIn(A, self.inbox.seen())
        self.add_at(C, T0 + timedelta(hours=25))  # cut is T0 + 1 h
        seen = self.inbox.seen()
        self.assertNotIn(B, seen)
        self.assertIn(A, seen)
        self.assertIn(C, seen)
        self.assertEqual(self.nonce_rows(), 2)

    def test_replay_after_pruning_is_refused_as_stale(self):
        msg = self.msg("e1", "hours", T0)
        envelope = seal(msg, KEY, nonce=A, now=T0.timestamp())
        self.assertEqual(unseal(envelope, KEY, now=T0.timestamp(), seen=self.inbox.seen()), msg)
        later = T0 + timedelta(hours=25)
        self.add_at(B, later)
        self.assertNotIn(A, self.inbox.seen())  # the first nonce is gone
        with self.assertRaises(EnvelopeError) as caught:
            unseal(envelope, KEY, now=later.timestamp(), seen=self.inbox.seen())
        self.assertEqual(caught.exception.code, "stale")
        self.assertNotIn(A, self.inbox.seen())  # never accepted, nothing recorded
        self.assertEqual(self.nonce_rows(), 1)

    def test_replay_inside_the_window_after_reopen_is_still_replay(self):
        msg = self.msg("e2", "hours", T0)
        envelope = seal(msg, KEY, nonce=A, now=T0.timestamp())
        unseal(envelope, KEY, now=T0.timestamp(), seen=self.inbox.seen())
        self.add_at(B, T0 + timedelta(seconds=200))  # a prune runs and keeps A
        self.inbox.close()
        reopened = self.open_inbox()
        with self.assertRaises(EnvelopeError) as caught:
            unseal(envelope, KEY, now=T0.timestamp() + 200, seen=reopened.seen())
        self.assertEqual(caught.exception.code, "replay")
        self.assertEqual(self.nonce_rows(reopened), 2)

    def test_lookup_alone_never_prunes(self):
        self.add_at(A, T0)
        self.now = T0 + timedelta(hours=48)
        seen = self.inbox.seen()
        for _ in range(3):
            self.assertIn(A, seen)
            self.assertNotIn(B, seen)
        self.assertEqual(self.nonce_rows(), 1)


if __name__ == "__main__":
    unittest.main()
