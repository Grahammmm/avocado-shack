"""H01 tests: canonical content, generator and migration check.

Every test that writes uses its own temporary directory; the checkout is only read.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import contextlib
import copy
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import migration_check, sitegen
from hass.content_model import (
    CONTENT_DIR, REPO_ROOT, SITE_DIR, ContentError, load_and_validate, load_content, validate,
)

GENERATED = [sitegen.SITE_PREFIX + name for name in (
    "catalog-products.js", "producers.js", "producers.json", "community.json", "index.html", "hike/index.html")]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _quiet(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = fn(*args)
    return code, out.getvalue()


class IsolatedRepo:
    """A throwaway repo layout: copied content/templates/site JSON, images linked read-only."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="hass-h01-")
        self.root = Path(self._tmp.name)
        shutil.copytree(REPO_ROOT / "hass" / "content", self.root / "hass" / "content")
        shutil.copytree(REPO_ROOT / "hass" / "templates", self.root / "hass" / "templates")
        site = self.root / "storefront-mockup"
        (site / "hike").mkdir(parents=True)
        for rel in GENERATED + ["storefront-mockup/held-products.json", "storefront-mockup/hiking-preview.json"]:
            shutil.copyfile(REPO_ROOT / rel, self.root / rel)
        (site / "assets").symlink_to(SITE_DIR / "assets", target_is_directory=True)

    def edit(self, name, fn):
        path = self.root / "hass" / "content" / name
        data = json.loads(path.read_text("utf-8"))
        fn(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def cleanup(self):
        self._tmp.cleanup()


class GeneratorTests(unittest.TestCase):
    def test_generated_files_are_byte_identical_to_committed_site(self):
        files = sitegen.render(load_and_validate())
        self.assertEqual(sorted(files), sorted(GENERATED))
        for rel, data in files.items():
            with self.subTest(rel=rel):
                self.assertEqual(data, (REPO_ROOT / rel).read_bytes())

    def test_check_mode_passes_on_checkout(self):
        code, out = _quiet(sitegen.main, ["--check"])
        self.assertEqual(code, 0, out)
        content = load_and_validate()  # HASS-LIVE-ADD-1: a live add or hide changes the counts; they come from the content, not a constant
        self.assertIn(f"{len(content.active_products())} active products, {len(content.makers)} makers", out)

    def test_out_mode_renders_into_temp_dir_without_touching_checkout(self):
        before = {rel: _sha(REPO_ROOT / rel) for rel in GENERATED}
        with tempfile.TemporaryDirectory(prefix="hass-h01-out-") as tmp:
            code, out = _quiet(sitegen.main, ["--out", tmp])
            self.assertEqual(code, 0, out)
            for rel in GENERATED:
                self.assertEqual(_sha(Path(tmp) / rel), before[rel], rel)
        self.assertEqual(before, {rel: _sha(REPO_ROOT / rel) for rel in GENERATED})

    def test_store_edit_regenerates_only_pages_and_escapes_markup(self):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        repo.edit("store.json", lambda s: s.update(hours=["Monday–Friday 9am–6pm", "Saturday & Sunday 10am–4pm"]))
        code, out = _quiet(sitegen.main, ["--check", "--repo", str(repo.root)])
        self.assertEqual(code, 1)
        self.assertIn("storefront-mockup/index.html", out)
        self.assertNotIn("catalog-products.js", out)
        code, out = _quiet(sitegen.main, ["--write", "--repo", str(repo.root)])
        self.assertEqual(code, 0, out)
        page = (repo.root / "storefront-mockup" / "index.html").read_text("utf-8")
        self.assertIn("<p>Monday–Friday 9am–6pm<br>Saturday &amp; Sunday 10am–4pm</p>", page)
        self.assertEqual(_quiet(sitegen.main, ["--check", "--repo", str(repo.root)])[0], 0)

    def test_hidden_and_held_products_are_not_emitted(self):
        content = load_and_validate()
        active_before = len(content.active_products())  # HASS-LIVE-ADD-1: derived, not 169 + 1 (a live add or hide changes it)
        content.products[0]["status"] = "hidden"
        hidden_id = content.products[0]["id"]
        catalog = sitegen.render(content)[sitegen.SITE_PREFIX + "catalog-products.js"].decode("utf-8")
        records = json.loads(catalog.split("\n", 1)[0][len("const catalog="):].rstrip(";"))
        ids = {r["id"] for r in records}
        self.assertEqual(len(records), active_before - 1)
        self.assertNotIn(hidden_id, ids)
        self.assertNotIn("photo-product-040", ids)
        self.assertNotIn("photo-product-133", ids)
        for record in records:
            self.assertNotIn("status", record)
            self.assertNotIn("hold", record)

    def test_unknown_template_slot_is_rejected(self):
        with self.assertRaises(ContentError):
            sitegen.render_template("<p>{{store.phone}}</p>", sitegen.store_slots(load_content().store))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.base = load_content(CONTENT_DIR)

    def assertRejected(self, mutate, expect):
        content = copy.deepcopy(self.base)
        mutate(content)
        with self.assertRaises(ContentError) as ctx:
            validate(content, SITE_DIR)
        self.assertTrue(any(expect in p for p in ctx.exception.problems), ctx.exception.problems)

    def test_checkout_content_is_valid(self):
        validate(self.base, SITE_DIR)

    def test_rejections(self):
        event = {"id": "hike-2026-12-05", "title": "Morning walk", "startsAt": "2026-12-05T09:00:00-08:00",
                 "timezone": "America/Los_Angeles", "status": "scheduled"}

        def add_event(**changes):
            def mutate(c):
                c.community["events"].append({**event, **changes})
            return mutate

        def product(i, **changes):
            def mutate(c):
                c.products[i].update(changes)
            return mutate

        cases = {
            "price field": (product(0, price=4.5), "unknown field 'price'"),
            "unit field": (product(1, sampleUnit="each"), "unknown field 'sampleUnit'"),
            "currency text": (product(0, description="Only $3 today."), "forbidden text '$'"),
            "markup in name": (product(0, name="<b>Avocado</b>"), "forbidden text '<'"),
            "unknown category": (product(0, category="merch"), "category 'merch'"),
            "dangling maker": (product(0, producerKey="Nobody Farm"), "not a maker"),
            "duplicate id": (product(1, id="photo-product-001"), "duplicate id"),
            "missing image file": (product(0, image="assets/products/does-not-exist.webp"), "does not exist"),
            "path traversal image": (product(0, image="../community-data/x.webp"), "image must be"),
            "bad status": (product(0, status="deleted"), "status must be"),
            "hold on active product": (product(0, hold={"reason": "x", "source": "https://example.org/"}),
                                       "only allowed on held"),
            "held without hold record": (lambda c: next(p for p in c.products if p.get("status") == "held").pop("hold"), ".hold: must be an object"),
            "http maker url": (lambda c: c.makers["Etto"].update(url="http://ettopastificio.com/"), "https://"),
            "extra maker field": (lambda c: c.makers["Etto"].update(organic=True), "unknown field 'organic'"),
            "store markup": (lambda c: c.store.update(hours=["9am<script>"]), "forbidden text '<'"),
            "store unknown field": (lambda c: c.store.update(email="a@b.c"), "unknown field 'email'"),
            "email connected": (lambda c: c.community["club"].update(emailConnected=True), "emailConnected"),
            "route idea rsvp": (lambda c: c.community["routeIdeas"][0].update(rsvpEnabled=True), "rsvpEnabled"),
            "route idea dated": (lambda c: c.community["routeIdeas"][0].update(status="scheduled"), "'idea'"),
            "event without offset": (add_event(startsAt="2026-12-05T09:00:00"), "UTC offset"),
            "event bad date": (add_event(startsAt="2026-13-45T09:00:00-08:00"), "not a valid"),
            "event timezone": (add_event(timezone="UTC"), "America/Los_Angeles"),
            "event missing status": (lambda c: c.community["events"].append(
                {k: v for k, v in event.items() if k != "status"}), "missing field 'status'"),
            "event capacity zero": (add_event(capacity=0), "positive integer"),
            "event capacity bool": (add_event(capacity=True), "positive integer"),
            "rsvp without meeting point": (add_event(rsvpEnabled=True), "meetingPoint"),
            "sample promoted": (add_event(id="preview-point-buchon"), "cannot become real events"),
            "unknown trail": (add_event(trailId="idea-nowhere"), "not a route idea"),
            "event unknown field": (add_event(attendees=["someone"]), "unknown field 'attendees'"),
            "event date-only with offset": (add_event(startsAt="2026-12-05-08:00"), "UTC offset"),
            "event naive minutes": (add_event(startsAt="2026-12-05T08:00"), "UTC offset"),
            "id trailing newline": (product(0, id="photo-product-001\n"), "invalid id"),
            "image trailing newline": (product(0, image="assets/products/photo-product-001.webp\n"), "image must be"),
        }
        for name, (mutate, expect) in cases.items():
            with self.subTest(case=name):
                self.assertRejected(mutate, expect)

    def test_valid_real_event_is_accepted_and_emitted(self):
        content = copy.deepcopy(self.base)
        content.community["events"].append({
            "id": "hike-2026-12-05", "title": "Morning walk", "startsAt": "2026-12-05T09:00:00-08:00",
            "timezone": "America/Los_Angeles", "status": "scheduled", "meetingPoint": "Trailhead",
            "rsvpEnabled": True, "capacity": 12, "trailId": "idea-cass-hill"})
        validate(content, SITE_DIR)
        community = json.loads(sitegen.render(content)[sitegen.SITE_PREFIX + "community.json"])
        self.assertEqual([e["id"] for e in community["events"]], ["hike-2026-12-05"])


class RejectedSourceWritesNothingTests(unittest.TestCase):
    """Malformed source documents fail as content-invalid (exit 2) and write no output."""

    EVENT = {"id": "hike-2026-12-05", "title": "Morning walk", "startsAt": "2026-12-05T09:00:00-08:00",
             "timezone": "America/Los_Angeles", "status": "scheduled"}

    def assertGeneratorRejects(self, name, mutate, expect):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        repo.edit(name, mutate)
        with self.assertRaises(ContentError) as ctx:
            load_and_validate(repo.root / "hass" / "content", repo.root / "storefront-mockup")
        self.assertTrue(any(expect in p for p in ctx.exception.problems), ctx.exception.problems)
        site_before = {rel: _sha(repo.root / rel) for rel in GENERATED}
        with tempfile.TemporaryDirectory(prefix="hass-h01-reject-") as tmp:
            out = Path(tmp) / "out"
            code, text = _quiet(sitegen.main, ["--out", str(out), "--repo", str(repo.root)])
            self.assertEqual(code, 2, text)
            self.assertIn("content invalid:", text)
            self.assertFalse(out.exists(), "rejected content must not write output")
        code, text = _quiet(sitegen.main, ["--write", "--repo", str(repo.root)])
        self.assertEqual(code, 2, text)
        self.assertEqual(site_before, {rel: _sha(repo.root / rel) for rel in GENERATED})

    def test_unknown_root_fields_are_rejected(self):
        cases = {
            "products price": ("products.json", lambda d: d.update(price=4.5), "products.json: unknown field 'price'"),
            "products private note": ("products.json", lambda d: d.update(privateNote="fixture-only"),
                                      "products.json: unknown field 'privateNote'"),
            "makers price": ("makers.json", lambda d: d.update(price=4.5), "makers.json: unknown field 'price'"),
            "makers private note": ("makers.json", lambda d: d.update(privateNote="fixture-only"),
                                    "makers.json: unknown field 'privateNote'"),
            "products payload missing": ("products.json", lambda d: d.pop("products"),
                                         "products.json: missing field 'products'"),
        }
        for case, (name, mutate, expect) in cases.items():
            with self.subTest(case=case):
                self.assertGeneratorRejects(name, mutate, expect)

    def test_non_string_event_and_route_idea_ids_are_rejected(self):
        def idea_id(value):
            return lambda d: d["routeIdeas"][0].update(id=value)

        def event(**changes):
            return lambda d: d["events"].append({**self.EVENT, **changes})

        cases = {
            "route idea array id": (idea_id([]), "routeIdeas[0]: invalid or duplicate id []"),
            "route idea object id": (idea_id({}), "routeIdeas[0]: invalid or duplicate id {}"),
            "event array id": (event(id=[]), "events[0]: invalid or duplicate id []"),
            "event object id": (event(id={"a": 1}), "events[0]: invalid or duplicate id {'a': 1}"),
            "event array trailId": (event(trailId=[]), "trailId [] is not a route idea"),
        }
        for case, (mutate, expect) in cases.items():
            with self.subTest(case=case):
                self.assertGeneratorRejects("community.json", mutate, expect)


class MigrationCheckTests(unittest.TestCase):
    def test_checkout_preserves_baseline(self):
        failures, report = migration_check.run_checks(REPO_ROOT)
        self.assertEqual(failures, [])
        self.assertEqual(report["baselineListings"], 170)
        self.assertEqual(report["baselineListingsPreserved"], 170)
        self.assertEqual(report["baselineMakers"], 26)
        self.assertGreaterEqual(report["makers"], report["baselineMakers"])  # HASS-LIVE-ADD-1: a live add may add a maker
        self.assertEqual(report["sourceLinksPreserved"], report["baselineSourceLinks"])
        self.assertEqual(report["heldProducts"], 2)
        self.assertEqual(report["heldExcluded"], ["photo-product-040", "photo-product-133"])

    def test_baseline_records_the_migrated_site(self):
        baseline = json.loads((CONTENT_DIR / "migration-baseline.json").read_text("utf-8"))
        self.assertEqual(baseline["listings"]["count"], 170)
        self.assertEqual(len(set(baseline["listings"]["ids"])), 170)
        self.assertEqual(baseline["makers"]["count"], 26)
        self.assertEqual(len(set(baseline["sources"]["makerUrls"].values())), 26)
        self.assertEqual(baseline["held"]["ids"], ["photo-product-040", "photo-product-133"])

    def _failures_after(self, name, mutate):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        repo.edit(name, mutate)
        _quiet(sitegen.main, ["--write", "--repo", str(repo.root)])
        failures, _ = migration_check.run_checks(repo.root)
        return failures

    def test_isolated_copy_passes(self):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        self.assertEqual(migration_check.run_checks(repo.root)[0], [])

    def test_deleted_listing_fails(self):
        failures = self._failures_after("products.json", lambda d: d["products"].pop(5))
        self.assertTrue(any("baseline listings deleted" in f for f in failures), failures)

    def test_hidden_listing_is_still_preserved(self):
        failures = self._failures_after("products.json", lambda d: d["products"][5].update(status="hidden"))
        self.assertEqual(failures, [])

    def test_restoring_held_product_fails(self):
        def restore(d):
            for p in d["products"]:
                if p["id"] == "photo-product-040":
                    p.pop("hold")
                    p.update(status="active", description="Cheese.", producerKey=None, displayBrand="Sierra Nevada")
        failures = self._failures_after("products.json", restore)
        self.assertTrue(any("photo-product-040 is no longer held" in f for f in failures), failures)

    def test_lost_source_link_fails(self):
        failures = self._failures_after(
            "community.json", lambda d: d["routeIdeas"][0].update(sourceUrl="https://example.org/other"))
        self.assertTrue(any("source links no longer recorded" in f for f in failures), failures)

    def test_hand_edited_site_file_fails(self):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        page = repo.root / "storefront-mockup" / "producers.json"
        page.write_bytes(page.read_bytes() + b"\n")
        failures, _ = migration_check.run_checks(repo.root)
        self.assertTrue(any("differ from generated output" in f for f in failures), failures)


if __name__ == "__main__":
    unittest.main()
