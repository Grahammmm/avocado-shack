"""AV2022-08 (H08): the owner matches however the address is written; a config entry that is neither is a ConfigError.

Email compares case-insensitively; a phone compares as `+` and its digits (spaces, dashes, dots, brackets dropped).
Only 555 numbers and example.invalid addresses. Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import unittest

from hass import conversation
from hass.tests.test_conversation import SETTINGS, ConversationTestCase

PHONE = "+1 (555) 123-4567"
ENTRY = "ownerSenders entry {} is not an email address or a +country phone number"


class OwnerSenderMatchTests(ConversationTestCase):
    def use(self, *senders):
        self.set_settings({**SETTINGS, "ownerSenders": list(senders)})
        self.conv = self.open()

    def assert_owner(self, sender):
        self.assertNotEqual(self.say("help", sender=sender), "ignored")
        self.assertEqual(len(self.replies()), 1)

    def assert_ignored(self, sender):
        self.assertEqual(self.say("help", sender=sender), "ignored")
        self.assertEqual(self.replies(), [])

    def config_error(self, *senders):
        self.set_settings({**SETTINGS, "ownerSenders": list(senders)})
        with self.assertRaises(conversation.ConfigError) as caught:
            conversation.load_settings(self.repo.state)
        return str(caught.exception)

    def test_phone_punctuation_is_ignored(self):
        self.use(PHONE)
        for sender in ("+15551234567", "+1.555.123.4567", " +1 555-123-4567 "):
            with self.subTest(sender=sender):
                self.assert_owner(sender)

    def test_email_case_is_ignored_both_ways(self):
        for config, sender in (("Owner@Example.invalid", "owner@example.invalid"),
                               ("owner@example.invalid", "OWNER@Example.Invalid")):
            with self.subTest(config=config, sender=sender):
                self.use(config)
                self.assert_owner(sender)

    def test_near_miss_senders_are_ignored(self):
        self.use(PHONE, "owner@example.invalid")
        for sender in ("+15551234568", "+5551234567", "15551234567", "owner+x@example.invalid",
                       "owner@example.invalid.", "stranger@example.invalid", None, "", "   "):
            with self.subTest(sender=sender):
                self.assert_ignored(sender)

    def test_other_chat_still_ignored_for_matching_sender(self):
        self.use(PHONE)
        self.assertEqual(self.say("help", chat="chat-fixture-group", sender="+15551234567"), "ignored")
        self.assertEqual(self.replies(), [])

    def test_bad_entries_name_only_the_entry_number(self):
        for bad in ("555-123-4567", "owner", "a@b", "", "   ", 42, None, "owner @example.invalid", "a@b@example.invalid",
                    "+1 555 123 4567 x9", "+"):
            with self.subTest(bad=bad):  # the whole message is fixed text, so no entry value can be echoed
                self.assertEqual(self.config_error("owner@example.invalid", bad), ENTRY.format(2))

    def test_every_bad_entry_is_numbered(self):
        message = self.config_error("owner", "owner@example.invalid", "555-123-4567")
        self.assertEqual(message, f"{ENTRY.format(1)}; {ENTRY.format(3)}")

    def test_phone_digit_count_bounds(self):
        for digits in ("1555123", "1555123456789012"):  # 7 and 16 digits
            with self.subTest(digits=digits):
                self.assertEqual(self.config_error("+" + digits), ENTRY.format(1))
        for digits in ("15551234", "155512345678901"):  # 8 and 15 digits
            with self.subTest(digits=digits):
                self.use("+" + digits)
                self.assert_owner("+" + digits)

    def test_settings_keep_entries_as_written_and_audit_keeps_received_sender(self):
        self.use(PHONE)
        self.assertEqual(self.conv.settings["ownerSenders"], (PHONE,))
        self.assertEqual(self.conv.settings["ownerKeys"], frozenset({"+15551234567"}))
        self.assertEqual(self.say("hours", sender="+1.555.123.4567"), "proposed")
        self.replies()
        self.assertEqual(self.say("yes", sender="+15551234567"), "approved")
        [sender] = self.conv.db.execute("SELECT sender FROM approvals").fetchone()
        self.assertEqual(sender, "+15551234567")

    def test_sender_key_rejects_non_strings_and_bare_values(self):
        for value in (None, 42, ["owner@example.invalid"], "", "owner", "555-123-4567", "+1 555 123 4567\n5"):
            with self.subTest(value=value):
                self.assertIsNone(conversation.sender_key(value))


if __name__ == "__main__":
    unittest.main()
