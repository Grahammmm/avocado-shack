"""AVB-24 tests: hass/margins.py turns one purchase line into exact-cent cost and suggested-price steps;
bad inputs exit 2 naming the field. Pure calculator: no files, no content, no network."""

import ast
import contextlib
import io
import json
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path

from hass import margins

ROOT = Path(__file__).resolve().parents[2]
BASE = ["--pack-cost", "24.00", "--units", "12", "--shrink", "5", "--margin", "35"]


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = margins.main(list(args))
        except SystemExit as e:  # argparse usage errors
            code = e.code
    return code, out.getvalue(), err.getvalue()


def with_arg(flag, value):
    args = list(BASE)
    args[args.index(flag) + 1] = value
    return args


class MarginTests(unittest.TestCase):
    def test_worked_example_ceils_to_the_cent_and_shows_every_step(self):
        r = margins.compute("24.00", "12", "5", "35")
        self.assertEqual((r["unit_cost"], r["price"]), ("2.00", "3.24"))
        self.assertTrue(r["sellable_cost"].startswith("2.105263"))
        self.assertGreaterEqual(Decimal(r["margin_actual_pct"]), Decimal("35.0"))
        self.assertEqual(r["margin_actual_pct"], "35.0")
        code, out, err = run(*BASE)
        self.assertEqual((code, err), (0, ""))
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "unit_cost = 24.00 / 12 = 2.00")
        self.assertEqual(lines[1], "sellable_cost = 2.00 / (1 - 5/100) = 2.105263...")
        self.assertEqual(lines[2], "price = 2.105263... / (1 - 35/100) = 3.238866...")
        self.assertEqual(lines[3], "suggested_price = round up to the cent (3.238866...) = 3.24")
        self.assertEqual(lines[4], "margin_actual = (3.24 - 2.105263...) / 3.24 = 35.0%")
        self.assertEqual(lines[-1], margins.NOTE)
        self.assertEqual(lines[-1], "Suggestion only. Prices are not on the site; any price change needs your approval.")

    def test_json_carries_the_same_facts(self):
        code, out, _ = run(*BASE, "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data, margins.compute("24.00", "12", "5", "35"))
        self.assertEqual([s["name"] for s in data["steps"]],
                         ["unit_cost", "sellable_cost", "price", "suggested_price", "margin_actual"])

    def test_zero_shrink_and_zero_margin_price_is_unit_cost(self):
        r = margins.compute("24.00", "12", "0", "0")
        self.assertEqual((r["unit_cost"], r["sellable_cost"], r["price"], r["margin_actual_pct"]),
                         ("2.00", "2.00", "2.00", "0.0"))

    def test_upper_bounds_compute_and_out_of_range_percent_exits_2(self):
        r = margins.compute("100000.00", "1", "90", "90")
        self.assertEqual((r["sellable_cost"], r["price"], r["margin_actual_pct"]), ("1000000.00", "10000000.00", "90.0"))
        for flag, field in (("--margin", "margin"), ("--shrink", "shrink")):
            for bad in ("91", "-1", "90.01"):
                code, out, err = run(*with_arg(flag, bad))
                self.assertEqual((code, out), (2, ""), (flag, bad))
                self.assertIn(f"{field} must be 0 to 90", err)

    def test_bad_units_and_pack_cost_exit_2_naming_the_field(self):
        cases = [("--units", "0", "units"), ("--units", "1.5", "units"), ("--units", "10001", "units"),
                 ("--units", "abc", "units"), ("--pack-cost", "0.001", "pack cost"), ("--pack-cost", "abc", "pack cost"),
                 ("--pack-cost", "NaN", "pack cost"), ("--pack-cost", "Infinity", "pack cost"),
                 ("--pack-cost", "-5.00", "pack cost"), ("--pack-cost", "0", "pack cost"),
                 ("--pack-cost", "100000.01", "pack cost"), ("--margin", "NaN", "margin"), ("--shrink", "sNaN", "shrink")]
        for flag, bad, field in cases:
            code, out, err = run(*with_arg(flag, bad))
            self.assertEqual((code, out), (2, ""), (flag, bad))
            self.assertTrue(err.startswith(f"margins: error: {field} must "), (flag, bad, err))

    def test_missing_input_exits_2(self):
        code, out, _ = run("--pack-cost", "24.00", "--units", "12", "--shrink", "5")
        self.assertEqual((code, out), (2, ""))

    def test_round_to_raises_to_next_ending_and_never_lowers(self):
        self.assertEqual(margins.compute("24.00", "12", "5", "35", "0.99")["price"], "3.99")
        self.assertEqual(margins.compute("24.00", "12", "5", "35", "0.49")["price"], "3.49")
        exact = margins.compute("3.99", "1", "0", "0", "0.99")
        self.assertEqual((exact["price"], exact["steps"][-2]["value"]), ("3.99", "3.99"))
        self.assertEqual(margins.compute("3.50", "1", "0", "0", "0.49")["price"], "4.49")
        code, out, _ = run(*BASE, "--round-to", "0.99")
        self.assertIn("rounded_price = next .99 ending at or above 3.24 = 3.99", out)
        self.assertIn("margin_actual = (3.99 - 2.105263...) / 3.99 = 47.2%", out)
        for bad in ("0.5", "0.50", "1", "abc", "NaN"):
            code, out, err = run(*BASE, "--round-to", bad)
            self.assertEqual((code, out), (2, ""), bad)
            self.assertIn("round-to must be", err)

    def test_equivalent_spellings_give_identical_results_without_exponent_form(self):
        outs = {run(*with_arg("--pack-cost", v))[1] for v in ("24", "24.0", "24.00", "2.4E1")}
        self.assertEqual(len(outs), 1)
        self.assertEqual(len({run(*with_arg("--margin", v))[1] for v in ("35", "35.0", "3.5E1")}), 1)
        tiny = run("--pack-cost", "0.01", "--units", "10000", "--shrink", "50", "--margin", "50", "--json")[1]
        big = run("--pack-cost", "100000", "--units", "1", "--shrink", "0", "--margin", "0")[1]
        for text in (outs.pop(), tiny, big):
            self.assertNotRegex(text, r"\d[eE][+-]?\d")
        self.assertEqual((json.loads(tiny)["unit_cost"], json.loads(tiny)["price"]), ("0.000001", "0.01"))
        self.assertIn("unit_cost = 100000.00 / 1 = 100000.00", big)

    def test_script_runs_directly(self):
        p = subprocess.run([sys.executable, "hass/margins.py", *BASE], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual((p.returncode, p.stdout.splitlines()[-1]), (0, margins.NOTE))

    def test_pure_imports_only_stdlib_and_opens_nothing(self):
        tree = ast.parse(Path(margins.__file__).read_text())
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(mods, {"argparse", "json", "re", "sys", "decimal"})
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertNotIn("open", calls)


if __name__ == "__main__":
    unittest.main()
