"""RF0035-11: stock.checked keeps its "Which one is right?" request when one product is named in two availability lists.

The plan raises the existing TWICE refusal as a question; the real dispatcher then retains the validated lists, day and
request texts, and the owner's next reply is read against them. Only a corrected NONEMPTY list replaces a bucket: an
empty list is rejected and an omitted one keeps the old list, so nothing here clears a bucket or chooses an answer.
Run: python3 -B -m unittest hass.tests.test_stock_checked_conflict -v
"""

import copy
import itertools
import json
import types
import unittest
from datetime import timedelta

from hass.skills import openreq, stock
from hass.tests.test_conversation import CHAT
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import SkillCase

EGGS, HASS, LEMONS, HONEY = "photo-product-024", "photo-product-001", "photo-product-017", "photo-product-042"
DAY = "2026-11-01"  # SkillCase's clock is Monday 2026-11-02 09:00 PST: yesterday is inside the check-day window
QUESTION = stock.TWICE.format(name="Cal Poly eggs")
BUCKETS = {"yes": "in", "limited": "limited", "no": "out"}


def _ctx():
    products = [{"id": pid, "name": name, "status": "active"}
                for pid, name in ((EGGS, "Cal Poly eggs"), (HASS, "Hass avocado"), (LEMONS, "Lemons"), (HONEY, "Honey"))]
    return types.SimpleNamespace(today="2026-11-08", content=types.SimpleNamespace(products=products, store={}))


class PlanBranches(unittest.TestCase):
    def test_cross_bucket_repeat_is_a_question_without_any_plan(self):
        for first, second in itertools.permutations(("in", "limited", "out"), 2):
            slots = {first: [EGGS, HONEY], second: [LEMONS, EGGS]}
            if first == "in":  # one repeated identity among valid neighbours, whichever buckets hold it
                slots = {first: [HASS, EGGS], second: [EGGS, LEMONS]}
            ctx = _ctx()
            before = copy.deepcopy((slots, vars(ctx.content)))
            with self.subTest(first=first, second=second):
                with self.assertRaises(stock.Refusal) as caught:
                    stock.STOCK_CHECKED.plan(slots, ctx)
                self.assertEqual(caught.exception.reply, QUESTION)
                self.assertEqual(caught.exception.kind, "question")
                self.assertIsInstance(caught.exception, ValueError)
                self.assertEqual((slots, vars(ctx.content)), before)

    def test_unrelated_stock_refusals_are_not_promoted(self):
        def ctx_with(**fields):
            ctx = _ctx()
            ctx.content.products[0].update(fields)
            return ctx
        controls = [
            ({"in": [EGGS, EGGS]}, _ctx()),  # the same list twice stays a plain refusal
            ({"in": [""]}, _ctx()),  # malformed list
            ({"in": [EGGS]}, ctx_with(status="hidden")),
            ({"in": [EGGS]}, ctx_with(status="held")),
            ({"day": "2026-11-09", "in": [EGGS]}, _ctx()),  # future day
            ({"day": "2026-10-01", "in": [EGGS]}, _ctx()),  # more than a week ago
            ({"day": "not a day", "in": [EGGS]}, _ctx())]
        for slots, ctx in controls:
            with self.subTest(slots=slots):
                with self.assertRaises(stock.Refusal) as caught:
                    stock.STOCK_CHECKED.plan(slots, ctx)
                self.assertEqual(caught.exception.kind, "refuse")
        done = _ctx()
        done.content.store = {"selection_checked_on": "2026-11-08"}
        done.content.products[0].update(available="yes", available_on="2026-11-08")
        with self.assertRaises(stock.Refusal) as caught:
            stock.STOCK_CHECKED.plan({"in": [EGGS]}, done)
        self.assertEqual((caught.exception.reply, caught.exception.kind), (stock.DONE_TODAY, "refuse"))
        with self.assertRaises(stock.Refusal) as caught:
            stock.STOCK_CLEAR.plan({"items": [EGGS]}, _ctx())
        self.assertEqual(caught.exception.kind, "refuse")


class RealDispatcherChecked(SkillCase):
    """The PRODUCTION stock.checked through the real Conversation, dispatcher and Editor on the throwaway shop."""
    SKILLS = (stock.STOCK_CHECKED,)

    def setUp(self):
        super().setUp()
        self.edit_products(lambda p: p.update(status="active"), EGGS, LEMONS)  # both known records are active

    def edit_products(self, change, *pids):
        path = self.repo.wt / "hass" / "content" / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        for product in doc["products"]:
            if product["id"] in pids:
                change(product)
        path.write_text(json.dumps(doc), "utf-8")
        git(self.repo.wt, "commit", "-qam", "seed products")  # the writer worktree is clean at each draft
        self.base = self.count()

    def tell(self, text, slots, *, calls=False):
        call = {"skill": "stock.checked", "slots": slots}
        return self.raw(text, {"calls": [call]} if calls else call)

    def raw(self, text, reply):
        self.script(text, reply)
        disposition = self.say(text)
        return disposition, "\n".join(self.replies())

    def conflict(self, text="eggs are in and out, checked yesterday", *, calls=False, pid=None):
        slots = {"day": DAY, "in": [EGGS], "out": [EGGS]}
        self.script(text, {"calls": [{"skill": "stock.checked", "slots": slots}]} if calls
                    else {"skill": "stock.checked", "slots": slots})
        self.assertEqual(self.say(text, **({"pid": pid} if pid else {})), "question")
        req = self.live()
        self.assertIsNotNone(req)  # the clarification must retain its entire request
        self.assertEqual((req["skill"], req["slots"], req["texts"], req["asked_slot"], req["question"]),
                         ("stock.checked", slots, [text], None, QUESTION))
        self.assertEqual(self.replies(), [QUESTION])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        return req

    def ops(self):
        return [(o["op"], o["args"]) for o in json.loads(self.drafts()[-1]["ops_json"])]

    def test_real_checked_conflict_retains_request_and_snapshot(self):
        req = self.conflict()
        self.conv = self.open()  # prove persisted context, not just in-memory state
        corrected = {"out": [LEMONS]}
        self.assertEqual(self.tell("the lemons are out", corrected)[0], "proposed")
        text, recent = self.asked[-1]
        self.assertEqual((text, recent), ("the lemons are out", {"skill": "stock.checked", "slots": req["slots"],
                                                                 "question": QUESTION, "earlier": req["texts"]}))
        self.assertEqual(self.live()["request_id"], req["request_id"])
        self.assertEqual(self.live()["slots"], {"day": DAY, "in": [EGGS], "out": [LEMONS]})
        self.nothing_written()

    def prepares_exact_check(self, calls):  # calls: the conflict arrives as a one-call envelope; the correction is a single reply
        req = self.conflict(calls=calls)
        disposition, reply = self.tell("the lemons are out", {"out": [LEMONS]})
        self.assertEqual(self.asked[-1][1]["slots"], req["slots"])  # the model saw the retained lists and day
        self.assertEqual(disposition, "proposed", reply)
        self.assertEqual(self.live()["request_id"], req["request_id"])
        self.assertEqual(self.live()["slots"], {"day": DAY, "in": [EGGS], "out": [LEMONS]})
        self.assertEqual(len(self.drafts()), 1)  # exactly one ordinary draft, the check and its words together
        self.assertEqual(self.ops(), [("store.confirm_selection", {"date": DAY, "yes": [EGGS], "no": [LEMONS]})])
        self.nothing_written()  # the owner's own coded yes still decides
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(self.commits(), 1)

    def test_nonempty_corrected_bucket_prepares_exact_check(self):
        self.prepares_exact_check(calls=False)

    def test_nonempty_corrected_bucket_prepares_exact_check_after_envelope_conflict(self):
        self.prepares_exact_check(calls=True)

    def test_empty_null_and_omitted_bucket_cannot_silently_resolve(self):
        for label, slots in (("empty", {"out": []}), ("null", {"out": None}), ("omitted", {}), ("bare day", {"day": DAY})):
            with self.subTest(label):
                self.conv.requests.close_live(CHAT, self.now)
                req = self.conflict(text=f"eggs in and out {label}")
                disposition, reply = self.tell(f"still unsure {label}", slots)
                self.assertNotEqual(disposition, "proposed", reply)
                self.assertEqual(self.live()["request_id"], req["request_id"])
                self.assertEqual(self.live()["slots"], req["slots"])  # the contradiction is neither cleared nor dropped
                self.assertEqual(self.drafts(), [])
                self.nothing_written()
        self.say("yes")  # a bare yes chooses nothing
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        self.assertEqual(self.raw("never mind", {"cancel": True})[0], "cancelled")
        self.assertIsNone(self.live())
        self.assertEqual(self.tell("checked, lemons out", {"out": [LEMONS]})[0], "proposed")  # a fresh request starts empty
        self.assertEqual(self.live()["slots"], {"out": [LEMONS]})
        self.nothing_written()

    def test_repeat_limit_and_cancel_leave_no_partial_check(self):
        req = self.conflict()
        for number in range(2, openreq.MAX_UNRESOLVED + 1):
            disposition, reply = self.tell(f"unsure {number}", {"skill": "stock.checked", "slots": req["slots"]})
            self.assertEqual((disposition, reply), ("question", QUESTION))
            self.assertEqual((self.live()["request_id"], self.live()["slots"], self.live()["asks"]),
                             (req["request_id"], req["slots"], number))
        self.conv.outbox.strict = False  # the stuck example is the skill's first trigger, which says "selection"; not under test here
        self.assertEqual(self.tell("unsure again", {"skill": "stock.checked", "slots": req["slots"]})[0], "backlog")
        self.assertIsNone(self.live())
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        self.conflict("eggs both in and out, again")
        self.assertEqual(self.raw("never mind", {"cancel": True})[0], "cancelled")
        self.assertIsNone(self.live())
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_duplicate_and_expired_conflict_do_not_continue(self):
        req = self.conflict(pid="conflict-message")
        self.assertEqual(self.say(req["texts"][0], pid="conflict-message"), "duplicate")
        self.assertEqual(self.live(), req)
        self.now += timedelta(minutes=openreq.TTL_MINUTES + 1)
        self.assertEqual(self.tell("lemons out", {"out": [LEMONS]})[0], "proposed")  # a fresh, complete request
        self.assertNotEqual(self.live()["request_id"], req["request_id"])
        self.assertEqual(self.live()["slots"], {"out": [LEMONS]})  # nothing carried over from the expired conflict
        self.assertIsNone(self.asked[-1][1])
        self.assertEqual(self.ops(), [("store.confirm_selection", {"no": [LEMONS]})])
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
