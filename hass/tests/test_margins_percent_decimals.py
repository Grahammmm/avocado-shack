"""RF0720-3 tests: hass/margins.py refuses a --shrink or --margin percentage with more than 2 meaningful decimals,
naming the field, exit 2, nothing on stdout; accepted inputs print byte-identical output to origin/main."""

import json
import unittest

from hass import margins
from hass.tests.test_margins import BASE, run, with_arg

NOTE = "Suggestion only. Prices are not on the site; any price change needs your approval."


def golden(sellable, price_line, rest):  # origin/main output text for BASE with one percentage changed
    return "\n".join(["unit_cost = 24.00 / 12 = 2.00", sellable, price_line, *rest, NOTE]) + "\n"


SELL5 = "sellable_cost = 2.00 / (1 - 5/100) = 2.105263..."
MAIN = {  # captured from origin/main before RF0720-3
    ("--margin", "12.25"): golden(SELL5, "price = 2.105263... / (1 - 12.25/100) = 2.399160...",
                                  ["suggested_price = round up to the cent (2.399160...) = 2.40",
                                   "margin_actual = (2.40 - 2.105263...) / 2.40 = 12.2%"]),
    ("--margin", "5.000"): golden(SELL5, "price = 2.105263... / (1 - 5/100) = 2.216066...",
                                  ["suggested_price = round up to the cent (2.216066...) = 2.22",
                                   "margin_actual = (2.22 - 2.105263...) / 2.22 = 5.1%"]),
    ("--margin", "1e1"): golden(SELL5, "price = 2.105263... / (1 - 10/100) = 2.339181...",
                                ["suggested_price = round up to the cent (2.339181...) = 2.34",
                                 "margin_actual = (2.34 - 2.105263...) / 2.34 = 10.0%"]),
    ("--shrink", "0"): golden("sellable_cost = 2.00 / (1 - 0/100) = 2.00", "price = 2.00 / (1 - 35/100) = 3.076923...",
                              ["suggested_price = round up to the cent (3.076923...) = 3.08",
                               "margin_actual = (3.08 - 2.00) / 3.08 = 35.0%"]),
}


def refused(field):
    return 2, "", f"margins: error: {field} must be a finite number with at most 2 decimals\n"


class PercentDecimalsTests(unittest.TestCase):
    def test_more_than_two_decimals_refused_naming_the_field(self):
        cases = [("--margin", "33.333", "margin"), ("--margin", "33.333333333333333333", "margin"),
                 ("--shrink", "1e-30", "shrink"), ("--shrink", "0.001", "shrink"), ("--shrink", "5.125", "shrink"),
                 ("--margin", "1E-3", "margin"), ("--margin", "12.2500001", "margin")]
        for flag, value, field in cases:
            with self.subTest(flag=flag, value=value):
                self.assertEqual(run(*with_arg(flag, value)), refused(field))
                self.assertEqual(run(*with_arg(flag, value), "--json"), refused(field))  # no JSON on stdout

    def test_long_values_beyond_context_precision_are_not_rounded_before_the_check(self):
        long_bad = "12.25000000000000000000000000001"  # 31 decimals; 28-digit context rounding would make it 12.25
        long_zeros = "12.25" + "0" * 40  # trailing zeros only: still 2 meaningful decimals
        for flag, field in (("--margin", "margin"), ("--shrink", "shrink")):
            with self.subTest(flag=flag, value=long_bad):
                self.assertEqual(run(*with_arg(flag, long_bad)), refused(field))
                self.assertEqual(run(*with_arg(flag, long_bad), "--json"), refused(field))
            with self.subTest(flag=flag, value=long_zeros):
                self.assertEqual(run(*with_arg(flag, long_zeros)), run(*with_arg(flag, "12.25")))
        with self.assertRaises(margins.InputError) as cm:
            margins.compute("24.00", "12", long_bad, "35")
        self.assertEqual(str(cm.exception), "shrink must be a finite number with at most 2 decimals")

    def test_compute_direct_refuses_with_the_same_message(self):
        for shrink, margin, field in (("1e-30", "35", "shrink"), ("5", "33.333", "margin")):
            with self.subTest(field=field), self.assertRaises(margins.InputError) as cm:
                margins.compute("24.00", "12", shrink, margin)
            self.assertEqual(str(cm.exception), f"{field} must be a finite number with at most 2 decimals")

    def test_accepted_inputs_print_byte_identical_output(self):
        for (flag, value), want in MAIN.items():
            with self.subTest(flag=flag, value=value):
                self.assertEqual(run(*with_arg(flag, value)), (0, want, ""))
        self.assertEqual(run(*with_arg("--margin", "5.000")), run(*with_arg("--margin", "5")))
        self.assertEqual(run(*with_arg("--margin", "35.00")), run(*BASE))
        code, out, err = run(*with_arg("--margin", "12.25"), "--json")
        self.assertEqual((code, err), (0, ""))
        data = json.loads(out)
        self.assertEqual((data["inputs"]["margin_pct"], data["price"]), ("12.25", "2.40"))
        self.assertEqual(out, json.dumps(margins.compute("24.00", "12", "5", "12.25"), indent=2) + "\n")

    def test_decimals_checked_before_range_and_plain(self):
        self.assertEqual(run(*with_arg("--margin", "90.001")), refused("margin"))
        self.assertEqual(run(*with_arg("--shrink", "-0.001")), refused("shrink"))
        self.assertEqual(run(*with_arg("--margin", "+33.333")), refused("margin"))
        self.assertEqual(run(*with_arg("--margin", "91")), (2, "", "margins: error: margin must be 0 to 90\n"))
        self.assertEqual(run(*with_arg("--margin", "90.01")), (2, "", "margins: error: margin must be 0 to 90\n"))

    def test_nan_and_infinity_keep_the_finite_message(self):
        for flag, field in (("--margin", "margin"), ("--shrink", "shrink")):
            for value in ("NaN", "inf", "Infinity", "sNaN"):
                with self.subTest(flag=flag, value=value):
                    self.assertEqual(run(*with_arg(flag, value)), (2, "", f"margins: error: {field} must be a finite number\n"))

    def test_pack_cost_and_round_to_untouched(self):
        self.assertEqual(run(*with_arg("--pack-cost", "0.001"))[2],
                         "margins: error: pack cost must be a finite number with at most 2 decimals\n")
        self.assertEqual(run(*BASE, "--round-to", "0.990")[0], 0)


if __name__ == "__main__":
    unittest.main()
