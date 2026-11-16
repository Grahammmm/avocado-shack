"""AV0022-07 (H06): a bare ``undo`` skips drafts that are themselves undos and takes the change before.

Uses the H06 fixture-adapter setup of ``test_undo_twice`` (temp repo, linked writer worktree, private state dir, fake
previewer). No live state, browser or network.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import unittest

from hass import conversation
from hass.tests.test_undo import H06TestCase

REVERT = "history.revert"


class FlakyEditor(conversation.Editor):
    fail = False

    def apply(self, change_id, draft_hash):
        if self.fail: return {"result": "failed", "reason": "simulated apply failure"}
        return super().apply(change_id, draft_hash)


class BareUndoSkipsUndoTests(H06TestCase):
    def undo_proposal(self, target, waiting=None):
        """A bare undo proposes the revert of ``target``; returns the proposed row."""
        self.assertEqual(self.say("undo"), "proposed")
        [reply] = self.replies()
        prefix = (f"{waiting['summary']} is still waiting for your yes. Reply no {waiting['code']} to drop it.\n\n"
                  if waiting else "")
        self.assertTrue(reply.startswith(prefix + "To undo that, I'd change it back:\nHere's the change I'd make:"), reply)
        row = self.drafts()[-1]
        self.assertEqual(json.loads(row["ops_json"]), [{"op": REVERT, "args": {"changeId": target["change_id"]}}])
        return row

    def approve(self):
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        return self.drafts()[-1]

    def test_second_undo_drafts_the_change_before(self):
        a, b = self.apply("desc"), self.apply("hours")
        self.undo_proposal(b)
        self.approve()
        self.undo_proposal(a)  # the applied undo of B is skipped, B itself is reverted
        self.approve()
        self.assertEqual([d["state"] for d in self.drafts()], ["reverted", "reverted", "verified", "verified"])
        rows, commits = len(self.drafts()), self.commits()
        self.assertEqual(self.say("undo"), "no-target")
        self.assertEqual(self.replies(), ["There's nothing to undo."])
        self.assertEqual((len(self.drafts()), self.commits()), (rows, commits))

    def test_only_an_undo_left_is_nothing_to_undo(self):
        a = self.apply("desc")
        self.undo_proposal(a)
        self.approve()
        rows, commits = len(self.drafts()), self.commits()
        for text in ("undo", "Undo.", "UNDO!"):
            with self.subTest(text):
                self.assertEqual(self.say(text), "no-target")
                self.assertEqual(self.replies(), ["There's nothing to undo."])
        self.assertEqual((len(self.drafts()), self.commits()), (rows, commits))

    def test_undo_naming_an_undo_is_still_refused(self):
        a = self.apply("desc")
        self.undo_proposal(a)
        u = self.approve()
        self.assertEqual(self.say(f"undo {u['code']}"), "not-drafted")
        self.assertEqual(self.replies(),
                         ["I couldn't undo that, so nothing changed. Could you say it another way?"])
        self.assertEqual([d["state"] for d in self.drafts()], ["reverted", "verified"])

    def test_proposed_undo_does_not_change_the_choice(self):
        self.apply("desc")
        b = self.apply("hours")
        first = self.undo_proposal(b)
        rows = len(self.drafts())
        self.assertEqual(self.undo_proposal(b)["row_id"], first["row_id"])  # same proposal, no second draft
        self.assertEqual((len(self.drafts()), self.commits()), (rows, 2))

    def test_failed_apply_is_skipped(self):
        self.editor = FlakyEditor(self.repo.state, self.editor.registry)
        self.conv = self.open()
        a = self.apply("desc")
        self.editor.fail = True
        b = self.apply("hours")
        self.assertEqual((b["state"], b["commit"]), ("failed", None))
        self.editor.fail = False
        waiting = self.drafts()[-1]  # a failed apply leaves a fresh proposal waiting
        self.assertEqual((waiting["state"], waiting["summary"]), ("proposed", b["summary"]))
        self.undo_proposal(a, waiting=waiting)
        self.assertEqual(self.drafts()[-2], waiting)


class IsUndoTests(unittest.TestCase):
    def test_only_a_non_empty_all_revert_list_is_an_undo(self):
        rev = {"op": REVERT, "args": {"changeId": "chg-1"}}
        cases = {json.dumps([rev]): True, json.dumps([rev, rev]): True, json.dumps([]): False,
                 json.dumps([rev, {"op": "store.set_hours", "args": {}}]): False, json.dumps({"op": REVERT}): False,
                 json.dumps([REVERT]): False, '[{"op": "history.revert"': False, "": False, None: False,
                 "[" * 100000 + "]" * 100000: False}
        for ops_json, expected in cases.items():
            with self.subTest(str(ops_json)[:40]):
                self.assertIs(conversation._is_undo({"ops_json": ops_json}), expected)


if __name__ == "__main__":
    unittest.main()
