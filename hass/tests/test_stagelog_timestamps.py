"""Stage-log reader skips non-finite or float-overflowing timestamps."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

from hass import stagelog

SCRIPT = str(Path(stagelog.__file__))
A, H, R = "a" * 12, "b" * 12, "c" * 12


def line(t, stage, ident=A, extra=""):
    return '{"t": %s, "stage": "%s", "id": "%s"%s}' % (t, stage, ident, extra)


BAD = ["NaN", "Infinity", "-Infinity", "1e400", "-1e400", "9" * 401]


class T(unittest.TestCase):
    def write(self, *lines, name="s.jsonl"):
        d = tempfile.mkdtemp()
        p = os.path.join(d, name)
        Path(p).write_text("\n".join(lines) + "\n")
        return p

    def cli(self, *paths):
        r = subprocess.run([sys.executable, "-B", SCRIPT, *paths], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def test_reader_skips_nonfinite_timestamps_in_place(self):
        for bad in BAD:
            p = self.write(line("1.0", "accepted"), line(bad, "handled"), line("2.0", "ack-end"))
            before = Path(p).read_bytes()
            rows = stagelog.read(p)
            self.assertEqual([r["stage"] for r in rows], ["accepted", "ack-end"], bad)
            self.assertEqual(Path(p).read_bytes(), before)

    def test_huge_integer_timestamp_is_skipped_without_overflow(self):
        p = self.write(line("1.0", "accepted"), line("9" * 401, "handled"), line("2.0", "ack-end"))
        self.assertEqual([r["t"] for r in stagelog.read(p)], [1.0, 2.0])
        code, out, err = self.cli(p)
        self.assertEqual((code, out, err), (0, "%s accepted=0.0 ack-end=1.0\n" % A, ""))

    def test_bad_timestamp_only_is_successfully_empty(self):
        for bad in BAD:
            p = self.write(line(bad, "accepted"))
            self.assertEqual(stagelog.read(p), [])
            self.assertEqual(self.cli(p), (0, "", ""))

    def test_valid_numeric_types_are_not_coerced(self):
        p = self.write(line("0", "accepted"), line("-3", "ack-end"), line("0.5", "handled"),
                       line("true", "sent"), line('"1"', "sent"), line("null", "sent"),
                       line("1", "sent", extra=', "x": NaN'))
        rows = stagelog.read(p)
        self.assertEqual([(r["t"], type(r["t"])) for r in rows],
                         [(0, int), (-3, int), (0.5, float), (1, int)])

    def test_multifile_reply_join_ignores_bad_numeric_anchor(self):
        a = self.write(line("10", "accepted"), line("11", "reply-queued", A, ', "rid": "%s"' % R), name="a.jsonl")
        b = self.write(line("Infinity", "reply-queued", A, ', "rid": "%s"' % H),
                       line("12", "reply-pulled", R), line("13", "bb-send-end", R), line("12", "reply-pulled", H), name="b.jsonl")
        out = self.cli(a, b)
        self.assertEqual(out[0], 0)
        self.assertEqual(out[1], "%s accepted=0 reply-queued=1 reply-pulled=2 bb-send-end=3\n" % A)
        self.assertEqual(out[1:], ("%s accepted=0 reply-queued=1 reply-pulled=2 bb-send-end=3\n" % A, ""))

    def test_existing_stage_order_duplicates_and_unknown_stages(self):
        p = self.write(line("3", "ack-end"), line("1", "accepted"), line("2", "weird"), line("5", "accepted"), "garbage", "[1]")
        self.assertEqual(self.cli(p)[1], "%s accepted=0 ack-end=2 weird=1\n" % A)


if __name__ == "__main__":
    unittest.main()
