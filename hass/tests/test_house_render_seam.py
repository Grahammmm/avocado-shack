"""SKILLS-PIC-1 tests: the house-style render inside ``photos.install``, behind the ``houseRender`` setting.

* flag off (absent, false, or anything but the JSON value true): the committed bytes are exactly the metadata-free web copy,
  as before;
* flag on: the committed file is the house picture (800x800 JPEG, no metadata, named photo-<sha16>.jpg), the same input gives
  the same bytes, and the bytes the skill previews with ``house_check`` are the bytes the editor commits;
* a photo that cannot be made house-style (busy background, too dark, blurry, too small) is not installed: the op is refused
  with a plain sentence asking for a retake and nothing is written;
* the home page hero keeps the owner's pixels (D6).

Picture tests need Pillow (pinned in CI by tests/test_pillow_ci.py) and are skipped without it. The editor tests use the same
PhotoRepo harness as test_set_photo; the unit tests use a bare context and a private media root. No network, no live service.
"""
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import house_style as hs, media, newitem_render, voice
from hass.ops import Refused, photos

try:
    from PIL import Image, ImageFilter
    from hass import newitem_synthetic as syn
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

ALT = "Cal Poly honey in a jar"
CASES = dict(syn.cases()) if HAVE_PIL else {}


def photo(name):
    return syn.make_photo(**CASES[name])


def blurred(data, radius):
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").filter(ImageFilter.GaussianBlur(radius)).save(out, "JPEG", quality=84)
    return out.getvalue()


def cutout_with_rgb(data, change):
    """A PNG of the transparent-cut-out fixture with its colour channels changed by ``change`` and its alpha kept as it was."""
    original = Image.open(io.BytesIO(data)).convert("RGBA")
    out = io.BytesIO()
    changed = change(original.convert("RGB")).convert("RGBA")
    changed.putalpha(original.getchannel("A"))
    changed.save(out, "PNG")
    return out.getvalue()


def darkened(data, factor):
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").point(lambda v: round(v * factor)).save(out, "JPEG", quality=84)
    return out.getvalue()


class Bare:
    """A media root and an install context with no editor: enough to call photos.install and photos.house_check."""

    def __init__(self, test, **settings):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.media, self.site = Path(tmp.name) / "media", Path(tmp.name) / "site"
        (self.site / "assets" / "products").mkdir(parents=True)
        self.settings = {"mediaRoot": str(self.media), **settings}
        self.ctx = SimpleNamespace(settings=self.settings, site_dir=self.site, assets={})

    def store(self, data):
        return media.store_original(self.media, data, received_at="2026-11-08T18:00:00+00:00", source="fixture")["sha256"]

    def web(self, sha):
        return Path(media.web_copy(self.media, sha)["path"]).read_bytes()


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class FlagTests(unittest.TestCase):
    def test_flag_off_installs_the_web_copy_unchanged(self):
        for label, settings in (("absent", {}), ("false", {"houseRender": False}), ("string", {"houseRender": "true"}),
                                ("one", {"houseRender": 1}), ("null", {"houseRender": None})):
            for name in ("jar-white-sheet", "bottle-bench-png", "jar-dark-wood"):  # even a busy photo: the old behaviour
                with self.subTest(flag=label, photo=name):
                    bare = Bare(self, **settings)
                    sha = bare.store(photo(name))
                    ext = "png" if name.endswith("png") else "jpg"
                    target = photos.install(bare.ctx, sha, ALT)
                    self.assertEqual(target, f"assets/products/photo-{sha[:16]}.{ext}")
                    self.assertEqual(bare.ctx.assets[target], bare.web(sha))

    def test_flag_on_installs_a_house_picture_named_by_the_original(self):
        for name in ("jar-white-sheet", "bottle-bench-png", "jar-phone-rotated", "jar-cutout-alpha"):
            with self.subTest(photo=name):
                bare = Bare(self, houseRender=True)
                sha = bare.store(photo(name))
                target = photos.install(bare.ctx, sha, ALT)
                self.assertEqual(target, f"assets/products/photo-{sha[:16]}.jpg")  # D1, also for a PNG original
                data = bare.ctx.assets[target]
                self.assertNotEqual(data, bare.web(sha))
                im = Image.open(io.BytesIO(data))
                self.assertEqual((im.format, im.size, im.mode), ("JPEG", (800, 800), "RGB"))
                self.assertFalse(im.getexif() or im.info.get("exif") or im.info.get("icc_profile"))
                self.assertFalse(syn.has_exif_location(data))
                self.assertTrue(hs.check_image(data)["pass"])

    def test_same_input_same_bytes(self):
        bare = Bare(self, houseRender=True)
        sha = bare.store(photo("bottle-grey-wall-tilted"))
        first = photos.install(bare.ctx, sha, ALT)
        data = bare.ctx.assets[first]
        photos._house.cache_clear()  # a fresh render, not the cached one
        again = Bare(self, houseRender=True)
        self.assertEqual(again.store(photo("bottle-grey-wall-tilted")), sha)
        self.assertEqual(photos.install(again.ctx, sha, ALT), first)
        self.assertEqual(again.ctx.assets[first], data)
        self.assertEqual(hashlib.sha256(again.ctx.assets[first]).hexdigest(), hashlib.sha256(data).hexdigest())

    def test_orientation_tag_is_applied_not_kept(self):
        bare = Bare(self, houseRender=True)
        sha = bare.store(photo("jar-phone-rotated"))
        data = bare.ctx.assets[photos.install(bare.ctx, sha, ALT)]
        self.assertIsNone(Image.open(io.BytesIO(data)).getexif().get(0x0112))
        self.assertTrue(hs.check_image(data)["pass"])

    def test_check_gives_the_same_bytes_install_commits(self):
        bare = Bare(self, houseRender=True)
        sha = bare.store(photo("jar-white-sheet"))
        verdict = photos.house_check(bare.settings, sha)
        self.assertTrue(verdict["ok"])
        self.assertEqual((verdict["problems"], verdict["reason"]), ([], None))
        self.assertEqual(bare.ctx.assets.get("x"), None)
        target = photos.install(bare.ctx, sha, ALT)
        self.assertEqual(bare.ctx.assets[target], verdict["jpeg"])

    def test_verdict_is_a_copy(self):
        bare = Bare(self)
        data = bare.web(bare.store(photo("jar-white-sheet")))
        verdict = photos.house_picture(data)
        verdict["problems"].append("x")
        verdict["report"]["x"] = 1
        again = photos.house_picture(data)
        self.assertEqual(again["problems"], [])
        self.assertNotIn("x", again["report"])

    def test_turning_the_flag_on_after_a_raw_install_says_so_plainly(self):
        bare = Bare(self)
        sha = bare.store(photo("jar-white-sheet"))
        target = photos.install(bare.ctx, sha, ALT)
        (bare.site / target).write_bytes(bare.ctx.assets[target])  # as committed earlier, the way it came
        later = SimpleNamespace(settings={**bare.settings, "houseRender": True}, site_dir=bare.site, assets={})
        out = photos.install(later, sha, ALT)
        self.assertEqual(out, Refused(photos.ALREADY_RAW))
        self.assertEqual(later.assets, {})
        again = SimpleNamespace(settings={**bare.settings, "houseRender": True}, site_dir=bare.site, assets={})
        (bare.site / target).write_bytes(photos.house_check(bare.settings, sha)["jpeg"])  # the house picture already there
        self.assertEqual(photos.install(again, sha, ALT), target)  # reused, not rewritten
        self.assertEqual(again.assets, {})

    def test_home_hero_keeps_the_owners_pixels(self):
        bare = Bare(self, houseRender=True)
        sha = bare.store(photo("jar-white-sheet"))
        target = photos.install(bare.ctx, sha, ALT, style=False)
        self.assertEqual(target, f"assets/products/photo-{sha[:16]}.jpg")
        self.assertEqual(bare.ctx.assets[target], bare.web(sha))


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class RetakeTests(unittest.TestCase):
    def verdict(self, data):
        bare = Bare(self, houseRender=True)
        sha = bare.store(data)
        return bare, sha, photos.install(bare.ctx, sha, ALT)

    def assertRetake(self, data, code):
        bare, sha, out = self.verdict(data)
        self.assertIsInstance(out, photos.Retake, out)
        self.assertIsInstance(out, Refused)
        self.assertIn(code, out.problems)
        self.assertEqual(out.reason, photos.RETAKE[out.problems[0]])
        self.assertEqual(bare.ctx.assets, {})  # nothing queued: not installed silently
        self.assertEqual(list((bare.site / "assets" / "products").iterdir()), [])
        check = photos.house_check(bare.settings, sha)
        self.assertFalse(check["ok"])
        self.assertEqual(check["problems"], list(out.problems))
        self.assertEqual(check["reason"], out.reason)
        return out

    def test_busy_backgrounds_are_not_faked(self):
        for name in ("jar-dark-wood", "bag-red-cloth"):
            with self.subTest(photo=name):
                self.assertRetake(photo(name), "busy")

    def test_a_small_photo_is_flagged(self):
        self.assertRetake(photo("bag-bench-small"), "small")

    def test_a_blurry_photo_is_flagged(self):
        sharp = photo("bottle-bench-png")
        self.assertEqual(self.verdict(sharp)[2], "assets/products/photo-%s.jpg" % self.verdict(sharp)[1][:16])
        self.assertRetake(blurred(photo("jar-white-sheet"), 6), "blurry")

    def test_a_dark_photo_is_flagged(self):
        self.assertRetake(darkened(photo("jar-white-sheet"), .3), "dark")

    def test_a_blurry_cutout_is_flagged_and_a_sharp_one_is_not(self):
        sharp = photo("jar-cutout-alpha")
        bare, sha, out = self.verdict(sharp)
        self.assertEqual(out, f"assets/products/photo-{sha[:16]}.jpg")  # the sharp control still installs
        for radius in (6, 12, 24):
            with self.subTest(radius=radius):
                self.assertRetake(cutout_with_rgb(sharp, lambda rgb: rgb.filter(ImageFilter.GaussianBlur(radius))), "blurry")

    def test_a_black_cutout_is_a_plain_dark_retake_not_a_crash(self):
        out = self.assertRetake(cutout_with_rgb(photo("jar-cutout-alpha"), lambda rgb: Image.new("RGB", rgb.size, (0, 0, 0))), "dark")
        self.assertEqual(out.reason, photos.RETAKE["dark"])

    def test_the_renderer_lifts_a_pure_black_subject_without_dividing_by_zero(self):
        made = newitem_render.render(cutout_with_rgb(photo("jar-cutout-alpha"), lambda rgb: Image.new("RGB", rgb.size, (0, 0, 0))))
        self.assertEqual((made["report"]["subject_luma"], made["report"]["exposure_gain"]), (0.0, 1.25))

    def test_a_moderately_dim_photo_is_lifted_not_refused(self):
        bare, sha, out = self.verdict(darkened(photo("jar-white-sheet"), .5))
        self.assertEqual(out, f"assets/products/photo-{sha[:16]}.jpg")

    def test_every_defect_is_listed_and_the_first_one_is_told(self):
        out = self.assertRetake(blurred(darkened(photo("jar-white-sheet"), .3), 6), "dark")
        self.assertEqual(out.problems, ("dark", "blurry"))
        self.assertEqual(out.reason, photos.RETAKE["dark"])

    def test_defects_found_in_the_render_report_are_each_reported(self):
        real = newitem_render.render
        failing = {"jpeg": b"x", "report": {"isolation": "cutout", "scale": 1.0, "subject_luma": 140.0}, "check": {"pass": False}}
        with mock.patch.object(newitem_render, "render", return_value=failing):
            photos._house.cache_clear()
            bare = Bare(self, houseRender=True)
            out = photos.install(bare.ctx, bare.store(photo("jar-white-sheet")), ALT)
        photos._house.cache_clear()
        self.assertEqual(out.problems, ("style",))  # the finished picture fails the house check and nothing else is known
        self.assertEqual(out.reason, photos.RETAKE["style"])
        self.assertIs(newitem_render.render, real)

    def test_every_sentence_for_mike_follows_the_voice_rules(self):
        for text in (*photos.RETAKE.values(), *photos.RENDER_REPLY.values(), photos.MAKE_FAILED, photos.ALREADY_RAW):
            with self.subTest(text=text):
                self.assertEqual(voice.check(text), [])


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class RefusalTests(unittest.TestCase):
    def test_unreadable_or_unsafe_photos_are_refused_with_their_own_plain_reply(self):
        for exc in (media.Refused("unreadable"), newitem_render.Refused("too-many-pixels"), newitem_render.Refused("blank")):
            with self.subTest(exc=repr(exc)), mock.patch.object(photos, "house_picture", side_effect=exc):
                bare = Bare(self, houseRender=True)
                out = photos.install(bare.ctx, bare.store(photo("jar-white-sheet")), ALT)
                self.assertEqual(out, Refused(photos.RENDER_REPLY[exc.code] if isinstance(exc, newitem_render.Refused) else exc.reply))
                self.assertEqual(bare.ctx.assets, {})
                self.assertEqual(voice.check(out.reason), [])

    def test_a_missing_picture_library_or_a_disk_problem_gives_one_fixed_reply(self):
        for exc in (hs.PillowMissing("Pillow is needed (python3 -m pip install Pillow) /usr/lib"), OSError(13, "denied", "/secret/path")):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(photos, "house_picture", side_effect=exc):
                bare = Bare(self, houseRender=True)
                out = photos.install(bare.ctx, bare.store(photo("jar-white-sheet")), ALT)
                self.assertEqual(out, Refused(photos.MAKE_FAILED))
                self.assertNotIn("Pillow", out.reason)
                self.assertNotIn("secret", out.reason)

    def test_bytes_that_are_not_a_photo_never_reach_the_render(self):
        for junk in (b"", b"not a picture", b"\xff\xd8\xff\xe0 truncated", b"\x89PNG\r\n\x1a\n" + b"\0" * 20):
            with self.subTest(junk=junk[:12]):
                with self.assertRaises((media.Refused, newitem_render.Refused)):
                    photos.house_picture(junk)

    def test_the_stored_photo_check_refuses_what_it_cannot_find(self):
        bare = Bare(self, houseRender=True)
        self.assertIsInstance(photos.house_check(bare.settings, "not-a-sha"), Refused)
        self.assertIsInstance(photos.house_check({}, "a" * 64), Refused)
        self.assertIsInstance(photos.house_check(bare.settings, "a" * 64), Refused)  # not in the store


def strip(size, mode="RGB", colour=(240, 238, 230)):
    out = io.BytesIO()
    Image.new(mode, size, colour).save(out, "PNG")
    return out.getvalue()


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class ExtremeAspectTests(unittest.TestCase):
    """A strip (1000x1) has no border ring to measure: it is refused with one fixed reply, never an IndexError."""

    STRIPS = {"wide-opaque": strip((1000, 1)), "tall-opaque": strip((1, 1000)), "wide-short": strip((2000, 10)),
              "wide-with-alpha": strip((1000, 1), "RGBA", (200, 30, 30, 120)), "tall-with-alpha": strip((1, 1000), "RGBA", (200, 30, 30, 120))}

    def test_the_renderer_refuses_a_strip_with_its_own_code(self):
        for name, data in self.STRIPS.items():
            with self.subTest(photo=name), self.assertRaises(newitem_render.Refused) as caught:
                newitem_render.render(data)
            self.assertEqual(caught.exception.code, "too-narrow")

    def test_isolate_alone_refuses_a_strip_too(self):
        with self.assertRaises(newitem_render.Refused) as caught:
            newitem_render.isolate(Image.new("RGB", (1000, 1), (240, 238, 230)))
        self.assertEqual(caught.exception.code, "too-narrow")

    def test_install_and_the_stored_photo_check_give_one_plain_reply(self):
        for name, data in self.STRIPS.items():
            with self.subTest(photo=name):
                bare = Bare(self, houseRender=True)
                sha = bare.store(data)
                want = Refused(photos.RENDER_REPLY["too-narrow"])
                self.assertEqual(photos.install(bare.ctx, sha, ALT), want)
                self.assertEqual(photos.house_check(bare.settings, sha), want)
                self.assertEqual(bare.ctx.assets, {})
                self.assertEqual(voice.check(want.reason), [])

    def test_the_limit_is_about_forty_to_one(self):
        for size in ((800, 19), (19, 800)):  # 320x8 working copy (7.6 rounds up): the last shape that is rendered, no crash
            with self.subTest(size=size):
                made = newitem_render.render(strip(size))
                self.assertEqual(Image.open(io.BytesIO(made["jpeg"])).size, (800, 800))
        for size in ((800, 18), (18, 800)):  # 7.2 rounds down to 7
            with self.subTest(size=size), self.assertRaises(newitem_render.Refused):
                newitem_render.render(strip(size))

    def test_the_drafting_tool_reports_the_strip_as_refused(self):
        self.assertIn("too-narrow", newitem_render.REPLIES)
        self.assertEqual(voice.check(photos.RENDER_REPLY["too-narrow"]), [])


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class EditorTests(unittest.TestCase):
    """Through the real editor: prepare, apply, commit, undo on a throwaway repo (the PhotoRepo harness)."""

    def setUp(self):
        from hass.tests.test_set_photo import PhotoRepo
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)

    def flag(self, **extra):
        from hass.tests.test_set_photo import _settings
        _settings(self.repo, mediaRoot=str(self.repo.media), **extra)

    def committed_image(self, sha, ext="jpg"):
        return (self.repo.wt / "storefront-mockup" / "assets" / "products" / f"photo-{sha[:16]}.{ext}").read_bytes()

    def test_a_strip_stops_prepare_with_the_plain_reply(self):
        from hass.tests.test_set_photo import PID, _photo
        from hass.tests.test_catalog_ops import _req
        self.flag(houseRender=True)
        sha = self.repo.store(strip((1000, 1)))
        head, drafts = self.repo.head(), self.repo.drafts()
        result = self.repo.prepare(_req(_photo(PID, sha, ALT)))
        self.assertEqual((result["result"], result["reason"]), ("refused", photos.RENDER_REPLY["too-narrow"]))
        self.assertEqual((self.repo.head(), self.repo.drafts(), self.repo.status()), (head, drafts, ""))

    def test_the_approved_draft_names_the_picture_bytes(self):
        from hass.tests.test_set_photo import PID, _photo
        from hass.tests.test_catalog_ops import _req
        self.flag(houseRender=True)
        sha = self.repo.store(photo("jar-white-sheet"))
        draft = self.repo.prepare(_req(_photo(PID, sha, ALT)))["draft"]
        target = f"assets/products/photo-{sha[:16]}.jpg"
        self.assertEqual(draft["assets"], {target: "sha256:" + hashlib.sha256(photos.house_check({"mediaRoot": str(self.repo.media)}, sha)["jpeg"]).hexdigest()})
        self.assertEqual(self.repo.prepare(_req(_photo(PID, sha, ALT)))["draft"], draft)  # same bytes: same draft
        self.assertEqual(self.repo.apply(draft)["result"], "applied")
        self.assertEqual("sha256:" + hashlib.sha256(self.committed_image(sha)).hexdigest(), draft["assets"][target])

    def test_turning_the_flag_on_after_prepare_does_not_commit_a_different_picture(self):
        from hass.tests.test_set_photo import PID, _photo
        from hass.tests.test_catalog_ops import _req
        self.flag()
        sha = self.repo.store(photo("jar-white-sheet"))
        raw = self.repo.prepare(_req(_photo(PID, sha, ALT)))["draft"]  # the owner previewed and approved the picture as it came
        self.flag(houseRender=True)
        head = self.repo.head()
        result = self.repo.apply(raw)
        self.assertEqual(result["result"], "stale", result)
        self.assertEqual((self.repo.head(), self.repo.status()), (head, ""))
        self.assertFalse((self.repo.wt / "storefront-mockup" / "assets" / "products" / f"photo-{sha[:16]}.jpg").exists())
        fresh = self.repo.prepare(_req(_photo(PID, sha, ALT)))["draft"]  # a new look at the new picture needs its own approval
        self.assertNotEqual(fresh["draft_hash"], raw["draft_hash"])
        self.assertNotEqual(fresh["assets"], raw["assets"])

    def test_turning_the_flag_off_after_prepare_does_not_commit_the_raw_picture(self):
        from hass.tests.test_set_photo import PID, _photo
        from hass.tests.test_catalog_ops import _req
        self.flag(houseRender=True)
        sha = self.repo.store(photo("jar-white-sheet"))
        house = self.repo.prepare(_req(_photo(PID, sha, ALT)))["draft"]
        self.flag()
        head = self.repo.head()
        result = self.repo.apply(house)
        self.assertEqual(result["result"], "stale", result)
        self.assertEqual((self.repo.head(), self.repo.status()), (head, ""))
        self.assertNotEqual(self.repo.prepare(_req(_photo(PID, sha, ALT)))["draft"]["draft_hash"], house["draft_hash"])

    def test_flag_off_is_the_old_bytes_through_the_editor(self):
        from hass.tests.test_set_photo import PID, _photo
        self.flag()
        sha = self.repo.store(photo("jar-white-sheet"))
        self.repo.run(_photo(PID, sha, ALT))
        self.assertEqual(self.committed_image(sha), Path(media.web_copy(self.repo.media, sha)["path"]).read_bytes())

    def test_set_photo_commits_the_previewed_house_picture(self):
        from hass.tests.test_set_photo import PID, _photo
        self.flag(houseRender=True)
        sha = self.repo.store(photo("jar-phone-rotated"))
        seen = photos.house_check({"mediaRoot": str(self.repo.media)}, sha)  # what the skill showed before the yes
        self.assertTrue(seen["ok"])
        self.repo.run(_photo(PID, sha, ALT))
        product = self.repo.product(PID)
        self.assertEqual((product["image"], product["imageAlt"]), (f"assets/products/photo-{sha[:16]}.jpg", ALT))
        self.assertEqual(self.committed_image(sha), seen["jpeg"])
        self.assertEqual(self.repo.status(), "")

    def test_product_add_with_a_photo_uses_the_house_picture(self):
        from hass.tests.test_product_add_photo import NEW_ID, _add
        self.flag(houseRender=True)
        sha = self.repo.store(photo("bottle-grey-wall-tilted"))
        self.repo.run(_add(photo=sha, imageAlt=ALT))
        added = self.repo.products()[-1]
        self.assertEqual((added["id"], added["image"]), (NEW_ID, f"assets/products/photo-{sha[:16]}.jpg"))
        self.assertEqual(self.committed_image(sha), photos.house_check({"mediaRoot": str(self.repo.media)}, sha)["jpeg"])
        self.assertTrue(hs.check_image(self.committed_image(sha))["pass"])

    def test_a_defective_photo_stops_the_change_and_writes_nothing(self):
        from hass.tests.test_set_photo import PID, _photo
        from hass.tests.test_catalog_ops import _req
        from hass.tests.test_product_add_photo import _add
        self.flag(houseRender=True)
        sha = self.repo.store(photo("jar-dark-wood"))
        for op in (_photo(PID, sha, ALT), _add(photo=sha, imageAlt=ALT)):
            with self.subTest(op=op[0]):
                head, drafts = self.repo.head(), self.repo.drafts()
                result = self.repo.prepare(_req(op))
                self.assertEqual(result["result"], "refused", result)
                self.assertEqual(result["reason"], photos.RETAKE["busy"])
                self.assertEqual((self.repo.head(), self.repo.drafts(), self.repo.status()), (head, drafts, ""))
                self.assertFalse((self.repo.wt / "storefront-mockup" / "assets" / "products" / f"photo-{sha[:16]}.jpg").exists())

    def test_set_home_image_is_unchanged_with_the_flag_on(self):
        self.flag(houseRender=True)
        sha = self.repo.store(photo("jar-white-sheet"))
        self.repo.run(("store.set_home_image", {"photo": sha, "imageAlt": ALT}))
        self.assertEqual(self.committed_image(sha), Path(media.web_copy(self.repo.media, sha)["path"]).read_bytes())


if __name__ == "__main__":
    unittest.main()
