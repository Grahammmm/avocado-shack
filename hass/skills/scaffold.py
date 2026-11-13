"""AVB-20: the new-skill scaffolder. One command makes a skill that already passes the lint and the case kit.

    python3 hass/skills/scaffold.py new GROUP.VERB --op OP --label "owner words" [--arg NAME ...] [--say SENTENCE ...]
                                        [--module NAME] [--setup JSON] [--root DIR] [--dry-run]

It writes four files, runs the lint (with the case-file minima) and the 10 case rows through the real kit, and keeps the
files only if all of that passes; otherwise it removes what it wrote and says why. Nothing else is touched: no registry
list, no live file, no network.

    hass/skills/<module>.py                           the skill: one typed op, one pure plan, the refusals
    hass/tests/fixtures/skills/<group>/<name>.jsonl   10 case rows (2+ refusals, 1 undo) and 2 plan rows
    docs/hass/skills/<module>.md                      the doc page: one row per sentence the cases say
    hass/tests/test_skills_<module>.py                lint, case rows and doc page, the same three checks for every skill

The skill wraps ONE registered op whose arguments are product ids (`product.*` only), text, bool, int, date, time or
enum. Anything else (a maker key, a url, a picture, a list, hikes, routes) is written by hand: the command says so.

MACHINE-VALID IS NOT ACCEPTED. The sentences, rules and refusals are placeholders in the owner's voice; the expected
diffs are recorded from a first run on the scratch shop. A person reads every one before the skill is merged, and the new
skill stays `private-only` (no live approval) until the operator lists its op in hass/live_policy.py.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import re
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.content_model import REPO_ROOT  # noqa: E402
from hass.skills import model, testkit  # noqa: E402

SAMPLE_PRODUCTS = (("honey", "photo-product-042"), ("eggs", "photo-product-024"), ("lemons", "photo-product-017"))
HELD_PRODUCT = "photo-product-040"  # on hold in the shop's content: a plan must refuse it
UNKNOWN_PRODUCT = "photo-product-999"
SAMPLES = {"text": ("Picked this morning.", "Made in small batches.", "Kept on the front table."),
           "bool": (True, True, True), "int": (3, 4, 5), "date": ("2026-11-12", "2026-11-13", "2026-11-14"),
           "time": ("09:00", "10:00", "11:00")}
SLOT_KIND = {"text": "text", "bool": "bool", "int": "int", "date": "day", "time": "clock", "enum": "enum"}
NEEDS_STATUS = {"product.restore": "hidden"}  # every other product op needs an active product
ASK_ITEM, NO_PRICE_REPLY = "Which product?", None  # NO_PRICE_REPLY is written into the module, see MODULE
NOTE = "scaffold: placeholder written by hass/skills/scaffold.py; a person reads and replaces it"
MODULE_RE = re.compile(r"[a-z][a-z0-9_]*")


class ScaffoldError(Exception):
    """Something the author must change; the message says what."""


@dataclass
class Spec:
    name: str
    op: str
    label: str
    module: str
    args: dict  # slot name -> op argument name (not the product id)
    kinds: dict  # slot name -> op argument kind
    choices: dict  # slot name -> enum choices
    has_item: bool
    says: list
    summary: str
    setup: list = field(default_factory=list)
    recorded: dict = field(default_factory=dict)

    @property
    def group(self): return self.name.split(".")[0]

    @property
    def verb(self):
        words = self.name.split(".")[1].replace("_", " ")
        return words.split(" ")[0] if self.has_item else words  # "hide_product" -> "hide the honey"

    @property
    def cases(self): return f"hass/tests/fixtures/skills/{self.group}/{self.name}.jsonl"

    def paths(self):
        return {"module": f"hass/skills/{self.module}.py", "cases": self.cases, "doc": f"docs/hass/skills/{self.module}.md",
                "test": f"hass/tests/test_skills_{self.module}.py"}


# -- reading the request ------------------------------------------------------------------------------------------
def _snake(arg): return re.sub(r"(?<=[a-z0-9])([A-Z])", lambda m: "_" + m.group(1).lower(), arg).lower()


def _title(text): return text[:1].upper() + text[1:]


def _typo(sentence):
    """Swap two letters in the longest word (deterministic): a plausible slip for the typo row."""
    words = sentence.split(" ")
    i = max(range(len(words)), key=lambda k: (len(words[k]), -k))
    w = words[i]
    if len(w) >= 4:
        words[i] = w[:1] + w[2] + w[1] + w[3:]
    return " ".join(words)


def build_spec(ns, ops, registry_skills) -> Spec:
    if not model.NAME_RE.fullmatch(ns.name):
        raise ScaffoldError(f"{ns.name!r} must be group.verb in lower case (letters, digits, underscore)")
    if ns.name in {s.name for s in registry_skills}:
        raise ScaffoldError(f"a skill called {ns.name} already exists; names are never reused")
    module = ns.module or ns.name.replace(".", "_")
    if not MODULE_RE.fullmatch(module):
        raise ScaffoldError(f"module name {module!r} must be lower case letters, digits and underscores")
    label = " ".join(ns.label.split())
    if not label or re.search(r"\b[a-z]+\.[a-z_]+\b", label):
        raise ScaffoldError("--label is the skill in the owner's words, never an id like group.verb")
    op = ops.get(ns.op)
    if op is None:
        raise ScaffoldError(f"{ns.op!r} is not a registered op; see `python3 -m hass.ops` or hass/ops/*.py")
    chosen = list(dict.fromkeys(ns.arg or ()))
    for name in chosen:
        if name not in op.args or name == "id":
            raise ScaffoldError(f"--arg {name!r} is not a plain argument of {ns.op} (its arguments: {', '.join(op.args)})")
    wanted = [a for a, spec in op.args.items() if spec.required or a in chosen]
    has_item = "id" in op.args
    if has_item and not ns.op.startswith("product."):
        raise ScaffoldError(f"{ns.op} takes an id that is not a product; the scaffolder covers product ops and plain ops only: write this skill by hand")
    args, kinds, choices = {}, {}, {}
    for a in wanted:
        if a == "id":
            continue
        kind = op.args[a].kind
        if kind not in SLOT_KIND:
            raise ScaffoldError(f"{ns.op} argument {a} is a {kind!r}: the scaffolder does not cover it; write this skill by hand")
        slot = _snake(a)
        args[slot], kinds[slot] = a, kind
        if kind == "enum":
            choices[slot] = tuple(op.args[a].choices or ())
    setup = json.loads(ns.setup) if ns.setup else []
    if not (isinstance(setup, list) and all(isinstance(o, dict) and set(o) == {"op", "args"} for o in setup)):
        raise ScaffoldError("--setup is a JSON list of {\"op\": ..., \"args\": {...}} applied before each draft row")
    verb = ns.name.split(".")[1].replace("_", " ")
    verb = verb.split(" ")[0] if has_item else verb
    if has_item:
        says = list(ns.say or ())[:3] + [f"{verb} the {n}" for n, _ in SAMPLE_PRODUCTS][len(ns.say or ()):3]
    else:
        says = list(ns.say or ())[:3] + [verb, f"please {verb}", f"could you {verb}"][len(ns.say or ()):3]
    summary = ns.summary or f"{_title(label)}. One at a time, after the owner's yes."
    if len(summary) > model.MAX_SUMMARY:
        raise ScaffoldError(f"--summary is over {model.MAX_SUMMARY} characters")
    spec = Spec(ns.name, ns.op, label, module, args, kinds, choices, has_item, says, summary, setup)
    if len(refusal_plan(spec)) < model.MIN_REFUSAL_ROWS:
        raise ScaffoldError(f"{ns.op} has nothing the scaffold can refuse (no product, no text); write this skill by hand")
    taken = {model._fold(t.text): s.name for s in registry_skills for t in s.triggers}
    for t in triggers(spec):
        if model._fold(t.text) in taken:
            raise ScaffoldError(f"the sentence {t.text!r} is already a trigger of {taken[model._fold(t.text)]}; give your own with --say")
    return spec


# -- the rows -----------------------------------------------------------------------------------------------------
def _value(spec, slot, i):
    kind = spec.kinds[slot]
    return spec.choices[slot][i % len(spec.choices[slot])] if kind == "enum" else SAMPLES[kind][i % 3]


def _slots(spec, i, pid=None):
    out = {"item": pid or SAMPLE_PRODUCTS[i % 3][1]} if spec.has_item else {}
    out.update({s: _value(spec, s, i) for s in spec.args})
    return out


def _text(spec, i):
    """The owner's sentence for row i; with a text slot the value is part of it."""
    base = spec.says[i % 3]
    texts = [s for s in spec.args if spec.kinds[s] == "text"]
    return f"{base}: {_value(spec, texts[0], i)}" if texts else base


def draft_setup(spec) -> list:
    """Ops that act on a hidden product start from a shop where the sample products are hidden; --setup replaces that."""
    if spec.setup or NEEDS_STATUS.get(spec.op) != "hidden":
        return spec.setup
    return [{"op": "product.hide", "args": {"id": pid}} for _n, pid in SAMPLE_PRODUCTS]


def ask_for(spec, slot): return f"What should the {slot.replace('_', ' ')} be?"


def refusal_plan(spec) -> list:
    """The refusals this scaffold writes, in order: (code, condition, row slots, setup ops for the row, module constant)."""
    out, texts = [], [s for s in spec.args if spec.kinds[s] == "text"]
    if texts:
        out.append(("price", "the words carry a price", {**_slots(spec, 0), texts[0]: "Only $9 today"}, None, "NO_PRICE"))
    if spec.has_item:
        out.append(("held", "the product is on hold", _slots(spec, 0, HELD_PRODUCT), None, "HELD"))
        if NEEDS_STATUS.get(spec.op) == "hidden":
            out.append(("not_hidden", "the product is not hidden", _slots(spec, 0), None, "NOT_HIDDEN"))
        else:
            hide = [{"op": "product.hide", "args": {"id": SAMPLE_PRODUCTS[2][1]}}]
            out.append(("hidden", "the product is hidden", _slots(spec, 0, SAMPLE_PRODUCTS[2][1]), hide, "HIDDEN"))
        out.append(("unknown", "the product is not in the shop", _slots(spec, 0, UNKNOWN_PRODUCT), None, "UNKNOWN"))
    if texts:
        out.append(("blank", "a required word is blank", {**_slots(spec, 0), texts[0]: "  "}, None, f"ASKS[{texts[0]!r}]"))
    return out[:3]


REFUSAL_NOUN = {"held": "raw milk cheese", "hidden": "lemons", "not_hidden": "honey", "unknown": "plums"}


def _refusal_text(spec, code, slots):
    """The owner's sentence for a refusal row: the same verb, the product the rule is about, the words he gave."""
    base = f"{spec.verb} the {REFUSAL_NOUN[code]}" if code in REFUSAL_NOUN else spec.says[0]
    texts = [s for s in spec.args if spec.kinds[s] == "text"]
    return f"{base}: {slots[texts[0]]}" if texts and code in ("price", "blank") else base


REPLY_WORDS = {"price": "doesn't show prices", "held": "on hold", "hidden": "is hidden", "not_hidden": "is not hidden",
               "unknown": "don't know a product", "blank": "What should the"}


def triggers(spec) -> tuple:
    a, b, c = spec.says
    multi = f"{spec.verb} the honey and the eggs" if spec.has_item else f"{a} and {b}"
    vague = f"{spec.verb} something"
    return (model.Trigger(a), model.Trigger(b), model.Trigger(c), model.Trigger(_typo(a), "typo"),
            model.Trigger(multi, "multi"), model.Trigger(vague, "vague"))


def case_rows(spec, recorded=None) -> list:
    """The 10 case rows and 2 plan rows. ``recorded`` (from the first run) fills the expected diff, files and preview."""
    rec, name, v = recorded or {}, spec.name, 1
    t = triggers(spec)
    first_ask = ASK_ITEM if spec.has_item else ask_for(spec, next(iter(spec.args)))

    def call(slots): return {"skill": name, "slots": slots}

    def draft(rid, kind, texts, replies, slot_sets, **extra):
        got = rec.get(rid, {})
        ops = [op for s in slot_sets for op in plan_ops(spec, s)]
        expect = {"skill": name, "disposition": "proposed", "ops": ops, "diff": got.get("diff", []), "files": got.get("files", []),
                  "preview": got.get("preview", {"kind": "none"})}
        row = {"id": rid, "kind": kind, "version": v, "note": NOTE, "texts": texts, "replies": replies, "expect": expect, **extra}
        if draft_setup(spec): row["setup"] = draft_setup(spec)
        return row

    s0, s1, s2 = _slots(spec, 0), _slots(spec, 1), _slots(spec, 2)
    rows = [draft("s01-clean-1", "clean", [_text(spec, 0)], [call(s0)], [s0], undo=True),
            draft("s02-clean-2", "clean", [_text(spec, 1)], [call(s1)], [s1]),
            draft("s03-typo", "typo", [_typo(_text(spec, 2))], [call(s2)], [s2])]
    if spec.has_item:
        s1 = {**s0, "item": s1["item"]}  # two products, the same words: the claims check reads his one message
        both = {"calls": [call(s0), call(s1)]}
        text = t[4].text + "".join(f": {s0[s]}" for s in spec.args if spec.kinds[s] == "text")
        rows.append(draft("s04-multi-two-products", "multi", [text], [both], [s0, s1]))
    else:
        rows.append(draft("s04-clean-3", "clean", [f"{spec.says[0]} again, please"], [call(s2)], [s2]))
    rows += [
        {"id": "s05-vague", "kind": "vague", "version": v, "note": NOTE, "texts": [t[5].text], "replies": [{"question": first_ask}],
         "expect": {"disposition": "question", "question_contains": first_ask}},
        {"id": "s06-vague-asks-again", "kind": "vague", "version": v, "note": NOTE, "texts": ["can you do something about it"],
         "replies": [{"question": first_ask}], "expect": {"disposition": "question", "question_contains": first_ask}}]
    answer = _text(spec, 0)
    rows.append(draft("s07-turns-question-then-answer", "turns", ["I need a change", answer], [{"question": first_ask}, call(s0)], [s0]))
    rows[-1]["expect"]["dispositions"] = ["question", "proposed"]
    rows[-1]["expect"].pop("disposition")
    for n, (code, why, slots, setup, _const) in enumerate(refusal_plan(spec), 8):
        row = {"id": f"x{n:02d}-refuse-{code.replace('_', '-')}", "kind": "refuse", "version": v, "note": NOTE,
               "texts": [_refusal_text(spec, code, slots)], "replies": [call(slots)],
               "expect": {"skill": name, "disposition": "unsupported", "reply_contains": REPLY_WORDS[code]}}
        if setup: row["setup"] = setup
        rows.append(row)
    for n in range(len(rows), 10):  # a plain op with one refusal still needs 10 rows: more clean variants
        s = _slots(spec, n)
        rows.append(draft(f"s{n + 1:02d}-clean-{n}", "clean", [f"{spec.says[n % 3]} (variant {n})"], [call(s)], [s]))
    rows.append({"id": "plan-ok", "plan": True, "version": v, "skill": name, "slots": s0, "ctx": {"today": "2026-11-08"},
                 "expect_ops": plan_ops(spec, s0)})
    missing = dict(s0)
    drop = "item" if spec.has_item else next(iter(spec.args))
    missing.pop(drop)
    rows.append({"id": "plan-missing-asks", "plan": True, "version": v, "skill": name, "slots": missing, "ctx": {"today": "2026-11-08"},
                 "expect_error": ASK_ITEM if spec.has_item else ask_for(spec, drop)})
    return rows


def plan_ops(spec, slots) -> list:
    args = {"id": slots["item"]} if spec.has_item else {}
    args.update({spec.args[s]: slots[s] for s in spec.args})
    return [{"op": spec.op, "args": args}]


# -- the files ----------------------------------------------------------------------------------------------------
MODULE = '''"""{name} (scaffolded by hass/skills/scaffold.py, AVB-20): {label}. One skill over the typed op ``{op}``.

SCAFFOLD: machine-valid, never accepted. A person reads every sentence below, the case rows in
{cases} and docs/hass/skills/{module}.md before this is merged: the rules, refusals and wording are
placeholders. Authoring guide: docs/hass/SKILLS.md. Wording: docs/hass/VOICE.md.

The plan is a pure function of the slots and an optional ``ctx`` (``ctx.content`` as the loaded content). It writes
nothing: it returns one ``{op}`` call, or raises a ``Refusal`` carrying the sentence the owner is told.
``live_class`` is ``private-only``: the op is not in the live boundary (hass/live_policy.py) until its owner lists it.
"""
from __future__ import annotations

import re

from hass import voice
from hass.content_model import ID_RE
from hass.skills.model import Skill, Slot, Trigger, Undo

OP = {op!r}
HAS_ITEM = {has_item!r}  # a product op: the first slot is the product
NEEDS = {needs!r}  # the product state the op needs: active, or hidden to bring one back
ARGS = {args}  # slot name -> op argument
ASKS = {asks}  # slot name -> the one short question
TEXT_SLOTS = {text_slots}  # words that must not carry a price
ASK_ITEM = "Which product?"
NO_PRICE = "The website doesn't show prices, so I haven't made any change. Could you send it without the price?"
HELD = "I can't change {{name}} right now. It is on hold until someone has looked at it."
HIDDEN = "{{name}} is hidden. Do you want me to bring it back first?"
NOT_HIDDEN = "{{name}} is not hidden, so there is nothing to bring back."
UNKNOWN = "I don't know a product called that. Which product?"
PRICE = re.compile(r"[$]|\\b(?:prices?|costs?|dollars?)\\b", re.IGNORECASE)


class Refusal(ValueError):
    """A plan that cannot go on. ``reply`` is the owner's sentence; ``kind`` is "question" when one answer fixes it."""

    def __init__(self, reply, kind="refuse", backlog=None):
        super().__init__(reply)
        self.reply, self.kind, self.backlog = reply, kind, backlog


def _q(text) -> str:
    return voice.quote(" ".join(str(text).split()))


def _plan(slots, ctx=None) -> list:
    """One ``{op}`` call, or a Refusal. Reads only: nothing is written."""
    slots = slots if isinstance(slots, dict) else {{}}
    args = {{}}
    pid = slots.get("item")
    if HAS_ITEM:
        if not (isinstance(pid, str) and ID_RE.fullmatch(pid)):
            raise Refusal(ASK_ITEM, "question")
        args["id"] = pid
    for slot, arg in ARGS.items():
        value = slots.get(slot)
        if value is None or (isinstance(value, str) and not value.strip()):  # missing or blank: ask, never guess
            raise Refusal(ASKS[slot], "question")
        if slot in TEXT_SLOTS and PRICE.search(value):
            raise Refusal(NO_PRICE)
        args[arg] = value
    content = getattr(ctx, "content", None)
    if HAS_ITEM and content is not None:
        product = next((p for p in getattr(content, "products", ()) if isinstance(p, dict) and p.get("id") == pid), None)
        if product is None:
            raise Refusal(UNKNOWN, "question")
        name, status = _q(product.get("name", "")), product.get("status")
        if status == "held":
            raise Refusal(HELD.format(name=name))
        if NEEDS == "hidden" and status != "hidden":
            raise Refusal(NOT_HIDDEN.format(name=name))
        if NEEDS == "active" and status != "active":
            raise Refusal(HIDDEN.format(name=name))
    return [{{"op": OP, "args": args}}]


{name_const} = Skill(
    name={name!r}, label={label!r}, version=1,
    summary={summary!r},
    triggers=(
{triggers}
    ),
    slots=(
{slots}
    ),
    rules=({rules}),
    plan=_plan, edits=({edits}),
    side_effects=("none",), preview={preview!r}, approval="owner-yes",
    live_class="private-only",  # {op} is not in the live boundary until its owner lists it
    undo=Undo("revert", "none"),
    refuse=(
{refuse}
    ),
    cases={cases!r},
)

SKILLS = ({name_const},)
'''


def _slot_lines(spec):
    lines = []
    if spec.has_item:
        lines.append(f'        Slot("item", "product_ref", required=True, ask=ASK_ITEM),')
    for s in spec.args:
        lines.append(f'        Slot({s!r}, {SLOT_KIND[spec.kinds[s]]!r}, required=True, ask={ask_for(spec, s)!r}),')
    return "\n".join(lines)


def render_module(spec) -> str:
    rec = spec.recorded
    edits = rec.get("edits", ())
    refuse_lines = "\n".join(f"        ({why!r}, {const})," for _c, why, _s, _u, const in refusal_plan(spec))
    rules = [r for r, on in (("no-price-in-words", any(spec.kinds[s] == "text" for s in spec.args)),
                             ("active-product-only" if NEEDS_STATUS.get(spec.op) != "hidden" else "hidden-product-only", spec.has_item),
                             ("held-product-refused", spec.has_item)) if on]
    return MODULE.format(
        name=spec.name, label=spec.label, op=spec.op, cases=spec.cases, module=spec.module, has_item=spec.has_item,
        needs=NEEDS_STATUS.get(spec.op, "active"), args=repr(dict(spec.args)),
        asks=repr({s: ask_for(spec, s) for s in spec.args}), text_slots=repr(tuple(s for s in spec.args if spec.kinds[s] == "text")),
        name_const=spec.name.upper().replace(".", "_"), summary=spec.summary,
        triggers="\n".join(f"        Trigger({t.text!r}{'' if t.tag == 'clean' else f', {t.tag!r}'})," for t in triggers(spec)),
        slots=_slot_lines(spec), rules="".join(f"{r!r}, " for r in rules).rstrip() , edits="".join(f"({f!r}, {p!r}), " for f, p in edits),
        preview=rec.get("skill_preview", "none"), refuse=refuse_lines)


def render_cases(spec) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in case_rows(spec, spec.recorded.get("rows")))


def _outcome(row):
    kind = row["kind"]
    if kind == "refuse":
        return f"Refused in plain words (\"{row['expect']['reply_contains']}...\"). Nothing is written."
    if "question_contains" in row["expect"]:
        return f"Asks \"{row['expect']['question_contains']}\". Nothing is written."
    return "Drafts the change; nothing is written before his `yes <code>`; `undo` puts it back."


def render_doc(spec) -> str:
    rows = [r for r in case_rows(spec, spec.recorded.get("rows")) if "kind" in r]
    table = "\n".join(f"| \"{r['texts'][-1]}\" | {_outcome(r)} |" for r in rows)
    return f"""# {_title(spec.label)}

**SCAFFOLD: a person reads this page, the sentences and the case rows before the skill is merged.** Made by
`hass/skills/scaffold.py` (AVB-20). Machine-valid is not accepted.

Code: `hass/skills/{spec.module}.py` (`{spec.name}`). Cases: `{spec.cases}`. Tests: `hass/tests/test_skills_{spec.module}.py`
and the generic kit tests (`test_skills_plans`, `test_skills_cases`). Authoring guide: `docs/hass/SKILLS.md`. Wording:
`docs/hass/VOICE.md`.

{spec.summary} It plans one `{spec.op}` per request. He says `yes <code>`; nothing is written before his yes, and `undo` (with its own yes)
puts the shop back as it was.

## Phrases it handles

| He says | What happens |
|---|---|
{table}

## Where it stands

`live_class` is `private-only`: `{spec.op}` is in neither live table (`hass/live_policy.py`), so a real draft is refused as "not live"
until the operator lists it. The preview is `{spec.recorded.get('skill_preview', 'none')}`.
"""


def render_test(spec) -> str:
    return f'''"""Scaffolded checks for {spec.name} (hass/skills/scaffold.py): lint, the case rows and the doc page.
Run: python3 -B -m unittest hass.tests.test_skills_{spec.module} -v
"""
import unittest

from hass.content_model import REPO_ROOT
from hass.ops import load_registry
from hass.skills import load_skills, skill_lint, testkit
from hass.skills import {spec.module} as module

SKILL = module.{spec.name.upper().replace(".", "_")}


class Scaffolded(unittest.TestCase):
    def test_registered_and_lint_clean(self):
        self.assertIs(load_skills().get({spec.name!r}), SKILL)
        self.assertEqual(skill_lint([SKILL], load_registry(), repo_root=REPO_ROOT), [])

    def test_every_case_row_passes(self):
        results = testkit.run_file(REPO_ROOT / SKILL.cases, (SKILL,))
        self.assertGreaterEqual(len(results), 10)
        for result in results:
            with self.subTest(row=result.id):
                self.assertEqual(result.problems, [])

    def test_doc_page_names_every_sentence(self):
        doc = (REPO_ROOT / "docs" / "hass" / "skills" / "{spec.module}.md").read_text("utf-8")
        for row in testkit.load_rows(REPO_ROOT / SKILL.cases):
            if "texts" in row:
                self.assertIn(row["texts"][-1], doc)


if __name__ == "__main__":
    unittest.main()
'''


# -- recording the first run ---------------------------------------------------------------------------------------
@contextlib.contextmanager
def _capture(box):
    """Watch the kit's own diff and preview checks, so the expected values come from the real run on the scratch shop."""
    diff_fn, prev_fn = testkit._check_diff, testkit._check_preview

    def diff(expect, files, diff_, chosen, res):
        box["files"], box["diff"] = list(files), copy.deepcopy(diff_)
        return diff_fn(expect, files, diff_, chosen, res)

    def prev(expect, requests, skill, res):
        box["requests"] = copy.deepcopy(requests)
        return prev_fn(expect, requests, skill, res)

    testkit._check_diff, testkit._check_preview = diff, prev
    try:
        yield
    finally:
        testkit._check_diff, testkit._check_preview = diff_fn, prev_fn


def record(spec, path) -> dict:
    """First run: the rows with empty expectations, to read the diff, files and preview the real shop gives."""
    skills = {s.name: s for s in testkit.load_skill_module(path)}
    skill = skills[spec.name]
    out, preview = {}, None
    for row in case_rows(spec):
        if row.get("plan") or row["expect"].get("disposition", "") != "proposed" and "dispositions" not in row["expect"]:
            continue
        box = {}
        with _capture(box):
            res = testkit.run_case_row(copy.deepcopy(row), skills, skill)
        if "diff" not in box or "requests" not in box or not box["requests"]:
            raise ScaffoldError(f"row {row['id']} did not end in a draft ({[f'[{c}] {d}' for c, d in res.problems][:2]}); "
                                "the op needs state the scratch shop lacks: pass --setup, or write this skill by hand")
        last = box["requests"][-1]
        preview = {k: last[k] for k in ("kind", "id") if k in last}
        out.setdefault("rows", {})[row["id"]] = {"diff": box["diff"], "files": box["files"], "preview": preview}
    if not out:
        raise ScaffoldError("no case row ended in a draft; the scaffolder cannot learn what this op changes")
    kinds = {r["preview"]["kind"] for r in out["rows"].values()}
    if kinds == {"product"}:
        out["skill_preview"] = "product:the product"
    elif kinds == {"store"}:
        out["skill_preview"] = "home"
    else:
        raise ScaffoldError(f"the preview requests were {sorted(kinds)}; the scaffolder covers product and home previews only")
    edits = []
    for r in out["rows"].values():
        for e in r["diff"]:
            item = (e["file"], re.sub(r"\[[^\]]+\]", "[id]", e["path"]))
            if item not in edits:
                edits.append(item)
    out["edits"] = tuple(sorted(edits))
    return out


# -- writing, checking, rolling back ---------------------------------------------------------------------------------
def _write(root, spec, written):
    texts = {"module": render_module(spec), "cases": render_cases(spec), "doc": render_doc(spec), "test": render_test(spec)}
    for key, rel in spec.paths().items():
        path = root / rel
        for parent in reversed(path.parents):
            if parent != root and root in parent.parents and not parent.exists():
                written.append(parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(texts[key], encoding="utf-8")
        written.append(path)


def _rollback(written):
    for path in reversed(written):
        try:
            path.unlink() if path.is_file() else path.rmdir()
        except OSError:
            pass


def check(spec, root) -> list:
    """The lint with the case-file minima, the golden plan, and every case row on the scratch shop. [] when all pass."""
    from hass.ops import load_registry
    from hass.skills import skill_lint
    skills = testkit.load_skill_module(root / spec.paths()["module"])
    golden = {spec.name: [r["slots"] for r in case_rows(spec) if r.get("plan") and "expect_ops" in r]}
    problems = skill_lint(skills, load_registry(), repo_root=root, golden=golden)
    for res in testkit.run_file(root / spec.cases, skills):
        problems += [f"{spec.name}: row {res.id}: [{c}] {d}" for c, d in res.problems]
    return problems


def scaffold(ns, out=print) -> int:
    from hass.ops import load_registry
    root = Path(ns.root).resolve() if ns.root else REPO_ROOT
    spec = build_spec(ns, load_registry(), testkit.registry_skills())
    for rel in spec.paths().values():
        if (root / rel).exists():
            raise ScaffoldError(f"{rel} already exists; the scaffolder never overwrites")
    if (root / "hass" / "skills" / f"{spec.module}.py").exists():
        raise ScaffoldError(f"module {spec.module} already exists")
    if ns.dry_run:
        out(f"would write under {root}:")
        for rel in spec.paths().values():
            out(f"  {rel}")
        return 0
    written: list = []
    try:
        _write(root, spec, written)  # first pass: empty expectations, to learn the diff, files and preview
        spec.recorded = record(spec, root / spec.paths()["module"])
        for rel in spec.paths().values():
            (root / rel).unlink()
        _write(root, spec, [])
        problems = check(spec, root)
        if problems:
            raise ScaffoldError("the new skill does not pass its own checks:\n  " + "\n  ".join(problems[:8]))
    except Exception:
        _rollback(written)
        raise
    out(f"scaffolded {spec.name} over {spec.op}: lint clean, {len(case_rows(spec))} rows pass (10 cases, 2 plans)")
    for rel in spec.paths().values():
        out(f"  wrote {rel}")
    out("REVIEW before merge: every sentence, rule and refusal is a placeholder, and the expected diffs were recorded from a")
    out("first run on the scratch shop. Edit the module, the rows and the doc page; then run")
    out(f"  python3 -B -m unittest hass.tests.test_skills_{spec.module} hass.tests.test_skills_cases hass.tests.test_skills_plans")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hass/skills/scaffold.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    new = sub.add_parser("new", help="create a skill, its cases, its doc page and its test")
    new.add_argument("name", help="group.verb, lower case; never reused")
    new.add_argument("--op", required=True, help="the registered op the skill plans")
    new.add_argument("--label", required=True, help="the skill in the owner's words (no group.verb)")
    new.add_argument("--arg", action="append", help="an optional op argument to take as a required slot (repeatable)")
    new.add_argument("--say", action="append", help="an owner sentence for the first rows (up to 3; the rest are written for you)")
    new.add_argument("--summary", help="at most 120 characters")
    new.add_argument("--module", help="module name (default group_verb)")
    new.add_argument("--setup", help="JSON list of {op, args} applied before each draft row")
    new.add_argument("--root", help="write under this folder instead of the repository (the checks still use the real shop content)")
    new.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args(argv)
    try:
        return scaffold(ns)
    except (ScaffoldError, ValueError) as exc:
        print(f"scaffold: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
