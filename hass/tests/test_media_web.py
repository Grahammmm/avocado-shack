"""H10 part 2 tests: metadata-free web copy of a stored photo. Every image is built byte-by-byte here (fake GPS)."""

import hashlib, os, stat, tempfile, unittest, zlib  # noqa: E401
from pathlib import Path

from hass import media

AT = "2026-11-02T18:00:00+00:00"
XMP = b"http://ns.adobe.com/xap/1.0/\0<x:xmpmeta xmlns:geo='urn:fake-geo'>0 0 0</x:xmpmeta>"

def seg(marker, body):
    return bytes([0xFF, marker]) + (len(body) + 2).to_bytes(2, "big") + body

def tiff(order, orientation=None):
    """A tiny EXIF TIFF block: optional Orientation plus a fake GPS IFD pointer and a fake 'GPS 0 0 0' value."""
    num = lambda v, n: v.to_bytes(n, "little" if order == "II" else "big")  # noqa: E731
    entries = [num(0x0112, 2) + num(3, 2) + num(1, 4) + num(orientation, 2) + b"\0\0"] if orientation else []
    entries.append(num(0x8825, 2) + num(4, 2) + num(1, 4) + num(0, 4))
    head = (b"II*\0" if order == "II" else b"MM\0*") + num(8, 4)
    return head + num(len(entries), 2) + b"".join(entries) + num(0, 4) + b"GPS 0 0 0"

def exif(order="II", orientation=1):
    return seg(0xE1, b"Exif\0\0" + tiff(order, orientation))

APP0 = seg(0xE0, b"JFIF\0\x01\x01\0\0\x01\0\x01\0\0")
TABLES = seg(0xDB, bytes(65)) + seg(0xC0, b"\x08\0\x01\0\x01\x01\x01\x11\0") + seg(0xC4, bytes(17))
SCAN = seg(0xDA, b"\x01\x01\0\0\x3f\0") + b"\x12\xff\0\x34\xff\xd0\x56\xff\xd9"  # stuffed byte + restart marker

def jpeg(*extra, scan=SCAN):
    return b"\xff\xd8" + APP0 + b"".join(extra) + TABLES + scan

def chunk(kind, data):
    return len(data).to_bytes(4, "big") + kind + data + zlib.crc32(kind + data).to_bytes(4, "big")

PNG_KEPT = [chunk(b"IHDR", b"\0\0\0\x01\0\0\0\x01\x08\x03\0\0\0"), chunk(b"gAMA", b"\0\0\xb1\x8f"),
            chunk(b"iCCP", b"fake\0\0x"), chunk(b"PLTE", b"\0\0\0")]
PNG_DATA = [chunk(b"IDAT", b"x\x9cc"), chunk(b"IDAT", b"`\0\0\0\x02\0\x01"), chunk(b"IEND", b"")]

def png(*extra):
    return media.KINDS["png"] + b"".join(PNG_KEPT) + b"".join(extra) + b"".join(PNG_DATA)

def files(root):
    return sorted(str(Path(d, n).relative_to(root)) for d, _, names in os.walk(root) for n in names)

class WebCopyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"

    def copy(self, data):
        return media.web_copy(self.root, media.store_original(self.root, data, received_at=AT, source="fixture")["sha256"])

    def refused(self, data, code, sha=None):
        sha = sha or media.store_original(self.root, data, received_at=AT, source="fixture")["sha256"]
        with self.assertRaises(media.Refused) as cm: media.web_copy(self.root, sha)
        self.assertEqual(cm.exception.code, code)
        for leak in (str(self.tmp), sha[:8], "/"): self.assertNotIn(leak, cm.exception.reply)
        self.assertFalse((self.root / "web").exists())  # nothing written, not even the folder
        return cm.exception

    def test_jpeg_drops_location_xmp_comment_and_iptc(self):
        data = jpeg(exif("II", 1), seg(0xE1, XMP), seg(0xFE, b"shot at the fake spot"), seg(0xED, b"Photoshop 3.0\0GPS"))
        rec = self.copy(data)
        out = Path(rec["path"]).read_bytes()
        self.assertEqual(out, b"\xff\xd8" + APP0 + TABLES + SCAN)  # APP0, DQT, SOF, DHT kept; SOS..EOI byte-identical
        self.assertEqual(out[out.index(b"\xff\xda"):], data[data.index(b"\xff\xda"):])
        for gone in (b"Exif", b"GPS", b"urn:fake-geo", b"ns.adobe.com", b"fake spot", b"Photoshop"): self.assertNotIn(gone, out)
        sha = hashlib.sha256(data).hexdigest()
        self.assertEqual(rec, {"sha256": sha, "web_sha256": hashlib.sha256(out).hexdigest(), "kind": "jpeg",
                               "bytes": len(out), "removed": ["APP1", "APP13", "COM"], "duplicate": False,
                               "path": str(self.root / "web" / sha[:2] / f"{sha}.jpg")})
        self.assertEqual(stat.S_IMODE(os.lstat(rec["path"]).st_mode), 0o600)
        for d in (self.root / "web", Path(rec["path"]).parent): self.assertEqual(stat.S_IMODE(os.lstat(d).st_mode), 0o700)

    def test_only_colour_app_segments_survive(self):
        icc, adobe = seg(0xE2, b"ICC_PROFILE\0\x01\x01fake"), seg(0xEE, b"Adobe\0\x64\0\0\0\0\x01")
        data = jpeg(icc, seg(0xE2, b"MPF\0II*\0"), adobe, seg(0xE0, b"JFXX\0\x10"), seg(0xE5, b"vendor"), seg(0xEE, b"Other"))
        rec = self.copy(data)
        self.assertEqual(Path(rec["path"]).read_bytes(), b"\xff\xd8" + APP0 + icc + adobe + TABLES + SCAN)
        self.assertEqual(rec["removed"], ["APP0", "APP14", "APP2", "APP5"])

    def test_marker_fill_bytes_are_legal(self):
        # header fill: dropped with the header rebuild; the dropped EXIF still goes, the kept segments stay canonical
        data = b"\xff\xd8\xff\xff" + APP0 + b"\xff" + exif("II", 1) + b"\xff\xff\xff" + TABLES + SCAN
        rec = self.copy(data)
        self.assertEqual(Path(rec["path"]).read_bytes(), b"\xff\xd8" + APP0 + TABLES + SCAN)
        self.assertEqual(rec["removed"], ["APP1"])
        # fill before SOS, a restart marker, a second scan and EOI: the whole SOS..EOI tail is copied byte-for-byte
        body = SCAN[:SCAN.index(b"\xff\xd0")]
        tail = b"\xff\xff" + body + b"\xff\xff\xd0\x56\xff\xff" + SCAN[:-2] + b"\xff\xff\xff\xd9"
        rec = self.copy(jpeg(scan=tail))
        self.assertEqual(Path(rec["path"]).read_bytes(), b"\xff\xd8" + APP0 + TABLES + tail)
        self.assertEqual(rec["removed"], [])

    def test_orientation_is_kept_for_jpeg_and_refused_for_png(self):
        err = self.refused(png(chunk(b"eXIf", tiff("MM", 8))), "needs-rotation")
        self.assertIn("sideways", err.reply)
        for order in ("II", "MM"):
            with self.subTest(order=order):
                out = Path(self.copy(jpeg(exif(order, 6)))["path"]).read_bytes()
                self.assertEqual(out, b"\xff\xd8" + media.ORIENT_APP1(6) + APP0 + TABLES + SCAN)
        for data in (jpeg(exif("MM", None)), jpeg(exif("II", None)), jpeg(exif("MM", 1)), png(chunk(b"eXIf", tiff("II", 1)))):
            with self.subTest(head=data[:40]):
                self.assertNotIn(b"GPS", Path(self.copy(data)["path"]).read_bytes())

    def test_png_keeps_image_chunks_only(self):
        extra = [chunk(b"tEXt", b"Comment\0GPS 0 0 0"), chunk(b"iTXt", b"XML:com.adobe.xmp\0\0\0\0\0" + XMP),
                 chunk(b"eXIf", tiff("II", 1)), chunk(b"tIME", b"\x07\xea\x0b\x02\x12\0\0"), chunk(b"prVt", b"private")]
        data = png(*extra)
        rec = self.copy(data)
        out = Path(rec["path"]).read_bytes()
        self.assertEqual(out, media.KINDS["png"] + b"".join(PNG_KEPT + PNG_DATA))
        self.assertEqual(rec["removed"], ["eXIf", "iTXt", "prVt", "tEXt", "tIME"])
        self.assertEqual(rec["kind"], "png")
        self.assertTrue(rec["path"].endswith(".png"))
        chunks = media._png_chunks(out)  # re-walks with CRC verification
        self.assertEqual(media._png_idat(chunks), media._png_idat(media._png_chunks(data)))
        for gone in (b"GPS", b"urn:fake-geo", b"eXIf", b"tIME", b"private"): self.assertNotIn(gone, out)

    def test_malformed_and_unsafe_tails_are_unreadable(self):
        bad_idat = PNG_DATA[0][:-1] + bytes([PNG_DATA[0][-1] ^ 1])
        cases = {
            "jpeg length past end": b"\xff\xd8\xff\xe1\xff\xf0abc\xff\xd9",
            "jpeg without SOS": b"\xff\xd8" + APP0 + seg(0xDB, bytes(65)) + b"\xff\xd9",
            "jpeg bad marker": b"\xff\xd8" + APP0 + b"\x00\x00\xff\xd9",
            "jpeg malformed exif": jpeg(seg(0xE1, b"Exif\0\0II*\0\xff\xff\0\0")),
            "jpeg orientation 9": jpeg(exif("II", 9)),
            "jpeg appended image with exif": jpeg() + jpeg(exif("II", 1)),
            "jpeg comment between scans": jpeg(scan=SCAN[:-2] + seg(0xFE, b"GPS") + SCAN),
            "jpeg filled comment between scans": jpeg(scan=SCAN[:-2] + b"\xff\xff" + seg(0xFE, b"GPS") + SCAN),
            "jpeg appended image after filled EOI": jpeg(scan=SCAN[:-2] + b"\xff\xff\xd9") + jpeg(exif("II", 1)),
            "png bad crc": media.KINDS["png"] + b"".join(PNG_KEPT) + bad_idat + b"".join(PNG_DATA[1:]),
            "png truncated chunk": media.KINDS["png"] + PNG_KEPT[0] + b"\0\0\x03\xe8IDATxx" + media.PNG_END,
            "png trailer after IEND": png() + chunk(b"tEXt", b"GPS 0 0 0") + PNG_DATA[-1],
        }
        for name, data in cases.items():
            with self.subTest(name):
                self.refused(data, "unreadable")
        self.assertEqual(self.copy(jpeg() + b"\0\0")["removed"], [])  # NUL padding after EOI is still fine

    def test_idempotent_and_conflicting_copy(self):
        data = jpeg(exif())
        first = self.copy(data)
        again = media.web_copy(self.root, first["sha256"])
        self.assertEqual(again, {**first, "duplicate": True})
        self.assertEqual(len([f for f in files(self.root) if f.startswith("web")]), 1)
        Path(first["path"]).write_bytes(b"other")
        self.assertEqual(self.refused_at(first["sha256"]), "corrupt-store")
        self.assertEqual(Path(first["path"]).read_bytes(), b"other")

    def refused_at(self, sha):
        with self.assertRaises(media.Refused) as cm: media.web_copy(self.root, sha)
        return cm.exception.code

    def test_tampered_or_symlinked_original(self):
        data = jpeg(exif())
        sha = media.store_original(self.root, data, received_at=AT, source="fixture")["sha256"]
        original = self.root / "originals" / sha[:2] / f"{sha}.jpg"
        original.write_bytes(data.replace(b"GPS", b"gps"))
        self.refused(data, "corrupt-store", sha)
        original.unlink()
        victim = self.tmp / "victim.jpg"
        victim.write_bytes(data)
        original.symlink_to(victim)
        self.refused(data, "corrupt-store", sha)
        original.unlink()
        victim.rename(original)  # a correct original again, but now reached through a symlinked folder
        os.rename(original.parent, self.tmp / "elsewhere")
        original.parent.symlink_to(self.tmp / "elsewhere", target_is_directory=True)
        self.refused(data, "corrupt-store", sha)

    def test_unknown_or_invalid_sha(self):
        media.store_original(self.root, png(), received_at=AT, source="fixture")
        self.refused(None, "not-found", "0" * 64)
        self.refused(None, "not-found", hashlib.sha256(png()).hexdigest()[:2] + "0" * 62)  # folder exists, file does not
        for bad in ("../" * 21 + "x", "A" * 64, "0" * 63, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): media.web_copy(self.root, bad)
