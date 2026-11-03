"""FAV-02 tests: label_eval scores LabelReader replies offline; --live is exercised only with a fake transport."""

import base64, contextlib, io, json, stat, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import label_eval as ev

FIXTURE, URL, CANARY = Path(__file__).resolve().parent / "fixtures" / "label-eval.jsonl", "http://127.0.0.1:11434", "ZQXCANARY"
BAD_URL = (2, "", "--url, --model or --photos is not usable")


def run(*argv, transport=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ev.main([str(a) for a in argv], transport=transport)
    return code, out.getvalue(), err.getvalue().removeprefix("label_eval: ").strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.cases = ev.load_cases(FIXTURE)

    def write(self, name, rows):
        path = self.tmp / name
        path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows), "utf-8")
        return path

    def score(self, replies):
        code, out, err = run("score", "--cases", FIXTURE, "--replies", self.write("r.jsonl", [{"id": k, "reply": v} for k, v in replies.items()]))
        return code, json.loads(out or "{}"), err

    def perfect(self): return {c["id"]: dict(c["expected"]) for c in self.cases}


class ScoreTests(Base):
    def test_fixture_has_8_to_12_cases_and_no_photo_files(self):
        self.assertTrue(8 <= len(self.cases) <= 12)
        self.assertEqual(list(FIXTURE.parent.glob("label-*")), [FIXTURE])

    def test_all_right_then_a_different_brand_is_wrong_and_listed(self):
        code, summary, err = self.score(self.perfect())  # l10 expects brand null and the reply has none: "none", not "right"
        self.assertEqual((code, err, summary["cases"], summary["wrongIds"]), (0, "", 10, {"name": [], "brand": [], "category": []}))
        self.assertEqual(summary["fields"], {"name": {"right": 10, "wrong": 0, "none": 0}, "brand": {"right": 9, "wrong": 0, "none": 1},
                                             "category": {"right": 10, "wrong": 0, "none": 0}})
        replies = self.perfect()
        replies["l03"]["brand"] = "Some Other Farm"
        _, summary, _ = self.score(replies)
        self.assertEqual((summary["wrongIds"]["brand"], summary["fields"]["brand"]), (["l03"], {"right": 8, "wrong": 1, "none": 1}))

    def test_expected_null_kept_value_is_wrong_but_dropped_value_is_none(self):
        for value, verdict in (("Acme Farm", "wrong"), ("Organic Acme", "none"), ("$4", "none"), ("unknown", "none"), (None, "none")):
            with self.subTest(value=value):
                replies = self.perfect()
                replies["l10"]["brand"] = value
                _, summary, _ = self.score(replies)
                self.assertEqual(summary["wrongIds"]["brand"], ["l10"] if verdict == "wrong" else [])
                self.assertEqual(summary["fields"]["brand"]["right"], 9)

    def test_category_is_case_insensitive_unknown_is_none_and_failed_read_is_none(self):
        replies = self.perfect() | {"l04": {}}
        replies["l01"]["category"], replies["l02"]["category"], replies["l03"]["category"] = "FRUIT", "gadgets", "dairy"
        _, summary, _ = self.score(replies)
        self.assertEqual(summary["fields"]["category"], {"right": 7, "wrong": 1, "none": 2})
        self.assertEqual((summary["wrongIds"]["category"], summary["fields"]["name"]["none"]), (["l03"], 1))

    def test_unusable_inputs_exit_2_naming_the_line(self):
        rows, good = FIXTURE.read_text("utf-8").splitlines(), [{"id": c["id"], "reply": {}} for c in self.cases]
        wrote = iter(range(99))

        def swap(n, row): return self.write(f"c{next(wrote)}.jsonl", rows[:n] + [row if isinstance(row, str) else json.dumps(row)] + rows[n + 1:])
        case = lambda **kw: {"id": "l01", "photo": "a.jpg", "expected": dict.fromkeys(ev.FIELDS), **kw}  # noqa: E731
        sep = {"name": "a\u2028b", "brand": None, "category": None}
        refused = {"dup": (self.write("dup.jsonl", rows + [rows[0]]), good, "cases line 11: duplicate id"),
                   "json": (swap(2, '{"id": "l03", "photo": "x.jpg"'), good, "cases line 3: not valid JSON"),
                   "number": (swap(0, case(expected={"name": 5, "brand": None, "category": None})), good, "cases line 1: expected value is neither text nor null"),
                   "sep": (swap(1, case(id="l02", expected=sep)), good, "cases line 2: line separator"),
                   "path": (swap(0, case(photo="../a.jpg")), good, "cases line 1: not a case"),
                   "unknown": (FIXTURE, good + [{"id": "zz", "reply": {}}], "replies line 11: no such case"),
                   "missing": (FIXTURE, good[:4] + good[5:], "cases line 5: no reply"),
                   "repeat": (FIXTURE, good + [good[0]], "replies line 11: duplicate id"),
                   "reply-sep": (FIXTURE, [{"id": "l01", "reply": {"name": "a\u2028b"}}] + good[1:], "replies line 1: line separator"),
                   "reply-escaped": (FIXTURE, ['{"id": "l01", "reply": {"name": "a\\u2029b"}}'] + good[1:], "replies line 1: line separator"),
                   "reply-text": (FIXTURE, ['{"id": "l01", "reply": "text"}'] + good[1:], "replies line 1: not a reply"),
                   "reply-json": (FIXTURE, good[:1] + ["{nope"] + good[2:], "replies line 2: not valid JSON")}
        for label, (case_file, reply_rows, message) in refused.items():
            with self.subTest(label):
                self.assertEqual(run("score", "--cases", case_file, "--replies", self.write("r.jsonl", reply_rows)), (2, "", message))
        self.assertEqual(run("score", "--cases", FIXTURE, "--replies", self.tmp / "absent.jsonl"), (2, "", "replies: unreadable"))

    def test_output_never_holds_a_label_value_or_photo_name(self):
        row = {"id": "k1", "photo": f"{CANARY}-photo.jpg", "expected": {"name": f"{CANARY} name", "brand": f"{CANARY} brand", "category": "fruit"}}
        cases = self.write("c.jsonl", [row])
        reply = {"name": f"{CANARY} other", "brand": f"{CANARY} brand", "category": "fruit"}
        code, out, err = run("score", "--cases", cases, "--replies", self.write("r.jsonl", [{"id": "k1", "reply": reply}]))
        self.assertEqual((code, json.loads(out)["wrongIds"]["name"]), (0, ["k1"]))
        bad = run("score", "--cases", cases, "--replies", self.write("bad.jsonl", [{"id": "k1", "reply": reply}, "{" + CANARY]))
        self.assertNotIn(CANARY, out + err + str(bad))


class LiveTests(Base):
    def setUp(self):
        super().setUp()
        self.photos, self.calls = self.tmp / "photos", []
        self.photos.mkdir()
        for i, case in enumerate(self.cases): (self.photos / case["photo"]).write_bytes(b"\xff\xd8synthetic-%d" % i)

    def transport(self, url, body, headers, timeout):
        self.calls.append(json.loads(body))
        if len(self.calls) == 3: return 500, b""
        reply = {"name": f"read-{len(self.calls)}", "maker": "Not Kept By keep"}
        return 200, json.dumps({"done": True, "message": {"content": json.dumps(reply)}}).encode()

    def live(self, out, photos=None, url=URL):
        return run("--live", "--url", url, "--model", "m", "--photos", photos or self.photos, "--out", out, transport=self.transport)

    def test_one_request_per_case_and_raw_replies_written_0600(self):
        out = self.tmp / "sub" / "replies.jsonl"
        out.parent.mkdir()
        code, stdout, err = self.live(out)
        self.assertEqual((code, err, json.loads(stdout), len(self.calls)), (0, "", {"recorded": 10, "failedCalls": 1}, 10))
        sent = [base64.b64decode(body["messages"][0]["images"][0]) for body in self.calls]
        self.assertEqual(sent, [b"\xff\xd8synthetic-%d" % i for i in range(10)])
        rows = [json.loads(line) for line in out.read_text("utf-8").splitlines()]
        self.assertEqual([r["id"] for r in rows], [c["id"] for c in self.cases])
        self.assertEqual((rows[0]["reply"], rows[2]["reply"]), ({"name": "read-1", "maker": "Not Kept By keep"}, {}))  # RAW, not keep()
        self.assertEqual((stat.S_IMODE(out.stat().st_mode), [p.name for p in out.parent.iterdir()]), (0o600, ["replies.jsonl"]))
        self.assertEqual(run("score", "--cases", FIXTURE, "--replies", out)[0], 0)  # the recording is scorable

    def test_existing_out_or_out_in_the_repo_exits_2_and_sends_nothing(self):
        out, inside = self.tmp / "taken.jsonl", ev.REPO / "hass" / "tests" / "label-eval-should-not-exist.jsonl"
        out.write_text("theirs\n")
        self.assertEqual(self.live(out), (2, "", "--out already exists"))
        self.assertEqual(self.live(inside), (2, "", "--out must be outside the repository"))
        self.assertEqual((out.read_text(), self.calls, inside.exists()), ("theirs\n", [], False))

    def test_symlinked_or_unusable_photo_exits_2_and_sends_nothing(self):
        target, out, path = self.tmp / "elsewhere.jpg", self.tmp / "replies.jsonl", self.photos / self.cases[-1]["photo"]
        target.write_bytes(b"x")
        for label in ("link", "missing", "directory", "empty"):
            with self.subTest(label):
                if path.is_dir(): path.rmdir()
                path.unlink(missing_ok=True)
                {"link": lambda: path.symlink_to(target), "missing": lambda: None, "directory": path.mkdir, "empty": lambda: path.write_bytes(b"")}[label]()
                code, stdout, err = self.live(out)
                self.assertEqual((code, stdout, self.calls, out.exists()), (2, "", [], False))
                self.assertTrue(err.startswith("a photo is"), err)

    def test_non_loopback_url_and_missing_flags_send_nothing(self):
        out = self.tmp / "replies.jsonl"
        self.assertEqual(self.live(out, url="http://example.com:11434"), BAD_URL)
        self.assertEqual(self.live(out, photos=self.tmp / "nope"), BAD_URL)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            ev.main(["--live", "--url", URL, "--model", "m", "--out", str(out)], transport=self.transport)
        self.assertEqual((stop.exception.code, self.calls, out.exists()), (2, [], False))


if __name__ == "__main__":
    unittest.main()
