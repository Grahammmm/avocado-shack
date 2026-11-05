"""AV1922-04 tests: `interpreter_eval.py compare` classifies each case between two recorded reply files with the
existing scorer. Synthetic reply files in a temporary directory; no model, no socket."""

import json, subprocess, sys, unittest  # noqa: E401
from unittest import mock

from hass import interpreter_eval as ev
from hass.tests import test_interpreter_eval as base

CANARY = "CANARY-reply-text"


class CompareTests(base.EvalTestCase):
    def mk(self, drop=(), **change):
        rows = {i: r for i, r in self.replies_map().items() if i not in drop}
        rows.update(change)
        return rows

    def replies_map(self): return dict(self.replies)

    def file(self, name, rows):
        return self.write(name, [{"id": i, "reply": r} for i, r in rows.items()])

    def cmp(self, before, after, *extra):
        return base.run("compare", "--before", self.file("b.jsonl", before), "--after", self.file("a.jsonl", after), *extra)

    def test_four_outcomes_use_after_reason_in_case_order(self):
        after = self.mk(e01={"unsupported": CANARY}, e25={"question": CANARY}, e06={"unsupported": CANARY})
        after = dict(reversed(list(after.items())))  # reply-file order must not matter
        code, out, err = self.cmp(self.replies, after)
        self.assertEqual((code, err, out.count("\n")), (1, "", 1))
        self.assertEqual(json.loads(out), {
            "regressed": [{"id": "e01", "why": "expected ops, got unsupported"}], "fixed": ["e25"],
            "stillFailing": 2, "passedBoth": 65, "missing": {"before": [], "after": []}})
        self.assertNotIn(CANARY, out)
        self.assertEqual(65 + 2 + 1 + 1, len(self.cases))

    def test_pure_compare_scores_each_side_once_with_same_objects(self):
        with mock.patch.object(ev, "score", wraps=ev.score) as spy:
            ev.compare(self.cases, self.replies, self.replies, base.REGISTRY)
        self.assertEqual([c.args[0] is self.cases and c.args[2] is base.REGISTRY for c in spy.call_args_list], [True, True])

    def test_identical_inputs_have_no_changes_and_exit_0(self):
        code, out, err = self.cmp(self.replies, self.replies)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), {"regressed": [], "fixed": [], "stillFailing": 3, "passedBoth": 66,
                                           "missing": {"before": [], "after": []}})

    def test_fixed_or_still_failing_only_exits_0_and_one_regression_exits_1(self):
        fixed = self.cmp(self.replies, self.replies_with(e25={"question": "Which?"}))
        self.assertEqual((fixed[0], json.loads(fixed[1])["fixed"]), (0, ["e25"]))
        both = self.cmp(self.replies, self.replies_with(e25={"question": "Which?"}, e01={"unsupported": "x"}))
        self.assertEqual(both[0], 1)  # a fix elsewhere does not excuse a regression
        self.assertEqual(json.loads(both[1])["fixed"], ["e25"])

    def replies_with(self, **change): return self.mk(**change)

    def test_missing_ids_are_per_side_and_never_classified(self):
        code, out, _ = self.cmp(self.mk(drop=("e03", "e04")), self.mk(drop=("e04", "e06")))
        got = json.loads(out)
        self.assertEqual((code, got["missing"]), (0, {"before": ["e03", "e04"], "after": ["e04", "e06"]}))
        self.assertEqual((got["regressed"], got["fixed"], got["stillFailing"], got["passedBoth"]), ([], [], 2, 64))
        code, out, _ = self.cmp({}, {})  # both empty: everything missing, nothing compared
        got = json.loads(out)
        self.assertEqual((code, got["stillFailing"], got["passedBoth"], len(got["missing"]["after"])), (0, 0, 0, 69))

    def test_extra_reply_ids_are_ignored(self):
        code, out, _ = self.cmp(self.mk(zz9={"unsupported": "x"}), self.replies)
        self.assertEqual((code, json.loads(out)["passedBoth"]), (0, 66))
        self.assertNotIn("zz9", out)

    def test_explicit_cases_path_and_reason_is_the_scorers(self):
        code, out, _ = self.cmp(self.replies, self.replies, "--cases", base.CASES)
        self.assertEqual(code, 0)
        # a regression reason is exactly what score gives for the after reply
        bad = {"ops": [{"op": "product.hide", "args": {}}], "revises": None}
        want = self.why("e01", bad)
        got = json.loads(self.cmp(self.replies, self.mk(e01=bad))[1])["regressed"]
        self.assertEqual(got, [{"id": "e01", "why": want[0]}])

    def test_invalid_input_exits_2_with_no_summary(self):
        good = self.file("good.jsonl", self.replies)
        bad = self.write("bad.jsonl", ['{"id": "e01", "reply": {}}', "not json"])
        for args in (("--before", good, "--after", bad), ("--before", bad, "--after", good),
                     ("--before", good, "--after", self.tmp / "missing.jsonl")):
            code, out, err = base.run("compare", *args)
            self.assertEqual((code, out), (2, ""))
            self.assertTrue(err.startswith("replies") and "Traceback" not in err, err)
        dup = self.write("dup.jsonl", ['{"id": "e01", "reply": {}}', '{"id": "e01", "reply": {}}'])
        self.assertEqual(base.run("compare", "--before", good, "--after", dup)[::2], (2, "replies line 2: duplicate id"))
        short = self.write("short.jsonl", self.rows[:5])
        code, out, err = base.run("compare", "--before", good, "--after", good, "--cases", short)
        self.assertEqual((code, out, err), (2, "", "cases: 5 cases, expected 69"))

    def test_mixed_modes_and_missing_arguments_exit_2_before_any_work(self):
        good = self.file("good.jsonl", self.replies)
        bad_argv = [("compare",), ("compare", "--before", good), ("compare", "--after", good),
                    ("compare", "--before", good, "--after", good, "--replies", good),
                    ("compare", "--before", good, "--after", good, "--out", self.tmp / "o"),
                    ("compare", "--before", good, "--after", good, "--url", base.URL),
                    ("compare", "--before", good, "--after", good, "--model", "m"),
                    ("compare", "--before", good, "--after", good, "--live"),
                    ("score", "--replies", good, "--before", good), ("score", "--replies", good, "--after", good),
                    ("--live", "--url", base.URL, "--model", "m", "--out", self.tmp / "o2", "--before", good)]
        for argv in bad_argv:
            with mock.patch.object(ev, "load_cases") as cases, mock.patch.object(ev, "live") as live:
                with self.assertRaises(SystemExit) as stop: base.run(*argv)
            self.assertEqual(stop.exception.code, 2, argv)
            cases.assert_not_called(), live.assert_not_called()
        self.assertEqual(base.scored(base.CASES, base.REPLIES)[0], 0)  # score is unchanged

    def test_never_prints_case_text_or_writes_files(self):
        before_bytes = self.file("b.jsonl", self.replies).read_bytes()
        self.file("a.jsonl", self.mk(e01={"unsupported": CANARY}))
        names = sorted(p.name for p in self.tmp.iterdir())
        code, out, err = self.cmp(self.replies, self.mk(e01={"unsupported": CANARY}))
        self.assertEqual(code, 1)
        for c in self.cases: self.assertNotIn(c["text"], out + err)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), names)
        self.assertEqual((self.tmp / "b.jsonl").read_bytes(), before_bytes)

    def test_real_cli_exit_codes(self):
        same = self.file("same.jsonl", self.replies)
        worse = self.file("worse.jsonl", self.mk(e01={"unsupported": "x"}))
        run = lambda *a: subprocess.run([sys.executable, "-B", str(base.Path(ev.__file__)), "compare", *map(str, a)],  # noqa: E731
                                        capture_output=True, text=True)
        self.assertEqual(run("--before", same, "--after", same).returncode, 0)
        r = run("--before", same, "--after", worse)
        self.assertEqual((r.returncode, len(r.stdout.splitlines())), (1, 1))
        self.assertEqual(run("--before", same, "--after", self.tmp / "none").returncode, 2)


if __name__ == "__main__":
    unittest.main()
