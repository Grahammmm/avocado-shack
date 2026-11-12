"""RF2100-12: the pure checker closes the top-level key set of a ``calls`` envelope."""
import copy
import unittest

from hass import interpret_check
from hass.skills import dispatch, router
from hass.tests import test_skills_router as fixture  # alias: do not import discoverable TestCase classes

SKILLS = fixture.SKILLS
FIXED = "I could not read that message as a change. " + interpret_check.AGAIN
CALL = {"skill": "stock.set", "slots": {"what": "eggs out"}}
OTHER = {"skill": "stock.set", "slots": {"what": "honey in"}}
RANKED = [("stock.set", 3.0)]


def env(**extra):
    return {"calls": [copy.deepcopy(CALL)], **extra}


class EnvelopeTests(unittest.TestCase):
    def test_calls_envelope_extra_keys_get_fixed_shape_question(self):
        for key in ("unsupported", "ops", "slots", "question", "cancel", "summary", "canary_key"):
            for value in (None, False, "", [], {}, "canary-value", 5):
                with self.subTest(key=key, value=value):
                    reply = env(**{key: value})
                    before = copy.deepcopy(reply)
                    out = interpret_check.check_skill(reply, SKILLS)
                    self.assertEqual(out, {"question": FIXED})
                    self.assertEqual(reply, before)
                    self.assertNotIn(key, out["question"])

    def test_extra_envelope_shape_precedes_revision_and_call_problems(self):
        bad_calls = [
            [CALL] * 13, [], "x", [{"skill": 5}], [{"skill": "stock.set", "slots": {"colour": "red"}}],
            [{"skill": "no.such", "slots": {}}], [CALL, CALL],
        ]
        for calls in bad_calls:
            with self.subTest(calls=calls):
                self.assertEqual(interpret_check.check_skill({"calls": calls, "x": 1}, SKILLS), {"question": FIXED})
        for rev in ("zzz", ["a"], {"a": 1}, 7):
            with self.subTest(rev=rev):
                self.assertEqual(interpret_check.check_skill(env(revises=rev, x=1), SKILLS), {"question": FIXED})
        both = interpret_check.check_skill({"skill": "stock.set", "calls": [CALL], "x": 1}, SKILLS)
        self.assertIn("one change", both["question"])

    def test_real_router_refuses_mixed_envelopes_without_calls_or_backlog(self):
        for key in ("question", "unsupported", "ops", "slots", "canary_key"):
            with self.subTest(key=key):
                store = fixture._backlog()
                reply = env(**{key: "raw model words"})
                result = router.route(reply, RANKED, SKILLS, text="eggs are out", store=store)
                self.assertEqual(result.action, "question")
                self.assertEqual(result.reply, FIXED)
                self.assertFalse(result.calls)
                self.assertIsNone(result.revises)
                self.assertEqual(store.rows(), [])

    def test_valid_calls_keep_identity_and_revision_contract(self):
        for reply in (env(), env(revises=None), {"calls": [CALL, OTHER]}):
            with self.subTest(reply=reply):
                self.assertIs(interpret_check.check_skill(reply, SKILLS), reply)
        waiting = env(revises="AB12")
        self.assertIs(interpret_check.check_skill(waiting, SKILLS, pending_codes=("AB12",)), waiting)
        stale = interpret_check.check_skill(env(revises="AB12"), SKILLS)
        self.assertIn("could not find draft", stale["question"])
        result = router.route({"calls": [CALL, OTHER]}, RANKED, SKILLS, text="eggs are out", store=fixture._backlog())
        self.assertEqual(result.action, "run")
        self.assertEqual([c[1] for c in result.calls], [CALL["slots"], OTHER["slots"]])

    def test_other_reply_paths_and_inputs_are_unchanged(self):
        single = {"skill": "stock.set", "slots": {"what": "eggs out"}}
        self.assertIs(interpret_check.check_skill(single, SKILLS), single)
        none = interpret_check.check_skill({"skill": "none", "summary": "x"}, SKILLS)
        self.assertEqual(none, {"skill": "none", "summary": "x"})
        # RF0330-13: the none catch-all is a closed shape; an extra key is refused, not stripped
        mixed = interpret_check.check_skill({"skill": "none", "summary": "x", "extra": 1}, SKILLS)
        self.assertEqual(set(mixed), {"question"})
        for passthrough in ({"question": "q?"}, {"unsupported": "u"}, {"ops": []}):
            self.assertIs(interpret_check.check_skill(passthrough, SKILLS), passthrough)
        unknown = interpret_check.check_skill({"calls": [{"skill": "no.such", "slots": {}}]}, SKILLS)
        self.assertEqual(unknown, {"skill": "none", "summary": "", "unknown": True})

    def test_dispatch_boundary_already_refuses_mixed_envelopes(self):
        for key in ("unsupported", "ops", "slots", "question", "canary_key"):
            with self.subTest(key=key):
                self.assertIsNone(dispatch.checked(env(**{key: "x"})))
        self.assertIsNotNone(dispatch.checked(env()))


if __name__ == "__main__":
    unittest.main()
