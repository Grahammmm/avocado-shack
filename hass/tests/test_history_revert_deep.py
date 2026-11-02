"""H06 tests: ``history.revert`` treats a change or draft record nested too deep as unreadable, never a RecursionError.

Each case applies a real store change in a throwaway StoreRepo (temp repo + temp state dir, fixture content only),
then replaces ``<state>/changes/<id>.json`` or ``<state>/drafts/<id>.json`` with deeply nested JSON (RF1520-10).
Run: python3 -m unittest hass.tests.test_history_revert_deep -v
"""

import json
import types
import unittest

from hass.ops.history import _draft_ops
from hass.tests.test_store_ops import NEW_HOURS, REVERT, SET_HOURS, StoreTestCase, _req

STORE = "hass/content/store.json"
DEEP = {"list": b"[" * 100000, "object": b'{"ops": ' * 100000, "closed": b"[" * 100000 + b"]" * 100000}


class DeepRecordTests(StoreTestCase):
    def setUp(self):
        self.r = self.repo()
        self.original = self.r.store()["hours"]
        self.change_id = self.r.run((SET_HOURS, {"hours": NEW_HOURS}))["change_id"]
        self.record = self.r.state / "changes" / f"{self.change_id}.json"
        self.draft = self.r.state / "drafts" / f"{self.change_id}.json"

    def changes(self):
        return {p.name: p.read_bytes() for p in sorted((self.r.state / "changes").iterdir())}

    def assert_refused(self, reason):
        """Undo is refused with exactly ``reason``; nothing drafted, content, history and change log byte-identical."""
        r = self.r
        drafts, content, head, changes = r.drafts(), r.read(STORE), r.head(), self.changes()
        draft = self.draft.read_bytes()
        result = r.prepare(_req((REVERT, {"changeId": self.change_id})))
        self.assertEqual((result["result"], result.get("reason")), ("refused", reason), str(result)[:200])
        self.assertNotIn("RecursionError", json.dumps(result))
        self.assertEqual((r.drafts(), r.read(STORE), r.head(), r.status()), (drafts, content, head, ""))
        self.assertEqual((self.changes(), self.draft.read_bytes()), (changes, draft))
        self.assertEqual(r.store()["hours"], NEW_HOURS)

    def test_too_deep_change_record_is_unreadable(self):
        for name, data in DEEP.items():
            with self.subTest(name):
                self.record.write_bytes(data)
                self.assert_refused(f"{self.change_id} record is unreadable")

    def test_too_deep_draft_is_false(self):
        ctx = types.SimpleNamespace(state_dir=str(self.r.state))
        self.assertIsInstance(_draft_ops(ctx, self.change_id), list)  # the real draft still reads
        for name, data in DEEP.items():
            with self.subTest(name):
                self.draft.write_bytes(data)
                self.assertIs(_draft_ops(ctx, self.change_id), False)

    def test_too_deep_draft_takes_the_unreadable_draft_path(self):
        for name, data in DEEP.items():
            with self.subTest(name):
                self.draft.write_bytes(data)
                self.assert_refused(f"{self.change_id} draft is unreadable")

    def test_deep_but_parseable_record_is_malformed_not_unreadable(self):
        # nesting json can read keeps its existing shape check: only the parse failure is new
        self.record.write_bytes(b"[" * 50 + b"]" * 50)
        self.assert_refused(f"{self.change_id} record is malformed")

    def test_normal_revert_unchanged(self):
        self.r.run((REVERT, {"changeId": self.change_id}))
        self.assertEqual(self.r.store()["hours"], self.original)
        self.assertEqual(json.loads(self.record.read_text("utf-8"))["revertedBy"][:4], "chg-")


if __name__ == "__main__":
    unittest.main()
