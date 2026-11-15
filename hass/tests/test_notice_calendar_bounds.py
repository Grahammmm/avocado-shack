"""RF2315-13: notice windows stay inclusive without constructing dates past date.max."""
import copy
import json
import types
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from hass import editor
from hass.content_model import REPO_ROOT
from hass.ops import OpContext, Refused, load_registry
from hass.skills import load_skills, shop
from hass.tests import test_skill_dispatch as fixture
from hass.tests.test_store_ops import StoreTestCase, _req

TEXT = "Closed Thursday"
SET = "store.set_notice"
UNTIL = "9999-12-31"


def noon(day):
    return datetime.combine(date.fromisoformat(day), datetime.min.time(), ZoneInfo("America/Los_Angeles")) + timedelta(hours=12)


def slots(until=UNTIL):
    return {"text": TEXT, "until": until}


class NoticeBounds(unittest.TestCase):
    def skill(self, today, until=UNTIL, store=None):
        values = slots(until)
        ctx = types.SimpleNamespace(today=today, store={} if store is None else store)
        before = copy.deepcopy((values, vars(ctx)))
        try:
            return shop.plan_notice(values, ctx)
        finally:
            self.assertEqual((values, vars(ctx)), before)

    def op(self, today, until=UNTIL, store=None):
        content = types.SimpleNamespace(store={} if store is None else copy.deepcopy(store))
        before = copy.deepcopy(content.store)
        result = load_registry()[SET].apply(content, slots(until), OpContext(noon(today), REPO_ROOT, {}))
        if isinstance(result, Refused):
            self.assertEqual(content.store, before)
        else:
            self.assertEqual(content.store, {**before, "notice": {**slots(until), "from": today}})  # AV2152-08: no from = today
            self.assertEqual(len(result), 1)
            self.assertEqual((result[0].collection, result[0].before, result[0].after),
                             ("store", before, content.store))
        return result

    def test_skill_notice_date_max_today_is_allowed(self):
        self.assertEqual(self.skill(UNTIL), [{"op": SET, "args": slots()}])

    def test_op_notice_date_max_today_is_allowed(self):
        self.assertNotIsInstance(self.op(UNTIL), Refused)

    def test_notice_window_near_date_max_59_60_61(self):
        for today, until, days in (("9999-11-02", UNTIL, 59), ("9999-11-01", UNTIL, 60),
                                   ("9999-10-31", UNTIL, 61), ("2026-11-08", "2027-01-07", 60),
                                   ("2026-11-08", "2027-01-08", 61)):
            with self.subTest(today=today, until=until):
                self.assertEqual((date.fromisoformat(until) - date.fromisoformat(today)).days, days)
                if days <= 60:
                    self.assertEqual(self.skill(today, until), [{"op": SET, "args": slots(until)}])
                    self.assertNotIsInstance(self.op(today, until), Refused)
                else:
                    with self.assertRaises(shop.SkillStop) as caught:
                        self.skill(today, until)
                    self.assertEqual((caught.exception.kind, caught.exception.reply), ("refused", shop.NOTICE_LONG))
                    self.assertEqual(self.op(today, until), Refused("the last day is more than 60 days ahead"))

    def test_notice_past_invalid_already_true_and_clear(self):
        for until, reply in (("9999-12-30", shop.NOTICE_PAST), ("9999-02-30", shop.UNTIL_ASK)):
            with self.subTest(until=until), self.assertRaises(shop.SkillStop) as caught:
                self.skill(UNTIL, until)
            self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", reply))
        self.assertEqual(self.op(UNTIL, "9999-12-30"), Refused("the last day 9999-12-30 is already past"))
        store = {"notice": slots()}
        with self.assertRaises(shop.SkillStop) as caught:
            self.skill(UNTIL, store=store)
        self.assertEqual(caught.exception.kind, "question")
        self.assertTrue(caught.exception.reply.startswith("It already says that:"))
        self.assertEqual(self.op(UNTIL, store=store), Refused("the home page already shows that notice"))
        ctx = types.SimpleNamespace(today=UNTIL, store=store)
        self.assertEqual(shop.plan_notice({"clear": True}, ctx), [{"op": "store.clear_notice", "args": {}}])
        content = types.SimpleNamespace(store=copy.deepcopy(store))
        clear = load_registry()["store.clear_notice"].apply
        clear(content, {}, OpContext(noon(UNTIL), REPO_ROOT, {}))
        self.assertEqual(content.store, {})
        self.assertEqual(store, {"notice": slots()})
        self.assertEqual(clear(content, {}, OpContext(noon(UNTIL), REPO_ROOT, {})), Refused("there is no notice"))
        with self.assertRaises(shop.SkillStop) as caught:
            shop.plan_notice({"clear": True}, types.SimpleNamespace(today=UNTIL, store={}))
        self.assertEqual((caught.exception.kind, caught.exception.reply), ("refused", shop.NO_NOTICE))


class EditorBounds(StoreTestCase):
    def test_editor_prepare_date_max_proposes_without_source_writes(self):
        repo = self.repo()
        before = (repo.head(), repo.store(), repo.status())
        for today in (UNTIL, "9999-11-02", "9999-11-01"):
            with self.subTest(today=today):
                out = editor.prepare(_req((SET, slots())), state=str(repo.state), now=noon(today))
                self.assertEqual(out["result"], "ok", out)
                self.assertEqual(out["draft"]["ops"], [{"op": SET, "args": slots()}])
                self.assertEqual(out["draft"]["records"][0]["after"]["notice"], {**slots(), "from": UNTIL})  # AV2152-08: no from = the first prepare's today (its draft is reused)
                self.assertEqual((repo.head(), repo.store(), repo.status()), before)

    def test_invalid_typed_date_writes_no_draft(self):
        repo = self.repo()
        before = (repo.head(), repo.store(), repo.status(), repo.drafts())
        out = editor.prepare(_req((SET, slots("9999-02-30"))), state=str(repo.state), now=noon(UNTIL))
        self.assertEqual(out["result"], "invalid", out)
        self.assertEqual((repo.head(), repo.store(), repo.status(), repo.drafts()), before)


class NoticeDispatch(fixture.SkillCase):
    SKILLS = (load_skills().skills["shop.notice"],)

    def notice(self, until=UNTIL):
        text = f"Put up a notice saying {TEXT} until {until}"
        self.script(text, fixture.skill_reply("shop.notice", **slots(until)))
        return text

    def test_real_skill_dispatch_date_max_proposes_without_writes(self):
        self.now = noon(UNTIL)
        before = (self.repo.head(), self.repo.status())
        draft, _ = self.propose(self.notice())
        self.assertEqual(json.loads(draft["ops_json"]), [{"op": SET, "args": slots()}])
        self.nothing_written()
        self.assertEqual((self.repo.head(), self.repo.status()), before)

    def test_ordinary_notice_approval_undo_unchanged(self):
        before = (self.repo.wt / "hass/content/store.json").read_bytes()
        draft, _ = self.propose(self.notice("2026-11-02"))
        self.nothing_written()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        self.assertEqual(json.loads((self.repo.wt / "hass/content/store.json").read_bytes())["notice"], {**slots("2026-11-02"), "from": "2026-11-02"})
        undo = editor.prepare(_req(("history.revert", {"changeId": draft["change_id"]})),
                              state=str(self.repo.state), now=self.now)
        self.assertEqual(undo["result"], "ok", undo)
        self.assertEqual(self.editor.apply(undo["draft"]["change_id"], undo["draft"]["draft_hash"])["result"], "applied")
        self.assertEqual((self.repo.wt / "hass/content/store.json").read_bytes(), before)

    def test_cancelled_notice_cannot_be_approved(self):
        draft, _ = self.propose(self.notice("2026-11-02"))
        self.assertEqual(self.say("no"), "rejected")
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.nothing_written()

    def test_expired_notice_cannot_be_approved(self):
        draft, _ = self.propose(self.notice("2026-11-02"))
        self.now += timedelta(seconds=601)
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.assertEqual(self.drafts()[0]["state"], "expired")
        self.nothing_written()

    def test_duplicate_notice_message_does_not_create_another_draft(self):
        text = self.notice("2026-11-02")
        self.assertEqual(self.say(text, pid="notice-1"), "proposed")
        self.assertEqual(self.say(text, pid="notice-1"), "duplicate")
        self.assertEqual(len(self.drafts()), 1)
        self.nothing_written()

    def test_stale_notice_draft_cannot_overwrite_a_later_notice(self):
        draft, _ = self.propose(self.notice("2026-11-02"))
        later = editor.prepare(_req((SET, {"text": "Open Friday", "until": "2026-11-03"})),
                               state=str(self.repo.state), now=self.now)["draft"]
        self.assertEqual(self.editor.apply(later["change_id"], later["draft_hash"])["result"], "applied")
        self.say(f"yes {draft['code']}")
        old = self.drafts()[0]
        self.assertEqual((old["state"], old["reason"]), ("rejected", "stale"))
        self.assertEqual(self.drafts()[-1]["state"], "proposed")
        self.assertEqual(self.commits(), 1)
        self.assertEqual(json.loads((self.repo.wt / "hass/content/store.json").read_bytes())["notice"]["text"], "Open Friday")
