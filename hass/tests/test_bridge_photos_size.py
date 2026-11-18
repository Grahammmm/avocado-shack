"""RF0450-12 (H08/H10) tests: BlueBubblesPhotos.fetch refuses a download whose length differs from the attachment's
declared int totalBytes as `size-mismatch` (a cut-off photo is never returned), and refuses a message guid holding a
C0/C1 control character with ValueError before any call. Fake transports only: nothing listens, connects or downloads.
Run: python3 -m unittest hass.tests.test_bridge_photos_size -v"""

import unittest

from hass.bridge import BridgeError
from hass.tests import test_bridge_photos as _bp
from hass.tests.test_bridge_photos import JPG, PASSWORD, FakeTransport, _meta


class SizeMismatchTests(unittest.TestCase):
    setUp, photos, fails = _bp.PhotosTests.setUp, _bp.PhotosTests.photos, _bp.PhotosTests.fails  # helpers only, not its tests

    def mismatch(self, items, files, n=1):
        exc = self.fails(fake := FakeTransport(meta=_meta(*items), files=files), "size-mismatch", n=n)
        self.assertIsNone(exc.status)
        return fake

    def test_short_download_is_size_mismatch_without_password(self):
        fake = self.mismatch([{"guid": "att-1", "totalBytes": len(JPG)}], {"att-1": (200, JPG[:-10])})
        self.assertEqual(len(fake.calls), 2)
        with self.assertRaises(BridgeError) as ctx: self.photos(fake).fetch("msg-1", 1)
        for text in (str(ctx.exception), repr(ctx.exception)):
            self.assertNotIn(PASSWORD, text)
            self.assertNotIn("password=", text)

    def test_long_download_is_size_mismatch(self):
        self.mismatch([{"guid": "att-1", "totalBytes": len(JPG)}], {"att-1": (200, JPG + b"x")})

    def test_one_byte_short_or_long_is_size_mismatch(self):
        for body in (JPG[:-1], JPG + b"\x00"):
            with self.subTest(size=len(body)):
                self.mismatch([{"guid": "att-1", "totalBytes": len(JPG)}], {"att-1": (200, body)})

    def test_second_of_two_short_returns_nothing(self):
        items = [{"guid": "att-1", "totalBytes": len(JPG)}, {"guid": "att-2", "totalBytes": len(JPG)}]
        fake = self.mismatch(items, {"att-1": (200, JPG), "att-2": (200, JPG[:100])}, n=2)
        self.assertEqual(len(fake.calls), 3)

    def test_first_of_two_short_stops_before_second_download(self):
        items = [{"guid": "att-1", "totalBytes": len(JPG)}, {"guid": "att-2", "totalBytes": len(JPG)}]
        fake = self.mismatch(items, {"att-1": (200, JPG[:100]), "att-2": (200, JPG)}, n=2)
        self.assertEqual(len(fake.calls), 2)

    def test_matching_lengths_still_download(self):
        items = [{"guid": "att-1", "totalBytes": len(JPG)}, {"guid": "att-2", "totalBytes": len(JPG) + 1}]
        fake = FakeTransport(meta=_meta(*items), files={"att-1": (200, JPG), "att-2": (200, JPG + b"2")})
        self.assertEqual(self.photos(fake).fetch("msg-1", 2), [JPG, JPG + b"2"])

    def test_absent_or_none_total_bytes_accepts_any_length(self):
        for item in ({"guid": "att-1"}, {"guid": "att-1", "totalBytes": None}):
            for body in (JPG[:-10], JPG + b"x", b"x"):
                with self.subTest(item=item, size=len(body)):
                    fake = FakeTransport(meta=_meta(item), files={"att-1": (200, body)})
                    self.assertEqual(self.photos(fake).fetch("msg-1", 1), [body])

    def test_declared_zero_with_empty_body_is_empty(self):
        self.fails(FakeTransport(meta=_meta({"guid": "att-1", "totalBytes": 0}), files={"att-1": (200, b"")}), "empty")

    def test_declared_zero_with_a_body_is_size_mismatch(self):
        self.mismatch([{"guid": "att-1", "totalBytes": 0}], {"att-1": (200, JPG)})

    def test_http_error_keeps_its_code_and_status(self):
        fake = FakeTransport(meta=_meta({"guid": "att-1", "totalBytes": len(JPG)}), files={"att-1": (500, b"")})
        self.assertEqual(self.fails(fake, "http-error").status, 500)


class MessageGuidControlTests(unittest.TestCase):
    setUp, photos = _bp.PhotosTests.setUp, _bp.PhotosTests.photos

    def test_control_characters_refused_before_any_call(self):
        fake = FakeTransport()
        for guid in ("m\n1", "m\x00", "m\x7f", "m\x85", "m\x1f", "m\x9f", "\tm"):
            with self.subTest(guid=repr(guid)):
                with self.assertRaises(ValueError) as ctx: self.photos(fake).fetch(guid, 1)
                self.assertIn("without control characters", str(ctx.exception))
        self.assertEqual(fake.calls, [])

    def test_plain_and_printable_non_ascii_guids_still_work(self):
        for guid in ("m-1", "m\xa0é"):
            with self.subTest(guid=repr(guid)):
                fake = FakeTransport()
                self.assertEqual(self.photos(fake).fetch(guid, 1), [JPG])
                self.assertEqual(len(fake.calls), 2)


if __name__ == "__main__":
    unittest.main()
