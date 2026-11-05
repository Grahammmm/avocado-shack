"""AVB-24 (F03): private price and margin calculator (percentages to 2 decimals). One purchase line (pack cost, units,
shrink %, target margin % of price) becomes cost per sellable unit and a suggested price, every step shown, exact
Decimal cents rounded up only at the end. Pure (no file, content or network access); a suggestion only, it never stores or publishes a price.
    python3 hass/margins.py --pack-cost 24.00 --units 12 --shrink 5 [--margin 35 [--round-to 0.99] | --price 3.49] [--json]"""
import argparse
import json
import re
import sys
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, DivisionByZero, InvalidOperation, Overflow, localcontext
from decimal import Decimal as D

PACK_COST_MAX, UNITS_MIN, UNITS_MAX = 100000, 1, 10000  # LIMITS.md cites these
CENT, NOTE = D("0.01"), "Suggestion only. Prices are not on the site; any price change needs your approval."
PLAIN = re.compile(r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)  # no _, +, non-ASCII digits


class InputError(ValueError):  # a bad input; the message names the field
    pass


def _decimal_places(d):  # exact meaningful decimals from the digit tuple; no context rounding, trailing zeros ignored
    _, digits, exp = d.as_tuple()
    sig = "".join(map(str, digits)).rstrip("0")
    return 0 if not sig else max(0, -exp - (len(digits) - len(sig)))


def _num(field, raw, lo, hi, places=None, whole=False, decimals=None):
    try:
        d = D(str(raw).strip())
    except InvalidOperation:
        raise InputError(f"{field} must be a number") from None
    if not d.is_finite() or (whole and d != d.to_integral_value()) or (places and d.as_tuple().exponent < -places):
        kind = "whole number" if whole else "number" + (f" with at most {places} decimals" if places else "")
        raise InputError(f"{field} must be a finite {kind}")
    if decimals is not None and _decimal_places(d) > decimals:  # never quantizes: 5 prints as 5
        raise InputError(f"{field} must be a finite number with at most {decimals} decimals")
    if not PLAIN.fullmatch(str(raw).strip()):
        raise InputError(f"{field} must be a plain number (digits and one point)")
    if not D(lo) <= d <= D(hi):
        raise InputError(f"{field} must be {lo} to {hi}")
    return d.quantize(CENT) if places else d.normalize() + 0  # 24 / 24.0 / 24.00 all give one value


def _show(d):  # plain text, never exponent form: cents when exact to the cent, else 6 places, '...' when inexact
    six = d.quantize(D("0.000001"), ROUND_HALF_EVEN)
    return format(d.quantize(CENT), "f") if d == d.quantize(CENT) else format(six, "f") + ("" if six == d else "...")


def _outer():  # fixed context for validation, formatting and comparisons: never the caller's precision, traps or rounding
    return Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999, capitals=1, clamp=0, flags=[],
                   traps=[InvalidOperation, DivisionByZero, Overflow])


def compute(pack_cost, units, shrink, margin, round_to=None):
    with localcontext(_outer()):  # a copy: the caller's context, settings and flags stay untouched, even on error
        return _compute(pack_cost, units, shrink, margin, round_to)


def _compute(pack_cost, units, shrink, margin, round_to):
    pack = _num("pack cost", pack_cost, "0.01", f"{PACK_COST_MAX}.00", places=2)
    n, s, m = _num("units", units, UNITS_MIN, UNITS_MAX, whole=True), _num("shrink", shrink, 0, 90, decimals=2), _num("margin", margin, 0, 90, decimals=2)
    end = None if round_to is None else _num("round-to", round_to, 0, 1)
    if end is not None and end not in (D("0.49"), D("0.99")):
        raise InputError("round-to must be 0.49 or 0.99")
    with localcontext() as ctx:  # rounding intermediates up keeps each one >= its true value
        ctx.prec, ctx.rounding = 60, ROUND_CEILING
        sellable = (unit := pack / n) / (1 - s / 100)
        price = (raw := sellable / (1 - m / 100)).quantize(CENT, ROUND_CEILING)
        steps = [("unit_cost", f"{_show(pack)} / {n:f}", unit), ("sellable_cost", f"{_show(unit)} / (1 - {s:f}/100)", sellable),
                 ("price", f"{_show(sellable)} / (1 - {m:f}/100)", raw), ("suggested_price", f"round up to the cent ({_show(raw)})", price)]
        if end is not None:  # smallest X.49 / X.99 at or above the price; never lowers it
            ended = (price - end).to_integral_value(ROUND_CEILING) + end
            steps.append(("rounded_price", f"next .{str(end)[-2:]} ending at or above {_show(price)}", ended))
            price = ended
        actual = ((price - sellable) / price * 100).quantize(D("0.1"), ROUND_FLOOR)
    steps = [{"name": a, "expression": b, "value": _show(c)} for a, b, c in steps]
    steps.append({"name": "margin_actual", "expression": f"({_show(price)} - {_show(sellable)}) / {_show(price)}", "value": f"{actual:f}%"})
    return {"inputs": {"pack_cost": _show(pack), "units": f"{n:f}", "shrink_pct": f"{s:f}", "margin_pct": f"{m:f}",
                       "round_to": None if end is None else f"{end:f}"}, "steps": steps, "unit_cost": _show(unit),
            "sellable_cost": _show(sellable), "price": _show(price), "margin_actual_pct": f"{actual:f}", "note": NOTE}


def check(pack_cost, units, shrink, price):  # reverse question: the margin a current shelf price actually gives
    with localcontext(_outer()):
        return _check(pack_cost, units, shrink, price)


def _check(pack_cost, units, shrink, price):
    pack = _num("pack cost", pack_cost, "0.01", f"{PACK_COST_MAX}.00", places=2)
    n, s, p = _num("units", units, UNITS_MIN, UNITS_MAX, whole=True), _num("shrink", shrink, 0, 90, decimals=2), _num("price", price, "0.01", f"{PACK_COST_MAX}.00", places=2)
    with localcontext() as ctx:  # same intermediates and floor as compute's margin_actual
        ctx.prec, ctx.rounding = 60, ROUND_CEILING
        sellable = (unit := pack / n) / (1 - s / 100)
        actual = ((p - sellable) / p * 100).quantize(D("0.1"), ROUND_FLOOR)
    steps = [{"name": a, "expression": b, "value": _show(c)} for a, b, c in (("unit_cost", f"{_show(pack)} / {n:f}", unit),
             ("sellable_cost", f"{_show(unit)} / (1 - {s:f}/100)", sellable), ("price", "given", p))]
    steps.append({"name": "margin_actual", "expression": f"({_show(p)} - {_show(sellable)}) / {_show(p)}", "value": f"{actual:f}%"})
    return {"inputs": {"pack_cost": _show(pack), "units": f"{n:f}", "shrink_pct": f"{s:f}", "price": _show(p)}, "steps": steps,
            "unit_cost": _show(unit), "sellable_cost": _show(sellable), "price": _show(p), "margin_actual_pct": f"{actual:f}",
            "below_cost": p < sellable, "note": NOTE}


def render(r):
    below = ["below_cost = yes: this price does not cover the cost per sellable unit"] if r.get("below_cost") is True else []
    return "\n".join([f"{s['name']} = {s['expression']} = {s['value']}" for s in r["steps"]] + below + [r["note"]])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="margins", description="Private price and margin calculator (suggestion only).")
    for flag in ("--pack-cost", "--units", "--shrink", "--margin", "--round-to", "--price"):
        ap.add_argument(flag, required=flag in ("--pack-cost", "--units", "--shrink"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if (a.margin is None) == (a.price is None):
        ap.error("give --margin or --price, not both")
    if a.price is not None and a.round_to is not None:
        ap.error("--round-to goes with --margin")
    try:
        r = compute(a.pack_cost, a.units, a.shrink, a.margin, a.round_to) if a.price is None else check(a.pack_cost, a.units, a.shrink, a.price)
    except InputError as e:
        print(f"margins: error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if a.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
