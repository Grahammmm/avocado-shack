"""RF1530-16: notice.stale_paths keeps the exact pre-start specials artifact consistent on and after the first day.

Every tree is synthetic and external (a temp dir); only the checker clock is injected. Run:
python3 -m unittest hass.tests.test_notice_specials_prestart -v
"""

import contextlib, copy, io, json, os, tempfile, unittest  # noqa: E401
from datetime import date
from pathlib import Path
from unittest import mock

from hass import notice, sitegen
from hass.content_model import REPO_ROOT, load_content, validate_store

BASE = load_content()
INDEX = "storefront-mockup/index.html"
D10, D11, D12, D16 = date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12), date(2026, 11, 16)


def sp(n, start, end):
    return {"id": f"sp-{n}", "title": f"Synthetic {n}", "deal": f"Free sample {n}", "start": start, "end": end, "order": n}


def make(*items, **store_extra):
    content = copy.deepcopy(BASE)
    content.store.update(store_extra)
    content.store["specials"] = list(items)
    problems = []
    validate_store(problems, content.store, product_ids={p["id"] for p in content.active_products()})
    assert problems == [], problems
    return content


def check(content, root, today):
    with mock.patch.object(sitegen, "shop_today", return_value=today):
        return notice.stale_paths(content, root)


class Tree(tempfile.TemporaryDirectory):
    """A scratch root holding the generated files rendered for ``saved`` day (templates linked read-only)."""

    def __init__(self, content, saved):
        super().__init__()
        self.root = Path(self.name)
        (self.root / "hass").mkdir()
        (self.root / "hass" / "templates").symlink_to(REPO_ROOT / "hass" / "templates", target_is_directory=True)
        self.files = sitegen.render(content, today=saved)
        for rel, data in self.files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(data)

    def __enter__(self):
        return self

    def snapshot(self):
        return {rel: ((self.root / rel).read_bytes(), (self.root / rel).stat().st_mtime_ns) for rel in self.files}


class PrestartTests(unittest.TestCase):
    def test_prestart_artifact_stays_consistent_on_first_and_later_active_days(self):
        content = make(sp(1, "2026-11-11", "2026-11-15"))
        with Tree(content, D10) as tree:
            self.assertNotIn(b"Synthetic 1", tree.files[INDEX])
            self.assertIn(b"Synthetic 1", sitegen.render(content, today=D11)[INDEX])
            before = tree.snapshot()
            for today in (D10, D11, D12, D16):
                with self.subTest(today=today):
                    self.assertEqual(check(content, tree.root, today), [])
            self.assertEqual(tree.snapshot(), before)

    def test_cli_check_accepts_the_prestart_artifact_on_its_first_day(self):
        content = make(sp(1, "2026-11-11", "2026-11-15"))
        with Tree(content, D10) as tree:
            root = tree.root
            (root / "hass" / "content").mkdir()
            for src in (REPO_ROOT / "hass" / "content").iterdir():
                (root / "hass" / "content" / src.name).symlink_to(src)
            (root / "hass" / "content" / "store.json").unlink()
            (root / "hass" / "content" / "store.json").write_text(json.dumps(content.store), encoding="utf-8")
            for dirpath, _dirs, names in os.walk(REPO_ROOT / "storefront-mockup"):
                target = root / Path(dirpath).relative_to(REPO_ROOT)
                target.mkdir(parents=True, exist_ok=True)
                for name in names:
                    if not (target / name).exists():
                        (target / name).symlink_to(Path(dirpath) / name)
            for today, expected in ((D11, 0), (D12, 0)):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(sitegen, "shop_today", return_value=today), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = sitegen.main(["--check", "--repo", str(root)])
                self.assertEqual(code, expected, (today, out.getvalue(), err.getvalue()))

    def test_overlapping_starts_reconstruct_each_prior_subset(self):
        one, two = sp(1, "2026-11-11", "2026-11-20"), sp(2, "2026-11-13", "2026-11-20")
        content = make(one, two)
        only_first = make(one)
        with Tree(only_first, D12) as tree:  # saved while only the first card was active
            self.assertEqual(tree.files[INDEX].count(b"<h3>"), 1)
            self.assertEqual(check(content, tree.root, date(2026, 11, 14)), [])
        with Tree(content, D12) as tree:  # same phase as the real current content
            self.assertEqual(tree.files[INDEX].count(b"<h3>"), 1)
        # a phase that never existed: both cards' content but only the second (start 13th) card shown
        only_second = make(sp(2, "2026-11-11", "2026-11-20"))
        with Tree(only_second, D12) as tree:
            self.assertEqual(check(content, tree.root, date(2026, 11, 14)), [INDEX])

    def test_future_active_page_is_not_an_earlier_artifact(self):
        content = make(sp(1, "2026-11-11", "2026-11-15"))
        with Tree(content, D11) as tree:  # generated with the future card showing
            self.assertIn(b"Synthetic 1", tree.files[INDEX])
            self.assertEqual(check(content, tree.root, D10), [INDEX])
        with Tree(content, D10) as tree:
            self.assertEqual(check(content, tree.root, D10), [])  # start after today: no predecessor needed
        later = make(sp(1, "2026-11-12", "2026-11-15"))
        with Tree(later, D11) as tree:  # start tomorrow: card not yet active, page is the current render
            self.assertEqual(check(later, tree.root, D11), [])

    def test_prestart_tolerance_does_not_mask_damage(self):
        content = make(sp(1, "2026-11-11", "2026-11-15"))
        edits = {
            "deal": lambda b: b.replace(b"</body>", b'<p class="special-deal">Free sample 2</p></body>'),
            "text": lambda b: b + b"<!-- x -->",
        }
        for name, fn in edits.items():
            with self.subTest(name), Tree(content, D10) as tree:
                (tree.root / INDEX).write_bytes(fn((tree.root / INDEX).read_bytes()))
                self.assertEqual(check(content, tree.root, D11), [INDEX])
        with self.subTest("catalog"), Tree(content, D10) as tree:
            catalog = tree.root / "storefront-mockup/catalog-products.js"
            catalog.write_bytes(catalog.read_bytes() + b" ")
            self.assertEqual(check(content, tree.root, D11), ["storefront-mockup/catalog-products.js"])
        with self.subTest("missing"), Tree(content, D10) as tree:
            (tree.root / INDEX).unlink()
            self.assertEqual(check(content, tree.root, D11), [INDEX])
        with self.subTest("file symlink"), Tree(content, D10) as tree:
            target = tree.root / INDEX
            referent = tree.root / "elsewhere.html"
            referent.write_bytes(target.read_bytes())
            target.unlink()
            target.symlink_to(referent)
            self.assertEqual(check(content, tree.root, D11), [INDEX])
        with self.subTest("parent symlink"), Tree(content, D10) as tree:
            hike = tree.root / "storefront-mockup" / "hike"
            moved = tree.root / "moved-hike"
            hike.rename(moved)
            hike.symlink_to(moved, target_is_directory=True)
            self.assertIn("storefront-mockup/hike/index.html", check(content, tree.root, D11))

    def test_freshness_clock_does_not_rewind_with_specials(self):
        content = make(sp(1, "2026-11-15", "2026-11-20"), selection_checked_on="2026-11-10")
        # saved on the 12th (fresh), checked on the 18th: the old fresh sentence must not be accepted
        with Tree(content, D12) as tree:
            self.assertNotIn(b"more than a week ago", tree.files[INDEX])
            self.assertEqual(check(content, tree.root, date(2026, 11, 18)), [INDEX])
        # an otherwise old specials phase rendered with the current (stale) freshness passes
        old_phase = copy.deepcopy(content)
        with Tree(old_phase, date(2026, 11, 18)) as tree:
            self.assertEqual(check(content, tree.root, date(2026, 11, 18)), [])
        # expired notice plus pre-start special
        both = make(sp(1, "2026-11-11", "2026-11-15"),
                    notice={"text": "Closed Monday", "until": "2026-11-10"})
        with Tree(both, D10) as tree:
            self.assertIn(b"Closed Monday", tree.files[INDEX])
            self.assertEqual(check(both, tree.root, D11), [])

    def test_calendar_min_max_duplicate_starts_and_readonly(self):
        # date.min: no predecessor, no underflow
        content = make(sp(1, "0001-01-01", "0001-01-02"))
        with Tree(content, date.max) as tree:
            check(content, tree.root, date.min)
        # date.max start reached: representable predecessor is the pre-start phase
        content = make(sp(1, "9999-12-31", "9999-12-31"))
        with Tree(content, date(9999, 12, 30)) as tree:
            before = tree.snapshot()
            self.assertEqual(check(content, tree.root, date.max), [])
            self.assertEqual(tree.snapshot(), before)
            # start in the future (relative to today): no new predecessor
            self.assertEqual(check(content, tree.root, date(9999, 12, 29)), [])
        with Tree(content, date.max) as tree:  # page with the card, checked before it starts
            self.assertEqual(check(content, tree.root, date(9999, 12, 29)), [INDEX])
        # duplicate starts and no specials
        dup = make(sp(1, "2026-11-11", "2026-11-15"), sp(2, "2026-11-11", "2026-11-15"))
        with Tree(dup, D10) as tree:
            self.assertEqual(check(dup, tree.root, D12), [])
        none = make()
        with Tree(none, D10) as tree:
            self.assertEqual(check(none, tree.root, D12), [])
        # stale_paths never mutates content
        snap = copy.deepcopy(dup.store)
        with Tree(dup, D10) as tree:
            check(dup, tree.root, D12)
        self.assertEqual(dup.store, snap)


if __name__ == "__main__":
    unittest.main()
