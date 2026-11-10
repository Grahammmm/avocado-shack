"""RF2135-11: item.hide refuses permanent deletion from the owner's own words, not only from the optional reason slot."""

import copy
import types
import unittest

from hass.content_model import REPO_ROOT, load_and_validate
from hass.skills import items as it
from hass.skills.testkit import load_rows, run_case_row
from hass.tests.test_skills_items import CONTENT, SITE, SKILLS

HIDE = SKILLS["item.hide"]
ID = "photo-product-055"


def ctx_for(*texts, content=None):
    return types.SimpleNamespace(today="2026-11-08", texts=list(texts), **({"content": content} if content else {}))


def row(rid, texts, kind):
    reply = {"skill": "item.hide", "slots": {"items": [ID]}}
    return {"id": rid, "kind": kind, "version": 1, "texts": texts, "replies": [reply] + [{"question": "ok?"}] * (len(texts) - 1),
            "expect": {"disposition": "unsupported", "reply_contains": "don't delete anything for good", "skill": "item.hide"}}


class PermanentIntent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = load_and_validate(CONTENT, SITE)

    def refuses(self, slots, ctx):
        with self.assertRaises(it.Refusal) as caught:
            HIDE.plan(slots, ctx)
        self.assertEqual(caught.exception.reply, it.NOT_DELETED)
        self.assertEqual(caught.exception.backlog, "policy")

    def test_owner_permanent_delete_refuses_when_reason_missing_or_innocuous(self):
        for extra in ({}, {"reason": ""}, {"reason": "slow seller"}):
            slots = {"items": [ID], **extra}
            before = copy.deepcopy(slots)
            self.refuses(slots, ctx_for("delete Cashews forever", content=self.content))
            self.assertEqual(slots, before)

    def test_reason_only_legacy_call_keeps_its_refusal(self):
        self.refuses({"items": [ID], "reason": "delete forever"}, types.SimpleNamespace(today="2026-11-08"))
        for slots in ({"items": [ID], "reason": "slow seller"}, {"items": [ID]}):
            self.assertEqual(HIDE.plan(slots, ctx_for("delete the cashews", content=self.content)),
                             [{"op": "product.hide", "args": {"id": ID}}])

    def test_affirmative_permanent_delete_variants_and_negations(self):
        for text in ("Delete it FOREVER", "erase it for ever", "wipe the cashews  for good", "please delete it permanently",
                     "deleting it for good"):
            self.refuses({"items": [ID]}, ctx_for(text))
        for text in ("don't delete it forever, just hide it", "Don’t delete it for good", "never delete it permanently",
                     "hide it for the winter", "stop selling it for good", "hide it permanently", "delete the cashews",
                     "hide the Forever Cashews"):
            self.assertEqual(HIDE.plan({"items": [ID]}, ctx_for(text)), [{"op": "product.hide", "args": {"id": ID}}], text)

    def test_request_latest_explicit_instruction_wins(self):
        ok = [{"op": "product.hide", "args": {"id": ID}}]
        self.assertEqual(HIDE.plan({"items": [ID]}, ctx_for("delete it forever", "actually just hide it instead")), ok)
        self.refuses({"items": [ID]}, ctx_for("just hide it", "no, delete it for good"))
        self.assertEqual(HIDE.plan({"items": [ID]}, ctx_for("hide the cashews")), ok)

    def test_real_dispatch_refuses_logs_policy_and_never_prepares_hide(self):
        r = row("perm-1", ["delete the cashews forever"], "refuse")  # the model omits its optional reason
        res = run_case_row(r, SKILLS, HIDE)
        self.assertEqual(res.problems, [])

    def test_subsequent_explicit_hide_uses_normal_approval_and_undo(self):
        rows = load_rows(REPO_ROOT / HIDE.cases)
        normal = next(r for r in rows if r["id"] == "hide-2-cashews")  # propose, yes, undo through the existing harness
        self.assertEqual(run_case_row(normal, SKILLS, HIDE).problems, [])


if __name__ == "__main__":
    unittest.main()
