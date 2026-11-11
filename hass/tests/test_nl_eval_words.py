"""RF0845-13 tests: mustContain words are judged against drafted argument VALUES, not op names, arg names or JSON syntax.
Real registry, judge, score, compare and offline main; no model, no socket."""

import contextlib, io, json, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import nl_eval as nl
from hass.ops import load_registry

REGISTRY, CORPUS = load_registry(), Path(__file__).resolve().parent / "fixtures" / "nl-corpus.jsonl"
MISSING = {"verdict": "wrong-draft", "kind": "ops", "intent": True, "why": "required words missing"}
PASS = {"verdict": "pass", "kind": "ops", "intent": True, "why": None}


def case(ops, must, cid="n001", **extra):
    return {"id": cid, "text": "synthetic", "intent": "store", "expect": {"ops": ops, "revises": None}, "ask": False, "refuse": False,
            "pending": [], "mustContain": must, **extra}


def draft(op, **args): return {"ops": [{"op": op, "args": args}], "revises": None}  # noqa: E704
def record(reply): return {"reply": reply, "failed": None, "ms": 1}  # noqa: E704
def verdict(c, reply): return nl.judge(c, record(reply), REGISTRY)  # noqa: E704


NOTICE = case([{"op": "store.set_notice", "args": {}}], ["text"])
BAD, GOOD = draft("store.set_notice", text="Closed today."), draft("store.set_notice", text="Read this TEXT.")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = nl.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class ValueOnlyContentTests(unittest.TestCase):
    def test_argument_key_is_not_required_content(self):
        self.assertEqual(verdict(NOTICE, BAD), MISSING)
        self.assertEqual(verdict(NOTICE, GOOD), PASS)

    def test_operation_name_is_not_required_content(self):
        c = case([{"op": "store.set_notice", "args": {}}], ["set_notice"])
        self.assertEqual(verdict(c, BAD), MISSING)
        self.assertEqual(verdict(c, draft("store.set_notice", text="Use set_notice here")), PASS)

    def test_nested_keys_and_serialization_are_not_prose(self):
        value = {"key": {"inner": 'Caf\u00e9 "Q"\nline', "n": [12, True, None, "Hours", {}, []]}, "empty": {}}
        self.assertEqual(list(nl._leaves(value)), ['caf\u00e9 "q"\nline', "12", "true", "null", "hours"])
        texts = nl._texts_of({"ops": [{"op": "store.set_hours", "args": value}], "revises": None})
        for absent in ("key", "inner", "store", "args", "\\n", "\\u00e9", "[", "{", '\\"'): self.assertFalse(any(absent in t for t in texts), absent)

    def test_required_phrase_cannot_span_argument_leaves(self):
        c = case([{"op": "store.set_headline", "args": {}}], ["fresh eggs"])
        self.assertEqual(verdict(c, draft("store.set_headline", first="fresh", second="eggs")), MISSING)
        self.assertEqual(verdict(c, draft("store.set_headline", first="Just FRESH EGGS", second="x")), PASS)
        hours = case([{"op": "store.set_hours", "args": {}}], ["10am to"])
        self.assertEqual(verdict(hours, draft("store.set_hours", hours=["10am", "to 4pm"])), MISSING)
        self.assertEqual(verdict(hours, draft("store.set_hours", hours=["Daily 10am to 4pm"])), PASS)
        two_ops = {"ops": [{"op": "store.set_headline", "args": {"first": "fresh", "second": "x"}},
                           {"op": "store.set_story", "args": {"text": "eggs"}}], "revises": None}
        spanning = case([{"op": "store.set_headline", "args": {}}, {"op": "store.set_story", "args": {}}], ["fresh eggs"])
        self.assertEqual(verdict(spanning, two_ops), MISSING)
        spanning["mustContain"] = ["fresh", "eggs"]  # different required words may sit in different leaves and ops
        self.assertEqual(verdict(spanning, two_ops), PASS)

    def test_question_refusal_and_absent_requirement_unchanged(self):
        ask = {"id": "n002", "text": "t", "intent": "vague", "expect": {"question": True}, "ask": True, "refuse": False, "pending": [], "mustContain": ["Which"]}
        self.assertEqual(verdict(ask, {"question": "Which one?"}), {"verdict": "pass", "kind": "question", "intent": True, "why": None})
        self.assertEqual(verdict(ask, {"question": "Say again?"})["verdict"], "content-miss")
        no_words = case([{"op": "store.set_notice", "args": {}}], [])
        del no_words["mustContain"]
        self.assertEqual(verdict(no_words, BAD), PASS)
        also = case([{"op": "store.set_notice", "args": {}}], ["zzz"], also=[{"question": True}])
        self.assertEqual(verdict(also, {"question": "zzz?"})["verdict"], "pass")
        self.assertEqual(verdict(also, BAD)["verdict"], "wrong-draft")
        self.assertEqual(verdict(case([{"op": "store.set_notice", "args": {}}], ["cocktail"]), draft("store.set_notice", text="Cocktails at five"))["verdict"], "pass")
        failed = nl.judge(NOTICE, {"reply": BAD, "failed": "timeout", "ms": 1}, REGISTRY)
        self.assertEqual(failed["verdict"], "call-failed")
        before = json.dumps(BAD, sort_keys=True)
        verdict(NOTICE, BAD)
        self.assertEqual(json.dumps(BAD, sort_keys=True), before)

    def test_score_and_compare_expose_missing_content(self):
        corpus, bad, good = [NOTICE], {"n001": record(BAD)}, {"n001": record(GOOD)}
        s = nl.score(corpus, bad, REGISTRY)
        self.assertEqual((s["strictAccuracy"], s["wrongDrafts"], s["verdicts"]["wrong-draft"], s["verdicts"]["pass"]), (0.0, 1, 1, 0))
        down = nl.compare(corpus, good, bad, REGISTRY)
        self.assertEqual((down["compared"], down["regressed"], down["newWrongDrafts"], down["fixed"]), (1, [{"id": "n001", "why": "required words missing"}], ["n001"], []))
        up = nl.compare(corpus, bad, good, REGISTRY)
        self.assertEqual((up["compared"], up["regressed"], up["fixed"]), (1, [], ["n001"]))

    def test_offline_cli_scores_and_compares_value_only(self):
        rows = [json.loads(line) for line in CORPUS.read_text().splitlines() if line.strip()]
        rows[0] = {**NOTICE, "id": rows[0]["id"]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "corpus.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            for name, reply in (("bad", BAD), ("good", GOOD)): (root / f"{name}.jsonl").write_text(json.dumps({"id": rows[0]["id"], **record(reply)}) + "\n")
            corpus = ("--corpus", root / "corpus.jsonl")
            code, out, err = run("score", *corpus, "--replies", root / "bad.jsonl")
            summary = json.loads(out)
            self.assertEqual((code, summary["scored"], summary["strictAccuracy"], summary["wrongDrafts"], err), (0, 1, 0.0, 1, ""))
            code, out, err = run("score", *corpus, "--replies", root / "good.jsonl")
            self.assertEqual((code, json.loads(out)["strictAccuracy"], json.loads(out)["wrongDrafts"], err), (0, 1.0, 0, ""))
            code, out, err = run("compare", *corpus, "--before", root / "good.jsonl", "--after", root / "bad.jsonl")
            self.assertEqual((code, json.loads(out)["regressed"], err), (1, [{"id": rows[0]["id"], "why": "required words missing"}], ""))
            code, out, err = run("compare", *corpus, "--before", root / "bad.jsonl", "--after", root / "good.jsonl")
            self.assertEqual((code, json.loads(out)["fixed"], err), (0, [rows[0]["id"]], ""))
            for text in ("Closed today.", "Read this"): self.assertNotIn(text, out + err)


if __name__ == "__main__":
    unittest.main()
