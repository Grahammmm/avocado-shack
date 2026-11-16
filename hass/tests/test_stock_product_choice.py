"""AV2007-12 tests: one product named whole is taken before asking which (QA1-06).

Pure helper tests run on a synthetic catalogue; the Conversation tests replay the four recorded bad questions (verbatim, no
model) through the real Conversation, editor and shelf-check flow on the H02 throwaway repo.
Run: python3 -B -m unittest hass.tests.test_stock_product_choice -q
"""

import json
import unittest
from types import SimpleNamespace

from hass import nl_prep
from hass.tests.test_conversation import _ops
from hass.tests.test_shelf_check_flow import Q_SHELF, ShelfCase, Scripted


def prod(pid, name, status="active", brand="", category="fruit", desc=""):
    return {"id": pid, "name": name, "status": status, "brand": brand, "category": category, "description": desc}


CATALOGUE = [prod("p-rasp", "Raspberries", brand="AG Berries"), prod("p-gold", "Golden raspberries"), prod("p-lem", "Lemons"),
             prod("p-lime", "Limes"), prod("p-blue", "Blueberries"), prod("p-pres", "Linn's blueberry preserves", category="pantry"),
             prod("p-held", "Figs", status="held"), prod("p-hid", "Plums", status="hidden")]


def content(products=CATALOGUE):
    return SimpleNamespace(products=list(products), makers={}, community={}, store={})


def op(result):
    [call] = result["ops"]
    return call["op"], call["args"]["id"], call["args"]["available"]


class Helper(unittest.TestCase):
    def test_exact_raspberries_beats_golden_sibling(self):
        for text, available in (("we're out of raspberries", "no"), ("raspberries are back", "yes"), ("Out of raspberries.", "no")):
            for order in (CATALOGUE, CATALOGUE[::-1]):
                got = nl_prep.resolve_stock_choice(text, content(order))
                self.assertEqual(op(got), ("product.set_availability", "p-rasp", available), text)
                self.assertIsNone(got["revises"])

    def test_three_lemon_emoji_are_one_product_not_three(self):
        for text in ("\U0001F34B\U0001F34B\U0001F34B out!!", "\U0001F34B\ufe0f out", "out of \U0001F34B\U0001F34B"):
            self.assertEqual(op(nl_prep.resolve_stock_choice(text, content())), ("product.set_availability", "p-lem", "no"), text)

    def test_typo_only_names_current_catalogue_products(self):
        self.assertEqual(op(nl_prep.resolve_stock_choice("blubereis sold out", content())), ("product.set_availability", "p-blue", "no"))
        got = nl_prep.resolve_stock_choice("blubereis sold out", content([p for p in CATALOGUE if "blue" not in p["id"] and "pres" not in p["id"]]))
        self.assertEqual(got, {"question": nl_prep.NO_PRODUCT})  # the shop does not carry it: no name is offered
        self.assertNotIn("ice cream", json.dumps(got))

    def test_equal_exact_and_fuzzy_matches_still_ask(self):
        twins = [prod("a", "Honey", brand="Linn's"), prod("b", "Honey", brand="Bee Co")]
        got = nl_prep.resolve_stock_choice("honey is sold out", content(twins))
        self.assertEqual(got, {"question": "Which one do you mean: Honey (Linn's) or Honey (Bee Co)?"})
        fuzzy = nl_prep.resolve_stock_choice("peich sold out", content([prod("a", "Peach"), prod("b", "Perch", category="fish")]))
        self.assertIsNone(fuzzy and fuzzy.get("ops"))
        many = [prod(f"m{i}", f"Jam {w}") for i, w in enumerate("apple pear plum fig quince cherry peach lime kiwi mango melon grape".split())]
        got = nl_prep.resolve_stock_choice("jam sold out", content(many))
        self.assertIn("question", got)
        self.assertNotIn("ops", got)

    def test_empty_malformed_negated_partial_requests_fall_through(self):
        for text in ("", "   ", None, 7, "\U0001F34B\U0001F34B", "lemons", "are we out of raspberries?", "we're not out of raspberries",
                     "raspberries are $4 and out", "raspberries sold out tomorrow", "out of raspberries and limes", "raspberries are out and lemons are back",
                     "raspberries are back but limes sold out", "we're out of raspberries for the week", "out of fruit", "raspberries are low",
                     "out of 3 raspberries", "raspberries aren't back", "put it back", "it is back", "that is back"):
            self.assertIsNone(nl_prep.resolve_stock_choice(text, content()), repr(text))

    def test_status_and_alias_boundaries(self):
        figs = nl_prep.resolve_stock_choice("out of figs", content())
        self.assertEqual(figs, {"question": "I can't change Figs right now. It is on hold until someone has looked at it."})
        self.assertEqual(nl_prep.resolve_stock_choice("plums are back", content()), {"question": "Plums is hidden. Do you want me to bring it back first?"})
        alias = [{"name": "rasp", "kind": "product", "id": "p-rasp"}]
        self.assertEqual(op(nl_prep.resolve_stock_choice("rasp sold out", content(), alias)), ("product.set_availability", "p-rasp", "no"))
        stale = [{"name": "rasp", "kind": "product", "id": "gone"}]
        self.assertIsNone(nl_prep.resolve_stock_choice("rasp sold out", content(), stale))

    def test_nothing_is_mutated_and_bad_content_does_not_raise(self):
        c = content()
        before = json.dumps(c.products)
        nl_prep.resolve_stock_choice("out of raspberries", c, [{"name": "rasp", "kind": "product", "id": "p-rasp"}])
        self.assertEqual(json.dumps(c.products), before)
        self.assertIsNone(nl_prep.resolve_stock_choice("out of raspberries", SimpleNamespace(products=None)) and None)

    def test_hints_prefer_the_one_exact_name(self):
        hint = nl_prep.make_hinter(content())("we're out of raspberries", __import__("datetime").date(2026, 11, 2))
        self.assertEqual(hint["products"][0]["is"]["id"], "p-rasp")


RECORDED = {  # verbatim owner text -> the recorded model question the old code relayed (never shown now)
    "we're out of raspberries": "Which raspberries should I mark sold out: the regular ones or the golden ones?",
    "raspberries are back": "Which raspberries are back: the regular ones or the golden ones?",
    "\U0001F34B\U0001F34B\U0001F34B out!!": "Which lemons should I mark sold out: the lemons or the limes?",
    "blubereis sold out": "I don't see a blueberry ice cream on the list. Did you mean the Blueberries, the Linn's blueberry preserves, or a new product?",
}
EXPECT = {"we're out of raspberries": ("photo-product-057", "no"), "raspberries are back": ("photo-product-057", "yes"),
          "\U0001F34B\U0001F34B\U0001F34B out!!": ("photo-product-017", "no"), "blubereis sold out": ("photo-product-058", "no")}


class Real(ShelfCase):
    def setUp(self):
        super().setUp()
        self.interp = Scripted({text: {"question": q} for text, q in RECORDED.items()}, self.asked)
        self.conv = self.open()

    def test_four_recorded_questions_reconcile_in_real_conversation(self):
        for text, (pid, available) in EXPECT.items():
            self.assertEqual(self.say(text), "question", text)
            self.assertEqual(self.replies(), [Q_SHELF], text)  # only the shelf question: never the model's which-one
            self.assertEqual(self.say("yes"), "proposed", text)
            [reply] = self.replies()
            self.assertNotIn("ice cream", reply)
            drafts = self.drafts()
            self.assertEqual(drafts[-1]["state"], "proposed")
            ops = json.loads(drafts[-1]["ops_json"])
            self.assertEqual([(c["op"], c["args"]["id"], c["args"]["available"]) for c in ops if c["op"] == "product.set_availability"], [("product.set_availability", pid, available)], text)
            self.say("no")
            self.replies()
            self.nothing_written()

    def test_checked_shelf_proposes_directly(self):
        self.checked("2026-11-02")
        self.assertEqual(self.say("we're out of raspberries"), "proposed")
        [draft] = self.drafts()
        self.assertEqual([(c["op"], c["args"]) for c in json.loads(draft["ops_json"])], [("product.set_availability", {"id": "photo-product-057", "available": "no"})])
        self.assertEqual(self.commits(), 0)

    def test_errors_pending_refusals_and_skill_modes_unchanged(self):
        self.interp.mapping["out of ideas"] = {"question": "Which ideas?"}
        self.assertEqual(self.say("out of ideas"), "question")  # nothing on the site is named: one plain question, never a made-up name
        self.assertEqual(self.replies(), [nl_prep.NO_PRODUCT])
        self.replies()
        # a text that is not a stock request keeps the model's question
        self.interp.mapping["bananas are green"] = {"question": "Which bananas?"}
        self.assertEqual(self.say("bananas are green"), "question")
        self.assertEqual(self.replies(), ["Which bananas?"])
        self.interp.mapping["raspberries are out"] = {"unsupported": "nope"}  # an explicit unsupported is never reconciled
        self.assertEqual(self.say("raspberries are out"), "unsupported")
        self.nothing_written()

    def test_a_waiting_draft_or_open_request_keeps_the_models_question(self):
        self.interp.mapping["change the hours to nine to five"] = _ops(("store.set_hours", {"hours": ["Monday-Friday 9am-5pm"]}))
        self.checked("2026-11-02")
        self.assertEqual(self.say("change the hours to nine to five"), "proposed")
        self.replies()
        self.assertEqual(self.say("we're out of raspberries"), "question")
        self.assertEqual(self.replies(), [RECORDED["we're out of raspberries"]])

    def test_repeat_delivery_leaves_state_safe(self):
        self.say("we're out of raspberries", pid="dup")
        self.say("we're out of raspberries", pid="dup")
        self.assertEqual(len(self.open_asks()), 1)
        self.nothing_written()
        self.interp.mapping["out of raspberries and limes"] = {"question": "Which?"}
        self.assertEqual(self.say("out of raspberries and limes"), "question")
        self.assertEqual(self.replies()[-1], "Which?")
        self.nothing_written()
