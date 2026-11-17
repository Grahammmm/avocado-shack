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
        self.assertEqual(len(ev.load_cases(path)), 84)
        code, out, err = self.run_main(path)
        self.assertEqual((code, err, json.loads(out)["cases"]), (0, "", 84))

    def test_real_fixture_loads_63_cases_unchanged(self):
        self.assertEqual(ev.load_cases(CASES), self.rows)
        self.assertEqual(len(self.rows), 84)

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

    def test_no_draft_expectation_requires_literal_true(self):  # RF1155-12
        for key in ("question", "unsupported"):
            self.assertTrue(ev._expect_ok(json.loads('{"%s": true}' % key)))
            for raw in ("1", "1.0", "1e0", "false", "0", "null", '"true"', "[true]", "{}"):
                self.assertFalse(ev._expect_ok(json.loads('{"%s": %s}' % (key, raw))), (key, raw))
        self.assertFalse(ev._expect_ok({"question": True, "unsupported": True}))
        self.assertFalse(ev._expect_ok([True]))

    def test_score_and_compare_reject_numeric_expectation_by_first_bad_line(self):
        late = next(n for n, r in enumerate(self.rows, 1) if r["expect"] == {"unsupported": True})
        early = self.kind_line("question")
        first, second = sorted((early, late))
        rows = [dict(r) for r in self.rows]
        rows[first - 1]["expect"] = {next(iter(rows[first - 1]["expect"])): 1}
        rows[second - 1]["expect"] = {next(iter(rows[second - 1]["expect"])): 1.0}
        path = self.tmp / "numeric.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        self.assertRefused(path, first, "not a case")
        out, err = io.StringIO(), io.StringIO()
        missing = str(self.tmp / "absent.jsonl")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ev.main(["compare", "--cases", str(path), "--before", missing, "--after", missing])
        self.assertEqual((code, out.getvalue(), err.getvalue()), (2, "", f"interpreter_eval: cases line {first}: not a case\n"))


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
        self.assertEqual((ids[55:63], len(set(ids))), ([f"e{n}" for n in range(56, 64)], 84))
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
                self.assertEqual(len(ev.load_cases(path)), 84)

    def captured_requests(self):
        bodies = []

        def transport(url, body, headers, timeout):
            bodies.append(json.loads(json.loads(body)["messages"][1]["content"]))
            return 200, json.dumps({"done": True, "message": {"content": '{"question": "Which one?"}'}}).encode()
        out = self.tmp / "fresh.jsonl"
        code, _, _ = base.run("--live", "--url", base.URL, "--model", "m", "--out", out, transport=transport)
        self.assertEqual((code, len(bodies)), (0, 84))
        return bodies

    def test_live_sends_notes_only_for_cases_that_have_them(self):
        for case, sent in zip(self.cases, self.captured_requests()):
            with self.subTest(case=case["id"]):
                self.assertEqual((sent["message"], sent["pending"]), (case["text"], case["pending"]))
                if case.get("notes"):
                    self.assertEqual(sent["notes"], case["notes"])
                else:  # exactly the four fields a no-notes request has today (AV0007-10: plus aliases when the case has some)
                    self.assertEqual(set(sent), {"message", "pending", "today", "weekday"} | ({"aliases"} if case.get("aliases") else set()))

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
        self.assertEqual((code, err, summary["missing"], summary["passed"]), (0, "", ["e62"], 80))


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
        new = self.cases[63:69]
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
        args = {c["id"]: c["expect"]["ops"][0]["args"] for c in self.cases[66:69]}
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
        self.assertEqual((code, err, len(bodies)), (0, "", 84))
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


def _ops(*calls): return {"ops": [{"op": op, "args": args} for op, args in calls], "revises": None}


class V8GroupAndCopySlotTests(base.EvalTestCase):
    """AV2152-13: the six v8 cases (whole shelf, whole maker, partial description, cancel note, notice first day, club
    intro) and the unchanged scorer's verdict on mutated replies. Synthetic replies only; no model call."""

    NEW = [f"e{n}" for n in range(70, 76)]
    OLD = ("Sourdough from Brian’s in Atascadero. A crust worth tearing, a loaf that belongs beside soup. "
           "Butter is enough; the rest is optional.")
    ETTO = [f"photo-product-{n}" for n in ("082", "171", "172", "173", "174")]
    CANCEL = ("hike.cancel", {"id": "hike-2026-11-22-cass-hill", "note": "Rained out - we will pick a new date soon."})
    NOTICE = ("store.set_notice", {"text": "Closed Thanksgiving Day", "from": "2026-11-26", "until": "2026-11-26"})
    INTRO = "Walk with us along the coast, share the trail, and leave room for discovery."

    def case(self, case_id): return next(c for c in self.cases if c["id"] == case_id)

    def avail(self, ids, available="limited"):
        return _ops(*[("product.set_availability", {"id": i, "available": available}) for i in ids])

    def test_v8_six_cases_shapes_and_membership(self):
        new = self.cases[69:75]
        self.assertEqual([c["id"] for c in new], self.NEW)
        self.assertEqual(len({c["id"] for c in self.cases}), 84)
        self.assertEqual([c["text"] for c in new], [
            "Everything on the flowers shelf is limited.", "All the Etto products are limited.",
            "Add \"Great on toast.\" to the end of Brian's sourdough bread description; keep every existing sentence.",
            "Cancel hike hike-2026-11-22-cass-hill with the note: Rained out - we will pick a new date soon.",
            "Set the home notice to \"Closed Thanksgiving Day\" from 2026-11-26 through 2026-11-26.",
            "Set the hiking club opening paragraph to: " + self.INTRO])
        self.assertTrue(all(set(c) == {"id", "text", "pending", "expect"} and c["pending"] == [] and
                            c["expect"]["revises"] is None for c in new))
        self.assertEqual([[o["op"] for o in c["expect"]["ops"]] for c in new],
                         [["product.set_availability"], ["product.set_availability"] * 5, ["product.edit"],
                          ["hike.cancel"], ["store.set_notice"], ["club.set_intro"]])
        products = load_content().products  # membership frozen from the catalog on main, not from a reply
        flowers = sorted(p["id"] for p in products if p["category"] == "flowers" and p["status"] == "active")
        etto = sorted(p["id"] for p in products if p.get("producerKey") == "Etto" and p["status"] == "active")
        self.assertEqual((flowers, etto), (["photo-product-006"], self.ETTO))  # the flowers shelf has ONE member on main
        self.assertEqual([o["args"] for o in self.case("e70")["expect"]["ops"]],
                         [{"id": "photo-product-006", "available": "limited"}])
        self.assertEqual([o["args"] for o in self.case("e71")["expect"]["ops"]],
                         [{"id": i, "available": "limited"} for i in self.ETTO])
        for case in new:  # registry-valid, as every earlier case is
            result = {"ops": case["expect"]["ops"], "revises": None}
            self.assertIs(interpret_check.check(result, base.REGISTRY, set()), result, case["id"])
        self.assertEqual([self.why(i, self.replies[i]) for i in self.NEW], [[]] * 6)

    def test_v8_group_missing_extra_wrong_id_or_order_fails(self):
        self.assertEqual(self.why("e71", self.avail(self.ETTO)), [])
        for short in (self.ETTO[1:], self.ETTO[:-1]):  # first or last member left out
            self.assertTrue(self.why("e71", self.avail(short))[0].startswith("ops "))
        self.assertTrue(self.why("e71", self.avail(self.ETTO + ["photo-product-006"]))[0].startswith("ops "))  # extra op
        self.assertEqual(self.why("e71", self.avail(["photo-product-006"] + self.ETTO[1:])), ["op 1 product.set_availability: arg id differs"])
        self.assertEqual(self.why("e71", self.avail(self.ETTO[:-1] + ["photo-product-006"])), ["op 5 product.set_availability: arg id differs"])
        self.assertEqual(self.why("e71", self.avail(self.ETTO, "no")), ["op 1 product.set_availability: arg available differs"])
        self.assertEqual(self.why("e71", self.avail(self.ETTO[::-1])), ["op 1 product.set_availability: arg id differs"])
        self.assertEqual(self.why("e70", self.avail(["photo-product-082"])), ["op 1 product.set_availability: arg id differs"])
        self.assertEqual(self.why("e70", self.avail(["photo-product-006"], "no")), ["op 1 product.set_availability: arg available differs"])

    def test_v8_description_preserves_all_old_text(self):
        def edit(pid, text): return _ops(("product.edit", {"id": pid, "description": text}))
        self.assertEqual(self.why("e72", edit("photo-product-015", self.OLD + " Great on toast.")), [])
        for bad in ("Great on toast.", self.OLD, self.OLD.split(". ")[0] + ". Great on toast.", self.OLD + "Great on toast."):
            self.assertEqual(self.why("e72", edit("photo-product-015", bad)), ["op 1 product.edit: arg description differs"])
        self.assertEqual(self.why("e72", edit("photo-product-082", self.OLD + " Great on toast.")), ["op 1 product.edit: arg id differs"])
        self.assertEqual(self.why("e72", _ops(("product.edit", {"id": "photo-product-015"}))), ["op 1 product.edit: missing arg description"])
        self.assertEqual(self.why("e72", {"question": "Which sentences should stay?"}), ["expected ops, got question"])

    def test_v8_cancel_note_required_in_reply(self):
        self.assertEqual(self.why("e73", _ops(self.CANCEL)), [])
        no_note = _ops(("hike.cancel", {"id": "hike-2026-11-22-cass-hill"}))
        self.assertEqual(self.why("e73", no_note), ["op 1 hike.cancel: missing arg note"])
        changed = _ops(("hike.cancel", {**self.CANCEL[1], "note": "Rained out"}))
        self.assertEqual(self.why("e73", changed), ["op 1 hike.cancel: arg note differs"])
        update = _ops(("hike.update", {"id": "hike-2026-11-22-cass-hill", "accessNote": self.CANCEL[1]["note"]}))
        self.assertEqual(self.why("e73", update), ["ops hike.update but expected hike.cancel"])
        self.assertEqual(self.why("e18", no_note), [])  # the inherited cancel without a note is unchanged

    def test_v8_notice_requires_first_and_last_days(self):
        self.assertEqual(self.why("e74", _ops(self.NOTICE)), [])
        args = self.NOTICE[1]
        no_from = {k: v for k, v in args.items() if k != "from"}
        self.assertEqual(self.why("e74", _ops(("store.set_notice", no_from))), ["op 1 store.set_notice: missing arg from"])
        for name, value in (("from", "2026-11-25"), ("until", "2026-11-27"), ("text", "Closed Thanksgiving")):
            self.assertEqual(self.why("e74", _ops(("store.set_notice", {**args, name: value}))),
                             [f"op 1 store.set_notice: arg {name} differs"])
        no_until = {k: v for k, v in args.items() if k != "until"}
        self.assertTrue(self.why("e74", _ops(("store.set_notice", no_until))))  # until is required by the op itself

    def test_v8_club_intro_not_store_intro(self):
        self.assertEqual(self.why("e75", _ops(("club.set_intro", {"text": self.INTRO}))), [])
        self.assertEqual(self.why("e75", _ops(("store.set_intro", {"text": self.INTRO}))), ["ops store.set_intro but expected club.set_intro"])
        self.assertEqual(self.why("e75", _ops(("club.set_intro", {"text": self.INTRO[:-1] + "!"}))), ["op 1 club.set_intro: arg text differs"])
        self.assertEqual(self.why("e75", _ops(("club.set_intro", {"text": "Walk with us along the coast."}))), ["op 1 club.set_intro: arg text differs"])
        self.assertTrue(self.why("e75", _ops(("club.set_intro", {}))))  # text is required by the op itself

    def test_v8_prior_scores_and_refusals_unchanged(self):
        code, out, err = base.scored(CASES, REPLIES)
        summary = json.loads(out)
        self.assertEqual((code, err, summary["passed"], [f["id"] for f in summary["failed"]]), (0, "", 81, ["e06", "e13", "e25"]))
        old = ev.score(self.cases[:69], self.replies, base.REGISTRY)  # the 69 earlier cases score exactly as before
        self.assertEqual((old["passed"], [f["id"] for f in old["failed"]]), (66, ["e06", "e13", "e25"]))
        got = lambda skip=(), more=(): base.scored(CASES, self.write("r.jsonl", [{"id": k, "reply": v} for k, v in self.replies.items() if k not in skip] + list(more)))  # noqa: E731
        code, out, _ = got(skip=("e75",))
        self.assertEqual((code, json.loads(out)["missing"], json.loads(out)["passed"]), (0, ["e75"], 80))
        code, out, _ = got(more=[{"id": "e99", "reply": {"question": "?"}}])
        self.assertEqual((code, json.loads(out)["extra"], json.loads(out)["passed"]), (0, ["e99"], 81))
        self.assertEqual(base.scored(self.write("c.jsonl", self.rows[:83]), REPLIES), (2, "", "cases: 83 cases, expected 84"))
        self.assertEqual(base.scored(self.write("d.jsonl", self.rows[:83] + [self.rows[0]]), REPLIES), (2, "", "cases line 84: duplicate id"))


class V6SamplesPhotoAvailabilityTests(base.EvalTestCase):
    """AV1622-12: the five v6 cases (sample hikes hide/show, old photo back, stop showing sold out vs sold out)."""

    NEW = ["e76", "e77", "e78", "e79", "e80"]
    EGGS = "photo-product-024"

    def ops(self, op, **args): return _ops((op, args))

    def test_v6_five_cases_match_registry(self):
        new = self.cases[75:80]
        self.assertEqual(([c["id"] for c in new], len({c["id"] for c in self.cases})), (self.NEW, 84))
        self.assertTrue(all(set(c) == {"id", "text", "pending", "expect"} and c["pending"] == [] and
                            c["expect"]["revises"] is None for c in new))
        self.assertEqual([[(o["op"], o["args"]) for o in c["expect"]["ops"]] for c in new], [
            [("hike.samples", {"show": False})], [("hike.samples", {"show": True})],
            [("store.clear_home_image", {})],
            [("product.clear_availability", {"id": self.EGGS})],
            [("product.set_availability", {"id": self.EGGS, "available": "no"})]])
        eggs = [p for p in load_content().products if p["id"] == self.EGGS]
        self.assertEqual([(p["name"], p["status"]) for p in eggs], [("Cal Poly eggs", "active")])
        for case in new:
            result = {"ops": case["expect"]["ops"], "revises": None}
            self.assertIs(interpret_check.check(result, base.REGISTRY, set()), result, case["id"])
        self.assertEqual([self.why(i, self.replies[i]) for i in self.NEW], [[]] * 5)

    def test_v6_clear_is_not_sold_out(self):
        clear, sold = self.replies["e79"], self.replies["e80"]
        self.assertEqual(self.why("e79", sold), ["ops product.set_availability but expected product.clear_availability"])
        self.assertEqual(self.why("e80", clear), ["ops product.clear_availability but expected product.set_availability"])
        self.assertEqual((self.why("e79", clear), self.why("e80", sold)), ([], []))
        self.assertEqual(self.why("e80", self.ops("product.set_availability", id=self.EGGS, available="limited")),
                         ["op 1 product.set_availability: arg available differs"])

    def test_v6_sample_bool_and_photo_clear(self):
        self.assertEqual(self.why("e76", self.ops("hike.samples", show=True)), ["op 1 hike.samples: arg show differs"])
        self.assertEqual(self.why("e77", self.ops("hike.samples", show=False)), ["op 1 hike.samples: arg show differs"])
        self.assertEqual(self.why("e78", self.ops("hike.samples", show=True)),
                         ["ops hike.samples but expected store.clear_home_image"])
        self.assertEqual(self.why("e78", self.ops("product.clear_availability", id=self.EGGS)),
                         ["ops product.clear_availability but expected store.clear_home_image"])

    def test_v6_preserves_previous_scores(self):
        old = ev.score(self.cases[:75], self.replies, base.REGISTRY)
        new = ev.score(self.cases, self.replies, base.REGISTRY)
        self.assertEqual((old["passed"], new["passed"]), (72, 81))
        self.assertEqual(old["failed"], new["failed"])  # the three intentional negatives are the only failures
        self.assertEqual((new["missing"], new["extra"]), ([], []))
        code, out, err = base.scored(CASES, self.write("r.jsonl", [{"id": k, "reply": v} for k, v in self.replies.items() if k != "e79"]))
        self.assertEqual((code, err, json.loads(out)["missing"], json.loads(out)["passed"]), (0, "", ["e79"], 80))

    def test_v6_count_bounds(self):
        too_few = base.scored(self.write("a.jsonl", self.rows[:83]), REPLIES)
        self.assertEqual(too_few, (2, "", "cases: 83 cases, expected 84"))
        extra = dict(json.loads(self.rows[0]), id="e99")
        self.assertEqual(base.scored(self.write("b.jsonl", self.rows + [json.dumps(extra)]), REPLIES),
                         (2, "", "cases: 85 cases, expected 84"))
        self.assertEqual(base.scored(self.write("c.jsonl", self.rows[:83] + [self.rows[0]]), REPLIES),
                         (2, "", "cases line 84: duplicate id"))


class V9UndoBrandAliasPhotoTests(base.EvalTestCase):
    """AV0007-10: the four v9 cases (undo guidance, brand-only new product, owner alias, missing-field photo answer),
    the optional `aliases` context and its forwarding. Synthetic replies and a fake transport only; no model call."""

    NEW, n = ["e81", "e82", "e83", "e84"], iter(range(100))
    HASH = "5ca1ab1e" * 8

    def case(self, case_id): return next(c for c in self.cases if c["id"] == case_id)

    def rows_with(self, case_id, **change):
        rows = [dict(c) for c in self.cases]
        next(r for r in rows if r["id"] == case_id).update(change)
        return self.write("v9.jsonl", rows)

    def requests(self, cases_path):
        bodies = []

        def transport(url, body, headers, timeout):
            bodies.append(json.loads(json.loads(body)["messages"][1]["content"]))
            return 200, json.dumps({"done": True, "message": {"content": '{"question": "Which one?"}'}}).encode()
        code, _, err = base.run("--live", "--cases", cases_path, "--url", base.URL, "--model", "m",
                                "--out", self.tmp / f"out{next(self.n)}.jsonl", transport=transport)
        self.assertEqual((code, err), (0, ""))
        return bodies

    def test_v9_four_cases_and_synthetic_replies(self):
        self.assertEqual([c["id"] for c in self.cases[80:]], self.NEW)
        self.assertEqual([c["text"] for c in (self.case(i) for i in self.NEW)][0::2],
                         ["undo the hours change", "the green jam is sold out"])
        self.assertEqual(self.case("e81")["expect"], {"question": True})
        self.assertEqual(self.case("e81")["pending"], [])
        self.assertEqual(list(self.replies["e81"]), ["question"])
        self.assertIn("undo", self.replies["e81"]["question"])
        self.assertIn("history", self.replies["e81"]["question"])
        blob = json.dumps([self.case(i) for i in self.NEW] + [self.replies[i] for i in self.NEW])
        self.assertNotIn("history.revert", blob)
        self.assertEqual(ev.score(self.cases[80:], self.replies, base.REGISTRY)["passed"], 4)

    def test_v9_add_without_display_brand(self):
        args = self.case("e82")["expect"]["ops"][0]["args"]
        self.assertEqual(args, {"name": "Juniper oat crackers", "brand": "Fixture Pantry", "category": "pantry",
                                "description": "Crisp oat crackers.", "photo": self.HASH, "imageAlt": "A packet of oat crackers"})
        self.assertNotIn("displayBrand", self.replies["e82"]["ops"][0]["args"])
        self.assertEqual(self.case("e82")["expect"]["revises"], None)
        self.assertEqual(self.why("e82", self.replies["e82"]), [])
        for key, wrong in (("photo", "ab" * 32), ("name", "Oat crackers"), ("brand", "Other"), ("category", "bread"),
                           ("description", "Crunchy."), ("imageAlt", "A crate")):
            reply = json.loads(json.dumps(self.replies["e82"]))
            reply["ops"][0]["args"][key] = wrong
            self.assertEqual(len(self.why("e82", reply)), 1, key)
            del reply["ops"][0]["args"][key]
            self.assertEqual(len(self.why("e82", reply)), 1, key)

    def test_v9_alias_target_and_availability(self):
        self.assertEqual(self.case("e83")["aliases"], [{"name": "green jam", "kind": "product", "id": "photo-product-001"}])
        self.assertEqual(self.why("e83", self.replies["e83"]), [])
        good = self.replies["e83"]["ops"][0]
        for args in ({"id": "photo-product-002", "available": "no"}, {"id": "photo-product-001", "available": "limited"},
                     {"available": "no"}):
            self.assertEqual(len(self.why("e83", {"ops": [{"op": good["op"], "args": args}], "revises": None})), 1, args)
        self.assertTrue(self.why("e83", {"ops": [{"op": "product.hide", "args": {"id": "photo-product-001"}}], "revises": None}))

    def test_v9_missing_field_photo_answer(self):
        entry = self.case("e84")["pending"][0]
        self.assertEqual((entry["state"], entry["missing"]), ("needs-details", ["imageAlt"]))
        self.assertEqual(entry["ops"][0]["args"]["photo"], self.HASH)
        self.assertEqual(self.case("e84")["expect"]["revises"], entry["code"])
        self.assertEqual(self.why("e84", self.replies["e84"]), [])
        for mutate in (lambda a: a.pop("imageAlt"), lambda a: a.update(imageAlt="Something else"),
                       lambda a: a.update(photo="ab" * 32), lambda a: a.update(id="photo-product-002")):
            reply = json.loads(json.dumps(self.replies["e84"]))
            mutate(reply["ops"][0]["args"])
            self.assertEqual(len(self.why("e84", reply)), 1)
        for revises in (None, "zzzz"):
            self.assertTrue(self.why("e84", dict(self.replies["e84"], revises=revises)), revises)

    def test_v9_alias_context_validation(self):
        good = {"name": "green jam", "kind": "product", "id": "photo-product-001"}
        for bad in (None, "x", {"a": 1}, [good] * 51, [dict(good, extra="x")], [{"name": "a", "kind": "product"}],
                    [dict(good, kind="shelf")], [dict(good, name=3)], [dict(good, id=None)], ["green jam"]):
            with self.subTest(bad=str(bad)[:30]):
                code, out, err = base.scored(self.rows_with("e83", aliases=bad), REPLIES)
                self.assertEqual((code, out, err), (2, "", "cases line 83: bad aliases"))
        self.assertEqual(len(ev.load_cases(self.rows_with("e83", aliases=[good] * 50))), 84)
        self.assertEqual(len(ev.load_cases(self.rows_with("e83", aliases=[dict(good, kind="maker")]))), 84)

    def test_v9_context_forwarding(self):
        bodies = self.requests(CASES)
        self.assertEqual([("aliases" in b) for b in bodies], [False] * 82 + [True] + [False])
        self.assertEqual(bodies[82]["aliases"], self.case("e83")["aliases"])
        self.assertEqual(bodies[82]["message"], "the green jam is sold out")
        self.assertEqual(bodies[82]["pending"], [])
        notes = [{"key": "k", "text": "t"}]
        both = self.requests(self.rows_with("e83", notes=notes))[82]
        self.assertEqual((both["aliases"], both["notes"]), (self.case("e83")["aliases"], notes))
        empty = self.requests(self.rows_with("e83", aliases=[]))[82]
        self.assertNotIn("aliases", empty)

    def test_v9_prior_scores_and_refusals_unchanged(self):
        old = ev.score(self.cases[:80], self.replies, base.REGISTRY)
        self.assertEqual((old["passed"], [f["id"] for f in old["failed"]]), (77, ["e06", "e13", "e25"]))
        code, out, err = base.scored(CASES, self.write("r.jsonl", [{"id": k, "reply": v} for k, v in self.replies.items() if k != "e84"]))
        self.assertEqual((code, json.loads(out)["missing"], json.loads(out)["passed"], err), (0, ["e84"], 80, ""))
        self.assertEqual(base.scored(self.write("c.jsonl", self.rows[:83] + [self.rows[0]]), REPLIES),
                         (2, "", "cases line 84: duplicate id"))
        bad = self.rows_with("e84", pending=[dict(self.case("e84")["pending"][0], code="a b")])
        self.assertEqual(base.scored(bad, REPLIES), (2, "", "cases line 84: bad pending code"))
        _, out, _ = base.scored(CASES, REPLIES)
        for text in ("green jam", "oat crackers", "wooden crate", "undo the hours"):
            self.assertNotIn(text, out)


if __name__ == "__main__":
    unittest.main()
