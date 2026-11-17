"""RF0015-21: an already-absent phone must not block a requested address change in shop.contact."""
import copy
import json
import types
import unittest

from hass.skills import shop
from hass.tests import test_skill_dispatch as dispatch_fixture

NOPHONE = "There is no phone number on the site, so there is nothing to take off."
BASE = {"streetAddress": "1023 Example Street", "town": "Morro Bay"}
CLEAR = {"op": "store.clear_phone", "args": {}}


def ctx_for(store, kind="dict"):
    if kind == "ns":
        return types.SimpleNamespace(today="2026-11-08", store=store, texts=["take the phone off"])
    return types.SimpleNamespace(today="2026-11-08", content={"store": store}, texts=["take the phone off"])


def plan(slots, store, kind="dict"):
    slots, store = copy.deepcopy(slots), copy.deepcopy(store)
    before = (copy.deepcopy(slots), copy.deepcopy(store))
    first = shop.plan_contact(slots, ctx_for(store, kind))
    again = shop.plan_contact(slots, ctx_for(store, kind))
    assert first == again and (slots, store) == before
    return first


class MissingPhone(unittest.TestCase):
    def test_changed_address_is_drafted_without_a_clear(self):
        for absent in ({}, {"phone": ""}, {"phone": None}):
            for kind in ("dict", "ns"):
                store = {**BASE, **absent}
                for slots, args in (({"town": "Los Osos"}, {"town": "Los Osos"}),
                                    ({"street_address": "4 Example Road"}, {"streetAddress": "4 Example Road"}),
                                    ({"town": "Los Osos", "street_address": "4 Example Road"},
                                     {"town": "Los Osos", "streetAddress": "4 Example Road"})):
                    with self.subTest(absent=absent, kind=kind, slots=slots):
                        self.assertEqual(plan({"clear": True, **slots}, store, kind),
                                         [{"op": "store.set_address", "args": args}])

    def test_nothing_left_to_change_is_still_refused(self):
        for slots in ({"clear": True}, {"clear": True, "town": "Morro Bay"},
                      {"clear": True, "town": "Morro  Bay", "street_address": "1023 Example  Street"}):
            with self.subTest(slots=slots):
                with self.assertRaises(shop.SkillStop) as caught:
                    plan(slots, BASE)
                self.assertEqual(caught.exception.reply, NOPHONE)
                self.assertEqual(caught.exception.kind, "refused")

    def test_case_change_in_town_is_a_real_change(self):
        self.assertEqual(plan({"clear": True, "town": "morro bay"}, BASE),
                         [{"op": "store.set_address", "args": {"town": "morro bay"}}])

    def test_existing_phone_and_unknown_store_keep_their_plans(self):
        store = {**BASE, "phone": "8055550100"}
        self.assertEqual(plan({"clear": True, "town": "Los Osos"}, store),
                         [CLEAR, {"op": "store.set_address", "args": {"town": "Los Osos"}}])
        self.assertEqual(plan({"clear": True, "town": "Morro Bay"}, store), [CLEAR])
        self.assertEqual(shop.plan_contact({"clear": True}, None), [CLEAR])
        self.assertEqual(shop.plan_contact({"clear": True, "town": "Los Osos"}, None),
                         [CLEAR, {"op": "store.set_address", "args": {"town": "Los Osos"}}])

    def test_other_requests_are_unchanged(self):
        store = {**BASE, "phone": "8055550100"}
        self.assertEqual(plan({"phone": "805 555 0100", "town": "Los Osos"}, store),
                         [{"op": "store.set_address", "args": {"town": "Los Osos"}}])
        self.assertEqual(plan({"town": "Los Osos"}, store), [{"op": "store.set_address", "args": {"town": "Los Osos"}}])
        with self.assertRaises(shop.SkillStop) as caught:
            plan({"town": "Morro Bay"}, store)
        self.assertTrue(caught.exception.reply.startswith("It already says that:"))

    def test_conflict_and_bad_addresses_still_stop(self):
        for slots, kind in (({"phone": "805 555 0100", "clear": True, "town": "Los Osos"}, "question"),
                            ({"clear": True, "town": "x" * (shop.MAX_ADDRESS_PART + 1)}, "question"),
                            ({"clear": True, "town": "12345"}, "question"),
                            ({"clear": True, "street_address": "$5 Road"}, "refused")):
            with self.subTest(slots=slots):
                with self.assertRaises(shop.SkillStop) as caught:
                    plan(slots, BASE)
                self.assertEqual(caught.exception.kind, kind)


class RealDispatcherContact(dispatch_fixture.SkillCase):
    SKILLS = (shop.SHOP_CONTACT,)

    def test_phone_off_and_new_town_drafts_only_the_address(self):
        text = "take the phone off and change the town to Los Osos"
        self.script(text, dispatch_fixture.skill_reply("shop.contact", clear=True, town="Los Osos"))
        store = self.repo.wt / "hass" / "content" / "store.json"
        self.assertFalse(json.loads(store.read_text("utf-8")).get("phone"))  # the synthetic scratch store has no phone
        draft, _reply = self.propose(text)
        self.assertEqual(draft["state"], "proposed")
        ops = json.loads(draft["ops_json"])
        self.assertEqual(ops, [{"op": "store.set_address", "args": {"town": "Los Osos"}}])
        self.nothing_written()
        self.assertEqual(shop.SHOP_CONTACT.live_class, "private-only")
