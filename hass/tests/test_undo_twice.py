"""H06 tests: ``history.revert`` refuses to undo an undo, so the original's ``revertedBy`` stays set (RF1650-3).

The store cases use a throwaway StoreRepo (temp repo + temp state dir, fixture content only, production ops); the
conversation case uses the H06 fixture-adapter setup. No live state, browser or network.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import os
import unittest

from hass import editor
from hass.tests.test_store_ops import REVERT, StoreTestCase, _req
from hass.tests.test_undo import H06TestCase

PRODUCTS = "hass/content/products.json"
EDIT = ("product.edit", {"id": "photo-product-001", "description": "Buttery and new."})


class UndoTwiceTests(StoreTestCase):
    def setUp(self):
        self.r = self.repo()
        self.a = self.r.run(EDIT)["change_id"]
        self.u = self.r.run((REVERT, {"changeId": self.a}))["change_id"]

    def draft(self, change_id):
        return self.r.state / "drafts" / f"{change_id}.json"

    def reverted_by(self, change_id):
        return editor.show(change_id, state=str(self.r.state))["change"].get("revertedBy")

    def revert(self, change_id):
        return self.r.prepare(_req((REVERT, {"changeId": change_id})))

    def assert_refused(self, change_id, reason):
        """Revert is refused with exactly ``reason``; nothing drafted, content and history unchanged."""
        r = self.r
        drafts, content, head = r.drafts(), r.read(PRODUCTS), r.head()
        result = self.revert(change_id)
        self.assertEqual((result["result"], result.get("reason")), ("refused", reason), result)
        self.assertNotIn("Traceback", json.dumps(result))
        self.assertEqual((r.drafts(), r.read(PRODUCTS), r.head(), r.status()), (drafts, content, head, ""))
        self.assertEqual((self.reverted_by(self.a), self.reverted_by(self.u)), (self.u, None))

    def test_undo_of_an_undo_is_refused(self):
        self.assert_refused(self.u, f"{self.u} is an undo; to bring the change back, ask for it again")

    def test_original_still_reports_already_undone(self):
        self.assert_refused(self.a, f"{self.a} was already undone by {self.u}")

    def test_any_revert_call_in_the_draft_makes_it_an_undo(self):
        path = self.draft(self.u)
        draft = json.loads(path.read_text("utf-8"))
        path.write_text(json.dumps({**draft, "ops": [{"op": "store.set_hours", "args": {}}, *draft["ops"]]}), "utf-8")
        self.assert_refused(self.u, f"{self.u} is an undo; to bring the change back, ask for it again")

    def test_unreadable_draft_is_refused(self):
        cases = {"truncated": b'{"ops": [', "empty": b"", "not utf-8": b"\xff\xfe{", "top list": b"[]",
                 "ops a string": b'{"ops": "history.revert"}', "ops missing": b"{}",
                 "op not a dict": b'{"ops": [["history.revert"]]}'}
        for name, data in cases.items():
            with self.subTest(name):
                self.draft(self.u).write_bytes(data)
                self.assert_refused(self.u, f"{self.u} draft is unreadable")

    def test_directory_at_draft_path_is_unreadable(self):
        path = self.draft(self.u)
        path.unlink()
        path.mkdir()
        self.assert_refused(self.u, f"{self.u} draft is unreadable")

    def test_symlinked_draft_is_never_read(self):
        path = self.draft(self.u)
        target = self.r.state / "elsewhere.json"
        target.write_bytes(path.read_bytes())
        for name, dest in (("to a real draft", target), ("dangling", self.r.state / "missing.json")):
            with self.subTest(name):
                path.unlink()
                os.symlink(dest, path)
                self.assert_refused(self.u, f"{self.u} draft is unreadable")


def _description(repo):
    return next(p for p in json.loads(repo.read(PRODUCTS))["products"] if p["id"] == EDIT[1]["id"])["description"]


class RevertStillWorksTests(StoreTestCase):
    def test_normal_change_reverts_as_today(self):
        r = self.repo()
        before = _description(r)
        a = r.run(EDIT)["change_id"]
        u = r.run((REVERT, {"changeId": a}))["change_id"]
        self.assertEqual(_description(r), before)
        self.assertEqual(editor.show(a, state=str(r.state))["change"]["revertedBy"], u)

    def test_missing_draft_keeps_todays_behaviour(self):
        r = self.repo()
        before = _description(r)
        a = r.run(EDIT)["change_id"]
        (r.state / "drafts" / f"{a}.json").unlink()
        result = r.prepare(_req((REVERT, {"changeId": a})))
        self.assertEqual(result["result"], "ok", result)
        self.assertEqual(r.apply(result["draft"])["result"], "applied")
        self.assertEqual(_description(r), before)


class ConversationUndoTwiceTests(H06TestCase):
    def test_second_undo_is_refused_without_a_proposal(self):
        a = self.apply("desc")
        self.assertEqual(self.say("undo"), "proposed")
        self.replies()
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        u = self.drafts()[-1]
        rows, commits = len(self.drafts()), self.commits()
        self.assertEqual(self.say("undo"), "no-target")
        self.assertEqual(self.replies(), ["There's nothing to undo."])
        self.assertEqual((len(self.drafts()), self.commits()), (rows, commits))
        self.assertEqual([d["state"] for d in self.drafts()], ["reverted", "verified"])
        self.assertEqual(editor.show(a["change_id"], state=str(self.repo.state))["change"]["revertedBy"],
                         u["change_id"])


if __name__ == "__main__":
    unittest.main()
