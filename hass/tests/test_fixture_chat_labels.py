"""FAV-03 (H10): fixture_chat --labels URL --label-model NAME passes a LabelReader to the Conversation.

In-process main() with a recording fake in place of LabelReader (no model, no network). Without the flags nothing
changes; a bad flag is named, never its value, and writes nothing to the state dir.
Run: python3 -B -m unittest hass.tests.test_fixture_chat_labels -v
"""

import contextlib
import io
import json
import unittest
from unittest import mock

from hass import fixture_chat
from hass.conversation import PHOTO_QUESTION
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_demo_transcript_photo import DEMO, MAPPING
from hass.tests.test_set_photo import FIXTURES as MEDIA, PhotoRepo, _settings

URL, MODEL, LABEL = "http://127.0.0.1:11434", "vision-test", "The label looks like \ue000"


class FakeReader:
    made, reads = [], []

    def __init__(self, url, model, **kwargs):
        self.url, self.model = url, model
        FakeReader.made.append(self)

    def read(self, image_bytes, categories):
        FakeReader.reads.append(self)
        return {"name": "Fake Jam", "brand": "Fake Co"}


class FixtureChatLabelTests(unittest.TestCase):
    def setUp(self):
        FakeReader.made, FakeReader.reads = [], []
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))

    def run_main(self, *extra, photos=True, patched=True):
        argv = ["--state", str(self.repo.state), "--fixture", str(DEMO), "--interpreter", str(MAPPING), *extra]
        if photos: argv += ["--photos", str(MEDIA)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            if patched: stack.enter_context(mock.patch.object(fixture_chat, "LabelReader", FakeReader))
            conv = stack.enter_context(mock.patch.object(fixture_chat, "FixtureConversation", wraps=fixture_chat.FixtureConversation))
            code = fixture_chat.main(argv)
        return code, out.getvalue(), err.getvalue(), conv

    def listing(self):
        return sorted((str(p.relative_to(self.repo.state)), p.stat().st_size)
                      for p in self.repo.state.rglob("*") if p.is_file())

    def texts(self, out):
        return [json.loads(line)["text"] for line in out.splitlines()]

    def refused(self, *extra, **kw):
        before = self.listing()
        code, out, err, conv = self.run_main(*extra, **kw)
        self.assertEqual((code, out), (2, ""))
        conv.assert_not_called()
        self.assertEqual(self.listing(), before)  # no draft, message row or inbox file
        return err

    def test_without_the_flags_nothing_changes(self):
        code, out, err, conv = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertIsNone(conv.call_args.kwargs["labels"])
        self.assertEqual(FakeReader.made, [])
        self.assertFalse([t for t in self.texts(out) if LABEL in t])
        self.assertTrue(self.texts(out)[0].startswith(PHOTO_QUESTION))

    def test_both_flags_pass_the_reader_and_a_photo_question_carries_the_label(self):
        code, out, err, conv = self.run_main("--labels", URL, "--label-model", MODEL)
        self.assertEqual((code, err), (0, ""))
        reader = conv.call_args.kwargs["labels"]
        self.assertIs(reader, FakeReader.made[-1])
        self.assertEqual((reader.url, reader.model), (URL, MODEL))
        self.assertTrue(FakeReader.reads and all(r is reader for r in FakeReader.reads))
        asked = self.texts(out)[0]
        self.assertTrue(asked.startswith(PHOTO_QUESTION))
        self.assertIn(LABEL + "Fake Co Fake Jam\ue001.", asked)

    def test_only_one_label_flag_is_refused(self):
        for flags in (("--labels", URL), ("--label-model", MODEL)):
            with self.subTest(flags):
                self.assertEqual(self.refused(*flags), "fixture_chat: --labels and --label-model go together\n")

    def test_a_bad_url_is_named_by_flag_and_never_printed(self):
        err = self.refused("--labels", "http://example.com:11434", "--label-model", MODEL, patched=False)
        self.assertEqual(err, "fixture_chat: --labels: not a loopback http URL\n")
        self.assertNotIn("example.com", err)

    def test_a_bad_model_is_named_by_flag_and_never_printed(self):
        err = self.refused("--labels", URL, "--label-model", "two words", patched=False)
        self.assertTrue(err.startswith("fixture_chat: --label-model:"))
        self.assertNotIn("two words", err)
        self.assertNotIn("11434", err)

    def test_a_bad_url_wins_over_a_bad_model_and_the_model_is_not_printed(self):
        err = self.refused("--labels", "https://127.0.0.1", "--label-model", "two words", patched=False)
        self.assertEqual(err, "fixture_chat: --labels: not a loopback http URL\n")

    def test_flags_without_photos_are_refused(self):
        self.assertEqual(self.refused("--labels", URL, "--label-model", MODEL, photos=False),
                         "fixture_chat: --labels: needs --photos\n")

    def test_good_flags_build_the_real_reader_and_only_a_photo_calls_it(self):
        with mock.patch("hass.interpreter_local.urllib_transport", side_effect=OSError("down")) as net:
            code, out, err, conv = self.run_main("--labels", URL, "--label-model", MODEL, patched=False)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(type(conv.call_args.kwargs["labels"]).__name__, "LabelReader")
        self.assertTrue(net.called)  # the first photo reached the reader; its failure is today's reply exactly
        self.assertNotIn(LABEL, out)


if __name__ == "__main__":
    unittest.main()
