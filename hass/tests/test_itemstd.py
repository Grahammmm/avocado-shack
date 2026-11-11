"""AV1109-01 (ITEMSTD-2): the item-standard checker in hass/itemstd.py and its report CLI."""
import contextlib
import copy
import hashlib
import io
import itertools
import json
import os
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


BAD_CATEGORIES = ([], {}, ["vegetables"], {"vegetables": True}, None, 7, True, "invalid")


class BadShelfTest(unittest.TestCase):
    def test_container_categories_are_missing_shelf_without_mutation(self):
        for bad in ([], {}, ["vegetables"], {"name": "vegetables"}):
            rec, makers = product(category=bad), copy.deepcopy(MAKERS)
            before = (copy.deepcopy(rec), copy.deepcopy(makers))
            res = itemstd.check_product(rec, makers)
            self.assertEqual(set(res), KEYS, bad)
            self.assertEqual(res["missing"], ["shelf", "own_photo"], bad)
            self.assertFalse(res["complete"], bad)
            self.assertEqual(res["ask_order"], ["shelf"], bad)
            self.assertEqual(voice.plain(res["question"]), "Which shelf should it go on?", bad)
            self.assertEqual((rec, makers), before, "inputs are never changed")

    def test_bad_category_preserves_question_priority(self):
        makers = {"Smith Farm": TOWN_MAKER}
        for bad in BAD_CATEGORIES:
            res = itemstd.check_product(product(name="", category=bad), makers)
            self.assertEqual(res["ask_order"], ["name", "shelf"], bad)
            self.assertEqual(voice.plain(res["question"]), "What is it called?", bad)
            res = itemstd.check_product(product(category=bad, brand="", producerKey=None), makers)
            self.assertEqual(res["ask_order"], ["shelf", "producer", "producer_town"], bad)
            self.assertEqual(voice.plain(res["question"]), "Which shelf should it go on?", bad)
            self.assertEqual(res["missing"].count("shelf"), 1, bad)
        # the container answers exactly like the existing null and unknown-string controls
        controls = [itemstd.check_product(product(category=c, brand="", producerKey=None), makers)
                    for c in (None, "invalid", [], {})]
        self.assertTrue(all(c == controls[0] for c in controls))

    def test_bad_category_keeps_inactive_suppression(self):
        makers = {"Smith Farm": TOWN_MAKER}
        for bad in ([], {}):
            self.assertIsNone(itemstd.check_product({"status": "held", "category": bad}, makers))
            res = itemstd.check_product(product(status="hidden", category=bad), makers)
            self.assertIn("shelf", res["missing"])
            self.assertEqual((res["ask_order"], res["question"]), ([], None))
        report = itemstd.build_report(
            [product(id="a", category=[]), product(id="b", status="held", category={}),
             product(id="c", status="hidden", category=[]), product(id="d")], makers, {})
        s = report["summary"]
        self.assertEqual((s["products_active"], s["products_held"], s["products_hidden"]), (2, 1, 1))
        self.assertEqual((s["products_with_an_information_gap"], s["products_incomplete"]), (1, 1))
        self.assertEqual(s["missing_by_field_products"]["shelf"], 1)


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


    def test_report_cli_handles_container_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            content = tmp / "content"
            content.mkdir()
            (content / "products.json").write_text(json.dumps({"schemaVersion": 1, "products": [
                product(id="ok"), product(id="lst", category=[]), product(id="obj", category={"a": 1}),
                product(id="held", status="held", category=[])]}), encoding="utf-8")
            (content / "makers.json").write_text(json.dumps({"schemaVersion": 1, "makers": MAKERS}), encoding="utf-8")
            inputs = tree_hashes(content / "products.json", content / "makers.json")
            text = self.run_cli(SCRIPT, "--content", str(content), cwd=tmp)
            as_json = self.run_cli(SCRIPT, "--content", str(content), "--json", cwd=tmp)
            for got in (text, as_json):
                self.assertEqual(got.returncode, 0, got.stderr)
                self.assertEqual(got.stderr, "")
            self.assertIn("Active products with an information gap: 2 of 3", text.stdout)
            self.assertIn("  shelf: 2", text.stdout)
            report = json.loads(as_json.stdout)
            s = report["summary"]
            self.assertEqual((s["products_active"], s["products_held"], s["products_incomplete"]), (3, 1, 2))
            self.assertEqual(s["missing_by_field_products"]["shelf"], 2)
            rows = {r["id"]: r for r in report["products"]}
            self.assertEqual(rows["ok"]["missing"], ["own_photo"])
            for pid in ("lst", "obj"):
                self.assertEqual(rows[pid]["ask_order"], ["shelf"])
                self.assertEqual(rows[pid]["question"], "Which shelf should it go on?")
            self.assertEqual(report, itemstd.report_for(content), "report and pure checker agree")
            self.assertEqual(tree_hashes(content / "products.json", content / "makers.json"), inputs)
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["content"])

    def test_report_write_with_bad_shelf_is_atomic_and_scratch_only(self):
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
                product(), product(id="lst", category=[]), product(id="obj", category={})]}), encoding="utf-8")
            (content / "makers.json").write_text(json.dumps({"schemaVersion": 1, "makers": MAKERS}), encoding="utf-8")
            inputs = tree_hashes(content / "products.json", content / "makers.json")
            foreign = tmp / "elsewhere"
            foreign.mkdir()
            script = repo / "hass" / "itemstd.py"
            got = self.run_cli(script, "--write", cwd=foreign)
            self.assertEqual(got.returncode, 0, got.stderr)
            self.assertEqual(got.stderr, "")
            written = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(written["summary"]["missing_by_field_products"]["shelf"], 2)
            self.assertEqual(sorted(r["id"] for r in written["products"] if "shelf" in r["missing"]), ["lst", "obj"])
            self.assertEqual(sorted(p.name for p in reports.iterdir()), ["catalog-gaps.json"], "no orphan temp file")
            self.assertEqual(tree_hashes(content / "products.json", content / "makers.json"), inputs)
            # a real refusal still exits 2 and keeps the sentinel report
            target.write_bytes(b"old report\n")
            (content / "products.json").write_text(json.dumps({"schemaVersion": 1, "products": [
                product(category=[]), {"name": "no id", "category": {}}]}), encoding="utf-8")
            got = self.run_cli(script, "--write", cwd=foreign)
            self.assertEqual((got.returncode, got.stdout), (2, ""))
            self.assertIn("itemstd:", got.stderr)
            self.assertEqual(target.read_bytes(), b"old report\n")
            self.assertEqual(sorted(p.name for p in reports.iterdir()), ["catalog-gaps.json"])

    DEEP = 20000

    def deep_repo(self, tmp: Path, bad: str, shape: str, report: bytes = None):
        """Synthetic copied repo; `bad` (products.json or makers.json) carries raw over-deep JSON."""
        repo = tmp / "repo"
        (repo / "hass" / "style").mkdir(parents=True)
        for f in ("__init__.py", "voice.py", "itemstd.py", "style/item-standard.json"):
            shutil.copy(REPO / "hass" / f, repo / "hass" / f)
        content, reports = repo / "hass" / "content", repo / "reports" / "hass"
        content.mkdir()
        good = {"products.json": '{"schemaVersion": 1, "products": [%s]}' % json.dumps(product()),
                "makers.json": '{"schemaVersion": 1, "makers": %s}' % json.dumps(MAKERS)}
        key = "products" if bad == "products.json" else "makers"
        empty = "[]" if key == "products" else "{}"
        deep = "[" * self.DEEP + "]" * self.DEEP if shape == "array" else '{"a":' * self.DEEP + "1" + "}" * self.DEEP
        good[bad] = '{"schemaVersion": 1, "%s": %s, "extra": %s}' % (key, empty, deep)
        for name, text in good.items():
            (content / name).write_text(text, encoding="utf-8")
        target = reports / "catalog-gaps.json"
        if report is not None:
            reports.mkdir(parents=True)
            target.write_bytes(report)
        return repo, content, reports, target

    def test_load_refuses_excessive_json_nesting(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for bad in ("products.json", "makers.json"):
                for shape in ("array", "object"):
                    _, content, _, _ = self.deep_repo(tmp / f"{bad}{shape}", bad, shape)
                    for name, key, kind in (("products.json", "products", list), ("makers.json", "makers", dict)):
                        if name == bad:
                            with self.assertRaises(itemstd.ReportError) as cm:
                                itemstd._load(content / name, key, kind)
                            self.assertIn("JSON nesting is too deep", str(cm.exception))
                            self.assertNotIn("[[[", str(cm.exception))
                        else:
                            self.assertIsInstance(itemstd._load(content / name, key, kind)[0], kind)

    def test_report_cli_deep_products_and_makers_are_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for bad in ("products.json", "makers.json"):
                for shape in ("array", "object"):
                    root = tmp / f"{bad}{shape}"
                    root.mkdir()
                    repo, content, _, _ = self.deep_repo(root, bad, shape)
                    for extra in ((), ("--json",)):
                        got = self.run_cli(repo / "hass" / "itemstd.py", "--content", str(content), *extra, cwd=root)
                        self.assertEqual((got.returncode, got.stdout), (2, ""))
                        self.assertIn("itemstd:", got.stderr)
                        self.assertIn("JSON nesting is too deep", got.stderr)
                        self.assertNotIn("Traceback", got.stderr)
                        self.assertNotIn("RecursionError", got.stderr)

    def test_deep_input_preserves_existing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for bad in ("products.json", "makers.json"):
                for shape in ("array", "object"):
                    root = tmp / f"{bad}{shape}"
                    root.mkdir()
                    repo, content, reports, target = self.deep_repo(root, bad, shape, report=b"old report\n")
                    inputs = tree_hashes(content / "products.json", content / "makers.json")
                    foreign = root / "elsewhere"
                    foreign.mkdir()
                    got = self.run_cli(repo / "hass" / "itemstd.py", "--write", cwd=foreign)
                    self.assertEqual((got.returncode, got.stdout), (2, ""))
                    self.assertIn("itemstd:", got.stderr)
                    self.assertNotIn("Traceback", got.stderr)
                    self.assertEqual(target.read_bytes(), b"old report\n")
                    self.assertEqual(sorted(p.name for p in reports.iterdir()), ["catalog-gaps.json"])
                    self.assertEqual(tree_hashes(content / "products.json", content / "makers.json"), inputs)
                    self.assertEqual(list(foreign.iterdir()), [])

    def test_deep_input_does_not_create_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for bad in ("products.json", "makers.json"):
                root = tmp / bad
                root.mkdir()
                repo, _, reports, target = self.deep_repo(root, bad, "array")
                got = self.run_cli(repo / "hass" / "itemstd.py", "--write", cwd=root)
                self.assertEqual((got.returncode, got.stdout), (2, ""))
                self.assertFalse(target.exists())
                self.assertFalse(reports.exists())

    def test_shallow_unknown_metadata_remains_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            content = tmp / "content"
            content.mkdir()
            (content / "products.json").write_text(
                '{"schemaVersion": 1, "products": [], "extra": [[[{"a": [1]}]]]}', encoding="utf-8")
            (content / "makers.json").write_text(
                '{"schemaVersion": 1, "makers": %s, "extra": {"a": {"b": [[]]}}}' % json.dumps(MAKERS), encoding="utf-8")
            got = self.run_cli(SCRIPT, "--content", str(content), "--json", cwd=tmp)
            self.assertEqual(got.returncode, 0, got.stderr)
            self.assertEqual(json.loads(got.stdout), itemstd.report_for(content))

    REFUSAL = "itemstd: cannot write report\n"
    CANARY = "private-canary-7f3a"

    def synthetic_repo(self, tmp: Path):
        repo = tmp / "repo"
        (repo / "hass" / "style").mkdir(parents=True)
        for f in ("__init__.py", "voice.py", "itemstd.py", "style/item-standard.json"):
            shutil.copy(REPO / "hass" / f, repo / "hass" / f)
        content, reports = repo / "hass" / "content", repo / "reports" / "hass"
        content.mkdir()
        reports.mkdir(parents=True)
        (content / "products.json").write_text(json.dumps({"schemaVersion": 1, "products": [product()]}), encoding="utf-8")
        (content / "makers.json").write_text(json.dumps({"schemaVersion": 1, "makers": MAKERS}), encoding="utf-8")
        return repo, content, reports

    def external(self, tmp: Path, old: bytes | None = b"old report\n"):
        """A real catalog and an explicit external target; the checkout's own report is never named."""
        content, out = tmp / "content", tmp / "out"
        content.mkdir()
        out.mkdir()
        (content / "products.json").write_text('{"schemaVersion": 1, "products": []}', encoding="utf-8")
        (content / "makers.json").write_text('{"schemaVersion": 1, "makers": {}}', encoding="utf-8")
        target = out / "catalog-gaps.json"
        if old is not None: target.write_bytes(old)
        return content, out, target

    def call_main(self, content: Path, target: Path, *args):
        real = itemstd.write_report
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(itemstd, "REPORT_PATH", target), \
             mock.patch.object(itemstd, "write_report", lambda report, target=target: real(report, target)), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = itemstd.main(["report", "--content", str(content), *args])
        return rc, out.getvalue(), err.getvalue()

    def assert_refused(self, got, out_dir: Path, names):
        rc, out, err = got
        self.assertEqual((rc, out, err), (2, "", self.REFUSAL))
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), names, "no staging residue")

    def test_report_cli_directory_target_is_private_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo, content, reports = self.synthetic_repo(tmp)
            target = reports / "catalog-gaps.json"
            target.mkdir()
            (target / "canary.txt").write_bytes(self.CANARY.encode())
            foreign = tmp / "elsewhere"
            foreign.mkdir()
            inputs = tree_hashes(content / "products.json", content / "makers.json")
            got = self.run_cli(repo / "hass" / "itemstd.py", "--write", cwd=foreign)
            self.assertEqual((got.returncode, got.stdout, got.stderr), (2, "", self.REFUSAL))
            self.assertEqual((target / "canary.txt").read_bytes(), self.CANARY.encode())
            self.assertEqual(sorted(p.name for p in reports.iterdir()), ["catalog-gaps.json"])
            self.assertEqual(sorted(p.name for p in target.iterdir()), ["canary.txt"])
            self.assertEqual(list(foreign.iterdir()), [])
            self.assertEqual(tree_hashes(content / "products.json", content / "makers.json"), inputs)

    def test_report_cli_staging_creation_failure_is_controlled(self):
        for old in (b"old report\n", None):
            with self.subTest(old=old), tempfile.TemporaryDirectory() as tmp:
                content, out, target = self.external(Path(tmp), old)
                with mock.patch.object(itemstd.tempfile, "mkstemp", side_effect=OSError(self.CANARY)):
                    got = self.call_main(content, target, "--write")
                self.assert_refused(got, out, [] if old is None else ["catalog-gaps.json"])
                self.assertEqual(target.read_bytes() if old is not None else None, old)

    def test_report_cli_write_and_close_failure_preserve_old_report(self):
        real_fdopen, opened = os.fdopen, []

        class FaultFile:
            def __init__(self, fh, mode):
                self.fh, self.mode = fh, mode
                opened.append(fh)

            def __enter__(self): return self

            def __exit__(self, *exc):
                self.fh.close()
                if self.mode == "close" and exc[0] is None: raise OSError(self.CANARY)
                return False

            def write(self, text):
                if self.mode == "write": raise OSError(self.CANARY)
                return self.fh.write(text)

        FaultFile.CANARY = self.CANARY
        for mode in ("write", "close"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                content, out, target = self.external(Path(tmp))
                opened.clear()
                with mock.patch.object(itemstd.os, "fdopen", lambda fd, *a, **k: FaultFile(real_fdopen(fd, *a, **k), mode)):
                    got = self.call_main(content, target, "--write")
                self.assert_refused(got, out, ["catalog-gaps.json"])
                self.assertEqual(target.read_bytes(), b"old report\n")
                self.assertTrue(opened and all(fh.closed for fh in opened), "staging descriptor closed")

    def test_report_cli_replace_failure_preserves_old_report(self):
        staged = []

        def failing_replace(src, dst):
            staged.append(Path(src).read_bytes())
            raise OSError(f"{self.CANARY} {src} {dst}")

        with tempfile.TemporaryDirectory() as tmp:
            content, out, target = self.external(Path(tmp))
            with mock.patch.object(itemstd.os, "replace", failing_replace):
                got = self.call_main(content, target, "--write")
            self.assert_refused(got, out, ["catalog-gaps.json"])
            self.assertEqual(target.read_bytes(), b"old report\n")
            self.assertEqual(json.loads(staged[0])["schema"], 2, "the real report was staged before the failure")

    def test_report_success_and_readonly_modes_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            content, out, target = self.external(Path(tmp))
            report = itemstd.report_for(content)
            with mock.patch.object(itemstd, "write_report") as writer:
                rc, text, err = self.call_main(content, target)
                rc_json, as_json, err_json = self.call_main(content, target, "--json")
            writer.assert_not_called()
            self.assertEqual((rc, text, err, rc_json, err_json), (0, itemstd.report_text(report) + "\n", "", 0, ""))
            self.assertEqual(json.loads(as_json), report)
            self.assertEqual(target.read_bytes(), b"old report\n")
            rc, text, err = self.call_main(content, target, "--write")
            self.assertEqual((rc, text, err), (0, itemstd.report_text(report) + "\n", ""))
            self.assertEqual(target.read_text(encoding="utf-8"), json.dumps(report, ensure_ascii=False, indent=1) + "\n")
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["catalog-gaps.json"])

    def test_non_os_programming_errors_are_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            content, out, target = self.external(Path(tmp))
            with mock.patch.object(itemstd.os, "replace", side_effect=RuntimeError("bug")):
                with self.assertRaises(RuntimeError):
                    self.call_main(content, target, "--write")
            self.assertEqual(target.read_bytes(), b"old report\n")
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["catalog-gaps.json"])


if __name__ == "__main__":
    unittest.main()
