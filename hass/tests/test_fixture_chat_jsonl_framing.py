"""RF0640-13 (H09): a fixture JSONL record ends at LF only. A literal U+0085, U+2028 or U+2029 inside a message value is
legal JSON string content and stays in that one row; between two objects it is a malformed physical line, never two
records. Fixture files are external synthetic files; replay uses a harmless mapped reply and sends nothing.
Run: python3 -B -m unittest hass.tests.test_fixture_chat_jsonl_framing -v
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
from hass.tests.test_editor import WriterRepo
from hass.tests.test_fixture_chat_queue import START, line

NEL, LS, PS = "\u0085", "\u2028", "\u2029"
AT = "2026-11-02T09:00:00-08:00"
TEXTS = [f"{NEL}start", f"mid{LS}dle", f"end{PS}", f"all{NEL}{LS}{PS}three", f"{LS}{PS}{NEL}", f"ends{NEL}{LS}{PS}"]
REPLY = "Noted, nothing to change."


def dump(row, ascii_only=False):
    return json.dumps(row, ensure_ascii=ascii_only)


class FramingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="hass-framing-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def read(self, data, name="fixture.jsonl"):
        path = self.folder / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return FixtureAdapter(path).inbound()

    def refusal(self, data):
        with self.assertRaises(ValueError) as caught:
            self.read(data)
        return str(caught.exception)

    def test_literal_unicode_separators_stay_inside_one_record(self):
        for text in TEXTS:
            with self.subTest(text=text.encode("unicode_escape")):
                got = self.read(dump(line("u-1", text, AT)) + "\n")
                self.assertEqual([m.text for m in got], [text])
        rows = [line(f"u-{i}", t, AT) for i, t in enumerate(TEXTS)]
        got = self.read("".join(dump(r) + "\n" for r in rows))
        self.assertEqual([m.text for m in got], TEXTS)
        self.assertEqual([m.provider_id for m in got], [f"u-{i}" for i in range(len(TEXTS))])

    def test_escaped_and_literal_spellings_decode_identically(self):
        text = f"caf\u00e9 \u5bff\u53f8 a{NEL}b{LS}c{PS}d\nline\rcr\ttab"
        row = line("e-1", text, AT)
        literal, escaped = dump(row), dump(row, ascii_only=True)
        self.assertNotIn("\n", literal)
        self.assertTrue(escaped.isascii())
        a, b = self.read(literal + "\n"), self.read(escaped + "\n", "escaped.jsonl")
        self.assertEqual((a, [m.text for m in a]), (b, [text]))

    def test_lf_crlf_cr_and_final_record_compatibility(self):
        rows = [dump(line(f"c-{i}", f"row{LS}{i}", AT)) for i in range(3)]
        want = [f"row{LS}{i}" for i in range(3)]
        for name, eol in (("lf", "\n"), ("crlf", "\r\n"), ("cr", "\r")):
            with self.subTest(eol=name):
                self.assertEqual([m.text for m in self.read(eol.join(rows) + eol, name + ".jsonl")], want)
                self.assertEqual([m.text for m in self.read(eol.join(rows), name + "-bare.jsonl")], want)
        self.assertEqual(self.read(""), [])
        self.assertEqual(self.read("\n\n"), [])
        mixed = f"\n{rows[0]}\n\n{rows[1]}\n\n\n"
        self.assertEqual([m.text for m in self.read(mixed)], want[:2])

    def test_non_lf_unicode_between_objects_is_not_a_record_boundary(self):
        a, b = dump(line("n-1", "one", AT)), dump(line("n-2", "two", AT))
        for sep in (NEL, LS, PS):
            with self.subTest(sep=sep.encode("unicode_escape")):
                self.assertEqual(self.refusal(a + sep + b + "\n"), "fixture line 1: not JSON")
        for raw in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e"):  # raw C0 controls: still invalid JSON
            with self.subTest(raw=raw.encode("unicode_escape")):
                self.assertEqual(self.refusal(a + raw + b + "\n"), "fixture line 1: not JSON")
                inside = dump(line("n-3", "xKEYy", AT)).replace("KEY", raw)  # json.dumps would escape it
                self.assertEqual(self.refusal(inside + "\n"), "fixture line 1: not JSON")

    def test_error_after_unicode_value_names_actual_physical_line(self):
        good = dump(line("p-1", f"a{NEL}b{LS}c{PS}d", AT))
        self.assertEqual(self.refusal(f"{good}\n\n{{not json\n"), "fixture line 3: not JSON")
        self.assertEqual(self.refusal(f"{good}\r\n\r\n{{not json\r\n"), "fixture line 3: not JSON")


class ReplayTests(unittest.TestCase):
    def fresh(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": SETTINGS})
        return repo

    def run_cli(self, repo, rows, mapping, *flags, text=None):
        fixture, interpreter = repo.state.parent / "fixture.jsonl", repo.state.parent / "interpreter.json"
        fixture.write_text(text if text is not None else "".join(dump(r) + "\n" for r in rows), "utf-8")
        interpreter.write_text(json.dumps(mapping), "utf-8")
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state",
                               str(repo.state), "--fixture", str(fixture), "--interpreter", str(interpreter), *flags],
                              capture_output=True, text=True, encoding="utf-8", cwd=REPO_ROOT)

    def replies(self, run):
        return [json.loads(r)["text"] for r in run.stdout.split("\n") if r]

    def test_direct_and_queue_replay_preserve_message_text(self):
        text = f"Is the stall{NEL} open{LS} today{PS}?"
        mapping = {text: {"unsupported": REPLY}}
        rows = [line("r-1", text, AT)]
        direct = self.run_cli(self.fresh(), rows, mapping)
        self.assertEqual((direct.returncode, direct.stderr, self.replies(direct)), (0, "", [REPLY]))
        repo = self.fresh()
        head = repo.head()
        queued = self.run_cli(repo, rows, mapping, "--queue", START)
        self.assertEqual((queued.returncode, self.replies(queued)), (0, [REPLY]))
        self.assertEqual(queued.stderr.strip(), "fixture_chat: queued=1 duplicate=0 history=0 handled=1")
        again = self.run_cli(repo, rows, mapping, "--queue", START)
        self.assertEqual((again.returncode, again.stdout), (0, ""))
        self.assertEqual(again.stderr.strip(), "fixture_chat: queued=0 duplicate=1 history=0 handled=0")
        self.assertEqual(repo.head(), head)  # nothing prepared or applied

    def test_bad_later_row_handles_and_queues_no_prefix(self):
        text = f"hello{LS}there"
        mapping = {text: {"unsupported": REPLY}}
        data = dump(line("b-1", text, AT)) + "\n{not json\n"
        for flags in ((), ("--queue", START)):
            with self.subTest(flags=flags):
                repo = self.fresh()
                head = repo.head()
                run = self.run_cli(repo, None, mapping, *flags, text=data)
                self.assertEqual((run.returncode, run.stdout, run.stderr), (2, "", "fixture_chat: fixture line 2: not JSON\n"))
                self.assertEqual(repo.head(), head)
                for db, table in (("conversation", "messages"), ("inbox", "inbound")):
                    path = repo.state / f"{db}.sqlite3"
                    if path.exists():
                        con = sqlite3.connect(path)
                        try: self.assertEqual(con.execute(f"SELECT count(*) FROM {table}").fetchone(), (0,))
                        finally: con.close()


if __name__ == "__main__":
    unittest.main()
