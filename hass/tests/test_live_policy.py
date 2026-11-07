"""HASS-LIVEPOL-1: protected-content acceptance, entirely synthetic drafts."""
import unittest
from hass import live_policy as policy


def edit(before, after, field="description", collection="products", op="product.edit"):
    return {"ops": [{"op": op, "args": {}}], "records": [
        {"collection": collection, "key": "fixture", "before": {field: before}, "after": {field: after}}]}


class LivePolicyTests(unittest.TestCase):
    def test_protected_fields(self):
        for collection, fields in policy.FIELDS.items():
            for field in fields:
                for before, after in (("old", "new"), (None, "new"), ("old", None)):
                    with self.subTest(collection=collection, field=field, before=before):
                        self.assertIn(f"protected field: {collection}.{field}", policy.check(edit(
                            before, after, field, collection)))
        self.assertIn("protected field: club.clubName", policy.check(edit("old", "new", "clubName", "club")))

    def test_protected_ops_bulk_and_undo(self):
        for op in sorted(policy.OPS | {"route.edit", "route.add", "route.hide", "route.restore"}):
            with self.subTest(op=op):
                self.assertIn(f"protected operation: {op}", policy.check(edit("old", "new", op=op)))
        draft = edit("old", "new")
        draft["records"] *= 10
        self.assertEqual(policy.check(draft), [])
        draft["records"].append(draft["records"][0])
        self.assertIn("more than 10 records", policy.check(draft))
        draft["ops"] = [{"op": "history.revert", "args": {}}]
        self.assertEqual(policy.check(draft), [])
        draft["ops"].append({"op": "route.edit"})
        self.assertTrue(policy.check(draft))

    def test_substitutions_removals_and_additions(self):
        cases = [("Grown in California.", "Grown in Mexico.", "origin/organic"),
                 ("Organic Hass avocados.", "Not organic Hass avocados.", "origin/organic"),
                 ("Certified organic. Sweet.", "Sweet.", "origin/organic"),
                 ("Award-winning honey.", "Prize-winning honey.", "health/awards/endorsements"),
                 ("$4 per lb.", "$5 per lb.", "prices"),
                 ("a@example.com", "b@example.com", "contact"),
                 ("805.555.0101", "805.555.0102", "contact"),
                 ("(805) 555-0101", "(805) 555-0102", "contact"),
                 ("Dogs allowed on leash.", "Dogs welcome.", "trail facts"),
                 ("‘organic’ fruit", "conventional fruit", "origin/organic"),
                 ("pesticide free", "not pesticide-free", "origin/organic"),
                 ("Endorsed by a farmer.", "Not endorsed by a farmer.", "health/awards/endorsements"),
                 ("20¢", "30¢", "prices")]
        for before, after, kind in cases:
            for old, new in ((before, after), (before, None), (None, before)):
                with self.subTest(before=old, after=new):
                    self.assertIn(f"protected sentences: {kind}", policy.check(edit(old, new)))

    def test_benign_edits_and_sentence_multiset(self):
        for before, after in [("Hello", "Welcome"),
                              ("Grown in California. Sweet and creamy.", "Grown in California. Rich and creamy."),
                              ("Organic. Hello!", "Hello! Organic."),
                              ("Organic\nHello", "Organic\nWelcome"),
                              (["Organic", "Hello"], ["Organic", "Welcome"])]:
            with self.subTest(before=before): self.assertEqual(policy.check(edit(before, after)), [])
        draft = edit(None, "Sweet and creamy")
        draft["records"][0]["before"] = None
        self.assertEqual(policy.check(draft), [])
        self.assertTrue(policy.check(edit("Organic. Organic.", "Organic.")))
        self.assertTrue(policy.check(edit({"text": "Organic"}, {"text": "Not organic"}, "notice", "store")))
        for value in (42, True, None, [1, 2]):
            self.assertIsInstance(policy.sentences(value), list)

    def test_check_never_raises_on_odd_drafts(self):
        cycle = []
        cycle.append(cycle)
        for value in (None, [], "bad", {}, {"ops": [], "records": []},
                      {"ops": [None], "records": []}, {"ops": [{"op": 1}], "records": []},
                      {"ops": [{"op": "product.edit"}], "records": [None]},
                      edit(object(), "ok"), edit(cycle, "ok"), edit(float("nan"), "ok")):
            with self.subTest(type=type(value).__name__):
                self.assertEqual(policy.check(value), ["the change could not be read"])
