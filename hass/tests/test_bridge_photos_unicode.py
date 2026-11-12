"""RF1100-21 (H10/H12/H16) tests: BlueBubblesPhotos refuses surrogate code points in message and attachment guids
before any URL is built; valid Unicode and first-n-only behaviour are preserved. Fake transports only.
Run: python3 -B -m unittest hass.tests.test_bridge_photos_unicode -v"""

import json, unittest  # noqa: E401
from unittest import mock
from urllib.parse import unquote, urlsplit

from hass import bridge_photos
from hass.tests.test_bridge_photos import JPG, PASSWORD, FakeTransport, PhotosTests, _meta

MSG_TEXT = ("guid must be a non-empty str of at most 200 chars without control characters "
            "or surrogate code points, and must not be '.' or '..'")
SURROGATES = ("\ud800", "\udbff", "\udc00", "\udfff")


class UnicodeGuidTests(unittest.TestCase):
    setUp, photos, fails = PhotosTests.setUp, PhotosTests.photos, PhotosTests.fails

    def test_message_surrogates_refused_before_io(self):
        bad = [s + "x" for s in SURROGATES] + ["x" + s for s in SURROGATES] + ["ab" + s + "cd" for s in SURROGATES]
        bad += ["\ud83d\ude00", "\ud83d", "a" * 199 + "\ud800"]  # adjacent high/low pair is still two surrogates
        for guid in bad:
            with self.subTest(guid=ascii(guid)):
                fake = FakeTransport()
                photos = self.photos(fake)
                with mock.patch.object(bridge_photos, "_quote") as quote, \
                        mock.patch.object(bridge_photos, "_private_file") as pf, \
                        mock.patch("pathlib.Path.read_text") as read:
                    with self.assertRaises(ValueError) as ctx: photos.fetch(guid, 1)
                self.assertEqual(str(ctx.exception), MSG_TEXT)
                self.assertEqual((quote.call_count, pf.call_count, read.call_count, len(fake.calls)), (0, 0, 0, 0))

    def test_attachment_surrogate_shape_before_any_download(self):
        for bad in SURROGATES:
            for items, n in (([{"guid": bad}], 1), ([{"guid": "att-1"}, {"guid": "a" + bad}], 2),
                             ([{"guid": "att-1"}, {"guid": "att-2"}, {"guid": bad + "z"}], 3)):
                with self.subTest(bad=ascii(bad), n=n):
                    raw = json.dumps({"data": {"attachments": items}}).encode()  # ensure_ascii: escaped surrogates
                    self.assertIn(b"\\ud", raw.lower())
                    fake = FakeTransport(meta=(200, raw), files={"att-1": (200, JPG), "att-2": (200, JPG)})
                    exc = self.fails(fake, "shape", n=n)
                    self.assertEqual((len(fake.calls), exc.status), (1, None))

    def test_surrogate_after_n_is_ignored(self):
        items = [{"guid": "att-1"}, {"guid": "att-2"}, {"guid": "bad\ud800"}]
        fake = FakeTransport(meta=_meta(*items), files={"att-1": (200, JPG), "att-2": (200, JPG + b"2")})
        self.assertEqual(self.photos(fake).fetch("msg-1", 2), [JPG, JPG + b"2"])
        self.assertEqual(len(fake.calls), 3)

    def test_supplementary_scalar_and_json_pair_download(self):
        emoji, enc = "\U0001F600", "%F0%9F%98%80"
        fake = FakeTransport(meta=_meta({"guid": "att-" + emoji}), files={"att-" + emoji: (200, JPG)})
        self.assertEqual(self.photos(fake).fetch("msg-" + emoji, 1), [JPG])
        self.assertEqual([urlsplit(u).path for u, *_ in fake.calls],
                         ["/api/v1/message/msg-" + enc, "/api/v1/attachment/att-" + enc + "/download"])
        raw = b'{"data": {"attachments": [{"guid": "a\\ud83d\\ude00"}]}}'  # escaped pair decodes to one scalar
        fake = FakeTransport(meta=(200, raw), files={"a" + emoji: (200, JPG)})
        self.assertEqual(self.photos(fake).fetch("msg-1", 1), [JPG])
        self.assertEqual(urlsplit(fake.calls[1][0]).path, "/api/v1/attachment/a" + enc + "/download")

    def refuse_attachments(self, items, n):
        fake = FakeTransport(meta=_meta(*items))
        self.fails(fake, "shape", n=n)
        self.assertEqual(len(fake.calls), 1)

    def test_valid_unicode_boundaries_preserved(self):
        guid = "\xe9\xa0" * 100  # accented letter + NBSP, exactly 200 code points
        fake = FakeTransport(meta=_meta({"guid": guid}), files={guid: (200, JPG)})
        self.assertEqual(self.photos(fake).fetch(guid, 1), [JPG])
        slashy = "a/b?c"
        fake = FakeTransport(meta=_meta({"guid": slashy}), files={slashy: (200, JPG)})
        self.assertEqual(self.photos(fake).fetch(slashy, 1), [JPG])
        self.assertEqual([len(urlsplit(u).path.split("/")) for u, *_ in fake.calls], [5, 6])  # one segment each
        self.assertEqual(unquote(urlsplit(fake.calls[0][0]).path.split("/")[4]), slashy)
        for bad in ("", "a" * 201, "a\nb", "a\x85b", None, 5, b"abc"):
            with self.subTest(guid=repr(bad)):
                with self.assertRaises(ValueError): self.photos(FakeTransport()).fetch(bad, 1)
        self.refuse_attachments([{"guid": "x" * 201}], 1)
        self.refuse_attachments([{"guid": "a"}, {"guid": "a"}], 2)
        self.refuse_attachments([{"guid": "a\x00"}], 1)
        fake = FakeTransport(meta=_meta({"guid": "a"}))
        self.fails(fake, "attachment-count", n=2)
        self.assertEqual(len(fake.calls), 1)

    def test_error_never_exposes_input_or_secret(self):
        with self.assertRaises(ValueError) as ctx: self.photos(FakeTransport()).fetch("CANARY-GUID-\ud800", 1)
        for text in (str(ctx.exception), repr(ctx.exception), repr(ctx.exception.args)):
            self.assertNotIn("CANARY", text)
            self.assertNotIn(PASSWORD, text)
        raw = json.dumps({"data": {"attachments": [{"guid": "CANARY-ATT-\ud800"}]}}).encode()
        exc = self.fails(FakeTransport(meta=(200, raw)), "shape")
        for text in (str(exc), repr(exc), repr(exc.args)):
            self.assertNotIn("CANARY", text)
            self.assertNotIn(PASSWORD, text)
        self.assertEqual((exc.__cause__, exc.__context__), (None, None))


if __name__ == "__main__":
    unittest.main()
