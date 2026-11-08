"""HASS-NL-1 tests: the hints the shop software works out before the model reads an owner text (hass/nl_prep.py), how the
interpreter request carries them, and Conversation's `recent` question. Synthetic catalog and texts only; no model, no socket.
Run: python3 -m unittest hass.tests.test_nl_prep -v
"""

import json
import unittest
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from hass import conversation, nl_eval, nl_prep
from hass.interpreter_local import LocalInterpreter
from hass.tests.test_conversation import ConversationTestCase

MONDAY = date(2026, 11, 9)  # the corpus' fixed "today"
URL = "http://127.0.0.1:11434"


def product(n, name, category="fruit", maker=None, status="active", description=""):
    return {"id": f"photo-product-{n:03d}", "name": name, "category": category, "producerKey": maker, "status": status,
            "description": description}


def tiny(hours=("Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday")):
    products = [product(1, "Hass avocados"), product(2, "Lemons"), product(3, "Cal Poly eggs", "eggs", "calpoly"),
                product(4, "Stepladder avocado blossom honey", "pantry", "stepladder"),
                product(5, "Big Sur Honey Company honey", "pantry", "bigsur"),
                product(6, "Rye bread", "bread", "brian"), product(7, "Cracked wheat sourdough", "bread", "brian"),
                product(8, "Cass Hill Blend", "drinks", "cass"), product(9, "Old jam", "pantry", status="hidden"),
                product(10, "Cal Poly white cheddar", "dairy", "calpoly"), product(11, "Cal Poly chipotle cheddar", "dairy", "calpoly")]
    makers = {"calpoly": {"name": "Cal Poly"}, "brian": {"name": "Brian's Bakery"}, "stepladder": {"name": "Stepladder"},
              "bigsur": {"name": "Big Sur Honey Company"}, "cass": {"name": "Cass Hill Coffee"}}
    events = [{"id": "hike-2026-11-14-point-buchon", "title": "Point Buchon walk", "startsAt": "2026-11-14T08:30:00-08:00", "status": "scheduled"},
              {"id": "hike-2026-11-22-cass-hill", "title": "Cass Hill hike", "startsAt": "2026-11-22T09:00:00-08:00", "status": "scheduled"}]
    return SimpleNamespace(products=products, makers=makers, community={"events": events, "routeIdeas": [{"id": "idea-morro", "title": "Morro Rock"}]},
                           store={"hours": list(hours)})


class HintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hint = staticmethod(nl_prep.make_hinter(tiny()))

    def ask(self, text, aliases=None, today=MONDAY):
        return self.hint(text, today, aliases)

    def test_one_match_is_a_product_and_two_are_ambiguous(self):
        self.assertEqual(self.ask("eggs are out")["products"], [{"said": "eggs", "is": {"id": "photo-product-003", "name": "Cal Poly eggs"}}])
        [row] = self.ask("honey is sold out")["products"]
        self.assertEqual([c["id"] for c in row["ambiguous"]], ["photo-product-004", "photo-product-005"])
        self.assertNotIn("is", row)
        [row] = self.ask("the cheddar is low")["products"]
        self.assertEqual(len(row["ambiguous"]), 2)

    def test_a_spelling_guess_is_marked_as_a_guess(self):
        [row] = self.ask("avacados limited today")["products"]
        self.assertEqual((row["is"]["id"], row["spelling"]), ("photo-product-001", "guessed"))
        [row] = self.ask("lemons are limited")["products"]
        self.assertNotIn("spelling", row)

    def test_an_owner_alias_names_exactly_its_record(self):
        alias = [{"name": "the good stuff", "kind": "product", "id": "photo-product-005"}]
        [row] = self.ask("the good stuff is gone", aliases=alias)["products"]
        self.assertEqual((row["is"]["id"], row["alias"]), ("photo-product-005", True))
        self.assertNotIn("products", self.ask("zzz is gone", aliases=[{"name": 5}, "junk", {"name": "x"}]))

    def test_a_shelf_lists_its_active_products_only(self):
        [shelf] = self.ask("bread is gone")["shelves"]
        self.assertEqual((shelf["shelf"], shelf["count"]), ("bread", 2))
        self.assertEqual(sorted(p["id"] for p in shelf["products"]), ["photo-product-006", "photo-product-007"])
        self.assertNotIn("photo-product-009", json.dumps(self.ask("pantry is empty")["shelves"]))  # hidden stays out

    def test_a_maker_alone_lists_its_products(self):
        [row] = self.ask("nothing from Cal Poly today")["makers"]
        self.assertEqual(row["key"], "calpoly")
        self.assertEqual(len(row["products"]), 3)

    def test_dates_are_worked_out_in_the_pacific_calendar(self):
        dates = {row["said"]: row for row in self.ask("tomorrow, the 29th, dec 5, in 2 weeks, last friday")["dates"]}
        self.assertEqual(dates["tomorrow"]["date"], "2026-11-10")
        self.assertEqual((dates["29th"]["date"], dates["29th"]["weekday"]), ("2026-11-29", "Sunday"))
        self.assertEqual(dates["dec 5"]["date"], "2026-12-05")
        self.assertEqual(dates["in 2 weeks"]["date"], "2026-11-23")
        self.assertEqual(dates["last friday"]["date"], "2026-11-06")
        [row] = self.ask("wednesday")["dates"]
        self.assertEqual((row["next"], row["last"]), ("2026-11-11", "2026-11-04"))

    def test_an_unclear_day_gives_both_readings_and_a_loose_time_gives_none(self):
        [row] = self.ask("next saturday")["dates"]
        self.assertEqual(row["unclear"], ["2026-11-14", "2026-11-21"])
        self.assertNotIn("date", row)
        [row] = self.ask("sometime next week")["dates"]
        self.assertIsNone(row["date"])
        self.assertIn("ask", row["note"])

    def test_a_past_date_rolls_to_next_year_and_a_bad_one_is_left_out(self):
        self.assertEqual(self.ask("nov 2")["dates"][0]["date"], "2027-11-02")
        self.assertNotIn("dates", self.ask("feb 30"))

    def test_times_and_numbers(self):
        times = {t["said"]: t["time"] for t in self.ask("8:30am, 5pm, noon and 17:45")["times"]}
        self.assertEqual(times, {"8:30am": "08:30", "5pm": "17:00", "noon": "12:00", "17:45": "17:45"})
        self.assertNotIn("times", self.ask("no time here"))
        self.assertEqual(self.ask("two dozen")["numbers"], [{"said": "two", "value": 2}, {"said": "dozen", "value": 12}])

    def test_a_price_is_only_flagged_never_used(self):
        self.assertEqual(self.ask("make the lemons $9 each")["price"], {"mentioned": True, "amounts": ["9"]})
        self.assertNotIn("price", self.ask("lemons are out"))

    def test_hikes_by_name_and_by_weekday(self):
        named = self.ask("cancel the point buchon walk")["hikes"]["named"]
        self.assertEqual(named[0]["hike"], "hike-2026-11-14-point-buchon")
        [row] = self.ask("move the walk on saturday")["hikes"]["onThatWeekday"]
        self.assertEqual(row["scheduled hikes"][0]["hike"], "hike-2026-11-14-point-buchon")
        self.assertNotIn("hikes", self.ask("change the shop hours on saturday"))  # a weekday alone is not about hikes

    def test_a_hike_name_is_not_also_the_product_of_that_name(self):
        out = self.ask("cancel the cass hill walk")
        self.assertEqual(out["hikes"]["named"][0]["hike"], "hike-2026-11-22-cass-hill")
        self.assertNotIn("products", out)
        self.assertEqual(self.ask("cass hill blend is out")["products"][0]["is"]["id"], "photo-product-008")

    def test_the_hours_the_store_already_shows_are_a_fact_not_a_draft(self):
        self.assertEqual(self.ask("can you change the shop hours to 9 to 5 on saturdays")["alreadyTrue"], ["Saturday already 9am–5pm"])
        self.assertEqual(self.ask("saturday 9am to 5pm")["alreadyTrue"], ["Saturday already 9am–5pm"])
        self.assertEqual(self.ask("wed 9-6")["alreadyTrue"], ["Wednesday already 9am–6pm"])
        for text in ("saturdays 10 to 4", "sunday 10-2", "make saturday 9 to 6", "saturday hours?", "open at 9 to 5"):
            self.assertNotIn("alreadyTrue", self.ask(text), text)
        self.assertNotIn("alreadyTrue", nl_prep.make_hinter(tiny(hours=()))("saturday 9 to 5", MONDAY))

    def test_a_two_day_hours_request_is_a_fact_only_when_every_change_is_already_true(self):
        for text in ("Saturday 9 to 5 and Sunday 10 to 2", "Sunday 10 to 2 and Saturday 9 to 5", "9 to 5 on saturday and 10 to 2 on sunday"):
            self.assertNotIn("alreadyTrue", self.ask(text), text)
        self.assertEqual(self.ask("Saturday 9 to 5 and Wednesday 9 to 6")["alreadyTrue"], ["Saturday already 9am–5pm", "Wednesday already 9am–6pm"])
        self.assertEqual(self.ask("saturday and wednesday 9 to 5").get("alreadyTrue"), None)

    def test_a_shared_prefix_is_not_resolved_to_one_product(self):
        hint = nl_prep.make_hinter(SimpleNamespace(products=[product(1, "Lemons"), product(2, "Lemonade", "drinks")], makers={},
                                                   community={}, store={"hours": []}))
        self.assertNotIn("products", hint("lem is out", MONDAY))
        self.assertEqual(hint("lemons is out", MONDAY)["products"][0]["is"]["id"], "photo-product-001")

    def test_asked_range(self):
        for text, want in (("9 to 5", ("9am", "5pm")), ("8:30-4pm", ("8:30am", "4pm")), ("10am until 2pm", ("10am", "2pm")),
                           ("11 to 3", ("11am", "3pm")), ("noon to 5", None), ("sat 13 to 5", None), ("no range", None)):
            self.assertEqual(nl_prep.asked_range(text), want, text)

    def test_nothing_to_say_is_an_empty_dict_and_the_same_text_gives_the_same_hints(self):
        self.assertEqual(self.ask("hello there"), {})
        self.assertEqual(self.ask("honey 5pm tomorrow $4"), self.ask("honey 5pm tomorrow $4"))

    def test_odd_content_and_odd_text_never_raise(self):
        for content in (SimpleNamespace(), SimpleNamespace(products=None, makers=[], community="x", store=3),
                        SimpleNamespace(products=[None, 3, {"id": 4}, {"id": "p", "name": None}], makers={"k": None, "j": 5}, community={"events": [None, {"id": 1}]})):
            hint = nl_prep.make_hinter(content)
            for text in ("eggs are out", "\ud800 lone surrogate", "x" * 5000, "", "nov 31 29th 99/99 25:99 $", "ａｖｏ"):
                self.assertIsInstance(hint(text, MONDAY, None), dict)

    def test_a_hint_never_carries_a_claim_a_price_or_a_quantity_it_was_not_given(self):
        out = json.dumps(self.ask("honey is sold out"))
        for word in ("organic", "local", "$", "quantity"):
            self.assertNotIn(word, out)


class CorpusHintTests(unittest.TestCase):
    """The corpus catalog: the hints agree with the answer key wherever the key names one product."""

    def test_clear_availability_cases_resolve_to_the_expected_product(self):
        hint = nl_prep.make_hinter(nl_eval._content())
        checked = 0
        for case in nl_eval.load_corpus():
            ops = case["expect"].get("ops") or []
            ids = {c["args"]["id"] for c in ops if c["op"].startswith("product.") and "id" in c["args"]}
            if case["intent"] != "availability" or len(ids) != 1 or case.get("also") or len(ops) != 1: continue
            rows = hint(case["text"], nl_eval.SENT_AT.date(), case.get("aliases")).get("products", [])
            resolved = {r["is"]["id"] for r in rows if "is" in r}
            if resolved: self.assertEqual(resolved, ids, case["id"])  # a hint that names a product names the right one
            checked += 1
        self.assertGreater(checked, 40)


class RequestTests(unittest.TestCase):
    def fake(self, seen):
        def transport(url, body, headers, timeout):
            seen.append(json.loads(body))
            return 200, json.dumps({"done": True, "message": {"content": json.dumps({"question": "ok"})}}).encode()
        return transport

    def user(self, seen):
        return json.loads(seen[-1]["messages"][1]["content"])

    def make(self, seen, **kw):
        return LocalInterpreter(URL, "m", "SYSTEM", transport=self.fake(seen), clock=lambda: datetime(2026, 11, 9, 17, 40, tzinfo=timezone.utc), **kw)

    def test_no_hinter_and_no_recent_leaves_the_request_as_it_was(self):
        seen = []
        self.make(seen).interpret("eggs are out", [])
        self.assertEqual(set(self.user(seen)), {"message", "pending", "today", "weekday"})

    def test_hints_and_recent_are_added_only_when_there_is_something(self):
        seen = []
        interp = self.make(seen, hinter=nl_prep.make_hinter(tiny()))
        interp.interpret("eggs are out", [], recent={"question": "Which one?"})
        user = self.user(seen)
        self.assertEqual(user["hints"]["products"][0]["is"]["id"], "photo-product-003")
        self.assertEqual(user["recent"], {"question": "Which one?"})
        interp.interpret("hello there", [])
        self.assertEqual(set(self.user(seen)), {"message", "pending", "today", "weekday"})
        for bad in (None, {}, {"question": ""}, {"question": 5}, "Which one?", ["x"]):
            interp.interpret("hello there", [], recent=bad)
            self.assertNotIn("recent", self.user(seen), bad)

    def test_the_hint_day_is_the_pacific_day(self):
        seen = []
        late = datetime(2026, 11, 10, 3, 30, tzinfo=timezone.utc)  # 7:30pm Monday in California
        interp = self.make(seen, hinter=nl_prep.make_hinter(tiny()))
        interp.interpret("tomorrow", [], sent_at=late)
        user = self.user(seen)
        self.assertEqual((user["today"], user["hints"]["dates"][0]["date"]), ("2026-11-09", "2026-11-10"))

    def test_a_raising_or_wrong_hinter_means_no_hints_not_a_failed_call(self):
        for hinter in (lambda *a: 1 / 0, lambda *a: "text", lambda *a: None):
            seen = []
            interp = self.make(seen, hinter=hinter)
            self.assertEqual(interp.interpret("eggs", []), {"question": "ok"})
            self.assertEqual((interp.last_error, "hints" in self.user(seen)), (None, False))
        with self.assertRaises(ValueError):
            LocalInterpreter(URL, "m", "SYSTEM", hinter="not callable")

    def test_hints_are_sent_after_the_saved_context(self):
        seen = []
        self.make(seen, hinter=nl_prep.make_hinter(tiny())).interpret("eggs are out", [], notes=["n"], aliases=[{"name": "x", "kind": "product", "id": "photo-product-001"}])
        self.assertEqual(list(self.user(seen))[-3:], ["notes", "aliases", "hints"])


class RecentQuestionTests(ConversationTestCase):
    """Conversation passes Hass's last question to the interpreter, but only while it is the newest word and still fresh."""

    def setUp(self):
        super().setUp()
        self.asked = []
        outer = self

        class Recording(conversation.FixtureInterpreter):
            def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
                outer.asked.append((text, recent))
                return super().interpret(text, pending)

        self.interp = Recording(self.interp.mapping)
        self.conv = self.open()

    def test_the_first_message_has_no_recent_and_the_answer_gets_the_question(self):
        self.assertEqual(self.say("when?"), "question")
        self.replies()
        self.assertEqual(self.asked[-1], ("when?", None))
        self.now += timedelta(minutes=5)
        self.say("hours")
        self.assertEqual(self.asked[-1], ("hours", {"question": "Which day should change?"}))

    def test_it_is_dropped_after_30_minutes_or_once_something_else_was_said(self):
        self.say("when?")
        self.now += timedelta(minutes=31)
        self.say("hours")
        self.assertIsNone(self.asked[-1][1])
        self.say("when?")
        self.say("hours")  # answered once: the proposal is newest now
        self.say("desc")
        self.assertIsNone(self.asked[-1][1])

    def test_a_question_from_before_a_newer_message_is_not_recent(self):
        self.say("when?")
        self.say("status")  # a command, not a question
        self.say("hours")
        self.assertIsNone(self.asked[-1][1])

    def test_a_question_is_kept_only_up_to_500_characters(self):
        self.interp.mapping["long?"] = {"question": "Which one? " + "x" * 600}
        self.say("long?")
        self.say("hours")
        self.assertIsNone(self.asked[-1][1])
        self.assertEqual(conversation.RECENT_MAX, 500)

    def test_a_missing_table_or_bad_row_is_no_recent_not_a_crash(self):
        self.conv.db.execute("DROP TABLE outbox")
        self.assertIsNone(self.conv._recent_question(self.now))


class GuideTests(unittest.TestCase):
    """docs/hass/NATURAL_LANGUAGE.md says the same numbers and commands the code uses."""
    DOCS = Path(__file__).resolve().parents[2] / "docs" / "hass"

    def test_the_guide_is_linked_and_states_the_real_question_window(self):
        guide = (self.DOCS / "NATURAL_LANGUAGE.md").read_text("utf-8")
        self.assertIn("](NATURAL_LANGUAGE.md)", (self.DOCS / "README.md").read_text("utf-8"))
        self.assertIn(f"{conversation.RECENT_MINUTES} minutes <!-- conversation.RECENT_MINUTES -->", guide)
        for command in ("`status`", "`undo`", "`no a1b2`", "`yes a1b2`"):
            self.assertIn(command, guide)
        self.assertNotIn("$", guide.replace("`", "").replace("prices", ""))  # no price is promised anywhere on the page


if __name__ == "__main__":
    unittest.main()
