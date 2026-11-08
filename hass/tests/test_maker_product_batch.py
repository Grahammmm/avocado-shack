"""AV1937-02 tests: one draft adds a maker and a product that names it (H03).

A producerKey equal to the key of a clean maker.add EARLIER in the same ops list passes the argument check; a key added
later, by a refused or incomplete maker.add, or only similar to one, stays invalid. Throwaway repos and the fixture
conversation only: no model, no network, nothing outside a temp dir.
Run: python3 -B -m unittest hass.tests.test_maker_product_batch -v
"""

import dataclasses
import json
import unittest

from hass import conversation, editor
from hass.ops import load_registry
from hass.tests import fixture_ops, test_undo
from hass.tests.test_catalog_ops import NEW, CatalogTestCase, _req
from hass.tests.test_conversation import _ops
from hass.tests.test_editor import git

KEY = "Bee Happy Farm"
MAKER = {"key": KEY, "name": KEY, "place": "Templeton, California", "story": "Keeps bees and bottles honey.",
         "url": "https://example.com/bee-happy"}
HONEY = {**NEW, "name": "New honey", "brand": KEY, "displayBrand": KEY, "producerKey": KEY}
NOT_A_MAKER = "not a maker in makers.json"


class Spy:
    """Registry whose ops count their apply calls (and may be replaced) so tests can see what really ran."""

    def __init__(self, **replace):
        self.calls, self.registry = [], {}
        for name, op in load_registry().items():
            fn = replace.get(name, op.apply)
            self.registry[name] = dataclasses.replace(op, apply=self._wrap(name, fn))

    def _wrap(self, name, fn):
        def apply(content, args, ctx):
            self.calls.append(name)
            return fn(content, args, ctx)
        return apply


class BatchTestCase(CatalogTestCase):
    def prepare(self, repo, *ops, spy=None):
        return editor.prepare(_req(*ops), state=str(repo.state), registry=(spy or Spy()).registry)

    def snapshot(self, repo):
        changes = repo.state / "changes"
        return (repo.head(), repo.status(), repo.drafts(), sorted(p.name for p in changes.iterdir()) if changes.is_dir() else [],
                repo.read("hass/content/makers.json"), repo.read("hass/content/products.json"),
                repo.read("storefront-mockup/producers.json"), repo.read("storefront-mockup/catalog-products.js"))

    def rejected(self, repo, result_name, *ops, spy=None):
        before = self.snapshot(repo)
        result = self.prepare(repo, *ops, spy=spy)
        self.assertEqual(result["result"], result_name, result)
        self.assertEqual(self.snapshot(repo), before)
        return result

    def commits(self, repo):
        return int(git(repo.wt, "rev-list", "--count", "HEAD"))


class AddMakerThenProductTests(BatchTestCase):
    def test_add_maker_then_product_one_draft(self):
        repo = self.repo()
        base, spy = self.commits(repo), Spy()
        result = self.prepare(repo, ("maker.add", MAKER), ("product.add", HONEY), spy=spy)
        self.assertEqual(result["result"], "ok", result)
        draft = result["draft"]
        self.assertEqual([(r["collection"], r["key"]) for r in draft["records"]],
                         [("makers", KEY), ("products", "photo-product-175")])
        self.assertEqual(spy.calls, ["maker.add", "product.add"])  # each op simulated exactly once
        self.assertEqual((self.commits(repo), KEY in repo.makers()), (base, False))  # nothing written before approval
        applied = editor.apply(draft["change_id"], draft["draft_hash"], state=str(repo.state), registry=spy.registry)
        self.assertEqual(applied["result"], "applied", applied)
        self.assertEqual(self.commits(repo), base + 1)  # one signed content commit holds both
        self.assertIn("Signed-off-by:", git(repo.wt, "log", "-1", "--format=%B"))
        self.assertEqual(repo.makers()[KEY]["place"], "Templeton, California")
        self.assertEqual(repo.products()[-1]["producerKey"], KEY)
        self.assertIn(KEY.encode(), repo.read("storefront-mockup/producers.json"))
        self.assertIn("photo-product-175", [p["id"] for p in repo.catalog()])

    def test_product_before_maker_invalid(self):
        repo = self.repo()
        result = self.rejected(repo, "invalid", ("product.add", HONEY), ("maker.add", MAKER))
        self.assertEqual(result["problems"], [f"ops[0] 'product.add': product.add.producerKey: {NOT_A_MAKER}"])
        # later in the list, not just adjacent, and after other ops
        self.rejected(repo, "invalid", ("maker.add", {**MAKER, "key": "Other Farm", "name": "Other Farm"}),
                      ("product.add", HONEY), ("maker.add", MAKER))
        # a product.edit before the add is no different
        self.rejected(repo, "invalid", ("product.edit", {"id": "photo-product-001", "producerKey": KEY}),
                      ("maker.add", MAKER))

    def test_edit_in_same_draft_may_name_the_new_maker(self):
        repo = self.repo()
        repo.run(("maker.add", MAKER), ("product.edit", {"id": "photo-product-001", "producerKey": KEY}))
        self.assertEqual({p["id"]: p.get("producerKey") for p in repo.products()}["photo-product-001"], KEY)

    def test_refused_maker_never_authorizes_product(self):
        repo = self.repo()
        repo.run(("maker.add", {**MAKER, "key": "Test Farm", "name": "Test Farm"}), ("maker.hide", {"key": "Test Farm"}))
        twin_name = {**MAKER, "key": "Etto Two", "name": "etto"}
        cases = {"existing name twin": (twin_name, "Etto Two", "maker Etto already has this name; edit it instead"),
                 "folded key twin": ({**MAKER, "key": "etto", "name": "Brand New Pastas"}, "etto", "maker Etto already exists"),
                 "spaced key twin": ({**MAKER, "key": "Etto ", "name": "Brand New Pastas"}, "Etto ", None),
                 "hidden key twin": ({**MAKER, "key": "TEST FARM", "name": "Brand New Pastas"}, "TEST FARM",
                                     "maker Test Farm already exists; restore it instead"),
                 "overlong key": ({**MAKER, "key": "x" * 65}, "x" * 65, "maker key is longer than 64 characters")}
        for label, (maker, key, reason) in cases.items():
            with self.subTest(label):
                spy = Spy()
                result = self.rejected(repo, "refused" if reason else "invalid", ("maker.add", maker),
                                       ("product.add", {**HONEY, "producerKey": key}), spy=spy)
                if reason:
                    self.assertEqual(result["reason"], reason)
                self.assertNotIn("product.add", spy.calls)  # the dependent product never ran
        # a refusal in the middle of the list also stops it before the later product
        spy = Spy()
        self.rejected(repo, "refused", ("maker.add", MAKER), ("maker.add", {**MAKER, "key": "etto"}),
                      ("product.add", HONEY), spy=spy)
        self.assertNotIn("product.add", spy.calls)

    def test_invalid_or_incomplete_maker_add(self):
        repo = self.repo()
        product = ("product.add", HONEY)
        no_story = {k: v for k, v in MAKER.items() if k != "story"}
        result = self.rejected(repo, "invalid", ("maker.add", no_story), product)  # invalid beats missing
        self.assertEqual(result["problems"], [f"ops[1] 'product.add': product.add.producerKey: {NOT_A_MAKER}"])
        self.rejected(repo, "needs-details", ("maker.add", no_story), ("product.add", {k: v for k, v in HONEY.items()
                                                                                        if k != "producerKey"}))
        bad = {"bad https": {**MAKER, "url": "http://example.com/x"}, "markup": {**MAKER, "story": "<b>Honey</b>"},
               "non-string key": {**MAKER, "key": 5}, "unknown arg": {**MAKER, "owner": "x"}}
        for label, maker in bad.items():
            with self.subTest(label):
                result = self.rejected(repo, "invalid", ("maker.add", maker), ("product.add", HONEY))
                self.assertTrue(any(p.startswith("ops[0] 'maker.add'") for p in result["problems"]), result)
                self.assertTrue(any(p.startswith("ops[1] 'product.add'") and NOT_A_MAKER in p
                                    for p in result["problems"]), result)
        # no provisional key escapes one computation: the same product alone is still invalid, and content is untouched
        self.assertEqual(self.prepare(repo, ("maker.add", no_story))["result"], "needs-details")
        self.rejected(repo, "invalid", product)
        self.assertNotIn(KEY, repo.makers())

    def test_unknown_or_nonexact_key_invalid(self):
        repo = self.repo()
        for key in ("Nobody", "bee happy farm", "Bee  Happy Farm", "Bee Happy Farm ", " Bee Happy Farm",
                    "Ｂee Happy Farm", "", None, 5):
            with self.subTest(key=key):
                result = self.rejected(repo, "invalid", ("maker.add", MAKER), ("product.add", {**HONEY, "producerKey": key}))
                self.assertTrue(all(p.startswith("ops[1] 'product.add'") for p in result["problems"]), result)
        self.assertEqual(self.prepare(repo, ("maker.add", MAKER), ("product.add", {
            k: v for k, v in HONEY.items() if k != "producerKey"}))["result"], "ok")  # absent producerKey works
        self.assertEqual(self.prepare(repo, ("maker.add", MAKER), ("product.add", HONEY))["result"], "ok")

    def test_existing_hidden_and_newly_hidden_maker_refused(self):
        repo = self.repo()
        reason = f"maker {KEY} is hidden; restore the maker first"
        self.assertEqual(self.rejected(repo, "refused", ("maker.add", MAKER), ("maker.hide", {"key": KEY}),
                                       ("product.add", HONEY))["reason"], reason)
        repo.run(("maker.add", MAKER), ("maker.hide", {"key": KEY}))  # hidden in an earlier change
        self.assertEqual(self.rejected(repo, "refused", ("product.add", HONEY))["reason"], reason)
        held = self.rejected(repo, "refused", ("maker.add", {**MAKER, "key": "Fresh Farm", "name": "Fresh Farm"}),
                             ("product.edit", {"id": "photo-product-040", "producerKey": "Fresh Farm"}))
        self.assertIn("Graziers raw-milk cheese recall", held["reason"])  # a held product stays blocked

    def test_second_product_failure_is_atomic(self):
        repo = self.repo()
        self.rejected(repo, "refused", ("maker.add", MAKER), ("product.add", HONEY), ("product.add", HONEY))
        self.rejected(repo, "invalid", ("maker.add", MAKER), ("product.add", HONEY),
                      ("product.add", {**HONEY, "name": "Other honey", "image": "assets/products/no-such-file.webp"}))
        self.assertNotIn(KEY, repo.makers())

    def test_dependent_op_is_rechecked_against_the_real_result(self):
        repo = self.repo()
        spy = Spy(**{"maker.add": lambda content, args, ctx: []})  # accepted, but adds nothing
        result = self.rejected(repo, "invalid", ("maker.add", MAKER), ("product.add", HONEY), spy=spy)
        self.assertEqual(result["problems"], [f"ops[1] 'product.add': product.add.producerKey: {NOT_A_MAKER}"])
        self.assertEqual(spy.calls, ["maker.add"])  # stopped before the product ran


class ApplyAndUndoTests(BatchTestCase):
    def test_prepare_render_apply_recompute_same_records(self):
        repo = self.repo()
        spy = Spy()
        draft = self.prepare(repo, ("maker.add", MAKER), ("product.add", HONEY), spy=spy)["draft"]
        again = self.prepare(repo, ("maker.add", MAKER), ("product.add", HONEY), spy=spy)["draft"]
        self.assertEqual((again["change_id"], again["records"]), (draft["change_id"], draft["records"]))
        self.assertEqual(spy.calls, ["maker.add", "product.add"] * 2)
        rendered = editor.render_draft(draft["change_id"], state=str(repo.state), registry=spy.registry)
        self.assertEqual((rendered["result"], rendered["records"]), ("ok", draft["records"]))
        spy.calls.clear()
        base = self.commits(repo)
        first = editor.apply(draft["change_id"], draft["draft_hash"], state=str(repo.state), registry=spy.registry)
        self.assertEqual((first["result"], first["records"]), ("applied", draft["records"]))
        self.assertEqual(spy.calls, ["maker.add", "product.add"])  # recomputed once, never repeated
        repeat = editor.apply(draft["change_id"], draft["draft_hash"], state=str(repo.state), registry=spy.registry)
        self.assertEqual(repeat["result"], "already-applied")
        self.assertEqual((spy.calls, self.commits(repo)), (["maker.add", "product.add"], base + 1))

    def test_stale_approval_after_another_content_commit(self):
        repo = self.repo()
        draft = self.prepare(repo, ("maker.add", MAKER), ("product.add", HONEY))["draft"]
        repo.run(("maker.edit", {"key": "Etto", "story": "Slow-dried pasta from Paso Robles."}))
        head = repo.head()
        result = editor.apply(draft["change_id"], draft["draft_hash"], state=str(repo.state))
        self.assertEqual(result["result"], "stale", result)
        self.assertEqual((repo.head(), KEY in repo.makers()), (head, False))

    def test_undo_hides_both_and_conflicts_atomically(self):
        repo = self.repo()
        change = repo.run(("maker.add", MAKER), ("product.add", HONEY))["change_id"]
        for label, edit in (("maker", ("maker.edit", {"key": KEY, "story": "Also keeps goats."})),
                            ("product", ("product.edit", {"id": "photo-product-175", "description": "Dark and floral."}))):
            with self.subTest(label):
                other = self.repo()
                change2 = other.run(("maker.add", MAKER), ("product.add", HONEY))["change_id"]
                other.run(edit)
                result = self.rejected(other, "refused", ("history.revert", {"changeId": change2}))
                self.assertTrue(result["reason"].startswith("conflict: "), result)
                self.assertIn(KEY, other.makers())
                self.assertEqual(other.products()[-1]["status"], "active")  # neither half was undone
        repo.run(("history.revert", {"changeId": change}))
        self.assertIs(repo.makers()[KEY].get("hidden"), True)  # hidden, not deleted: history and ids stay
        self.assertEqual(repo.products()[-1]["status"], "hidden")
        self.assertNotIn(KEY.encode(), repo.read("storefront-mockup/producers.json"))
        self.assertNotIn("photo-product-175", [p["id"] for p in repo.catalog()])


class FixtureConversationTests(test_undo.H06TestCase):
    TEXT = "new honey from Bee Happy Farm in Templeton, see example.com/bee-happy"

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state, {**fixture_ops.registry(), **load_registry()})
        self.conv = self.open()
        self.base = self.count()
        calls = (("maker.add", MAKER), ("product.add", HONEY))
        self.interp.mapping.update({self.TEXT: _ops(*calls), "new honey in Templeton": _ops(*calls),
                                    "this honey isn't from Bee Happy Farm in Templeton": _ops(*calls)})

    def makers_file(self):
        return self.content("makers")["makers"]

    def test_named_maker_and_product_proposed_together_and_applied_once(self):
        self.assertEqual(self.say(self.TEXT), "proposed")
        [reply] = self.sent()
        self.assertIn(KEY, reply["text"])
        self.assertEqual((self.commits(), KEY in self.makers_file()), (0, False))  # nothing written before yes
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.product("photo-product-175")["producerKey"], KEY)
        self.assertEqual(self.say("undo"), "proposed")  # undo needs its own approval
        self.sent()
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        self.assertEqual(self.commits(), 2)
        self.assertIs(self.makers_file()[KEY].get("hidden"), True)
        self.assertEqual(self.product("photo-product-175")["status"], "hidden")

    def test_unstated_or_negated_maker_still_asks(self):
        for text in ("new honey in Templeton", "this honey isn't from Bee Happy Farm in Templeton"):
            with self.subTest(text):
                self.assertEqual(self.say(text), "claim-question")
                self.assertIn('You didn\'t say "link" and ', self.replies()[0])
                self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_no_cancels_both(self):
        self.assertEqual(self.say(self.TEXT), "proposed")
        self.sent()
        self.assertEqual(self.say("no"), "rejected")
        self.sent()
        self.assertEqual((self.commits(), KEY in self.makers_file()), (0, False))
        self.assertEqual([d["state"] for d in self.drafts()], ["rejected"])


if __name__ == "__main__":
    unittest.main()
