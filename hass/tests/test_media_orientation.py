"""AV0022-01 (H10) tests: a JPEG with EXIF Orientation 2-8 is accepted; its web copy carries one fresh EXIF segment with
only that Orientation (no GPS, camera or date). PNG eXIf rotation is still refused. Every image is built in memory.
Run: python3 -m unittest hass.tests.test_media_orientation -v
"""

import contextlib
import hashlib
import io
import unittest

from hass import conversation, media
from hass.conversation import Inbound
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_media_web import APP0, PNG_DATA, PNG_KEPT, SCAN, TABLES, chunk, jpeg, png, seg, tiff
from hass.tests.test_photo_draft import FakePhotos, PhotoInterpreter
from hass.tests.test_set_photo import ALT, ASSETS, PID, PhotoRepo, _photo, _settings

SECRETS = (b"FakeCam", b"Model-X", b"2026:11:02 18:00:00", b"37N-fake", b"GPS")


def rich_tiff(order, orientation, kind=3, count=1):
    """IFD0 with Orientation, Make, Model, DateTime and a GPS IFD (fake latitude); strings stored after the IFDs."""
    num = lambda v, n: v.to_bytes(n, "little" if order == "II" else "big")  # noqa: E731
    strings, entries = [b"FakeCam\0", b"Model-X\0", b"2026:11:02 18:00:00\0"], 5
    gps_at = 8 + 2 + 12 * entries + 4
    data_at = gps_at + 2 + 12 + 4
    offsets = [data_at + sum(map(len, strings[:i])) for i in range(3)]
    ifd0 = [num(0x0112, 2) + num(kind, 2) + num(count, 4) + num(orientation, 2) + b"\0\0"]
    ifd0 += [num(tag, 2) + num(2, 2) + num(len(s), 4) + num(at, 4) for tag, s, at in zip((0x010F, 0x0110, 0x0132), strings, offsets)]
    ifd0.append(num(0x8825, 2) + num(4, 2) + num(1, 4) + num(gps_at, 4))
    gps = num(1, 2) + num(0x0002, 2) + num(2, 2) + num(4, 4) + b"37N-"[:4] + num(0, 4)
    head = (b"II*\0" if order == "II" else b"MM\0*") + num(8, 4)
    return head + num(entries, 2) + b"".join(ifd0) + num(0, 4) + gps + b"".join(strings) + b"37N-fake GPS"


def app1(body):
    return seg(0xE1, b"Exif\0\0" + body)


def before(data):
    """What the pre-change filter wrote: SOI + kept segments + the SOS..EOI tail (no EXIF at all)."""
    segs, tail = media._jpeg_split(data)
    return b"\xff\xd8" + b"".join(s for m, s in segs if media._jpeg_kept(m, s)) + tail


def app1s(out):
    return [s for m, s in media._jpeg_split(out)[0] if m == 0xE1]


class OrientationFilterTest(unittest.TestCase):
    def test_built_segment_layout(self):
        built = media.ORIENT_APP1(6)
        self.assertEqual(len(built), 36)
        self.assertEqual(built.hex(), "ffe10022" + b"Exif\0\0".hex() + "49492a0008000000" + "0100" + "120103000100000006000000"
                         + "00000000")

    def test_sideways_jpeg_keeps_only_the_orientation(self):
        for order in ("II", "MM"):
            with self.subTest(order=order):
                data = jpeg(app1(rich_tiff(order, 6)), seg(0xE1, b"http://ns.adobe.com/xap/1.0/\0GPS"))
                self.assertEqual(media.check_photo(data), "jpeg")
                out, removed = media._jpeg_copy(data)
                self.assertEqual(app1s(out), [media.ORIENT_APP1(6)])
                self.assertEqual(out, b"\xff\xd8" + media.ORIENT_APP1(6) + APP0 + TABLES + SCAN)
                for leak in SECRETS: self.assertNotIn(leak, out)
                self.assertEqual(removed, {"APP1"})

    def test_each_value_2_to_8_is_carried_and_the_scan_is_untouched(self):
        for value in range(2, 9):
            with self.subTest(value=value):
                data = jpeg(app1(rich_tiff("MM", value)))
                out, _ = media._jpeg_copy(data)
                self.assertEqual(app1s(out), [media.ORIENT_APP1(value)])
                self.assertEqual(media._check_orientation(app1s(out)[0][10:]), value)
                self.assertEqual(out[out.index(b"\xff\xda"):], data[data.index(b"\xff\xda"):])

    def test_upright_or_no_exif_output_is_unchanged(self):
        for data in (jpeg(), jpeg(app1(rich_tiff("II", 1))), jpeg(app1(tiff("MM", None))), jpeg(app1(tiff("II", 1)))):
            with self.subTest(head=data[:30]):
                out, _ = media._jpeg_copy(data)
                self.assertEqual(out, before(data))
                self.assertEqual(app1s(out), [])

    def test_malformed_exif_is_still_unreadable(self):
        good = rich_tiff("II", 6)
        cases = {"bad byte order": b"IM*\0" + good[4:], "type LONG": rich_tiff("II", 6, kind=4),
                 "count 2": rich_tiff("II", 6, count=2), "value 0": rich_tiff("II", 0), "value 9": rich_tiff("MM", 9),
                 "truncated IFD": good[:20], "two different tags in one IFD": tiff("II", 6)[:8] + b"\x02\0"
                 + tiff("II", 6)[10:22] + tiff("II", 3)[10:22] + b"\0\0\0\0"}
        for name, body in cases.items():
            with self.subTest(name), self.assertRaises(media.Refused) as cm: media.check_photo(jpeg(app1(body)))
            self.assertEqual(cm.exception.code, "unreadable")

    def test_two_exif_segments_must_agree(self):
        with self.assertRaises(media.Refused) as cm: media.check_photo(jpeg(app1(rich_tiff("II", 6)), app1(tiff("MM", 3))))
        self.assertEqual(cm.exception.code, "unreadable")
        with self.assertRaises(media.Refused) as cm: media.check_photo(jpeg(app1(rich_tiff("II", 6)), app1(tiff("MM", None))))
        self.assertEqual(cm.exception.code, "unreadable")  # absent reads as 1, which disagrees with 6
        out, _ = media._jpeg_copy(jpeg(app1(rich_tiff("II", 6)), app1(tiff("MM", 6))))
        self.assertEqual(app1s(out), [media.ORIENT_APP1(6)])

    def test_png_rotation_is_still_refused(self):
        with self.assertRaises(media.Refused) as cm: media.check_photo(png(chunk(b"eXIf", tiff("MM", 8))))
        self.assertEqual((cm.exception.code, cm.exception.reply), ("needs-rotation", media.REPLIES["needs-rotation"]))
        self.assertIn("sideways", cm.exception.reply)
        self.assertEqual(media._png_copy(png())[0], media.KINDS["png"] + b"".join(PNG_KEPT + PNG_DATA))


class OrientationEndToEndTest(unittest.TestCase):
    def test_owner_sends_a_sideways_jpeg_and_it_is_installed_upright(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        _settings(repo, **SETTINGS, mediaRoot=str(repo.media))
        data = jpeg(app1(rich_tiff("II", 6)))
        conv = conversation.Conversation(str(repo.state), conversation.Editor(repo.state), PhotoInterpreter(),
                                         lambda: T0, photos=FakePhotos(data))
        got = conv.handle(Inbound("m1", CHAT, OWNER, "", received_at=T0.isoformat(), attachments=1))
        self.assertEqual(got, "photo-draft")
        sha = hashlib.sha256(data).hexdigest()
        repo.run(_photo(PID, sha))
        installed = (repo.wt / f"{ASSETS}photo-{sha[:16]}.jpg").read_bytes()
        self.assertTrue(installed.startswith(b"\xff\xd8\xff\xe1" + media.ORIENT_APP1(6)[2:]))
        for leak in SECRETS: self.assertNotIn(leak, installed)
        self.assertEqual(repo.product(PID)["imageAlt"], ALT)
        with contextlib.redirect_stdout(io.StringIO()) as out: code = media.main(["verify", "--root", str(repo.media)])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn('"result": "ok"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
