"""RF0420-11 tests: hass/margins.py accepts only plain ASCII number text (digits, one point, optional exponent);
underscores, non-ASCII digits and a leading + are refused naming the field, exit 2, nothing on stdout."""

import contextlib
import io
import json
import unittest

from hass import margins

BASE = ["--pack-cost", "24.00", "--units", "12", "--shrink", "5", "--margin", "35"]
# origin/main (before RF0420-11) --json output for BASE + --round-to 0.99, compact form of the exact bytes
GOLDEN = json.loads(
    '{"inputs": {"pack_cost": "24.00", "units": "12", "shrink_pct": "5", "margin_pct": "35", "round_to": "0.99"}, "steps": ['
    '{"name": "unit_cost", "expression": "24.00 / 12", "value": "2.00"}, '
    '{"name": "sellable_cost", "expression": "2.00 / (1 - 5/100)", "value": "2.105263..."}, '
    '{"name": "price", "expression": "2.105263... / (1 - 35/100)", "value": "3.238866..."}, '
    '{"name": "suggested_price", "expression": "round up to the cent (3.238866...)", "value": "3.24"}, '
    '{"name": "rounded_price", "expression": "next .99 ending at or above 3.24", "value": "3.99"}, '
    '{"name": "margin_actual", "expression": "(3.99 - 2.105263...) / 3.99", "value": "47.2%"}], '
    '"unit_cost": "2.00", "sellable_cost": "2.105263...", "price": "3.99", "margin_actual_pct": "47.2", '
    '"note": "Suggestion only. Prices are not on the site; any price change needs your approval."}')


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = margins.main(list(args))
    return code, out.getvalue(), err.getvalue()


def with_arg(flag, value):
    args = list(BASE) + (["--round-to", "0.99"] if flag == "--round-to" else [])
    args[args.index(flag) + 1] = value
    return args


class PlainNumberTests(unittest.TestCase):
    def test_underscore_nonascii_digits_and_plus_refused_naming_the_field(self):
        cases = [("--pack-cost", "2_4.00", "pack cost"), ("--units", "1_2", "units"), ("--margin", "\uff13\uff15", "margin"),
                 ("--shrink", "\u0665", "shrink"), ("--pack-cost", "+24.00", "pack cost"), ("--units", "+12", "units"),
                 ("--round-to", "\uff10.99", "round-to"), ("--round-to", "+0.99", "round-to"), ("--shrink", "\u0665_0", "shrink")]
        for flag, value, field in cases:
            with self.subTest(flag=flag, value=value):
                code, out, err = run(*with_arg(flag, value))
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertEqual(err, f"margins: error: {field} must be a plain number (digits and one point)\n")

    def test_plain_ascii_forms_accepted_with_todays_results(self):
        want = run(*BASE)
        self.assertEqual(want[0], 0)
        for value in ("24", "24.0", " 24.00 ", "2.4E1", "240e-1", "24."):
            with self.subTest(value=value):
                self.assertEqual(run(*with_arg("--pack-cost", value)), want)
        code, out, _ = run(*with_arg("--shrink", ".5"))
        self.assertEqual(code, 0)
        self.assertIn("2.00 / (1 - 0.5/100)", out)

    def test_nan_infinity_and_negative_keep_todays_messages(self):
        for value, msg in (("NaN", "margin must be a finite number"), ("Infinity", "margin must be a finite number"),
                           ("-5.00", "margin must be 0 to 90"), ("-1", "margin must be 0 to 90")):
            with self.subTest(value=value):
                self.assertEqual(run(*with_arg("--margin", value)), (2, "", f"margins: error: {msg}\n"))
        self.assertEqual(run(*with_arg("--pack-cost", "-5.00"))[2], "margins: error: pack cost must be 0.01 to 100000.00\n")

    def test_compute_direct_refuses_underscore_units(self):
        for units in ("1_000", "\uff11\uff12", "+12"):
            with self.subTest(units=units), self.assertRaises(margins.InputError) as cm:
                margins.compute("24.00", units, "5", "35")
            self.assertEqual(str(cm.exception), "units must be a plain number (digits and one point)")

    def test_json_output_for_valid_input_byte_identical_to_today(self):
        code, out, err = run(*BASE, "--round-to", "0.99", "--json")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, json.dumps(GOLDEN, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
