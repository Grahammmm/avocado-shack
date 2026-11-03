"""RF1510-12 (H09): a fixture_chat input that cannot be loaded ends the run with a message naming the flag
(`--interpreter: unreadable | not JSON | not a JSON object`, `--fixture: unreadable`, exit 2) and never a file path;
any other OSError prints only its strerror. Runs the CLI as a subprocess against a throwaway writer repo.
Run: python3 -B -m unittest hass.tests.test_fixture_chat_inputs -v
"""

import contextlib
import io
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import editor
from hass.content_model import REPO_ROOT
from hass.conversation import Conversation, Editor, FixtureInterpreter
from hass.fixture_chat import FixtureAdapter, FixtureConversation, main
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_demo_transcript import DEMO, MAPPING
from hass.tests.test_editor import WriterRepo
from hass.tests.test_fixture_chat_queue import START

BAD_INTERPRETERS = [  # (file name, bytes or None for a directory or a missing file, expected message)
    ("absent.json", None, "--interpreter: unreadable"), ("folder.json", "dir", "--interpreter: unreadable"),
    ("latin.json", b"\xff\xfe{\"a\": 1}", "--interpreter: unreadable"),
    ("text.json", b"not json", "--interpreter: not JSON"),
    ("list.json", b"[]", "--interpreter: not a JSON object"), ("str.json", b'"x"', "--interpreter: not a JSON object"),
]


class FixtureChatInputTests(unittest.TestCase):
    def fresh(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": SETTINGS})
        folder = Path(tempfile.mkdtemp(prefix="hass-inputs-privatedir-", dir=repo.state.parent))
        return repo, folder

    def run_cli(self, repo, fixture=DEMO, interpreter=MAPPING, *flags):
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state",
                               str(repo.state), "--fixture", str(fixture), "--interpreter", str(interpreter), *flags],
                              capture_output=True, text=True, cwd=REPO_ROOT)

    def refused(self, run, message, repo, head, *names):
        self.assertEqual((run.returncode, run.stdout, run.stderr), (2, "", f"fixture_chat: {message}\n"))
        for name in names: self.assertNotIn(name, run.stderr)
        self.assertEqual(repo.head(), head)
        db = repo.state / "conversation.sqlite3"
        if db.exists():
            con = sqlite3.connect(db)
            try:
                self.assertEqual(con.execute("SELECT count(*) FROM messages").fetchone(), (0,))
            finally:
                con.close()

    def test_bad_interpreter_names_the_flag_not_the_file(self):
        repo, folder = self.fresh()
        head = repo.head()
        for name, body, message in BAD_INTERPRETERS:
            path = folder / name
            if body == "dir": path.mkdir()
            elif body is not None: path.write_bytes(body)
            for flags in ((), ("--queue", START)):
                with self.subTest(name=name, flags=flags):
                    run = self.run_cli(repo, DEMO, path, *flags)
                    self.refused(run, message, repo, head, folder.name, name, str(repo.state.parent))
                    self.assertFalse((repo.state / "inbox.sqlite3").exists())

    def test_unreadable_fixture_handles_and_sends_nothing(self):
        repo, folder = self.fresh()
        head = repo.head()
        (folder / "folder.jsonl").mkdir()
        (folder / "latin.jsonl").write_bytes(b"\xff\xfe\n")
        for name in ("absent.jsonl", "folder.jsonl", "latin.jsonl"):
            for flags in ((), ("--queue", START)):
                with self.subTest(name=name, flags=flags):
                    run = self.run_cli(repo, folder / name, MAPPING, *flags)
                    self.refused(run, "--fixture: unreadable", repo, head, folder.name, name)

    def test_bad_fixture_line_message_unchanged(self):
        repo, folder = self.fresh()
        (folder / "bad.jsonl").write_text("{not json\n", "utf-8")
        self.refused(self.run_cli(repo, folder / "bad.jsonl"), "fixture line 1: not JSON", repo, repo.head())

    def test_later_os_error_prints_strerror_without_path(self):
        repo, folder = self.fresh()
        secret = str(repo.state / "conversation.sqlite3")
        argv = ["--state", str(repo.state), "--fixture", str(DEMO), "--interpreter", str(MAPPING)]
        for exc, message in ((PermissionError(13, "Permission denied", secret), "PermissionError: Permission denied"),
                             (OSError(f"cannot write {secret}"), "OSError: error")):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(Conversation, "handle", side_effect=exc):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = main(argv)
                self.assertEqual((code, out.getvalue(), err.getvalue()), (2, "", f"fixture_chat: {message}\n"))
                self.assertNotIn(str(repo.state.parent), err.getvalue())

    def test_valid_inputs_print_the_same_transcript(self):
        (cli, _), (ref, _) = self.fresh(), self.fresh()
        run = self.run_cli(cli)
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        adapter = FixtureAdapter(str(DEMO))  # the pre-RF1510-12 main loop, in process
        conversation = FixtureConversation(str(ref.state), Editor(str(ref.state)),
                                    FixtureInterpreter(json.loads(MAPPING.read_text("utf-8"))),
                                    lambda: datetime.now(timezone.utc), None, photos=None)
        for message in adapter.inbound(): conversation.handle(message)
        conversation.flush(adapter)
        expected = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in adapter.sent)
        self.assertEqual(self.masked(run.stdout, cli), self.masked(expected, ref))

    def masked(self, out, repo):
        out = re.sub(r"Expires [^\n]*?\.", "Expires <time>.", out)
        con = sqlite3.connect(repo.state / "conversation.sqlite3")
        try:
            for (code,) in con.execute("SELECT code FROM drafts"): out = out.replace(code, "<code>")
        finally:
            con.close()
        return out


if __name__ == "__main__":
    unittest.main()
