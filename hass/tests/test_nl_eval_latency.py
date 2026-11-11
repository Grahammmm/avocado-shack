"""Offline latency report: huge admitted integer milliseconds format without OverflowError. No model, no socket."""

import contextlib, io, json, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import nl_eval as nl
from hass.ops import load_registry

CORPUS = Path(__file__).resolve().parent / "fixtures" / "nl-corpus.jsonl"
REGISTRY = load_registry()
HUGE = 10 ** 400
BIG = "1" + "0" * 397  # HUGE ms in whole seconds
ROW_HEAD = ("| Latency p50 (s) | ", "| Latency p95 (s) | ")


class LatencyReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = nl.load_corpus(CORPUS)[:1]
        cls.reply = {"ops": cls.corpus[0]["expect"]["ops"], "revises": cls.corpus[0]["expect"]["revises"]}

    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def write(self, name, **fields):
        path = self.tmp / name
        path.write_text(json.dumps({"id": self.corpus[0]["id"], "reply": self.reply, **fields}) + "\n")
        return path

    def summary(self, **fields):
        return nl.score(self.corpus, nl.load_replies(self.write("r.jsonl", **fields)), REGISTRY)

    def cells(self, text):
        return [line.split("|")[2].strip() for line in text.split("\n") if line.startswith(ROW_HEAD)]

    def test_huge_ms_report_does_not_overflow(self):
        s = self.summary(ms=HUGE)
        self.assertEqual(s["latencyMs"], {"p50": HUGE, "p95": HUGE, "max": HUGE, "calls": 1})
        self.assertEqual(self.cells(nl.report([("a", s)])), [BIG + ".0", BIG + ".0"])

    def test_huge_first_ms_wins_over_small_final_ms(self):
        s = self.summary(ms=5, firstMs=HUGE)
        self.assertEqual((s["latencyMs"]["calls"], s["latencyMs"]["max"]), (1, HUGE))
        self.assertEqual(self.cells(nl.report([("a", s)])), [BIG + ".0", BIG + ".0"])
        failed = self.summary(ms=5, firstMs=HUGE, firstFailed="timeout")
        self.assertEqual((failed["latencyMs"], failed["firstAttemptTimeouts"]), ({"p50": None, "p95": None, "max": None, "calls": 0}, 1))
        self.assertEqual(self.cells(nl.report([("a", failed)])), ["n/a", "n/a"])

    def test_overflow_fallback_rounds_integer_tenths(self):
        for extra, want in ((4, BIG + ".0"), (49, BIG + ".0"), (50, BIG + ".0"), (51, BIG + ".1"), (150, BIG + ".2"),
                            (149, BIG + ".1"), (250, BIG + ".2"), (950, "1" + "0" * 396 + "1.0")):
            with self.subTest(extra=extra):
                self.assertEqual(self.cells(nl.report([("a", self.summary(ms=HUGE + extra))])), [want, want])

    def test_ordinary_report_bytes_are_unchanged(self):
        for ms, want in ((0, "0.0"), (1050, "1.1"), (1049, "1.0"), (2500, "2.5"), (123456, "123.5")):
            with self.subTest(ms=ms):
                self.assertEqual(self.cells(nl.report([("a", self.summary(ms=ms))])), [want, want])
        self.assertEqual(self.cells(nl.report([("a", self.summary())])), ["n/a", "n/a"])

    def test_offline_cli_report_outputs_one_complete_table(self):
        huge, small = self.write("huge.jsonl", ms=HUGE), self.write("small.jsonl", ms=2500)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = nl.main(["report", "--corpus", str(CORPUS), "--run", f"huge={huge}", "--run", f"small={small}"])
        lines = out.getvalue().split("\n")
        self.assertEqual((code, err.getvalue(), lines[-1], lines[0]), (0, "", "", "| Measure | huge | small |"))
        self.assertIn(f"| Latency p95 (s) | {BIG}.0 | 2.5 |", lines)
        self.assertIn(f"| Latency p50 (s) | {BIG}.0 | 2.5 |", lines)


if __name__ == "__main__":
    unittest.main()
