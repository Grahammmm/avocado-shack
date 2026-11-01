"""H16 vs NB-AV-01 (operator decision 2026-10-31 17:28): an expired `revises` code starts fresh; an unknown one asks.

A draft that existed and lapsed has nothing left to revise, so the answer is handled as a new request (H16).
A code that never existed keeps NB-AV-01's "not waiting" question and opens no draft.
Run: python3 -B -m unittest hass.tests.test_revises_expired_vs_unknown -v
"""

import unittest
from datetime import timedelta

from hass.tests import test_needs_details_expiry as h16
from hass.tests.test_conversation import T0


class RevisesExpiredVsUnknownTests(h16.NeedsDetailsExpiryTests):
    def test_expired_code_starts_a_fresh_draft(self):
        q = self.ask()
        self.now = T0 + h16.TTL + timedelta(seconds=1)
        self.assertEqual(self.answer("done", q["code"]), "proposed")
        self.replies()
        old, new = self.drafts()
        self.assertEqual((old["state"], new["state"]), ("expired", "proposed"))
        self.assertNotEqual(new["code"], q["code"])

    def test_unknown_code_still_asks(self):
        q = self.ask()
        self.assertEqual(self.answer("done", "ZZZZ"), "question")
        self.assertEqual(self.replies(), ["I could not find draft ZZZZ waiting; reply with the change again."])
        self.assertEqual([(d["code"], d["state"]) for d in self.drafts()], [(q["code"], "needs-details")])


# Reuse the H16 helpers only; the inherited H16 tests already run in their own module (None is not collected).
for _name in [n for n in vars(h16.NeedsDetailsExpiryTests) if n.startswith("test_")]:
    setattr(RevisesExpiredVsUnknownTests, _name, None)

if __name__ == "__main__":
    unittest.main()
