"""RF0721-10 tests: a photo whose SHA the request already retains still fills the asked, unfilled attachment slot (spec
reports/hass/SKILLS-SPEC.md:269); list de-duplication is kept separate from answering the question.

Store cases run on a temporary sqlite file with an explicit clock; the dispatcher cases run the real ``dispatch.photo`` on the
existing toy PHOTO_ITEM skill. Nothing is fetched, no model is called, nothing is approved or applied.
Run: python3 -B -m unittest hass.tests.test_open_request_repeat_photo -q
"""
import unittest
from datetime import timedelta

from hass import conversation
from hass.skills import dispatch
from hass.tests.test_conversation import CHAT, OWNER
from hass.tests.test_open_requests import OTHER_ID, OWNER_ID, T0, StoreCase
from hass.tests.test_skill_dispatch import HIKE_ADD, PHOTO_ITEM, SkillCase, registry_of, skill_reply, toy
from hass.skills.model import Slot

SHA, OTHER = "a" * 64, "b" * 64
LATER = T0 + timedelta(minutes=5)
NO_FLAG = toy("item.nofrom", "put a photo somewhere", (Slot("photo", "attachment", True),), PHOTO_ITEM.plan)
REGISTRY = registry_of(PHOTO_ITEM, NO_FLAG)


class RepeatStoreCase(StoreCase):
    def retained(self, skill="item.picture", asked="photo", slots=None, attachments=(SHA,), at=T0, owner=OWNER_ID):
        return self.put(at, owner=owner, skill=skill, slots=slots if slots is not None else {"product": "jam"},
                        asked_slot=asked, question="send the photo", ask={"kind": "photo"}, attachments=list(attachments))

    def rows(self):
        return [tuple(r) for r in self.db.execute("SELECT * FROM open_requests ORDER BY request_id")]


class StoreTests(RepeatStoreCase):
    def test_retained_sha_fills_empty_asked_attachment_slot(self):
        rid = self.retained()
        how, req = self.store.bind_attachment(OWNER_ID, "p2", SHA, LATER, REGISTRY)
        self.assertEqual(how, "filled")
        self.assertEqual((req["request_id"], req["skill"], req["attachments"]), (rid, "item.picture", [SHA]))
        self.assertEqual(req["slots"], {"product": "jam", "photo": SHA})
        self.assertEqual((req["asked_slot"], req["ask"] or None), (None, None))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM open_requests").fetchone()[0], 1)

    def test_retained_sha_in_a_longer_list_keeps_order_and_cardinality(self):
        self.retained(attachments=(OTHER, SHA))
        how, req = self.store.bind_attachment(OWNER_ID, "p2", SHA, LATER, REGISTRY)
        self.assertEqual((how, req["attachments"], req["slots"]["photo"]), ("filled", [OTHER, SHA], SHA))

    def test_repeat_without_eligible_slot_remains_no_write_attached(self):
        cases = {
            "absent registry": (dict(), None),
            "unknown skill": (dict(skill="no.such.skill"), REGISTRY),
            "wrong slot kind": (dict(asked="product", slots={}), REGISTRY),
            "no from_attachment": (dict(skill="item.nofrom", slots={}), REGISTRY),
            "already filled": (dict(slots={"product": "jam", "photo": OTHER}), REGISTRY),
        }
        for label, (kw, registry) in cases.items():
            with self.subTest(label):
                self.db.execute("DROP TABLE IF EXISTS open_requests")
                self.retained(**kw)
                before = self.rows()
                how, req = self.store.bind_attachment(OWNER_ID, "p2", SHA, LATER, registry)
                self.assertEqual((how, req["attachments"]), ("attached", [SHA]))
                self.assertEqual(self.rows(), before)  # no write: nothing renewed, nothing filled

    def test_new_sha_and_repeat_after_fill_preserve_existing_semantics(self):
        self.retained(attachments=())
        how, req = self.store.bind_attachment(OWNER_ID, "p2", SHA, LATER, REGISTRY)
        self.assertEqual((how, req["attachments"], req["slots"]["photo"]), ("filled", [SHA], SHA))
        before = self.rows()
        how, req = self.store.bind_attachment(OWNER_ID, "p3", SHA, LATER + timedelta(seconds=5), REGISTRY)
        self.assertEqual((how, req["attachments"], req["slots"]["photo"]), ("attached", [SHA], SHA))
        self.assertEqual(self.rows(), before)
        how, req = self.store.bind_attachment(OWNER_ID, "p4", OTHER, LATER + timedelta(seconds=9), REGISTRY)
        self.assertEqual((how, req["attachments"], req["slots"]["photo"]), ("attached", [SHA, OTHER], SHA))

    def test_owner_expiry_and_bad_sha_boundaries(self):
        self.retained(owner=OTHER_ID)
        theirs = self.rows()
        how, req = self.store.bind_attachment(OWNER_ID, "p2", SHA, LATER, REGISTRY)  # another owner's row is not ours to fill
        self.assertEqual((how, req["skill"], req["slots"], req["attachments"]), ("opened", None, {}, [SHA]))
        self.assertEqual([r for r in self.rows() if r[2] == OTHER_ID], [r for r in theirs if r[2] == OTHER_ID])

        self.db.execute("DROP TABLE open_requests")
        rid = self.retained()
        stale = self.rows()
        how, req = self.store.bind_attachment(OWNER_ID, "p3", SHA, T0 + timedelta(hours=3), REGISTRY)  # expired: not resurrected
        self.assertEqual((how, req["skill"], req["slots"]), ("opened", None, {}))
        self.assertNotEqual(req["request_id"], rid)
        old = self.db.execute("SELECT state, slots_json FROM open_requests WHERE request_id = ?", (rid,)).fetchone()
        self.assertEqual((old["state"] in ("open", "drafted"), old["slots_json"]), (False, stale[0][5]))  # never filled, never live

        before = self.rows()
        for bad in ("short", "g" * 64, None, 5):
            with self.assertRaises(ValueError):
                self.store.bind_attachment(OWNER_ID, "p4", bad, LATER, REGISTRY)
        self.assertEqual(self.rows(), before)


class DispatchTests(SkillCase):
    SKILLS = (HIKE_ADD, PHOTO_ITEM)

    def asked_photo(self):
        self.script("this is for the jam", skill_reply("item.picture", product="Cal Poly strawberry jam"))
        self.assertEqual(self.say("this is for the jam"), "question")
        self.assertEqual(self.live()["asked_slot"], "photo")
        self.conv.db.execute("UPDATE open_requests SET attachments_json = ? WHERE state = 'open'", ('["%s"]' % SHA,))
        self.assertEqual(self.live()["attachments"], [SHA])

    def photo(self, caption=""):
        msg = conversation.Inbound("p2", CHAT, OWNER, caption, False, "new", self.now.isoformat(), 1)
        return self.conv.dispatch.photo(msg, self.now, SHA, caption)

    def test_real_dispatch_repeated_retained_photo_advances_without_generic_question(self):
        self.asked_photo()
        replies = len(self.replies())
        self.assertEqual(self.photo(), "proposed")
        live = self.live()
        self.assertEqual((live["state"], live["slots"]["photo"], live["attachments"]), ("drafted", SHA, [SHA]))
        generic = dispatch.PHOTO_FOR.format(labels=PHOTO_ITEM.label)
        self.assertNotIn(generic, self.replies()[replies:])  # the generic photo-purpose question is not repeated
        self.nothing_written()  # proposed only: no approval, no writer commit

    def test_caption_handoff_keeps_filled_photo(self):
        self.asked_photo()
        self.assertIsNone(self.photo("the jam jar"))  # the caption is read with this request by the normal path
        live = self.live()
        self.assertEqual((live["slots"]["photo"], live["attachments"], live["asked_slot"]), (SHA, [SHA], None))
        self.assertEqual(live["state"], "open")
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
