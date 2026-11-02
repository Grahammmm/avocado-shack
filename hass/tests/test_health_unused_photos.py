"""AV0022-14 (H19/H21): health --writer names photo-<sha> copies no product's image uses (info only, read-only).
WriterRepo temp repos only; the worktree's assets symlink (to the real repo) is replaced by a committed temp dir.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""
import json, os, shutil, unittest  # noqa: E401
from unittest import mock

from hass import health
from hass.tests import test_health_writer as hw
from hass.tests.test_editor import WriterRepo, git
from hass.tests.test_health import SETTINGS

A, B = "photo-0123456789abcdef.jpg", "photo-fedcba9876543210.png"


class UnusedPhotosTest(unittest.TestCase):
    config, run_health = hw.HealthWriterTest.config, hw.HealthWriterTest.run_health

    def setUp(self):
        self.repo = WriterRepo()
        self.addCleanup(self.repo.cleanup)
        self.tmp = self.repo.state.parent
        self.config({"worktree": str(self.repo.wt), "settings": SETTINGS})
        assets = self.repo.wt / "storefront-mockup" / "assets"
        assets.unlink()  # never write through the fixture's symlink into the real repo
        self.dir, self.products = assets / "products", self.repo.wt / "hass" / "content" / "products.json"
        self.dir.mkdir(parents=True)
        self.commit()

    def commit(self, *names, images=()):
        for name in names: (self.dir / name).write_bytes(b"x")
        doc = json.loads(self.products.read_text("utf-8"))
        for i, (image, status) in enumerate(images): doc["products"][i].update(image=image, status=status)
        self.products.write_text(json.dumps(doc), "utf-8")
        git(self.repo.wt, "add", "-A")
        git(self.repo.wt, "commit", "-q", "--allow-empty", "-m", "photos")

    def unused(self, *extra):
        code, doc, _ = self.run_health("--writer", *extra)
        return code, doc, [p["detail"] for p in doc["info"] if p["check"] == "photo-unused"]

    def test_clean_worktree_has_no_entry(self):  # 1
        base = self.unused()
        self.assertEqual((base[0], base[1]["ok"], base[2]), (0, True, []))
        self.commit(A, B, "photo-product-001.webp", images=[(f"assets/products/{A}", "active"),
                                                            (f"assets/products/{B}", "active")])
        code, doc, found = self.unused()
        self.assertEqual((code, doc["ok"], doc["fingerprint"], found), (0, True, base[1]["fingerprint"], []))

    def test_one_unused_is_info_only(self):  # 2, 8
        seen = str(self.tmp / "health.seen")
        before = self.unused("--seen", seen)
        self.commit(A)
        code, doc, found = self.unused("--seen", seen)
        self.assertEqual(found, [f"1 unused: {A}"])
        self.assertEqual((code, doc["ok"], doc["notify"], doc["fingerprint"], doc["problems"]),
                         (before[0], True, False, before[1]["fingerprint"], before[1]["problems"]))
        self.assertTrue(before[1]["notify"] and (self.dir / A).is_file())  # notify from the first run; never deleted
        (self.repo.wt / "hass" / "untracked.txt").write_text("x")  # with a problem: info still leaves the exit code
        self.assertEqual(self.unused()[::2], (1, [f"1 unused: {A}"]))

    def test_more_than_five_sorted_then_count(self):  # 3
        names = [f"photo-{i:016x}.{'png' if i % 2 else 'jpg'}" for i in (6, 3, 0, 5, 2, 4, 1)]
        self.commit(*names[:5])
        self.assertEqual(self.unused()[2], [f"5 unused: {', '.join(sorted(names[:5]))}"])
        self.commit(*names[5:])
        self.assertEqual(self.unused()[2], [f"7 unused: {', '.join(sorted(names)[:5])} and 2 more"])

    def test_only_set_photo_names_count(self):  # 4
        for name in ("photo-product-001.webp", "photo-0123456789abcdef.webp", "photo-0123456789ABCDEF.jpg",
                     "photo-0123.jpg", f"{A}.bak", f"x{A}", f"{A}\n"):
            (self.dir / name).write_bytes(b"x")
        (self.dir / B).mkdir()
        (self.dir / B / "inside.txt").write_text("x")
        (self.repo.state.parent / "outside.jpg").write_bytes(b"x")
        (self.dir / A).symlink_to(self.repo.state.parent / "outside.jpg")
        self.commit()
        self.assertEqual(self.unused()[::2], (0, []))

    def test_hidden_product_still_uses_its_photo(self):  # 5
        self.commit(A, images=[(f"assets/products/{A}", "hidden")])
        self.assertEqual(self.unused()[::2], (0, []))

    def test_without_writer_never_lists_products(self):  # 6
        self.commit(A)
        with mock.patch.object(health.os, "scandir", wraps=os.scandir) as spy:
            doc = self.run_health()[1]
        self.assertFalse([c for c in spy.call_args_list if c.args and "products" in str(c.args[0])])
        self.assertNotIn("photo-unused", [p["check"] for p in doc["info"]])
        with mock.patch.object(health.os, "scandir", wraps=os.scandir) as spy:
            self.assertEqual(self.unused()[2], [f"1 unused: {A}"])  # positive control: --writer does list it
        self.assertTrue([c for c in spy.call_args_list if c.args and str(c.args[0]).endswith("products")])

    def test_unreadable_inputs_give_no_entry(self):  # 7
        self.commit(A)
        for text in ("{", "[]", "{}", '{"products": 3}', '{"products": null}', "[" * 100000):
            with self.subTest(text=text[:20]):
                self.products.write_text(text, "utf-8")
                code, doc, found = self.unused()
                self.assertEqual((code, found), (1, []))  # the uncommitted edit: writer still reported
                self.assertIn("writer", [p["check"] for p in doc["problems"]])
        git(self.repo.wt, "checkout", "-q", "--", "hass/content/products.json")
        shutil.rmtree(self.dir)
        self.assertEqual(self.unused()[2], [])
        self.config("{")
        self.assertEqual(self.unused()[2], [])


if __name__ == "__main__":
    unittest.main()
