"""AVB-02 (H08) tests: load_settings refuses an ownerChat that is a group or another person's one-to-one chat.

Each case writes a config.json into a temp state dir. Run: python3 -m unittest hass.tests.test_owner_chat_config -v
"""

import json
import tempfile
import unittest

from hass import conversation

GROUP_PROBLEM = "ownerChat is a group chat; it must be the owner's one-to-one chat"
ADDRESS_PROBLEM = "ownerChat is a one-to-one chat with an address that is not in ownerSenders"
TTL_PROBLEM = "approvalTtlSeconds must be an integer >= 60"
OWNER_PHONE = "+15552222222"


def _load(chat, senders=(OWNER_PHONE,), ttl=600):
    settings = {"ownerSenders": list(senders), "ownerChat": chat, "approvalTtlSeconds": ttl}
    with tempfile.TemporaryDirectory() as sdir:
        with open(f"{sdir}/config.json", "w", encoding="utf-8") as fh: json.dump({"settings": settings}, fh)
        return conversation.load_settings(sdir)


class OwnerChatConfigTests(unittest.TestCase):
    def _refused(self, *args, **kwargs):
        with self.assertRaises(conversation.ConfigError) as ctx: _load(*args, **kwargs)
        return str(ctx.exception)

    def test_group_chat_is_refused_and_id_not_echoed(self):
        message = self._refused("iMessage;+;chat123")
        self.assertEqual(message, GROUP_PROBLEM)
        self.assertNotIn("chat123", message)

    def test_one_to_one_with_non_owner_address_is_refused_and_numbers_not_echoed(self):
        message = self._refused("iMessage;-;+15550001111")
        self.assertEqual(message, ADDRESS_PROBLEM)
        self.assertNotIn("5550001111", message)
        self.assertNotIn("5552222222", message)

    def test_one_to_one_with_unparseable_address_is_refused(self):
        self.assertEqual(self._refused("iMessage;-;not an address"), ADDRESS_PROBLEM)

    def test_owner_phone_in_another_format_loads(self):
        settings = _load("iMessage;-;+1 (555) 222-2222")
        self.assertEqual(settings["ownerChat"], "iMessage;-;+1 (555) 222-2222")
        self.assertEqual(settings["ownerKeys"], frozenset({OWNER_PHONE}))

    def test_email_is_casefolded_and_service_prefix_is_not_restricted(self):
        settings = _load("SMS;-;owner@example.com", senders=["Owner@Example.com"])
        self.assertEqual(settings["ownerChat"], "SMS;-;owner@example.com")

    def test_plain_chat_ids_load_with_unchanged_settings(self):
        for chat in ("chat", "chat@example.invalid"):
            with self.subTest(chat=chat):
                self.assertEqual(_load(chat), {
                    "ownerSenders": (OWNER_PHONE,), "ownerKeys": frozenset({OWNER_PHONE}), "ownerChat": chat,
                    "approvalTtlSeconds": 600, "mediaRoot": None, "guestCountsDb": None, "interpreterDailyCap": None,
                    "skillsMode": "ops-only", "houseRender": False})  # SKILLS-FW-3: the two new settings, defaults

    def test_group_chat_and_bad_ttl_report_both_problems_in_one_error(self):
        self.assertEqual(self._refused("iMessage;+;chat123", ttl=5), f"{GROUP_PROBLEM}; {TTL_PROBLEM}")

    def test_non_owner_one_to_one_and_bad_ttl_report_both_problems(self):
        self.assertEqual(self._refused("iMessage;-;+15550001111", ttl=5), f"{ADDRESS_PROBLEM}; {TTL_PROBLEM}")

    def test_empty_chat_keeps_the_existing_message_only(self):
        self.assertEqual(self._refused("  "), "ownerChat must be a chat id")


if __name__ == "__main__":
    unittest.main()
