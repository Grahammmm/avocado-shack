"""Organic badge parity (AV1622-07): shop.js organic() and hass.ops.catalog ORGANIC_NAME_RE/ORGANIC_MAKERS must agree.

The real browser function runs in node:vm (fixtures/shop_organic_driver.cjs); the real Python ``_organic`` runs on
the same synthetic products. Mutation controls use temp-file copies of shop.js outside the checkout.
"""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass.ops import catalog

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "hass" / "tests" / "fixtures" / "shop_organic_driver.cjs"
SHOP = ROOT / "storefront-mockup" / "shop.js"

NAMES = ["organic", "ORGANIC milk", "(organic)", "organically", "nonorganic", "organic2", "organic_",
         "\u00e9organic", "organic\u00e9", "", "Organic-Valley", "an organic. bar", "Sea Salt"]
NEAR_MISS_MAKERS = ["ocean ranch", "Straus ", " Straus", "STRAUS", "Straus Family", "Nobody", "", None]


def run_driver(products, shop_path=None, timeout=60, driver=DRIVER):
    """Run the node driver once; any failure (node missing, nonzero, bad JSON, timeout) raises."""
    cmd = ["node", str(driver), json.dumps(products)] + ([str(shop_path)] if shop_path else [])
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    out = json.loads(done.stdout)
    if len(out["results"]) != len(products):
        raise AssertionError("driver returned the wrong number of results")
    return out


def python_results(products, regex=None, makers=None):
    """The real catalog._organic on each product, optionally with the rule inputs swapped (mutation controls)."""
    with mock.patch.object(catalog, "ORGANIC_NAME_RE", regex or catalog.ORGANIC_NAME_RE), \
            mock.patch.object(catalog, "ORGANIC_MAKERS", makers if makers is not None else catalog.ORGANIC_MAKERS):
        return [catalog._organic(p) for p in products]


def product(name="Sea Salt", key="Nobody", **extra):
    p = {"name": name, **extra}
    if key is not ...:
        p["producerKey"] = key
    return p


def probes(js_makers):
    """Synthetic products covering names, every maker in either rule, near-miss makers and non-signal fields."""
    out = [product(n) for n in NAMES]
    out += [product(n, m) for n in ("Sea Salt", "organic nuts") for m in sorted(set(js_makers) | set(catalog.ORGANIC_MAKERS))]
    out += [product("Sea Salt", m) for m in NEAR_MISS_MAKERS]
    out += [product("Sea Salt", ...), product("Sea Salt", None)]
    out += [product("Sea Salt", description="organic", displayBrand="Organic", brand="Straus"),
            product("Sea Salt", "Nobody", brand="Straus", displayBrand="Straus")]
    return out


def drift(js_out, items, regex=None, makers=None):
    """Names every disagreement between the JS rule/results and the (possibly mutated) Python rule."""
    regex = regex or catalog.ORGANIC_NAME_RE
    makers = tuple(makers if makers is not None else catalog.ORGANIC_MAKERS)
    rule, found = js_out["rule"], []
    if rule["source"] != regex.pattern:
        found.append(f"rule:name-regex-source js={rule['source']!r} py={regex.pattern!r}")
    if rule["flags"] != "i" or regex.flags != (re.ASCII | re.IGNORECASE):
        found.append(f"rule:flags js={rule['flags']!r} py={regex.flags!r}")
    if sorted(rule["makers"]) != sorted(makers) or len(set(rule["makers"])) != len(rule["makers"]) \
            or len(set(makers)) != len(makers):
        found.append(f"rule:makers js={rule['makers']!r} py={list(makers)!r}")
    for p, js in zip(items, js_out["results"]):
        if js != python_results([p], regex, makers)[0]:
            found.append(f"probe:{p['name']!r}/{p.get('producerKey', '<absent>')!r} js={js}")
    return found


class OrganicSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.shop_text = SHOP.read_text(encoding="utf-8")
        cls.baseline = run_driver([product()])["rule"]

    def mutated_shop(self, old, new, name="shop.js"):
        self.assertEqual(self.shop_text.count(old), 1, f"mutation anchor {old!r} must appear exactly once")
        path = Path(self.tmp.name) / name
        path.write_text(self.shop_text.replace(old, new), encoding="utf-8")
        return path

    def test_rule_metadata_matches(self):
        rule = self.baseline
        self.assertEqual(rule["source"], catalog.ORGANIC_NAME_RE.pattern)
        self.assertEqual(rule["flags"], "i")
        self.assertEqual(catalog.ORGANIC_NAME_RE.flags, re.ASCII | re.IGNORECASE)
        self.assertEqual(len(rule["makers"]), len(set(rule["makers"])))
        self.assertEqual(len(catalog.ORGANIC_MAKERS), len(set(catalog.ORGANIC_MAKERS)))
        self.assertEqual(set(rule["makers"]), set(catalog.ORGANIC_MAKERS))

    def test_actual_predicates_match(self):
        items = [product(n) for n in NAMES]
        out = run_driver(items)
        self.assertEqual(drift(out, items), [])
        got = dict(zip(NAMES, out["results"]))
        for name in ("organic", "ORGANIC milk", "(organic)", "Organic-Valley", "an organic. bar",
                     "\u00e9organic", "organic\u00e9"):  # non-ASCII letters are boundaries in both engines
            self.assertTrue(got[name], name)
        for name in ("organically", "nonorganic", "organic2", "organic_", "", "Sea Salt"):
            self.assertFalse(got[name], name)

    def test_all_makers_and_near_misses(self):
        items = probes(self.baseline["makers"])
        out = run_driver(items)
        self.assertEqual(drift(out, items), [])
        for p, js in zip(items, out["results"]):
            name_hit = bool(catalog.ORGANIC_NAME_RE.search(p["name"]))
            maker_hit = p.get("producerKey") in set(self.baseline["makers"])
            self.assertEqual(js, name_hit or maker_hit, p)
        plain = {(p.get("producerKey", "<absent>"), r) for p, r in zip(items, out["results"]) if p["name"] == "Sea Salt"}
        for m in self.baseline["makers"]:
            self.assertIn((m, True), plain)
        for m in NEAR_MISS_MAKERS + ["<absent>"]:
            self.assertNotIn((m, True), plain)
        # description / displayBrand / brand are not signals
        self.assertEqual(out["results"][-2:], [False, False])

    def test_js_only_maker_mutation_fails(self):
        shop = self.mutated_shop("'Massa Organics']", "'Massa Organics','Zed Farms']")
        items = probes(self.baseline["makers"] + ["Zed Farms"])
        out = run_driver(items, shop)
        self.assertEqual(out["rule"]["makers"][-1], "Zed Farms")
        found = drift(out, items)
        self.assertTrue(any(f.startswith("rule:makers") and "Zed Farms" in f for f in found), found)
        self.assertTrue(any(f.startswith("probe:") and "'Zed Farms'" in f for f in found), found)

    def test_js_name_rule_mutation_fails(self):
        items = probes(self.baseline["makers"])
        no_boundary = run_driver(items, self.mutated_shop("/\\borganic\\b/i", "/organic/i", "a.js"))
        found = drift(no_boundary, items)
        self.assertTrue(any(f.startswith("rule:name-regex-source") for f in found), found)
        self.assertTrue(any(f.startswith("probe:'nonorganic'") for f in found), found)
        no_case = run_driver(items, self.mutated_shop("/\\borganic\\b/i", "/\\borganic\\b/", "b.js"))
        found = drift(no_case, items)
        self.assertTrue(any(f.startswith("rule:flags") for f in found), found)
        self.assertTrue(any(f.startswith("probe:'ORGANIC milk'") for f in found), found)

    def test_python_only_mutation_fails(self):
        items = probes(self.baseline["makers"])
        out = run_driver(items)
        found = drift(out, items, makers=catalog.ORGANIC_MAKERS + ("Py Only",))
        self.assertTrue(any(f.startswith("rule:makers") for f in found), found)
        found = drift(out, items, makers=catalog.ORGANIC_MAKERS[1:])
        self.assertTrue(any(f.startswith("probe:") and "'Ocean Ranch'" in f for f in found), found)
        found = drift(out, items, regex=re.compile(r"organic", re.IGNORECASE | re.ASCII))
        self.assertTrue(any(f.startswith("rule:name-regex-source") for f in found), found)
        self.assertTrue(any(f.startswith("probe:'nonorganic'") for f in found), found)
        found = drift(out, items, regex=re.compile(r"\borganic\b", re.ASCII))
        self.assertTrue(any(f.startswith("rule:flags") for f in found), found)
        found = drift(out, items, regex=re.compile(r"\borganic\b", re.IGNORECASE))
        self.assertTrue(any(f.startswith("rule:flags") for f in found), found)
        self.assertEqual(drift(out, items), [])

    def test_unrecognized_rule_or_driver_failure_fails_closed(self):
        items = [product()]
        shapes = {
            "rewritten": ("function organic(p){return /\\borganic\\b/i.test(p.name)||['Ocean Ranch','Straus','Green Gold','Massa Organics'].includes(p.producerKey)}",
                          "function organic(p){return p.name.length>99}"),
            "second-regex": ("/\\borganic\\b/i.test(p.name)||", "/\\borganic\\b/i.test(p.name)||/x/.test(p.name)||"),
        }
        for label, (old, new) in shapes.items():
            with self.subTest(label), self.assertRaises(subprocess.CalledProcessError) as cm:
                run_driver(items, self.mutated_shop(old, new, f"{label}.js"))
            self.assertIn("Organic rule shape changed; update parity harness", cm.exception.stderr)
        d = Path(self.tmp.name)
        (d / "fail.cjs").write_text("process.exit(3)\n", encoding="utf-8")
        (d / "junk.cjs").write_text("process.stdout.write('not json\\n')\n", encoding="utf-8")
        (d / "short.cjs").write_text("process.stdout.write('{\"rule\":{},\"results\":[]}\\n')\n", encoding="utf-8")
        (d / "hang.cjs").write_text("setInterval(()=>{},1000)\n", encoding="utf-8")
        with self.assertRaises(subprocess.CalledProcessError):
            run_driver(items, driver=d / "fail.cjs")
        with self.assertRaises(json.JSONDecodeError):
            run_driver(items, driver=d / "junk.cjs")
        with self.assertRaises(AssertionError):
            run_driver(items, driver=d / "short.cjs")
        with self.assertRaises(subprocess.TimeoutExpired):
            run_driver(items, timeout=1, driver=d / "hang.cjs")


if __name__ == "__main__":
    unittest.main()
