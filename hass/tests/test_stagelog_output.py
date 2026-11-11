"""RF0445-10: the stage-table CLI escapes unsafe id/stage tokens at emission only; correlation keeps original strings."""
import json, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import stagelog

ROOT = Path(__file__).resolve().parents[2]


def row(t, stage, ident, **extra): return json.dumps({"t": t, "stage": stage, "id": ident, **extra})  # noqa: E704


class StageLogOutput(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.dir = Path(td.name)

    def run_cli(self, *files):
        paths = []
        for i, lines in enumerate(files):
            p = self.dir / f"s{i}.jsonl"
            p.write_text("\n".join(lines) + "\n", "utf-8")
            paths.append(p)
        before = [p.read_bytes() for p in paths]
        r = subprocess.run([sys.executable, "-B", str(ROOT / "hass" / "stagelog.py"), *map(str, paths)], capture_output=True, cwd=ROOT)
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        return r.stdout

    def test_cli_identifier_newline_and_carriage_return_are_literal_escapes(self):
        out = self.run_cli([row(1.0, "accepted", "synthetic\nFORGED"), row(2.0, "handled", "synthetic\nFORGED"),
                            row(1.0, "accepted", "a\rb")])
        self.assertEqual(out, b'"synthetic\\nFORGED" accepted=0.0 handled=1.0\n"a\\rb" accepted=0.0\n')
        self.assertNotIn(b"\r", out)
        self.assertEqual(out.count(b"\n"), 2)

    def test_cli_stage_controls_do_not_create_columns_or_terminal_sequences(self):
        out = self.run_cli([row(1.0, "accepted", "x"), row(2.0, "handled\tspoof", "x"), row(3.0, "e\x1b[2J", "x"),
                            row(4.0, "c1\x85z", "x")])
        self.assertEqual(out, b'x accepted=0.0 "handled\\tspoof"=1.0 "e\\u001b[2J"=2.0 "c1\\u0085z"=3.0\n')

    def test_cli_surrogate_identifier_and_stage_do_not_crash(self):
        for tok in ("\\ud800", "\\udc00"):
            raw = '{"t": 1.0, "stage": "accepted", "id": "i%s"}' % tok
            out = self.run_cli([raw])
            self.assertEqual(out, ('"i%s" accepted=0.0\n' % tok).encode())
            raw = '{"t": 1.0, "stage": "accepted", "id": "x"}\n{"t": 2.0, "stage": "s%s", "id": "x"}' % tok
            out = self.run_cli(raw.split("\n"))
            self.assertEqual(out, ('x accepted=0.0 "s%s"=1.0\n' % tok).encode())

    def test_cli_unicode_separators_are_escaped_but_printable_unicode_survives(self):
        out = self.run_cli([row(1.0, "accepted", "a\u2028b"), row(1.0, "accepted", "c\u2029d"), row(1.0, "accepted", "caf\u00e9")])
        self.assertEqual(out, b'"a\\u2028b" accepted=0.0\n"c\\u2029d" accepted=0.0\ncaf\xc3\xa9 accepted=0.0\n')

    def test_output_escaping_does_not_change_reply_join_or_duplicate_keys(self):
        rid = "r\nid\ud800"
        a = [row(1.0, "accepted", "m"), row(2.0, "reply-queued", "m", rid=rid)]
        b = [row(3.0, "reply-pulled", rid), row(9.0, "reply-pulled", rid)]
        rows = [r for lines in (a, b) for r in map(json.loads, lines)]
        self.assertEqual(stagelog.table(rows), [("m", {"accepted": 0.0, "reply-queued": 1.0, "reply-pulled": 2.0})])
        self.assertEqual([r["id"] for r in rows][2:], [rid, rid])
        out = self.run_cli(a, b)
        self.assertEqual(out, b"m accepted=0.0 reply-queued=1.0 reply-pulled=2.0\n")

    def test_healthy_cli_output_is_byte_identical(self):
        h = stagelog.short("m")
        out = self.run_cli([row(1.0, "accepted", h), row(1.5, "weird-stage", h), row(2.0, "handled", h), row(5.0, "accepted", "x")])
        self.assertEqual(out, f"{h} accepted=0.0 handled=1.0 weird-stage=0.5\nx accepted=0.0\n".encode())


if __name__ == "__main__":
    unittest.main()
