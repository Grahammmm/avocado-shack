"""AV1537-14 (H25): each number in docs/hass/LIMITS.md equals the code constant its comment names. Stdlib, offline."""
import importlib
import re
import unittest
from pathlib import Path
from unittest import mock

from hass import content_model, media

DOC = Path(__file__).resolve().parents[2] / "docs" / "hass" / "LIMITS.md"
CLAIM_RE = re.compile(r"\*\*(\d+)(?: ([A-Za-z]+))?\*\*\s*<!--\s*([\w.]+)\.(\w+)((?:\[\w+\])*)\s*-->")
BOLD_NUMBER_RE = re.compile(r"\*\*\d")
UNITS = {None: 1, "characters": 1, "MB": 2**20, "digits": 1, "dollars": 1}
IMAGE_TYPES = ("jpeg", "jpg", "png", "gif", "webp", "heic", "heif", "tiff", "bmp")
REQUIRED = {"media.MAX_BYTES", "conversation.HISTORY_MAX", "conversation.MEMORY_LIST_MAX", "ops.catalog.MAX_CANDIDATES",
            "memory.MAX_VALUE", "editor.MAX_OPS", "content_model.MAX_HOURS_LINES", "conversation.MAX_OWNER_TEXT",
            "conversation.FIND_TEXT_MAX", "conversation.ALIAS_NAME_MAX", "content_model.MAX_INTRO",
            "content_model.MAX_HEADLINE_LINE", "content_model.MAX_STORY", "content_model.MAX_NOTICE",
            "content_model.MAX_NOTICE_DAYS", "ops.store.PHONE_DIGITS", "margins.PACK_COST_MAX",
            "margins.UNITS_MIN", "margins.UNITS_MAX"}  # AV0022-15, AV1322-12, AV1222-12


def claims(doc: str) -> list:
    """(line, number, unit, module, name, keys) for every `**<n>[ unit]** <!-- module.NAME[key]... -->` pair."""
    return [(doc.count("\n", 0, m.start()) + 1, int(m[1]), m[2], m[3], m[4], re.findall(r"\[(\w+)\]", m[5]))
            for m in CLAIM_RE.finditer(doc)]


def problems(doc: str) -> list:
    """Every disagreement between the doc and the code, one string each (empty when the page is current)."""
    out, paired = [], {m.start() for m in CLAIM_RE.finditer(doc)}
    for m in BOLD_NUMBER_RE.finditer(doc):
        if m.start() not in paired:
            out.append(f"line {doc.count(chr(10), 0, m.start()) + 1}: bold number without a source comment")
    for line, number, unit, module, name, keys in claims(doc):
        source = f"{module}.{name}" + "".join(f"[{k}]" for k in keys)
        if unit not in UNITS:
            out.append(f"line {line}: unknown unit {unit!r} for {source}")
            continue
        try:
            value = getattr(importlib.import_module(f"hass.{module}"), name)
            for key in keys: value = value[key]
        except (ImportError, AttributeError, KeyError, TypeError) as exc:
            out.append(f"line {line}: {source} not found ({exc!r})")
            continue
        if value / UNITS[unit] != number:
            out.append(f"line {line}: doc says {number}{' ' + unit if unit else ''}, {source} is {value}")
    return out


def uncited_keys(doc: str) -> list:
    """TEXT_LIMITS field groups no claim comment cites, so a newly capped group forces a doc line."""
    cited = {keys[0] for _l, _n, _u, module, name, keys in claims(doc)
             if (module, name) == ("content_model", "TEXT_LIMITS") and keys}
    return sorted(set(content_model.TEXT_LIMITS) - cited)


def named_image_types(doc: str) -> set:
    return {t for t in IMAGE_TYPES if re.search(rf"\b{t}\b", doc, re.I)}


def private_text(doc: str) -> list:
    """E-mail addresses, phone numbers, links and file paths an owner page must not carry."""
    pattern = r"@|\d{7,}|\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}|https?://\S*|[\w~.-]*/[\w./-]+|\b\w+\.(?:py|json|sqlite3?|db|md)\b"
    return [m.group(0).strip() for m in re.finditer(pattern, doc, re.M)]


class LimitsDocTest(unittest.TestCase):
    def setUp(self):
        self.doc = DOC.read_text("utf-8")

    def test_every_number_matches_its_constant(self):
        self.assertEqual(problems(self.doc), [])
        sources = {f"{c[3]}.{c[4]}" for c in claims(self.doc)}
        self.assertLessEqual(REQUIRED, sources)

    def test_every_text_limits_group_is_cited(self):
        self.assertEqual(uncited_keys(self.doc), [])

    def test_photo_types_match_media_kinds(self):
        self.assertEqual(named_image_types(self.doc), set(media.KINDS))

    def test_no_private_text(self):
        self.assertEqual(private_text(self.doc), [])

    def test_changed_constant_goes_red(self):
        sample = "Photos up to **20 MB** <!-- media.MAX_BYTES -->."
        self.assertEqual(problems(sample), [])
        with mock.patch.object(media, "MAX_BYTES", 25 * 2**20):
            self.assertEqual(problems(sample), ["line 1: doc says 20 MB, media.MAX_BYTES is 26214400"])
        with mock.patch.object(media, "MAX_BYTES", 20 * 2**20 + 1):  # not a whole number of MB
            self.assertEqual(len(problems(sample)), 1)
        nested = "**80 characters** <!-- content_model.TEXT_LIMITS[product][name] -->"
        with mock.patch.dict(content_model.TEXT_LIMITS["product"], {"name": 90}):
            self.assertIn("is 90", problems(nested)[0])

    def test_new_limits_go_red_and_replies_keep_their_text(self):  # AV0022-15
        from hass import conversation
        lines = {c[4]: c[0] for c in claims(self.doc)}
        for mod, name, value, said in ((conversation, "FIND_TEXT_MAX", 61, "60 characters"),
                                       (conversation, "ALIAS_NAME_MAX", 61, "60 characters"),
                                       (content_model, "MAX_HOURS_LINES", 8, "7")):
            with self.subTest(name=name), mock.patch.object(mod, name, value):
                source = f"{mod.__name__.removeprefix('hass.')}.{name}"
                self.assertEqual(problems(self.doc), [f"line {lines[name]}: doc says {said}, {source} is {value}"])
        self.assertEqual(conversation.FIND_USAGE, "Send find and 1–60 characters, e.g. find lion's mane.")
        self.assertEqual(named_image_types(self.doc), {"jpeg", "png"})
        self.assertIn("upright or sideways", self.doc)

    def test_phone_and_cost_limits_go_red(self):  # AV1222-12
        from hass import margins
        from hass.ops import store
        lines = {c[4]: c[0] for c in claims(self.doc)}
        for mod, name, value, said in ((store, "PHONE_DIGITS", 11, "10 digits"), (margins, "UNITS_MAX", 20000, "10000"),
                                       (margins, "UNITS_MIN", 2, "1"), (margins, "PACK_COST_MAX", 200000, "100000 dollars")):
            with self.subTest(name=name), mock.patch.object(mod, name, value):
                source = f"{mod.__name__.removeprefix('hass.')}.{name}"
                self.assertEqual(problems(self.doc), [f"line {lines[name]}: doc says {said}, {source} is {value}"])
        self.assertEqual(store.PHONE_DIGITS, content_model.PHONE_DIGITS)

    def test_bold_number_without_comment_names_its_line(self):
        self.assertEqual(problems("Intro.\nAt most **7** things."), ["line 2: bold number without a source comment"])
        self.assertEqual(problems("**5** <!-- not a source -->"), ["line 1: bold number without a source comment"])

    def test_bad_unit_or_source_fails(self):
        self.assertIn("unknown unit 'KB'", problems("**20 KB** <!-- media.MAX_BYTES -->")[0])
        self.assertIn("not found", problems("**5** <!-- conversation.NO_SUCH -->")[0])
        self.assertIn("not found", problems("**5** <!-- content_model.TEXT_LIMITS[nope] -->")[0])

    def test_uncited_group_is_named(self):
        doc = self.doc.replace("TEXT_LIMITS[store]", "TEXT_LIMITS[maker]")
        self.assertEqual(uncited_keys(doc), ["store"])

    def test_wording_checks_catch_drift(self):
        self.assertEqual(named_image_types("JPEG, PNG or HEIC"), {"jpeg", "png", "heic"})
        self.assertEqual(private_text("Call 209-555-0100 or a@b.co, see hass/media.py or config.json"),
                         ["209-555-0100", "@", "hass/media.py", "config.json"])
