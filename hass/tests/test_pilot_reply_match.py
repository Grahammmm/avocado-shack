"""Offline, synthetic inputs for the attended pilot's text classifier."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/pilot_reply_match.py"
ASSET = ROOT / "hass/npp/assets/hass-npp-reply/reply-templates.json"
SPEC = importlib.util.spec_from_file_location("pilot_reply_match", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MATCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MATCHER)
VALUES = {"maker": "Fixture Maker", "name": "Fixture Source", "brand": "Fixture Brand",
          "claim": "Fixture Claim", "code": "cafe", "n": 3,
          "url": "https://fixture.invalid/?item=example#market"}


class PilotReplyMatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.reply = self.directory / "fixture-reply.txt"
        self.templates = self.directory / "fixture-templates.json"
        self.document = json.loads(ASSET.read_text(encoding="utf-8"))

    def invoke(self, reply, templates=None):
        self.reply.write_bytes(reply if isinstance(reply, bytes) else reply.encode("utf-8"))
        argv = ["--reply", str(self.reply)]
        if templates is not None:
            raw = templates if isinstance(templates, str) else json.dumps(templates)
            self.templates.write_text(raw, encoding="utf-8")
            argv += ["--templates", str(self.templates)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = MATCHER.main(argv)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_every_real_template_reports_only_its_key_and_allowed_metadata(self):
        # Covers escaped punctuation, all sections, and accidental value echo
        # on success; distinct exact output keeps deferred separate from posted.
        expected_fields = {"prompts.ready": "\nversion: 3\ncode length: 4",
                           "confirm.posted": "\nurl: present"}
        groups = {section: self.document[section]
                  for section in ("questions", "prompts", "guards", "confirm", "edits")}
        groups["brackets.parts"] = self.document["brackets"]["parts"]
        for section, templates in groups.items():
            for name, text in templates.items():
                if name.endswith("_note"):
                    continue
                key = f"{section}.{name}"
                with self.subTest(key=key):
                    reply = text.format(**VALUES)
                    expected = key + expected_fields.get(key, "") + "\n"
                    self.assertEqual(self.invoke(reply), (0, expected, ""))

    def test_no_template_for_extra_text_rewording_and_metadata(self):
        # Search, wildcard literal punctuation, or scanning metadata as replies
        # would make these non-templates classify as successful matches.
        ready = self.document["prompts"]["ready"].format(**VALUES)
        question = self.document["questions"]["ask_price"]
        metadata = [self.document["about"], self.document["guards"]["guard_note"],
                    self.document["existing"]["expired"], self.document["never_say"][0],
                    self.document["brackets"]["compose"]["rule"],
                    self.document["brackets"]["compose"]["separator"]]
        for index, reply in enumerate([
            "yes", "Fixture preface. " + ready, ready.replace("Post this", "Publish this"),
            ready[:-1] + "!", question + " Fixture extra sentence.",
            question + " " + self.document["questions"]["ask_unit"], question + "\n\n",
            self.document["questions"]["ask_near_maker"].format(maker="Fixture. Extra sentence"),
            *metadata,
        ]):
            with self.subTest(case=index):
                self.assertEqual(self.invoke(reply), (1, "", "no-template\n"))

    def test_override_escapes_literals_and_refuses_ambiguous_matches(self):
        # A choose-first implementation would report a key on collision.
        document = {"caps": self.document["caps"], "guards": {"first": "[Notice] {detail}."}}
        reply = "[Notice] Fixture detail."
        self.assertEqual(self.invoke(reply, document), (0, "guards.first\n", ""))
        document["guards"]["second"] = "[Notice] Fixture {detail}."
        self.assertEqual(self.invoke(reply, document), (1, "", "ambiguous-template\n"))

    def test_question_length_cap_uses_full_rendered_text_and_includes_boundary(self):
        # Checking only the literal template, counting bytes, using the default
        # cap on override, or checking every prompt as a question is incorrect.
        reply = self.document["questions"]["ask_edit_source"].format(name="Café Fixture")
        cap = self.document["caps"]
        cap["question_max_chars"] = len(reply)
        self.assertEqual(self.invoke(reply, self.document), (0, "questions.ask_edit_source\n", ""))
        cap["question_max_chars"] -= 1
        self.assertEqual(self.invoke(reply, self.document), (1, "", "question_max_chars\n"))
        cap["question_max_chars"] = 0
        ready = self.document["prompts"]["ready"].format(**VALUES)
        self.assertEqual(self.invoke(ready, self.document),
                         (0, "prompts.ready\nversion: 3\ncode length: 4\n", ""))

    def test_count_cap_rejects_joined_questions_without_exposing_them(self):
        # Count templated questions, not sentences or a ready prompt's '?'.
        questions = self.document["questions"]
        reply = " ".join(questions[name] for name in ("ask_identity", "ask_price", "ask_unit"))
        self.assertEqual(self.invoke(reply), (1, "", "max_questions_per_reply\n"))
        self.document["caps"]["max_questions_per_reply"] = 0
        self.assertEqual(self.invoke(questions["ask_price"], self.document),
                         (1, "", "max_questions_per_reply\n"))

    def test_invalid_inputs_only_emit_fixed_reasons(self):
        # Raw decoder or path diagnostics must not disclose input bytes or text.
        self.assertEqual(self.invoke(b"\xff"), (1, "", "unreadable-reply\n"))
        for templates in ('{"fixture_private":', {"caps": {"question_max_chars": True}}):
            with self.subTest(kind=type(templates).__name__):
                self.assertEqual(self.invoke("Fixture text", templates),
                                 (1, "", "invalid-templates\n"))

    def test_direct_cli_resolves_default_from_checkout_not_working_directory(self):
        # Imported main alone cannot catch a cwd-relative default or a broken
        # __main__ entry point; a normal capture may end in one CRLF.
        self.reply.write_bytes(self.document["guards"]["live_check_failed"].encode() + b"\r\n")
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--reply", str(self.reply)],
                                cwd=self.directory, capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "guards.live_check_failed\n", ""))


if __name__ == "__main__":
    unittest.main()
