"""HASS-IMAGE-1 tests: the background photo clean-up (``photo_polish``) behind an injectable transport.

Every path ends in a published picture or the existing fallback, and the interview never waits:
* a faithful edit is published (house-framed 800x800 JPEG, no metadata), the same bytes at every install;
* it also rescues a busy-background photo the house render alone would ask to retake;
* timeout, refusal, wrong size, wrong type, huge file, a changed product, no Hermes: the fallback, and one short
  ``polish-<code>`` row in the correspondence log;
* ``start`` returns at once; an install that comes first settles the fallback and a late answer is dropped;
* the switch defaults off, is validated, and needs ``houseRender``.

The stub transport writes its picture where the Hermes runner would. Label reading is stubbed (CI has no tesseract).
Needs Pillow; no network, no Hermes, no live service.
"""
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import media, photo_polish

try:
    from PIL import Image
    from hass import newitem_synthetic as syn
    from hass.ops import photos
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

ALT = "Cal Poly honey in a jar"
CASES = dict(syn.cases()) if HAVE_PIL else {}


def photo(name, **change):
    return syn.make_photo(**{**CASES[name], **change})


def png(im):
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def edit_of(data, size=1024, change=None):
    """What a faithful image edit looks like: the product on a plain ivory background, square, PNG."""
    im = Image.open(io.BytesIO(photos.house_picture(data)["jpeg"])).convert("RGB").resize((size, size))
    return png(change(im) if change else im)


class Stub:
    """transport(src, out, timeout): writes ``data`` to out (or answers ``said``), after ``wait`` seconds."""

    def __init__(self, data=None, said=None, wait=0.0):
        self.data, self.said, self.wait, self.calls = data, said, wait, 0

    def __call__(self, src, out, timeout):
        self.calls += 1
        time.sleep(self.wait)
        if self.said is not None:
            return self.said
        Path(out).write_bytes(self.data)
        return {"ok": True, "code": "ok"}


class Log:
    def __init__(self):
        self.rows = []

    def record(self, kind, reason, **kw):
        self.rows.append((kind, reason))
        return True


class Bare:
    def __init__(self, test, **settings):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.media, self.site = Path(tmp.name) / "media", Path(tmp.name) / "site"
        (self.site / "assets" / "products").mkdir(parents=True)
        self.settings = {"mediaRoot": str(self.media), "houseRender": True, "photo_polish": True, **settings}

    def ctx(self):
        return SimpleNamespace(settings=self.settings, site_dir=self.site, assets={})

    def store(self, data):
        return media.store_original(self.media, data, received_at="2026-11-16T10:00:00+00:00", source="fixture")["sha256"]

    def install(self, sha):
        ctx = self.ctx()
        out = photos.install(ctx, sha, ALT)
        return out, ctx.assets.get(out) if isinstance(out, str) else None


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
@mock.patch.object(photo_polish, "words", lambda framed: None)
class ContractTests(unittest.TestCase):
    def polish(self, bare, sha, stub):
        log = Log()
        code = photo_polish.run(bare.media, sha, log=log, transport=stub)
        return code, log.rows

    def test_a_faithful_edit_is_published_the_same_every_time(self):
        bare = Bare(self)
        data = photo("jar-white-sheet")
        sha = bare.store(data)
        code, rows = self.polish(bare, sha, Stub(edit_of(data)))
        self.assertEqual((code, rows), ("ok", []))
        target, first = bare.install(sha)
        self.assertEqual(target, f"assets/products/photo-{sha[:16]}.jpg")
        im = Image.open(io.BytesIO(first))
        self.assertEqual((im.format, im.size, im.mode), ("JPEG", (800, 800), "RGB"))
        self.assertFalse(im.getexif() or im.info.get("exif") or im.info.get("icc_profile"))
        self.assertNotEqual(first, photos.house_picture(data)["jpeg"])  # the edit, not the fallback
        self.assertEqual(bare.install(sha), (target, first))  # prepare, apply, verify: the same bytes
        self.assertEqual(photo_polish.decision(bare.media, sha)["use"], "polished")
        self.assertEqual(media.verify_store(bare.media)["result"], "ok")

    def test_a_busy_photo_is_rescued_by_a_faithful_edit(self):
        bare = Bare(self)
        busy = photo("jar-dark-wood")
        sha = bare.store(busy)
        alone = Bare(self, photo_polish=False)
        self.assertIsInstance(alone.install(alone.store(busy))[0], photos.Retake)  # the house render alone asks to retake
        plain = photo("jar-dark-wood", background="white-sheet")  # the same jar, as a clean edit would show it
        code, _ = self.polish(bare, sha, Stub(edit_of(plain)))
        self.assertEqual(code, "ok")
        target, data = bare.install(sha)
        self.assertEqual(target, f"assets/products/photo-{sha[:16]}.jpg")
        self.assertEqual(Image.open(io.BytesIO(data)).size, (800, 800))

    def assertFallback(self, stub, code, photo_name="jar-white-sheet"):
        bare = Bare(self)
        data = photo(photo_name)
        sha = bare.store(data)
        got, rows = self.polish(bare, sha, stub)
        self.assertEqual(got, code)
        self.assertEqual(rows, [("error", f"polish-{code}")])
        target, published = bare.install(sha)
        self.assertEqual(published, photos.house_picture(bare_web(bare, sha))["jpeg"])  # exactly the old behaviour
        self.assertEqual(photo_polish.decision(bare.media, sha)["use"], "house")
        self.assertFalse((bare.media / "polish" / sha[:2] / f"{sha}.jpg").exists())
        return target

    def test_timeout_refusal_and_failures_use_the_fallback(self):
        for said in ({"ok": False, "code": "timeout"}, {"ok": False, "code": "api"}, {"ok": False, "code": "auth"}):
            with self.subTest(said=said):
                self.assertFallback(Stub(said=said), said["code"])
        self.assertFallback(Stub(said="garbage"), "failed")

    def test_a_transport_that_raises_uses_the_fallback(self):
        def boom(src, out, timeout):
            raise RuntimeError("no network")
        self.assertFallback(boom, "transport")

    def test_wrong_size_wrong_type_huge_and_empty_use_the_fallback(self):
        data = photo("jar-white-sheet")
        wide = Image.new("RGB", (1024, 600), (245, 240, 230))
        self.assertFallback(Stub(png(wide)), "size")
        self.assertFallback(Stub(png(Image.new("RGB", (300, 300), (245, 240, 230)))), "size")
        self.assertFallback(Stub(b"GIF89a" + bytes(2000)), "type")
        self.assertFallback(Stub(b"<html>no picture</html>"), "type")
        self.assertFallback(Stub(edit_of(data) + bytes(photo_polish.MAX_OUTPUT_BYTES)), "huge")
        self.assertFallback(Stub(b""), "empty")

    def test_a_changed_product_is_rejected(self):
        data = photo("jar-white-sheet")
        recoloured = lambda im: Image.merge("RGB", im.split()[::-1])  # noqa: E731 - the jar turns another colour
        self.assertFallback(Stub(edit_of(data, change=recoloured)), "colour")
        other = photo("bottle-bench-png")
        self.assertFallback(Stub(edit_of(other)), "match")

    def test_changed_label_words_are_rejected(self):
        def centre_word(framed):  # "reads" one word across the middle of the product, wherever the render put it
            _rgb, _mask, box = photo_polish._product(framed)
            x0, y0, x1, y1 = (v * 2 for v in box)
            w, h = (x1 - x0) // 2, max(12, (y1 - y0) // 8)
            return [("SUNNY", ((x0 + x1) // 2 - w // 2, (y0 + y1) // 2 - h // 2, w, h))]

        def stamped(im):  # a new word painted across the label
            from PIL import ImageDraw
            d, (w, h) = ImageDraw.Draw(im), im.size
            d.rectangle((w * .3, h * .45, w * .7, h * .55), fill=(20, 20, 20))
            for i in range(5):
                d.rectangle((w * (.33 + i * .075), h * .47, w * (.36 + i * .075), h * .53), fill=(240, 240, 240))
            return im
        data = photo("jar-white-sheet")
        with mock.patch.object(photo_polish, "words", centre_word):
            ok = Bare(self)
            self.assertEqual(self.polish(ok, ok.store(data), Stub(edit_of(data))), ("ok", []))  # the same marks: kept
            bad = Bare(self)
            code, rows = self.polish(bad, bad.store(data), Stub(edit_of(data, change=stamped)))
        self.assertEqual((code, rows), ("text", [("error", "polish-text")]))

    def test_no_hermes_uses_the_fallback(self):
        transport = photo_polish.HermesTransport(launcher="/nonexistent/hermes")
        self.assertFallback(transport, "no-hermes")


def bare_web(bare, sha):
    return Path(media.web_copy(bare.media, sha)["path"]).read_bytes()


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
@mock.patch.object(photo_polish, "words", lambda framed: None)
class BackgroundTests(unittest.TestCase):
    def test_start_never_waits_and_a_late_answer_is_dropped(self):
        bare = Bare(self)
        data = photo("jar-white-sheet")
        sha = bare.store(data)
        gate = threading.Event()

        def slow(src, out, timeout):
            gate.wait(10)
            Path(out).write_bytes(edit_of(data))
            return {"ok": True, "code": "ok"}
        log = Log()
        began = time.monotonic()
        worker = photo_polish.start(bare.media, sha, log=log, transport=slow)
        self.assertLess(time.monotonic() - began, 0.5)  # the interview goes on at once
        self.assertIsNone(photo_polish.start(bare.media, sha, transport=slow))  # one job per photo
        target, first = bare.install(sha)  # the preview comes before the answer: the fallback is settled now
        self.assertIsInstance(target, str, target)
        self.assertEqual(first, photos.house_picture(bare_web(bare, sha))["jpeg"])
        gate.set()
        worker.join(30)
        self.assertEqual(log.rows, [("error", "polish-late")])
        self.assertEqual(bare.install(sha), (target, first))  # still the same bytes at apply and verify
        self.assertEqual(photo_polish.decision(bare.media, sha)["code"], "late")

    def test_a_settled_photo_is_not_sent_again(self):
        bare = Bare(self)
        sha = bare.store(photo("jar-white-sheet"))
        stub = Stub(said={"ok": False, "code": "api"})
        photo_polish.run(bare.media, sha, transport=stub)
        self.assertIsNone(photo_polish.start(bare.media, sha, transport=stub))
        self.assertEqual(stub.calls, 1)

    def test_switch_off_or_without_house_render_installs_as_before(self):
        data = photo("jar-white-sheet")
        for settings in ({"photo_polish": False}, {"photo_polish": "true"}, {"houseRender": False}):
            with self.subTest(settings=settings):
                bare = Bare(self, **settings)
                sha = bare.store(data)
                photo_polish.run(bare.media, sha, transport=Stub(edit_of(data)))
                ctx = SimpleNamespace(settings=bare.settings, site_dir=bare.site, assets={})
                target = photos.install(ctx, sha, ALT)
                house = bare.settings["houseRender"] is True
                want = photos.house_picture(bare_web(bare, sha))["jpeg"] if house else bare_web(bare, sha)
                self.assertEqual(ctx.assets[target], want)


class SettingTests(unittest.TestCase):
    def test_enabled_needs_both_switches_as_json_true(self):
        self.assertTrue(photo_polish.enabled({"photo_polish": True, "houseRender": True}))
        for settings in ({}, {"photo_polish": True}, {"photo_polish": 1, "houseRender": True},
                         {"photo_polish": "true", "houseRender": True}, {"photo_polish": True, "houseRender": False}):
            self.assertFalse(photo_polish.enabled(settings), settings)

    def test_the_model_is_one_line(self):
        source = Path(photo_polish.__file__).read_text("utf-8")
        self.assertEqual(sum(1 for line in source.splitlines() if "gpt-image-2-high" in line), 1)
        self.assertEqual(photo_polish.MODEL, "openai-codex:gpt-image-2-high")

    def test_find_hermes_reads_the_launcher_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, py = Path(tmp) / "release", Path(tmp) / "python3"
            (root / ".hermes" / "bin").mkdir(parents=True)
            py.write_text("")
            (root / ".hermes" / "bin" / "hermes").write_text(
                f"#!/bin/sh\nexec {py} -I -c 'import os\nsys.path.insert(0, '\"'\"'{root}'\"'\"')\n'\n")
            link = Path(tmp) / "current"
            link.symlink_to(root)
            outer = Path(tmp) / "hermes"
            outer.write_text(f"#!/usr/bin/env bash\nrelease_root=$(readlink -f {link})\nexec x\n")
            self.assertEqual(photo_polish.find_hermes(str(outer)), (str(py), str(root)))
            self.assertIsNone(photo_polish.find_hermes(str(Path(tmp) / "missing")))

    def test_transport_timeout_is_a_short_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            sleeper = Path(tmp) / "sleep.py"
            sleeper.write_text("import time\ntime.sleep(5)\n")
            transport = photo_polish.HermesTransport(python=sys.executable, root=tmp)
            with mock.patch.object(photo_polish.subprocess, "run", side_effect=photo_polish.subprocess.TimeoutExpired("x", 1)):
                self.assertEqual(transport(Path(tmp) / "in.png", Path(tmp) / "out.img", 1), {"ok": False, "code": "timeout"})
            done = SimpleNamespace(stdout=json.dumps({"ok": False, "code": "api"}) + "\n")
            with mock.patch.object(photo_polish.subprocess, "run", return_value=done):
                self.assertEqual(transport(Path(tmp) / "in.png", Path(tmp) / "out.img", 1), {"ok": False, "code": "api"})
            done = SimpleNamespace(stdout=json.dumps({"ok": False, "code": "Bearer abc/def"}) + "\n")
            with mock.patch.object(photo_polish.subprocess, "run", return_value=done):  # never a free text through
                self.assertEqual(transport(Path(tmp) / "in.png", Path(tmp) / "out.img", 1), {"ok": False, "code": "failed"})
            self.assertEqual(list(Path(tmp).glob("*.txt")), [])  # the prompt file is gone

    def test_load_settings_defaults_off_and_validates(self):
        from hass import conversation
        base = {"ownerSenders": ["+15555550100"], "ownerChat": "iMessage;-;+15555550100", "approvalTtlSeconds": 600}
        with tempfile.TemporaryDirectory() as tmp:
            def load(**extra):
                (Path(tmp) / "config.json").write_text(json.dumps({"settings": {**base, **extra}}))
                return conversation.load_settings(tmp)
            self.assertIs(load()["photo_polish"], False)
            self.assertIs(load(houseRender=True, photo_polish=True)["photo_polish"], True)
            for bad in ({"photo_polish": "true", "houseRender": True}, {"photo_polish": 1, "houseRender": True},
                        {"photo_polish": True}, {"photo_polish": True, "houseRender": False}):
                with self.subTest(settings=bad), self.assertRaisesRegex(conversation.ConfigError, "photo_polish must be"):
                    load(**bad)


if __name__ == "__main__":
    unittest.main()
