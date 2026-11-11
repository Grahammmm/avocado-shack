"""RF1315-13 (H09): decoder-excessive (deeply nested) JSON in a fixture row or the interpreter mapping ends the run with
the existing private exit-2 diagnostic (`fixture line N: not JSON` / `--interpreter: not JSON`), never a traceback.
Run: python3 -B -m unittest hass.tests.test_fixture_chat_deep_json -v
"""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import editor, fixture_chat
from hass.content_model import REPO_ROOT
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_demo_transcript import DEMO, MAPPING
from hass.tests.test_editor import WriterRepo
from hass.tests.test_fixture_chat_queue import START

N = 10000
ARRAY = "[" * N + "]" * N
OBJECT = '{"a":' * N + "1" + "}" * N
GOOD = json.dumps({"id": 1, "chat": "c", "sender": "x", "text": "hello", "at": "2026-11-02T09:00:00-08:00"})


class DeepJsonTests(unittest.TestCase):
    def fresh(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": SETTINGS})
        return repo, Path(tempfile.mkdtemp(prefix="hass-deep-", dir=repo.state.parent))

    def run_cli(self, repo, fixture, interpreter, *flags):
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state",
                               str(repo.state), "--fixture", str(fixture), "--interpreter", str(interpreter), *flags],
                              capture_output=True, text=True, cwd=REPO_ROOT)

    def assert_refused(self, run, message):
        self.assertEqual((run.returncode, run.stdout, run.stderr), (2, "", f"fixture_chat: {message}\n"))

    def assert_nothing_stored(self, repo):
        for name in ("conversation.sqlite3", "inbox.sqlite3"):
            db = repo.state / name
            if not db.exists(): continue
            con = sqlite3.connect(db)
            try:
                for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                                            "('messages','drafts','approvals','inbound')").fetchall():
                    self.assertEqual(con.execute(f"SELECT count(*) FROM {table}").fetchone(), (0,), table)
            finally:
                con.close()

    def test_deep_array_and_object_fixture_rows_refuse_by_physical_line(self):
        repo, folder = self.fresh()
        head = repo.head()
        for kind, deep in (("array", ARRAY), ("object", OBJECT)):
            fixture = folder / f"{kind}.jsonl"
            fixture.write_text(GOOD + "\n\n" + deep + "\n", "utf-8")
            for flags in ((), ("--queue", START)):
                with self.subTest(kind=kind, flags=flags):
                    run = self.run_cli(repo, fixture, MAPPING, *flags)
                    self.assert_refused(run, "fixture line 3: not JSON")
                    self.assertEqual(repo.head(), head)
                    self.assert_nothing_stored(repo)
        first = folder / "first.jsonl"
        first.write_text(ARRAY + "\n" + GOOD + "\n", "utf-8")
        self.assert_refused(self.run_cli(repo, first, MAPPING), "fixture line 1: not JSON")

    def test_deep_interpreter_mapping_refuses_by_flag_before_state(self):
        repo, folder = self.fresh()
        for kind, deep in (("array", ARRAY), ("object", OBJECT)):
            path = folder / f"{kind}.json"
            path.write_text(deep, "utf-8")
            with self.subTest(kind=kind):
                self.assert_refused(self.run_cli(repo, DEMO, path), "--interpreter: not JSON")
                self.assertFalse((repo.state / "conversation.sqlite3").exists())
        shallow = folder / "shallow.json"
        shallow.write_text("[[1]]", "utf-8")
        self.assert_refused(self.run_cli(repo, DEMO, shallow), "--interpreter: not a JSON object")

    def test_first_bad_line_wins_and_decoder_recursion_is_mapped_only_at_its_seam(self):
        with mock.patch.object(fixture_chat.json, "loads", side_effect=RecursionError):
            with self.assertRaisesRegex(ValueError, r"^fixture line 7: not JSON$"):
                fixture_chat._row(7, "{}")
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "m.json"
                path.write_text("{}", "utf-8")
                with self.assertRaisesRegex(ValueError, r"^--interpreter: not JSON$"):
                    fixture_chat._load_interpreter(path)
        with mock.patch.object(fixture_chat, "Inbound", side_effect=RecursionError):  # later validation is not swallowed
            with self.assertRaises(RecursionError):
                fixture_chat._row(1, GOOD)
        repo, folder = self.fresh()
        fixture = folder / "order.jsonl"
        fixture.write_text(GOOD + "\n\nnot json\n" + ARRAY + "\n", "utf-8")
        self.assert_refused(self.run_cli(repo, fixture, MAPPING), "fixture line 3: not JSON")


if __name__ == "__main__":
    unittest.main()
