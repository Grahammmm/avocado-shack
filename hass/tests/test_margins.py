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


# Run in a child with a small, supported digit limit so the parent runner's global limit is never touched.
OVERSIZED_PROBE = r'''
import json, sys
from decimal import Decimal, getcontext, localcontext, ROUND_DOWN, InvalidOperation
sys.path.insert(0, sys.argv[1])
from hass import margins

limit = sys.get_int_max_str_digits()
out = {"limit": limit, "refusals": [], "text": None, "context": None}
ok = ("24.00", "12", "5", "35")
for sign in (1, -1):
    huge = sign * 10 ** 1000  # built arithmetically, never from giant decimal text
    for i, label in enumerate(("pack cost", "units", "shrink", "margin", "round-to")):
        args = list(ok) + [None]
        args[i if i < 4 else 4] = huge
        try:
            margins.compute(*args[:4], args[4]) if i == 4 else margins.compute(*args[:4])
            out["refusals"].append(["compute", label, sign, "no error", ""])
        except Exception as e:
            out["refusals"].append(["compute", label, sign, type(e).__name__, str(e)])
    for i, label in enumerate(("pack cost", "units", "shrink", "price")):
        args = ["24.00", "12", "5", "3.49"]
        args[i] = huge
        try:
            margins.check(*args)
            out["refusals"].append(["check", label, sign, "no error", ""])
        except Exception as e:
            out["refusals"].append(["check", label, sign, type(e).__name__, str(e)])

try:  # giant digit TEXT keeps its ordinary range refusal
    margins.compute("9" * 1000, "12", "5", "35")
except Exception as e:
    out["text"] = [type(e).__name__, str(e)]

caller = getcontext().copy()
caller.prec, caller.rounding = 5, ROUND_DOWN
caller.clear_flags()
caller.traps[InvalidOperation] = False
before = (caller.prec, caller.rounding, caller.Emin, caller.Emax, dict(caller.flags), dict(caller.traps))
with localcontext(caller):
    try:
        margins.compute("24.00", "12", "5", 10 ** 1000)
    except margins.InputError as e:
        err = str(e)
    cur = getcontext()
    after = (cur.prec, cur.rounding, cur.Emin, cur.Emax, dict(cur.flags), dict(cur.traps))
out["context"] = [before == after, err, margins.compute(*ok)["price"], margins.compute(*ok) == margins.compute("24", "12.0", "5.00", "35.0"),
                  sys.get_int_max_str_digits() == limit]
print(json.dumps(out))
'''


class OversizedIntegerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = subprocess.run([sys.executable, "-B", "-X", "int_max_str_digits=640", "-", str(ROOT)], input=OVERSIZED_PROBE,
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        cls.out = json.loads(p.stdout)

    def test_oversized_integer_compute_refuses_each_field(self):
        rows = [r for r in self.out["refusals"] if r[0] == "compute"]
        self.assertEqual(self.out["limit"], 640)
        self.assertEqual(sorted({r[1] for r in rows}), ["margin", "pack cost", "round-to", "shrink", "units"])
        self.assertEqual(len(rows), 10)  # five fields, positive and negative
        for _, label, sign, kind, msg in rows:
            self.assertEqual((kind, msg), ("InputError", f"{label} must be a number"), (label, sign))

    def test_oversized_integer_check_refuses_each_field(self):
        rows = [r for r in self.out["refusals"] if r[0] == "check"]
        self.assertEqual(sorted({r[1] for r in rows}), ["pack cost", "price", "shrink", "units"])
        self.assertEqual(len(rows), 8)
        for _, label, sign, kind, msg in rows:
            self.assertEqual((kind, msg), ("InputError", f"{label} must be a number"), (label, sign))

    def test_integer_conversion_refusal_preserves_context_and_next_call(self):
        same_context, msg, price, same_result, same_limit = self.out["context"]
        self.assertEqual((same_context, msg, price, same_result, same_limit), (True, "margin must be a number", "3.24", True, True))

    def test_huge_numeric_text_retains_existing_refusal(self):
        self.assertEqual(self.out["text"], ["InputError", "pack cost must be 0.01 to 100000.00"])
        r = margins.compute(24, 12, Decimal("5"), 35, Decimal("0.99"))  # accepted ints and Decimals keep their values
        self.assertEqual((r["price"], r["inputs"]["units"]), ("3.99", "12"))
        self.assertEqual(margins.check(24, 12, 5, "3.49")["price"], "3.49")


if __name__ == "__main__":
    unittest.main()
