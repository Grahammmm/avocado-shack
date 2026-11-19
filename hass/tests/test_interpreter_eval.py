"""NB-AV-04 tests: the interpreter eval set and offline scorer. No model, no socket: --live uses a fake transport."""

import contextlib, dataclasses, io, json, os, tempfile, unittest  # noqa: E401
from collections import Counter
from pathlib import Path

from hass import interpret_check, interpreter_eval as ev
from hass.content_model import CATEGORIES, load_content
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
                         (0, "", {"cases": 104, "passed": 101, "missing": [], "extra": []}))
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
        self.assertEqual(kinds, {"product": 25, "maker": 9, "club": 1, "hike": 16, "store": 16, "route": 8, "revises": 7,
                                 "question": 11, "unsupported": 7, "lookup": 4})

    def test_missing_and_extra_ids(self):
        replies = {k: v for k, v in self.replies.items() if k != "e05"} | {"e999": {"question": "?"}}
        path = self.write("r.jsonl", [{"id": k, "reply": v} for k, v in replies.items()])
        code, out, _ = scored(CASES, path)
        summary = json.loads(out)
        self.assertEqual((code, summary["missing"], summary["extra"], summary["passed"]), (0, ["e05"], ["e999"], 100))

    def test_duplicate_id_in_either_file_exits_2(self):
        dup_cases = self.write("c.jsonl", self.rows[:103] + [self.rows[0]])
        dup_replies = self.write("r.jsonl", [{"_note": "x"}, {"id": "e01", "reply": {}}, {"id": "e01", "reply": {}}])
        self.assertEqual(scored(dup_cases, REPLIES), (2, "", "cases line 104: duplicate id"))
        self.assertEqual(scored(CASES, dup_replies), (2, "", "replies line 3: duplicate id"))

    def test_malformed_line_or_62_cases_exits_2_naming_only_the_line(self):
        broken = self.write("c.jsonl", self.rows[:3] + ['{"id": "e04", "text": "owner words"'] + self.rows[4:])
        self.assertEqual(scored(broken, REPLIES), (2, "", "cases line 4: not valid JSON"))
        self.assertEqual(scored(self.write("c62.jsonl", self.rows[:103]), REPLIES),
                         (2, "", "cases: 103 cases, expected 104"))
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
        self.assertEqual((code, json.loads(stdout), len(calls)), (0, {"failedCalls": 0, "recorded": 104}, 104))
        replies = ev.load_replies(out)
        self.assertEqual(list(replies), [c["id"] for c in self.cases])
        self.assertEqual(ev.score(self.cases, replies, REGISTRY)["passed"], 11)  # only the 11 must-ask cases pass

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


class V10NoPriceShelfMakerTests(EvalTestCase):
    """AV0222-13: v10 adds a price-only message, a price beside a sold-out change, an unknown shelf and a maker with no story."""

    NEW, AVO = ["e91", "e92", "e93", "e94"], "photo-product-001"

    def ops(self, op, **args): return {"ops": [{"op": op, "args": args}], "revises": None}

    def test_v10_exact_four_cases_and_raw_replies(self):
        new = self.cases[90:94]
        self.assertEqual(([c["id"] for c in new], len({c["id"] for c in self.cases})), (self.NEW, 104))
        self.assertTrue(all(c["pending"] == [] and set(c) == {"id", "text", "pending", "expect"} for c in new))
        self.assertEqual([c["text"] for c in new], ["Set the avocados to 2 for $3.", "The avocados are sold out. They were 2 for $3.",
                         "Move the avocados to the snacks shelf.", "Add a maker named Fixture Grove in Los Osos."])
        self.assertEqual([c["expect"] for c in new][::2][0], {"unsupported": True})
        self.assertEqual(new[2]["expect"], {"question": True})
        sold = {"ops": [{"op": "product.set_availability", "args": {"id": self.AVO, "available": "no"}}], "revises": None}
        maker = {"ops": [{"op": "maker.add", "args": {"key": "Fixture Grove", "name": "Fixture Grove", "place": "Los Osos"}}], "revises": None}
        self.assertTrue(new[1]["expect"] == sold and self.replies["e92"] == sold)
        self.assertTrue(new[3]["expect"] == maker and self.replies["e94"] == maker)
        self.assertEqual((list(self.replies["e91"]), list(self.replies["e93"])), (["unsupported"], ["question"]))
        self.assertEqual(self.replies["e91"]["unsupported"], interpret_check.PRICE_REPLY)
        self.assertEqual(self.replies["e93"]["question"], "There is no snacks shelf. Which shelf: Fruit, Vegetables, "
                         "Dairy & cheese, Eggs, Meat, Pantry, Drinks & coffee, Bread, Flowers or General?")
        self.assertNotIn("$", json.dumps(self.replies["e92"]))
        for key in ("story", "url", "organic", "producerKey", "clearStory"):
            self.assertNotIn(key, self.replies["e94"]["ops"][0]["args"])
        failed = {f["id"] for f in ev.score(self.cases, self.replies, REGISTRY)["failed"]}
        self.assertEqual(failed & set(self.NEW), set())
        self.assertEqual(self.rows[:90], CASES.read_text("utf-8").splitlines()[:90])

    def test_v10_price_only_and_mixed_availability(self):
        self.assertEqual(self.why("e91", self.replies["e91"]), [])
        self.assertEqual(self.why("e91", self.ops("product.set_availability", id=self.AVO, available="no")),
                         ["expected unsupported, got ops"])
        good = self.replies["e92"]
        self.assertEqual(self.why("e92", self.ops("product.set_availability", id="photo-product-081", available="no")),
                         ["op 1 product.set_availability: arg id differs"])
        self.assertEqual(self.why("e92", self.ops("product.set_availability", id=self.AVO, available="limited")),
                         ["op 1 product.set_availability: arg available differs"])
        self.assertEqual(self.why("e92", self.ops("product.set_availability", available="no")),
                         ["op 1 product.set_availability: missing arg id"])
        self.assertEqual(self.why("e92", dict(good, revises="v1")), ["expected ops, got question"])
        extra = {"ops": good["ops"] + [{"op": "product.hide", "args": {"id": self.AVO}}], "revises": None}
        self.assertEqual(self.why("e92", extra), ["ops product.set_availability,product.hide but expected product.set_availability"])
        priced = self.ops("product.edit", id=self.AVO, description="2 for $3")  # the dependency's checker turns a dollar into a question
        self.assertEqual(self.why("e92", priced), ["expected ops, got question"])

    def test_v10_unknown_shelf_question(self):
        self.assertEqual(self.why("e93", self.replies["e93"]), [])
        self.assertEqual(self.why("e93", self.ops("product.hide", id=self.AVO)), ["expected question, got ops"])
        self.assertEqual(self.why("e93", {"unsupported": "No."}), ["expected question, got unsupported"])
        # the existing checker turns an invalid shelf op into its own shelf question, so scoring passes it (documented, not a new policy)
        self.assertEqual(self.why("e93", self.ops("product.edit", id=self.AVO, category="snacks")), [])

    def test_v10_maker_without_story(self):
        args = {"key": "Fixture Grove", "name": "Fixture Grove", "place": "Los Osos"}
        self.assertEqual(self.why("e94", self.ops("maker.add", **args)), [])
        for field, other in (("name", "Fixture Glen"), ("place", "Morro Bay"), ("key", "Fixture Glen")):
            self.assertEqual(self.why("e94", self.ops("maker.add", **dict(args, **{field: other}))),
                             [f"op 1 maker.add: arg {field} differs"])
        self.assertEqual(self.why("e94", self.ops("maker.add", **{k: v for k, v in args.items() if k != "place"})),
                         ["op 1 maker.add: missing arg place"])
        self.assertEqual(self.why("e94", self.ops("maker.edit", **args)), ["ops maker.edit but expected maker.add"])
        self.assertEqual(self.why("e94", dict(self.replies["e94"], revises="v1")), ["expected ops, got question"])

    def test_v10_predecessor_outcomes(self):
        old = ev.score(self.cases[:90], self.replies, REGISTRY)
        new = ev.score(self.cases, self.replies, REGISTRY)
        self.assertEqual((old["passed"], new["passed"], old["failed"] == new["failed"]), (87, 101, True))
        self.assertEqual([f["id"] for f in new["failed"]], ["e06", "e13", "e25"])
        self.assertEqual(old["extra"], sorted(self.NEW + [f"e{n}" for n in range(95, 105)]))  # the scorer sorts ids as strings: e100 before e85


class V11BulkAndLayoutTests(EvalTestCase):
    """AV1052-16: whole shelf, whole maker, a product beside a shelf word and the fixed design reply. Synthetic replies."""

    NEW = ["e95", "e96", "e97", "e98"]
    DESIGN = "design changes cannot be made by message yet"

    def ops(self, op, **args): return {"ops": [{"op": op, "args": args}], "revises": None}

    def expect(self, case_id): return next(c for c in self.cases if c["id"] == case_id)["expect"]

    def test_v11_exact_append_and_raw_contracts(self):
        from hass.interpreter_prompt import DESIGN_UNSUPPORTED
        self.assertEqual([c["id"] for c in self.cases[94:98]], self.NEW)
        self.assertEqual([c["text"] for c in self.cases[94:98]], ["All the vegetables are in today", "Everything from Cal Poly is sold out",
                         "The Hass avocado on the Fruit shelf is sold out", "Make the product cards round"])
        self.assertTrue(all(c["pending"] == [] and set(c) == {"id", "text", "pending", "expect"} for c in self.cases[94:98]))
        want = {"e95": self.ops("product.set_availability_all", available="yes", shelf="vegetables"),
                "e96": self.ops("product.set_availability_all", available="no", maker="Cal Poly"),
                "e97": self.ops("product.set_availability", id="photo-product-001", available="no"),
                "e98": {"unsupported": self.DESIGN}}
        self.assertEqual({k: self.replies[k] for k in self.NEW}, want)
        self.assertEqual([self.expect(k) for k in self.NEW[:3]], [want[k] for k in self.NEW[:3]])
        self.assertEqual(self.expect("e98"), {"unsupported": True})
        self.assertEqual((DESIGN_UNSUPPORTED, self.replies["e98"]["unsupported"]), (self.DESIGN, self.DESIGN))
        content = load_content()
        self.assertIn("vegetables", CATEGORIES)
        self.assertIn("Cal Poly", {p.get("producerKey") for p in content.active_products()})
        self.assertEqual(next(p for p in content.active_products() if p["id"] == "photo-product-001")["category"], "fruit")
        self.assertEqual(ev.score(self.cases[94:98], self.replies, REGISTRY)["passed"], 4)

    def test_v11_bulk_is_one_operation_not_record_expansion(self):
        shelf = self.expect("e95")["ops"][0]
        for reply in (self.ops("product.set_availability_all", available="yes", shelf="fruit"),
                      self.ops("product.set_availability_all", available="no", shelf="vegetables"),
                      self.ops("product.set_availability_all", available="yes"),
                      self.ops("product.set_availability", id="photo-product-001", available="yes"),
                      self.ops("product.set_availability_all", available="yes", maker="Cal Poly")):
            self.assertNotEqual(self.why("e95", reply), [], reply)
        self.assertEqual(self.why("e95", self.ops(shelf["op"], **shelf["args"])), [])
        two = {"ops": 2 * self.replies["e95"]["ops"], "revises": None}
        many = {"ops": [{"op": "product.set_availability", "args": {"id": "photo-product-001", "available": "yes"}}] * 52, "revises": None}
        self.assertNotEqual(self.why("e95", two), [])
        self.assertNotEqual(self.why("e95", many), [])
        for reply in (self.ops("product.set_availability_all", available="no", maker="Cal Poly Pomona"),
                      self.ops("product.set_availability_all", available="yes", maker="Cal Poly"),
                      self.ops("product.set_availability_all", available="no", shelf="eggs"),
                      self.ops("product.set_availability", id="photo-product-001", available="no")):
            self.assertNotEqual(self.why("e96", reply), [], reply)

    def test_v11_product_word_beats_nearby_shelf_word(self):
        self.assertEqual(self.why("e97", self.replies["e97"]), [])
        for reply in (self.ops("product.set_availability_all", available="no", shelf="fruit"),
                      self.ops("product.set_availability", id="photo-product-002", available="no"),
                      self.ops("product.set_availability", id="photo-product-001", available="yes"),
                      dict(self.replies["e97"], revises="c3d4")):
            self.assertNotEqual(self.why("e97", reply), [], reply)

    def test_v11_design_raw_reply_not_conversation_acknowledgement(self):
        self.assertEqual(self.why("e98", self.replies["e98"]), [])
        other = {"unsupported": "I cannot restyle the site."}
        self.assertEqual(self.why("e98", other), [])  # the scorer reads the kind only; the raw contract above pins the wording
        self.assertNotEqual(other, self.replies["e98"])
        self.assertNotEqual(self.why("e98", self.ops("product.set_availability_all", available="no", shelf="fruit")), [])

    def test_v11_predecessor_failures_and_private_output_unchanged(self):
        summary = ev.score(self.cases, self.replies, REGISTRY)
        self.assertEqual(([f["id"] for f in summary["failed"]], summary["passed"], summary["missing"], summary["extra"]),
                         (["e06", "e13", "e25"], 101, [], []))
        self.assertNotIn("Cal Poly", json.dumps(summary))


class V12LookupVersusChangeTests(EvalTestCase):
    """AV1104-12: four questions that get a lookup and two changes phrased as questions. Synthetic replies, no model."""

    NEW = [f"e{n}" for n in range(99, 105)]
    HIKE = "hike-2026-11-14-point-buchon"  # the synthetic eval-events reference, not a real event
    PREFIX = {"cases": "a5425a8339bb4b5912380daa707473e853ad23968d94b32a1eb0011c7e2e9b99",  # sha256 of the 98 v11 lines
              "replies": "3f14513706e17468619db6eab21aef21b06da195acf247c81f231ca5d0d56e92"}
    WANT = [("how many are coming Saturday?", {"lookup": "status"}),
            ("is the sourdough sold out? I mean photo-product-015.", {"lookup": "listing photo-product-015"}),
            ("what's on the dairy shelf?", {"lookup": "shelf dairy"}),
            ("what are my hours?", {"lookup": "listing store"}),
            ("can you mark the eggs sold out?", {"ops": [{"op": "product.set_availability", "args": {"id": "photo-product-024", "available": "no"}}], "revises": None}),
            ("could you move the hike to 10am? I mean " + HIKE + ".", {"ops": [{"op": "hike.update", "args": {"id": HIKE, "time": "10:00"}}], "revises": None})]

    def ops(self, op, **args): return {"ops": [{"op": op, "args": args}], "revises": None}

    def test_v12_exact_append_and_six_raw_contracts(self):  # bug: a drifted text/target, an edited v11 row or a raw reply that differs from its expectation
        import hashlib
        new = self.cases[98:]
        self.assertEqual([c["id"] for c in new], self.NEW)
        self.assertEqual([(c["text"], c["expect"]) for c in new], self.WANT)
        self.assertTrue(all(c["pending"] == [] and set(c) == {"id", "text", "pending", "expect"} for c in new))
        self.assertTrue(all(self.replies[c["id"]] == c["expect"] for c in new), "raw replies equal expectations")
        self.assertEqual([list(self.replies[i]) for i in self.NEW], [["lookup"]] * 4 + [["ops", "revises"]] * 2)
        self.assertEqual(len({c["id"] for c in self.cases}), 104)
        lines = {"cases": CASES.read_text("utf-8").splitlines(True), "replies": REPLIES.read_text("utf-8").splitlines(True)}
        got = {k: hashlib.sha256("".join(v[:99 if k == "replies" else 98]).encode()).hexdigest() for k, v in lines.items()}
        self.assertEqual(got, self.PREFIX)  # the 98 inherited case lines and the note line + 98 replies are byte-identical
        self.assertEqual(ev.score(new, self.replies, REGISTRY)["passed"], 6)

    def test_v12_lookup_commands_are_distinct(self):  # bug: status/listing/shelf swapped, or a refused/blank lookup, a question or an op list satisfies a lookup
        for case_id, want in zip(self.NEW[:4], ("status", "listing photo-product-015", "shelf dairy", "listing store")):
            self.assertEqual(self.why(case_id, {"lookup": want}), [])
            for bad in ({"lookup": "status"}, {"lookup": "listing store"}, {"lookup": "shelf dairy"}, {"lookup": "listing photo-product-015"}, {"lookup": "shelf eggs"}):
                if bad["lookup"] != want: self.assertEqual(self.why(case_id, bad), ["lookup differs"], (case_id, bad))
            for bad in ({"lookup": ""}, {"lookup": "yes"}, {"lookup": "listing"}, {"lookup": "status; hide"}):
                self.assertEqual(self.why(case_id, bad), ["expected lookup, got unsupported"], (case_id, bad))
            self.assertEqual(self.why(case_id, {"question": "Which?"}), ["expected lookup, got question"])
            self.assertEqual(self.why(case_id, self.ops("product.hide", id="photo-product-081")), ["expected lookup, got ops"])
            self.assertEqual(self.why(case_id, {"unsupported": "No."}), ["expected lookup, got unsupported"])
            self.assertEqual(self.why(case_id, {"lookup": want, "ops": []}), ["expected lookup, got unsupported"])  # mixed shapes are not a lookup
        self.assertEqual(self.why("e102", {"lookup": "listing dairy"}), ["lookup differs"])  # a category is a shelf, not a listing

    def test_v12_question_form_changes_keep_typed_ops(self):  # bug: a polite question is answered as a lookup/question, or the op/target/time drifts
        for case_id, op, args in (("e103", "product.set_availability", {"id": "photo-product-024", "available": "no"}),
                                  ("e104", "hike.update", {"id": self.HIKE, "time": "10:00"})):
            good = self.ops(op, **args)
            self.assertEqual(self.why(case_id, good), [])
            for key, wrong in (("id", "photo-product-002" if case_id == "e103" else "hike-2026-11-22-cass-hill"),
                               ("available" if case_id == "e103" else "time", "yes" if case_id == "e103" else "22:00")):
                self.assertEqual(self.why(case_id, self.ops(op, **dict(args, **{key: wrong}))), [f"op 1 {op}: arg {key} differs"])
            self.assertEqual(self.why(case_id, self.ops(op, **{k: v for k, v in args.items() if k != "id"})), [f"op 1 {op}: missing arg id"])
            for other in ({"lookup": "status"}, {"question": "Which?"}, {"unsupported": "No."}):
                self.assertNotEqual(self.why(case_id, other), [])
            self.assertEqual(self.why(case_id, dict(good, revises="v1")), ["expected ops, got question"])
            self.assertEqual(self.why(case_id, {"ops": good["ops"] + [{"op": "product.hide", "args": {"id": "photo-product-024"}}], "revises": None})[0][:4], "ops ")
        self.assertEqual(self.why("e104", self.ops("hike.update", id=self.HIKE, time="10")), ["op 1 hike.update: arg time differs"])  # "10am" is HH:MM, not a bare hour

    def test_v12_real_catalog_targets_and_lookup_gate(self):  # bug: an id/name that no longer matches the catalog, or a lookup the real checker would refuse
        content = load_content()
        active = {p["id"]: p for p in content.active_products()}
        self.assertEqual((active["photo-product-024"]["name"], active["photo-product-024"]["category"]), ("Cal Poly eggs", "eggs"))
        self.assertEqual((active["photo-product-015"]["name"], active["photo-product-015"]["category"]), ("Brian's sourdough bread", "bread"))
        self.assertIn("dairy", CATEGORIES)
        self.assertNotIn(self.HIKE, {e["id"] for e in content.community["events"]})  # synthetic: not a real event
        for case in self.cases[98:]:  # the real checked/allowlist path returns each expectation unchanged
            self.assertIs(interpret_check.check(case["expect"], REGISTRY, set()), case["expect"], case["id"])

    def test_v12_lookup_mismatch_does_not_echo_canaries(self):  # bug: a wrong lookup command or reply body is echoed into the score reasons or CLI summary
        canary = "CANARY-zq7"
        wrong = {"e99": {"lookup": f"status {canary}"}, "e100": {"lookup": f"listing {canary}"}, "e101": {"lookup": f"shelf {canary}"},
                 "e102": {"lookup": f"yes {canary}"}, "e103": {"question": canary}, "e104": {"unsupported": canary}}
        rows = [{"id": k, "reply": wrong.get(k, v)} for k, v in self.replies.items()]
        code, out, err = scored(CASES, self.write("r.jsonl", rows))
        summary = json.loads(out)
        self.assertEqual((code, err, set(summary), summary["passed"]), (0, "", {"cases", "extra", "failed", "missing", "passed"}, 95))
        self.assertEqual(sorted(f["id"] for f in summary["failed"]), sorted(["e06", "e13", "e25", *wrong]))
        why = {f["id"]: f["why"] for f in summary["failed"]}
        self.assertEqual([why[k] for k in wrong], ["expected lookup, got unsupported"] + ["lookup differs"] * 2 + ["expected lookup, got unsupported", "expected ops, got question", "expected ops, got unsupported"])
        self.assertNotIn(canary, out + err)
        self.assertNotIn("how many are coming", out)

    def test_v12_inherited_outcomes_and_counts(self):  # bug: the new rows change an inherited verdict, or a fake always-question reply passes a lookup/change
        old, new = ev.score(self.cases[:98], self.replies, REGISTRY), ev.score(self.cases, self.replies, REGISTRY)
        self.assertEqual((old["passed"], new["passed"], old["failed"] == new["failed"]), (95, 101, True))
        self.assertEqual(([f["id"] for f in new["failed"]], new["missing"], new["extra"]), (["e06", "e13", "e25"], [], []))
        fake = {c["id"]: {"question": "Which one?"} for c in self.cases}
        self.assertEqual(ev.score(self.cases, fake, REGISTRY)["passed"], 11)  # only the inherited must-ask cases pass


class LookupKindTests(EvalTestCase):
    """AV1104-06: {"lookup": "<command>"} is a fourth, distinct kind: no tracked case changes, only the shape plumbing."""

    def case(self, expect):
        return {"id": "l01", "text": "how many are coming Saturday?", "pending": [], "expect": expect}

    def verdict(self, expect, reply):
        return [f["why"] for f in ev.score([self.case(expect)], {"l01": reply}, REGISTRY)["failed"]]

    def test_lookup_scores_as_its_own_kind_in_both_directions(self):  # bug: lookup folds into "unsupported", so a refused lookup passes an unsupported case
        self.assertEqual(self.verdict({"lookup": "status"}, {"lookup": "status"}), [])
        self.assertEqual(self.verdict({"lookup": "status"}, {"lookup": "Status."}), ["lookup differs"])  # the exact command, not its meaning
        self.assertEqual(self.verdict({"lookup": "status"}, {"lookup": "yes"}), ["expected lookup, got unsupported"])  # refused by interpret_check
        self.assertEqual(self.verdict({"lookup": "status"}, {"lookup": 5}), ["expected lookup, got unsupported"])  # unreadable shape
        self.assertEqual(self.verdict({"lookup": "status"}, {"question": "Which?"}), ["expected lookup, got question"])
        self.assertEqual(self.verdict({"lookup": "status"}, {"ops": [], "revises": None}), ["expected lookup, got question"])  # no change found: a question
        self.assertEqual(self.verdict({"unsupported": True}, {"lookup": "status"}), ["expected unsupported, got lookup"])
        self.assertEqual(self.verdict({"question": True}, {"lookup": "status"}), ["expected question, got lookup"])
        ops = {"ops": [{"op": "product.hide", "args": {"id": "photo-product-081"}}], "revises": None}
        self.assertEqual(self.verdict(ops, {"lookup": "status"}), ["expected ops, got lookup"])
        self.assertEqual(self.verdict({"lookup": "status"}, ops), ["expected lookup, got ops"])

    def test_lookup_expectations_load_and_bad_ones_are_refused_without_text(self):  # bug: a malformed expectation loads, or its text is echoed
        good = self.write("good.jsonl", [*self.rows[:103], json.dumps(self.case({"lookup": "find eggs"}))])
        self.assertEqual(ev.load_cases(good)[-1]["expect"], {"lookup": "find eggs"})
        for bad in ({"lookup": 5}, {"lookup": ""}, {"lookup": "status", "extra": "canary-zz"}, {"lookup": ["status"]}):
            path = self.write("bad.jsonl", [*self.rows[:103], json.dumps(self.case(bad))])
            code, _out, err = scored(path, REPLIES)
            self.assertEqual((code, err), (2, "cases line 104: not a case"), bad)
        self.assertEqual(scored(CASES, REPLIES)[0], 0)  # the tracked set is untouched: still 104 cases, 101 passing


if __name__ == "__main__":
    unittest.main()
