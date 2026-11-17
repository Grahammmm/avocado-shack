"""NB-AV-04 tests: the interpreter eval set and offline scorer. No model, no socket: --live uses a fake transport."""

import contextlib, dataclasses, io, json, os, tempfile, unittest  # noqa: E401
from collections import Counter
from pathlib import Path

from hass import interpret_check, interpreter_eval as ev
from hass.content_model import load_content
from hass.ops import load_registry

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES, REPLIES = FIXTURES / "interpreter-eval.jsonl", FIXTURES / "interpreter-eval-replies.jsonl"
REGISTRY, URL = load_registry(), "http://127.0.0.1:11434"


def run(*argv, transport=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ev.main([str(a) for a in argv], transport=transport)
    return code, out.getvalue(), err.getvalue().removeprefix("interpreter_eval: ").strip()


def scored(cases, replies): return run("score", "--cases", cases, "--replies", replies)


class EvalTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.cases, self.replies = ev.load_cases(CASES), ev.load_replies(REPLIES)
        self.rows = CASES.read_text("utf-8").splitlines()

    def write(self, name, rows):
        path = self.tmp / name
        path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows), "utf-8")
        return path

    def why(self, case_id, reply):
        case = next(c for c in self.cases if c["id"] == case_id)
        return [f["why"] for f in ev.score([case], {case_id: reply}, REGISTRY)["failed"]]


class ScoreTests(EvalTestCase):
    def test_recorded_fixture_passes_60_and_names_the_3_wrong(self):
        code, out, err = scored(CASES, REPLIES)
        summary = json.loads(out)
        self.assertEqual((code, err, {k: summary[k] for k in ("cases", "passed", "missing", "extra")}),
                         (0, "", {"cases": 90, "passed": 87, "missing": [], "extra": []}))
        self.assertEqual(summary["failed"], [
            {"id": "e06", "why": "ops product.restore but expected product.hide"},  # wrong op
            {"id": "e13", "why": "op 1 hike.create: missing arg capacity"},  # missing arg
            {"id": "e25", "why": "expected question, got ops"}])  # answered instead of asking
        self.assertEqual(json.loads(REPLIES.read_text("utf-8").splitlines()[0]),
                         {"_note": "synthetic replies for scorer tests; not model output"})

    def test_output_never_holds_a_case_text_or_reply_body(self):
        _, out, _ = scored(CASES, REPLIES)
        bodies = [c["text"] for c in self.cases] + [r.get("question") or r.get("unsupported") or "" for r in
                                                    self.replies.values()]
        bodies += [s for r in self.replies.values() for c in r.get("ops", []) for v in c["args"].values()
                   for s in (v if isinstance(v, list) else [v]) if isinstance(s, str)]
        self.assertTrue(all(len(b) < 4 or b not in out for b in bodies))
        leak = self.cases[2]["text"]  # replies whose op name or arg value carry owner text
        named = {"ops": [{"op": leak, "args": {}}], "revises": None}
        valued = {"ops": [{"op": "product.edit", "args": {"id": "photo-product-081", "name": leak}}], "revises": None}
        for got in (self.why("e03", named), self.why("e01", valued), self.why("e04", valued)):
            self.assertTrue(got and leak not in json.dumps(got), got)

    def test_spread_and_expected_ops_valid_against_real_registry_and_catalog(self):
        content, kinds = load_content(), Counter()
        products, trails = {p["id"] for p in content.products}, {r["id"] for r in content.community["routeIdeas"]}
        for case in self.cases:
            expect = case["expect"]
            kinds[next(iter(expect)) if "ops" not in expect else "revises" if expect["revises"]
                  else expect["ops"][0]["op"].split(".")[0]] += 1
            if "ops" not in expect: continue
            result = {"ops": expect["ops"], "revises": expect["revises"]}
            codes = {p["code"] for p in case["pending"]}
            self.assertIs(interpret_check.check(result, REGISTRY, codes), result, case["id"])  # names/kinds/code
            for call in expect["ops"]:
                op, args = call["op"], call["args"]
                if op.startswith("product.") and "id" in args: self.assertIn(args["id"], products, case["id"])
                if op in ("maker.edit", "maker.hide", "maker.restore"): self.assertIn(args["key"], content.makers)
                if "trailId" in args: self.assertIn(args["trailId"], trails)
                if op == "route.edit": self.assertIn(args["id"], trails, case["id"])
                if "photo" in args: self.assertRegex(args["photo"], r"\A[0-9a-f]{64}\Z", case["id"])
        self.assertEqual(kinds, {"product": 20, "maker": 8, "club": 1, "hike": 15, "store": 16, "route": 8, "revises": 7,
                                 "question": 10, "unsupported": 5})

    def test_missing_and_extra_ids(self):
        replies = {k: v for k, v in self.replies.items() if k != "e05"} | {"e99": {"question": "?"}}
        path = self.write("r.jsonl", [{"id": k, "reply": v} for k, v in replies.items()])
        code, out, _ = scored(CASES, path)
        summary = json.loads(out)
        self.assertEqual((code, summary["missing"], summary["extra"], summary["passed"]), (0, ["e05"], ["e99"], 86))

    def test_duplicate_id_in_either_file_exits_2(self):
        dup_cases = self.write("c.jsonl", self.rows[:89] + [self.rows[0]])
        dup_replies = self.write("r.jsonl", [{"_note": "x"}, {"id": "e01", "reply": {}}, {"id": "e01", "reply": {}}])
        self.assertEqual(scored(dup_cases, REPLIES), (2, "", "cases line 90: duplicate id"))
        self.assertEqual(scored(CASES, dup_replies), (2, "", "replies line 3: duplicate id"))

    def test_malformed_line_or_62_cases_exits_2_naming_only_the_line(self):
        broken = self.write("c.jsonl", self.rows[:3] + ['{"id": "e04", "text": "owner words"'] + self.rows[4:])
        self.assertEqual(scored(broken, REPLIES), (2, "", "cases line 4: not valid JSON"))
        self.assertEqual(scored(self.write("c62.jsonl", self.rows[:89]), REPLIES),
                         (2, "", "cases: 89 cases, expected 90"))
        self.assertEqual(scored(CASES, self.tmp / "absent.jsonl"), (2, "", "replies: unreadable"))

    def test_unknown_op_scores_as_question(self):
        unknown = {"ops": [{"op": "product.colour", "args": {"id": "photo-product-001"}}], "revises": None}
        self.assertEqual(self.why("e26", unknown), [])  # must-ask case: the check's question passes
        self.assertEqual(self.why("e03", unknown), ["expected ops, got question"])
        self.assertEqual(self.why("e26", "not an object"), ["expected question, got unsupported"])

    def test_revises_args_and_claim_fields(self):
        def hide(code): return {"ops": [{"op": "product.hide", "args": {"id": "photo-product-098"}}], "revises": code}
        self.assertEqual(self.why("e22", hide(None)), ["revises differs"])
        self.assertEqual(self.why("e22", hide("ffff")), ["expected ops, got question"])  # code not waiting
        self.assertEqual(self.why("e07", hide(None)), ["op 1 product.hide: arg id differs"])
        add = self.replies["e01"]["ops"][0]
        claim = {"ops": [{"op": add["op"], "args": {**add["args"], "producerKey": "Etto"}}], "revises": None}
        self.assertEqual(self.why("e01", claim), ["op 1 product.add: unexpected claim arg producerKey"])

    def test_v2_partial_revise_and_photo_on_existing_product_fail_by_name(self):
        partial = {"ops": [{"op": "hike.create", "args": {"time": "09:30"}}], "revises": "b7c8"}  # pre-AV0022-03 reply
        self.assertEqual(self.why("e35", partial), ["op 1 hike.create: missing arg title"])
        self.assertEqual(self.why("e35", {**self.replies["e35"], "revises": None}), ["revises differs"])
        photo = self.replies["e37"]["ops"][0]["args"]["photo"]
        existing = {"ops": [{"op": "product.set_photo", "args": {"id": "photo-product-001", "photo": photo,
                                                                   "imageAlt": "A crate of Meyer lemons"}}], "revises": None}
        self.assertEqual(self.why("e37", existing), ["ops product.set_photo but expected product.add"])
        self.assertEqual(self.why("e38", self.replies["e37"]), ["ops product.add but expected product.set_photo"])
        for case_id in ("e39", "e40"):  # writing the unconfirmed claim instead of asking fails
            self.assertEqual(self.why(case_id, self.replies["e03"]), ["expected question, got ops"])


class V3HomeAndRouteTests(EvalTestCase):
    """AV1322-14: the v3 cases for the home-page ops and route.add/hide/restore, and their failure paths."""

    def test_every_new_op_has_two_cases_and_all_new_cases_pass_recorded(self):
        ops = Counter(c["op"] for case in self.cases[40:55] for c in case["expect"].get("ops", ()))
        self.assertEqual(ops, {"store.set_headline": 2, "store.set_story": 2, "store.set_home_image": 2,
                               "store.set_notice": 2, "route.add": 2, "route.hide": 2, "route.restore": 2})
        failed = {f["id"] for f in ev.score(self.cases, self.replies, REGISTRY)["failed"]}
        self.assertEqual(failed & {c["id"] for c in self.cases[40:55]}, set())

    def test_route_add_without_a_source_passes_only_when_the_reply_asks(self):
        self.assertEqual(self.cases[50]["expect"], {"question": True})
        self.assertEqual(self.why("e51", self.replies["e51"]), [])
        full = self.replies["e49"]["ops"][0]["args"]
        for args in ({**full, "sourceUrl": "", "sourceName": ""}, {k: v for k, v in full.items() if not k.startswith("source")}):
            added = {"ops": [{"op": "route.add", "args": args}], "revises": None}
            self.assertEqual(self.why("e51", added), ["expected question, got ops"])
        self.assertEqual(self.why("e49", self.replies["e51"]), ["expected ops, got question"])

    def test_wrong_op_or_target_on_the_new_cases_fails_by_name(self):
        hide = lambda rid: {"ops": [{"op": "route.hide", "args": {"id": rid}}], "revises": None}  # noqa: E731
        self.assertEqual(self.why("e54", hide("idea-cass-hill")), ["ops route.hide but expected route.restore"])
        self.assertEqual(self.why("e53", hide("idea-cass-hill")), ["op 1 route.hide: arg id differs"])
        notice = self.replies["e47"]["ops"][0]["args"]
        late = {"ops": [{"op": "store.set_notice", "args": {**notice, "until": "2026-11-27"}}], "revises": None}
        self.assertEqual(self.why("e47", late), ["op 1 store.set_notice: arg until differs"])
        self.assertEqual(self.why("e42", self.replies["e41"]), ["op 1 store.set_headline: arg first differs"])


class LiveTests(EvalTestCase):
    def fake(self, calls):
        def transport(url, body, headers, timeout):
            calls.append(url)
            return 200, json.dumps({"done": True, "message": {"content": '{"question": "Which one?"}'}}).encode()
        return transport

    def test_out_inside_repo_existing_or_bad_url_refused_before_any_request(self):
        calls, existing, link = [], self.write("exists.jsonl", ["{}"]), self.tmp / "link.jsonl"
        os.symlink(self.tmp / "nowhere", link)
        for out, url in ((ev.REPO / "replies.jsonl", URL), (existing, URL), (link, URL),
                         (self.tmp / "new.jsonl", "http://example.com")):
            code, stdout, _ = run("--live", "--url", url, "--model", "m", "--out", out, transport=self.fake(calls))
            self.assertEqual((code, stdout), (2, ""), out)
        self.assertEqual((calls, existing.read_text("utf-8")), ([], "{}\n"))
        self.assertFalse((ev.REPO / "replies.jsonl").exists() or (self.tmp / "new.jsonl").exists())

    def test_live_records_one_reply_per_case_that_score_reads(self):
        calls, out = [], self.tmp / "fresh.jsonl"
        code, stdout, _ = run("--live", "--url", URL, "--model", "m", "--out", out, transport=self.fake(calls))
        self.assertEqual((code, json.loads(stdout), len(calls)), (0, {"failedCalls": 0, "recorded": 90}, 90))
        replies = ev.load_replies(out)
        self.assertEqual(list(replies), [c["id"] for c in self.cases])
        self.assertEqual(ev.score(self.cases, replies, REGISTRY)["passed"], 10)  # only the 10 must-ask cases pass

    def test_fixture_hikes_survive_the_prompt_caps_when_the_content_is_full(self):
        real = [{"id": f"hike-{n:02d}", "title": "t", "startsAt": f"2026-0{1 + n % 9}-01T08:00:00-08:00", "status": "scheduled",
                 "bring": f"real bring {n}", "accessNote": "a", "meetingPoint": "m", "capacity": 5} for n in range(15)]
        real += [{"id": f"old-{n:02d}", "title": "t", "startsAt": f"2025-01-{1 + n % 28:02d}T08:00:00-08:00", "status": "cancelled"}
                 for n in range(80)]
        content = dataclasses.replace(load_content(), community={"events": real, "routeIdeas": []})
        bodies = []

        def transport(url, body, headers, timeout):
            bodies.append(body)
            return 200, json.dumps({"done": True, "message": {"content": '{"question": "Which one?"}'}}).encode()
        out = self.tmp / "full.jsonl"
        ev.live(self.cases[:1], URL, "m", out, transport=transport, content=content)
        prompt = json.loads(bodies[0])["messages"][0]["content"]
        for hike in json.loads(ev.EVENTS.read_text("utf-8")):
            self.assertIn(hike["id"], prompt.split("Scheduled hike details (id")[-1])
            self.assertIn(hike["bring"], prompt)
            self.assertIn(hike["accessNote"], prompt)


if __name__ == "__main__":
    unittest.main()
