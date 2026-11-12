"""RF1651-13 tests: label_eval refuses options of the other mode before any input is read or anything is recorded."""

import contextlib, io, json, os, stat, unittest  # noqa: E401
from unittest import mock

from hass import label_eval as ev
from hass.tests import test_label_eval as base

SCORE_ERR = "score does not accept --url, --model, --photos, --out or --api"
LIVE_ERR = "--live does not accept --replies"
CANARY = "ZQXCANARY"


class Modes(base.Base):
    def setUp(self):
        super().setUp()
        self.photos, self.calls = self.tmp / "photos", []
        self.photos.mkdir()
        for i, case in enumerate(self.cases): (self.photos / case["photo"]).write_bytes(b"\xff\xd8synthetic-%d" % i)
        self.replies = self.write("r.jsonl", [{"id": k, "reply": v} for k, v in self.perfect().items()])
        self.out = self.tmp / "out.jsonl"

    def transport(self, url, body, headers, timeout):
        self.calls.append(json.loads(body))
        reply = {"name": "n", "category": "fruit"}
        return 200, json.dumps({"done": True, "message": {"content": json.dumps(reply)}}).encode()

    def refuse(self, *argv):
        """Run main with raising spies on every work seam; return (exit code, stdout, stderr)."""
        boom = AssertionError("work started before mode admission")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            for name in ("load_cases", "load_replies", "catalog_categories", "score", "live", "_read_photo", "LabelReader"):
                stack.enter_context(mock.patch.object(ev, name, side_effect=boom))
            stack.enter_context(mock.patch.object(ev.tempfile, "mkstemp", side_effect=boom))
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm: ev.main([str(a) for a in argv], transport=self.transport)
        return cm.exception.code, out.getvalue(), err.getvalue()

    def assertRefused(self, argv, message):
        code, out, err = self.refuse(*argv)
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.rstrip().endswith(f"error: {message}"), err)
        self.assertIn("usage:", err)
        self.assertEqual(err.count("error:"), 1)
        self.assertEqual(self.calls, [])
        return err

    def score_args(self, *extra): return ("score", "--cases", base.FIXTURE, "--replies", self.replies, *extra)

    def live_args(self, *extra):
        return ("--live", "--url", base.URL, "--model", "m", "--photos", self.photos, "--out", self.out, "--cases", base.FIXTURE, *extra)

    def test_score_rejects_each_recording_option_before_work(self):
        for extra in (("--url", base.URL), ("--model", "m"), ("--photos", self.photos), ("--out", self.out), ("--api", "ollama"), ("--api", "openai")):
            with self.subTest(extra=extra): self.assertRefused(self.score_args(*extra), SCORE_ERR)
        self.assertFalse(self.out.exists())

    def test_explicit_empty_is_not_omission(self):
        for flag in ("--url", "--model", "--photos", "--out"):
            with self.subTest(flag=flag, form="separate"): self.assertRefused(self.score_args(flag, ""), SCORE_ERR)
            with self.subTest(flag=flag, form="equals"): self.assertRefused(self.score_args(f"{flag}="), SCORE_ERR)
        code, out, err = base.run(*self.score_args())
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["cases"], len(self.cases))

    def test_live_rejects_replies_before_photo_or_model_work(self):
        sentinel = self.tmp / "sentinel.jsonl"
        sentinel.write_bytes(b"keep\n")
        for replies in (sentinel, self.tmp / "absent.jsonl", ""):
            with self.subTest(replies=str(replies)): self.assertRefused(self.live_args("--replies", replies), LIVE_ERR)
        self.assertRefused(self.live_args("--replies="), LIVE_ERR)
        self.assertEqual((sentinel.read_bytes(), self.out.exists(), [p.name for p in self.tmp.glob(".label-eval-*")]), (b"keep\n", False, []))

    def test_invalid_mode_precedes_unreadable_inputs(self):
        absent = self.tmp / "absent.jsonl"
        bad = self.write("bad.jsonl", ["{not json"])
        self.assertRefused(("score", "--cases", absent, "--replies", absent, "--url", base.URL), SCORE_ERR)
        self.assertRefused(("score", "--cases", bad, "--replies", self.replies, "--model", "m"), SCORE_ERR)
        self.assertRefused(("score", "--url", "u", "--model", "m", "--photos", "p", "--out", "o", "--api", "openai"), SCORE_ERR)
        self.assertRefused(("--live", "--cases", absent, "--replies", absent), LIVE_ERR)  # cross-mode error precedes missing live flags

    def test_cross_mode_diagnostics_and_output_paths_are_private(self):
        existing = self.tmp / "existing.jsonl"
        existing.write_bytes(b"keep\n")
        os.chmod(existing, 0o640)
        for target in (self.out, existing):
            for argv in (self.score_args("--url", f"http://{CANARY}.invalid", "--model", CANARY, "--out", target),
                         self.live_args("--replies", f"{self.tmp}/{CANARY}.jsonl")):
                with self.subTest(target=target.name, argv=argv[0]):
                    code, out, err = self.refuse(*argv)
                    self.assertEqual((code, out), (2, ""))
                    self.assertNotIn(CANARY, out + err)
                    self.assertNotIn(str(self.tmp), out + err)
        self.assertEqual((existing.read_bytes(), stat.S_IMODE(existing.stat().st_mode), self.out.exists()), (b"keep\n", 0o640, False))
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["existing.jsonl", "photos", "r.jsonl"])

    def test_valid_score_summary_and_loader_errors_unchanged(self):
        expected = {c: {"right": 0, "wrong": 0, "none": 0} for c in ("name", "brand", "category")}
        code, out, err = base.run(*self.score_args())
        summary = json.loads(out)
        self.assertEqual((code, err, summary["cases"], summary["wrongIds"]), (0, "", len(self.cases), {k: [] for k in expected}))
        self.assertEqual(sum(summary["fields"]["name"].values()), len(self.cases))
        code2, out2, _ = base.run("score", "--replies", self.replies)  # default cases
        self.assertEqual((code2, json.loads(out2)), (0, summary))
        self.assertEqual(base.run("score", "--cases", base.FIXTURE, "--replies", self.tmp / "gone.jsonl"), (2, "", "replies: unreadable"))
        self.assertEqual(self.calls, [])

    def test_valid_recording_backend_defaults_remain(self):
        shapes = []
        for n, extra in enumerate(((), ("--api", "ollama"), ("--api", "openai"))):
            out = self.tmp / f"rec{n}.jsonl"
            args = ("--live", "--url", base.URL, "--model", "m", "--photos", self.photos, "--out", out, *extra)
            urls = []

            def transport(url, body, headers, timeout, urls=urls):
                urls.append(url)
                content = json.dumps({"name": "n"})
                if "v1/chat" in url: return 200, json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": content}}]}).encode()
                return 200, json.dumps({"done": True, "message": {"content": content}}).encode()

            code, stdout, err = base.run(*args, transport=transport)
            self.assertEqual((code, err, json.loads(stdout)), (0, "", {"recorded": len(self.cases), "failedCalls": 0}))
            self.assertEqual((len(urls), stat.S_IMODE(out.stat().st_mode)), (len(self.cases), 0o600))
            shapes.append({u.rsplit("/", 2)[-2] + "/" + u.rsplit("/", 1)[-1] for u in urls})
        self.assertEqual(shapes[0], shapes[1])
        self.assertNotEqual(shapes[0], shapes[2])


if __name__ == "__main__":
    unittest.main()
