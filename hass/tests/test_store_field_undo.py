"""AV2152-11 (H06): undoing a store change sets back only the store fields that change wrote (hass/ops/history.py).

Throwaway StoreRepo (temp repo + temp state dir, fixture content only). Run: python3 -B -m unittest hass.tests.test_store_field_undo
"""

import json
from datetime import timedelta

from hass.content_model import shop_today
from hass.tests.test_store_ops import NEW_HOURS, REVERT, SET_ADDRESS, SET_HOURS, StoreTestCase, _req

STORE = "hass/content/store.json"
TEXT = "Closed Thanksgiving Day"


def day(offset):
    return (shop_today() + timedelta(days=offset)).isoformat()


# field -> (op, args, key written, value written)
OPS = {
    "hours": (SET_HOURS, {"hours": NEW_HOURS}, "hours", NEW_HOURS),
    "streetAddress": (SET_ADDRESS, {"streetAddress": "1023 Example Street"}, "streetAddress", "1023 Example Street"),
    "town": (SET_ADDRESS, {"town": "Cayucos"}, "town", "Cayucos"),
    "intro": ("store.set_intro", {"text": "Fresh from the coast."}, "intro", "Fresh from the coast."),
    "headline": ("store.set_headline", {"first": "Fresh and local.", "second": "Picked this week."}, "headline",
                 ["Fresh and local.", "Picked this week."]),
    "story": ("store.set_story", {"text": "Michael stocks the shelves with fruit from growers he knows by name."},
              "story", "Michael stocks the shelves with fruit from growers he knows by name."),
    "notice": ("store.set_notice", {"text": TEXT, "until": day(5)}, "notice", {"text": TEXT, "until": day(5)}),
    "phone": ("store.set_phone", {"phone": "805 555 0123"}, "phone", None),
    "selection_checked_on": ("store.confirm_selection", {}, "selection_checked_on", day(0)),
}


class FieldUndoBase(StoreTestCase):
    def setUp(self):
        self.r = self.repo()

    def run_op(self, field, **override):
        op, args, _key, _value = OPS[field]
        return self.r.run((op, {**args, **override}))

    def product(self):
        products = json.loads(self.r.read("hass/content/products.json"))["products"]
        return next(p["id"] for p in products if p["status"] == "active")

    def undo(self, change):
        return self.r.prepare(_req((REVERT, {"changeId": change["change_id"]})))

    def assert_refused_untouched(self, change, reason):
        head, drafts, content = self.r.head(), self.r.drafts(), self.r.read(STORE)
        result = self.undo(change)
        self.assertEqual((result["result"], result["reason"]), ("refused", reason))
        self.assertEqual((self.r.head(), self.r.drafts(), self.r.read(STORE), self.r.status()), (head, drafts, content, ""))


class FieldUndoTests(FieldUndoBase):
    def test_notice_undo_after_selection_check(self):
        original = self.r.store()
        notice = self.run_op("notice")
        check = self.run_op("selection_checked_on")
        self.assertEqual(self.r.store()["selection_checked_on"], day(0))
        undo = self.r.run((REVERT, {"changeId": notice["change_id"]}))
        self.assertEqual(self.r.store(), {**original, "selection_checked_on": day(0)})
        self.assertNotIn("notice", self.r.store())
        self.assertEqual(self.r.status(), "")
        record = json.loads((self.r.state / "changes" / f"{notice['change_id']}.json").read_text("utf-8"))
        self.assertEqual(record["revertedBy"], undo["change_id"])
        inverse = undo["records"][0]  # actual current -> merged dictionaries, not the old snapshots
        self.assertIn("notice", inverse["before"])
        self.assertEqual(inverse["after"]["selection_checked_on"], day(0))
        self.assertNotIn("notice", inverse["after"])
        # the later check can still be undone, newest or not
        self.r.run((REVERT, {"changeId": check["change_id"]}))
        self.assertEqual(self.r.store(), original)

    def test_each_store_field_preserves_later_other_field(self):
        for field in OPS:
            others = [f for f in OPS if f != field and not (
                {f, field} == {"streetAddress", "town"} and False)]
            for other in others:
                if field == "notice" and other == "notice":
                    continue
                with self.subTest(field=field, later=other):
                    repo = self.r = self.repo()
                    original = repo.store()
                    first = self.run_op(field)
                    self.run_op(other)
                    after_both = repo.store()
                    result = self.undo(first)
                    self.assertEqual(result["result"], "ok", result)
                    self.assertEqual(repo.apply(result["draft"])["result"], "applied")
                    now = repo.store()
                    self.assertEqual(now.get(field), original.get(field))
                    self.assertEqual(field in now, field in original)
                    self.assertEqual(now.get(other), after_both.get(other))
                    self.assertEqual(repo.status(), "")

    def test_optional_fields_set_and_removed(self):
        for field in ("intro", "headline", "story", "notice", "phone"):
            with self.subTest(field=field):
                repo = self.r = self.repo()
                self.assertNotIn(field, repo.store())
                first = self.run_op(field)
                self.assertIn(field, repo.store())
                self.run_op("hours")
                repo.run((REVERT, {"changeId": first["change_id"]}))
                self.assertNotIn(field, repo.store())
                self.assertEqual(repo.store()["hours"], NEW_HOURS)

    def test_clear_after_set_restores_the_field_and_keeps_later_other_fields(self):
        self.run_op("phone")
        cleared = self.r.run(("store.clear_phone", {}))
        self.run_op("intro")
        self.r.run((REVERT, {"changeId": cleared["change_id"]}))
        self.assertIn("phone", self.r.store())
        self.assertIn("intro", self.r.store())

    def test_store_and_product_batch_keeps_later_store_field(self):
        product = self.product()
        check = self.r.run(("store.confirm_selection", {"limited": [product]}))
        self.assertEqual({rec["collection"] for rec in check["records"]}, {"store", "products"})
        self.run_op("hours")
        self.r.run((REVERT, {"changeId": check["change_id"]}))
        self.assertNotIn("selection_checked_on", self.r.store())
        self.assertEqual(self.r.store()["hours"], NEW_HOURS)


class FieldConflictTests(FieldUndoBase):
    def conflict(self, change):
        return f"conflict: store store changed after {change['change_id']}"

    def test_same_field_conflicts_without_writes(self):
        cases = {
            "hours": ["Monday–Saturday 8am–5pm", "Closed Sunday"],
        }
        first = self.run_op("hours")
        self.run_op("hours", hours=cases["hours"])
        self.assert_refused_untouched(first, self.conflict(first))
        phone = self.run_op("phone")
        self.run_op("phone", phone="805 555 0199")
        self.assert_refused_untouched(phone, self.conflict(phone))
        notice = self.run_op("notice")
        self.run_op("notice", until=day(6))  # one notice subfield differs: the notice is one field
        self.assert_refused_untouched(notice, self.conflict(notice))
        removed = self.run_op("intro")
        self.r.run(("store.set_intro", {"text": "A different line."}))
        self.assert_refused_untouched(removed, self.conflict(removed))

    def test_later_removal_of_the_same_field_conflicts(self):
        notice = self.run_op("notice")
        self.r.run(("store.clear_notice", {}))
        self.assert_refused_untouched(notice, self.conflict(notice))

    def test_conflict_in_one_field_blocks_a_multi_field_change(self):
        both = self.r.run((SET_HOURS, {"hours": NEW_HOURS}), (SET_ADDRESS, {"town": "Cayucos"}))
        self.run_op("hours", hours=["Monday–Friday 10am–4pm"])
        self.assert_refused_untouched(both, self.conflict(both))

    def test_conflict_checks_run_before_any_restore(self):
        product = self.product()
        check = self.r.run(("store.confirm_selection", {"limited": [product]}))
        self.r.run(("store.confirm_selection", {"no": [product]}))  # same product, newer value: record-level conflict
        self.assert_refused_untouched(check, f"conflict: products {product} changed after {check['change_id']}")

    def test_change_away_and_back_is_value_based_safe(self):
        original = self.r.store()["hours"]
        first = self.run_op("hours")
        self.run_op("hours", hours=["Monday–Friday 10am–4pm"])
        self.r.run((SET_HOURS, {"hours": NEW_HOURS}))  # current equals what the first change wrote
        self.r.run((REVERT, {"changeId": first["change_id"]}))
        self.assertEqual(self.r.store()["hours"], original)


class RepeatedAndMalformedTests(FieldUndoBase):
    def test_repeated_store_ops_union_and_first_before(self):
        original = self.r.store()
        change = self.r.run((SET_HOURS, {"hours": NEW_HOURS}), ("store.set_intro", {"text": "Fresh from the coast."}),
                            (SET_HOURS, {"hours": ["Monday–Friday 10am–4pm"]}))
        self.run_op("streetAddress")
        self.r.run((REVERT, {"changeId": change["change_id"]}))
        store = self.r.store()
        self.assertEqual(store["hours"], original["hours"])
        self.assertNotIn("intro", store)
        self.assertEqual(store["streetAddress"], "1023 Example Street")

    def test_field_changed_twice_to_its_original_value_still_conflicts_with_later_edit(self):
        original = self.r.store()["hours"]
        change = self.r.run((SET_HOURS, {"hours": NEW_HOURS}), (SET_HOURS, {"hours": original}),
                            ("store.set_intro", {"text": "Fresh from the coast."}))
        self.assertEqual(self.r.store()["hours"], original)
        self.r.run((SET_HOURS, {"hours": ["Monday–Friday 10am–4pm"]}))
        self.assert_refused_untouched(change, f"conflict: store store changed after {change['change_id']}")

    def test_omitted_and_null_are_distinct(self):
        change = self.run_op("intro")
        path = self.r.state / "changes" / f"{change['change_id']}.json"
        record = json.loads(path.read_text("utf-8"))
        record["records"][0]["after"]["phone"] = None  # the change "wrote" an explicit null phone; none exists now
        path.write_text(json.dumps(record), "utf-8")
        self.assert_refused_untouched(change, f"conflict: store store changed after {change['change_id']}")

    def test_bad_store_snapshots_are_refused(self):
        for label, mutate in {
            "before list": lambda rs: rs[0].update(before=[]),
            "after null": lambda rs: rs[0].update(after=None),
            "after scalar": lambda rs: rs[0].update(after="x"),
            "wrong key": lambda rs: rs[0].update(key="other"),
            "bad middle record": lambda rs: rs.insert(1, {**rs[0], "before": 7}),
        }.items():
            with self.subTest(label):
                self.r = self.repo()
                change = self.run_op("hours")
                path = self.r.state / "changes" / f"{change['change_id']}.json"
                record = json.loads(path.read_text("utf-8"))
                mutate(record["records"])
                if label == "bad middle record":
                    record["records"].append({**record["records"][0], "before": {}, "after": {}})
                path.write_text(json.dumps(record), "utf-8")
                self.assert_refused_untouched(change, f"{change['change_id']} record is malformed")

    def test_legacy_full_snapshot_without_a_draft_still_undoes(self):
        original = self.r.store()
        change = self.run_op("hours")
        (self.r.state / "drafts" / f"{change['change_id']}.json").unlink()
        self.r.run((REVERT, {"changeId": change["change_id"]}))
        self.assertEqual(self.r.store(), original)

    def test_stale_approval_repeat_and_undo_of_undo(self):
        first = self.run_op("hours")
        result = self.undo(first)
        self.run_op("intro")  # an intervening store edit after the undo was prepared
        self.assertEqual(self.r.apply(result["draft"])["result"], "stale")
        record = json.loads((self.r.state / "changes" / f"{first['change_id']}.json").read_text("utf-8"))
        self.assertFalse(record.get("revertedBy"))
        undo = self.r.run((REVERT, {"changeId": first["change_id"]}))
        again = self.undo(first)
        self.assertIn("already undone", again["reason"])
        self.assertIn("is an undo", self.undo(undo)["reason"])
        self.assertEqual(self.r.status(), "")
