"""RF2210-12: unregistered expected op/arg names never reach score failure reasons. Offline; no model, no socket."""

import json, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import interpreter_eval as ev, nl_eval
from hass.tests import test_interpreter_eval as base

CANARY = "PRIVATE-CASE-CANARY-owner-words"
GOOD = {"ops": [{"op": "store.set_headline", "args": {"first": "A", "second": "B"}}], "revises": None}
REG = base.REGISTRY


def case(*calls, text=CANARY):
    return {"id": "e01", "text": text, "pending": [], "expect": {"ops": list(calls), "revises": None}}


def call(op="store.set_headline", **args): return {"op": op, "args": args or {"first": "A"}}


def why(c, reply=GOOD):
    failed = ev.score([c], {"e01": reply}, REG)["failed"]
    return failed[0]["why"] if failed else None


class FixedReasons(unittest.TestCase):
    def test_unknown_expected_op_never_enters_reason(self):
        for name in (CANARY, "x" * 5000, "caf\u00e9 \u202e\n\t", "", " "):
            c = case(call(name))
            before = json.dumps(c)
            self.assertEqual(why(c), "expected op is not registered")
            self.assertEqual(json.dumps(c), before)

    def test_unknown_expected_arg_never_enters_reason(self):
        for args in ({CANARY: CANARY}, {"first": "A", CANARY: 1}, {"image": "x"}, {"a\n": 1, "b": 2}):  # image: another op's arg
            out = why(case(call(**args)))
            self.assertEqual(out, "expected arg is not registered")
        out = why(case(call(first="A", third="C")))
        self.assertNotIn("third", out)
        self.assertEqual(why(case(call(first="A", second="B", **{})), {"ops": [{"op": "store.set_headline", "args": {"first": "A"}}], "revises": None}),
                         "op 1 store.set_headline: missing arg second")

    def test_complete_preflight_prevents_late_call_name_leak(self):
        other = {"ops": [{"op": "store.set_story", "args": {"text": "t"}}, GOOD["ops"][0]], "revises": None}
        self.assertEqual(why(case(call(), call(CANARY)), other), "expected op is not registered")
        self.assertEqual(why(case(call(), call(first="A", **{CANARY: 1})), other), "expected arg is not registered")
        self.assertEqual(why(case(call(CANARY, **{CANARY: 1}))), "expected op is not registered")  # op before args
        self.assertEqual(why(case(call(**{CANARY: 1}), call(CANARY))), "expected arg is not registered")  # call order

    def test_kind_mismatch_and_registered_reasons_are_unchanged(self):
        unknown = {"ops": [{"op": CANARY, "args": {}}], "revises": None}
        self.assertEqual(why(case(call(CANARY)), unknown), "expected ops, got question")
        c = case(call())
        self.assertIsNone(why(c))
        self.assertEqual(why(c, {"ops": [{"op": "store.set_story", "args": {"text": "t"}}], "revises": None}),
                         "ops store.set_story but expected store.set_headline")
        self.assertEqual(why(c, {"ops": [{"op": "store.set_headline", "args": {"first": "Z", "second": "B"}}], "revises": None}),
                         "op 1 store.set_headline: arg first differs")
        self.assertEqual(why({**c, "expect": {"question": True}}), "expected question, got ops")

    def test_shared_nl_judge_inherits_fixed_reason(self):
        out = nl_eval.judge(case(call(CANARY)), {"reply": GOOD}, REG)
        self.assertEqual((out["verdict"], out["intent"], out["why"]), ("wrong-draft", False, "expected op is not registered"))
        out = nl_eval.judge(case(call(first="A", **{CANARY: 1})), {"reply": GOOD}, REG)
        self.assertEqual((out["verdict"], out["why"]), ("wrong-draft", "expected arg is not registered"))


class CliAndCompare(base.EvalTestCase):
    def mutated(self, expect):
        rows = [json.loads(r) for r in self.rows]
        rows[0] = {**rows[0], "text": CANARY, "expect": expect}
        return rows

    def test_real_loader_and_score_cli_redact_expectation_names(self):
        replies = self.write("replies.jsonl", [{"id": "e01", "reply": GOOD}])
        for expect, reason in (({"ops": [call(CANARY)], "revises": None}, "expected op is not registered"),
                               ({"ops": [call(**{CANARY: 1})], "revises": None}, "expected arg is not registered")):
            cases = self.write("cases.jsonl", self.mutated(expect))
            snap = (cases.read_bytes(), replies.read_bytes())
            self.assertEqual(len(ev.load_cases(cases)), ev.CASE_COUNT)
            code, out, err = base.scored(cases, replies)
            self.assertEqual((code, err), (0, ""))
            self.assertNotIn(CANARY, out)
            self.assertEqual(json.loads(out)["failed"], [{"id": "e01", "why": reason}])
            proc = subprocess.run([sys.executable, "-B", "-m", "hass.interpreter_eval", "score", "--cases", str(cases),
                                   "--replies", str(replies)], capture_output=True, text=True, cwd=Path(base.__file__).parents[2])
            self.assertEqual((proc.returncode, proc.stderr), (0, ""))
            self.assertNotIn(CANARY, proc.stdout)
            self.assertEqual(json.loads(proc.stdout)["failed"], [{"id": "e01", "why": reason}])
            self.assertEqual(snap, (cases.read_bytes(), replies.read_bytes()))

    def test_compare_retains_always_failed_classification(self):
        cases = ev.load_cases(self.write("cases.jsonl", self.mutated({"ops": [call(CANARY)], "revises": None})))
        out = ev.compare(cases, {"e01": GOOD}, {"e01": GOOD}, REG)
        self.assertNotIn(CANARY, json.dumps(out))
        self.assertEqual(out["stillFailing"], 1)
        self.assertFalse(out.get("regressed"))
        self.assertFalse(out.get("fixed"))


if __name__ == "__main__":
    unittest.main()
