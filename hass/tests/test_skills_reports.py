"""AV1109-08 (SKILLS-SPEC 3.30): the read-only skill report.shelf.

Parts: the declaration and the registry lint; the reply against morning_report.facts + render on synthetic content (fresh,
stale, future, missing, duplicate names, hidden and held products, hikes); the count and no-push asks; every recorded case row
replayed through the REAL Dispatcher and Conversation (skills mode both, a scripted skill-reply interpreter, writer content
edited per row); the long report under the strict voice check; command precedence and the once-a-day ask staying with the report
command; nothing written. The kit's own run of the same rows (`hass.tests.test_skills_cases`) only plays their recorded text back.
Run: python3 -B -m unittest hass.tests.test_skills_reports -v
"""
import hashlib
import json
import sys
import types
import unittest
from datetime import date, timedelta
from unittest import mock

from hass import conversation, morning_report, voice
from hass.content_model import REPO_ROOT, Content
from hass.ops import load_registry
from hass.skills import dispatch, load_skills, reports, router, skill_lint, specials
from hass.skills.model import Undo, lint_cases
from hass.skills.testkit import load_rows
from hass.tests import test_skill_dispatch as base
from hass.tests.test_conversation import SETTINGS, ConversationTestCase
from hass.tests.test_editor import git
from hass.tests.test_hike_flow import Clocked, Scripted

CASES = REPO_ROOT / "hass" / "tests" / "fixtures" / "skills" / "reports" / "report.shelf.jsonl"
TODAY = date(2026, 11, 2)  # the Pacific day of the conversation tests' clock (test_conversation.T0)
DAY = TODAY.isoformat()
EGGS, BREAD, AVOCADO, ORANGES = "photo-product-024", "photo-product-015", "photo-product-001", "photo-product-016"
PLAIN = voice.plain
NO_COUNTS = "I don't keep counts; the last check says "
CATALOG = ("morning report", "what's sold out?", "wat is low today", "how are we doing", "what's on the shelves",
           "what's sold out and what hikes are coming up", "anything waiting for me?", "what did I check last",
           "how many eggs do we have", "email me the report every morning")  # SKILLS-SPEC 3.30 sentences 1-10


# -- synthetic content (unit level) ---------------------------------------------------------------------------------
def prod(name, available=None, on=DAY, status="active", pid=None):
    p = {"id": pid or name.lower().replace(" ", "-"), "name": name, "brand": "Shack", "displayBrand": "Shack", "status": status}
    if available is not None:
        p["available"] = available
    if available is not None and on:
        p["available_on"] = on
    return p


def content(products, checked=DAY, events=None):
    store = {"schemaVersion": 1} | ({"selection_checked_on": checked} if checked else {})
    return Content(products=products, makers={}, community={"events": events or []}, store=store)


def ctx(c, *texts, today=TODAY, aliases=None):
    return types.SimpleNamespace(content=c, today=today, texts=list(texts), aliases=aliases or {})


def said(c, *texts, **kw):
    return reports.shelf_reply({}, ctx(c, *texts, **kw))


def engine(c, today=TODAY):
    return morning_report.render(morning_report.facts(c, today))


def hike(title, day, hour=8):
    return {"id": title.lower().replace(" ", "-"), "title": title, "status": "scheduled", "capacity": 12,
            "startsAt": f"{day}T{hour:02d}:00:00-08:00"}


SHELF = [prod("eggs", "limited"), prod("honey", "no"), prod("flour", "yes"), prod("jam")]


class Declaration(unittest.TestCase):
    def test_report_shelf_registered_read_only_and_lints(self):
        registry = load_skills()
        skill = registry.get("report.shelf")
        self.assertIsNotNone(skill)
        self.assertEqual((skill.slots, skill.rules, skill.edits, skill.side_effects, skill.preview, skill.approval, skill.live_class,
                          skill.undo, skill.version), ((), (), (), ("none",), "none", "none", "read-only", Undo("none", "none"), 1))
        self.assertEqual(skill.cases, "hass/tests/fixtures/skills/reports/report.shelf.jsonl")

        class Untouchable:  # the plan reads nothing of the context
            def __getattr__(self, name):
                raise AssertionError(f"plan read ctx.{name}")
        self.assertEqual(skill.plan({}, Untouchable()), [])
        self.assertIs(dispatch.READ_ONLY["report.shelf"], reports.shelf_reply)
        self.assertIn("report.shelf", dispatch.READ_ONLY_LONG)
        self.assertIn("specials.show", dispatch.READ_ONLY_LONG)  # RF0325-11: the complete specials list also runs long
        self.assertNotIn("answer.site", dispatch.READ_ONLY_LONG)  # every other read-only skill keeps the everyday length rule
        self.assertTrue(set(CATALOG) <= {t.text for t in skill.triggers})
        problems = skill_lint(registry, load_registry(), repo_root=REPO_ROOT, golden={"report.shelf": [{}]})
        # The kit's rows have no 'undo' marker (it undoes every draft itself), as for specials.show: the no-op undo is the `turns` row.
        self.assertEqual([p for p in problems if p.startswith("report.shelf:") and "undo row" not in p], [])
        self.assertEqual([p for p in problems if "report.shelf" in p and not p.startswith("report.shelf:")], [])  # no trigger twice

    def test_the_case_file_has_the_rows_the_model_asks_for(self):
        rows = load_rows(CASES)
        self.assertGreaterEqual(len(rows), 10)
        self.assertEqual({r["version"] for r in rows}, {1})
        self.assertGreaterEqual(sum(r["kind"] == "refuse" for r in rows), 2)
        self.assertEqual([p for p in lint_cases(reports.REPORT_SHELF, REPO_ROOT) if "undo row" not in p], [])
        texts = {t for r in rows for t in r["texts"]}
        self.assertTrue((set(CATALOG) - {"morning report"}) <= texts)  # the bare words `morning report` are the command's (below)
        self.assertTrue(any(r["texts"][-1] == "undo" for r in rows))  # the no-op undo


class ShelfReplyIsTheEngine(unittest.TestCase):
    def test_shelf_reply_matches_facts_render(self):
        old, future = (TODAY - timedelta(days=10)).isoformat(), (TODAY + timedelta(days=1)).isoformat()
        for label, checked in (("fresh", DAY), ("stale", old), ("future", future), ("missing", None)):
            c = content([prod(n, w, on=checked) for n, w in (("eggs", "limited"), ("honey", "no"), ("flour", "yes"))], checked=checked)
            with self.subTest(label):
                self.assertEqual(said(c, "what's sold out?"), engine(c))
        self.assertIn("more than a week ago", said(content([prod("eggs", "no", on=old)], checked=old), "morning report"))
        self.assertIn("still to come", said(content([], checked=future), "wat is low today"))
        self.assertIn("I still need your shelf check.", said(content([], checked=None), "how are we doing"))

    def test_duplicate_names_hidden_and_held_products_and_hikes_come_from_the_engine(self):
        events = [hike("Cass Hill", DAY), hike("Point Buchon", (TODAY + timedelta(days=1)).isoformat(), 9),
                  hike("Next week", (TODAY + timedelta(days=7)).isoformat())]
        c = content([prod("Salt", "no", pid="salt-1"), prod("salt", "no", pid="salt-2"), prod("Pepper", "limited"),
                     prod("Secret", "no", status="hidden"), prod("Hold", "no", status="held")], events=events)
        text = said(c, "what's on the shelves")
        self.assertEqual(text, engine(c))
        self.assertIn("Salt (2)", PLAIN(text))
        self.assertIn("Cass Hill", text)
        self.assertIn("Point Buchon", text)
        self.assertNotIn("Next week", text)  # only today and tomorrow, as in the report
        self.assertIn("I can't see how many guests have signed up", text)  # unavailable, never 0
        self.assertNotIn("Secret", text)
        self.assertNotIn("Hold", text)
        self.assertIn("2 sold out", text)

    def test_the_day_may_come_as_text(self):
        c = content(SHELF)
        self.assertEqual(said(c, "morning report", today=DAY), engine(c))
        self.assertEqual(said(c, "morning report", today="not a day"), reports.UNREADABLE)

    def test_nothing_is_added_to_the_engine_text(self):
        text = said(content(SHELF), "what's sold out?")
        for extra in ("Waiting for you", "Nothing is waiting", "Is today's shelf check right", reports.NO_PUSH):
            self.assertNotIn(extra, text)


class CountsAreProductLocal(unittest.TestCase):
    def count(self, c, text, **kw):
        return PLAIN(said(c, text, **kw))

    def test_counts_are_product_local_not_inventory(self):
        c = content(SHELF)
        self.assertEqual(self.count(c, "how many eggs do we have"), NO_COUNTS + "eggs: limited")  # the named fixture
        self.assertEqual(self.count(c, "how many honey do we have"), NO_COUNTS + "honey: sold out")
        self.assertEqual(self.count(c, "how much flour do we have?"), NO_COUNTS + "flour: available")
        self.assertEqual(self.count(c, "how many jam is left"), NO_COUNTS + "jam: not confirmed")
        for text in ("how many eggs do we have", "how many of the eggs are left", "what's the number of eggs", "How MANY eggs???"):
            with self.subTest(text):
                self.assertEqual(self.count(c, text), NO_COUNTS + "eggs: limited")
        for answer in (self.count(c, "how many eggs do we have"), self.count(c, "how many flour do we have")):
            self.assertNotRegex(answer, r"\d")  # never a quantity

    def test_another_products_word_is_never_borrowed(self):
        c = content([prod("eggs", "limited"), prod("honey", "no"), prod("flour", "yes")])
        self.assertEqual(self.count(c, "how many honey do we have"), NO_COUNTS + "honey: sold out")
        c = content([prod("eggs"), prod("honey", "no")])  # eggs has no word of its own: not honey's
        self.assertEqual(self.count(c, "how many eggs do we have"), NO_COUNTS + "eggs: not confirmed")

    def test_a_word_counts_only_when_dated_on_the_latest_check_as_in_the_report(self):
        old = (TODAY - timedelta(days=3)).isoformat()
        c = content([prod("eggs", "limited", on=old), prod("honey", "no", on=None), prod("flour", "maybe"),
                     prod("tea", "yes")])
        c.products[1]["available"] = "no"  # undated
        for text, word in (("eggs", "not confirmed"), ("honey", "not confirmed"), ("flour", "not confirmed"), ("tea", "available")):
            with self.subTest(text):
                self.assertEqual(self.count(c, f"how many {text} do we have"), f"{NO_COUNTS}{text}: {word}")

    def test_an_old_missing_or_future_check_is_said_next_to_the_word(self):
        old, future = (TODAY - timedelta(days=9)).isoformat(), (TODAY + timedelta(days=2)).isoformat()
        for checked, tail in ((old, "more than a week ago"), (future, "still to come"), (None, "I still need your shelf check.")):
            c = content([prod("eggs", "limited", on=checked)], checked=checked)
            with self.subTest(checked):
                lines = self.count(c, "how many eggs do we have").split("\n")
                self.assertEqual(len(lines), 2)
                self.assertTrue(lines[0].startswith(NO_COUNTS + "eggs: "), lines)
                self.assertIn(tail, lines[1])
        self.assertEqual(self.count(content([prod("eggs", "limited")]), "how many eggs do we have").count("\n"), 0)

    def test_a_nickname_works_and_an_unclear_product_gets_the_resolvers_one_question(self):
        c = content([prod("Free range eggs", "limited", pid="eggs-1"), prod("Linn's triple berry preserves", "yes", pid="p-1"),
                     prod("Linn's blueberry preserves", "no", pid="p-2")])
        self.assertEqual(self.count(c, "how many hens do we have", aliases={"hens": ("product", "eggs-1")}),
                         NO_COUNTS + "Free range eggs: limited")
        self.assertEqual(self.count(c, "how many preserves do we have"),
                         "Which one do you mean: Linn's triple berry preserves (Shack) or Linn's blueberry preserves (Shack)?")
        self.assertEqual(self.count(c, "how many unicorns do we have"), "I don't know a product called that. What is it called on the site?")
        self.assertNotIn(NO_COUNTS, self.count(c, "how many preserves do we have"))

    def test_hidden_and_held_products_are_not_on_the_report(self):
        c = content([prod("eggs", "no", status="held"), prod("honey", "no", status="hidden")])
        for text in ("how many eggs do we have", "how many honey do we have"):
            self.assertEqual(self.count(c, text), reports.NOT_ON_REPORT)

    def test_a_count_of_everything_or_of_hikes_is_the_report_itself(self):
        c = content(SHELF, events=[hike("Cass Hill", DAY)])
        for text in ("how many things are sold out", "how many hikes are coming up", "how many do we have", "how many are low",
                     "how many people are coming"):
            with self.subTest(text):
                self.assertEqual(said(c, text), engine(c))

    def test_the_ask_is_read_from_every_message_of_the_request(self):
        c = content(SHELF)
        self.assertEqual(PLAIN(said(c, "how many eggs do we have", "the shelf report")), NO_COUNTS + "eggs: limited")
        self.assertEqual(said(c, "email me the report", "the shelf report"), reports.NO_PUSH)


class DeliveryAndUnreadable(unittest.TestCase):
    def test_delivery_refusal_and_unreadable_content(self):
        c = content(SHELF)
        for text in ("email me the report every morning", "send me the shelf report each day", "text me when things sell out",
                     "can you mail me the report", "give me the report every morning", "report me automatically", "send me the report",
                     "Remind me every Monday what is low", "message me the shelf report"):
            with self.subTest(text):
                self.assertEqual(said(c, text), reports.NO_PUSH)
        self.assertEqual(reports.NO_PUSH, "I don't send reports on my own. Ask me for the morning report when you want it.")
        for text in ("what's sold out?", "morning report", "how are we doing today", "what's low", "what's on the shelves tonight",
                     "what is the message on the shelf", "what did I check last"):
            with self.subTest(text):
                self.assertEqual(said(c, text), engine(c))
        for broken in ({"id": "x", "name": "", "status": "active"}, {"id": "y", "name": 5, "status": "active"},
                       {"id": "z", "name": "Bad\nname", "status": "active"}, "not an object"):
            with self.subTest(broken):
                self.assertEqual(said(content([prod("eggs", "no"), broken]), "what's sold out?"), reports.UNREADABLE)
                self.assertEqual(said(content([broken]), "how many eggs do we have"), reports.UNREADABLE)
        self.assertEqual(reports.shelf_reply({}, ctx(None, "morning report")), reports.UNREADABLE)
        self.assertEqual(reports.shelf_reply({}, types.SimpleNamespace(texts=["morning report"])), reports.UNREADABLE)
        for sentence in (reports.UNREADABLE, reports.NOT_ON_REPORT, reports.NO_PUSH):
            self.assertEqual(voice.check(sentence), [], sentence)
            self.assertNotRegex(sentence, r"(?i)traceback|exception|products\.json|Error")


# -- the real Dispatcher and Conversation ----------------------------------------------------------------------------------
def snapshot_of(case):
    wt = case.repo.wt
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((wt / "hass" / "content").glob("*.json"))}
    tables = {t: case.conv.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("drafts", "approvals")}
    has = lambda name: case.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone()  # noqa: E731
    tables["backlog"] = case.conv.db.execute("SELECT COUNT(*) FROM backlog").fetchone()[0] if has("backlog") else 0
    control = [r[0] for r in case.conv.db.execute("SELECT name FROM control")] if has("control") else []
    return {"head": git(wt, "rev-parse", "HEAD"), "status": git(wt, "status", "--porcelain"), "files": files, "tables": tables,
            "control": control, "calls": list(case.calls)}


SCENARIOS = {  # name -> (checked on, {product: word or (word, day)}, hikes)
    "fresh": (DAY, {AVOCADO: "yes", EGGS: "limited", BREAD: "no", ORANGES: "no"}, ()),
    "none": (None, {}, ()),
    "stale": ("2026-10-23", {EGGS: "limited", BREAD: "no"}, ()),
    "future": ("2026-11-03", {EGGS: "limited"}, ()),
    "hikes": (DAY, {EGGS: "limited", BREAD: "no"}, (hike("Cass Hill", "2026-11-03"), hike("Point Buchon", DAY, 14))),
}


class ShelfCase(ConversationTestCase):
    """The H02 throwaway repo with the production op registry, the skills mode both, one skill (REPORT_SHELF) and a scripted
    stand-in for the model that returns the raw skill reply recorded for each text; the router is the stub that backs it."""
    STUB_ROUTER = True

    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "skills": {"mode": "both"}})
        self.asked, self.calls = [], []
        self.interp = Scripted({}, self.asked)
        self.editor = Clocked(self.repo.state, lambda: self.now)
        for name in ("prepare", "apply", "recover", "render_draft"):
            real = getattr(self.editor, name)
            setattr(self.editor, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.registry = base.registry_of(reports.REPORT_SHELF) if self.STUB_ROUTER else load_skills()
        if self.STUB_ROUTER:
            patcher = mock.patch.dict(sys.modules, {"hass.skills.router": base.StubRouter(self.interp)})
            patcher.start()
            self.addCleanup(patcher.stop)
        self.conv = self.open()
        self.baseline = snapshot_of(self)

    def open(self, ed=None):
        return conversation.Conversation(str(self.repo.state), ed or self.editor, self.interp, lambda: self.now,
                                         skills=getattr(self, "registry", None))

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")

    def scenario(self, name):
        checked, words, hikes = SCENARIOS[name]

        def store(doc):
            doc.pop("selection_checked_on", None)
            if checked:
                doc["selection_checked_on"] = checked

        def products(doc):
            for p in doc["products"]:
                p.pop("available", None), p.pop("available_on", None)
                if p["id"] in words:
                    word, on = words[p["id"]] if isinstance(words[p["id"]], tuple) else (words[p["id"]], checked)
                    p["available"], p["available_on"] = word, on
        self.edit("store.json", store)
        self.edit("products.json", products)
        self.edit("community.json", lambda doc: doc.update(events=list(hikes)))
        self.baseline = snapshot_of(self)

    def ask(self, text, reply=None):
        self.interp.mapping[text] = base.skill_reply("report.shelf") if reply is None else reply
        return self.say(text), self.replies()

    def expected(self, day=TODAY):
        from hass.content_model import load_content
        return morning_report.render(morning_report.facts(load_content(self.repo.wt / "hass" / "content"), day))

    def untouched(self):
        now = snapshot_of(self)
        for key in ("head", "status", "files", "tables", "control", "calls"):
            self.assertEqual(now[key], self.baseline[key], key)


class RealDispatch(ShelfCase):
    def test_catalog_rows_use_real_dispatch(self):
        rows = load_rows(CASES)
        self.assertGreaterEqual(len(rows), 10)
        for row in rows:
            with self.subTest(row=row["id"]):
                self.setUp()  # a fresh repo, conversation and clock per row
                self.replay(row)

    def replay(self, row):
        self.scenario(row["note"].removeprefix("content: "))
        want = row["expect"].get("dispositions") or [row["expect"]["disposition"]] * len(row["texts"])
        for text, recorded, disposition in zip(row["texts"], row["replies"], want):
            command = conversation.parse_command(text) is not None
            if command:
                self.assertEqual(self.say(text), disposition, text)
                [reply] = self.replies()
                self.assertIn(row["expect"]["reply_contains"], reply)
                continue
            self.interp.mapping[text] = base.skill_reply("report.shelf")
            self.assertEqual((self.say(text), disposition), ("answer", "unsupported"), text)
            [reply] = self.replies()
            self.assertEqual(reply, recorded["unsupported"], row["id"])  # the engine's text, byte for byte, as delivered
            self.assertEqual(PLAIN(reply), reply)
            if reply.startswith(("Your last shelf check", "I still need your shelf check.\nOn the shelves")):
                self.assertEqual(reply, PLAIN(self.expected()), row["id"])  # a report row is exactly facts + render of that content
            self.assertEqual(voice.check(reply, long_ok=True), [])
            self.assertTrue(self.asked and self.asked[-1][0] == text)  # the model picked the skill; code wrote the answer
        self.untouched()

    def test_a_long_report_is_delivered_unchanged_under_strict_voice(self):
        self.scenario("fresh")
        names = [f"Long product name number {chr(65 + i)} for the shelf" for i in range(12)]
        ids = [p["id"] for p in json.loads((self.repo.wt / "hass" / "content" / "products.json").read_text("utf-8"))["products"][:12]]

        def products(doc):
            for p in doc["products"][:12]:
                p["name"], p["available"], p["available_on"] = names[ids.index(p["id"])], "limited" if ids.index(p["id"]) % 2 else "no", DAY
        self.edit("products.json", products)
        want = self.expected()
        self.assertGreater(len(PLAIN(want)), voice.LONG_AFTER)
        self.assertLessEqual(len(PLAIN(want)), morning_report.MAX_CHARS)
        status, [reply] = self.ask("what's sold out?")
        self.assertEqual((status, reply), ("answer", PLAIN(want)))
        with mock.patch.object(dispatch, "READ_ONLY_LONG", set()):  # without the flag the strict voice rule refuses it: nothing is truncated
            with self.assertRaises(voice.VoiceError):
                self.ask("how are we doing")

    def test_only_registered_skills_are_allowed_a_long_answer(self):
        self.registry = base.registry_of(reports.ANSWER_SITE)
        self.conv = self.open()
        self.interp.mapping["what time do we close"] = base.skill_reply("answer.site", kind="hours")
        with mock.patch.object(self.conv, "_reply", wraps=self.conv._reply) as reply:
            self.say("what time do we close")
        self.assertEqual(reply.call_args.kwargs, {"long_ok": False})  # an unregistered read-only skill keeps the everyday length rule
        self.registry = base.registry_of(specials.SPECIALS_SHOW)
        self.conv = self.open()
        self.interp.mapping["what are this week's specials"] = base.skill_reply("specials.show")
        with mock.patch.object(self.conv, "_reply", wraps=self.conv._reply) as reply:
            self.assertEqual(self.say("what are this week's specials"), "answer")
        self.assertEqual(reply.call_args.kwargs, {"long_ok": True})  # RF0325-11: a registered one may run long
        self.scenario("fresh")
        self.registry = base.registry_of(reports.REPORT_SHELF)
        self.conv = self.open()
        with mock.patch.object(self.conv, "_reply", wraps=self.conv._reply) as reply:
            self.ask("what's sold out?")
        self.assertEqual(reply.call_args.kwargs, {"long_ok": True})

    def test_morning_report_alone_is_the_command_and_keeps_the_once_a_day_question(self):
        self.scenario("stale")  # no check today: the command asks, once
        self.interp.mapping["morning report"] = base.skill_reply("report.shelf")
        self.assertEqual(self.say("morning report"), "report")
        [first] = self.replies()
        self.assertEqual(self.asked, [])  # the model is never asked: the command takes the whole message
        self.assertIn(conversation.SHELF_ASK, first)
        self.assertIn("Nothing is waiting for you.", first)
        self.assertEqual(self.say("report"), "report")
        [second] = self.replies()
        self.assertNotIn(conversation.SHELF_ASK, second)  # once a day
        self.assertTrue(first.startswith(PLAIN(self.expected())))

    def test_the_skill_never_uses_up_the_once_a_day_question(self):
        self.scenario("stale")
        for text in ("what's sold out?", "what is low today"):
            self.assertEqual(self.ask(text)[0], "answer")
        self.assertEqual(self.untouched(), None)
        self.assertEqual(self.say("report"), "report")
        [reply] = self.replies()
        self.assertTrue(reply.endswith(conversation.SHELF_ASK), reply)  # the command still asks, under its old conditions
        self.assertEqual([r[0] for r in self.conv.db.execute("SELECT name FROM control")], ["shelf-asked"])

    def test_repeat_and_undo_have_no_site_effect(self):
        self.scenario("fresh")
        first, second = self.ask("what's sold out?"), self.ask("what is sold out now")
        self.assertEqual((first[0], second[0]), ("answer", "answer"))
        self.assertEqual(first[1], second[1])  # asked again: answered again, never sent unasked or skipped
        self.assertEqual(self.say("undo"), "no-target")
        self.assertEqual(self.replies(), ["There's nothing to undo."])
        self.untouched()
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 3)  # three asks, three answers; nothing else

    def test_delivery_refusal_writes_nothing_and_schedules_nothing(self):
        self.scenario("fresh")
        status, [reply] = self.ask("email me the report every morning")
        self.assertEqual((status, reply), ("answer", reports.NO_PUSH))
        self.untouched()
        tables = {r[0] for r in self.conv.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertFalse({n for n in tables if "schedule" in n or "subscription" in n or "email" in n})

    def test_a_count_question_through_dispatch(self):
        self.scenario("fresh")
        status, [reply] = self.ask("how many eggs do we have")
        self.assertEqual((status, reply), ("answer", NO_COUNTS + "Cal Poly eggs: limited"))
        self.untouched()

    def test_unreadable_content_gets_the_plain_sentence(self):
        self.scenario("fresh")
        self.edit("products.json", lambda doc: doc["products"][0].update(name=""))
        self.baseline = snapshot_of(self)  # the unreadable record is the test's own state, set before the ask
        status, [reply] = self.ask("what's sold out?")
        self.assertEqual((status, reply), ("answer", reports.UNREADABLE))
        self.untouched()


class RealRouter(ShelfCase):
    """With the real router and the whole catalog: a typo, a vague and a multi ask reach the skill and are answered at once; a
    plain `what's sold out?` shares its words with three stock skills, so the owner is asked which he means first (the router's
    own rule, not changed here) and the pick he then makes stands."""
    STUB_ROUTER = False

    def test_typo_vague_and_multi_asks_route_to_the_skill_and_are_answered(self):
        self.scenario("fresh")
        names = {t.text: [n for n, _ in router.candidates(t.text, skills=self.registry)] for t in reports.REPORT_SHELF.triggers}
        for text in ("wat is low today", "how are we doing", "what's sold out and what hikes are coming up",
                     "how many eggs do we have", "email me the report every morning", "anything waiting for me?"):
            with self.subTest(text):
                self.assertEqual(names[text][0], "report.shelf")
                status, [reply] = self.ask(text)
                self.assertEqual(status, "answer")
                self.assertTrue(reply)
        for text in ("what did I check last", "what's on the shelves", "what's sold out?"):
            self.assertTrue(names[text])  # the lead of these is shared with the stock skills

    def test_a_plain_sold_out_question_is_asked_once_then_answered(self):
        self.scenario("fresh")
        status, [question] = self.ask("what's sold out?")
        self.assertEqual(status, "question")
        self.assertTrue(question.startswith("Do you want to ") and "morning shelf report" in question, question)
        self.untouched()
        status, [reply] = self.ask("the shelf report")
        self.assertEqual((status, reply), ("answer", PLAIN(self.expected())))
        self.untouched()



# -- AV1109-09 site answers --------------------------------------------------------------------------------------
SITE_CASES = REPO_ROOT / reports.ANSWER_SITE.cases
STORY = "We grow café fruit—slowly, with care."


def site_content():
    c = content([dict(prod("eggs", "limited"), producerKey="sunny")], events=[dict(hike("Cass Hill", "2026-11-03"), meetingPoint="North gate")])
    c.store["hours"] = ["Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday"]
    c.makers = {"sunny": {"name": "Sunny Farm", "place": "Cambria", "story": STORY}}
    return c


def site_ctx(c=None, **kw):
    from hass.tests.test_conversation import T0
    return types.SimpleNamespace(content=c if c is not None else site_content(), today=TODAY, now=T0,
                                 aliases=kw.pop("aliases", {}), texts=kw.pop("texts", []), guest_counts_db=kw.pop("guest_counts_db", None), **kw)


def site(kind, c=None, **slots):
    return PLAIN(reports.site_reply({"kind": kind, **slots}, site_ctx(c)))


class SiteSources(unittest.TestCase):
    def test_site_metadata_closed_kind_and_registry(self):
        skill = load_skills().get("answer.site")
        self.assertEqual(skill, reports.ANSWER_SITE)
        self.assertEqual(skill.plan({}, object()), [])
        self.assertEqual((skill.edits, skill.side_effects, skill.approval, skill.undo), ((), ("none",), "none", Undo("none", "none")))
        self.assertEqual([s.name for s in skill.slots], ["kind", "subject", "day"])
        # The kit refuses an undo marker on a read-only row (it undoes every draft itself), so as for report.shelf the no-op
        # undo is the `turns` row and only the lint's "undo row" count is not met.
        self.assertEqual([p for p in lint_cases(skill, REPO_ROOT) if "undo row" not in p], [])
        self.assertEqual([p for p in skill_lint(load_skills(), load_registry(), repo_root=REPO_ROOT,
                         golden={"answer.site": [{}]}) if p.startswith("answer.site:") and "undo row" not in p], [])
        for kind in reports.KINDS:
            slots = {"kind":kind}
            if kind in reports.SUBJECTS:
                slots["subject"] = {"product":"eggs", "maker":"Sunny Farm", "hike":"Cass Hill"}[reports.SUBJECTS[kind]]
            self.assertIsNone(reports.site_guard(slots, [], site_ctx()), slots)
        for slots in ({"kind":"invented"}, {"kind":[]}, {"kind":"product","subject":"eggs","day":"today"},
                      {"kind":"hours","subject":"eggs"}, {"kind":"hours","day":4}, {"kind":"product"}):
            self.assertIsNotNone(reports.site_guard(slots, [], site_ctx()), slots)
            self.assertTrue(reports.site_reply(slots, site_ctx()))
        self.assertEqual(reports.site_reply(None, site_ctx()), reports.SITE_ASK)

    def test_the_generated_prompt_spells_out_the_kind_tokens_and_subject_rules(self):
        """The interpreter sees only skills.prompt output: every accepted kind and its subject rule must be in it."""
        import re
        from hass.interpreter_prompt import build
        from hass.skills.prompt import skills_section
        from hass.tests.test_interpreter_prompt import TEST_REGISTRY, tiny_content
        reg = load_skills()
        for prompt in (skills_section(reg, [("answer.site", 9.0)]),
                       build(TEST_REGISTRY, tiny_content(), reg, [("answer.site", 9.0)])):
            [kind_line] = [ln for ln in prompt.splitlines() if ln.startswith("  slots: kind: enum, required")]
            self.assertIn("answer.site", prompt)
            [kinds_text] = re.findall(r"kind: enum, required - exactly one of \(([^)]*)\)", kind_line)
            self.assertEqual(tuple(kinds_text.split(" | ")), reports.KINDS)
            [subject_text] = re.findall(r"subject: text, optional - \(([^)]*)\)", kind_line)
            mapped = {}
            for family, kinds_ in re.findall(r"the (product|maker|hike)'s name for ([a-z_ ]+?)(?:,|$)", subject_text):
                mapped.update({k: family for k in kinds_.split(" or ")})
            self.assertEqual(mapped, reports.SUBJECTS)
            self.assertIn("day: day, optional - only for hours", kind_line)
        # the tokens the prompt gives are exactly the ones the guard lets through
        for kind in reports.KINDS:
            slots = {"kind": kind}
            if kind in reports.SUBJECTS:
                slots["subject"] = {"product": "eggs", "maker": "Sunny Farm", "hike": "Cass Hill"}[reports.SUBJECTS[kind]]
            self.assertIsNone(reports.site_guard(slots, [], site_ctx()), kind)
        # and the vocabulary is on the slot line, which the cap never shortens, with three candidates in full
        crowded = skills_section(reg, [("answer.site", 9.0), ("report.shelf", 5.0), ("stock.set", 4.0)])
        self.assertLessEqual(len(crowded.encode("utf-8")), 6 * 1024)
        for kind in reports.KINDS:
            self.assertIn(kind, crowded)

    def test_hours_day_today_and_literal_fallback(self):
        self.assertEqual(site("hours"), "The site says: Monday–Friday 9am–6pm")
        self.assertEqual(site("hours",day="saturday"), "The site says: Saturday 9am–5pm")
        self.assertEqual(site("hours",day="sunday"), "The site says: Closed Sunday")
        c=site_content()
        for line in ("Mon-Fri 8–4", "Mon—Fri 8–4", "Daily call first", "Every day 10 to 2"):
            c.store["hours"]=[line]
            self.assertEqual(site("hours",c), "The site says: "+line)
        for lines in (["Call first"], ["Daily 9–5", "Monday 10–4"], ["Daily 9–5", "Holidays vary"]):
            c.store["hours"]=lines
            reply=site("hours",c)
            self.assertTrue(reply.startswith("I can't tell which hours apply"))
            for line in lines: self.assertIn(line,reply)
        c.store["hours"]=[]
        self.assertEqual(site("hours",c),reports.NO_HOURS)
        from datetime import datetime
        ctx=site_ctx(); ctx.now=datetime.fromisoformat("2026-11-03T07:30:00+00:00")
        ctx.today=ctx.now.astimezone(reports.PACIFIC).date()
        self.assertEqual(reports.site_reply({"kind":"hours"},ctx),reports.site_reply({"kind":"hours"},site_ctx()))

    def test_next_and_count_share_real_upcoming_filter(self):
        c=site_content(); good=c.community["events"][0]
        c.community["routeIdeas"]=[dict(good,title="Idea")]
        excluded=[dict(good,id="cancelled",status="cancelled"),dict(good,id="completed",status="completed"),
                  dict(good,id="passed",startsAt="2026-11-01T08:00:00-08:00"),dict(good,id="now",startsAt=site_ctx().now.isoformat()),
                  dict(good,id="naive",startsAt="2026-11-03T08:00:00"),dict(good,id="bad",startsAt="bad"),dict(good,id="sample",sample=True)]
        c.community["events"]=[*excluded,dict(good,id="z",title="Later tie"),dict(good,id="a"),
                               dict(good,id="later",startsAt="2026-11-03T18:00:00+00:00")]
        self.assertEqual(site("hike_count",c),"Upcoming hikes on the site: 3.")
        self.assertIn("Cass Hill, tuesday, november 3 at 8 am. Meet at North gate.",site("next_hike",c))
        c.community["events"][len(excluded)+1].pop("meetingPoint")
        self.assertIn("can't see all the details",site("next_hike",c))
        c.community["events"]=excluded
        self.assertEqual(site("next_hike",c),reports.NO_HIKE)
        self.assertEqual(site("hike_count",c),"Upcoming hikes on the site: 0.")

    def test_product_and_linked_maker_are_record_local(self):
        c=site_content()
        ctx=site_ctx(c,aliases={"hens":("product","eggs")})
        self.assertIn("eggs: limited",PLAIN(reports.site_reply({"kind":"product","subject":"hens"},ctx)))
        self.assertEqual(site("product_maker",c,subject="eggs"),"Made by Sunny Farm in Cambria.")
        for link in (None,"absent"):
            c.products[0]["producerKey"]=link
            self.assertEqual(site("product_maker",c,subject="eggs"),reports.NO_MAKER)
        c.products[0]["producerKey"]="sunny"; c.makers["sunny"]["hidden"]=True
        self.assertEqual(site("product_maker",c,subject="eggs"),reports.NO_MAKER)
        c.makers["sunny"].pop("hidden"); c.makers["sunny"].pop("place")
        self.assertIn("can't see where",site("product_maker",c,subject="eggs"))
        c.products[0]["available_on"]="2026-10-01"
        self.assertIn("not confirmed",site("product",c,subject="eggs"))
        c.store["selection_checked_on"]="2026-10-01"
        self.assertIn("more than a week ago",site("product",c,subject="eggs"))
        for status in ("hidden","held"):
            c.products[0]["status"]=status
            self.assertIsNotNone(reports.site_guard({"kind":"product","subject":"eggs"},[],site_ctx(c)))
        c.products=[prod("eggs",pid="a"),prod("eggs",pid="b")]
        self.assertIn("Which one",site("product",c,subject="eggs"))
        self.assertIn("don't know a product",site("product",c,subject="unknown"))

    def test_maker_story_verbatim_strict_voice(self):
        c=site_content(); story="café—“fruit”! " + "a"*586
        c.makers["sunny"]["story"]=story
        reply=reports.site_reply({"kind":"maker_story","subject":"Sunny Farm"},site_ctx(c))
        self.assertEqual(PLAIN(reply),story)
        self.assertEqual(voice.check(reply,long_ok=True),[])
        c.makers["sunny"]["story"]=""
        self.assertEqual(site("maker_story",c,subject="Sunny Farm"),reports.NO_STORY)

    def test_signups_confirmed_or_unavailable(self):
        import sqlite3
        from tempfile import TemporaryDirectory
        from pathlib import Path
        slots={"kind":"hike_signups","subject":"Cass Hill"}
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"guests.sqlite3"
            self.assertIn("unavailable",reports.site_reply(slots,site_ctx(guest_counts_db=path)))
            self.assertFalse(path.exists())
            db=sqlite3.connect(path); db.execute("CREATE TABLE rsvps (event_id, party_size)"); db.commit()
            def reply(): return PLAIN(reports.site_reply(slots,site_ctx(guest_counts_db=path)))
            self.assertEqual(reply(),"Confirmed sign-ups for Cass Hill: 0.")
            db.executemany("INSERT INTO rsvps VALUES (?,?)",[("cass-hill",2),("cass-hill",3),("other",None)]); db.commit()
            before=path.read_bytes()
            self.assertEqual(reply(),"Confirmed sign-ups for Cass Hill: 5.")
            self.assertEqual(path.read_bytes(),before)
            for bad in (None,0,-1,"two"):
                db.execute("INSERT INTO rsvps VALUES (?,?)",("cass-hill",bad)); db.commit()
                self.assertIn("unavailable",reply())
                db.execute("DELETE FROM rsvps WHERE rowid=(SELECT MAX(rowid) FROM rsvps)"); db.commit()
            db.execute("DROP TABLE rsvps"); db.commit(); db.close()
            self.assertIn("unavailable",reply())
        from hass.ops import hikes
        self.assertNotRegex(hikes.GUEST_QUERY.lower(),r"email|name")
        with mock.patch.object(hikes,"guest_counts_checked",side_effect=sqlite3.OperationalError("denied")):
            self.assertIn("unavailable",reports.site_reply(slots,site_ctx(guest_counts_db="synthetic")))


class SiteDispatch(ShelfCase):
    def setUp(self):
        super().setUp()
        self.registry=base.registry_of(reports.ANSWER_SITE)
        self.conv=self.open()
        c=site_content()
        self.edit("products.json",lambda d:d.update(products=c.products))
        self.edit("store.json",lambda d:d.update(c.store))
        self.edit("makers.json",lambda d:d.update(makers=c.makers))
        self.edit("community.json",lambda d:d.update(c.community))
        self.baseline=snapshot_of(self)

    def ask_site(self,text,slots):
        self.interp.mapping[text]=base.skill_reply("answer.site",**slots)
        return self.say(text),self.replies()

    def test_model_answer_slot_ignored_real_dispatch_and_all_case_rows(self):
        rows=load_rows(SITE_CASES)
        self.assertGreaterEqual(len(rows),12)
        for row in rows:
            with self.subTest(row=row["id"]):
                self.setUp()
                meta=json.loads(row["note"])
                status,[reply]=self.ask_site(row["texts"][0],meta["slots"])
                self.assertEqual(status,"backlog" if meta["backlog"] else "answer")
                expected=row["replies"][0]["unsupported"]
                if meta["backlog"]:
                    self.assertTrue(reply.startswith(expected),reply)
                    self.assertIn("request #1",reply)
                    self.baseline["tables"]["backlog"]=1
                else: self.assertEqual(reply,expected)
                self.assertNotIn("FAKE ANSWER",reply)
                self.assertEqual(voice.check(reply),[])
                if row["texts"][-1]=="undo":  # the kit has no undo marker for a read-only skill: the no-op undo is a turns row
                    self.assertEqual(self.say("undo"),"no-target")
                    self.assertEqual(self.replies(),["There's nothing to undo."])
                self.untouched()

    def test_story_delivery_and_only_story_gets_long_flag(self):
        story="A"*600
        self.edit("makers.json",lambda d:d["makers"]["sunny"].update(story=story))
        with mock.patch.object(self.conv,"_reply",wraps=self.conv._reply) as send:
            self.assertEqual(self.ask_site("tell me Sunny Farm story",{"kind":"maker_story","subject":"Sunny Farm"}),('answer',[story]))
            self.assertEqual(send.call_args.kwargs,{"long_ok":True})
        with mock.patch.object(self.conv,"_reply",wraps=self.conv._reply) as send:
            self.ask_site("when do we close",{"kind":"hours"})
            self.assertEqual(send.call_args.kwargs,{"long_ok":False})

    def test_model_guest_prose_ignored_and_trusted_setting_only(self):
        import sqlite3
        path=self.repo.state/"synthetic-guests.sqlite3"
        db=sqlite3.connect(path); db.execute("CREATE TABLE rsvps (event_id, party_size)")
        db.executemany("INSERT INTO rsvps VALUES (?,?)",[("cass-hill",2),("cass-hill",4)]); db.commit(); db.close()
        before=path.read_bytes()
        self.set_settings({**SETTINGS,"skills":{"mode":"both"},"guestCountsDb":str(path)})
        self.conv=self.open()
        status,[reply]=self.ask_site("how many signed up for Cass Hill",{"kind":"hike_signups","subject":"Cass Hill","answer":"900 guests", "guestCountsDb":"not-trusted"})
        self.assertEqual((status,reply),("answer","Confirmed sign-ups for Cass Hill: 6."))
        self.assertEqual(path.read_bytes(),before)
        self.assertNotIn(str(path),reply)
        self.untouched()

    def test_unknown_subject_and_incorrect_combinations_backlog_once(self):
        for slots in ({"kind":"product","subject":"unknown"},{"kind":"hours","subject":"eggs"},
                      {"kind":"product","subject":"eggs","day":"today"}):
            self.setUp()
            self.assertEqual(self.ask_site("answer my site question",slots)[0],"backlog")
            self.baseline["tables"]["backlog"]=1
            self.untouched()

    def test_missing_kind_one_question_cancelled_and_expired_requests(self):
        self.assertEqual(self.ask_site("answer my site question",{})[0],"question")
        self.interp.mapping["never mind"] = {"cancel": True}
        self.assertEqual(self.say("never mind"),"cancelled")
        self.replies()
        self.assertEqual(self.ask_site("answer my site question again",{})[0],"question")
        self.now+=timedelta(hours=25)
        self.assertEqual(self.ask_site("what are the opening hours now",{"kind":"hours"})[0],"answer")
        self.assertEqual(self.drafts(),[])

    def test_duplicate_and_top_level_prose_are_not_relayed(self):
        self.interp.mapping["what time do we close"] = base.skill_reply("answer.site",kind="hours")
        self.assertEqual(self.say("what time do we close",pid="once"),"answer"); self.replies()
        self.assertEqual(self.say("what time do we close",pid="once"),"duplicate")
        self.assertEqual(self.replies(),[])
        raw={"skill":"answer.site","slots":{"kind":"hours"},"answer":"FAKE ANSWER"}
        self.assertIsNone(dispatch.checked(raw))
        self.interp.mapping["tell me hours please"]=raw
        self.say("tell me hours please")
        self.assertNotIn("FAKE ANSWER"," ".join(self.replies()))
        self.untouched()


if __name__ == "__main__":
    unittest.main()
