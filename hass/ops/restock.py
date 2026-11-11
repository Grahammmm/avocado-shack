"""AV1109-03 (SKILLS-STOCK-2 part 1): one active product's private restock day, ``restock_on`` (YYYY-MM-DD).

The day is an internal product field: it is never rendered or published. Setting it takes a Pacific day from today
to 60 days ahead (calendar days, from ``ctx.now``); ``clear`` removes the key (never null or blank). Hidden and held
products are refused, as is a request that changes nothing. Undo is the existing whole-product ``history.revert``.
"""

from __future__ import annotations

import copy
from datetime import date

from hass.content_model import shop_today
from hass.ops import Arg, NeedsDetails, Op, Refused
from hass.ops.catalog import _product, _touch

FIELD, MAX_AHEAD = "restock_on", 60


def _set_restock(content, args, ctx):
    clear, day = args.get("clear") is True, args.get(FIELD)
    if clear and day is not None:
        return Refused("give a restock day or clear it, not both")
    if not clear and day is None:
        return NeedsDetails([FIELD], "What day is more coming?")
    product = _product(content, args["id"])
    if not isinstance(product, dict):
        return product
    if product["status"] != "active":
        return Refused(f"{product['id']} is {product['status']}; restore it before setting its restock day")
    if clear and FIELD not in product:
        return Refused(f"{product['id']} has no restock day set; nothing to clear")
    if isinstance(day, str):
        when, today = date.fromisoformat(day), shop_today(ctx.now)  # check_args already proved a real YYYY-MM-DD
        if when < today:
            return Refused(f"{day} is in the past; give a day from today on")
        if (when - today).days > MAX_AHEAD:
            return Refused(f"{day} is more than {MAX_AHEAD} days ahead")
        if product.get(FIELD) == day:
            return Refused(f"{product['id']} already has restock day {day}; nothing to change")
    before = copy.deepcopy(product)
    if clear:
        product.pop(FIELD)
    else:
        product[FIELD] = day
    return _touch("products", product["id"], before, product)


OPS = (
    Op("product.set_restock", {"id": Arg("id"), FIELD: Arg("date", required=False), "clear": Arg("bool", required=False)},
       _set_restock),
)
