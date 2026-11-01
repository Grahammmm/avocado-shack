"""AV1737-02 (H08/H16) tests: each real edit gets its own id "<guid>:edited:<dateEdited>" and is timed by the edit,
so the inbox keeps it instead of answering duplicate. Synthetic fixtures, temp state dir, no network.
Run: python3 -m unittest discover -s hass/tests -t . -v"""

import json, tempfile, unittest  # noqa: E401

from hass.bridge import Drop, normalize, seal, unseal
from hass.inbox import Inbox
from hass.tests.test_bridge import KEY, NONCE, NOW, OWNER_CHAT, event
from hass.tests.test_conversation import SETTINGS, ConversationTestCase

GUID, EDIT_MS = "FAKE-0000-0000-0000-000000000002", 1793638870000
EDIT_ID = f"{GUID}:edited:{EDIT_MS}"


def edit_of(name, edited):
    """The named fixture delivered as an updated-message with this dateEdited."""
    ev = event(name)
    ev["type"], ev["data"]["dateEdited"] = "updated-message", edited
    return ev


class EditIdTests(unittest.TestCase):
    def test_edit_fixture_gets_composite_id_and_edit_time(self):
        msg = normalize(event("updated-message"))
        self.assertEqual((msg.provider_id, msg.kind, msg.text), (EDIT_ID, "edited", "yes"))
        self.assertEqual(msg.received_at, "2026-11-02T17:01:10+00:00")  # dateEdited, not dateCreated (17:01:00)

    def test_two_edits_of_one_guid_get_two_ids(self):
        first, second = (normalize(edit_of("updated-message", ms)) for ms in (EDIT_MS, EDIT_MS + 5000))
        self.assertEqual((first.provider_id, second.provider_id), (EDIT_ID, f"{GUID}:edited:{EDIT_MS + 5000}"))
        self.assertEqual(second.received_at, "2026-11-02T17:01:15+00:00")

    def test_overflowing_dateEdited_is_malformed(self):
        for value in (10 ** 30, 2 ** 63):
            with self.subTest(value=value):
                self.assertEqual(normalize(edit_of("updated-message", value)), Drop("malformed"))

    def test_new_message_and_reaction_keep_guid_and_dateCreated(self):
        new, reaction = normalize(event("new-message")), normalize(event("reaction"))
        self.assertEqual((new.provider_id, new.received_at),
                         ("FAKE-0000-0000-0000-000000000001", "2026-11-02T17:00:00+00:00"))
        self.assertEqual((reaction.kind, reaction.provider_id), ("reaction", "FAKE-0000-0000-0000-000000000007"))
        self.assertNotIn(":edited:", reaction.provider_id)
        edited_tapback = normalize(edit_of("reaction", EDIT_MS))  # a real edit of a tapback stays a reaction
        self.assertEqual((edited_tapback.kind, edited_tapback.provider_id), ("reaction", reaction.provider_id))
        self.assertEqual(edited_tapback.received_at, reaction.received_at)

    def test_dateEdited_on_a_new_message_changes_nothing(self):
        ev = event("new-message")
        ev["data"]["dateEdited"] = EDIT_MS
        self.assertEqual(normalize(ev), normalize(event("new-message")))

    def test_sealed_envelope_keeps_the_composite_id(self):
        msg, seen = normalize(event("updated-message")), set()
        envelope = json.loads(json.dumps(seal(msg, KEY, nonce=NONCE, now=NOW)))
        self.assertEqual(envelope["body"]["provider_id"], EDIT_ID)
        back = unseal(envelope, KEY, now=NOW, seen=seen)
        self.assertEqual((back, back.provider_id.encode("utf-8")), (msg, EDIT_ID.encode("utf-8")))


class EditInboxTests(unittest.TestCase):
    def open_inbox(self, start_at="2026-11-01T00:00:00+00:00"):
        folder = tempfile.TemporaryDirectory(prefix="hass-edit-ids-")
        self.addCleanup(folder.cleanup)
        box = Inbox(folder.name, start_at)
        self.addCleanup(box.close)
        return box

    def test_same_edit_twice_is_queued_then_duplicate(self):
        box = self.open_inbox()
        self.assertEqual([box.enqueue(normalize(event("updated-message"))) for _ in range(2)], ["queued", "duplicate"])
        self.assertEqual(box.state(EDIT_ID), "pending")

    def test_two_different_edits_are_both_queued(self):
        box = self.open_inbox()
        self.assertEqual([box.enqueue(normalize(edit_of("updated-message", ms))) for ms in (EDIT_MS, EDIT_MS + 1)],
                         ["queued", "queued"])
        self.assertEqual([box.state(f"{GUID}:edited:{ms}") for ms in (EDIT_MS, EDIT_MS + 1)], ["pending", "pending"])

    def test_original_and_its_edit_are_both_queued_in_either_order(self):
        original, edit = normalize(event("new-message")), normalize(edit_of("new-message", EDIT_MS))
        for order in ((original, edit), (edit, original)):
            with self.subTest(first=order[0].kind):
                box = self.open_inbox()
                self.assertEqual([box.enqueue(m) for m in order + order],
                                 ["queued", "queued", "duplicate", "duplicate"])
                self.assertEqual((box.state(original.provider_id), box.state(edit.provider_id)), ("pending", "pending"))

    def test_edit_after_the_start_point_is_kept_when_the_original_is_history(self):
        box = self.open_inbox("2026-11-02T17:00:30+00:00")  # between the send (17:00:00) and the edit (17:01:10)
        original, edit = normalize(event("new-message")), normalize(edit_of("new-message", EDIT_MS))
        self.assertEqual([box.enqueue(original), box.enqueue(edit)], ["history", "queued"])


class EditConversationTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "ownerChat": OWNER_CHAT})
        self.conv.db.close()
        self.conv = self.open()

    def test_edit_of_a_handled_message_is_not_a_duplicate(self):
        original, edit = normalize(event("new-message")), normalize(edit_of("new-message", EDIT_MS))
        self.assertEqual([self.conv.handle(m) for m in (original, edit, edit)],
                         ["proposed", "not-read", "duplicate"])


if __name__ == "__main__":
    unittest.main()
