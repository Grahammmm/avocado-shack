"""RF0720-4 tests: hass/margins.py --price P checks the margin a current shelf price gives (unit/sellable cost, price
given, margin_actual, a below-cost line); exactly one of --margin / --price. Pure calculator: no files, no network."""

import json
import unittest

from hass import margins
from hass.tests.test_margins import BASE, run

COST = ["--pack-cost", "24.00", "--units", "12", "--shrink", "5"]
WORKED = ("unit_cost = 24.00 / 12 = 2.00\nsellable_cost = 2.00 / (1 - 5/100) = 2.105263...\nprice = given = {p}\n"
          "margin_actual = ({p} - 2.105263...) / {p} = {m}\n")
BELOW = "below_cost = yes: this price does not cover the cost per sellable unit\n"


def price(value, *extra):
    return run(*COST, "--price", value, *extra)


class PriceCheckTests(unittest.TestCase):
    def test_suggested_price_checks_back_to_computes_own_margin_actual(self):
        expected = margins.compute("24.00", "12", "5", "35")["steps"][-1]["value"]
        self.assertEqual(expected, "35.0%")
        code, out, err = price("3.24")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, WORKED.format(p="3.24", m=expected) + margins.NOTE + "\n")
        r = margins.check("24.00", "12", "5", "3.24")
        self.assertEqual((r["margin_actual_pct"], r["below_cost"], r["price"]), ("35.0", False, "3.24"))
        self.assertEqual([s["name"] for s in r["steps"]], ["unit_cost", "sellable_cost", "price", "margin_actual"])

    def test_below_cost_price_shows_negative_margin_and_line_before_note(self):
        code, out, err = price("2.00")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, WORKED.format(p="2.00", m="-5.3%") + BELOW + margins.NOTE + "\n")
        self.assertTrue(margins.check("24.00", "12", "5", "2.10")["below_cost"])

    def test_price_at_sellable_cost_rounded_up_to_the_cent_is_not_below_cost(self):
        code, out, _ = price("2.11")
        self.assertEqual(code, 0)
        self.assertNotIn("below_cost", out)
        self.assertIn("margin_actual = (2.11 - 2.105263...) / 2.11 = 0.2%\n", out)
        exact = margins.check("3.99", "1", "0", "3.99")  # equal to an exact-cent cost: covered, zero margin
        self.assertEqual((exact["below_cost"], exact["margin_actual_pct"]), (False, "0.0"))

    def test_price_uses_the_pack_cost_cents_rules_naming_price(self):
        refused = {"3.245": "price must be a finite number with at most 2 decimals", "0": "price must be 0.01 to 100000.00",
                   "-1": "price must be 0.01 to 100000.00", "100000.01": "price must be 0.01 to 100000.00",
                   "1_0": "price must be a plain number (digits and one point)", "abc": "price must be a number",
                   "NaN": "price must be a finite number with at most 2 decimals"}
        for bad, msg in refused.items():
            self.assertEqual(price(bad), (2, "", f"margins: error: {msg}\n"), bad)
        code, out, _ = price("1e2")
        self.assertEqual(code, 0)
        self.assertIn("price = given = 100.00\n", out)
        self.assertEqual(price("100000.00")[0], 0)
        self.assertEqual(price("0.01")[0], 0)

    def test_exactly_one_of_margin_or_price_and_round_to_only_with_margin(self):
        cases = [(*BASE, "--price", "3.24"), tuple(COST), (*COST, "--price", "3.24", "--round-to", "0.99"),
                 (*BASE, "--price", "3.24", "--json")]
        for args in cases:
            code, out, err = run(*args)
            self.assertEqual((code, out), (2, ""), args)
            self.assertIn("margins: error: ", err)
        self.assertIn("give --margin or --price, not both", run(*BASE, "--price", "3.24")[2])
        self.assertIn("give --margin or --price, not both", run(*COST)[2])
        self.assertIn("--round-to goes with --margin", run(*COST, "--price", "3.24", "--round-to", "0.99")[2])

    def test_json_has_price_input_and_no_margin_fields(self):
        code, out, _ = price("2.00", "--json")
        self.assertEqual(code, 0)
        r = json.loads(out)
        self.assertEqual(r["inputs"], {"pack_cost": "24.00", "units": "12", "shrink_pct": "5", "price": "2.00"})
        self.assertNotIn("margin_pct", r["inputs"])
        self.assertNotIn("round_to", r["inputs"])
        self.assertIs(r["below_cost"], True)
        self.assertEqual((r["margin_actual_pct"], r["sellable_cost"]), ("-5.3", "2.105263..."))
        self.assertIs(json.loads(price("3.24", "--json")[1])["below_cost"], False)

    def test_margin_path_is_unchanged(self):
        main_text = ("unit_cost = 24.00 / 12 = 2.00\nsellable_cost = 2.00 / (1 - 5/100) = 2.105263...\n"  # main's bytes
                     "price = 2.105263... / (1 - 35/100) = 3.238866...\nsuggested_price = round up to the cent (3.238866...) = 3.24\n"
                     "margin_actual = (3.24 - 2.105263...) / 3.24 = 35.0%\n" + margins.NOTE + "\n")
        self.assertEqual(run(*BASE), (0, main_text, ""))
        code, out, _ = run(*BASE, "--json")
        self.assertEqual(out, json.dumps(margins.compute("24.00", "12", "5", "35"), indent=2) + "\n")
        r = json.loads(out)
        self.assertNotIn("below_cost", r)
        self.assertEqual(list(r), ["inputs", "steps", "unit_cost", "sellable_cost", "price", "margin_actual_pct", "note"])
        self.assertEqual(set(r["inputs"]), {"pack_cost", "units", "shrink_pct", "margin_pct", "round_to"})


if __name__ == "__main__":
    unittest.main()
