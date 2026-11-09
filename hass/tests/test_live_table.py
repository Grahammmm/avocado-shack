"""HASS-LIVE-PLAN-1: the live table (which chat changes may reach the website) on real operations and real content.

Real production ops prepared on a throwaway writer repo (hass.tests.test_editor.WriterRepo), then judged by hass.live_policy.
A change outside the table is refused in plain words and kept as a private proposal (one backlog row), never applied.
Run: python3 -m unittest hass.tests.test_live_table -v
"""
import json
import unittest
from datetime import datetime, timezone

from hass import conversation as conv, editor, live_policy as policy, voice
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, ConversationTestCase, _ops
from hass.tests.test_editor import WriterRepo
from hass.tests.test_live_policy import edit

NOW = datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc)
SITE = "fixture.example.invalid"
PRODUCT = "photo-product-001"


def op(opname, /, **args): return {"op": opname, "args": args}


class TableShape(unittest.TestCase):
    def test_every_real_operation_is_classified(self):
        """A new op fails this test until someone decides live or private for it (never silently live)."""
        names = set(load_registry())
        self.assertEqual(names - set(policy.LIVE) - set(policy.PRIVATE), set())
        self.assertEqual(set(policy.LIVE) & set(policy.PRIVATE), set())
        self.assertEqual(set(policy.LIVE) - names, set())
        self.assertEqual(set(policy.PRIVATE) - names, set())

    def test_the_table_is_exactly_what_g_approved(self):
        self.assertEqual(sorted(policy.LIVE), sorted([
            "product.hide", "product.restore", "product.edit", "product.set_availability", "product.clear_availability",
            "store.confirm_selection", "specials.add", "specials.edit", "specials.remove", "specials.clear_expired",
            "hike.create", "hike.update", "hike.cancel", "maker.edit", "history.revert",
            "product.add", "maker.add"]))  # HASS-LIVE-ADD-1 (G, 2026-11-09)
        self.assertEqual(policy.LIVE["product.edit"], {"id", "description", "category"})
        self.assertEqual(policy.LIVE["maker.edit"], {"key", "story"})
        self.assertEqual(policy.LIVE["product.add"], {"name", "brand", "category", "description", "photo", "imageAlt", "producerKey",
                                                      "displayBrand"})  # never `image`
        self.assertEqual(policy.LIVE["maker.add"], {"key", "name", "place", "story"})  # never `url`

    def test_every_private_reason_is_plain_and_passes_the_voice_check(self):
        for name in policy.PRIVATE:
            with self.subTest(op=name):
                text = policy.refusal([f"not live: {name}"])
                self.assertEqual(voice.check(text), [], text)
                self.assertIn("I've saved it for Graham", text)
                self.assertNotIn("not live", text)
        for reasons in (["not live: product.edit.brand"], ["not live: made.up"], ["sign-up is on"], ["more than 10 records"]):
            self.assertEqual(voice.check(policy.refusal(reasons)), [])


class RealDrafts(unittest.TestCase):
    def setUp(self):
        self.repo = WriterRepo()
        self.addCleanup(self.repo.cleanup)

    def draft(self, *ops):
        out = editor.prepare({"ops": list(ops)}, state=str(self.repo.state), now=NOW)
        self.assertEqual(out["result"], "ok", out)
        return out["draft"]

    def refused(self, *ops):
        return policy.check(self.draft(*ops))

    def maker_key(self):
        return next(iter(json.loads((self.repo.wt / "hass/content/makers.json").read_text())["makers"]))

    def test_live_from_chat(self):
        for label, ops in {
            "hide": [op("product.hide", id=PRODUCT)],
            "edit description": [op("product.edit", id=PRODUCT, description="Soft, sweet and easy to slice.")],
            "edit category": [op("product.edit", id=PRODUCT, category="pantry")],
            "stock word": [op("store.confirm_selection"), op("product.set_availability", id=PRODUCT, available="limited")],
            "special without a price": [op("specials.add", title="Sample Saturday", deal="Free sample Saturday", end="2026-11-15")],
            "hike, sign-up off": [op("hike.create", title="Mill Creek walk", date="2026-11-14", time="08:00",
                                     meetingPoint="Mill Creek trailhead", rsvpEnabled=False)],
        }.items():
            with self.subTest(label=label):
                self.assertEqual(self.refused(*ops), [])

    def test_maker_about_text_goes_live_but_not_place_or_link(self):
        makers = json.loads((self.repo.wt / "hass/content/makers.json").read_text())["makers"]
        key = next(k for k, m in makers.items() if not policy._protected(m["story"])[0])  # a story with no claim in it
        self.assertEqual(self.refused(op("maker.edit", key=key, story="A small family kitchen that cooks in careful batches.")), [])
        for field, value in (("place", "Somewhere, California"), ("url", "https://example.com/about"), ("name", "New Name")):
            with self.subTest(field=field):
                reasons = self.refused(op("maker.edit", key=key, **{field: value}))
                self.assertTrue(reasons, reasons)

    def test_a_product_name_and_maker_hide_and_restore_are_private_and_named_in_plain_words(self):
        """G's list is description and category, and the maker's about text: not a name, not hiding or restoring a maker."""
        self.assertEqual(self.refused(op("product.edit", id=PRODUCT, name="New plain name")), ["not live: product.edit.name"])
        self.assertIn("more than the part I can change from chat", policy.refusal(["not live: product.edit.name"]))
        for name in ("maker.hide", "maker.restore"):
            self.assertIn(name, policy.PRIVATE)
            self.assertNotIn(name, policy.LIVE)
            self.assertIn("I've saved it for Graham", policy.refusal([f"not live: {name}"]))
        self.assertEqual(self.refused(op("maker.hide", key=self.maker_key(), withProducts=True)), ["not live: maker.hide"])

    def test_undo_always_passes(self):
        self.assertEqual(policy.check(edit("old", "new", op="history.revert")), [])

    def test_private_only_never_goes_live(self):
        cases = {
            "product.edit brand": [op("product.edit", id=PRODUCT, brand="Someone Else")],
            "product.edit producer": [op("product.edit", id=PRODUCT, producerKey="Etto")],
            "product.edit name": [op("product.edit", id=PRODUCT, name="New plain name")],
            "maker hide": [op("maker.hide", key=self.maker_key(), withProducts=True)],
            "new item with a picture file that is already on the site (image argument)": [op("product.add", name="Test jam", brand="Test Orchard", category="pantry", image="assets/products/photo-product-001.webp",
                            description="Sweet jam.")],
            "hours": [op("store.set_hours", hours=["Monday 9am-5pm"])],
            "phone": [op("store.set_phone", phone="805 555 0123")],
            "address": [op("store.set_address", town="Somewhere")],
            "hike with trail": [op("hike.create", title="Walk", date="2026-11-14", time="08:00", meetingPoint="Trailhead",
                                   rsvpEnabled=False, trailId="idea-fiscalini-bluff")],
            "hike sign-up on": [op("hike.create", title="Walk", date="2026-11-14", time="08:00", meetingPoint="Trailhead", rsvpEnabled=True, capacity=8)],
            "special with a price": [op("specials.add", title="Berries", deal="2 for $5", end="2026-11-15")],
        }
        for label, ops in cases.items():
            with self.subTest(label=label):
                self.assertTrue(self.refused(*ops), label)

    def test_a_hike_that_already_has_sign_up_is_private_to_change(self):
        draft = self.draft(op("hike.create", title="Walk", date="2026-11-14", time="08:00", meetingPoint="Trailhead", rsvpEnabled=False))
        self.assertEqual(policy.check(draft), [])
        for record in draft["records"]:
            if record["collection"] == "events": record["before"] = {**(record["after"] or {}), "rsvpEnabled": True}
        self.assertEqual(policy.check(draft), ["sign-up is on"])
        self.assertIn("sign up", policy.refusal(["sign-up is on"]))

    def test_claims_still_block_inside_the_table(self):
        for text in ("Organic and grown in Paso Robles.", "Award-winning and good for your heart."):
            with self.subTest(text=text):
                self.assertTrue(self.refused(op("product.edit", id=PRODUCT, description=text)))

    def test_too_many_records_still_blocks(self):
        draft = self.draft(op("product.hide", id=PRODUCT))
        draft["records"] = draft["records"] * 11
        self.assertEqual(policy.check(draft), ["more than 10 records"])


class RefusedIsSavedPrivately(ConversationTestCase):
    """A refused live change is explained in plain words and kept, once, as a private proposal."""

    def setUp(self):
        super().setUp()
        fixture_ops.allow_live(self)
        self.conv.db.close()
        self.set_settings({**SETTINGS, "liveSite": SITE, "approvalNeedsCode": True})
        self.interp = conv.FixtureInterpreter({"organic": _ops(("test.set_product_description", {"id": PRODUCT, "description": "Organic fruit"}))})
        self.conv = self.open()
        self.addCleanup(lambda: self.conv.db.close())

    def backlog(self):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'backlog'").fetchone(): return []
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM backlog")]

    def test_refusal_is_plain_saved_once_and_nothing_is_applied(self):
        self.assertEqual(self.say("organic"), "proposed")
        [reply] = self.replies()
        self.assertIn("I can't put this on the website from chat", reply)
        self.assertIn("I've saved it for Graham to look at", reply)
        self.assertNotIn("Reply yes", reply)
        [row] = self.backlog()
        self.assertEqual((row["reason"], row["state"]), ("policy", "open"))
        code = self.drafts()[0]["code"]
        self.assertTrue(row["summary"].startswith(f"[{code}]"))
        self.assertIn("test.set_product_description", row["text"])
        self.assertEqual(self.say(f"yes {code}"), "no-target")  # a yes cannot get around it
        self.assertIn("I've saved it for Graham", self.replies()[0])
        self.assertEqual(len(self.backlog()), 1)  # once, not once per try
        self.assertEqual((self.editor.applies, self.commits()), (0, 0))
        self.assertEqual(self.conv.db.execute("SELECT count(*) FROM approvals").fetchone()[0], 0)

    def test_an_allowed_change_leaves_no_backlog_row(self):
        self.interp.mapping["hours"] = _ops(("test.set_store_hours", {"hours": ["Monday 9am-5pm"]}))
        self.assertEqual(self.say("hours"), "proposed")
        self.replies()
        self.assertEqual(self.backlog(), [])


if __name__ == "__main__":
    unittest.main()
