"""HASS-NL-1 tests: the natural-language corpus and its scorer. No model, no socket: --live uses a fake transport."""

import contextlib, io, json, os, tempfile, unittest  # noqa: E401
from collections import Counter
from pathlib import Path

from hass import nl_eval as nl
from hass.ops import load_registry

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CORPUS = FIXTURES / "nl-corpus.jsonl"
REGISTRY, URL = load_registry(), "http://127.0.0.1:11434"
FREE_TEXT = {"product.edit": "description", "hike.cancel": "note", "hike.recap": "recap", "store.set_notice": "text", "hike.update": "bring",
             "maker.edit": "place", "hike.create": "title", "product.add": "name"}


def run(*argv, transport=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = nl.main([str(a) for a in argv], transport=transport)
    return code, out.getvalue(), err.getvalue().removeprefix("nl_eval: ").strip()


def ideal(case):
    """A reply that fully satisfies the case: its expected outcome, with any required words written into a free-text arg."""
    expect, words = case["expect"], " ".join(case.get("mustContain", []))
    if "ops" in expect:
        calls = json.loads(json.dumps(expect["ops"]))
        if words and words.lower() not in json.dumps(calls).lower():
            first = calls[0]
            name = FREE_TEXT.get(first["op"])
            if first["op"] == "store.set_hours": first["args"]["hours"] = [words]
            elif name: first["args"][name] = words
        return {"ops": calls, "revises": expect["revises"]}
    return {"question": f"Which one? {words}"} if "question" in expect else {"unsupported": f"That is not a change I can make. {words}"}


def rows(corpus, make=ideal):
    return {c["id"]: {"reply": make(c), "failed": None, "ms": 1000} for c in corpus}


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = nl.load_corpus(CORPUS)

    def test_size_and_mix(self):
        c = self.corpus
        self.assertGreaterEqual(len(c), 200)
        self.assertEqual(len({x["text"] + json.dumps(x["pending"]) + json.dumps(x.get("recent")) for x in c}), len(c))  # no repeated case
        self.assertGreaterEqual(sum(x["ask"] for x in c), 40)
        self.assertGreaterEqual(sum(x["refuse"] for x in c), 40)
        self.assertGreaterEqual(sum("ops" in x["expect"] for x in c), 100)
        self.assertEqual(set(Counter(x["intent"] for x in c)), nl.INTENTS)  # every kind of message is covered

    def test_multi_turn_cases(self):
        c = self.corpus
        self.assertGreaterEqual(sum(bool(x["pending"]) for x in c), 30)
        self.assertGreaterEqual(sum(bool(x.get("recent")) for x in c), 10)
        self.assertGreaterEqual(sum(len(x["pending"]) >= 2 for x in c), 5)  # two drafts waiting
        self.assertTrue(any(x["pending"] and x["pending"][0]["state"] == "needs-details" for x in c))  # a waiting question and its answer
        self.assertTrue(any(x["expect"].get("revises") for x in c if "ops" in x["expect"]))  # a correction

    def test_the_voices_the_owner_task_asks_for(self):
        tags = Counter(t for x in self.corpus for t in x.get("tags", []))
        for tag in ("typo", "slang", "voice-to-text", "fragment", "multi", "price", "same-as-last-time", "photo-caption", "farm-stand",
                    "shelf", "correction", "ambiguous", "claim", "date", "alias", "two-drafts", "selection-check"):
            self.assertGreater(tags[tag], 0, tag)
        text = " ".join(x["text"].lower() for x in self.corpus)
        for phrase in ("actually make that $9", "same as last time", "undo that", "did it go up?", "cancel the point buchon hike"):
            self.assertIn(phrase, text)

    def test_expected_ops_are_real_registry_ops(self):
        for case in self.corpus:
            for expect in (case["expect"], *case.get("also", [])):
                for call in expect.get("ops", ()):
                    spec = REGISTRY[call["op"]]
                    self.assertTrue(set(call["args"]) <= set(spec.args), (case["id"], call["op"]))

    def test_a_perfect_run_passes_everything(self):
        summary = nl.score(self.corpus, rows(self.corpus), REGISTRY)
        self.assertEqual((summary["failed"], summary["wrongDrafts"], summary["strictAccuracy"], summary["intentAccuracy"]), ([], 0, 1.0, 1.0))
        self.assertEqual((summary["questionWhenUnsureRate"], summary["refusalRate"], summary["jsonValidRate"]), (1.0, 1.0, 1.0))

    def test_every_accepted_alternative_also_passes(self):
        for case in self.corpus:
            for alt in case.get("also", []):
                words = " ".join(case.get("mustContain", []))
                reply = ({"ops": alt["ops"], "revises": alt["revises"]} if "ops" in alt else {"question": f"Which? {words}"} if "question" in alt
                         else {"unsupported": f"No. {words}"})
                if "ops" in alt and words: continue  # free text cannot be invented for an alternative draft
                self.assertEqual(nl.judge(case, {"reply": reply, "failed": None, "ms": 1}, REGISTRY)["verdict"], "pass", case["id"])

    def test_corpus_is_synthetic_and_clean(self):
        import re
        blob = CORPUS.read_text("utf-8")
        self.assertEqual(sorted(set(re.findall(r"https?://[^\s\"]+", blob))), ["https://ettopasta.example", "https://freshroots.example"])
        self.assertEqual([m for m in re.findall(r"\b\d{3}[ -]\d{3}[ -]\d{4}\b", blob) if m[4:7] != "555"], [])  # only 555 test numbers
        self.assertNotIn("@", blob)

    def test_dates_match_the_fixed_sent_day(self):
        self.assertEqual(nl.SENT_AT.strftime("%A %Y-%m-%d"), "Monday 2026-11-09")


class ScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = nl.load_corpus(CORPUS)
        cls.by = {c["id"]: c for c in cls.corpus}

    def first(self, **match):
        return next(c for c in self.corpus if all(c.get(k) == v for k, v in match.items()))

    def verdict(self, case, reply, failed=None):
        return nl.judge(case, {"reply": reply, "failed": failed, "ms": 5}, REGISTRY)

    def test_a_draft_where_a_question_was_right_is_a_wrong_draft(self):
        case = next(c for c in self.corpus if c["text"] == "mark the honey sold out")
        got = self.verdict(case, {"ops": [{"op": "product.set_availability", "args": {"id": "photo-product-041", "available": "no"}}], "revises": None})
        self.assertEqual((got["verdict"], got["kind"]), ("wrong-draft", "ops"))

    def test_the_wrong_product_is_a_wrong_draft_but_the_right_intent(self):
        case = next(c for c in self.corpus if c["text"] == "eggs are out")
        got = self.verdict(case, {"ops": [{"op": "product.set_availability", "args": {"id": "photo-product-017", "available": "no"}}], "revises": None})
        self.assertEqual((got["verdict"], got["intent"], got["why"]), ("wrong-draft", True, "op 1 product.set_availability: arg id differs"))

    def test_asking_or_refusing_a_clear_request_is_over_cautious_not_unsafe(self):
        case = next(c for c in self.corpus if c["text"] == "eggs are out")
        for reply in ({"question": "Which?"}, {"unsupported": "No."}):
            self.assertEqual(self.verdict(case, reply)["verdict"], "over-cautious")

    def test_question_for_refusal_is_a_safe_kind_mismatch(self):
        case = next(c for c in self.corpus if c["text"] == "make the logo bigger")
        self.assertEqual(self.verdict(case, {"question": "Bigger how?"})["verdict"], "kind-mismatch")

    def test_required_words_in_a_refusal(self):
        case = next(c for c in self.corpus if c["text"] == "undo that")
        self.assertEqual(self.verdict(case, {"unsupported": "Send undo to undo the last change."})["verdict"], "pass")
        self.assertEqual(self.verdict(case, {"unsupported": "I cannot do that."})["verdict"], "content-miss")

    def test_op_order_and_availability_list_order_do_not_matter(self):
        case = next(c for c in self.corpus if c["text"].startswith("selection check done, lemons and oranges"))
        args = dict(case["expect"]["ops"][0]["args"])
        args["yes"] = list(reversed(args["yes"]))
        self.assertEqual(self.verdict(case, {"ops": [{"op": "store.confirm_selection", "args": args}], "revises": None})["verdict"], "pass")
        multi = next(c for c in self.corpus if c["text"] == "eggs are out and hide the cantaloupe")
        got = {"ops": list(reversed(multi["expect"]["ops"])), "revises": None}
        self.assertEqual(self.verdict(multi, got)["verdict"], "pass")

    def test_revises_is_part_of_the_intent(self):
        case = next(c for c in self.corpus if c["text"] == "no wait limited not out")
        reply = {"ops": case["expect"]["ops"], "revises": None}
        got = self.verdict(case, reply)
        self.assertEqual((got["verdict"], got["intent"]), ("wrong-draft", False))

    def test_a_failed_call_is_neither_a_pass_nor_a_wrong_draft(self):
        case = next(c for c in self.corpus if c["text"] == "eggs are out")
        got = self.verdict(case, {"unsupported": nl.FAILED}, failed="timeout")
        self.assertEqual((got["verdict"], got["kind"]), ("call-failed", "none"))

    def test_a_bad_op_becomes_a_question_after_the_conversation_check(self):
        case = next(c for c in self.corpus if c["text"] == "eggs are out")
        got = self.verdict(case, {"ops": [{"op": "product.sell", "args": {}}], "revises": None})
        self.assertEqual((got["kind"], got["verdict"]), ("question", "over-cautious"))

    def test_rates_on_a_known_mix(self):
        pick = lambda text: next(c for c in self.corpus if c["text"] == text)  # noqa: E731
        cases = [pick("eggs are out"), pick("hide the figs and show the figs"), pick("make the logo bigger"), pick("hide it")]
        replies = {
            cases[0]["id"]: {"reply": ideal(cases[0]), "failed": None, "ms": 1000},
            cases[1]["id"]: {"reply": {"ops": [{"op": "product.hide", "args": {"id": "photo-product-097"}}], "revises": None}, "failed": None, "ms": 3000},
            cases[2]["id"]: {"reply": {"unsupported": "design changes cannot be made by message yet"}, "failed": None, "ms": 2000},
            cases[3]["id"]: {"reply": {"unsupported": nl.FAILED}, "failed": "timeout", "ms": 120000}}
        s = nl.score(cases, replies, REGISTRY)
        self.assertEqual((s["scored"], s["wrongDrafts"], s["wrongDraftRate"], s["strictAccuracy"]), (4, 1, 0.25, 0.5))
        self.assertEqual((s["questionWhenUnsureRate"], s["refusalRate"], s["draftWhenShouldNotRate"]), (0.0, 1.0, 0.333))
        self.assertEqual((s["jsonValidRate"], s["callsFailed"], s["timeouts"]), (0.75, 1, 1))
        self.assertEqual(s["latencyMs"], {"p50": 2000, "p95": 3000, "max": 3000, "calls": 3})
        self.assertEqual(s["verdicts"]["wrong-draft"], 1)

    def test_missing_replies_are_listed_not_scored(self):
        s = nl.score(self.corpus, {self.corpus[0]["id"]: {"reply": ideal(self.corpus[0]), "failed": None, "ms": 1}}, REGISTRY)
        self.assertEqual((s["scored"], len(s["missing"])), (1, len(self.corpus) - 1))

    def test_percentiles_use_nearest_rank(self):
        self.assertEqual((nl._percentile([1, 2, 3, 4], 50), nl._percentile([1, 2, 3, 4], 95), nl._percentile([], 50)), (2, 4, None))

    def test_compare_reports_regressions_fixes_and_new_wrong_drafts(self):
        cases = self.corpus[:3]
        good = {c["id"]: {"reply": ideal(c), "failed": None, "ms": 1} for c in cases}
        bad = {c["id"]: {"reply": {"ops": [{"op": "product.hide", "args": {"id": "photo-product-097"}}], "revises": None}, "failed": None, "ms": 1} for c in cases}
        out = nl.compare(cases, good, bad, REGISTRY)
        self.assertEqual((len(out["regressed"]), out["fixed"], len(out["newWrongDrafts"])), (3, [], 3))
        back = nl.compare(cases, bad, good, REGISTRY)
        self.assertEqual((back["regressed"], len(back["fixed"]), back["newWrongDrafts"]), ([], 3, []))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.corpus = nl.load_corpus(CORPUS)

    def write_replies(self, name, make=ideal, only=None):
        path = self.tmp / name
        rows_ = [{"id": c["id"], "reply": make(c), "failed": None, "ms": 900} for c in self.corpus if only is None or c["id"] in only]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows_), "utf-8")
        return path

    def test_score_prints_one_json_summary_without_case_text(self):
        path = self.write_replies("r.jsonl", make=lambda c: {"question": "Which one?"})
        code, out, err = run("score", "--replies", path)
        self.assertEqual((code, err), (0, ""))
        summary = json.loads(out)
        self.assertGreater(summary["wrongDrafts"] + summary["verdicts"]["over-cautious"], 0)
        for case in self.corpus: self.assertNotIn(case["text"], out)

    def test_report_is_a_table_with_one_column_per_run(self):
        a, b = self.write_replies("a.jsonl"), self.write_replies("b.jsonl", make=lambda c: {"question": "Which?"})
        code, out, _ = run("report", "--run", f"before={a}", "--run", f"after={b}")
        lines = out.splitlines()
        self.assertEqual((code, lines[0]), (0, "| Measure | before | after |"))
        self.assertTrue(any(l.startswith("| Wrong-draft rate (unsafe) | 0.0% | 0.0% |") for l in lines))
        self.assertTrue(any(l.startswith("| Intent accuracy | 100.0% |") for l in lines))

    def test_compare_exit_codes(self):
        good, bad = self.write_replies("g.jsonl"), self.write_replies("b.jsonl", make=lambda c: {"question": "Which?"})
        self.assertEqual(run("compare", "--before", good, "--after", good)[0], 0)
        code, out, _ = run("compare", "--before", good, "--after", bad)
        self.assertEqual(code, 1)
        self.assertTrue(json.loads(out)["regressed"])

    def test_unreadable_inputs_exit_2_with_a_line_number_not_content(self):
        bad = self.tmp / "bad.jsonl"
        bad.write_text('{"id": "n001", "reply": {}}\nnot json\n', "utf-8")
        code, out, err = run("score", "--replies", bad)
        self.assertEqual((code, out, err), (2, "", "replies line 2: not valid JSON"))
        short = self.tmp / "short.jsonl"
        short.write_text(CORPUS.read_text("utf-8").splitlines()[0] + "\n", "utf-8")
        self.assertEqual(run("score", "--corpus", short, "--replies", bad)[0], 2)

    def test_corpus_validation_names_the_line(self):
        lines = CORPUS.read_text("utf-8").splitlines()
        row = json.loads(lines[0])
        for change, message in (({"intent": "nope"}, "unknown intent"), ({"ask": True}, "ask/refuse disagree with expect"),
                                ({"expect": {"ops": [], "revises": None}}, "bad expect"), ({"text": " "}, "bad text"),
                                ({"mustContain": "x"}, "bad mustContain"), ({"recent": {"question": 1}}, "bad recent"),
                                ({"surprise": 1}, "not a case")):
            path = self.tmp / "c.jsonl"
            path.write_text(json.dumps({**row, **change}) + "\n" + "\n".join(lines[1:]) + "\n", "utf-8")
            with self.assertRaises(nl.EvalError) as ctx: nl.load_corpus(path)
            self.assertEqual(str(ctx.exception), f"corpus line 1: {message}")
        dup = self.tmp / "dup.jsonl"
        dup.write_text("\n".join([lines[0], lines[0]]) + "\n", "utf-8")
        with self.assertRaises(nl.EvalError): nl.load_corpus(dup)

    def corpus_with_also(self, value, at=0, absent=False):
        lines = CORPUS.read_text("utf-8").splitlines()
        row = json.loads(lines[at])
        if absent: row.pop("also", None)
        else: row["also"] = value
        lines[at] = json.dumps(row)
        path = self.tmp / "also.jsonl"
        path.write_text("\n".join(lines) + "\n", "utf-8")
        return path

    def test_also_non_lists_refuse_with_the_line_number_never_type_error(self):
        for value in (None, 7, 1.5, True, False, "", "ab", {}, {"question": "x"}):
            for at in (0, 5):
                path = self.corpus_with_also(value, at)
                with self.assertRaises(nl.EvalError) as ctx: nl.load_corpus(path)
                self.assertEqual(str(ctx.exception), f"corpus line {at + 1}: bad expect")

    def test_also_absent_and_empty_are_equivalent_and_bad_members_still_refuse(self):
        self.assertEqual(nl.load_corpus(self.corpus_with_also(None, absent=True))[0]["expect"], self.corpus[0]["expect"])
        self.assertEqual(nl.load_corpus(self.corpus_with_also([]))[0]["also"], [])
        for value in ([None], [7]):
            with self.assertRaises(nl.EvalError) as ctx: nl.load_corpus(self.corpus_with_also(value))
            self.assertEqual(str(ctx.exception), "corpus line 1: bad expect")

    def test_cli_bad_also_exits_2_before_replies_are_read(self):
        for value in (None, 7, False):
            path = self.corpus_with_also(value)
            code, out, err = run("score", "--corpus", path, "--replies", self.tmp / "missing.jsonl")
            self.assertEqual((code, out, err), (2, "", "corpus line 1: bad expect"))

    def corpus_with_intent(self, value, at=0):
        lines = CORPUS.read_text("utf-8").splitlines()
        lines[at] = json.dumps({**json.loads(lines[at]), "intent": value})
        path = self.tmp / "intent.jsonl"
        path.write_text("\n".join(lines) + "\n", "utf-8")
        return path

    def test_non_string_and_unknown_intents_refuse_with_the_line_number_never_type_error(self):
        canary = "private-canary"
        for value in ([], {}, ["availability"], {canary: 1}, [[canary]], None, True, False, 7, 1.5, "", canary, "Availability", " availability"):
            for at in (0, 5):
                with self.assertRaises(nl.EvalError) as ctx: nl.load_corpus(self.corpus_with_intent(value, at))
                self.assertEqual(str(ctx.exception), f"corpus line {at + 1}: unknown intent")

    def test_cli_container_intent_exits_2_before_replies_are_read(self):
        for value in ([], {}, ["availability"]):
            code, out, err = run("score", "--corpus", self.corpus_with_intent(value), "--replies", self.tmp / "missing.jsonl")
            self.assertEqual((code, out, err), (2, "", "corpus line 1: unknown intent"))

    def test_intent_precedence_and_allowed_values_preserved(self):
        lines = CORPUS.read_text("utf-8").splitlines()
        row = json.loads(lines[0])
        for change, message in (({"intent": [], "text": " "}, "bad text"), ({"intent": [], "pending": 1}, "unknown intent")):
            path = self.tmp / "p.jsonl"
            path.write_text(json.dumps({**row, **change}) + "\n" + "\n".join(lines[1:]) + "\n", "utf-8")
            with self.assertRaises(nl.EvalError) as ctx: nl.load_corpus(path)
            self.assertEqual(str(ctx.exception), f"corpus line 1: {message}")
        for intent in nl.INTENTS: self.assertEqual(nl.load_corpus(self.corpus_with_intent(intent))[0]["intent"], intent)


def fake_model(seen=None):
    """A transport that answers each corpus text with its ideal reply (looked up by the owner text in the request)."""
    by_text = {c["text"]: c for c in nl.load_corpus(CORPUS)}

    def transport(url, body, headers, timeout):
        request = json.loads(body)
        fields = json.loads(request["messages"][1]["content"])
        if seen is not None: seen.append({"fields": fields, "think": request.get("think"), "timeout": timeout})
        case = by_text.get(fields["message"])
        reply = ideal(case) if case else {"question": "warm"}
        return 200, json.dumps({"done": True, "message": {"content": json.dumps(reply)}}).encode()
    return transport


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.corpus = nl.load_corpus(CORPUS)

    def live(self, out, **kw):
        return nl.live(self.corpus[:6], URL, "m", out, baseline=True, **{"transport": fake_model(), **kw})

    def test_live_records_every_case_and_links_the_file_only_when_complete(self):
        out = self.tmp / "run.jsonl"
        ticks = iter(range(0, 10_000, 7))
        self.assertEqual(self.live(out, clock=lambda: next(ticks) / 1000), {"recorded": 6, "failedCalls": 0})
        replies = nl.load_replies(out)
        self.assertEqual(list(replies), [c["id"] for c in self.corpus[:6]])
        self.assertEqual({r["ms"] for r in replies.values()}, {7})
        self.assertFalse(os.path.lexists(str(out) + ".partial"))
        self.assertEqual(oct(out.stat().st_mode & 0o777), "0o600")
        s = nl.score(self.corpus[:6], replies, REGISTRY)
        self.assertEqual((s["strictAccuracy"], s["wrongDrafts"]), (1.0, 0))

    def test_live_sends_the_fixed_day_think_false_and_the_saved_context(self):
        seen, out = [], self.tmp / "run.jsonl"
        cases = [c for c in self.corpus if c.get("aliases")][:1] + [c for c in self.corpus if c.get("recent")][:1]
        nl.live(cases, URL, "m", out, baseline=True, think=False, timeout=77, transport=fake_model(seen), warmup_timeout=0)
        self.assertEqual([s["think"] for s in seen], [False, False])
        self.assertEqual([s["timeout"] for s in seen], [77, 77])
        self.assertEqual(seen[0]["fields"]["today"], "2026-11-09")
        self.assertEqual(seen[0]["fields"]["weekday"], "Monday")
        self.assertIn("aliases", seen[0]["fields"])
        self.assertNotIn("recent", seen[1]["fields"])  # the baseline sends what the service sent before HASS-NL-1

    def test_live_resumes_a_partial_file_without_repeating_cases(self):
        out, seen = self.tmp / "run.jsonl", []
        first = fake_model()

        def stop_after_two(url, body, headers, timeout):
            if len(seen) == 2: raise KeyboardInterrupt
            seen.append(1)
            return first(url, body, headers, timeout)
        with self.assertRaises(KeyboardInterrupt):
            nl.live(self.corpus[:6], URL, "m", out, baseline=True, transport=stop_after_two, warmup_timeout=0)
        self.assertEqual(len(nl.load_replies(str(out) + ".partial")), 2)
        calls = []
        self.assertEqual(nl.live(self.corpus[:6], URL, "m", out, baseline=True, transport=fake_model(calls), warmup_timeout=0)["recorded"], 6)
        self.assertEqual(len(calls), 4)

    def test_a_failed_call_is_recorded_with_its_code(self):
        def down(url, body, headers, timeout): raise TimeoutError
        out = self.tmp / "run.jsonl"
        nl.live(self.corpus[:2], URL, "m", out, baseline=True, transport=down, warmup_timeout=0)
        self.assertEqual({r["failed"] for r in nl.load_replies(out).values()}, {"timeout"})

    def test_out_must_be_outside_the_repo_and_new(self):
        with self.assertRaises(nl.EvalError): self.live(nl.REPO / "x.jsonl")
        existing = self.tmp / "e.jsonl"
        existing.write_text("")
        with self.assertRaises(nl.EvalError): self.live(existing)

    def test_cli_live_prints_a_summary_and_never_case_text(self):
        out = self.tmp / "cli.jsonl"
        code, text, err = run("--live", "--baseline", "--url", URL, "--model", "m", "--out", out, "--limit", "3", "--warmup-timeout", "0",
                              "--think", "false", transport=fake_model())
        self.assertEqual((code, json.loads(text)), (0, {"recorded": 3, "failedCalls": 0}))
        for case in self.corpus[:3]: self.assertNotIn(case["text"], text + err)

    def test_subset(self):
        self.assertEqual(len(nl.subset(self.corpus, every=5)), -(-len(self.corpus) // 5))
        self.assertEqual(len(nl.subset(self.corpus, every=5, limit=3)), 3)

    def test_sample_covers_every_intent_in_corpus_order_and_is_stable(self):
        picked = nl.subset(self.corpus, sample=40)
        self.assertEqual(len(picked), 40)
        self.assertEqual({c["intent"] for c in picked}, nl.INTENTS)
        self.assertEqual([c["id"] for c in picked], [c["id"] for c in nl.subset(self.corpus, sample=40)])
        self.assertEqual([c["id"] for c in picked], sorted(c["id"] for c in picked))
        self.assertEqual(len(nl.subset(self.corpus, sample=10_000)), len(self.corpus))
        self.assertEqual(len(nl.subset(self.corpus, sample=40, limit=5)), 5)

    def test_ids_and_same_as_pick_exactly_those_cases(self):
        self.assertEqual([c["id"] for c in nl.subset(self.corpus, ids={"n003", "n001"})], ["n001", "n003"])
        done = self.tmp / "before.jsonl"
        nl.live(self.corpus[:4], URL, "m", done, baseline=True, transport=fake_model(), warmup_timeout=0)
        out = self.tmp / "after.jsonl"
        code, text, err = run("--live", "--url", URL, "--model", "m", "--out", out, "--same-as", done, "--warmup-timeout", "0", transport=fake_model())
        self.assertEqual((code, json.loads(text)["recorded"]), (0, 4))
        self.assertEqual(list(nl.load_replies(out)), list(nl.load_replies(done)))
        code, _text, err = run("--live", "--url", URL, "--model", "m", "--out", self.tmp / "x.jsonl", "--ids", "n001,zzz", transport=fake_model())
        self.assertEqual(code, 2)

    def test_the_no_op_hours_cases_want_an_it_already_says_that_question(self):
        cases = [c for c in self.corpus if "no-op" in c.get("tags", [])]
        self.assertGreaterEqual(len(cases), 3)
        for case in cases:
            self.assertEqual((case["expect"], case["ask"], case["mustContain"]), ({"question": True}, True, ["already"]))
            draft = {"ops": [{"op": "store.set_hours", "args": {"hours": ["Saturday 9am\u20135pm"]}}], "revises": None}
            row = {"reply": draft, "failed": None, "ms": 1}
            self.assertEqual(nl.judge(case, row, REGISTRY)["verdict"], "wrong-draft")  # drafting a change that changes nothing is the unsafe outcome
            row["reply"] = {"question": "It already says that: Saturday 9am\u20135pm. Did you mean something else?"}
            self.assertEqual(nl.judge(case, row, REGISTRY)["verdict"], "pass")

    def test_retry_timeout_asks_once_more_and_keeps_the_first_attempt(self):
        calls = []
        good = fake_model()

        def slow_then_fine(url, body, headers, timeout):
            calls.append(timeout)
            if len(calls) == 1: raise TimeoutError
            return good(url, body, headers, timeout)
        out = self.tmp / "retry.jsonl"
        nl.live(self.corpus[:1], URL, "m", out, baseline=True, timeout=30, retry_timeout=500, transport=slow_then_fine, warmup_timeout=0)
        [row] = nl.load_replies(out).values()
        self.assertEqual(calls, [30, 500])
        self.assertEqual((row["failed"], row["firstFailed"]), (None, "timeout"))  # answered, but the first try's timeout stays on record
        s = nl.score(self.corpus[:1], {self.corpus[0]["id"]: row}, REGISTRY)
        self.assertEqual(s["firstAttemptTimeouts"], 1)
        calls.clear()
        nl.live(self.corpus[1:2], URL, "m", self.tmp / "off.jsonl", baseline=True, timeout=30, transport=lambda *a: (_ for _ in ()).throw(TimeoutError), warmup_timeout=0)
        self.assertEqual(len(calls), 0)  # without --retry-timeout nothing is asked twice

    def test_live_after_run_sends_hints_and_recent_but_the_baseline_does_not(self):
        seen = []
        case = next(c for c in self.corpus if c.get("recent"))
        for baseline in (True, False):
            nl.live([case], URL, "m", self.tmp / f"run{baseline}.jsonl", baseline=baseline, transport=fake_model(seen), warmup_timeout=0)
        self.assertNotIn("recent", seen[0]["fields"])
        self.assertEqual(seen[1]["fields"]["recent"], case["recent"])
        hinted = next(c for c in self.corpus if c["text"] == "eggs are out")
        nl.live([hinted], URL, "m", self.tmp / "h.jsonl", baseline=False, transport=fake_model(seen), warmup_timeout=0)
        self.assertEqual(seen[-1]["fields"]["hints"]["products"][0]["is"]["id"], "photo-product-024")


if __name__ == "__main__":
    unittest.main()
