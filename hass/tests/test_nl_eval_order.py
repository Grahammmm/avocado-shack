"""RF1005-19: calls with the same op and target are matched one-to-one, so a harmless permutation is not a wrong draft."""

import contextlib, copy, io, itertools, json, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import nl_eval as nl
from hass.ops import load_registry

REGISTRY, ID = load_registry(), "photo-product-081"
CORPUS = Path(__file__).resolve().parent / "fixtures" / "nl-corpus.jsonl"


def call(op="product.edit", **args): return {"op": op, "args": args}  # noqa: E704


def case(*expected, **extra):
    return {"id": "synthetic01", "text": "synthetic text", "intent": "product", "ask": False, "refuse": False, "pending": [],
            "expect": {"ops": list(expected), "revises": None}, **extra}


def judge(c, calls, revises=None):
    return nl.judge(c, {"reply": {"ops": calls, "revises": revises}, "failed": None, "ms": 5}, REGISTRY)


NAME, DESC, CAT = call(id=ID, name="Morning apples"), call(id=ID, description="Crisp fruit"), call(id=ID, category="pantry")
BOTH = case(call(id=ID, name="Morning apples"), call(id=ID, description="Crisp fruit"))


class PermutationTests(unittest.TestCase):
    def test_same_op_same_target_disjoint_fields_match_in_either_order(self):
        for order in ([NAME, DESC], [DESC, NAME]):
            self.assertEqual(judge(BOTH, order), {"verdict": "pass", "kind": "ops", "intent": True, "why": None})
        three = case(NAME, DESC, CAT)
        for order in itertools.permutations([NAME, DESC, CAT]):
            self.assertEqual(judge(three, list(order))["verdict"], "pass")
        adds = case(call("product.add", name="Plums", category="fruit"), call("product.add", name="Figs", category="fruit"))
        for order in itertools.permutations(adds["expect"]["ops"]):
            self.assertEqual(judge(adds, list(order))["verdict"], "pass")

    def test_partial_expectations_require_reassignment_not_greedy_pairing(self):
        c = case(call(id=ID), call(id=ID, name="Morning apples"))
        for order in ([NAME, DESC], [DESC, NAME]):
            self.assertEqual(judge(c, copy.deepcopy(order))["verdict"], "pass")

    def test_matching_consumes_each_actual_call_once(self):
        for calls in ([NAME], [NAME, DESC, CAT], [NAME, call(id="photo-product-051", description="Crisp fruit")],
                      [NAME, call(id=ID, description="Other")], [NAME, call("product.hide", id=ID)]):
            got = judge(BOTH, calls)
            self.assertEqual(got["verdict"], "wrong-draft", calls)
        twice = case(NAME, call(id=ID, name="Morning apples"))
        self.assertEqual(judge(twice, [NAME, DESC])["verdict"], "wrong-draft")
        self.assertEqual(judge(BOTH, [DESC, call(id=ID, description="Other")])["why"], "op 1 product.edit: missing arg name")

    def test_matching_preserves_claim_type_revision_and_admission_guards(self):
        self.assertNotEqual(judge(BOTH, [DESC, call(id=ID, name="Morning apples", organic=True)])["verdict"], "pass")
        self.assertNotEqual(judge(BOTH, [NAME, NAME])["kind"], "ops")  # duplicate calls: a question, before matching
        self.assertNotEqual(judge(BOTH, [DESC, NAME], revises="X1")["verdict"], "pass")  # not a pending code: refused before matching
        revising = case(NAME, DESC, pending=[{"code": "X1"}])
        revising["expect"]["revises"] = "X1"
        self.assertEqual(judge(revising, [DESC, NAME], revises="X1")["verdict"], "pass")
        self.assertEqual(judge(revising, [DESC, NAME])["verdict"], "wrong-draft")
        self.assertNotEqual(judge(case(call("product.set_availability", id=ID, available="no")),
                                  [call("product.set_availability", id=ID, available=True)])["verdict"], "pass")
        self.assertNotEqual(judge(BOTH, [DESC, call("nope.op", id=ID)])["kind"], "ops")  # unknown op: a question, before matching
        self.assertNotEqual(judge(BOTH, [DESC] * 21)["kind"], "ops")

    def test_matching_does_not_sort_order_sensitive_lists_or_skip_words(self):
        hours = case(call("store.set_hours", hours=["Mon 9-5", "Tue 9-5"]))
        self.assertEqual(judge(hours, [call("store.set_hours", hours=["Tue 9-5", "Mon 9-5"])])["verdict"], "wrong-draft")
        words = case(NAME, DESC, mustContain=["crisp"])
        self.assertEqual(judge(words, [DESC, NAME])["verdict"], "pass")
        missing = case(NAME, call(id=ID, description="Tasty fruit"), mustContain=["crisp"])
        self.assertEqual(judge(missing, [call(id=ID, description="Tasty fruit"), NAME])["verdict"], "wrong-draft")

    def test_dense_twenty_call_matching_is_bounded_and_inputs_unchanged(self):
        fields = [f"Item {i:02d}" for i in range(20)]
        actual = [call(id=ID, name=n) for n in fields][::-1]
        wide = case(*[call(id=ID)] * 19, call(id=ID, name="Item 00"))
        tally = []
        before = copy.deepcopy((wide, actual))
        self.assertTrue(nl._matched(wide, {"ops": actual, "revises": None}, REGISTRY, tally))
        self.assertLessEqual(len(tally), 400)
        self.assertEqual(before, (wide, actual))
        none = case(*[call(id=ID, name="Item 00")] * 20)
        self.assertFalse(nl._matched(none, {"ops": actual, "revises": None}, REGISTRY))
        self.assertEqual(judge(none, actual)["verdict"], "wrong-draft")


class ScoreCompareCliTests(unittest.TestCase):
    def test_score_compare_cli_do_not_invent_permutation_regressions(self):
        fwd = {"synthetic01": {"reply": {"ops": [NAME, DESC], "revises": None}, "failed": None, "ms": 1}}
        rev = {"synthetic01": {"reply": {"ops": [DESC, NAME], "revises": None}, "failed": None, "ms": 1}}
        for rec in (fwd, rev):
            s = nl.score([BOTH], rec, REGISTRY)
            self.assertEqual((s["strictAccuracy"], s["wrongDrafts"]), (1.0, 0))
        for a, b in ((fwd, rev), (rev, fwd)):
            out = nl.compare([BOTH], a, b, REGISTRY)
            self.assertEqual((out["regressed"], out["fixed"], out["newWrongDrafts"]), ([], [], []))
        changed = {"synthetic01": {"reply": {"ops": [NAME, call(id=ID, description="Other")], "revises": None}, "failed": None, "ms": 1}}
        self.assertEqual(len(nl.compare([BOTH], fwd, changed, REGISTRY)["regressed"]), 1)
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        rows = [json.loads(line) for line in CORPUS.read_text("utf-8").splitlines() if line.strip()]
        rows = [BOTH, *[r for r in rows if r["id"] != "synthetic01"][:199]]
        (tmp / "c.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        for name, rec in (("f", fwd), ("r", rev)):
            (tmp / f"{name}.jsonl").write_text(json.dumps({"id": "synthetic01", **rec["synthetic01"]}) + "\n", "utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = nl.main(["score", "--corpus", str(tmp / "c.jsonl"), "--replies", str(tmp / "r.jsonl")])
        self.assertEqual((code, json.loads(out.getvalue())["wrongDrafts"], err.getvalue()), (0, 0, ""))
        self.assertNotIn("Crisp fruit", out.getvalue())


if __name__ == "__main__":
    unittest.main()
