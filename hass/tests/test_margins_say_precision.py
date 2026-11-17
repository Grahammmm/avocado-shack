"""RF0511-11 tests: margins.say rounds cost up and profit down to the cent from the calculator's original inputs, not from
the six-decimal display text. Synthetic inputs, in-process, no network. Run: python3 -B -m unittest hass.tests.test_margins_say_precision -v"""

import copy
import unittest
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, Inexact, InvalidOperation, Rounded, getcontext, localcontext
from fractions import Fraction
from math import ceil, floor

from hass import margins

TAIL = "This is only an idea. Prices are not shown on the website, and nothing changes unless you ask."
BOUNDARY = ("9971.01", "9973", "0.02")


def cost_fraction(pack, units, shrink):  # independent oracle: exact rational cost
    return Fraction(pack) / Fraction(units) / (1 - Fraction(shrink) / 100)


def money(c):  # integer cents -> "d.cc" (negative not needed: floor of profit may be < 0 only below cost)
    sign = "-" if c < 0 else ""
    return f"{sign}{abs(c) // 100}.{abs(c) % 100:02d}"


def oracle(r):
    i = r["inputs"]
    cost = cost_fraction(i["pack_cost"], i["units"], i["shrink_pct"])
    paid = money(ceil(cost * 100))
    if r.get("below_cost") is True:
        return f"At ${r['price']} you would lose money: each one costs you about ${paid}. This is only an idea. Nothing changes unless you ask."
    earns = money(floor((Fraction(r["price"]) - cost) * 100))
    return f"Charge ${r['price']}. Each one costs you about ${paid}, so you would earn about ${earns} on each, roughly {r['margin_actual_pct']}%. {TAIL}"


class SayPrecision(unittest.TestCase):
    def test_compute_reply_uses_unrounded_cost_for_cents(self):
        r = margins.compute(*BOUNDARY, "50")
        self.assertEqual(r["price"], "2.01")
        self.assertEqual(margins.say(r), f"Charge $2.01. Each one costs you about $1.01, so you would earn about $1.00 on each, roughly 50.2%. {TAIL}")

    def test_price_check_reply_uses_unrounded_cost_for_profit(self):
        r = margins.check(*BOUNDARY, "2.00")
        self.assertEqual(margins.say(r), f"Charge $2.00. Each one costs you about $1.01, so you would earn about $0.99 on each, roughly 49.9%. {TAIL}")

    def test_below_cost_reply_does_not_erase_subcent_loss(self):
        r = margins.check(*BOUNDARY, "1.00")
        self.assertIs(r["below_cost"], True)
        self.assertEqual(margins.say(r), "At $1.00 you would lose money: each one costs you about $1.01. This is only an idea. Nothing changes unless you ask.")

    def test_boundary_matrix_matches_independent_fraction_cent_oracle(self):
        packs = [BOUNDARY, ("9971.01", "9972", "0.02"), ("0.01", "10000", "0"), ("100000.00", "1", "90"), ("24.00", "12", "5"),
                 ("1.00", "1", "0"), ("100.00", "3", "33.33"), ("3.00", "300", "0.01")]
        for pack, units, shrink in packs:
            for price in ("0.01", "1.00", "2.00", "2.01", "3.24", "100000.00"):
                with self.subTest(kind="check", pack=pack, units=units, shrink=shrink, price=price):
                    r = margins.check(pack, units, shrink, price)
                    self.assertEqual(margins.say(r), oracle(r))
            for margin in ("0", "50", "90"):
                for end in (None, "0.49", "0.99"):
                    with self.subTest(kind="compute", pack=pack, units=units, shrink=shrink, margin=margin, end=end):
                        r = margins.compute(pack, units, shrink, margin, end)
                        self.assertEqual(margins.say(r), oracle(r))

    def test_precision_fix_preserves_context_result_and_ordinary_replies(self):
        hostile = Context(prec=3, rounding=ROUND_FLOOR, Emin=-5, Emax=5, capitals=0, clamp=1, flags=[], traps=[Inexact, Rounded, InvalidOperation])
        results = [margins.compute(*BOUNDARY, "50"), margins.check(*BOUNDARY, "2.00"), margins.check(*BOUNDARY, "1.00"),
                   margins.compute("24.00", "12", "5", "35")]
        want = [margins.say(r) for r in results]
        copies = copy.deepcopy(results)
        with localcontext(hostile) as ctx:
            ctx.clear_flags()
            before = (ctx.prec, ctx.rounding, ctx.Emin, ctx.Emax, ctx.capitals, ctx.clamp, dict(ctx.traps), dict(ctx.flags))
            got = [margins.say(r) for r in results]
            cur = getcontext()
            self.assertEqual((cur.prec, cur.rounding, cur.Emin, cur.Emax, cur.capitals, cur.clamp, dict(cur.traps), dict(cur.flags)), before)
        self.assertEqual(got, want)
        self.assertEqual(results, copies)
        self.assertEqual(want[3], f"Charge $3.24. Each one costs you about $2.11, so you would earn about $1.13 on each, roughly 35.0%. {TAIL}")
        with self.assertRaises(KeyError):
            margins.say({"price": "3.24", "inputs": results[0]["inputs"]})


if __name__ == "__main__":
    unittest.main()
