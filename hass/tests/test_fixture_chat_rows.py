"""RF1105-30 (H09/H16): every fixture line is checked before any message is handled or queued. A bad line ends the
run with `fixture_chat: fixture line <n>: <field> <rule>` (exit 2); nothing handled, queued or sent.
Run: python3 -B -m unittest hass.tests.test_fixture_chat_rows -v
"""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass import editor
from hass.content_model import REPO_ROOT
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_demo_transcript import DEMO, EXPECTED, KINDS, MAPPING
from hass.tests.test_editor import WriterRepo
from hass.tests.test_fixture_chat_queue import PAIR, START, line

OFFSET, ID = "at must be an ISO time with a UTC offset", "id must be a non-empty string or an integer"
KIND = "kind must be a non-empty string"
ROW = line("r-1", "hi", "2026-11-02T09:00:00-08:00")
NO_SENDER = json.dumps({k: v for k, v in ROW.items() if k != "sender"})
CASES = [  # (fixture text, or a change to ROW on line 1, expected message)
    ({"text": 5}, "text must be a string"), ({"chat": None}, "chat must be a string"),
    ({"fromMe": "no"}, "fromMe must be true or false"), ({"fromMe": 1}, "fromMe must be true or false"),
    ({"at": "2026-10-31T10:00:00"}, OFFSET), ({"at": "next tuesday"}, OFFSET), ({"at": 1793480000}, OFFSET),
    ({"at": None}, OFFSET), ({"id": True}, ID), ({"id": ""}, ID), ({"id": 1.5}, ID), ({"kind": ""}, KIND),
    ({"kind": 3}, KIND), (NO_SENDER + "\n", "sender must be a string"), ("[1, 2]\n", "row must be a JSON object"),
    ("\n{not json\n", "line 2: not JSON"), (f"{json.dumps(ROW)}\n\n{NO_SENDER}\n", "line 3: sender must be a string"),
]


class FixtureRowTests(unittest.TestCase):
    def fresh(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": SETTINGS})
        return repo, repo.head()

    def run_cli(self, repo, rows, *flags, text=None):
        fixture = repo.state.parent / "fixture.jsonl"
        fixture.write_text(text if text is not None else "".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state",
                               str(repo.state), "--fixture", str(fixture), "--interpreter", str(MAPPING), *flags],
                              capture_output=True, text=True, cwd=REPO_ROOT)

    def query(self, repo, db, sql):
        con = sqlite3.connect(repo.state / f"{db}.sqlite3")
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def refused(self, run, message, repo, head):  # exit 2, the line named, nothing handled, sent or committed
        self.assertEqual((run.returncode, run.stdout, run.stderr), (2, "", f"fixture_chat: {message}\n"))
        self.assertEqual(self.query(repo, "conversation", "SELECT * FROM drafts"), [])
        self.assertEqual(self.query(repo, "conversation", "SELECT * FROM messages"), [])
        self.assertEqual(repo.head(), head)

    def test_each_rule_names_the_line_and_field(self):
        folder = tempfile.TemporaryDirectory(prefix="hass-rows-")
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "fixture.jsonl"
        for case, message in CASES:
            with self.subTest(case=case):
                path.write_text(case if isinstance(case, str) else json.dumps({**ROW, **case}) + "\n", "utf-8")
                with self.assertRaises(ValueError) as caught:
                    FixtureAdapter(path).inbound()
                self.assertEqual(str(caught.exception), "fixture " + (message if message.startswith("line ") else
                                                                      f"line 1: {message}"))

    def test_bad_text_on_line_3_handles_and_sends_nothing(self):
        repo, head = self.fresh()
        run = self.run_cli(repo, [*PAIR, line("q-3", 5, "2026-11-02T09:02:00-08:00")])
        self.refused(run, "fixture line 3: text must be a string", repo, head)

    def test_first_bad_line_named_and_string_from_me_not_an_echo(self):
        repo, head = self.fresh()
        rows = [PAIR[0], {**PAIR[1], "fromMe": "no"}, PAIR[1], {**PAIR[1], "text": 5}]
        self.refused(self.run_cli(repo, rows), "fixture line 2: fromMe must be true or false", repo, head)

    def test_not_json_after_blank_line(self):
        repo, head = self.fresh()
        run = self.run_cli(repo, [], text="\n{not json\n" + json.dumps(PAIR[0]) + "\n")
        self.refused(run, "fixture line 2: not JSON", repo, head)

    def test_queue_bad_line_4_of_5_queues_nothing(self):
        repo, head = self.fresh()
        rows = [line(f"q-{i}", "yes", f"2026-11-02T09:0{i}:00-08:00") for i in range(1, 6)]
        rows[3]["at"] = "2026-11-02T09:04:00"
        self.refused(self.run_cli(repo, rows, "--queue", START), f"fixture line 4: {OFFSET}", repo, head)
        self.assertEqual(self.query(repo, "inbox", "SELECT * FROM inbound"), [])

    def test_value_never_echoed(self):
        repo, head = self.fresh()
        run = self.run_cli(repo, [{**PAIR[0], "sender": ["SECRET-XYZ"]}])
        self.refused(run, "fixture line 1: sender must be a string", repo, head)
        self.assertNotIn("SECRET-XYZ", run.stderr)

    def test_integer_id_accepted_as_string(self):
        repo, _ = self.fresh()
        run = self.run_cli(repo, [{**PAIR[0], "id": 7}, PAIR[1]])
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        ids = self.query(repo, "conversation", "SELECT provider_id FROM messages ORDER BY provider_id")
        self.assertEqual(ids, [("7",), ("q-2",)])

    def test_valid_fixture_copy_with_blank_lines_runs_as_before(self):
        repo, _ = self.fresh()
        run = self.run_cli(repo, [], text="\n" + DEMO.read_text("utf-8").replace("\n", "\n\n"))
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        texts = [json.loads(r)["text"] for r in run.stdout.splitlines()]
        self.assertEqual([next((k for k in KINDS if t.startswith(k)), t) for t in texts], EXPECTED)


if __name__ == "__main__":
    unittest.main()
