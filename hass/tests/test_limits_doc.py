"""AV1537-14 (H25): each number in docs/hass/LIMITS.md equals the code constant its comment names. Stdlib, offline."""
import importlib
import re
import types
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest import mock

from hass import content_model, media

DOC = Path(__file__).resolve().parents[2] / "docs" / "hass" / "LIMITS.md"
SHOP_JS = Path(__file__).resolve().parents[2] / "storefront-mockup" / "shop.js"
CLAIM_RE = re.compile(r"\*\*(\d+)(?: ([A-Za-z]+))?\*\*\s*<!--\s*([\w.]+)\.(\w+)((?:\[\w+\])*)\s*-->")
BOLD_NUMBER_RE = re.compile(r"\*\*\d")
UNITS = {None: 1, "characters": 1, "MB": 2**20, "digits": 1, "dollars": 1}
IMAGE_TYPES = ("jpeg", "jpg", "png", "gif", "webp", "heic", "heif", "tiff", "bmp")
REQUIRED = {"media.MAX_BYTES", "media.MAX_PHOTOS_PER_MESSAGE", "conversation.HISTORY_MAX", "conversation.MEMORY_LIST_MAX", "conversation.ALIAS_LIST_MAX", "conversation.COSTS_LIST_MAX", "ops.catalog.MAX_CANDIDATES",
            "memory.MAX_VALUE", "editor.MAX_OPS", "content_model.MAX_HOURS_LINES", "conversation.MAX_OWNER_TEXT",
            "conversation.FIND_TEXT_MAX", "conversation.ALIAS_NAME_MAX", "content_model.MAX_INTRO",
            "content_model.MAX_HEADLINE_LINE", "content_model.MAX_STORY", "content_model.MAX_NOTICE",
            "content_model.MAX_NOTICE_DAYS", "ops.store.PHONE_DIGITS", "margins.PACK_COST_MAX",
            "margins.UNITS_MIN", "margins.UNITS_MAX", "shop.NEW_BADGE_DAYS", "live_policy.MAX_RECORDS",
            "conversation.AGAIN_WINDOW_DAYS", "conversation.HISTORY_SEARCH_MAX", "conversation.HISTORY_TEXT_MAX",
            "content_model.MAX_CLUB_INTRO"}  # AV0022-15, AV1322-12, AV1222-12, AV1622-11, AV1937-13, AV2152-14


def claims(doc: str) -> list:
    """(line, number, unit, module, name, keys) for every `**<n>[ unit]** <!-- module.NAME[key]... -->` pair."""
    return [(doc.count("\n", 0, m.start()) + 1, int(m[1]), m[2], m[3], m[4], re.findall(r"\[(\w+)\]", m[5]))
            for m in CLAIM_RE.finditer(doc)]


def js_const(source: str, name: str) -> int:
    """The one numeric literal `const NAME = <digits>` in JavaScript text; anything else is a ValueError."""
    found = re.findall(rf"\b(?:const|let|var)\s+{name}\s*=([^;,\n]*)", source)
    if len(found) != 1:
        raise ValueError(f"{len(found)} declarations of {name}")
    if not re.fullmatch(r"\s*\d+\s*", found[0]):
        raise ValueError(f"{name} is not a number literal")
    return int(found[0])


def problems(doc: str, shop_js: str = None) -> list:
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
            if (module, name) == ("shop", "NEW_BADGE_DAYS") and not keys:  # AV1622-11: the one JavaScript source
                value = js_const(SHOP_JS.read_text("utf-8") if shop_js is None else shop_js, name)
            else:
                value = getattr(importlib.import_module(f"hass.{module}"), name)
                for key in keys: value = value[key]
        except (ImportError, AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
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


SHELF_MARK = "content_model.SHELF_LABELS"
SHELF_RE = re.compile(r"- A product is on exactly one shelf: (.+)\. Hass cannot add a shelf\. <!-- content_model\.SHELF_LABELS -->")
SHELVES = ["Fruit", "Vegetables", "Dairy & cheese", "Eggs", "Meat", "Pantry", "Drinks & coffee", "Bread", "Flowers", "General"]  # AV0222-12: the site's filter buttons


def shelf_problems(doc: str) -> list:
    """AV0222-12: the one shelf bullet names every shelf in code order, says one shelf and no new shelf, and the old category size claim is gone."""
    out, lines = [], [ln for ln in doc.splitlines() if SHELF_MARK in ln]
    if len(lines) != 1:
        out.append(f"{len(lines)} lines cite {SHELF_MARK}, not 1")
    elif not (m := SHELF_RE.fullmatch(lines[0].strip())):
        out.append(f"shelf line lacks the exactly-one-shelf and no-new-shelf wording: {lines[0].strip()}")
    else:
        labels = m[1].split(", ")
        if labels != list(content_model.SHELF_LABELS.values()):
            out.append(f"shelves {labels} are not the code's {list(content_model.SHELF_LABELS.values())}")
    if tuple(content_model.SHELF_LABELS) != content_model.CATEGORIES:
        out.append("SHELF_LABELS keys are not CATEGORIES")
    if re.search(r"category \*\*\d+ characters\*\*|TEXT_LIMITS\[product\]\[category\]", doc):
        out.append("old category size claim is still there")
    return out


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
                                       (conversation, "ALIAS_LIST_MAX", 21, "20"),
                                       (conversation, "COSTS_LIST_MAX", 21, "20"),  # AV2137-06
                                       (content_model, "MAX_HOURS_LINES", 8, "7")):
            with self.subTest(name=name), mock.patch.object(mod, name, value):
                source = f"{mod.__name__.removeprefix('hass.')}.{name}"
                self.assertEqual(problems(self.doc), [f"line {lines[name]}: doc says {said}, {source} is {value}"])
        self.assertEqual(conversation.FIND_USAGE, "Tell me a word or two to look for, like \ue000find lion's mane\ue001.")
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

    def test_photo_limit_docs_follow_constant(self):  # AV2152-04
        lines = {c[4]: c[0] for c in claims(self.doc)}
        with mock.patch.object(media, "MAX_PHOTOS_PER_MESSAGE", 5):
            self.assertEqual(problems(self.doc), [f"line {lines['MAX_PHOTOS_PER_MESSAGE']}: doc says 4, media.MAX_PHOTOS_PER_MESSAGE is 5"])
        commands = (DOC.parent / "COMMANDS.md").read_text("utf-8")
        for text in (self.doc, commands):
            self.assertNotRegex(text, r"(?i)one photo per message|one photo at a time")
        self.assertIn("1 to 4 photos per message", commands)
        for wording in ("Each newly accepted photo gets its own code and question", "already waiting, repeated in the same message",
                        "already on a product gets no new draft code"):
            self.assertIn(wording, self.doc)

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

    def test_new_badge_constant_goes_red(self):  # AV1622-11
        line = {c[4]: c[0] for c in claims(self.doc)}["NEW_BADGE_DAYS"]
        source = SHOP_JS.read_text("utf-8")
        self.assertEqual(js_const(source, "NEW_BADGE_DAYS"), 14)
        self.assertEqual(problems(self.doc), [])
        changed = source.replace("const NEW_BADGE_DAYS=14;", "const NEW_BADGE_DAYS=15;")
        self.assertNotEqual(changed, source)
        self.assertEqual(problems(self.doc, changed), [f"line {line}: doc says 14, shop.NEW_BADGE_DAYS is 15"])

    def test_new_badge_source_is_required(self):  # AV1622-11
        self.assertIn("shop.NEW_BADGE_DAYS", {f"{c[3]}.{c[4]}" for c in claims(self.doc)})
        no_claim = re.sub(r"\*\*14\*\* <!-- shop\.NEW_BADGE_DAYS -->", "14", self.doc)
        self.assertNotIn("shop.NEW_BADGE_DAYS", {f"{c[3]}.{c[4]}" for c in claims(no_claim)})
        self.assertEqual(problems(no_claim), [])  # the doc check alone is clean; REQUIRED coverage is what fails
        self.assertFalse(REQUIRED <= {f"{c[3]}.{c[4]}" for c in claims(no_claim)})
        for bad in ("", "const NEW_BADGE_DAYS=14;const NEW_BADGE_DAYS=14;", "const NEW_BADGE_DAYS=7*2;", "const NEW_BADGE_DAYS=days();",
                    "const NEW_BADGE_DAYS=", "const OTHER=14;"):
            with self.subTest(bad=bad):
                self.assertIn("shop.NEW_BADGE_DAYS not found", problems(self.doc, bad)[0])
        self.assertEqual(js_const("const  NEW_BADGE_DAYS = 14 ;", "NEW_BADGE_DAYS"), 14)
        self.assertEqual(problems("**5** <!-- conversation.NO_SUCH -->")[0][:7], "line 1:")
        self.assertIn("not found", problems("**3** <!-- shop.NEW_BADGE_DAYS[x] -->")[0])

    def test_maker_stop_limit_matches_source(self):  # AV1937-13
        from hass import live_policy
        lines = [c[0] for c in claims(self.doc) if (c[3], c[4]) == ("live_policy", "MAX_RECORDS")]
        self.assertEqual(len(lines), 2)  # the live-changes line and the maker-stop line
        self.assertIn("maker", self.doc.splitlines()[lines[-1] - 2] + self.doc.splitlines()[lines[-1] - 1])
        self.assertEqual(problems(self.doc), [])
        with mock.patch.object(live_policy, "MAX_RECORDS", 11):
            self.assertEqual(problems(self.doc), [f"line {n}: doc says 10, live_policy.MAX_RECORDS is 11" for n in lines])

    def test_maker_stop_limit_source_required(self):  # AV1937-13
        no_claim = self.doc.replace("**10** <!-- live_policy.MAX_RECORDS -->", "10")
        self.assertNotIn("live_policy.MAX_RECORDS", {f"{c[3]}.{c[4]}" for c in claims(no_claim)})
        self.assertEqual(problems(no_claim), [])  # the doc check alone is clean; REQUIRED coverage is what fails
        self.assertFalse(REQUIRED <= {f"{c[3]}.{c[4]}" for c in claims(no_claim)})
        self.assertIn("live_policy.MAX_RECORDS", REQUIRED)

    def test_store_undo_wording(self):  # AV2152-11
        section = self.doc.split("## Undoing a store change")[1].split("\n## ")[0]
        self.assertIn("keeps later edits to the other details", section)
        self.assertIn("different value, the undo is refused", section)
        self.assertNotIn("newest", section)

    def test_new_limits_follow_constants_and_require_sources(self):  # AV2152-14
        from hass import conversation
        by = {(c[3], c[4], tuple(c[5])): c for c in claims(self.doc)}
        cases = {("conversation", "AGAIN_WINDOW_DAYS", ()): (conversation, "AGAIN_WINDOW_DAYS", 8, "doc says 7, conversation.AGAIN_WINDOW_DAYS is 8"),
                 ("conversation", "HISTORY_SEARCH_MAX", ()): (conversation, "HISTORY_SEARCH_MAX", 11, "doc says 10, conversation.HISTORY_SEARCH_MAX is 11"),
                 ("conversation", "HISTORY_TEXT_MAX", ()): (conversation, "HISTORY_TEXT_MAX", 61, "doc says 60 characters, conversation.HISTORY_TEXT_MAX is 61"),
                 ("content_model", "MAX_CLUB_INTRO", ()): (content_model, "MAX_CLUB_INTRO", 401, "doc says 400 characters, content_model.MAX_CLUB_INTRO is 401")}
        for key, (module, name, value, said) in cases.items():
            self.assertIn(key, by)
            with mock.patch.object(module, name, value):
                self.assertEqual(problems(self.doc), [f"line {by[key][0]}: {said}"])
            self.assertIn(f"{key[0]}.{key[1]}", REQUIRED)
            line = self.doc.splitlines()[by[key][0] - 1]
            no_claim = self.doc.replace(line, re.sub(r"\*\*(\d+)[^*]*\*\*\s*<!--[^>]*-->", r"\1", line))
            self.assertNotIn(f"{key[0]}.{key[1]}", {f"{c[3]}.{c[4]}" for c in claims(no_claim)})
            self.assertFalse(REQUIRED <= {f"{c[3]}.{c[4]}" for c in claims(no_claim)}, key)
        note = by[("content_model", "TEXT_LIMITS", ("event", "cancelNote"))]
        with mock.patch.dict(content_model.TEXT_LIMITS["event"], {"cancelNote": 161}):
            self.assertEqual(problems(self.doc), [f"line {note[0]}: doc says 160 characters, content_model.TEXT_LIMITS[event][cancelNote] is 161"])
        self.assertIn("one line", self.doc.splitlines()[note[0] - 1])
        no_note = self.doc.replace("<!-- content_model.TEXT_LIMITS[event][cancelNote] -->", "")
        self.assertEqual(problems(no_note), [f"line {note[0]}: bold number without a source comment"])

    def test_again_window_and_named_approval_wording(self):  # AV2152-14
        line = next(l for l in self.doc.splitlines() if "AGAIN_WINDOW_DAYS" in l)
        for text in ("expired text proposal only", "exactly seven days still counts", "website still matches", "new code and expiry",
                     "separate `yes`", "photo draft", "cancelled, replaced or applied", "resuming applies nothing by itself"):
            self.assertIn(text, line)
            self.assertNotIn(text, line.replace(text, ""), text)  # dropping the phrase removes it from the checked line

    def test_notice_first_day_matches_fixed_clock_contract(self):  # AV2152-14
        from hass.ops import OpContext, Refused, load_registry
        prose = self.doc.split("MAX_NOTICE_DAYS -->")[1].split("\n")[0]
        for text in ("first day is today or later, never after its last day", "starts today", "Both days count", "Pacific", "no message is sent"):
            self.assertIn(text, prose)
        self.assertNotRegex(prose, r"\*\*\d")  # relative date rule: no unbound bold number

        def run(first, until, hour=12):
            now = datetime(2026, 11, 17, hour, tzinfo=ZoneInfo("America/Los_Angeles"))  # Pacific noon, 2026-11-17
            args = {"text": "Closed Thanksgiving Day", "until": until, **({"from": first} if first else {})}
            content = types.SimpleNamespace(store={})
            return load_registry()["store.set_notice"].apply(content, args, OpContext(now, content_model.REPO_ROOT, {})), content.store
        for first, until in (("2026-11-16", "2026-11-26"), ("2026-11-27", "2026-11-26"), ("2026-11-17", "2026-11-16")):
            result, store = run(first, until)
            self.assertIsInstance(result, Refused, (first, until))
            self.assertEqual(store, {})
        for first, until in (("2026-11-17", "2026-11-26"), ("2026-11-26", "2026-11-26"), (None, "2026-11-17")):
            result, store = run(first, until)
            self.assertNotIsInstance(result, Refused, (first, until))
            self.assertEqual(store["notice"]["from"], first or "2026-11-17")
        late, _ = run("2026-11-17", "2026-11-17", hour=23)  # still the Pacific 17th late in the evening
        self.assertNotIsInstance(late, Refused)

    def test_shelves_follow_code_and_reject_old_category_size(self):  # AV0222-12
        self.assertEqual(shelf_problems(self.doc), [])
        self.assertEqual(SHELVES, list(content_model.SHELF_LABELS.values()))  # independent literal list against the code table
        bullet = next(ln for ln in self.doc.splitlines() if SHELF_MARK in ln)
        for bad in (self.doc.replace(bullet, ""), self.doc.replace(bullet, bullet + "\n" + bullet),
                    self.doc.replace(" Flowers,", ""), self.doc.replace("General.", "General, Snacking."),
                    self.doc.replace("Eggs, Meat", "Meat, Eggs"), self.doc.replace("Flowers, General", "Flowers, Flowers, General"),
                    self.doc.replace("Hass cannot add a shelf.", ""), self.doc.replace("exactly one shelf", "a shelf"),
                    self.doc.replace("description **600", "category **40 characters** <!-- content_model.TEXT_LIMITS[product][category] -->, description **600", 1)):
            self.assertNotEqual(shelf_problems(bad), [])
        self.assertIn("old category size claim", shelf_problems(self.doc.replace("description **600", "category **40 characters** <!-- x -->, description **600", 1))[0])
        self.assertEqual(uncited_keys(self.doc), [])  # dropping the product category cite leaves the group covered by its other fields
        with mock.patch.dict(content_model.SHELF_LABELS, {"general": "Misc"}):
            self.assertIn("are not the code's", shelf_problems(self.doc)[0])
        with mock.patch.object(content_model, "CATEGORIES", content_model.CATEGORIES[::-1]):
            self.assertIn("SHELF_LABELS keys are not CATEGORIES", shelf_problems(self.doc))

    def test_alias_list_cap_is_required_and_code_bound(self):  # AV0222-12
        from hass import conversation
        line = next(ln for ln in self.doc.splitlines() if "conversation.ALIAS_LIST_MAX" in ln)
        self.assertIn("aliases apart from the notes and says how many more", line)
        self.assertIn("conversation.ALIAS_LIST_MAX", REQUIRED)
        self.assertFalse(REQUIRED <= {f"{c[3]}.{c[4]}" for c in claims(self.doc.replace(line, ""))})
        swapped = self.doc.replace("conversation.ALIAS_LIST_MAX", "conversation.MAX_INTERPRETER_ALIASES")  # the 50-hint cap is a different limit
        self.assertEqual(problems(swapped), [f"line {claims(swapped)[[c[4] for c in claims(swapped)].index('MAX_INTERPRETER_ALIASES')][0]}: doc says 20, conversation.MAX_INTERPRETER_ALIASES is {conversation.MAX_INTERPRETER_ALIASES}"])
        self.assertFalse(REQUIRED <= {f"{c[3]}.{c[4]}" for c in claims(swapped)})
        self.assertTrue(any("conversation.MEMORY_LIST_MAX" in ln and "saved notes" in ln for ln in self.doc.splitlines()))  # notes stay separate
        self.assertIn("conversation.ALIAS_NAME_MAX", self.doc)
