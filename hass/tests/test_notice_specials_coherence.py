"""RF1830-12: the generated-file check never accepts a notice/specials mix no single calendar day could produce.

Everything is synthetic: external trees under a temp root (templates linked), a patched checker clock, no server.
Run: python3 -m unittest hass.tests.test_notice_specials_coherence -v
"""

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from hass import notice, sitegen
from hass.content_model import REPO_ROOT, load_content, validate_store

INDEX = "storefront-mockup/index.html"
HIKE = "storefront-mockup/hike/index.html"
CATALOG = "storefront-mockup/catalog-products.js"
TODAY = date(2026, 11, 11)
NOTICE_TEXT, DEAL = "Closed for the harvest festival", "Two bunches for five"
BASE = load_content()


def d(n):
    return date(2026, 11, n)


def special(n, start, end, deal=DEAL):
    return {"id": f"sp-{n}", "title": f"Special {n}", "deal": deal, "start": d(start).isoformat(),
            "end": d(end).isoformat(), "order": n}


def make_content(notice_until=None, specials=(), **extra):
    content = copy.deepcopy(BASE)
    content.store.pop("selection_checked_on", None)
    if notice_until is not None:
        content.store["notice"] = {"text": NOTICE_TEXT, "until": notice_until.isoformat()}
    if specials:
        content.store["specials"] = [dict(s) for s in specials]
    content.store.update(extra)
    problems = []
    validate_store(problems, content.store, today=TODAY, product_ids={p["id"] for p in content.products})
    assert problems == [], problems
    return content


def day_pages(content, days=range(1, 12)):
    return {n: sitegen.render(content, today=d(n))[INDEX] for n in days}


class Tree:
    """An external repo root: linked templates, real generated files, everything else linked to the checkout."""

    def __init__(self, test, content):
        self.root = Path(tempfile.mkdtemp(prefix="rf1830-", dir=os.environ.get("TMPDIR")))
        test.addCleanup(lambda: self._remove())
        self.content = content
        (self.root / "hass" / "content").mkdir(parents=True)
        os.symlink(REPO_ROOT / "hass" / "templates", self.root / "hass" / "templates")
        for name in ("products", "makers", "community"):
            (self.root / "hass" / "content" / f"{name}.json").write_bytes((REPO_ROOT / "hass" / "content" / f"{name}.json").read_bytes())
        (self.root / "hass" / "content" / "store.json").write_text(json.dumps(content.store, indent=2))
        site = self.root / "storefront-mockup"
        site.mkdir()
        generated = {Path(p).relative_to("storefront-mockup") for p in sitegen.render(content, today=TODAY)}
        top = {p.parts[0] for p in generated}
        for entry in (REPO_ROOT / "storefront-mockup").iterdir():
            if entry.name not in top:
                os.symlink(entry, site / entry.name)
        (site / "hike").mkdir()
        for entry in (REPO_ROOT / "storefront-mockup" / "hike").iterdir():
            if Path("hike", entry.name) not in generated:
                os.symlink(entry, site / "hike" / entry.name)

    def _remove(self):
        for path in sorted(self.root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_symlink() or path.is_file():
                path.unlink()
            else:
                path.rmdir()
        self.root.rmdir()

    def save(self, today=TODAY, notice_today=None, specials_today=None):
        files = sitegen.render(self.content, self.root / "hass" / "templates", today=today,
                               notice_today=notice_today, specials_today=specials_today)
        for rel, data in files.items():
            path = self.root / rel
            if path.is_symlink():
                path.unlink()
            path.write_bytes(data)
        return files

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*")
                if p.is_file() and not p.is_symlink() and "content" not in p.parts}

    def stale(self):
        with mock.patch.object(sitegen, "shop_today", return_value=TODAY):
            return notice.stale_paths(self.content, self.root)


class CoherenceTests(unittest.TestCase):
    def test_nonoverlapping_notice_and_special_never_form_a_historical_artifact(self):
        content = make_content(d(5), [special(1, 7, 9)])
        tree = Tree(self, content)
        files = tree.save(notice_today=d(5), specials_today=d(8))
        page = files[INDEX].decode("utf-8")
        self.assertIn('class="home-notice"', page)
        self.assertIn("weekly-specials", page)
        self.assertLess(d(5), d(7))  # the notice ended before the special began
        self.assertNotIn(files[INDEX], day_pages(content).values())  # no real day produced this page
        self.assertEqual(tree.stale(), [INDEX])

    def test_real_before_notice_expiry_and_later_special_phases_stay_consistent(self):
        content = make_content(d(5), [special(1, 7, 9)])
        tree = Tree(self, content)
        tree.save(notice_today=d(5), specials_today=d(5))
        self.assertIn('class="home-notice"', (tree.root / INDEX).read_text())
        self.assertEqual(tree.stale(), [])
        tree.save(notice_today=d(8), specials_today=d(8))
        self.assertIn("weekly-specials", (tree.root / INDEX).read_text())
        self.assertEqual(tree.stale(), [])
        tree.save()
        self.assertEqual(tree.stale(), [])

    def test_overlapping_windows_allow_only_real_section_combinations(self):
        content = make_content(d(9), [special(1, 7, 13), special(2, 2, 3, "Early bird eggs")])
        tree = Tree(self, content)
        real = set(day_pages(content).values())
        days = range(2, 11)
        for nd in days:
            for sd in days:
                tree.save(notice_today=d(nd), specials_today=d(sd))
                page = (tree.root / INDEX).read_bytes()
                with self.subTest(notice_day=nd, specials_day=sd):
                    self.assertEqual(tree.stale(), [] if page in real else [INDEX])
        tree.save(notice_today=d(10), specials_today=d(3))  # no notice but a long-gone special: impossible
        self.assertEqual(tree.stale(), [INDEX])
        tree.save(notice_today=d(10), specials_today=d(10))  # notice gone, special ongoing: history kept
        self.assertNotIn("home-notice", (tree.root / INDEX).read_text())
        self.assertEqual(tree.stale(), [])

    def test_historical_sections_do_not_rewind_selection_freshness(self):
        content = make_content(d(5), [special(1, 7, 9)], selection_checked_on=d(1).isoformat())
        tree = Tree(self, content)
        tree.save(notice_today=d(5), specials_today=d(5))
        self.assertEqual(tree.stale(), [])  # the same dated sections with actual-today freshness pass
        stale_note = (tree.root / INDEX).read_text()
        self.assertIn("more than a week ago", stale_note)
        tree.save(today=d(5), notice_today=d(5), specials_today=d(5))  # old, still-fresh note
        self.assertNotIn("more than a week ago", (tree.root / INDEX).read_text())
        self.assertEqual(tree.stale(), [INDEX])
        self.assertEqual(content.store["selection_checked_on"], d(1).isoformat())

    def test_coherent_tolerance_does_not_mask_damage_or_missing_targets(self):
        content = make_content(d(5), [special(1, 7, 9)])
        tree = Tree(self, content)

        def damaged(edit):
            tree.save(notice_today=d(5), specials_today=d(5))
            path = tree.root / INDEX
            path.write_bytes(edit(path.read_bytes()))
            return tree.stale()

        self.assertEqual(damaged(lambda b: b.replace(NOTICE_TEXT.encode(), b"Wrong notice")), [INDEX])
        self.assertEqual(damaged(lambda b: b.replace(b'role="status"', b'role="alert"')), [INDEX])
        self.assertEqual(damaged(lambda b: b + b"<!-- extra -->"), [INDEX])
        tree.save(notice_today=d(8), specials_today=d(8))
        path = tree.root / INDEX
        path.write_bytes(path.read_bytes().replace(DEAL.encode(), b"Free everything"))
        self.assertEqual(tree.stale(), [INDEX])
        tree.save(notice_today=d(5), specials_today=d(5))
        (tree.root / CATALOG).write_bytes(b"corrupt")
        self.assertEqual(tree.stale(), [CATALOG])
        tree.save(notice_today=d(5), specials_today=d(5))
        (tree.root / INDEX).unlink()
        self.assertEqual(tree.stale(), [INDEX])
        tree.save(notice_today=d(5), specials_today=d(5))
        (tree.root / INDEX).unlink()
        os.symlink(tree.root / HIKE, tree.root / INDEX)
        self.assertEqual(tree.stale(), [INDEX])
        tree.save(notice_today=d(5), specials_today=d(5))
        real = tree.root / "storefront-mockup" / "hike"
        moved = tree.root / "hike-real"
        os.rename(real, moved)
        os.symlink(moved, real)
        self.assertEqual(tree.stale(), [HIKE])
        os.unlink(real)
        os.rename(moved, real)

    def test_calendar_edges_empty_sections_and_readonly(self):
        for content in (make_content(), make_content(specials=[]), make_content(d(11)), make_content(d(5))):
            tree = Tree(self, content)
            tree.save()
            before, store = tree.snapshot(), copy.deepcopy(content.store)
            self.assertEqual(tree.stale(), [])
            self.assertEqual((tree.snapshot(), content.store), (before, store))
        # a duplicate candidate day (notice end == special start == special end) renders once; no span is scanned
        content = make_content(d(5), [special(1, 5, 5), special(2, 5, 5)])
        tree = Tree(self, content)
        tree.save(notice_today=d(5), specials_today=d(5))
        with mock.patch.object(sitegen, "render", wraps=sitegen.render) as spy:
            self.assertEqual(tree.stale(), [])
        self.assertLessEqual(spy.call_count, 1 + 6)
        # calendar ends: no successor overflow, and nothing is rendered for today or later
        content = make_content()
        content.store["notice"] = {"text": NOTICE_TEXT, "until": date.max.isoformat()}
        tree = Tree(self, content)
        tree.save(today=date.max)
        with mock.patch.object(sitegen, "shop_today", return_value=date.max):
            self.assertEqual(notice.stale_paths(content, tree.root), [])
        content.store["notice"]["until"] = date.min.isoformat()
        tree.content = content
        tree.save(today=date.max)
        with mock.patch.object(sitegen, "shop_today", return_value=date.max):
            self.assertEqual(notice.stale_paths(content, tree.root), [])
        tree.save(today=date.max, notice_today=date.min)  # the notice's own last day is a valid earlier artifact
        with mock.patch.object(sitegen, "shop_today", return_value=date.max):
            self.assertEqual(notice.stale_paths(content, tree.root), [])

    def test_sitegen_check_rejects_impossible_tree_and_accepts_real_tree(self):
        content = make_content(d(5), [special(1, 7, 9)])
        tree = Tree(self, content)

        def check():
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(sitegen, "shop_today", return_value=TODAY), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = sitegen.main(["--check", "--repo", str(tree.root)])
            return code, out.getvalue(), err.getvalue()

        tree.save(notice_today=d(5), specials_today=d(8))
        before = tree.snapshot()
        code, out, err = check()
        self.assertEqual((code, err), (1, ""))
        self.assertIn("  " + INDEX, out.splitlines())
        self.assertEqual(tree.snapshot(), before)
        for day in (5, 8):
            tree.save(notice_today=d(day), specials_today=d(day))
            code, out, err = check()
            self.assertEqual((code, err), (0, ""))
            self.assertTrue(out.startswith("ok: "), out)


if __name__ == "__main__":
    unittest.main()
