"""RF1900-10: load_corpus refuses an expectation (primary or alternative) longer than interpret_check.MAX_OPS. No model, no socket."""

import contextlib, io, json, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import interpret_check, nl_eval as nl
from hass.ops import load_registry

CORPUS = Path(__file__).resolve().parent / "fixtures" / "nl-corpus.jsonl"
REGISTRY = load_registry()
MAX = interpret_check.MAX_OPS
CANARY = "zz-canary-text-9137"


def calls(count, prefix="synthetic"):
    return [{"op": "product.hide", "args": {"id": f"{prefix}-{i}"}} for i in range(count)]


def draft(count): return {"ops": calls(count), "revises": None}


class ExpectedLimitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.lines = CORPUS.read_text("utf-8").splitlines()

    def write(self, changes, blanks=0, name="c.jsonl"):
        """Copy of the corpus with row i (0-based) updated; `blanks` blank lines are put before row 0 so physical lines shift."""
        lines = list(self.lines)
        for at, change in changes.items(): lines[at] = json.dumps({**json.loads(lines[at]), **change})
        path = self.tmp / name
        path.write_text("\n" * blanks + "\n".join(lines) + "\n", "utf-8")
        return path

    def refused(self, path):
        with self.assertRaises(nl.EvalError) as ctx: nl.load_corpus(path)
        return str(ctx.exception)

    def message(self, line): return f"corpus line {line}: more than {MAX} expected ops"

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = nl.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def test_primary_expected_ops_above_runtime_cap_are_refused(self):
        self.assertEqual(MAX, 20)
        self.assertEqual(self.refused(self.write({0: {"expect": draft(MAX + 1)}})), self.message(1))
        self.assertEqual(self.refused(self.write({3: {"expect": draft(MAX + 5)}})), self.message(4))

    def test_every_alternative_is_checked_even_with_valid_primary(self):
        question = {"expect": {"question": True}, "ask": True, "refuse": False}
        self.assertEqual(self.refused(self.write({0: {**question, "also": [draft(MAX + 1)]}})), self.message(1))
        self.assertEqual(self.refused(self.write({0: {**question, "also": [draft(2), draft(MAX + 1)]}})), self.message(1))
        self.assertEqual(self.refused(self.write({0: {"also": [draft(MAX + 1)]}})), self.message(1))  # primary draft kept

    def test_exact_cap_and_no_draft_expectations_still_load(self):
        question = {"expect": {"question": True}, "ask": True, "refuse": False}
        refusal = {"expect": {"unsupported": True}, "ask": False, "refuse": True}
        for change in ({"expect": draft(MAX)}, {"expect": draft(MAX - 1)}, {"also": [draft(MAX)]}, {**question, "also": [draft(MAX), {"unsupported": True}]},
                       {**refusal, "also": [{"question": True}, draft(MAX - 1)]}, question, refusal):
            rows = nl.load_corpus(self.write({0: change}))
            self.assertEqual(len(rows), len(self.lines))
            for key, value in change.items(): self.assertEqual(rows[0][key], value)
        self.assertEqual(nl.load_corpus(CORPUS), [json.loads(x) for x in self.lines if x.strip()])

    def test_exact_cap_draft_is_admitted_by_the_runtime_checker_but_one_more_is_not(self):
        reply = {"ops": calls(MAX), "revises": None}
        rows = nl.load_corpus(self.write({0: {"expect": reply}}))
        self.assertEqual(interpret_check.check(reply, REGISTRY, set()).get("ops"), reply["ops"])
        self.assertIn("question", interpret_check.check(draft(MAX + 1), REGISTRY, set()))
        self.assertEqual(rows[0]["expect"], reply)

    def test_zero_and_malformed_ops_keep_existing_shape_diagnostic(self):
        for bad in ({"ops": [], "revises": None}, {"ops": "x", "revises": None}, {"ops": calls(MAX + 1) + ["junk"], "revises": None},
                    {"ops": calls(MAX + 1), "revises": 7}):
            self.assertEqual(self.refused(self.write({0: {"expect": bad}})), "corpus line 1: bad expect")
        self.assertEqual(self.refused(self.write({0: {"also": [{"ops": calls(MAX + 1) + ["junk"], "revises": None}]}})), "corpus line 1: bad expect")
        self.assertEqual(self.refused(self.write({0: {"expect": {"ops": calls(MAX + 1), "revises": "Q9"}}})), "corpus line 1: revises names no pending draft")
        self.assertEqual(self.refused(self.write({0: {"expect": draft(MAX + 1), "pending": [{"code": "A1"}]}, 1: {}})), self.message(1))

    def test_physical_line_and_private_cli_refusal(self):
        big = {"ops": [{"op": f"{CANARY}.op", "args": {f"{CANARY}-arg": CANARY, "id": f"{CANARY}-{i}"}} for i in range(MAX + 1)], "revises": None}
        for at, blanks in ((0, 0), (0, 3), (7, 2)):
            path = self.write({at: {"expect": big, "text": CANARY}}, blanks=blanks)
            line = at + 1 + blanks
            self.assertEqual(self.refused(path), self.message(line))
            replies, out_path = self.tmp / "missing-replies.jsonl", self.tmp / "report.md"
            for argv in (("score", "--replies", replies, "--corpus", path), ("report", "--run", f"a={replies}", "--corpus", path),
                         ("compare", "--before", replies, "--after", replies, "--corpus", path)):
                code, out, err = self.cli(*argv)
                self.assertEqual((code, out, err), (2, "", f"nl_eval: {self.message(line)}\n"), argv[0])
            self.assertFalse(out_path.exists())
            self.assertFalse(replies.exists())

    def test_valid_corpus_scoring_and_comparison_remain_exact(self):
        rows = nl.load_corpus(CORPUS)
        ideal = {c["id"]: {"reply": ({"ops": c["expect"]["ops"], "revises": c["expect"]["revises"]} if "ops" in c["expect"]
                                     else {"question": "Which one?"} if "question" in c["expect"] else {"unsupported": "No."}),
                           "failed": None, "ms": 5} for c in rows}
        replies = self.tmp / "replies.jsonl"
        replies.write_text("".join(json.dumps({"id": k, **v}) + "\n" for k, v in ideal.items()), "utf-8")
        code, out, err = self.cli("score", "--replies", replies)
        self.assertEqual((code, err), (0, ""))
        summary = json.loads(out)
        self.assertEqual(summary["scored"], len(rows))
        self.assertEqual(summary["schemaValidRate"], 1.0)
        code, out, err = self.cli("compare", "--before", replies, "--after", replies)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["regressed"], [])


if __name__ == "__main__":
    unittest.main()
