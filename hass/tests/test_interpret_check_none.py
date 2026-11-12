"""RF0330-13: the pure checker's exact {"skill": "none"} branch refuses malformed catch-alls instead of normalizing them."""

import copy
import unittest

from hass import interpret_check
from hass.skills import router
from hass.tests.test_skills_router import SKILLS, _backlog

FIXED = {"question": "I could not read that message as a change. Could you say it another way?"}
CANARY = "CANARY-7731"
BAD_SUMMARIES = (None, False, True, 0, 3, 1.5, [], ["x"], {}, {"a": 1}, b"bytes")
EXTRA_KEYS = ("slots", "ops", "unsupported", "question", "cancel", "revises", "summry", "meta", "unknown")
EXTRA_VALUES = (None, False, "", [], {}, CANARY)


def _check(reply, pending=()):
    before = copy.deepcopy(reply)
    out = interpret_check.check_skill(reply, SKILLS, pending)
    assert reply == before, "source reply was mutated"
    return out


class NoneShapeTests(unittest.TestCase):
    def test_supplied_nontext_none_summary_is_not_repaired(self):
        for bad in BAD_SUMMARIES:
            with self.subTest(bad):
                self.assertEqual(_check({"skill": "none", "summary": bad}), FIXED)
        self.assertEqual(_check({"skill": "none", "summary": ""}), {"skill": "none", "summary": ""})
        self.assertEqual(_check({"skill": "none"}), {"skill": "none", "summary": ""})

    def test_none_has_only_its_own_keys(self):
        for key in EXTRA_KEYS:
            for value in EXTRA_VALUES:
                with self.subTest(key=key, value=value):
                    out = _check({"skill": "none", "summary": "ok", key: value})
                    self.assertEqual(out, FIXED)
                    self.assertNotIn(CANARY, str(out))
        both = _check({"skill": "none", "calls": []})
        self.assertEqual(both, {"question": "I could not read that message as one change. Could you say it another way?"})

    def test_none_revision_is_shape_error_before_revision_lookup(self):
        for revises in (None, "abc", "stale", ["abc"], {"a": 1}):
            with self.subTest(revises):
                self.assertEqual(_check({"skill": "none", "revises": revises}, ("abc",)), FIXED)
        real = {"skill": "stock.set", "slots": {"what": "eggs"}, "revises": "abc"}
        self.assertIs(interpret_check.check_skill(real, SKILLS, ("abc",)), real)
        stale = interpret_check.check_skill(real, SKILLS, ())
        self.assertIn("could not find draft abc", stale["question"])

    def test_real_router_does_not_log_malformed_none(self):
        for reply in ({"skill": "none", "summary": None}, {"skill": "none", "summary": "x", "slots": {}},
                      {"skill": "none", "revises": None}):
            with self.subTest(reply):
                store = _backlog()
                sentinel = store.record("other", "sentinel", "earlier request")
                result = router.route(reply, [], SKILLS, text="order eggs", store=store)
                self.assertEqual((result.action, result.calls, result.revises, result.reply),
                                 ("question", (), None, FIXED["question"]))
                self.assertEqual([r["id"] for r in store.rows()], [sentinel])

    def test_valid_none_compatibility_is_exact(self):
        for summary in ("", " ", "  padded \n", "caf\u00e9 \u2603 \u65e5\u672c", "line one\nline two", "order eggs"):
            with self.subTest(summary):
                self.assertEqual(_check({"skill": "none", "summary": summary}), {"skill": "none", "summary": summary})
        store = _backlog()
        result = router.route({"skill": "none", "summary": "order eggs"}, [], SKILLS, text="order eggs", store=store)
        self.assertEqual((result.action, result.reason, result.summary), ("backlog", "unknown-skill", "order eggs"))
        self.assertEqual(len(store.rows()), 1)
        priced = router.route({"skill": "none", "summary": "price"}, [], SKILLS, text="eggs are 5 dollars",
                              hints={"price": True}, store=store)
        self.assertEqual((priced.action, priced.reason), ("backlog", "price"))

    def test_other_reply_paths_and_strict_dispatch_are_unchanged(self):
        single = {"skill": "stock.set", "slots": {"what": "eggs"}}
        calls = {"calls": [single]}
        self.assertIs(interpret_check.check_skill(single, SKILLS), single)
        self.assertIs(interpret_check.check_skill(calls, SKILLS), calls)
        unknown = {"skill": "stock.teleport", "slots": {}}
        self.assertEqual(_check(unknown), {"skill": "none", "summary": "", "unknown": True})
        for raw in ({"ops": []}, {"question": "which?"}, {"unsupported": "no"}):
            self.assertIs(interpret_check.check_skill(raw, SKILLS), raw)
        bad_slot = {"skill": "stock.set", "slots": {"nope": "x"}}
        self.assertIn("could not read the details", _check(bad_slot)["question"])


if __name__ == "__main__":
    unittest.main()
