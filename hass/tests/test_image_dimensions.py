"""AV1422-04 (H13): the header logo, Michael's portrait and the default hero carry width and height.

The numbers must equal the file's real pixel size (read here from the PNG IHDR / JPEG SOF, so a later asset swap fails
loudly); an owner-set home photo keeps none (its size is not stored). The browser case needs PLAYWRIGHT_MODULE: at 390x844
and 1440x900 each changed image has the same box as on a page without the attributes (+-1 px).
Run: python3 -m unittest hass.tests.test_image_dimensions -v
"""

import functools
import http.server
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from hass import sitegen
from hass.content_model import REPO_ROOT, load_content

SITE = REPO_ROOT / "storefront-mockup"
IMG_TAG = re.compile(r"<img\b[^>]*>")
SIZE_ATTRS = re.compile(r' (?:width|height)="\d+"')
CONTENT = load_content()


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def pixel_size(path):
    data = Path(path).read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    i = 2
    while i < len(data):  # JPEG: walk the segments to the first SOFn marker
        marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + length
    raise ValueError(f"no SOF in {path}")


def img(html, src):
    found = [t for t in IMG_TAG.findall(html) if f'src="{src}"' in t]
    assert len(found) == 1, (src, found)
    return found[0]


def size_attrs(tag):
    return re.findall(r' (width|height)="(\d+)"', tag)


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rendered = sitegen.render(CONTENT)
        cls.home = rendered["storefront-mockup/index.html"].decode("utf-8")
        cls.hike = rendered["storefront-mockup/hike/index.html"].decode("utf-8")
        cls.notfound = sitegen.publish_files(CONTENT, REPO_ROOT)["404.html"].decode("utf-8")


class ImageDimensionTests(Pages):
    def assertSize(self, tag, asset):
        width, height = pixel_size(SITE / asset)
        self.assertEqual(size_attrs(tag), [("width", str(width)), ("height", str(height))], tag)

    def test_named_images_carry_their_real_pixel_size(self):
        self.assertEqual(pixel_size(SITE / "assets/logo-header.png"), (148, 116))
        self.assertEqual(pixel_size(SITE / "assets/michael.jpg"), (1200, 900))
        self.assertEqual(pixel_size(SITE / "assets/store.jpg"), (1600, 900))
        for html, prefix in ((self.home, ""), (self.hike, "/"), (self.notfound, "/")):
            self.assertSize(img(html, f"{prefix}assets/logo-header.png"), "assets/logo-header.png")
        self.assertSize(img(self.home, "assets/michael.jpg"), "assets/michael.jpg")
        self.assertSize(img(self.hike, "/assets/michael.jpg"), "assets/michael.jpg")
        self.assertSize(img(self.home, "assets/store.jpg"), "assets/store.jpg")

    def test_owner_home_photo_keeps_no_dimensions_and_alt_stays_escaped(self):
        store = {**CONTENT.store, "homeImage": {"image": "assets/products/photo-0123456789abcdef.jpg", "imageAlt": 'Crates "A" & B'}}
        tag = sitegen.store_slots(store)["store.heroImageHtml"]
        self.assertEqual(size_attrs(tag), [])
        self.assertIn('alt="Crates &quot;A&quot; &amp; B"', tag)
        self.assertEqual(size_attrs(sitegen.store_slots(CONTENT.store)["store.heroImageHtml"]), [("width", "1600"), ("height", "900")])

    def test_no_other_image_gains_dimensions(self):
        counts = {name: sum(bool(size_attrs(t)) for t in IMG_TAG.findall(page)) for name, page in
                  (("home", self.home), ("hike", self.hike), ("404", self.notfound))}
        self.assertEqual(counts, {"home": 3, "hike": 2, "404": 1})
        self.assertEqual(len(IMG_TAG.findall(self.home)), 3)  # product cards are drawn by script.js, not in the page


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class ImageBoxTests(Pages):
    SHOTS = r"""const pw = require(process.env.PLAYWRIGHT_MODULE);
(async () => {
  const b = await pw.chromium.launch(), out = {};
  for (const [vp, w, h] of [['phone', 390, 844], ['desktop', 1440, 900]]) {
    const p = await b.newPage({viewport: {width: w, height: h}});
    for (const [name, url] of JSON.parse(process.env.URLS)) {
      await p.goto(url, {waitUntil: 'load'});
      await p.evaluate(async () => { for (const i of document.images) { i.scrollIntoView(); i.loading = 'eager'; }
        await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; }))); });
      out[vp + ' ' + name] = await p.evaluate(() => ['.brand img', '.hero-image', '.story > img', '.club-host img'].map(s => {
        const e = document.querySelector(s), r = e && e.getBoundingClientRect(); return r && [r.x, r.y + scrollY, r.width, r.height]; }));
    }
  }
  await b.close(); console.log(JSON.stringify(out));
})();
"""

    def test_boxes_equal_those_of_a_page_without_the_attributes(self):
        tmp = Path(tempfile.mkdtemp(prefix="av1422-04-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        pages = {"new": {"index.html": self.home, "hike/index.html": self.hike}}
        pages["old"] = {k: IMG_TAG.sub(lambda m: SIZE_ATTRS.sub("", m.group(0)), v) for k, v in pages["new"].items()}
        urls = []
        for variant, files in pages.items():
            root = tmp / variant
            root.mkdir()
            for name in ("style.css", "hiking.css", "trail-explorer.css"):
                shutil.copy(SITE / name, root / name)
            (root / "assets").mkdir()
            for name in ("logo-header.png", "michael.jpg", "store.jpg"):
                shutil.copy(SITE / "assets" / name, root / "assets" / name)
            for rel, text in files.items():
                (root / rel).parent.mkdir(exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            urls += [[f"{variant} home", f"http://127.0.0.1:{server.server_port}/"], [f"{variant} hike", f"http://127.0.0.1:{server.server_port}/hike/"]]
        script = tmp / "shots.js"
        script.write_text(self.SHOTS)
        done = subprocess.run(["node", str(script)], env={**os.environ, "URLS": json.dumps(urls)}, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        boxes = json.loads(done.stdout)
        for vp in ("phone", "desktop"):
            for page in ("home", "hike"):
                new, old = boxes[f"{vp} new {page}"], boxes[f"{vp} old {page}"]
                self.assertEqual([b is None for b in new], [b is None for b in old], (vp, page))
                self.assertTrue(any(new), (vp, page))
                for n, o in zip(new, old):
                    if n:
                        self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(n, o)), (vp, page, n, o))


if __name__ == "__main__":
    unittest.main()
