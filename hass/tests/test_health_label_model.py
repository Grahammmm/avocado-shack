"""AV0207-14: both model roles share one stubbed tags request; no live state or model."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import health
from hass.tests.test_health_model import NOW, SETTINGS, URL, MARK, reply, fail


class HealthLabelModelTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.root / "wt"), "settings": SETTINGS}))

    def run_health(self, names=(), *, extra=(), interpreter: str | None = "qwen", label: str | None = "llava", transport=None):
        args = ["--state", str(self.state), "--model", URL, *extra]
        if interpreter is not None: args += ["--model-name", interpreter]
        if label is not None: args += ["--label-model", label]
        raw = json.dumps({"models": [{"name": n} for n in names], "note": MARK}).encode()
        stub = mock.Mock(side_effect=transport or reply(200, raw))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(args, now=NOW, transport=stub)
        stub.assert_called_once_with(URL + "/api/tags", 3)
        line = out.getvalue()
        for leak in (URL, MARK, "qwen", "llava", "/api/tags"):
            self.assertNotIn(leak, line)
        doc = json.loads(line)
        self.assertEqual(code, 1 if doc["problems"] else 0)
        return doc, line

    def assert_details(self, expected, *args, **kwargs):
        doc, _ = self.run_health(*args, **kwargs)
        self.assertEqual(doc["problems"], [{"check": "model", "detail": s} for s in expected])

    def test_installed_and_each_missing_combination(self):
        for names, details in (
                (("qwen:latest", "llava:latest"), []),
                (("llava:latest",), ["interpreter model not installed"]),
                (("qwen:latest",), ["label model not installed"]),
                ((), ["interpreter and label models not installed"])):
            with self.subTest(names=names): self.assert_details(details, names)

    def test_no_label_preserves_exact_legacy_json_line(self):
        _, line = self.run_health(label=None)
        problems = [{"check": "model", "detail": "model not installed"}]
        expected = {"ok": False, "problems": problems, "info": [{"check": "conversation", "detail": "no conversation yet"}],
                    "fingerprint": hashlib.sha256(b"model\tmodel not installed").hexdigest(), "notify": True}
        self.assertEqual(line, json.dumps(expected, ensure_ascii=False, sort_keys=True) + "\n")

    def test_same_normalized_name_is_one_problem_or_none(self):
        for label in ("qwen", "qwen:latest"):
            self.assert_details(["interpreter and label models not installed"], label=label)
            self.assert_details([], ("qwen:latest",), label=label)

    def test_label_only_and_tag_normalization(self):
        self.assert_details([], ("llava:latest",), interpreter=None)
        self.assert_details(["label model not installed"], interpreter=None)
        self.assert_details(["label model not installed"], ("llava:latest",), interpreter=None, label="llava:13b")
        self.assert_details([], ("llava:13b",), interpreter=None, label="llava:13b")

    def test_transport_failures_keep_single_existing_detail(self):
        for transport, detail in ((fail(ConnectionRefusedError(MARK)), "unreachable"),
                                  (fail(TimeoutError(MARK)), "unreachable"),
                                  (reply(500, MARK.encode()), "http 500"),
                                  (reply(200, MARK.encode()), "bad reply"),
                                  (reply(200, b'{"models": null}'), "bad reply")):
            with self.subTest(detail=detail): self.assert_details([detail], transport=transport)

    def test_bad_label_flags_exit_before_any_read(self):
        for extra in (("--label-model", "llava"), ("--model", URL, "--label-model", "")):
            with mock.patch.object(health, "check") as check, mock.patch.object(health, "_seen_path") as seen:
                out, err, transport = io.StringIO(), io.StringIO(), mock.Mock()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                    health.main(["--state", str(self.state), *extra], transport=transport)
                self.assertEqual(cm.exception.code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertIn("--label-model needs --model", err.getvalue())
                check.assert_not_called()
                seen.assert_not_called()
                transport.assert_not_called()

    def test_check_keyword_and_change_only_notify(self):
        transport = mock.Mock(side_effect=reply(200, b'{"models": []}'))
        problems, _, unsafe = health.check(self.state, model=URL, label_model="llava", transport=transport, now=NOW)
        self.assertEqual((problems, unsafe), ([{"check": "model", "detail": "label model not installed"}], False))
        transport.assert_called_once_with(URL + "/api/tags", 3)
        seen = ("--seen", str(self.root / "seen"))
        for names, notify in (((), True), ((), False), (("qwen:latest",), True), (("qwen:latest",), False),
                              (("qwen:latest", "llava:latest"), True), (("qwen:latest", "llava:latest"), False)):
            doc, _ = self.run_health(names, extra=seen)
            self.assertEqual(doc["notify"], notify)


if __name__ == "__main__":
    unittest.main()
