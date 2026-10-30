"""Test-only Hass ops (H02). Passed to the editor through ``registry=``; never in hass.ops."""

from __future__ import annotations

import copy

from hass.ops import Arg, NotFound, Op, Touched


def _set_store_hours(content, args, ctx):
    before = copy.deepcopy(content.store)
    content.store["hours"] = list(args["hours"])
    return [Touched("store", "store", before, copy.deepcopy(content.store))]


def _set_product_description(content, args, ctx):
    for product in content.products:
        if product["id"] == args["id"]:
            before = copy.deepcopy(product)
            product["description"] = args["description"]
            return [Touched("products", args["id"], before, copy.deepcopy(product))]
    return NotFound(args["id"])


OPS = (
    Op("test.set_store_hours", {"hours": Arg("text_list")}, _set_store_hours),
    Op("test.set_product_description", {"id": Arg("id"), "description": Arg("text")}, _set_product_description),
)


def registry():
    return {op.name: op for op in OPS}
