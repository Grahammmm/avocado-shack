"""CI guard: the pinned Pillow is installed and can do what the house-style picture code needs.

Self-contained (no repo imports). It fails, not skips, when Pillow is missing, so a CI job that
lost the install step goes red instead of silently skipping every picture test.

Run: python3 -m unittest discover -s tests -p test_pillow_ci.py -v
"""
import os
import tempfile
import unittest

from PIL import Image  # ImportError here is the intended failure when Pillow is missing


class PillowCiTest(unittest.TestCase):
    def test_pinned_version(self):
        want = os.environ.get("PILLOW_VERSION")  # set by check.yml; unset on a plain local run
        if want:
            import PIL
            self.assertEqual(PIL.__version__, want)

    def test_resize_and_save_jpeg(self):
        img = Image.new("RGB", (40, 30), (254, 248, 236))
        img = img.resize((20, 20), Image.Resampling.LANCZOS)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.jpg")
            img.save(path, format="JPEG", quality=84)
            with Image.open(path) as back:
                back.load()
                self.assertEqual(back.size, (20, 20))
                self.assertEqual(back.format, "JPEG")
                self.assertEqual(back.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
