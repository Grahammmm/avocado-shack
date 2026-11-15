"""HASS-SHELFCHECK-FLOW-1 tests: marking a product sold out (or back) without today's shelf check is one plain question, and
the owner's yes drafts the original change with the check, in the same flow.

Conversation runs on the H02 throwaway repo with the PRODUCTION op registry and an injected clock; the interpreter is a
scripted stand-in that returns what a correct model returns for each text (no model, no socket). Every test also checks the
rule that did not change: an unconfirmed message never writes anything (no writer commit, no approval row), and only the owner's
own yes marks the check.
Run: python3 -B -m unittest hass.tests.test_shelf_check_flow -v
"""

import json
import unittest
from datetime import timedelta

from hass import conversation, editor as editor_mod
from hass.tests.test_conversation import STRANGER, ConversationTestCase, _ops
from hass.tests.test_editor import git

HASS = "photo-product-001"  # "Hass avocado"
SOLD_OUT = "mark the Hass avocado sold out"
BACK_IN = "the Hass avocado is back"
OTHER = "also the oranges are low"
HOURS = "change the hours to nine to five"
Q_SHELF = "Before I change that, is the shelf list right for today? Reply yes if it is, or tell me what is different."
Q_REPORT = "Is the shelf list right for today? Reply yes if it is, or tell me what is different."
NO_REPLY = "Okay, nothing was changed. Tell me what is different on the shelf list and I will draft that."
SOLD = ("product.set_availability", {"id": HASS, "available": "no"})
LOW = ("product.set_availability", {"id": "photo-product-016", "available": "limited"})
IN = ("product.set_availability", {"id": HASS, "available": "yes"})
HOURS_OP = ("store.set_hours", {"hours": ["Monday-Friday 9am-5pm"]})
TODAY = "2026-11-02"  # the test clock T0 is Monday 2026-11-02 09:00 PST


class Clocked(conversation.Editor):
    """The production registry, with the editor's clock the test clock."""

    def __init__(self, state, clock):
        super().__init__(state)
        self.clock = clock

    def prepare(self, ops):
        return editor_mod.prepare({"ops": ops}, state=self.state, registry=self.registry, now=self.clock())

    def apply(self, change_id, draft_hash):
        return editor_mod.apply(change_id, draft_hash, state=self.state, registry=self.registry, now=self.clock())


class Scripted(conversation.FixtureInterpreter):
    def __init__(self, mapping, asked):
        super().__init__(mapping)
        self.asked = asked

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        self.asked.append((text, recent))
        return super().interpret(text, pending)


class ShelfCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.asked = []
        self.interp = Scripted({
            SOLD_OUT: _ops(SOLD), BACK_IN: _ops(IN), OTHER: _ops(LOW), HOURS: _ops(HOURS_OP),
            "and the oranges too": _ops(SOLD, LOW), "oranges are low": _ops(LOW), "bananas": {"question": "Which bananas?"}},
            self.asked)
        self.editor = Clocked(self.repo.state, lambda: self.now)
        self.conv = self.open()

    def store_file(self):
        return self.repo.wt / "hass" / "content" / "store.json"

    def checked(self, day):
        path = self.store_file()
        path.write_text(json.dumps({**json.loads(path.read_text("utf-8")), "selection_checked_on": day}), "utf-8")
        git(self.repo.wt, "commit", "-qam", f"checked {day}")  # the writer worktree is clean at each draft
        self.base = self.count()

    def store(self):
        return json.loads(self.store_file().read_text("utf-8"))

    def product(self, pid=HASS):
        products = json.loads((self.repo.wt / "hass" / "content" / "products.json").read_text("utf-8"))["products"]
        return next(p for p in products if p["id"] == pid)

    def open_asks(self):  # SKILLS-FW-3: the one open-request store (was the open_asks table)
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_requests'").fetchone(): return []
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM open_requests")]

    def nothing_written(self):
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)

    def ask_and_get_question(self, text=SOLD_OUT, waiting=0):
        self.assertEqual(self.say(text), "question")
        self.assertEqual(self.replies(), [Q_SHELF])
        self.assertEqual(len(self.drafts()), waiting)
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)


class AskThenYesTests(ShelfCase):
    def test_no_check_asks_one_plain_question_and_writes_nothing(self):
        self.ask_and_get_question()
        for banned in ("selection", "not drafted", "Not drafted", HASS):
            self.assertNotIn(banned, Q_SHELF)
        self.assertEqual(len(self.open_asks()), 1)  # the same open-request store the hike flow uses

    def test_yes_drafts_the_check_and_the_original_change_together_and_still_needs_approval(self):
        self.ask_and_get_question()
        self.now += timedelta(minutes=2)
        self.assertEqual(self.say("yes"), "proposed")
        [reply] = self.replies()
        [draft] = self.drafts()
        self.assertEqual(draft["state"], "proposed")
        self.assertEqual([c["op"] for c in json.loads(draft["ops_json"])], ["store.confirm_selection", "product.set_availability"])
        self.assertIn("Got it. This draft also records that the shelf list was checked today.", reply)
        self.assertIn("the shelf check: from nothing to", reply)
        self.assertIn("the shelf word: from nothing to Sold out", reply)
        self.assertIn("Reply yes to save it, or no to cancel", reply)
        self.assertEqual(self.open_asks(), [])
        self.nothing_written()  # the draft is not applied: his normal approval is still needed
        self.assertNotIn("selection_checked_on", self.store())
        self.assertNotIn("available", self.product())

    def test_the_approval_applies_both_dated_today_and_it_is_logged(self):
        self.ask_and_get_question()
        self.say("yes")
        self.replies()
        [draft] = self.drafts()
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.store()["selection_checked_on"], TODAY)
        self.assertEqual((self.product()["available"], self.product()["available_on"]), ("no", TODAY))
        self.assertEqual(self.drafts()[0]["state"], "applied")  # the draft row is the log of who approved what
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 1)
        self.assertEqual(draft["code"], self.drafts()[0]["code"])

    def test_back_in_stock_is_the_same_flow(self):
        self.assertEqual(self.say(BACK_IN), "question")
        self.assertEqual(self.replies(), [Q_SHELF])
        self.assertEqual(self.say("yes"), "proposed")
        self.assertEqual([c["op"] for c in json.loads(self.drafts()[0]["ops_json"])], ["store.confirm_selection", "product.set_availability"])

    def test_several_products_in_one_message_are_one_question_and_one_draft(self):
        self.interp.mapping["both"] = _ops(SOLD, LOW)
        self.assertEqual(self.say("both"), "question")
        self.assertEqual(self.say("yes"), "proposed")
        self.assertEqual(len(json.loads(self.drafts()[0]["ops_json"])), 3)
        self.assertEqual(len(self.drafts()), 1)


class StaleCheckTests(ShelfCase):
    def test_a_check_older_than_today_is_treated_the_same(self):
        self.checked("2026-10-30")
        self.ask_and_get_question()
        self.assertEqual(self.say("yes"), "proposed")
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.store()["selection_checked_on"], TODAY)
        self.assertEqual(self.product()["available_on"], TODAY)

    def test_a_check_more_than_a_week_old_is_treated_the_same(self):
        self.checked("2026-09-01")
        self.ask_and_get_question()
        self.assertEqual(self.say("yes"), "proposed")

    def test_a_check_dated_after_today_says_the_date_looks_wrong_and_asks_nothing(self):
        self.checked("2026-11-05")
        self.assertEqual(self.say(SOLD_OUT), "not-drafted")
        self.assertEqual(self.replies(), [conversation.SHELF_CLOCK])
        self.assertEqual(self.open_asks(), [])
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.drafts(), [])
        self.nothing_written()


class SameValueNextDayTests(ShelfCase):
    def test_sold_out_yesterday_and_sold_out_again_today_goes_through_the_shelf_check(self):
        self.checked(TODAY)
        self.say(SOLD_OUT)
        self.say("yes")
        self.assertEqual(self.product()["available_on"], TODAY)
        self.now += timedelta(days=1)  # next day: the word and its date are both yesterday's
        self.replies()
        self.assertEqual(self.say(SOLD_OUT), "question")
        self.assertEqual(self.replies(), [Q_SHELF])
        self.assertEqual(self.say("yes"), "proposed")
        self.assertEqual([c["op"] for c in json.loads(self.drafts()[-1]["ops_json"])],
                         ["store.confirm_selection", "product.set_availability"])
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.product()["available_on"], "2026-11-03")
        self.assertEqual(self.store()["selection_checked_on"], "2026-11-03")


class TodaysCheckTests(ShelfCase):
    def test_with_todays_check_the_change_is_drafted_at_once_with_no_question(self):
        self.checked(TODAY)
        draft, reply = self.propose(SOLD_OUT)
        self.assertEqual([c["op"] for c in json.loads(draft["ops_json"])], ["product.set_availability"])
        self.assertNotIn("shelf list", reply)
        self.assertEqual(self.open_asks(), [])
        self.nothing_written()

    def test_a_refusal_that_is_not_the_check_is_unchanged(self):
        self.checked(TODAY)
        self.say(SOLD_OUT)
        self.replies()
        self.say("yes")
        self.replies()
        self.assertEqual(self.say(SOLD_OUT), "not-drafted")  # already sold out
        [reply] = self.replies()
        self.assertEqual(reply, "That's already how it is, so nothing changed.")
        self.assertEqual(self.open_asks(), [])


class OnlyTheOwnerTests(ShelfCase):
    def test_a_stranger_saying_yes_does_nothing_and_the_owners_yes_still_works(self):
        self.ask_and_get_question()
        self.assertEqual(self.say("yes", sender=STRANGER), "ignored")
        self.assertEqual(self.say("yes", chat="chat-fixture-group", sender=STRANGER), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        self.assertEqual(self.say("yes"), "proposed")

    def test_a_stranger_asking_for_the_change_gets_no_question_and_opens_nothing(self):
        self.assertEqual(self.say(SOLD_OUT, sender=STRANGER), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.open_asks(), [])
        self.assertEqual(self.say("yes"), "no-target")

    def test_the_owners_own_message_echoed_back_is_not_a_yes(self):
        self.ask_and_get_question()
        self.assertEqual(self.say("yes", from_me=True), "echo")
        self.assertEqual(self.drafts(), [])
        self.nothing_written()


class OtherAnswersTests(ShelfCase):
    def test_no_changes_nothing_closes_the_question_and_cancels_no_waiting_draft(self):
        self.checked(TODAY)
        waiting, _ = self.propose(HOURS)
        self.checked_ok = True
        self.checked("2026-10-31")  # make the next change need the check again
        self.assertEqual(self.say(SOLD_OUT), "question")
        self.replies()
        self.assertEqual(self.say("no"), "shelf-no")
        self.assertEqual(self.replies(), [NO_REPLY])
        self.assertEqual(self.open_asks(), [])
        self.assertEqual([(d["code"], d["state"]) for d in self.drafts()], [(waiting["code"], "proposed")])  # not cancelled
        self.assertEqual(self.say("yes"), "approved")  # the old yes meaning is back: it is the waiting draft's
        self.assertNotIn("available", self.product())

    def test_no_then_yes_marks_nothing(self):
        self.ask_and_get_question()
        self.assertEqual(self.say("no"), "shelf-no")
        self.replies()
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_a_yes_does_not_approve_a_waiting_draft_while_the_question_is_open(self):
        self.checked(TODAY)
        waiting, _ = self.propose(HOURS)
        self.checked("2026-10-31")
        self.ask_and_get_question(waiting=1)
        self.assertEqual(self.say("yes"), "proposed")
        self.assertEqual([(d["state"]) for d in self.drafts()], ["proposed", "proposed"])
        self.nothing_written()

    def test_a_yes_with_a_code_is_an_approval_not_the_answer(self):
        self.checked(TODAY)
        waiting, _ = self.propose(HOURS)
        self.checked("2026-10-31")
        self.ask_and_get_question(waiting=1)
        self.assertEqual(self.say(f"yes {waiting['code']}"), "approved")
        self.assertEqual(self.store()["selection_checked_on"], "2026-10-31")  # the check was not marked
        self.assertNotIn("available", self.product())

    def test_a_different_answer_is_the_next_change_and_the_original_is_not_silently_made(self):
        self.ask_and_get_question()
        self.assertEqual(self.say("oranges are low"), "question")  # it is another shelf change, so the check is asked again
        self.assertEqual(self.asked[-1], ("oranges are low", {"question": Q_SHELF, "earlier": [SOLD_OUT]}))
        self.assertEqual(self.replies(), [Q_SHELF])
        self.assertEqual(self.say("yes"), "proposed")
        self.assertEqual([c["args"].get("id") for c in json.loads(self.drafts()[0]["ops_json"]) if c["op"] == "product.set_availability"],
                         ["photo-product-016"])  # only the new one, never the Hass avocado
        self.nothing_written()

    def test_a_different_answer_that_needs_no_check_is_drafted_and_marks_no_check(self):
        self.ask_and_get_question()
        draft, _ = self.propose(HOURS)
        self.assertEqual([c["op"] for c in json.loads(draft["ops_json"])], ["store.set_hours"])
        self.assertEqual(self.open_asks(), [])
        self.assertEqual(self.say("yes"), "approved")  # approves the hours only
        self.assertNotIn("selection_checked_on", self.store())
        self.assertNotIn("available", self.product())

    def test_a_question_back_keeps_nothing_pending(self):
        self.ask_and_get_question()
        self.assertEqual(self.say("bananas"), "question")
        self.replies()
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.drafts(), [])

    def test_an_unrelated_message_while_the_question_is_open_closes_it(self):
        self.ask_and_get_question()
        draft, _ = self.propose(HOURS)
        self.assertEqual(self.say("yes"), "approved")
        self.assertNotIn("selection_checked_on", self.store())
        self.assertEqual(self.say("yes"), "no-target")  # nothing is waiting any more, and the old question is gone
        self.assertNotIn("available", self.product())

    def test_a_command_while_the_question_is_open_closes_it(self):
        self.ask_and_get_question()
        self.assertEqual(self.say("status"), "status")
        self.replies()
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.drafts(), [])
        self.nothing_written()


class ExpiryTests(ShelfCase):
    def test_the_question_expires_after_its_time_limit(self):
        self.ask_and_get_question()
        self.now += timedelta(minutes=conversation.RECENT_MINUTES + 1)
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.open_asks(), [])  # the old request is deleted, not only ignored
        self.nothing_written()

    def test_just_inside_the_time_limit_a_yes_still_works(self):
        self.ask_and_get_question()
        self.now += timedelta(minutes=conversation.RECENT_MINUTES - 1)
        self.assertEqual(self.say("yes"), "proposed")


class MorningReportTests(ShelfCase):
    def report(self):
        self.assertEqual(self.say("report"), "report")
        [reply] = self.replies()
        return reply

    def test_the_report_asks_the_same_question_once(self):
        first = self.report()
        self.assertTrue(first.startswith("I still need your shelf check."), first)
        self.assertTrue(first.endswith("\n\n" + Q_REPORT), first)
        self.assertEqual(first.count("Is the shelf list right for today?"), 1)
        self.assertNotIn("Is the shelf list right for today?", self.report())  # once a day
        self.nothing_written()

    def test_yes_after_the_report_drafts_the_check_alone_for_approval(self):
        self.report()
        self.assertEqual(self.say("yes"), "proposed")
        [reply] = self.replies()
        [draft] = self.drafts()
        self.assertEqual([c["op"] for c in json.loads(draft["ops_json"])], ["store.confirm_selection"])
        self.assertNotIn("also records", reply)
        self.nothing_written()
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.store()["selection_checked_on"], TODAY)

    def test_no_after_the_report_changes_nothing(self):
        self.report()
        self.assertEqual(self.say("no"), "shelf-no")
        self.assertEqual(self.replies(), [NO_REPLY])
        self.nothing_written()

    def test_the_report_asks_nothing_with_todays_check(self):
        self.checked(TODAY)
        self.assertNotIn("shelf list right", self.report())
        self.assertEqual(self.open_asks(), [])

    def test_a_stale_check_is_asked_too(self):
        self.checked("2026-10-20")
        self.assertTrue(self.report().endswith(Q_REPORT))

    def test_the_report_after_the_question_expired_is_not_asked_again_the_same_day(self):
        self.report()
        self.now += timedelta(minutes=conversation.RECENT_MINUTES + 1)
        self.assertEqual(self.say("yes"), "no-target")
        self.replies()
        self.assertNotIn("shelf list right", self.report())

    def test_the_next_day_asks_again(self):
        self.report()
        self.now += timedelta(days=1)
        self.assertTrue(self.report().endswith(Q_REPORT))

    def test_a_report_with_a_future_dated_check_asks_nothing(self):
        self.checked("2026-11-05")
        self.assertNotIn("shelf list right", self.report())

    def test_a_stranger_asking_for_the_report_gets_nothing(self):
        self.assertEqual(self.say("report", sender=STRANGER), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.open_asks(), [])


class OldStoreTests(ShelfCase):
    def test_a_store_made_before_this_change_keeps_its_open_request_in_the_one_store(self):
        # SKILLS-FW-3: the pre-FW-3 open_asks table (even without the pending column) is migrated into open_requests and dropped
        self.conv.db.execute("CREATE TABLE open_asks(provider_id TEXT PRIMARY KEY, asked_at TEXT NOT NULL, texts_json TEXT NOT NULL)")
        self.conv.db.execute("INSERT INTO open_asks VALUES ('old1', ?, ?)", (self.now.isoformat(), json.dumps(["add a hike"])))
        self.conv.requests.adopt_legacy(self.conv.settings["ownerChat"])
        self.assertIsNone(self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_asks'").fetchone())
        self.assertEqual([json.loads(r["texts_json"]) for r in self.open_asks()], [["add a hike"]])
        self.ask_and_get_question()
        self.assertEqual(self.say("yes"), "proposed")


class ReviseTests(ShelfCase):
    def test_a_change_that_revises_a_waiting_draft_replaces_it_after_the_yes(self):
        self.checked(TODAY)
        waiting, _ = self.propose(OTHER)
        self.checked("2026-10-31")
        self.interp.mapping["make that sold out instead"] = {"ops": _ops(("product.set_availability", {"id": "photo-product-016", "available": "no"}))["ops"],
                                                              "revises": waiting["code"]}
        self.assertEqual(self.say("make that sold out instead"), "question")
        self.replies()
        self.assertEqual(self.say("yes"), "proposed")
        states = {d["code"]: d["state"] for d in self.drafts()}
        self.assertEqual(states[waiting["code"]], "rejected")
        self.assertEqual(sum(1 for s in states.values() if s == "proposed"), 1)


if __name__ == "__main__":
    unittest.main()
