"""Fixture clocks stay local to each harness operation, not each Scratch lifetime."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from hass import content_model, editor
from hass.skills import testkit
from hass.tests.test_skills_stock import EGGS, SKILLS


CONFIRM = [{"op": "store.confirm_selection", "args": {}}]


class FixtureClock(unittest.TestCase):
    def scratch(self, **kwargs):
        sc = testkit.Scratch({}, SKILLS, **kwargs)
        self.addCleanup(sc.close)
        return sc

    def test_stock_fixture_is_independent_of_host_day(self):
        for day in ("2026-11-07", "2026-11-09", "2030-01-01"):
            class Ambient(datetime):
                @classmethod
                def now(cls, tz=None):
                    instant = datetime.fromisoformat(day + "T17:00:00+00:00")
                    return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
            with self.subTest(day=day), patch.object(content_model, "datetime", Ambient):
                for name in ("stock.set", "stock.checked", "stock.clear"):
                    results = testkit.run_file(testkit.FIXTURES / "stock" / (name + ".jsonl"), tuple(SKILLS.values()))
                    for result in results:
                        self.assertEqual(result.problems, [], (day, result.id))
                        if result.facts.get("disposition") == "proposed":
                            self.assertEqual(result.facts["undo"], "identical", result.id)
                self.assertIs(content_model.datetime, Ambient)

    def test_clock_reaches_setup_prepare_apply_recover_and_render(self):
        for fault in (None, "undo-leaves"):
            with self.subTest(fault=fault), patch.object(editor, "prepare", wraps=editor.prepare) as prepare, \
                    patch.object(editor, "apply", wraps=editor.apply) as apply, \
                    patch.object(editor, "recover", wraps=editor.recover) as recover, \
                    patch.object(editor, "render_draft", wraps=editor.render_draft) as render:
                sc = self.scratch(fault=fault, setup=CONFIRM)
                self.assertEqual(prepare.call_args.kwargs["now"], testkit.START)
                self.assertEqual(apply.call_args.kwargs["now"], testkit.START)
                sc.now += timedelta(minutes=3)
                out = sc.editor.prepare([{"op": "product.set_availability", "args": {"id": EGGS, "available": "no"}}])
                self.assertEqual(out["result"], "ok", out)
                draft = out["draft"]
                self.assertEqual(datetime.fromisoformat(draft["created_at"]), sc.now)
                self.assertEqual(prepare.call_args.kwargs["now"], sc.now)
                sc.editor.render_draft(draft["change_id"])
                self.assertEqual(render.call_args.kwargs["now"], sc.now)
                sc.now += timedelta(minutes=1)
                self.assertEqual(sc.editor.apply(draft["change_id"], draft["draft_hash"])["result"], "applied")
                self.assertEqual(apply.call_args.kwargs["now"], sc.now)
                sc.editor.recover()
                self.assertEqual(recover.call_args.kwargs["now"], sc.now)

    def test_context_and_editor_use_the_pacific_calendar_day(self):
        sc = self.scratch()
        for instant, day in (("2026-11-09T07:59:00+00:00", "2026-11-08"),
                             ("2026-11-09T08:01:00+00:00", "2026-11-09")):
            with self.subTest(instant=instant):
                sc.now = datetime.fromisoformat(instant)
                self.assertEqual(sc._ctx().today, day)
                out = sc.editor.prepare([{"op": "store.confirm_selection", "args": {"date": day}}])
                self.assertEqual(out["result"], "ok", out)
                draft = out["draft"]
                self.assertEqual(datetime.fromisoformat(draft["created_at"]), sc.now)
                self.assertEqual(sc.editor.apply(draft["change_id"], draft["draft_hash"])["result"], "applied")
                self.assertEqual(sc._ctx().content.store["selection_checked_on"], day)
        before = sc.now
        sc.say("unsupported")
        self.assertEqual(sc.now, before + timedelta(minutes=1))

    def test_fixture_clock_scope_restores_after_failure_and_close(self):
        ambient = content_model.datetime
        a, b = self.scratch(), self.scratch()
        b.now = testkit.START + timedelta(days=2)
        for sc in (a, b, a):
            self.assertIs(content_model.datetime, ambient)
            self.assertEqual(sc._ctx().today, content_model.shop_today(sc.now).isoformat())
            with patch.object(editor, "prepare", side_effect=ValueError("prepare failed")):
                with self.assertRaisesRegex(ValueError, "prepare failed"):
                    sc.editor.prepare(CONFIRM)
            self.assertIs(content_model.datetime, ambient)
        with patch.object(content_model, "load_and_validate", side_effect=ValueError("validation failed")):
            with self.assertRaisesRegex(ValueError, "validation failed"):
                a._ctx()
        self.assertIs(content_model.datetime, ambient)
        def fail_open():
            self.assertEqual(content_model.shop_today().isoformat(), "2026-11-08")
            raise ValueError("open failed")

        with patch("hass.tests.test_editor.WriterRepo", side_effect=fail_open):
            with self.assertRaisesRegex(ValueError, "open failed"):
                testkit.Scratch({}, SKILLS)
        self.assertIs(content_model.datetime, ambient)
        closed = testkit.Scratch({}, SKILLS)
        closed.close()
        self.assertIs(content_model.datetime, ambient)
        self.assertEqual(a._ctx().today, "2026-11-08")

    def test_future_dates_are_still_refused(self):
        sc = self.scratch()
        out = sc.editor.prepare([{"op": "store.confirm_selection", "args": {"date": "2026-11-09"}}])
        self.assertNotEqual(out["result"], "ok", out)
        with self.assertRaises(content_model.ContentError):
            sc._seed({"store": {"selection_checked_on": "2026-11-09"}})


if __name__ == "__main__":
    unittest.main()
