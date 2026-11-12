"""RF1830-13: stage-log JSONL framing is physical LF/CRLF/CR only; literal NEL/LS/PS inside JSON strings are data."""
import json, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import stagelog

ROOT = Path(__file__).resolve().parents[2]
SEPS = {"NEL": "\u0085", "LS": "\u2028", "PS": "\u2029"}


def row(t, stage, ident, ascii_=False, **extra): return json.dumps({"t": t, "stage": stage, "id": ident, **extra}, ensure_ascii=ascii_)  # noqa: E704


class StageLogFraming(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.dir = Path(td.name)

    def write(self, name, data):
        p = self.dir / name
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return p

    def run_cli(self, *paths):
        before = [p.read_bytes() for p in paths]
        r = subprocess.run([sys.executable, "-B", str(ROOT / "hass" / "stagelog.py"), *map(str, paths)], capture_output=True, cwd=ROOT)
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        return r.stdout

    def test_literal_separators_and_escaped_spellings_decode_identically(self):
        combined = "x" + "".join(SEPS.values()) + "y"
        for name, s in list(SEPS.items()) + [("ALL", combined)]:
            ident, stage = f"a{s}b", f"st{s}ge"
            lines = lambda a: [row(1.0, "accepted", ident, a, note=f"n{s}"), row(2.0, stage, ident, a, meta={"k" + s: s})]  # noqa: E731
            lit = self.write(f"{name}-lit.jsonl", "\n".join(lines(False)) + "\n")
            esc = self.write(f"{name}-esc.jsonl", "\n".join(lines(True)) + "\n")
            got = stagelog.read(lit)
            self.assertEqual(len(got), 2, name)
            self.assertEqual(got, stagelog.read(esc), name)
            self.assertEqual([r["id"] for r in got], [ident, ident])
            self.assertEqual(got[1]["stage"], stage)
            self.assertEqual(got[1]["meta"], {"k" + s: s})
        cafe = self.write("cafe.jsonl", row(1.0, "accepted", "caf\u00e9") + "\n")
        self.assertEqual(stagelog.read(cafe)[0]["id"], "caf\u00e9")

    def test_cli_keeps_and_escapes_literal_separator_ids_and_stages(self):
        paths = []
        for name, s in SEPS.items():
            paths.append(self.write(f"{name}.jsonl", "\n".join([row(1.0, "accepted", f"a{s}b"), row(2.0, "handled", f"a{s}b"),
                                                               row(3.0, f"s{s}x", f"a{s}b")]) + "\n"))
        out = self.run_cli(*paths)
        want = "".join('"a\\u%04xb" accepted=0.0 handled=1.0 "s\\u%04xx"=2.0\n' % (ord(s), ord(s)) for s in SEPS.values())
        self.assertEqual(out, want.encode())
        for s in SEPS.values(): self.assertNotIn(s.encode("utf-8"), out)
        self.assertEqual(out.count(b"\n"), 3)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), sorted(p.name for p in paths))

    def test_literal_reply_id_still_joins_across_files(self):
        rid = "r\u2028\u0085\u2029id"
        a = self.write("mac.jsonl", "\n".join([row(1.0, "accepted", "m\u2028"), row(2.0, "reply-queued", "m\u2028", rid=rid)]) + "\n")
        b = self.write("host.jsonl", "\n".join([row(3.0, "reply-pulled", rid), row(9.0, "reply-pulled", rid), row(4.0, "bb-send-end", rid)]) + "\n")
        rows = stagelog.read(a) + stagelog.read(b)
        self.assertEqual(len(rows), 5)
        self.assertEqual(stagelog.table(rows), [("m\u2028", {"accepted": 0.0, "reply-queued": 1.0, "reply-pulled": 2.0, "bb-send-end": 3.0})])
        self.assertEqual(self.run_cli(a, b), b'"m\\u2028" accepted=0.0 reply-queued=1.0 reply-pulled=2.0 bb-send-end=3.0\n')

    def test_lf_crlf_cr_and_unterminated_last_record_keep_compatibility(self):
        r1, r2, r3 = row(1.0, "accepted", "a"), row(2.0, "handled", "a"), row(3.0, "ack-end", "a\\n\\r\\tz")
        for name, data in {"lf": f"{r1}\n\n{r2}\n{r3}\n", "crlf": f"{r1}\r\n\r\n{r2}\r\n{r3}", "cr": f"{r1}\r{r2}\r{r3}\r", "nofinal": f"{r1}\n{r2}\n{r3}"}.items():
            got = stagelog.read(self.write(name + ".jsonl", data.encode()))
            self.assertEqual([r["stage"] for r in got], ["accepted", "handled", "ack-end"], name)
        self.assertEqual(got[2]["id"], "a\\n\\r\\tz")
        p = self.write("esc.jsonl", row(1.0, "accepted", "a\nb\rc\td") + "\n")
        self.assertEqual(stagelog.read(p)[0]["id"], "a\nb\rc\td")
        self.assertEqual(self.run_cli(p), b'"a\\nb\\rc\\td" accepted=0.0\n')

    def test_unicode_between_objects_is_not_a_record_delimiter(self):
        for s in SEPS.values():
            joined = row(1.0, "accepted", "a") + s + row(2.0, "handled", "a")
            p = self.write("between.jsonl", "\n".join([row(0.5, "accepted", "pre"), joined, row(3.0, "handled", "pre")]) + "\n")
            self.assertEqual([(r["stage"], r["id"]) for r in stagelog.read(p)], [("accepted", "pre"), ("handled", "pre")])
        # a raw C0 control inside a string is still invalid JSON and is not salvaged
        p = self.write("c0.jsonl", b'{"t": 1.0, "stage": "accepted", "id": "a\x01b"}\n' + row(2.0, "accepted", "ok").encode() + b"\n")
        self.assertEqual([r["id"] for r in stagelog.read(p)], ["ok"])

    def test_bad_deep_and_unusable_timestamp_rows_do_not_hide_literal_neighbors(self):
        s = "\u2028"
        data = "\n".join([row(1.0, "accepted", f"a{s}"), "{not json", "[" * 100000, '{"t": true, "stage": "accepted", "id": "b"}',
                          '{"t": 1e999, "stage": "accepted", "id": "c"}', '{"stage": "accepted", "id": "d"}',
                          row(2.0, "handled", f"a{s}")]) + "\n"
        p = self.write("mixed.jsonl", data)
        got = stagelog.read(p)
        self.assertEqual([(r["t"], r["stage"], r["id"]) for r in got], [(1.0, "accepted", f"a{s}"), (2.0, "handled", f"a{s}")])
        self.assertEqual(p.read_bytes(), data.encode("utf-8"))
        self.assertEqual(sorted(x.name for x in self.dir.iterdir()), ["mixed.jsonl"])


if __name__ == "__main__":
    unittest.main()
