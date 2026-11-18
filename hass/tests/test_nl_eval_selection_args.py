"""RF1911-12: the eval CLI refuses zero and negative --every/--limit/--sample before reading anything. Offline, synthetic."""
import contextlib, io, unittest  # noqa: E401
from unittest import mock

from hass import nl_eval as nl

CASES = [{"id": f"c{i}", "intent": f"i{i % 2}", "text": "t"} for i in range(5)]


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try: code = nl.main([str(a) for a in argv])
        except SystemExit as e: code = e.code
    return code, err.getvalue()


LIVE = ("--live", "--url", "http://127.0.0.1:1", "--model", "m", "--out", "/nonexistent/never.jsonl")


class SelectionArgs(unittest.TestCase):
    def test_nonpositive_selectors_refuse_before_reads(self):
        with mock.patch.object(nl, "load_corpus") as corpus, mock.patch.object(nl, "load_registry") as reg, mock.patch.object(nl, "live") as live:
            for flag in ("--every", "--limit", "--sample"):
                for value in ("0", "-1"):
                    with self.subTest(flag=flag, value=value):
                        code, err = run(*LIVE, flag, value)
                        self.assertEqual(code, 2)
                        self.assertIn("positive integer", err)
            for mocked in (corpus, reg, live): mocked.assert_not_called()

    def test_noninteger_selectors_still_refuse(self):
        with mock.patch.object(nl, "load_corpus") as corpus, mock.patch.object(nl, "live") as live:
            for flag in ("--every", "--limit", "--sample"):
                for value in ("abc", "1.5"):
                    with self.subTest(flag=flag, value=value):
                        self.assertEqual(run(*LIVE, flag, value)[0], 2)
            corpus.assert_not_called()
            live.assert_not_called()

    def selected(self, *flags):
        with mock.patch.object(nl, "load_corpus", return_value=CASES), mock.patch.object(nl, "load_registry"), \
                mock.patch.object(nl, "live", return_value={"recorded": 0}) as live:
            code, _ = run(*LIVE, *flags)
        self.assertEqual(code, 0)
        return [c["id"] for c in live.call_args.args[0]]

    def test_positive_and_omitted_selection_controls(self):
        self.assertEqual(self.selected(), ["c0", "c1", "c2", "c3", "c4"])
        self.assertEqual(self.selected("--every", "1"), ["c0", "c1", "c2", "c3", "c4"])
        self.assertEqual(self.selected("--every", "2"), ["c0", "c2", "c4"])
        self.assertEqual(self.selected("--every", "99"), ["c0"])
        self.assertEqual(self.selected("--limit", "99"), ["c0", "c1", "c2", "c3", "c4"])
        self.assertEqual(self.selected("--every", "2", "--limit", "2"), ["c0", "c2"])
        self.assertEqual(self.selected("--sample", "99"), ["c0", "c1", "c2", "c3", "c4"])

    def test_small_positive_sample_keeps_existing_intent_floor(self):
        self.assertEqual(self.selected("--sample", "1"), [c["id"] for c in nl.stratified(CASES, 1)])
        self.assertEqual(len({c["intent"] for c in nl.stratified(CASES, 1)}), 2)


if __name__ == "__main__":
    unittest.main()
