"""RF2210-13: schemaValidRate counts only replies with an admitted top-level envelope. No model, no socket."""

import contextlib, copy, io, json, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import nl_eval as nl
from hass.ops import load_registry

CORPUS = Path(__file__).resolve().parent / "fixtures" / "nl-corpus.jsonl"
REGISTRY = load_registry()
ASK = next(c for c in nl.load_corpus(CORPUS) if c["ask"])
REFUSE = next(c for c in nl.load_corpus(CORPUS) if c["refuse"])


def rate(reply, case=ASK, failed=None, **extra):
    return nl.score([case], {case["id"]: {"reply": reply, "failed": failed, "ms": 5, **extra}}, REGISTRY)


class SchemaRateTests(unittest.TestCase):
    def test_question_and_refusal_require_exact_nonblank_text_envelope(self):
        for key in ("question", "unsupported"):
            for bad in (None, True, 3, "", "  ", ["x"], {"a": 1}):
                s = rate({key: bad})
                self.assertEqual((s["jsonValidRate"], s["schemaValidRate"]), (1.0, 0.0), (key, bad))
            for extra in ({key: "Which?", "ops": []}, {"question": "Which?", "unsupported": "No"}, {key: "Which?", "x": 1}):
                self.assertEqual(rate(extra)["schemaValidRate"], 0.0, extra)
            for good in ("Which one?", "  padded  "):
                reply = {key: good}
                self.assertEqual(rate(reply)["schemaValidRate"], 1.0)
                self.assertEqual(reply, {key: good})

    def test_ops_envelope_requires_list_and_revision_shape(self):
        for bad in ({"ops": "x", "revises": None}, {"ops": []}, {"revises": None}, {"ops": [], "revises": 3}, {"ops": [], "revises": True},
                    {"ops": [], "revises": ["a"]}, {"ops": [], "revises": {}}, {"ops": [], "revises": None, "x": 1}):
            self.assertEqual(rate(bad)["schemaValidRate"], 0.0, bad)
        for good in ({"ops": [], "revises": None}, {"ops": [], "revises": "A1"}, {"ops": ["junk"], "revises": None},
                     {"ops": [{"op": "no.such", "args": {}}], "revises": "Z9"}):
            self.assertEqual(rate(good)["schemaValidRate"], 1.0, good)

    def test_schema_measures_raw_reply_not_fallback_or_expectation(self):
        fallback = nl._checked(None)
        self.assertEqual(rate({"question": None})["schemaValidRate"], 0.0)
        self.assertEqual(rate(fallback)["schemaValidRate"], 1.0)
        same = {"unsupported": "That is not a change I can make."}
        a, b = rate(same, ASK), rate(same, REFUSE)
        self.assertEqual((a["schemaValidRate"], b["schemaValidRate"]), (1.0, 1.0))
        self.assertNotEqual(a["verdicts"], b["verdicts"])

    def test_failed_missing_and_retry_denominators_are_preserved(self):
        self.assertIsNone(nl.score([ASK], {}, REGISTRY)["schemaValidRate"])
        self.assertEqual(rate({"question": "Which?"}, failed="timeout")["schemaValidRate"], 0.0)
        self.assertEqual(rate({"question": "Which?"}, firstFailed="timeout", firstMs=None)["schemaValidRate"], 1.0)
        corpus = [ASK, REFUSE, next(c for c in nl.load_corpus(CORPUS) if c not in (ASK, REFUSE))]
        replies = {ASK["id"]: {"reply": {"question": "Which?"}, "failed": None, "ms": 5},
                   REFUSE["id"]: {"reply": {"question": None}, "failed": None, "ms": 5}}
        s = nl.score(corpus, replies, REGISTRY)
        self.assertEqual((s["scored"], s["schemaValidRate"], s["jsonValidRate"], len(s["missing"])), (2, 0.5, 1.0, 1))

    def test_metric_repair_changes_no_verdict_or_other_summary_field(self):
        reply = {"question": None}
        before = copy.deepcopy(reply)
        s, again = rate(reply), rate(reply)
        self.assertEqual(s, again)
        self.assertEqual(reply, before)
        self.assertEqual(s["verdicts"]["kind-mismatch"], 1)
        self.assertEqual(s["jsonValidRate"], 1.0)
        good = rate(nl._checked(None))  # what the conversation turns the bad reply into
        self.assertEqual({k: v for k, v in s.items() if k != "schemaValidRate"}, {k: v for k, v in good.items() if k != "schemaValidRate"})

    def test_offline_score_cli_reports_zero_for_malformed_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            for reply, want in (({"question": None}, 0.0), ({"question": "Which?"}, 1.0)):
                path = Path(tmp) / "r.jsonl"
                path.write_text(json.dumps({"id": ASK["id"], "reply": reply, "failed": None, "ms": 5}) + "\n", "utf-8")
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = nl.main(["score", "--replies", str(path)])
                s = json.loads(out.getvalue())
                self.assertEqual((code, err.getvalue(), s["scored"], s["jsonValidRate"], s["schemaValidRate"]), (0, "", 1, 1.0, want))
                self.assertNotIn(ASK["text"], out.getvalue())


if __name__ == "__main__":
    unittest.main()
