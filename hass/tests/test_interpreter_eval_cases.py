"""RF0550-4 tests: load_cases refuses, by line and without content, a case whose pending codes or expected answer can
never be scored (bad or repeated pending code, revises naming no pending draft, more than MAX_OPS expected ops); exit 2
from main, never a traceback. The real fixture and every valid case load as before. No model call; --live never run."""

import contextlib, io, json, re, tempfile, unittest, unittest.mock  # noqa: E401
from pathlib import Path

from hass import interpret_check, interpreter_eval as ev
from hass.content_model import load_content
from hass.tests import test_interpreter_eval as base  # module import: its test classes are not collected twice

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES, REPLIES = FIXTURES / "interpreter-eval.jsonl", FIXTURES / "interpreter-eval-replies.jsonl"
TEXT, SUMMARY = "PLANTED owner text 7Q", "PLANTED pending summary 9Z"  # must never reach stderr
OP = {"op": "product.hide", "args": {"id": "photo-product-098"}}


class LoadCasesRefusalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.rows = [json.loads(line) for line in CASES.read_text("utf-8").splitlines()]
        self.ops_line = next(n for n, r in enumerate(self.rows, 1) if r["id"] == "e22")  # an ops case with revises

    def kind_line(self, kind):
        return next(n for n, r in enumerate(self.rows, 1) if r["expect"] == {kind: True})

    def case_file(self, line, pending=None, expect=None):
        """The real cases with only ``line`` edited (planted text and summaries)."""
        rows = [dict(r) for r in self.rows]
        row = rows[line - 1]
        row["text"] = TEXT
        if pending is not None: row["pending"] = [dict(p, summary=SUMMARY) for p in pending]
        if expect is not None: row["expect"] = expect
        path = self.tmp / "cases.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        return path

    def run_main(self, path):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ev.main(["score", "--cases", str(path), "--replies", str(REPLIES)])
        return code, out.getvalue(), err.getvalue()

    def assertRefused(self, path, line, reason, planted=()):
        code, out, err = self.run_main(path)
        self.assertEqual((code, out, err), (2, "", f"interpreter_eval: cases line {line}: {reason}\n"))
        for secret in (TEXT, SUMMARY, "Traceback", *planted):
            self.assertNotIn(secret, err)
        with self.assertRaises(ev.EvalError): ev.load_cases(path)

    def assertLoads(self, path):
        self.assertEqual(len(ev.load_cases(path)), 69)
        code, out, err = self.run_main(path)
        self.assertEqual((code, err, json.loads(out)["cases"]), (0, "", 69))

    def test_real_fixture_loads_63_cases_unchanged(self):
        self.assertEqual(ev.load_cases(CASES), self.rows)
        self.assertEqual(len(self.rows), 69)

    def test_bad_pending_code_refused(self):
        bad = [{"code": ["a"]}, {"code": 7}, {"code": ""}, {"code": "a b"}, {"code": "x" * 17}, {},
               {"code": None}, {"code": True}, {"code": "a\tb"}, {"code": "a\x00b"}, {"code": "a\u2028b"},
               {"code": "a\u00a0b"}, {"code": {"k": "v"}}]
        for entry in bad:
            with self.subTest(entry=entry):
                path = self.case_file(self.ops_line, [{"code": "a1b2"}, entry], {"ops": [OP], "revises": "a1b2"})
                self.assertRefused(path, self.ops_line, "bad pending code")
        for entry in ({"code": ["a"]}, {"code": "a b"}):  # also on a question case, where nothing else is checked
            with self.subTest(question=entry):
                path = self.case_file(self.kind_line("question"), [entry])
                self.assertRefused(path, self.kind_line("question"), "bad pending code", ["a b"])

    def test_code_limits_that_still_load(self):
        for code in ("a", "x" * 16, "A-1_b.2"):
            with self.subTest(code=code):
                self.assertLoads(self.case_file(self.ops_line, [{"code": code}], {"ops": [OP], "revises": code}))

    def test_repeated_pending_code_refused(self):
        path = self.case_file(self.ops_line, [{"code": "a1b2"}, {"code": "a1b2"}], {"ops": [OP], "revises": "a1b2"})
        self.assertRefused(path, self.ops_line, "repeated pending code", ["a1b2"])
        path = self.case_file(self.kind_line("unsupported"), [{"code": "q1q1"}, {"code": "q1q1"}])
        self.assertRefused(path, self.kind_line("unsupported"), "repeated pending code", ["q1q1"])

    def test_revises_naming_no_pending_draft_refused(self):
        for pending in ([{"code": "a1b2"}], [], [{"code": "a1b2"}, {"code": "c3d4"}]):
            with self.subTest(pending=pending):
                path = self.case_file(self.ops_line, pending, {"ops": [OP], "revises": "zzzz"})
                self.assertRefused(path, self.ops_line, "revises names no pending draft", ["zzzz", "a1b2"])

    def test_revises_null_or_a_pending_code_loads(self):
        two = [{"code": "a1b2"}, {"code": "c3d4"}]
        for pending, revises in ((two, "c3d4"), (two, None), ([], None)):
            with self.subTest(revises=revises, pending=len(pending)):
                self.assertLoads(self.case_file(self.ops_line, pending, {"ops": [OP], "revises": revises}))

    def test_more_than_max_ops_refused_exactly_max_loads(self):
        most = interpret_check.MAX_OPS
        path = self.case_file(self.ops_line, [{"code": "a1b2"}], {"ops": [OP] * (most + 1), "revises": "a1b2"})
        self.assertRefused(path, self.ops_line, f"more than {most} expected ops", ["photo-product-098"])
        self.assertLoads(self.case_file(self.ops_line, [{"code": "a1b2"}], {"ops": [OP] * most, "revises": "a1b2"}))

    def test_question_or_unsupported_case_with_pending_codes_loads(self):
        for kind in ("question", "unsupported"):
            with self.subTest(kind=kind):
                self.assertLoads(self.case_file(self.kind_line(kind), [{"code": "q1"}, {"code": "q2"}]))

    def test_refusal_is_by_first_bad_line(self):
        rows = [dict(r) for r in self.rows]
        rows[4]["pending"], rows[9]["pending"] = [{"code": 1}], [{"code": "a"}, {"code": "a"}]
        path = self.tmp / "two.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        self.assertEqual(self.run_main(path)[2], "interpreter_eval: cases line 5: bad pending code\n")


class V4NotesTests(base.EvalTestCase):
    """AV1102-10: the v4 cases, the optional `notes` on a case, and how live() and the scorer treat them."""

    def notes_file(self, notes, case_id="e62"):
        rows = [dict(r, text=TEXT) if r["id"] == case_id else r for r in self.cases]
        next(r for r in rows if r["id"] == case_id)["notes"] = notes
        path = self.tmp / "notes.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        return path, 1 + [r["id"] for r in rows].index(case_id)

    def test_real_fixture_has_8_new_unique_cases_and_two_with_notes(self):
        ids = [c["id"] for c in self.cases]
        self.assertEqual((ids[55:63], len(set(ids))), ([f"e{n}" for n in range(56, 64)], 69))
        self.assertTrue(all(ev.ID_RE.fullmatch(i) for i in ids))
        self.assertEqual({c["id"] for c in self.cases if "notes" in c}, {"e62", "e63"})
        self.assertEqual([c["expect"] for c in self.cases[56:61:2]][:1], [{"question": True}])
        self.assertEqual([c["expect"] for c in self.cases[59:61]], [{"unsupported": True}] * 2)

    def test_bad_notes_exit_2_naming_the_line_never_the_text(self):
        good = {"key": "tone", "text": "short"}
        bad = ["x", {}, "", None, [good, "x"], [good] * 21, [dict(good, extra="y")], [{"key": "tone"}],
               [{"key": 1, "text": "a"}], [{"key": "k", "text": ["a"]}], {"key": "k", "text": "t"}]
        for notes in bad:
            with self.subTest(notes=notes):
                path, line = self.notes_file(notes)
                code, out, err = LoadCasesRefusalTests.run_main(self, path)
                self.assertEqual((code, out, err), (2, "", f"interpreter_eval: cases line {line}: bad notes\n"))
                self.assertNotIn(TEXT, err)

    def test_up_to_20_notes_or_none_load(self):
        for notes in ([], [{"key": "k", "text": "t"}] * 20):
            with self.subTest(n=len(notes)):
                path, _ = self.notes_file(notes)
                self.assertEqual(len(ev.load_cases(path)), 69)

    def captured_requests(self):
        bodies = []

        def transport(url, body, headers, timeout):
            bodies.append(json.loads(json.loads(body)["messages"][1]["content"]))
            return 200, json.dumps({"done": True, "message": {"content": '{"question": "Which one?"}'}}).encode()
        out = self.tmp / "fresh.jsonl"
        code, _, _ = base.run("--live", "--url", base.URL, "--model", "m", "--out", out, transport=transport)
        self.assertEqual((code, len(bodies)), (0, 69))
        return bodies

    def test_live_sends_notes_only_for_cases_that_have_them(self):
        for case, sent in zip(self.cases, self.captured_requests()):
            with self.subTest(case=case["id"]):
                self.assertEqual((sent["message"], sent["pending"]), (case["text"], case["pending"]))
                if case.get("notes"):
                    self.assertEqual(sent["notes"], case["notes"])
                else:  # exactly the four fields a no-notes request has today
                    self.assertEqual(set(sent), {"message", "pending", "today", "weekday"})

    def test_organic_claim_on_the_farm_note_case_fails_by_the_existing_rule(self):
        args = self.replies["e63"]["ops"][0]["args"]
        maker = {"ops": [{"op": "product.add", "args": {**args, "producerKey": "Etto"}}], "revises": None}
        self.assertEqual(self.why("e63", maker), ["op 1 product.add: unexpected claim arg producerKey"])
        organic = {"ops": [{"op": "product.add", "args": {**args, "organic": True}}], "revises": None}  # not an arg
        self.assertEqual(self.why("e63", organic), ["expected ops, got question"])
        self.assertEqual(self.why("e63", self.replies["e63"]), [])
        self.assertEqual(self.why("e62", self.replies["e62"]), [])

    def test_replies_file_missing_a_new_id_scores_it_failed_and_exits_0(self):
        rows = [json.dumps({"id": k, "reply": v}) for k, v in self.replies.items() if k != "e62"]
        path = self.tmp / "r.jsonl"
        path.write_text("\n".join(rows) + "\n", "utf-8")
        code, out, err = base.scored(CASES, path)
        summary = json.loads(out)
        self.assertEqual((code, err, summary["missing"], summary["passed"]), (0, "", ["e62"], 65))


class V5PhoneAndHikeTextTests(base.EvalTestCase):
    """AV1222-09: the 6 v5 cases (store phone, partial hike text edits) and the hike overlay that live() lays over the content."""

    def prompts(self, **kw):
        bodies = []

        def transport(url, body, headers, timeout):
            bodies.append(json.loads(body)["messages"][0]["content"])
            return 200, json.dumps({"done": True, "message": {"content": '{"question": "Which one?"}'}}).encode()
        code, _, err = base.run("--live", "--url", base.URL, "--model", "m", "--out", self.tmp / "o.jsonl", transport=transport)
        return code, err, bodies

    def test_six_new_cases_follow_the_v4_ones_and_are_valid_for_the_registry(self):
        new = self.cases[63:]
        self.assertEqual([c["id"] for c in new], [f"e{n}" for n in range(64, 70)])
        self.assertEqual([c["expect"].get("ops", [{}])[0].get("op") for c in new],
                         ["store.set_phone", "store.clear_phone", None, "hike.update", "hike.update", "hike.update"])
        self.assertEqual(new[2]["expect"], {"question": True})
        for case in new:  # the existing scorability rule: op names exist and args are valid for the op
            if "ops" in case["expect"]:
                result = {"ops": case["expect"]["ops"], "revises": None}
                self.assertIs(interpret_check.check(result, base.REGISTRY, set()), result, case["id"])
        self.assertEqual(self.why("e64", self.replies["e64"]), [])

    def test_partial_edit_expectations_are_the_whole_fixture_text_plus_the_change(self):
        hike = json.loads(ev.EVENTS.read_text("utf-8"))[0]
        args = {c["id"]: c["expect"]["ops"][0]["args"] for c in self.cases[66:]}
        self.assertEqual(args["e67"]["bring"], hike["bring"] + ", sunscreen")
        self.assertTrue(args["e68"]["accessNote"].startswith(hike["accessNote"]))
        self.assertNotEqual(args["e69"]["meetingPoint"], hike["meetingPoint"])
        self.assertEqual({a["id"] for a in args.values()}, {hike["id"]})

    def test_a_resend_of_only_the_new_part_or_a_short_number_fails_by_name(self):
        part = {"ops": [{"op": "hike.update", "args": {"id": "hike-2026-11-14-point-buchon", "bring": "sunscreen"}}], "revises": None}
        self.assertEqual(self.why("e67", part), ["op 1 hike.update: arg bring differs"])
        self.assertEqual(self.why("e66", self.replies["e64"]), ["expected question, got ops"])
        self.assertEqual(self.why("e64", self.replies["e66"]), ["expected ops, got question"])

    def test_live_prompt_lists_the_fixture_hike_details_and_content_files_stay_unchanged(self):
        watched = [p for p in (ev.REPO / "hass" / "content").rglob("*") if p.is_file()]
        before = {p: p.read_bytes() for p in watched}
        code, err, bodies = self.prompts()
        self.assertEqual((code, err, len(bodies)), (0, "", 69))
        hike = json.loads(ev.EVENTS.read_text("utf-8"))[0]
        row = " | ".join(json.dumps(str(hike[k]), ensure_ascii=False) for k in ("id", "meetingPoint", "capacity", "bring", "accessNote"))
        self.assertTrue(row in bodies[0], "fixture hike details row missing from the live prompt")
        self.assertEqual({p: p.read_bytes() for p in watched}, before)

    def test_overlay_id_already_in_the_content_is_refused_naming_it(self):
        events = self.tmp / "events.json"
        events.write_text(json.dumps([{"id": "dup-1", "status": "scheduled"}]), "utf-8")
        content = load_content()
        content.community["events"] = [{"id": "dup-1", "title": "T", "status": "scheduled"}]
        with unittest.mock.patch.object(ev, "EVENTS", events):
            with self.assertRaisesRegex(ev.EvalError, "dup-1"):
                ev.live(self.cases, base.URL, "m", self.tmp / "o.jsonl", content=content)
        self.assertFalse((self.tmp / "o.jsonl").exists())

    def test_no_case_text_holds_an_email_or_a_phone_outside_555_01xx(self):
        for case in self.cases:
            text = json.dumps(case)
            self.assertNotRegex(text, r"@\S+\.\S+", case["id"])
            for number in re.findall(r"\d{3}\D{0,2}\d{4}", text):
                self.assertRegex(number, r"^555\D{0,2}01\d\d$|^555\D{0,2}0123$", (case["id"], number))
        for line in ev.EVENTS.read_text("utf-8").splitlines():
            self.assertNotRegex(line, r"@\S+\.\S+")


if __name__ == "__main__":
    unittest.main()
