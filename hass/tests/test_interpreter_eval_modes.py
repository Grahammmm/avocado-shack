"""RF0300-12 tests: `interpreter_eval.py score` refuses recorder-only flags (--url, --model, --out) instead of
silently ignoring them. Synthetic fixtures only; no model, no socket; loaders/scorer/recorder are sentinels."""

import contextlib, io, json, os, unittest  # noqa: E401
from unittest import mock

from hass import interpreter_eval as ev
from hass.tests import test_interpreter_eval as base

REFUSAL = "score takes only --replies and --cases"
CANARY_URL, CANARY_MODEL, CANARY_OUT = "http://canary-url.invalid", "canary-model-name", "canary-out/file.jsonl"


def boom(*_a, **_k): raise AssertionError("work ran before the argument refusal")


def refuse(*argv, patched=True):
    """Run main (by default with every loader/scorer/recorder replaced by a raising sentinel) and expect an
    argparse refusal; returns (code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), contextlib.ExitStack() as stack:
        for name in ("load_cases", "load_replies", "load_registry", "score", "live") if patched else ():
            stack.enter_context(mock.patch.object(ev, name, boom))
        try:
            ev.main([str(a) for a in argv])
        except SystemExit as exc:
            return exc.code, out.getvalue(), err.getvalue()
    raise AssertionError("main returned instead of refusing")


class ScoreModeTests(base.EvalTestCase):
    def assertRefused(self, *argv):
        code, out, err = refuse(*argv)
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.strip().endswith(REFUSAL), err)
        for canary in (CANARY_URL, CANARY_MODEL, CANARY_OUT):
            self.assertNotIn(canary, err)

    def test_score_rejects_each_recorder_only_flag(self):
        for extra in (("--url", CANARY_URL), ("--model", CANARY_MODEL), ("--out", CANARY_OUT),
                      ("--url", CANARY_URL, "--model", CANARY_MODEL, "--out", CANARY_OUT)):
            self.assertRefused("score", "--replies", base.REPLIES, *extra)

    def test_empty_recorder_option_is_still_supplied(self):
        for extra in (("--url", ""), ("--model", ""), ("--out", ""), ("--out=",), ("--url=", "--model=")):
            self.assertRefused("score", "--replies", base.REPLIES, *extra)
        self.assertEqual(base.run("score", "--replies", base.REPLIES)[0], 0)  # omission stays accepted

    def test_refusal_precedes_unreadable_inputs_and_registry(self):
        target = self.tmp / "never-created.jsonl"
        self.assertRefused("score", "--cases", self.tmp / "no-cases", "--replies", self.tmp / "no-replies",
                           "--out", target)
        self.assertRefused("score", "--replies", "", "--model", CANARY_MODEL)  # empty replies path: refused first too
        self.assertFalse(target.exists())

    def test_existing_outside_file_is_not_touched(self):
        victim = self.tmp / "victim.jsonl"
        victim.write_bytes(b"keep me\n")
        os.chmod(victim, 0o640)
        before = (victim.read_bytes(), victim.stat().st_mode)
        missing = self.tmp / "absent.jsonl"
        code, out, err = refuse("score", "--replies", base.REPLIES, "--out", victim, patched=False)
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.strip().endswith(REFUSAL), err)
        self.assertNotIn(str(victim), err)
        self.assertEqual(refuse("score", "--replies", base.REPLIES, "--out", missing, patched=False)[0], 2)
        self.assertEqual((victim.read_bytes(), victim.stat().st_mode), before)
        self.assertFalse(missing.exists())

    def test_valid_score_output_is_unchanged(self):
        for argv in (("score", "--replies", base.REPLIES), ("score", "--cases", base.CASES, "--replies", base.REPLIES)):
            code, out, err = base.run(*argv)
            summary = json.loads(out)
            self.assertEqual((code, err, {k: summary[k] for k in ("cases", "passed", "missing", "extra")}),
                             (0, "", {"cases": 98, "passed": 95, "missing": [], "extra": []}))
            self.assertEqual([f["id"] for f in summary["failed"]], ["e06", "e13", "e25"])
        short = self.write("short.jsonl", [{"id": "e01", "reply": {"unsupported": "x"}}])
        code, out, _ = base.run("score", "--replies", short)
        self.assertEqual((code, json.loads(out)["passed"] < 72), (0, True))  # wrong/missing replies still exit 0

    def test_valid_compare_and_fake_recording_forms_remain(self):
        code, out, err = base.run("compare", "--before", base.REPLIES, "--after", base.REPLIES)
        self.assertEqual((code, err, json.loads(out)["regressed"]), (0, "", []))
        out_file = self.tmp / "rec.jsonl"
        fake = mock.Mock(side_effect=lambda *a, **k: {"recorded": 0, "failedCalls": 0})
        with mock.patch.object(ev, "live", fake):
            code, out, _ = base.run("--live", "--url", base.URL, "--model", "m", "--out", out_file)
        self.assertEqual((code, json.loads(out)), (0, {"recorded": 0, "failedCalls": 0}))
        self.assertEqual(fake.call_count, 1)


if __name__ == "__main__":
    unittest.main()
