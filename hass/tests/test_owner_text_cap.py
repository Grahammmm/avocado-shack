"""AV1737-04 (H05/H22) tests: owner text over MAX_OWNER_TEXT gets one TOO_LONG reply and is never interpreted.

Nothing is drafted, no daily interpreter call is used and a waiting draft is untouched; text at exactly the cap and
memory commands are unaffected. Same H06 setup (temp Git repo, private state dir, injected clock, fake interpreter).
Run: python3 -m unittest hass.tests.test_owner_text_cap -v
"""

import unittest
from datetime import timedelta

from hass import content_model, conversation
from hass.tests.test_interpreter_cap import CapTestCase

LIMIT = conversation.MAX_OWNER_TEXT
AT_CAP, OVER = "a" * LIMIT, "a" * (LIMIT + 1)
TEXT_BAD = "Not saved: text must be 1–500 plain characters."


class OwnerTextCapTests(CapTestCase):
    CAP = None

    def setUp(self):
        super().setUp()
        hours = self.interp.mapping["hours"]
        for text in (AT_CAP, OVER, "é" * LIMIT, "é" * (LIMIT + 1), "\U0001F951" * 2000):
            self.interp.mapping[text] = hours  # a reachable text proposes the hours change

    def too_long(self, text):
        drafts = self.drafts()
        self.assertEqual(self.say(text), "too-long")
        self.assertEqual(self.replies(), [conversation.TOO_LONG])
        self.assertEqual(self.drafts(), drafts)

    def test_reply_names_the_limit(self):
        self.assertIn(f"over {LIMIT} characters", conversation.TOO_LONG)

    def test_text_at_the_cap_is_interpreted(self):
        self.assertEqual(self.say(AT_CAP), "proposed")
        self.assertEqual((self.interp.calls, len(self.drafts())), (1, 1))

    def test_one_over_the_cap_is_never_interpreted_or_drafted(self):
        self.too_long(OVER)
        self.too_long(OVER + " hours")
        self.assertEqual((self.interp.calls, self.drafts()), (0, []))

    def test_duplicate_over_long_delivery_replies_once(self):
        self.assertEqual(self.say(OVER, pid="long1"), "too-long")
        self.assertEqual(self.say(OVER, pid="long1"), "duplicate")
        self.assertEqual(self.replies(), [conversation.TOO_LONG])
        self.assertEqual(self.interp.calls, 0)

    def test_code_points_not_bytes(self):
        self.assertEqual(self.say("é" * LIMIT), "proposed")  # 8000 bytes in UTF-8, still at the cap
        self.replies()
        self.too_long("é" * (LIMIT + 1))
        self.assertEqual(self.say("\U0001F951" * 2000), "proposed")  # 2000 emoji, each one code point
        self.assertEqual(self.interp.calls, 2)

    def test_cap_covers_the_longest_field_limit_twice(self):
        longest = max(v for f in content_model.TEXT_LIMITS.values() for v in f.values())
        self.assertGreaterEqual(LIMIT, 2 * longest)

    def test_waiting_draft_stays_proposed_with_its_expiry(self):
        draft, _ = self.propose("hours")
        self.now += timedelta(minutes=1)
        self.too_long(OVER)
        [after] = self.drafts()
        self.assertEqual((after["state"], after["expires_at"]), ("proposed", draft["expires_at"]))
        self.assertEqual(self.interp.calls, 1)
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")  # still approvable

    def test_long_remember_goes_to_memory_not_the_cap(self):
        self.assertEqual(self.say("remember hours: " + "x" * LIMIT), "memory-invalid")
        self.assertEqual(self.replies(), [TEXT_BAD])
        self.assertEqual(self.interp.calls, 0)


class OwnerTextCapWithDailyCapTests(CapTestCase):
    CAP = 1

    def setUp(self):
        super().setUp()
        self.interp.mapping[OVER] = self.interp.mapping["hours"]

    def usage(self):
        return [tuple(r) for r in self.conv.db.execute("SELECT day, calls FROM usage")] if "usage" in self.tables() else []

    def test_over_long_text_does_not_use_the_days_call(self):
        self.assertEqual(self.say(OVER), "too-long")
        self.assertEqual(self.replies(), [conversation.TOO_LONG])
        self.assertEqual((self.usage(), self.interp.calls), ([], 0))
        self.propose("hours")  # the one call of the day is still free
        self.assertEqual(self.usage()[0][1], 1)
        self.assertEqual(self.say(OVER), "too-long")  # over the cap: still the length reply, not the daily one
        self.assertEqual(self.replies(), [conversation.TOO_LONG])
        self.assertEqual((self.usage()[0][1], self.interp.calls), (1, 1))


if __name__ == "__main__":
    unittest.main()
