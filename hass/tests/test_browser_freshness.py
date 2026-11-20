"""AV1622-04: shelf-check words and the selection line are worked out in the visitor's browser (shop.js, Pacific day).

The real freshness block of storefront-mockup/shop.js runs under Node (hass/tests/freshness_probe.cjs, visitor's zone set
far from Pacific) and is compared with sitegen's own helpers at supplied "today" values.
Run: python3 -B -m unittest hass.tests.test_browser_freshness -v
"""

import copy
import json
import os
import subprocess
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from hass import sitegen
from hass.content_model import load_and_validate, shop_today

ROOT = Path(__file__).resolve().parents[2]
SHOP, PROBE = ROOT / "storefront-mockup" / "shop.js", Path(__file__).with_name("freshness_probe.cjs")
CATALOG, INDEX = sitegen.SITE_PREFIX + "catalog-products.js", sitegen.SITE_PREFIX + "index.html"
CHECK = date(2026, 10, 20)  # a Tuesday
PHONE = "8055550123"


def probe(cases):
    env = {**os.environ, "TZ": "Pacific/Kiritimati"}  # the visitor's own zone must never matter
    done = subprocess.run(["node", str(PROBE), str(SHOP)], input=json.dumps(cases), capture_output=True, text=True,
                          env=env, timeout=60)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


def noon_utc(day: date) -> str:  # a UTC instant that is the same calendar day in Pacific
    return datetime(day.year, day.month, day.day, 20, tzinfo=timezone.utc).isoformat()


def catalog_of(files):
    first, _, rest = files[CATALOG].decode("utf-8").partition("\n")
    return json.loads(first[len("const catalog="):].rstrip(";")), json.loads(rest[len("const catalogFreshness="):].rstrip(";\n"))


def words_of(records, fresh, day: date, ids=None):
    """{product id: the word the page shows} for catalog ``records`` + ``fresh`` metadata opened on Pacific day ``day``."""
    out = probe([{"fn": "refresh", "catalog": records, "freshness": fresh, "now": noon_utc(day), "note": None}])[0]
    return {r["id"]: w for r, w in zip(records, out["availability"]) if ids is None or r["id"] in ids}


def browser_words(files, day: date, ids=None):
    """Same, for generated ``files``."""
    records, fresh = catalog_of(files)
    return words_of(records, fresh, day, ids)


def sel(checked, **extra):
    return {"selection_checked_on": checked.isoformat(), **extra}


class ParityTests(unittest.TestCase):
    def test_constants_equal_sitegen(self):
        got = probe([{"fn": "constants"}])[0]
        self.assertEqual(got, {"stale": sitegen.STALE_AFTER_DAYS, "words": sitegen.AVAILABILITY_WORDS})

    def test_age_zero_seven_eight_parity(self):
        cases, want = [], []
        for phone in (None, PHONE):
            for age in (0, 1, 3, 7, 8, 9, 30):
                today, store = CHECK + timedelta(days=age), sel(CHECK, **({"phone": phone} if phone else {}))
                cases.append({"fn": "selectionLine", "args": [CHECK.isoformat(), today.isoformat(), phone]})
                want.append(sitegen.checked_line(store, today))
                for state in ("yes", "limited", "no"):
                    prod = {"available": state, "available_on": CHECK.isoformat()}
                    cases.append({"fn": "availabilityWord", "args": [state, CHECK.isoformat(), CHECK.isoformat(), today.isoformat()]})
                    want.append(sitegen.availability_label(prod, store, today))
        self.assertEqual(probe(cases), want)
        by_age = {a: probe([{"fn": "availabilityWord", "args": ["yes", "2026-10-20", "2026-10-20", (CHECK + timedelta(days=a)).isoformat()]}])[0]
                  for a in (0, 7, 8)}
        self.assertEqual(by_age, {0: "Available today", 7: "Available today", 8: "Last confirmed Tuesday, October 20"})
        self.assertIn("more than a week ago - call (805) 555-0123 or visit", probe(
            [{"fn": "selectionLine", "args": ["2026-10-20", "2026-10-28", PHONE]}])[0])

    def test_product_day_older_than_store(self):
        old, today = CHECK - timedelta(days=2), CHECK + timedelta(days=1)
        prod, store = {"available": "yes", "available_on": old.isoformat()}, sel(CHECK)
        want = sitegen.availability_label(prod, store, today)
        self.assertEqual(want, "Last confirmed Sunday, October 18")  # a later store check does not refresh an unnamed product
        self.assertEqual(probe([{"fn": "availabilityWord", "args": ["yes", old.isoformat(), CHECK.isoformat(), today.isoformat()]}]), [want])

    def test_pacific_midnight_and_dst(self):
        instants = ["2026-03-08T09:59:59Z", "2026-03-08T10:00:01Z", "2026-03-09T06:59:59Z", "2026-03-09T07:00:01Z",  # spring forward
                    "2026-11-01T06:59:59Z", "2026-11-01T07:00:01Z", "2026-11-02T07:59:59Z", "2026-11-02T08:00:01Z",  # fall back
                    "2028-02-29T07:59:59Z", "2028-02-29T08:00:01Z", "2028-03-01T07:59:59Z", "2026-12-31T23:59:59Z",
                    "2026-07-04T06:59:59Z", "2026-07-04T07:00:00Z"]
        got = probe([{"fn": "pacificDay", "iso": i} for i in instants])
        want = [shop_today(datetime.fromisoformat(i.replace("Z", "+00:00"))).isoformat() for i in instants]
        self.assertEqual(got, want)
        self.assertNotEqual(shop_today(datetime(2026, 7, 4, 6, 59, 59, tzinfo=timezone.utc)), date(2026, 7, 4))  # UTC date differs
        # Day counts across a 23-hour and a 25-hour day and a leap day: the stale test is on whole calendar days.
        for checked, today in ((date(2026, 3, 1), date(2026, 3, 8)), (date(2026, 3, 1), date(2026, 3, 9)),
                               (date(2026, 10, 25), date(2026, 11, 1)), (date(2026, 10, 25), date(2026, 11, 2)),
                               (date(2028, 2, 21), date(2028, 2, 29)), (date(2028, 2, 21), date(2028, 2, 28)),
                               (date(2027, 2, 21), date(2027, 3, 1)), (date(2027, 2, 21), date(2027, 2, 28))):
            with self.subTest(checked=checked, today=today):
                prod = {"available": "limited", "available_on": checked.isoformat()}
                got = probe([{"fn": "availabilityWord", "args": ["limited", checked.isoformat(), checked.isoformat(), today.isoformat()]},
                             {"fn": "selectionLine", "args": [checked.isoformat(), today.isoformat(), None]}])
                self.assertEqual(got, [sitegen.availability_label(prod, sel(checked), today), sitegen.checked_line(sel(checked), today)])

    def test_missing_invalid_and_future_dates(self):
        ok, bad = "2026-10-20", ("", None, "2026-02-30", "2026-13-01", "20261020", "2026-10-20T09:00", 20261020, "2026-1-5", " 2026-10-20")
        cases = []
        for b in bad:
            cases += [{"fn": "selectionLine", "args": [b, "2026-10-21", None]},
                      {"fn": "availabilityWord", "args": ["yes", b, ok, "2026-10-21"]},
                      {"fn": "availabilityWord", "args": ["yes", ok, b, "2026-10-21"]},
                      {"fn": "availabilityWord", "args": ["yes", ok, ok, b]}]
        for state in (None, "", "Yes", "constructor", "toString", "maybe", ["yes"], 1):
            cases.append({"fn": "availabilityWord", "args": [state, ok, ok, "2026-10-21"]})
        cases += [{"fn": "selectionLine", "args": [ok, "2026-10-19", None]},                # store check in the visitor's future
                  {"fn": "availabilityWord", "args": ["yes", ok, ok, "2026-10-19"]},
                  {"fn": "availabilityWord", "args": ["yes", "2026-10-23", ok, "2026-10-22"]}]  # product day after the visitor's today
        self.assertEqual(probe(cases), [None] * len(cases))
        self.assertIsNone(sitegen.availability_label({"available": "yes", "available_on": "2026-10-23"}, sel(CHECK), date(2026, 10, 22)))


class RenderedTests(unittest.TestCase):
    def setUp(self):
        self.content = copy.deepcopy(load_and_validate())
        self.ids = [p["id"] for p in self.content.active_products()[:4]]
        self.content.store["selection_checked_on"] = CHECK.isoformat()
        for pid, state in zip(self.ids, ("yes", "limited", "no")):  # ids[3] has no word
            next(p for p in self.content.products if p["id"] == pid).update({"available": state, "available_on": CHECK.isoformat()})

    def test_old_build_new_browser_clock(self):
        built = sitegen.render(copy.deepcopy(self.content), today=CHECK)
        later = sitegen.render(copy.deepcopy(self.content), today=CHECK + timedelta(days=8))
        self.assertEqual(built[CATALOG], later[CATALOG], "the catalog bytes must not depend on the build date")
        self.assertEqual(built[INDEX].count(b"more than a week"), 0)  # the build-time text is the no-JS fallback
        self.assertEqual(later[INDEX].count(b"more than a week"), 1)
        self.assertIn(b'data-checked-on="2026-10-20"', built[INDEX])
        words = {d: browser_words(built, CHECK + timedelta(days=d), self.ids) for d in (0, 7, 8)}
        fresh = {self.ids[0]: "Available today", self.ids[1]: "Limited", self.ids[2]: "Sold out", self.ids[3]: None}
        self.assertEqual(words[0], fresh)
        self.assertEqual(words[7], fresh)
        stale = "Last confirmed Tuesday, October 20"
        self.assertEqual(words[8], {self.ids[0]: stale, self.ids[1]: stale, self.ids[2]: stale, self.ids[3]: None})
        # the same bytes, opened 8 days on: the paragraph gets the very text a rebuild would give it
        records, fresh_meta = catalog_of(built)
        note = {"checkedOn": "2026-10-20", "phone": None, "text": "build-time text"}
        out = probe([{"fn": "refresh", "catalog": records, "freshness": fresh_meta, "note": note, "now": noon_utc(CHECK + timedelta(days=8))}])[0]
        self.assertEqual(out["note"], sitegen.checked_line(self.content.store, CHECK + timedelta(days=8)))
        self.assertIn("(more than a week ago - call or visit to confirm)", out["note"])
        untouched = probe([{"fn": "refresh", "catalog": records, "freshness": fresh_meta, "note": None, "now": noon_utc(CHECK)}])[0]
        self.assertIsNone(untouched["note"])

    def test_phone_travels_with_the_paragraph(self):
        self.content.store["phone"] = PHONE
        page = sitegen.render(copy.deepcopy(self.content), today=CHECK)[INDEX].decode("utf-8")
        self.assertIn(f'data-checked-on="2026-10-20" data-phone="{PHONE}"', page)
        note = {"checkedOn": "2026-10-20", "phone": PHONE, "text": "x"}
        out = probe([{"fn": "refresh", "catalog": [], "freshness": {"selectionCheckedOn": "2026-10-20"}, "note": note,
                      "now": noon_utc(CHECK + timedelta(days=9))}])[0]
        self.assertEqual(out["note"], sitegen.checked_line(self.content.store, CHECK + timedelta(days=9)))

    def test_stale_available_filter(self):
        files = sitegen.render(copy.deepcopy(self.content), today=CHECK)
        avail = {sitegen.AVAILABILITY_WORDS["yes"], sitegen.AVAILABILITY_WORDS["limited"]}  # shop.js AVAIL is pinned to these
        self.assertEqual({w for w in browser_words(files, CHECK).values() if w in avail}, avail)
        stale_only = browser_words(files, CHECK + timedelta(days=8))
        self.assertFalse([w for w in stale_only.values() if w in avail], "stale records must never pass Available today")
        # mixed: one product re-checked on a later store check stays fresh, the others (older day) are excluded
        later = CHECK + timedelta(days=5)
        self.content.store["selection_checked_on"] = later.isoformat()
        next(p for p in self.content.products if p["id"] == self.ids[0]).update({"available": "yes", "available_on": later.isoformat()})
        mixed = browser_words(sitegen.render(copy.deepcopy(self.content), today=later), later + timedelta(days=1), self.ids)
        self.assertEqual(mixed[self.ids[0]], "Available today")
        self.assertTrue(mixed[self.ids[1]].startswith("Last confirmed "))
        self.assertTrue(mixed[self.ids[2]].startswith("Last confirmed "))

    def test_public_metadata_allowlist(self):
        content = load_and_validate()
        records, fresh = catalog_of(sitegen.render(content, today=CHECK))
        self.assertEqual((len(records), fresh), (len(content.active_products()), {"selectionCheckedOn": None}))
        allowed = set(sitegen.PRODUCT_PUBLIC_FIELDS + sitegen.PRODUCT_OPTIONAL_PUBLIC)
        self.assertTrue(all(set(r) <= allowed for r in records), "unchanged records: no invented checks")
        # with checks recorded: only the two public aliases are added, nothing internal, hidden or held
        hidden = next(p for p in self.content.products if p["id"] == self.ids[0])
        hidden["status"] = "hidden"
        held = next(p for p in self.content.products if p["status"] == "held")
        held.update({"available": "yes", "available_on": CHECK.isoformat()})
        records, fresh = catalog_of(sitegen.render(self.content, today=CHECK))
        self.assertEqual(fresh, {"selectionCheckedOn": "2026-10-20"})
        self.assertTrue(all(set(r) <= allowed | {"availabilityState", "availabilityCheckedOn"} for r in records))
        shown = {r["id"] for r in records}
        self.assertNotIn(hidden["id"], shown)
        self.assertNotIn(held["id"], shown)
        self.assertEqual({r["id"]: (r["availabilityState"], r["availabilityCheckedOn"]) for r in records if "availabilityState" in r},
                         {self.ids[1]: ("limited", "2026-10-20"), self.ids[2]: ("no", "2026-10-20")})
        self.assertFalse(any("availability" in r for r in records), "no finished word is published")
        text = sitegen.render(self.content, today=CHECK)[CATALOG].decode("utf-8")
        for secret in ('"hold"', '"status"', '"available"', '"available_on"', "Available today", "Last confirmed"):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
