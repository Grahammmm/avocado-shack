"""Offline contracts for the natural-language Clover count parser."""
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal, localcontext
from io import StringIO
from unittest.mock import patch

from hass.clover.qty_words import CountIntent, parse
from hass.tests.test_clover_client import NoNetwork


class CountSentenceTests(NoNetwork):
    def assert_intent(self, text, mode, quantity, unit, query):
        actual = parse(text)
        self.assertEqual(actual, CountIntent(mode, Decimal(quantity), unit, query))
        self.assertIsInstance(getattr(actual, "quantity", None), Decimal)

    def test_c1_modes(self):
        # C1: A broad number matcher could conflate an arrival with an absolute count.
        for text, mode in (
            ("there are 30 blue mugs", "count"),
            ("30 of the blue mugs", "count"),
            ("we have 30 blue mugs", "count"),
            ("blue mugs: 30", "count"),
            ("30 blue mugs on the shelf", "count"),
            ("got 30 more blue mugs", "add"),
            ("30 more blue mugs came in", "add"),
            ("received 30 blue mugs", "add"),
            ("set blue mugs to 30", "set"),
        ):
            with self.subTest(text=text):
                self.assert_intent(text, mode, "30", None, "blue mugs")
        self.assertIsNone(parse("blue mugs to 30"))
        self.assertIsNone(parse("30 more blue mugs"))
        self.assertIsNone(parse("set the price of blue mugs to 30"))

    def test_c2_numbers(self):
        # C2: Reading only the first number word or using float/ambient Decimal
        # arithmetic could truncate a compound, fractional weight, or dozen count.
        with localcontext() as context:
            context.prec = 1
            for text, quantity, unit in (
                ("103 eggs", "103", None),
                ("zero eggs", "0", None),
                ("ninety nine eggs", "99", None),
                ("ninety-nine eggs", "99", None),
                ("a dozen eggs", "12", None),
                ("2 dozen eggs", "24", None),
                ("two dozen eggs", "24", None),
                ("3.125 lb eggs", "3.125", "lb"),
                ("2.5 lbs eggs", "2.5", "lb"),
                ("four pounds of eggs", "4", "lb"),
            ):
                with self.subTest(text=text):
                    self.assert_intent(text, "count", quantity, unit, "eggs")
        for text in ("1.2345 lb eggs", "1.5 eggs", "1.5 dozen eggs"):
            with self.subTest(text=text):
                self.assertIsNone(parse(text))

    def test_c3_refuses_vague(self):
        # C3: Searching for a number or cleaning first could turn a hedge, a
        # price, a second count, a question or a second line into a write intent.
        for text in (
            "a few blue mugs", "some blue mugs", "about 30 blue mugs", "30ish blue mugs",
            "30 or so blue mugs", "a case of 12 blue mugs", "-30 blue mugs",
            "$30 blue mugs", "30 dollars of blue mugs", "30 blue mugs and 12 red mugs",
            "30 blue mugs and twelve red mugs", "are there 30 blue mugs?",
            "are there 30 blue mugs", "30 blue mugs?", "30 blue\nmugs",
            "30 blue mugs\n", "30 blue\u2028mugs", "30 " + "m" * 198,
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse(text))
        self.assert_intent("30 " + "m" * 197, "count", "30", None, "m" * 197)

    def test_c4_query_only(self):
        # C4: Leaving articles/filler behind or singularizing the noun would
        # change lookup; a debug print, log or file read would break local purity.
        stdout, stderr = StringIO(), StringIO()
        with (
            redirect_stdout(stdout), redirect_stderr(stderr),
            patch("builtins.open", side_effect=AssertionError("file access")),
            patch("pathlib.Path.open", side_effect=AssertionError("file access")),
            patch("logging.Logger._log", side_effect=AssertionError("logging")),
        ):
            self.assert_intent("  WE HAVE thirty of THE Blue Mugs now!  ", "count", "30", None, "blue mugs")
            self.assert_intent("An Apple: 2", "count", "2", None, "apple")
            self.assert_intent("set the count of the Blue Mugs to seven", "set", "7", None, "blue mugs")
            self.assert_intent("got 2 dozen more eggs", "add", "24", None, "eggs")
            self.assertIsNone(parse("about 30 blue mugs"))
        self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))

    def test_c5_sentence_table(self):
        # C5: A frame-specific change could parse the same quantity correctly in
        # one frame but retain its units/filler or accept ambiguous text in another.
        accepted = (
            ("there are 30 blue mugs", "count", "30", None, "blue mugs"),
            ("30 of the blue mugs", "count", "30", None, "blue mugs"),
            ("we have thirty blue mugs now", "count", "30", None, "blue mugs"),
            ("BLUE MUGS: 30", "count", "30", None, "blue mugs"),
            ("30 blue mugs on the shelf", "count", "30", None, "blue mugs"),
            ("got 2 dozen more eggs", "add", "24", None, "eggs"),
            ("30 more blue mugs came in", "add", "30", None, "blue mugs"),
            ("received 30 blue mugs", "add", "30", None, "blue mugs"),
            ("set blue mugs to 7", "set", "7", None, "blue mugs"),
            ("received a dozen eggs", "add", "12", None, "eggs"),
            ("we received two dozen of the eggs", "add", "24", None, "eggs"),
            ("we have twenty-five tea towels", "count", "25", None, "tea towels"),
            ("twenty one jars on the shelf now", "count", "21", None, "jars"),
            ("there are 0 blue mugs.", "count", "0", None, "blue mugs"),
            ("The stone bowls: ninety-nine", "count", "99", None, "stone bowls"),
            ("we have 2.125 lbs of pears", "count", "2.125", "lb", "pears"),
            ("received 1.5 lb more oats", "add", "1.5", "lb", "oats"),
            ("pears: 6 pounds", "count", "6", "lb", "pears"),
            ("set the count of the oats to 3.25 lb", "set", "3.25", "lb", "oats"),
            ("there is one baker’s basket", "count", "1", None, "baker's basket"),
        )
        refused = (
            "a few blue mugs",
            "some blue mugs",
            "there are about 30 blue mugs",
            "30ish blue mugs",
            "30 or so blue mugs",
            "received a case of 12 blue mugs",
            "we have -30 blue mugs",
            "blue mugs: $30",
            "received 30 dollars",
            "30 blue mugs and 12 red mugs",
            "we have thirty blue mugs and twelve red mugs",
            "are there 30 blue mugs?",
            "can we set blue mugs to 30",
            "30 blue mugs\n12 red mugs",
            "30 " + "x" * 198,
            "set blue mugs to 1.5",
            "received 2.3456 lbs oats",
            "set price of mugs to 12",
            "received 12",
            "received 30 blue mugs and a dozen eggs",
        )
        self.assertEqual((len(accepted), len(refused)), (20, 20))
        for text, *expected in accepted:
            with self.subTest(text=text):
                self.assert_intent(text, *expected)
        for text in refused:
            with self.subTest(text=text):
                self.assertIsNone(parse(text))
