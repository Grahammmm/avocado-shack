"""RF2345-19: a truncated EXIF IFD0 directory is unreadable before orientation policy or web writes. Synthetic bytes only."""

import os, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import media
from hass.tests.test_media_web import AT, chunk, exif, files, jpeg, png, tiff

def head(order, offset=8):
    return (b"II*\0" if order == "II" else b"MM\0*") + offset.to_bytes(4, "little" if order == "II" else "big")

def n(order, v, size):
    return v.to_bytes(size, "little" if order == "II" else "big")

def gps(order):
    return n(order, 0x8825, 2) + n(order, 4, 2) + n(order, 1, 4) + n(order, 0, 4)

def orient(order, v):
    return n(order, 0x0112, 2) + n(order, 3, 2) + n(order, 1, 4) + n(order, v, 2) + b"\0\0"

def bad_directories(order):
    one = head(order) + n(order, 1, 2)
    return {
        "tag-only": one + gps(order)[:2],
        "orientation-missing-last-two": one + orient(order, 1)[:10],
        "no-trailer": one + gps(order),
        "trailer-3-of-4": one + gps(order) + b"\0\0\0",
        "offset-in-header": head(order, 4) + n(order, 0, 2) + n(order, 0, 4),
        "offset-outside": head(order, 500) + n(order, 0, 2) + n(order, 0, 4),
        "absent-count": head(order) + b"\0",
        "huge-count": head(order) + n(order, 0xFFFF, 2) + gps(order) + n(order, 0, 4),
        "later-entry-truncated": head(order) + n(order, 2, 2) + gps(order) + gps(order)[:5],
    }

def containers(body):
    return {"jpeg": jpeg(exif_raw(body)), "png": png(chunk(b"eXIf", body))}

def exif_raw(body):
    return b"\xff\xe1" + (len(body) + 8).to_bytes(2, "big") + b"Exif\0\0" + body

class IfdBoundsTest(unittest.TestCase):
    def unreadable(self, data):
        with self.assertRaises(media.Refused) as cm: media.check_photo(data)
        self.assertEqual(cm.exception.code, "unreadable")

    def test_helper_and_containers_refuse_every_truncated_directory(self):
        for order in ("II", "MM"):
            for name, body in bad_directories(order).items():
                with self.subTest(order=order, case=name):
                    with self.assertRaises(media.Refused) as cm: media._check_orientation(body)
                    self.assertEqual(cm.exception.code, "unreadable")
                    for data in containers(body).values(): self.unreadable(data)

    def test_complete_directories_keep_legacy_behaviour(self):
        for order in ("II", "MM"):
            self.assertEqual(media._check_orientation(head(order) + n(order, 0, 2) + n(order, 0, 4)), 1)
            self.assertEqual(media._check_orientation(head(order) + n(order, 1, 2) + gps(order) + n(order, 0, 4)), 1)
            self.assertEqual(media._check_orientation(head(order, 12) + b"\0\0\0\0" + n(order, 0, 2) + n(order, 0, 4)), 1)
            for v in range(1, 9):
                body = head(order) + n(order, 2, 2) + gps(order) + orient(order, v) + n(order, 0, 4)
                self.assertEqual(media._check_orientation(body), v)
                self.assertEqual(media.check_photo(jpeg(exif_raw(body))), "jpeg")
            self.assertEqual(media.check_photo(jpeg(exif(order, 1))), "jpeg")
            self.assertEqual(media.check_photo(png(chunk(b"eXIf", tiff(order, None)))), "png")

    def test_png_rotation_still_needs_rotation_and_malformed_wins(self):
        for v in range(2, 9):
            with self.assertRaises(media.Refused) as cm: media.check_photo(png(chunk(b"eXIf", tiff("MM", v))))
            self.assertEqual(cm.exception.code, "needs-rotation")
        self.unreadable(png(chunk(b"eXIf", bad_directories("MM")["orientation-missing-last-two"])))

    def test_bytearray_input_is_unchanged(self):
        data = bytearray(jpeg(exif_raw(bad_directories("II")["tag-only"])))
        before = bytes(data)
        self.unreadable(data)
        self.assertEqual(bytes(data), before)

class WebCopyRefusalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"

    def test_stored_malformed_original_gets_no_web_copy_twice(self):
        body = bad_directories("II")["tag-only"]
        data = jpeg(exif_raw(body))
        sha = media.store_original(self.root, data, received_at=AT, source="fixture")["sha256"]
        snapshot = {f: (self.root / f).read_bytes() for f in files(self.root)}
        for _ in range(2):
            with self.assertRaises(media.Refused) as cm: media.web_copy(self.root, sha)
            self.assertEqual(cm.exception.code, "unreadable")
            self.assertFalse((self.root / "web").exists())
            self.assertEqual({f: (self.root / f).read_bytes() for f in files(self.root)}, snapshot)

if __name__ == "__main__":
    unittest.main()
