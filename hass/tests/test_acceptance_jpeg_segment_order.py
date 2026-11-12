"""The offline picture oracle inspects JPEG metadata segments placed after the frame header (SKILLS-SPEC.md:646)."""
import tempfile
import unittest
from pathlib import Path

from hass.skills import acceptance_run as ar

NAME = "photo-0123456789abcdef.jpg"
ORIGINALS = {"0123456789abcdef" + "0" * 48}


def seg(marker, payload):
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def tiff(tags, order="II"):
    bo = "little" if order == "II" else "big"
    entries = b"".join(t.to_bytes(2, bo) + (3).to_bytes(2, bo) + (1).to_bytes(4, bo) + (0).to_bytes(4, bo) for t in tags)
    return order.encode() + (42).to_bytes(2, bo) + (8).to_bytes(4, bo) + len(tags).to_bytes(2, bo) + entries + (0).to_bytes(4, bo)


def exif(tags, order="II"):
    return seg(0xE1, b"Exif\0\0" + tiff(tags, order))


SOF = seg(0xC0, b"\x08" + (16).to_bytes(2, "big") + (16).to_bytes(2, "big") + b"\x01\x01\x11\x00")
DQT = seg(0xDB, b"\x00" + bytes(64))
SOS = seg(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\xff\xd9"
APP0 = seg(0xE0, b"JFIF\0\x01\x01\x00\x00\x01\x00\x01\x00\x00")


def jpeg(before=(), after=()):
    return b"\xff\xd8" + APP0 + b"".join(before) + DQT + SOF + b"".join(after) + SOS


def problems(data, house_render=False):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / NAME).write_bytes(data)
        return ar.picture_problems({NAME}, Path(d), {"picture": {"house": "off"}}, house_render, ORIGINALS)


class JpegSegmentOrder(unittest.TestCase):
    def test_clean_jpeg_dimensions_unchanged(self):
        self.assertEqual(ar._image_info(jpeg()), ("jpeg", 16, 16, []))
        self.assertEqual(problems(jpeg()), [])

    def test_numeric_gps_after_sof_is_metadata_and_location_data(self):
        for order in ("II", "MM"):
            for place in ("before", "after"):
                e = exif([0x8825], order)
                data = jpeg(before=[e]) if place == "before" else jpeg(after=[e])
                self.assertNotIn(b"GPS", data)
                self.assertEqual(ar._image_info(data), ("jpeg", 16, 16, ["exif-gps"]), (order, place))
                self.assertEqual(problems(data), ["picture carries metadata", "picture carries location data"], (order, place))

    def test_xmp_iptc_and_comment_after_sof_match_before_sof(self):
        for s in (seg(0xE1, b"http://ns.adobe.com/xap/1.0/\0<x/>"), seg(0xED, b"Photoshop 3.0\0"), seg(0xFE, b"hello")):
            for house in (False, True):
                a, b = problems(jpeg(before=[s]), house), problems(jpeg(after=[s]), house)
                self.assertEqual(a, ["picture carries metadata"])
                self.assertEqual(a, b)

    def test_orientation_exception_does_not_depend_on_segment_position(self):
        for place in ("before", "after"):
            def mk(tags):
                return jpeg(before=[exif(tags)]) if place == "before" else jpeg(after=[exif(tags)])
            self.assertEqual(problems(mk([0x0112])), [])
            self.assertEqual(problems(mk([0x0112]), True), ["picture carries metadata"])
            self.assertEqual(problems(mk([0x0112, 0x010F])), ["picture carries metadata"])

    def test_stop_at_sos_and_skip_payload_bytes_without_false_markers(self):
        fake = b"\xff\xfe\x00\x05abc"  # looks like a comment segment
        data = jpeg(after=[seg(0xDD, fake)])
        self.assertEqual(ar._image_info(data), ("jpeg", 16, 16, []))
        data = jpeg().replace(b"\x12\x34", fake)  # entropy-coded bytes after SOS are never walked
        self.assertEqual(ar._image_info(data), ("jpeg", 16, 16, []))

    def test_truncated_post_sof_segment_is_bounded_and_not_false_clean(self):
        base = b"\xff\xd8" + DQT + SOF
        for tail in (b"\xff\xe1\x00", b"\xff\xe1\x00\x00xx", b"\xff\xfe\x00\x01xx", b"\xff\xfe\xff\xffxx", b"\x00\x00\x00\x00\x00"):
            typ, w, h, meta = ar._image_info(base + tail)
            self.assertEqual((typ, w, h), ("jpeg", 16, 16))
            if tail != b"\xff\xe1\x00":
                self.assertTrue(meta, tail)
        self.assertTrue(ar._image_info(b"\xff\xd8" + seg(0xC0, b"\x08\x00"))[3])
        self.assertIn("picture carries metadata", problems(base + b"\xff\xfe\xff\xffxx"))

    def test_marker_fill_bytes_after_sof_are_skipped(self):
        for fill in (b"\xff", b"\xff\xff\xff"):
            clean = b"\xff\xd8" + APP0 + DQT + SOF + fill + SOS
            self.assertEqual(ar._image_info(clean), ("jpeg", 16, 16, []), fill)
            self.assertEqual(problems(clean), [], fill)
            between = b"\xff\xd8" + APP0 + DQT + SOF + fill + DQT + fill + SOS  # fill before and after another segment
            self.assertEqual(ar._image_info(between), ("jpeg", 16, 16, []), fill)
            marked = b"\xff\xd8" + APP0 + DQT + SOF + fill + seg(0xFE, b"x") + fill + SOS
            self.assertEqual(ar._image_info(marked), ("jpeg", 16, 16, ["segment-fe"]), fill)
            self.assertEqual(problems(marked), ["picture carries metadata"], fill)
            gps = b"\xff\xd8" + APP0 + DQT + SOF + fill + exif([0x8825]) + SOS
            self.assertEqual(ar._image_info(gps), ("jpeg", 16, 16, ["exif-gps"]), fill)

    def test_fill_bytes_with_nothing_after_are_not_false_clean(self):
        base = b"\xff\xd8" + DQT + SOF
        for tail in (b"\xff\xff\xff\xff", b"\xff\xff\xff\xff\xff", b"\xff\xff\xff\xff\xff\xff\xff\xff"):  # 4+ bytes, as the loop's own length floor
            self.assertTrue(ar._image_info(base + tail)[3], tail)

    def test_post_sof_metadata_gives_bad_picture(self):
        self.assertTrue(problems(jpeg(after=[seg(0xFE, b"x")])))


if __name__ == "__main__":
    unittest.main()
