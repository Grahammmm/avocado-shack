"""An hours draft cannot change a weekday the owner said to keep unchanged (RF2315-20)."""
import json
import types
import unittest

from hass.skills import shop
from hass.tests import test_skill_dispatch as fixture
from hass.tests.test_editor import git

OLD = ["Monday–Thursday 9am–6pm", "Friday 9am–5pm", "Saturday 9am–5pm", "Closed Sunday"]
GOOD = ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–5pm", "Closed Sunday"]
WRONG = ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–5pm · Sunday 10am–4pm"]
ASK = "Do you want Sunday to stay closed?"
KEEPS = ("Don't change Sunday; Friday till 7", "Keep Sunday unchanged; Friday till 7")


def ctx(*texts, old=None):
    return types.SimpleNamespace(store={"hours": OLD[:] if old is None else old}, texts=list(texts))


class KeepDay(unittest.TestCase):
    def question(self, hours, context, reply=ASK):
        with self.assertRaises(shop.SkillStop) as caught:
            shop.plan_hours({"hours": hours}, context)
        self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", reply))

    def test_keep_and_dont_change_protect_saved_sunday(self):
        for said in KEEPS:
            with self.subTest(said=said):
                self.question(WRONG, ctx(said))
                self.question(WRONG[:2] + ["Saturday 9am–5pm"], ctx(said))  # Sunday removed

    def test_protected_day_kept_allows_friday_change(self):
        for said in KEEPS:
            self.assertEqual(shop.plan_hours({"hours": GOOD}, ctx(said)),
                             [{"op": "store.set_hours", "args": {"hours": GOOD}}])

    def test_finite_grammar_and_boundaries(self):
        for said in ("please do not change SUN hours", "Don’t change sunday.", "keep Sun unchanged, Friday till 7",
                     "Friday till 7\nKeep Sunday hours unchanged"):
            with self.subTest(said=said):
                self.assertEqual(shop._kept_days([said]), {6})
        for said in ("notable Sunday", "keep Sunday flowers unchanged", "change Sunday", "not only Sunday",
                     "don't change Sunday or Monday", "he said \"don't change Sunday\" ok"):
            with self.subTest(said=said):
                self.assertEqual(shop._kept_days([said]), frozenset())
        # an ordinary Sunday edit still works
        self.assertEqual(shop.plan_hours({"hours": WRONG}, ctx("change Sunday to 10 to 4, Friday till 7")),
                         [{"op": "store.set_hours", "args": {"hours": WRONG}}])

    def test_remove_or_add_protected_day_asks(self):
        old = ["Friday 9am–5pm"]
        self.question(["Friday 9am–7pm", "Sunday 10am–4pm"], ctx("Keep Sunday unchanged", "Friday till 7", old=old),
                      "You didn't name Sunday. Should I add hours for it?")
        self.question(GOOD[:3], ctx("Don't change Sunday; Friday till 7"), ASK)

    def test_conflicting_joined_texts_ask_instead_of_override(self):
        self.question(WRONG, ctx("Don't change Sunday", "Friday till 7 and Sunday 10am–4pm"))
        self.assertEqual(shop.plan_hours({"hours": GOOD}, ctx("Don't change Sunday", "Friday till 7")),
                         [{"op": "store.set_hours", "args": {"hours": GOOD}}])


class RealDispatch(fixture.SkillCase):
    SKILLS = (shop.SHOP_HOURS,)

    def setUp(self):
        super().setUp()
        path = self.repo.wt / "hass/content/store.json"
        store = json.loads(path.read_text("utf-8"))
        store["hours"] = OLD[:]
        path.write_text(json.dumps(store), "utf-8")
        git(self.repo.wt, "add", "hass/content/store.json")
        git(self.repo.wt, "commit", "-qm", "keep-day fixture hours")
        self.base = self.count()

    def test_real_dispatch_contradicting_keep_has_no_draft(self):
        text = "Don't change Sunday; Friday till 7"
        self.script(text, fixture.skill_reply("shop.hours", hours=WRONG))
        self.assertEqual(self.say(text, pid="keep-wrong"), "question")
        self.assertEqual(self.replies(), [ASK])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_real_dispatch_corrected_list_proposes_but_is_not_applied(self):
        text = "Keep Sunday unchanged; Friday till 7"
        self.script(text, fixture.skill_reply("shop.hours", hours=GOOD))
        draft, _ = self.propose(text)
        self.assertEqual(json.loads(draft["ops_json"]),
                         [{"op": "store.set_hours", "args": {"hours": GOOD}}])
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
