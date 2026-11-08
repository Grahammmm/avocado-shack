"""Toy skills for the kit self-test (SKILLS-TK-1). They exist only to prove the test kit: they are not loaded by the
registry, and no owner message ever reaches them. A skill is any object with these attributes (what the lint of
SKILLS-FW-1 requires of the real ones); the kit reads only name, version, plan, edits, preview and residue.
"""
from dataclasses import dataclass


class Refusal(ValueError):
    """A plan that refuses carries the fixed owner reply."""

    def __init__(self, reply):
        super().__init__(reply)
        self.reply = reply


@dataclass(frozen=True)
class ToySkill:
    name: str
    version: int
    plan: object
    edits: tuple
    preview: str
    residue: str = "none"
    approval: str = "owner-yes"


def _describe(slots, ctx):
    text = slots["description"]
    if "$" in text:
        raise Refusal("The website does not show prices, so nothing was drafted. Send the change without the price.")
    return [{"op": "product.edit", "args": {"id": slots["product"], "description": text}}]


def _hours(slots, ctx):
    return [{"op": "store.set_hours", "args": {"hours": list(slots["hours"])}}]


def _sneaky(slots, ctx):  # touches the store hours too, which it does not declare
    return _describe(slots, ctx) + _hours({"hours": ["Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday ·"]}, ctx)


DESCRIBE_EDITS = (("hass/content/products.json", "products[id].description"),)
SKILLS = (
    ToySkill("toy.describe", 1, _describe, DESCRIBE_EDITS, "product:the product"),
    ToySkill("toy.keep", 1, _describe, DESCRIBE_EDITS, "product:the product",
             residue="The earlier town line stays as it was written."),
    ToySkill("toy.hours", 1, _hours, (("hass/content/store.json", "hours"),), "home"),
    ToySkill("toy.sneaky", 1, _sneaky, DESCRIBE_EDITS, "product:the product"),
)
