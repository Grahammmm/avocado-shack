"""AV1737-01 (H08) tests: a tapback (associatedMessageType set) is kind "reaction"; an updated-message without a
dateEdited (delivery/read) is Drop("receipt"). Synthetic fixtures, no network.
Run: python3 -m unittest discover -s hass/tests -t . -v"""

import json, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass.bridge import Drop, normalize, seal, unseal
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_bridge import KEY, NONCE, NOW, OWNER_CHAT, event
from hass.tests.test_conversation import OWNER, SETTINGS, ConversationTestCase


def variant(name, **data):
    """The named fixture with data fields replaced; a value of ... removes the field."""
    ev = event(name)
    for key, value in data.items():
        ev["data"].pop(key, None) if value is ... else ev["data"].__setitem__(key, value)
    return ev


class ReactionTests(unittest.TestCase):
    def test_string_tapback_is_a_reaction_with_text_unchanged(self):
        msg = normalize(event("reaction"))
        self.assertEqual((msg.kind, msg.text, msg.sender, msg.chat, msg.from_me),
                         ("reaction", "Liked \u201cDraft A1 ready\u201d", OWNER, OWNER_CHAT, False))
        self.assertEqual(msg.provider_id, "FAKE-0000-0000-0000-000000000007")

    def test_integer_tapback_codes_are_reactions(self):
        for code in (2000, 2001, 3001, 0):
            with self.subTest(code=code):
                self.assertEqual(normalize(variant("new-message", associatedMessageType=code)).kind, "reaction")

    def test_misshapen_tapback_types_are_malformed(self):
        for value in (True, False, {}, [], ["like"], 1.5, {"type": "like"}):
            with self.subTest(value=value):
                self.assertEqual(normalize(variant("reaction", associatedMessageType=value)), Drop("malformed"))

    def test_empty_or_absent_tapback_is_a_plain_new_message(self):
        for value in (None, "", ...):
            with self.subTest(value=value):
                msg = normalize(variant("new-message", associatedMessageType=value))
                self.assertEqual((msg.kind, msg.text), ("new", "desc"))
        self.assertEqual(normalize(variant("new-message", associatedMessageGuid="p:0/FAKE")).kind, "new")

    def test_group_chat_reaction_is_still_dropped_by_the_chat_check(self):
        group = variant("group-chat", associatedMessageType="love")
        self.assertEqual(normalize(group), Drop("group-or-unknown-chat"))
        group["data"]["dateEdited"] = None
        group["type"] = "updated-message"
        self.assertEqual(normalize(group), Drop("group-or-unknown-chat"))


class ReceiptTests(unittest.TestCase):
    def test_receipt_fixture_is_dropped(self):
        self.assertEqual(normalize(event("receipt")), Drop("receipt"))

    def test_update_without_a_real_dateEdited_is_a_receipt(self):
        for value in (..., None, 0, -1, "1793638870000", True, 1.5e12, []):
            with self.subTest(value=value):
                self.assertEqual(normalize(variant("updated-message", dateEdited=value)), Drop("receipt"))

    def test_real_edit_stays_edited(self):
        msg = normalize(event("updated-message"))
        self.assertEqual((msg.kind, msg.text), ("edited", "yes"))

    def test_delivery_update_of_a_tapback_is_a_receipt(self):
        ev = event("reaction")
        ev["type"] = "updated-message"
        for value in (..., None, 0):
            with self.subTest(value=value):
                if value is not ...: ev["data"]["dateEdited"] = value
                self.assertEqual(normalize(ev), Drop("receipt"))
        ev["data"]["associatedMessageType"] = {}  # receipt is decided before the tapback type
        self.assertEqual(normalize(ev), Drop("receipt"))

    def test_dateEdited_on_a_new_message_changes_nothing(self):
        self.assertEqual(normalize(variant("new-message", dateEdited=None)).kind, "new")


class ReactionEnvelopeTests(unittest.TestCase):
    def test_reaction_seals_and_unseals(self):
        msg, seen = normalize(event("reaction")), set()
        envelope = json.loads(json.dumps(seal(msg, KEY, nonce=NONCE, now=NOW)))
        self.assertEqual(envelope["body"]["kind"], "reaction")
        self.assertEqual(unseal(envelope, KEY, now=NOW, seen=seen), msg)
        self.assertEqual(seen, {NONCE})


class ReactionConversationTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "ownerChat": OWNER_CHAT})
        self.conv.db.close()
        self.conv = self.open()

    def through_fixture_adapter(self, *events):
        folder = tempfile.TemporaryDirectory(prefix="hass-reaction-")
        self.addCleanup(folder.cleanup)
        jsonl, inbound = Path(folder.name) / "events.jsonl", [normalize(e) for e in events]
        jsonl.write_text("".join(json.dumps({"id": m.provider_id, "chat": m.chat, "sender": m.sender, "text": m.text,
                                             "fromMe": m.from_me, "kind": m.kind, "at": m.received_at}) + "\n"
                                 for m in inbound), "utf-8")
        read = FixtureAdapter(jsonl).inbound()
        self.assertEqual(read, inbound)
        return read

    def test_reaction_is_recorded_edited_ignored_without_reply_or_interpreter(self):
        # text "desc" would propose a draft as a plain message: a tapback with that wording must not
        tapback = variant("reaction", text="desc")
        with mock.patch.object(self.interp, "interpret", wraps=self.interp.interpret) as interpret:
            dispositions = [self.conv.handle(m) for m in self.through_fixture_adapter(tapback, tapback)]
            self.assertEqual(dispositions, ["edited-ignored", "duplicate"])
            self.assertEqual((interpret.call_count, self.replies(), self.drafts(), self.commits()), (0, [], [], 0))
            self.assertEqual(self.conv.handle(normalize(event("new-message"))), "proposed")
            self.assertEqual(interpret.call_count, 1)


if __name__ == "__main__":
    unittest.main()
