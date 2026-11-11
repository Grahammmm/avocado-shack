"""Unknown weekdays stay unknown until the owner names them (RF2115-10)."""
import copy
import json
import types
import unittest
from datetime import timedelta

from hass.skills import shop
from hass.tests import test_skill_dispatch as fixture
from hass.tests.test_editor import git

OLD = ["Friday 9am–5pm"]
FRIDAY = "Friday 9am–7pm"
QUESTION = "You didn't name Sunday. Should I add hours for it?"


def context(old=None, texts=None):
    return types.SimpleNamespace(store={"hours": OLD[:] if old is None else old},
                                 texts=["Friday till 7"] if texts is None else texts)


class UnnamedAdditions(unittest.TestCase):
    def assert_question(self, hours, ctx, reply):
        stop = shop.check_hours_untouched({"hours": hours}, ctx.texts, ctx)
        self.assertIsNotNone(stop)
        self.assertEqual((stop.kind, stop.reply), ("question", reply))
        with self.assertRaises(shop.SkillStop) as caught:
            shop.plan_hours({"hours": hours}, ctx)
        self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", reply))

    def test_unnamed_absent_weekday_open_and_closed_both_ask(self):
        for sunday in ("Sunday 10am–4pm", "Closed Sunday"):
            with self.subTest(sunday=sunday):
                slots, ctx = {"hours": [FRIDAY, sunday]}, context()
                before = copy.deepcopy((slots, vars(ctx)))
                self.assert_question(slots["hours"], ctx, QUESTION)
                self.assertEqual((slots, vars(ctx)), before)

    def test_explicitly_named_new_day_is_allowed(self):
        rows = (("Friday till 7 and Sunday 10 to 4", [FRIDAY, "Sunday 10am–4pm"]),
                ("Friday till 7 and closed weekends", [FRIDAY, "Closed Saturday–Sunday"]),
                ("Friday through Sunday 9 to 7", ["Friday–Sunday 9am–7pm"]))
        for said, hours in rows:
            with self.subTest(said=said):
                self.assertEqual(shop.plan_hours({"hours": hours}, context(texts=[said])),
                                 [{"op": "store.set_hours", "args": {"hours": hours}}])
        self.assert_question([FRIDAY, "Closed Saturday–Sunday"],
                             context(texts=["Friday till 7 and closed Saturday"]), QUESTION)

    def test_sparse_unchanged_schedule_does_not_ask(self):
        for ctx in (context(), context(old=[])):
            slots = {"hours": [FRIDAY]}
            before = copy.deepcopy((slots, vars(ctx)))
            self.assertEqual(shop.plan_hours(slots, ctx),
                             [{"op": "store.set_hours", "args": slots}])
            self.assertEqual((slots, vars(ctx)), before)
        for ctx in (None, context(texts=[]), types.SimpleNamespace(texts=["Friday till 7"])):
            self.assertIsNone(shop.check_hours_untouched({"hours": [FRIDAY, "Closed Sunday"]}, [], ctx))

    def test_existing_unnamed_day_guards_keep_their_priority(self):
        for saturday in ([], ["Saturday 10am–4pm"]):
            self.assert_question([FRIDAY, *saturday, "Closed Sunday"],
                                 context(old=[*OLD, "Saturday 9am–5pm"]),
                                 "Do you want Saturday to stay 9am–5pm?")
        self.assert_question([FRIDAY, "Closed Sunday"], context(old=[*OLD, "Call ahead"]),
                             "Do you want to keep “Call ahead” in the hours?")
        self.assert_question([FRIDAY, "Closed Sunday", "Monday 10am–4pm"], context(),
                             "You didn't name Monday. Should I add hours for it?")

    def test_grouped_proposed_line_does_not_hide_new_unnamed_day(self):
        self.assert_question(["Friday–Sunday 9am–7pm"], context(),
                             "You didn't name Saturday. Should I add hours for it?")
        for separator in (", ", " · "):
            self.assert_question([FRIDAY + separator + "Closed Sunday"], context(), QUESTION)


class RealDispatcherAdditions(fixture.SkillCase):
    SKILLS = (shop.SHOP_HOURS,)

    def setUp(self):
        super().setUp()
        path = self.repo.wt / "hass/content/store.json"
        store = json.loads(path.read_text("utf-8"))
        store["hours"] = OLD[:]
        path.write_text(json.dumps(store), "utf-8")
        git(self.repo.wt, "add", "hass/content/store.json")
        git(self.repo.wt, "commit", "-qm", "sparse fixture hours")
        self.base = self.count()
        self.hours = [FRIDAY, "Sunday 10am–4pm"]

    def ask(self):
        text = "Friday till 7"
        self.script(text, fixture.skill_reply("shop.hours", hours=self.hours))
        self.assertEqual(self.say(text, pid="first-hours"), "question")
        self.assertEqual(self.replies(), [QUESTION])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def correct(self):
        text = "Sunday 10 to 4 too"
        self.script(text, fixture.skill_reply("shop.hours", hours=self.hours))
        draft, _ = self.propose(text)
        self.assertEqual(json.loads(draft["ops_json"]),
                         [{"op": "store.set_hours", "args": {"hours": self.hours}}])
        self.nothing_written()
        return draft

    def test_real_dispatch_question_then_explicit_day_can_propose(self):
        self.ask()
        self.assertEqual(self.say("Friday till 7", pid="first-hours"), "duplicate")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.say("yes"), "no-target")
        self.replies()
        self.assertEqual(self.drafts(), [])
        self.conv = self.open()  # continuation must survive persistence
        self.correct()

    def test_cancelled_corrected_hours_cannot_be_approved(self):
        self.ask()
        draft = self.correct()
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.assertEqual(self.drafts()[-1]["state"], "rejected")
        self.nothing_written()

    def test_expired_corrected_hours_cannot_be_approved(self):
        self.ask()
        draft = self.correct()
        self.now += timedelta(seconds=601)
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.assertEqual(self.drafts()[-1]["state"], "expired")
        self.nothing_written()

    def test_stale_corrected_hours_cannot_be_applied(self):
        self.ask()
        draft = self.correct()
        path = self.repo.wt / "hass/content/store.json"
        store = json.loads(path.read_text("utf-8"))
        store["hours"] = ["Friday 8am–5pm"]
        path.write_text(json.dumps(store), "utf-8")
        git(self.repo.wt, "add", "hass/content/store.json")
        git(self.repo.wt, "commit", "-qm", "another fixture edit")
        self.base = self.count()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")  # acknowledgement, not an apply verdict
        original = next(row for row in self.drafts() if row["code"] == draft["code"])
        self.assertEqual((original["state"], original["reason"]), ("rejected", "stale"))
        self.assertEqual(self.drafts()[-1]["state"], "proposed")
        self.assertEqual(json.loads(path.read_text("utf-8"))["hours"], store["hours"])
        self.assertEqual(self.commits(), 0)


if __name__ == "__main__":
    unittest.main()
