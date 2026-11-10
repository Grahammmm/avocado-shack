"""AV1109-01 (ITEMSTD-2): the item-standard checker in hass/itemstd.py and its report CLI."""
import copy
import hashlib
import itertools
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import itemstd, voice

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "hass" / "itemstd.py"
CONTENT = REPO / "hass" / "content"
REPORT = REPO / "reports" / "hass" / "catalog-gaps.json"
SOURCE_COMMIT = "56c907093b6ba62c2e5a6188d5363961b560b00b"  # the content reports/hass/catalog-gaps.json was built from
SOURCE_BLOBS = {"products.json": "62d54a487d150904bbc670782664d599bc57ffab",
                "makers.json": "94272f260afde7e7a19abc63b46c19bc8ed6030a"}
KEYS = {"complete", "missing", "display_problems", "needs_a_look", "ask_order", "question"}
TOWN_MAKER = {"name": "Smith Farm", "place": "Arroyo Grande, California", "story": "A farm.", "url": "https://example.com"}
MAKERS = {"Smith Farm": TOWN_MAKER,
          "Coast Co": {"name": "Coast Co", "place": "California\u2019s Central Coast", "story": "S.", "url": ""}}


def product(**over):
    rec = {"id": "photo-product-900", "name": "Tomatoes", "brand": "Smith Farm", "displayBrand": "Smith Farm",
           "producerKey": "Smith Farm", "category": "vegetables", "image": "assets/products/photo-product-900.webp",
           "description": "Ripe and sweet. Slice them thick.", "status": "active"}
    rec.update(over)
    return rec


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def tree_hashes(*paths):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


class PureContractTest(unittest.TestCase):
    def test_pure_contract_and_suppression(self):
        rec, makers = product(), copy.deepcopy(MAKERS)
        before = (copy.deepcopy(rec), copy.deepcopy(makers))
        first = itemstd.check_product(rec, makers)
        self.assertEqual(set(first), KEYS)
        self.assertEqual((rec, makers), before, "inputs are never changed")
        self.assertEqual(first, itemstd.check_product(rec, makers), "repeat calls agree")
        self.assertTrue(first["complete"])
        self.assertEqual(first["missing"], ["own_photo"])  # stock picture: an upgrade, not a gap
        self.assertEqual((first["ask_order"], first["question"]), ([], None))
        self.assertEqual(set(itemstd.CODES), {"name", "shelf", "producer", "producer_town", "own_photo", "description",
                                              "story", "website"})
        # held: nothing at all, even when everything else is broken
        self.assertIsNone(itemstd.check_product({"status": "held"}, {}))
        self.assertIsNone(itemstd.check_product(product(status="held", name="", category="x", brand=""), makers))
        # hidden: findings, but never a question
        hidden = itemstd.check_product(product(status="hidden", name=""), makers)
        self.assertIn("name", hidden["missing"])
        self.assertEqual((hidden["ask_order"], hidden["question"]), ([], None))
        hidden_maker = itemstd.check_maker({"name": "X", "place": "Central Coast", "story": "S.", "hidden": True})
        self.assertIn("producer_town", hidden_maker["missing"])
        self.assertIsNone(hidden_maker["question"])
        # market placeholder and unlinked own brand: producer and town missing
        for brand in ("Producer not identified", "From the market", "Avocado Shack", "", None):
            res = itemstd.check_product(product(brand=brand, producerKey=None), makers)
            self.assertEqual(res["missing"], ["producer", "producer_town", "own_photo"], brand)
            self.assertFalse(res["complete"])
        # a named brand with no maker record: the producer is known, the town is not, and the link needs a look
        res = itemstd.check_product(product(brand="SLO Cider", producerKey=None), makers)
        self.assertEqual(res["missing"], ["producer_town", "own_photo"])
        self.assertEqual(res["needs_a_look"], ["brand_without_maker_record"])
        self.assertEqual(voice.plain(res["question"]), "Which town is SLO Cider in?")
        # a dangling producerKey never counts as a maker
        res = itemstd.check_product(product(producerKey="Gone Farm", brand="Gone Farm"), makers)
        self.assertEqual((res["missing"], res["needs_a_look"]), (["producer_town", "own_photo"], ["broken_maker_link"]))
        res = itemstd.check_product(product(producerKey="Gone Farm", brand="Producer not identified"), makers)
        self.assertEqual(res["missing"], ["producer", "producer_town", "own_photo"])
        self.assertIn("broken_maker_link", res["needs_a_look"])
        # a linked maker whose place is a region
        res = itemstd.check_product(product(producerKey="Coast Co", brand="Coast Co"), makers)
        self.assertEqual((res["missing"], res["needs_a_look"]), (["producer_town", "own_photo"], ["place_is_a_region"]))
        self.assertEqual(voice.plain(res["question"]), "Which town is Coast Co in?")
        # own photo and display problems
        own = itemstd.check_product(product(image="assets/products/photo-0123456789abcdef.jpg"), makers)
        self.assertEqual((own["missing"], own["display_problems"]), ([], ["alt_is_default"]))
        odd = itemstd.check_product(product(name="Tomatoes 2 " + "x" * 80, description="Wow! " * 130, image=""), makers)
        self.assertTrue(odd["complete"], "display problems alone are not missing information")
        self.assertEqual(odd["display_problems"], ["name_long", "name_has_digit", "description_long",
                                                   "description_punctuation", "description_no_full_stop",
                                                   "picture_missing"])

    def test_check_maker(self):
        self.assertEqual(itemstd.check_maker(TOWN_MAKER), {"complete": True, "missing": [], "display_problems": [],
                                                           "needs_a_look": [], "ask_order": [], "question": None})
        res = itemstd.check_maker({"name": "Smith Farm", "place": "Near Chico, California", "story": "S."})
        self.assertEqual(res["missing"], ["producer_town", "website"])  # website: listed, never a gap, never asked
        self.assertFalse(res["complete"])
        self.assertEqual((res["ask_order"], res["needs_a_look"]), (["producer_town"], ["place_is_a_region"]))
        self.assertEqual(voice.plain(res["question"]), "Which town is Smith Farm in?")
        res = itemstd.check_maker({"name": "", "place": "", "story": "", "url": "https://x.example"})
        self.assertEqual(res["missing"], ["name", "producer_town", "story"])
        self.assertEqual((res["needs_a_look"], res["question"]), ([], "Which town are they in?"))
        res = itemstd.check_maker({"name": "Smith Farm", "place": "Arroyo Grande, California", "story": "S."})
        self.assertEqual((res["complete"], res["missing"], res["question"]), (True, ["website"], None))


class TownFormatTest(unittest.TestCase):
    def test_town_format_not_geographic_lookup(self):
        cases = {
            "": "blank", "   ": "blank", None: "blank",
            "Central Coast": "region", "Northern California": "region", "California\u2019s Central Coast": "region",
            "California's Central Coast, California": "region", "Central Coast, California": "region",
            "Near Chico, California": "region", "Glenn County, California": "region",
            "Coachella Valley, California": "region",
            "Arroyo Grande, California": "town", "Mill Valley, California": "town", "Rochester, New York": "town",
            "San Jos\u00e9, California": "town", "Coeur d\u2019Alene, Idaho": "town", "Winston-Salem, North Carolina": "town",
            "St. Helena, California": "town", "Pasoo Robels, Califronia": "town",  # spelling is not checked
            "Chico": "other", "Chico, California, USA": "other", "Chico, 95926": "other", ", California": "other",
        }
        with mock.patch.object(socket, "socket", side_effect=AssertionError("no network")):
            for place, want in cases.items():
                self.assertEqual(itemstd.classify_place(place), want, place)
        self.assertEqual(itemstd.check_maker({"name": "M", "place": "Pasoo Robels, Califronia", "story": "S.",
                                              "url": "u"})["missing"], [])
        rec = {"name": "M", "place": "chico", "story": "S.", "url": "u"}
        self.assertEqual(itemstd.check_maker(rec)["needs_a_look"], ["place_not_town_state"])
        self.assertEqual(rec["place"], "chico", "the record is never normalized")


class PriorityTest(unittest.TestCase):
    def test_priority_and_optional_fields(self):
        makers = {"Smith Farm": TOWN_MAKER, "Blank Place": {"name": "Blank Place", "place": "", "story": "S."}}
        for gaps in itertools.product((False, True), repeat=4):
            no_name, no_shelf, no_producer, no_town = gaps
            over: dict = {"name": "" if no_name else "Tomatoes", "category": "nope" if no_shelf else "vegetables"}
            if no_producer: over.update(brand="Producer not identified", producerKey=None)
            elif no_town: over.update(brand="Blank Place", producerKey="Blank Place")
            res = itemstd.check_product(product(**over), makers)
            want = [c for c, g in zip(("name", "shelf", "producer", "producer_town"), gaps) if g]
            if no_producer and "producer_town" not in want: want.append("producer_town")
            self.assertEqual(res["ask_order"], want, gaps)
            self.assertEqual(res["complete"], not want, gaps)
            if not want:
                self.assertIsNone(res["question"])
                continue
            first = {"name": "What is it called?", "shelf": "Which shelf should it go on?",
                     "producer": "Who grew the Tomatoes this week?",
                     "producer_town": "Which town is Blank Place in?"}[want[0]]
            self.assertEqual(voice.plain(res["question"]), first, gaps)
        # description and story are required but never asked; a photo and a website are never asked
        res = itemstd.check_product(product(description="  "), makers)
        self.assertEqual((res["complete"], res["missing"], res["question"]), (False, ["own_photo", "description"], None))
        res = itemstd.check_maker({"name": "Smith Farm", "place": "Arroyo Grande, California", "story": ""})
        self.assertEqual((res["complete"], res["missing"], res["question"]), (False, ["story", "website"], None))
        packaged = itemstd.check_product(product(category="pantry", name="Jam", brand="", producerKey=None), makers)
        self.assertEqual(voice.plain(packaged["question"]), "Who makes the Jam?")
        chips = itemstd.check_product(product(id="photo-product-018", name="Chips", brand="", producerKey=None), makers)
        self.assertEqual(voice.plain(chips["question"]), "Who makes the Chips?")


class VoiceTest(unittest.TestCase):
    def test_every_question_passes_voice(self):
        self.assertEqual(set(itemstd.QUESTIONS), {"name", "shelf", "producer_fresh", "producer_packaged", "producer_town",
                                                  "producer_town_no_label"})
        names = ("Tomatoes", "photo-product-001 {item}", "None", "[x] -> y.json", "\u00a1Ol\u00e9!!", "unit_cost")
        asked = []
        for name in names:
            for shelf in ("vegetables", "pantry"):
                asked.append(itemstd.check_product(product(name=name, category=shelf, brand="", producerKey=None), {}))
            asked.append(itemstd.check_product(product(brand=name, producerKey=None), {}))
            asked.append(itemstd.check_maker({"name": name, "place": "Central Coast", "story": "S."}))
        asked.append(itemstd.check_product(product(name=""), MAKERS))
        asked.append(itemstd.check_product(product(category=""), MAKERS))
        asked.append(itemstd.check_maker({"name": "", "place": "", "story": "S."}))
        questions = [r["question"] for r in asked]
        self.assertTrue(all(isinstance(q, str) and q.strip() for q in questions))
        for q in questions:
            self.assertEqual(voice.check(q), [], q)
            self.assertNotIn("{", voice._ours(q))
            self.assertTrue(voice.plain(q).endswith("?"), q)
        for key, template in itemstd.QUESTIONS.items():
            filled = template.format(item=voice.quote("tomatoes"), maker=voice.quote("Smith Farm"))
            self.assertEqual(voice.check(filled), [], key)
        self.assertEqual(len({voice.plain(q) for q in questions if "Tomatoes" in voice.plain(q)}), 3)


class ReportTest(unittest.TestCase):
    def run_cli(self, script, *args, cwd):
        return subprocess.run([sys.executable, "-B", str(script), "report", *args], cwd=cwd, capture_output=True,
                              text=True, timeout=120)

    def historical_content(self, tmp: Path) -> Path:
        if all(git_blob((CONTENT / f).read_bytes()) == b for f, b in SOURCE_BLOBS.items()):
            return CONTENT
        out = tmp / "historical"
        out.mkdir()
        for f in SOURCE_BLOBS:
            got = subprocess.run(["git", "-C", str(REPO), "show", f"{SOURCE_COMMIT}:hass/content/{f}"],
                                 capture_output=True, timeout=60)
            if got.returncode != 0: self.skipTest(f"content changed and {SOURCE_COMMIT[:7]} is not in this clone")
            (out / f).write_bytes(got.stdout)
        return out

    def test_historical_catalog_count_parity(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = self.historical_content(Path(tmp))
            report = itemstd.report_for(content)
            hist = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(hist["source_commit"], SOURCE_COMMIT)
        s, h = report["summary"], hist["summary"]
        self.assertEqual((s["products_active"], s["products_held"], s["makers"]), (170, 2, 26))
        self.assertEqual((h["products_active"], h["products_held"], h["makers"]), (170, 2, 26))
        self.assertEqual(s["products_with_an_information_gap"], h["products_with_an_information_gap"])
        self.assertEqual(s["products_with_an_information_gap"], 80)
        self.assertEqual(s["missing_by_field_products"]["producer_town"], h["missing_by_field_products"]["producer_town"])
        self.assertEqual(s["missing_by_field_products"]["producer"], h["missing_by_field_products"]["producer"])
        self.assertEqual((s["missing_by_field_products"]["producer_town"], s["missing_by_field_products"]["producer"]),
                         (80, 64))
        self.assertEqual(s["own_photo_upgrades"], 170)
        self.assertEqual(s["products_incomplete"], 80, "170 stock pictures do not inflate the gaps")
        self.assertEqual((s["makers_with_a_gap"], s["makers_with_a_region"]), (6, 6))
        regions = [m["key"] for m in report["makers"] if "place_is_a_region" in m["needs_a_look"]]
        self.assertEqual(sorted(regions), sorted(["Straus", "Alle-Pia", "Corberosa", "Massa Organics", "Sierra Nevada",
                                                  "Ava\u2019s"]))

    def test_report_read_only_and_explicit_write(self):
        watched = [REPORT, CONTENT / "products.json", CONTENT / "makers.json"]
        before = tree_hashes(*watched)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            text = self.run_cli(SCRIPT, cwd=tmp)
            as_json = self.run_cli(SCRIPT, "--json", cwd=tmp)
            self.assertEqual((text.returncode, as_json.returncode), (0, 0), text.stderr + as_json.stderr)
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), [], "nothing written in the working folder")
            report = json.loads(as_json.stdout)
            self.assertEqual(report, itemstd.report_for(CONTENT), "JSON is the pure checker's report")
            s = report["summary"]
            self.assertIn(f"Active products with an information gap: {s['products_with_an_information_gap']} of "
                          f"{s['products_active']}", text.stdout)
            self.assertEqual(report["source"]["content"], "hass/content")
        self.assertEqual(tree_hashes(*watched), before, "the report and content are unchanged without --write")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo = tmp / "repo"
            (repo / "hass" / "style").mkdir(parents=True)
            for f in ("__init__.py", "voice.py", "itemstd.py", "style/item-standard.json"):
                shutil.copy(REPO / "hass" / f, repo / "hass" / f)
            content, reports = repo / "hass" / "content", repo / "reports" / "hass"
            content.mkdir()
            reports.mkdir(parents=True)
            target = reports / "catalog-gaps.json"
            target.write_bytes(b"old report\n")
            (content / "products.json").write_text(json.dumps({"schemaVersion": 1, "products": [
                product(), product(id="p2", brand="Producer not identified", producerKey=None),
                product(id="p3", status="held")]}), encoding="utf-8")
            (content / "makers.json").write_text(json.dumps({"schemaVersion": 1, "makers": MAKERS}), encoding="utf-8")
            script, foreign = repo / "hass" / "itemstd.py", tmp / "elsewhere"
            foreign.mkdir()
            inputs = tree_hashes(content / "products.json", content / "makers.json")
            got = self.run_cli(script, cwd=foreign)
            self.assertEqual((got.returncode, target.read_bytes()), (0, b"old report\n"), got.stderr)
            self.assertIn("Active products with an information gap: 1 of 2", got.stdout)
            got = self.run_cli(script, "--write", cwd=foreign)
            self.assertEqual(got.returncode, 0, got.stderr)
            written = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(written["summary"]["products_held"], 1)
            self.assertEqual(written["summary"]["missing_by_field_products"]["producer"], 1)
            self.assertEqual(written["summary"]["makers_with_a_region"], 1)
            self.assertEqual(sorted(p.name for p in reports.iterdir()), ["catalog-gaps.json"])
            self.assertEqual(sorted(p.name for p in foreign.iterdir()), [])
            self.assertEqual(tree_hashes(content / "products.json", content / "makers.json"), inputs)
            # an empty catalog: zero counts, no errors
            empty = tmp / "empty"
            empty.mkdir()
            (empty / "products.json").write_text('{"schemaVersion": 1, "products": []}', encoding="utf-8")
            (empty / "makers.json").write_text('{"schemaVersion": 1, "makers": {}}', encoding="utf-8")
            got = self.run_cli(script, "--content", str(empty), "--json", cwd=foreign)
            self.assertEqual(got.returncode, 0, got.stderr)
            summary = json.loads(got.stdout)["summary"]
            self.assertEqual((summary["products_active"], summary["products_with_an_information_gap"], summary["makers"]),
                             (0, 0, 0))
            self.assertEqual(json.loads(got.stdout)["source"]["content"], "a folder outside this repository")
            # missing or malformed input: exit nonzero, say why, and leave the old report alone
            target.write_bytes(b"old report\n")
            bad = tmp / "bad"
            bad.mkdir()
            (bad / "makers.json").write_text('{"schemaVersion": 1, "makers": {}}', encoding="utf-8")
            for products_text in (None, "{not json", '{"products": []}', '{"schemaVersion": 1, "products": {}}',
                                  '{"schemaVersion": 1, "products": [{"name": "no id"}]}'):
                if products_text is not None: (bad / "products.json").write_text(products_text, encoding="utf-8")
                got = self.run_cli(script, "--content", str(bad), "--write", cwd=foreign)
                self.assertEqual(got.returncode, 2, products_text)
                self.assertIn("itemstd:", got.stderr)
                self.assertEqual(got.stdout, "")
                self.assertEqual(target.read_bytes(), b"old report\n", products_text)
                self.assertEqual(sorted(p.name for p in reports.iterdir()), ["catalog-gaps.json"])


if __name__ == "__main__":
    unittest.main()
