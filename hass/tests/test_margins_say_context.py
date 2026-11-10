"""RF0844-11 tests: hass/margins.say (the margin chat formatter) ignores and preserves the caller's Decimal context
(precision, rounding, exponent limits, traps, flags), so a valid margin command still queues its reply. Synthetic inputs,
in-process, no network. Run: python3 -B -m unittest hass.tests.test_margins_say_context -v"""

import unittest
from decimal import (ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_UP, Clamped, Context, DivisionByZero, FloatOperation, Inexact,
                     InvalidOperation, Overflow, Rounded, Subnormal, Underflow, getcontext, localcontext)

from hass import margins
from hass.tests import test_conversation, test_status_pause

ALL_SIGNALS = [Clamped, DivisionByZero, Inexact, InvalidOperation, Overflow, Rounded, Subnormal, Underflow, FloatOperation]
TAIL = "This is only an idea. Prices are not shown on the website, and nothing changes unless you ask."
# Literal expected sentences (frozen from the default-context formatter; independent of say run under a hostile context).
SUGGEST = [
    (("24.00", "12", "5", "35"), f"Charge $3.24. Each one costs you about $2.11, so you would earn about $1.13 on each, roughly 35.0%. {TAIL}"),
    (("100000.00", "1", "90", "90"), f"Charge $10000000.00. Each one costs you about $1000000.00, so you would earn about $9000000.00 on each, roughly 90.0%. {TAIL}"),
    (("0.01", "10000", "0", "0"), f"Charge $0.01. Each one costs you about $0.01, so you would earn about $0.00 on each, roughly 99.9%. {TAIL}"),
    (("100.00", "3", "33.33", "12.34"), f"Charge $57.04. Each one costs you about $50.00, so you would earn about $7.04 on each, roughly 12.3%. {TAIL}"),
]
BELOW = [
    (("24.00", "12", "5", "2.00"), "At $2.00 you would lose money: each one costs you about $2.11. This is only an idea. Nothing changes unless you ask."),
    (("100000.00", "1", "90", "0.01"), "At $0.01 you would lose money: each one costs you about $1000000.00. This is only an idea. Nothing changes unless you ask."),
]
SAVED_REPLY = f"Charge $3.24. Each one costs you about $2.11, so you would earn about $1.13 on each, roughly 35.0%. {TAIL}"


def snap(ctx):
    return (ctx.prec, ctx.rounding, ctx.Emin, ctx.Emax, ctx.capitals, ctx.clamp,
            tuple(sorted(k.__name__ for k, v in ctx.traps.items() if v)), tuple(sorted(k.__name__ for k, v in ctx.flags.items() if v)))


def clean():  # an explicit known-good context, independent of the module's own factory
    return Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])


def hostile():
    yield "prec2", Context(prec=2, traps=[InvalidOperation])
    yield "prec4", Context(prec=4, traps=[InvalidOperation, DivisionByZero, Overflow])
    yield "floor", Context(prec=9, rounding=ROUND_FLOOR, traps=[InvalidOperation])
    yield "prec2-up", Context(prec=2, rounding=ROUND_UP, traps=ALL_SIGNALS)
    yield "limits", Context(prec=28, Emin=-8, Emax=8, clamp=1, capitals=0, traps=[InvalidOperation, Overflow])
    yield "trap-inexact", Context(traps=[Inexact])
    yield "trap-rounded", Context(traps=[Rounded])
    yield "trap-both", Context(traps=[Inexact, Rounded])
    yield "all-traps", Context(prec=3, traps=ALL_SIGNALS)
    yield "no-traps", Context(prec=1, traps=[])


def results():  # computed in a clean explicit context by the unchanged compute/check
    with localcontext(clean()):
        return [margins.compute(*a) for a, _ in SUGGEST], [margins.check(*a) for a, _ in BELOW]


class SayContextTests(unittest.TestCase):
    def setUp(self):
        self.suggest, self.below = results()

    def test_say_ignores_precision_rounding_traps_and_exponent_limits(self):
        for name, ctx in hostile():
            with self.subTest(name), localcontext(ctx):
                for r, (_, want) in zip(self.suggest, SUGGEST):
                    self.assertEqual(margins.say(r), want)

    def test_below_cost_say_is_equally_isolated(self):
        for name, ctx in hostile():
            with self.subTest(name), localcontext(ctx):
                for r, (_, want) in zip(self.below, BELOW):
                    self.assertIs(r["below_cost"], True)
                    self.assertEqual(margins.say(r), want)

    def test_say_preserves_caller_context_and_input(self):
        for name, ctx in hostile():
            for preset in (False, True):
                with self.subTest(name, preset=preset), localcontext(ctx) as inner:
                    inner.clear_flags()
                    if preset:
                        inner.flags[Inexact] = inner.flags[Rounded] = inner.flags[Clamped] = True
                    cur, before = getcontext(), snap(inner)
                    rs = self.suggest + self.below
                    copies = [dict(r) for r in rs]
                    for r in rs:
                        margins.say(r)
                        margins.say(r)  # repeated calls stay stable
                    self.assertIs(getcontext(), cur)
                    self.assertEqual(snap(cur), before)
                    self.assertEqual(rs, copies)

    def test_say_exception_restores_context(self):
        good, bad = self.suggest[0], {"price": "3.24"}  # no sellable_cost: the existing KeyError
        garbled = dict(good, price="not a number")  # the existing decimal conversion error
        for name, ctx in hostile():
            with self.subTest(name), localcontext(ctx) as inner:
                inner.clear_flags()
                cur, before = getcontext(), snap(inner)
                with self.assertRaises(KeyError):
                    margins.say(bad)
                self.assertEqual(snap(getcontext()), before)
                with self.assertRaises(ArithmeticError):
                    margins.say(garbled)
                self.assertIs(getcontext(), cur)
                self.assertEqual(snap(cur), before)
                self.assertEqual(margins.say(good), SUGGEST[0][1])  # a later valid call is not poisoned


class MarginHandlerTests(test_status_pause.StoreMixin, test_conversation.ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.conv = self.open()

    def margin(self, text, pid=None):
        self.assertEqual(self.say(text, pid=pid), "margin")
        return self.replies()

    def untouched(self):
        self.assertEqual((self.drafts(), self.approvals(), self.commits(), self.editor.applies), ([], 0, 0, 0))

    def test_margin_handle_queues_reply_under_decimal_trap(self):
        for name, traps in (("rounded", [Rounded]), ("inexact", [Inexact]), ("both", [Inexact, Rounded])):
            with self.subTest(name), localcontext(Context(prec=4, traps=traps)) as inner:
                inner.clear_flags()
                before = snap(inner)
                self.assertEqual(self.margin("margin 24 for 12 at 35% shrink 5%", pid=f"p-{name}"), [SAVED_REPLY])
                self.assertEqual(self.disposition(f"p-{name}"), "margin")
                self.assertEqual(self.say("margin 24 for 12 at 35% shrink 5%", pid=f"p-{name}"), "duplicate")  # the retry
                self.assertEqual(self.replies(), [])
                self.assertEqual(snap(getcontext()), before)
                self.untouched()

    def test_saved_cost_margin_queues_reply_under_decimal_trap(self):
        self.assertEqual(self.say("cost photo-product-001: 24 for 12"), "memory-saved")
        self.replies()
        rows = [tuple(r) for r in self.conv.db.execute("SELECT * FROM memory")]
        with localcontext(Context(prec=3, traps=[Inexact, Rounded])):
            [reply] = self.margin("margin photo-product-001 at 35% shrink 5%", pid="saved-1")
        prefix, _, body = reply.partition("\n")
        self.assertTrue(prefix.startswith("Using the cost you gave me "), prefix)
        self.assertEqual(body, SAVED_REPLY)
        self.assertEqual([tuple(r) for r in self.conv.db.execute("SELECT * FROM memory")], rows)
        self.assertEqual(self.say("margin photo-product-001 at 35% shrink 5%", pid="saved-1"), "duplicate")
        self.assertEqual(self.replies(), [])
        self.untouched()


if __name__ == "__main__":
    unittest.main()
