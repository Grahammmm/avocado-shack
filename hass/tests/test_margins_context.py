"""RF0220-9 tests: hass/margins.py compute/check/main ignore and preserve the caller's Decimal context (precision,
rounding, exponent limits, traps, flags), on success and refusal. Synthetic inputs, in-process, no network."""

import contextlib
import json
import socket
import unittest
from decimal import (ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_UP, Clamped, Context, DivisionByZero, FloatOperation,
                     Inexact, InvalidOperation, Overflow, Rounded, Subnormal, Underflow, getcontext, localcontext)
from unittest import mock

from hass import margins
from hass.tests.test_margins import run

ALL_SIGNALS = [Clamped, DivisionByZero, Inexact, InvalidOperation, Overflow, Rounded, Subnormal, Underflow, FloatOperation]
COMPUTE_CASES = [("24.00", "12", "5", "35", None), ("24.00", "12", "5", "35", "0.99"), ("24.00", "12", "5", "35", "0.49"),
                 ("100000.00", "1", "90", "90", None), ("0.01", "10000", "0", "0", None), ("0.01", "10000", "90", "90", "0.99"),
                 ("100.00", "3", "33.33", "12.34", "0.49")]
CHECK_CASES = [("24.00", "12", "5", "3.24"), ("24.00", "12", "5", "2.00"), ("100000.00", "1", "90", "0.01"),
               ("0.01", "10000", "90", "100000.00")]
CLI_CASES = [("--pack-cost", "24.00", "--units", "12", "--shrink", "5", "--margin", "35"),
             ("--pack-cost", "24.00", "--units", "12", "--shrink", "5", "--margin", "35", "--round-to", "0.99"),
             ("--pack-cost", "24.00", "--units", "12", "--shrink", "5", "--margin", "35", "--round-to", "0.49", "--json"),
             ("--pack-cost", "24.00", "--units", "12", "--shrink", "5", "--price", "3.24"),
             ("--pack-cost", "24.00", "--units", "12", "--shrink", "5", "--price", "2.00", "--json")]
REFUSALS = [(("abc", "12", "5", "35"), "pack cost must be a number"),
            (("24.00", "1_2", "5", "35"), "units must be a plain number (digits and one point)"),
            (("24.00", "12", "\u0665", "35"), "shrink must be a plain number (digits and one point)"),
            (("24.00", "12", "+5", "35"), "shrink must be a plain number (digits and one point)"),
            (("24.00", "12", "5", "NaN"), "margin must be a finite number"),
            (("24.00", "12", "sNaN", "35"), "shrink must be a finite number"),
            (("24.00", "10001", "5", "35"), "units must be 1 to 10000"),
            (("24.00", "12", "5", "91"), "margin must be 0 to 90"),
            (("24.00", "12", "5.001", "35"), "shrink must be a finite number with at most 2 decimals"),
            (("24.00", "12", "5", "35.1234567890123456789012345678901"), "margin must be a finite number with at most 2 decimals")]


def snap(ctx):
    return (ctx.prec, ctx.rounding, ctx.Emin, ctx.Emax, ctx.capitals, ctx.clamp,
            tuple(sorted(k.__name__ for k, v in ctx.traps.items() if v)), tuple(sorted(k.__name__ for k, v in ctx.flags.items() if v)))


def clean():  # an explicit known-good context, independent of the module's own factory
    return Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])


def hostile():
    yield "prec4", Context(prec=4, traps=[InvalidOperation, DivisionByZero, Overflow])
    yield "prec9-floor", Context(prec=9, rounding=ROUND_FLOOR, traps=[InvalidOperation])
    yield "prec2-up", Context(prec=2, rounding=ROUND_UP, traps=ALL_SIGNALS)
    yield "limits", Context(prec=28, Emin=-8, Emax=8, clamp=1, capitals=0, traps=[InvalidOperation, Overflow])
    yield "trap-inexact", Context(traps=[Inexact])
    yield "trap-rounded", Context(traps=[Rounded])
    yield "trap-both", Context(traps=[Inexact, Rounded])
    yield "all-traps", Context(prec=3, traps=ALL_SIGNALS)
    yield "no-traps", Context(prec=1, traps=[])
    preset = Context(prec=6, traps=[Inexact, Rounded])
    yield "preset-flags", preset


def frozen():  # expected results, computed in a clean explicit context before any hostile one is entered
    with localcontext(clean()):
        return ([margins.compute(*c) for c in COMPUTE_CASES], [margins.check(*c) for c in CHECK_CASES],
                [run(*c) for c in CLI_CASES], [_refusal(a) for a, _ in REFUSALS])


def _refusal(args):
    try:
        margins.compute(*args)
    except margins.InputError as e:
        return str(e)
    raise AssertionError("expected a refusal")


class NoNetwork(unittest.TestCase):
    def setUp(self):
        for name in ("socket", "create_connection"):
            p = mock.patch.object(socket, name, side_effect=AssertionError("network used"))
            p.start()
            self.addCleanup(p.stop)
        self.exp = frozen()


class MarginContextTests(NoNetwork):
    def test_frozen_expectations_are_the_known_outputs(self):  # the clean-context expectations are not circular
        compute, check, cli, refusals = self.exp
        self.assertEqual((compute[0]["price"], compute[0]["margin_actual_pct"]), ("3.24", "35.0"))
        self.assertEqual((check[1]["price"], check[1]["margin_actual_pct"], check[1]["below_cost"]), ("2.00", "-5.3", True))
        self.assertEqual(refusals[0], REFUSALS[0][1])
        self.assertEqual([r for _, r in REFUSALS], refusals)
        self.assertEqual(cli[0][0], 0)
        self.assertTrue(cli[0][1].splitlines()[-1] == margins.NOTE)

    def test_compute_and_check_ignore_caller_precision_and_rounding(self):
        compute, check, _, _ = self.exp
        for name, ctx in hostile():
            with self.subTest(name), localcontext(ctx):
                self.assertEqual([margins.compute(*c) for c in COMPUTE_CASES], compute)
                self.assertEqual([margins.check(*c) for c in CHECK_CASES], check)
        for i, end in ((1, "0.99"), (2, "0.49")):  # both price endings are among the compared cases
            self.assertEqual(compute[i]["inputs"]["round_to"], end)
            self.assertTrue(compute[i]["price"].endswith(end[1:]))

    def test_inexact_and_rounded_traps_do_not_escape(self):
        for traps in ([Inexact], [Rounded], [Inexact, Rounded]):
            with self.subTest(traps), localcontext(Context(prec=4, traps=traps)):
                r = margins.compute("24.00", "12", "5", "35")
                self.assertEqual((r["price"], r["margin_actual_pct"]), ("3.24", "35.0"))
                self.assertEqual([s["value"] for s in r["steps"]], ["2.00", "2.105263...", "3.238866...", "3.24", "35.0%"])
                self.assertEqual(r["steps"][1]["expression"], "2.00 / (1 - 5/100)")
                c = margins.check("24.00", "12", "5", "2.00")
                self.assertEqual((c["price"], c["margin_actual_pct"], c["below_cost"]), ("2.00", "-5.3", True))
                self.assertEqual(margins.render(c), margins.render(self.exp[1][1]))
                self.assertIn("below_cost = yes", margins.render(c))

    def test_success_preserves_all_caller_context_state(self):
        for name, ctx in hostile():
            for preset in (False, True):
                with self.subTest(name, preset=preset), localcontext(ctx) as inner:
                    inner.clear_flags()
                    if preset:
                        inner.flags[Inexact] = inner.flags[Rounded] = inner.flags[Clamped] = True
                    cur = getcontext()
                    before = snap(cur)
                    margins.compute("24.00", "12", "5", "35", "0.99")
                    margins.check("24.00", "12", "5", "3.24")
                    run(*CLI_CASES[0])
                    run(*CLI_CASES[4])
                    self.assertIs(getcontext(), cur)
                    self.assertEqual(snap(cur), before)

    def test_invalid_input_preserves_context_and_refusals(self):
        _, _, _, refusals = self.exp
        for name, ctx in hostile():
            with self.subTest(name), localcontext(ctx) as inner:
                inner.clear_flags()
                cur, before = getcontext(), snap(inner)
                for (args, msg), clean_msg in zip(REFUSALS, refusals):
                    with self.assertRaises(margins.InputError) as cm:
                        margins.compute(*args)
                    self.assertEqual((str(cm.exception), snap(getcontext())), (msg, before))
                    self.assertEqual(msg, clean_msg)
                with self.assertRaises(margins.InputError) as cm:
                    margins.check("24.00", "12", "5", "0")
                self.assertEqual(str(cm.exception), "price must be 0.01 to 100000.00")
                with self.assertRaises(margins.InputError):
                    margins.check("24.00", "12", "5.001", "3.24")
                code, out, err = run("--pack-cost", "24.00", "--units", "12", "--shrink", "5.001", "--margin", "35")
                self.assertEqual((code, out, err), (2, "", "margins: error: shrink must be a finite number with at most 2 decimals\n"))
                self.assertIs(getcontext(), cur)
                self.assertEqual(snap(cur), before)

    def test_cli_text_and_json_are_context_independent(self):
        _, _, cli, _ = self.exp
        for name, ctx in hostile():
            with self.subTest(name), localcontext(ctx) as inner:
                inner.clear_flags()
                before = snap(inner)
                for args, expected in zip(CLI_CASES, cli):
                    self.assertEqual(run(*args), expected)
                    bad = run("--pack-cost", "24.00", "--units", "12", "--shrink", "5", "--margin", "95")  # refusal between calls
                    self.assertEqual(bad, (2, "", "margins: error: margin must be 0 to 90\n"))
                    self.assertEqual(run(*args), expected)  # restoration is not a one-shot reset
                self.assertEqual(snap(getcontext()), before)
        self.assertEqual(json.loads(cli[2][1])["steps"][-2]["name"], "rounded_price")

    def test_default_context_output_is_unchanged_and_default_flags_stay_clean(self):
        with localcontext(Context(traps=[])) as ctx:
            ctx.clear_flags()
            margins.compute("24.00", "12", "5", "35")
            margins.check("24.00", "12", "5", "3.24")
            self.assertEqual(snap(ctx)[-1], ())  # no Inexact/Rounded leak into the caller's flags


if __name__ == "__main__":
    unittest.main()
