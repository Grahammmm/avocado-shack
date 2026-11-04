"""RF1346-1: top-level storefront-mockup/*.cjs must not drive the archived commerce preview."""
import re, tempfile, unittest
from pathlib import Path
TOP = Path(__file__).resolve().parents[2] / "storefront-mockup"
MOVED = ("shop-qa.cjs", "mobile-function-qa.cjs", "mobile-function-long-qa.cjs", "qa.cjs")
EVIDENCE = ("shop-desktop.png", "shop-mobile.png", "shop-QA.json", "QA.json", "hass.png", "hass-mobile.png", "mobile-function-qa.json",
            "mobile-function-long-qa.json", "mobile-function-reverify.json", "mobile-function-review.md",
            "mobile-visual-375-boxes.png", "mobile-visual-375-merch.png", "mobile-visual-390-boxes.png", "mobile-visual-390-merch.png")
COMMERCE = ("data-add=", "#box-grid", "#merch-grid", "merch-tee", "#bag", "#detail-add")
ACT = re.compile(r"""locator\(\s*(?:'([^']*)'|"([^"]*)"|`([^`]*)`)\s*\)(?:\.(?:first|last|nth)\([^)]*\))*\.(?:click|fill)\(""")


def problems(top):
    out = [f"{n} is back at the top level" for n in MOVED + EVIDENCE if (top / n).exists()]
    for p in sorted(top.glob("*.cjs")):
        for m in ACT.finditer(p.read_text()):
            sel = "".join(g or "" for g in m.groups())
            out += [f"{p.name} drives {c} via {sel}" for c in COMMERCE if c in sel]
    return out


class LiveQaScripts(unittest.TestCase):
    def test_live_scripts_are_catalog_only(self):
        self.assertEqual(problems(TOP), [])

    def test_commerce_evidence_is_archived_and_detected_at_top(self):
        ev = TOP / "archive" / "commerce-preview" / "qa" / "evidence"
        self.assertEqual([n for n in EVIDENCE if not (ev / n).is_file()], [])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "shop-QA.json").write_text("{}")
            self.assertEqual(problems(Path(d)), ["shop-QA.json is back at the top level"])

    def test_detects_moved_name_and_commerce_click(self):
        with tempfile.TemporaryDirectory() as d:
            top = Path(d)
            for name, text in {"shop-qa.cjs": "x", "ok.cjs": "p.locator('[data-add=\"x\"],#bag').count();p.locator('#y').click();",
                               "a.cjs": "p.locator('[data-add=\"x\"]').first().click();", "b.cjs": "p.locator(\"#bag\").fill('1');"}.items():
                (top / name).write_text(text)
            got = " | ".join(problems(top))
            self.assertEqual([got.count(k) for k in ("shop-qa.cjs is back", "a.cjs drives", "b.cjs drives", "ok.cjs")], [1, 1, 1, 0])
