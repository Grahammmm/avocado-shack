"""RF0111-12: a recorded failure is shown as a bounded code, never as the recorded text. No model, no socket."""

import contextlib, io, json, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import nl_eval as nl
from hass.ops import load_registry
from hass.tests.test_nl_eval import CORPUS, ideal

REGISTRY, MARK = load_registry(), "PRIVATE_SENTINEL_DO_NOT_ECHO"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = nl.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class FailureCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.corpus = nl.load_corpus(CORPUS)
        self.case = next(c for c in self.corpus if "ops" in c["expect"])

    def write(self, name, failed=None, extra=None):
        rows = []
        for c in self.corpus:
            row = {"id": c["id"], "reply": ideal(c), "failed": None, "ms": 5}
            if c is self.case: row.update({"reply": None, "failed": failed, **(extra or {})})
            rows.append(row)
        path = self.tmp / name
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        return path

    def why(self, failed, reply=None, **extra):
        return nl.judge(self.case, {"reply": reply, "failed": failed, "ms": 5, **extra}, REGISTRY)

    def test_unknown_recorded_failure_never_echoes_text(self):
        text = f"{MARK} {self.case['text']}\r\nC:\\secret https://x.example/é"
        path = self.write("f.jsonl", text)
        loaded = nl.load_replies(path)
        self.assertEqual(loaded[self.case["id"]]["failed"], text)  # evidence is not rewritten
        j = nl.judge(self.case, loaded[self.case["id"]], REGISTRY)
        self.assertEqual(j, {"verdict": "call-failed", "kind": "none", "intent": False, "why": "call failed: unknown"})
        code, out, err = run("score", "--replies", path)
        self.assertEqual((code, err), (0, ""))
        summary = json.loads(out)
        self.assertEqual(summary["callsFailed"], 1)
        for bad in (MARK, self.case["text"], "secret", "https://"): self.assertNotIn(bad, out)

    def test_score_and_compare_cli_keep_exit_codes_without_failure_text(self):
        before, after = self.write("b.jsonl", None, {"reply": ideal(self.case)}), self.write("a.jsonl", MARK + self.case["text"])
        self.assertEqual(run("compare", "--before", before, "--after", before)[0], 0)
        code, out, err = run("compare", "--before", before, "--after", after)
        self.assertEqual((code, err), (1, ""))
        self.assertIn(self.case["id"], json.dumps(json.loads(out)["regressed"]))
        for bad in (MARK, self.case["text"]): self.assertNotIn(bad, out)

    def test_known_codes_and_ascii_http_triplets_remain_exact(self):
        for ok in ("clock", "request", "timeout", "connect", "shape", "not-json", "too-large", "unknown", "error", "contract", "http-400", "http-503"):
            self.assertEqual(self.why(ok)["why"], f"call failed: {ok}")
        for bad in ("http-４００", "http-+40", "http-40", "http-4000", "HTTP-400", "Timeout", " timeout", "timeout\n", "timeout: " + MARK, "http-400 " + MARK, "x" * 100000):
            self.assertEqual(self.why(bad)["why"], "call failed: unknown", repr(bad[:20]))

    def test_failure_precedence_and_first_attempt_accounting_do_not_change(self):
        self.assertEqual(self.why(MARK, reply=ideal(self.case))["verdict"], "call-failed")
        for empty in (None, ""):
            self.assertNotEqual(self.why(empty, reply=ideal(self.case))["verdict"], "call-failed")
        path = self.write("r.jsonl", None, {"reply": ideal(self.case), "firstFailed": MARK, "firstMs": 7})
        summary = json.loads(run("score", "--replies", path)[1])
        self.assertEqual((summary["callsFailed"], summary["firstAttemptFailures"]), (0, 1))
        self.assertNotIn(MARK, json.dumps(summary))
