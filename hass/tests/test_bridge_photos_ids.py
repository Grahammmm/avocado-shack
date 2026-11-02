"""RF0140-6 (H08/H10) tests: BlueBubblesPhotos checks each attachment guid it will download like the message guid
(<= 200 chars, no control characters), refuses a repeated guid and a non-int or negative totalBytes as `shape`, and
does so before any download. Fake transports only: nothing listens, connects or downloads.
Run: python3 -m unittest hass.tests.test_bridge_photos_ids -v"""

import unittest

from hass import media
from hass.bridge import BridgeError
from hass.tests.test_bridge_photos import JPG, PASSWORD, FakeTransport, PhotosTests, _meta


class AttachmentIdTests(unittest.TestCase):
    setUp, photos, fails = PhotosTests.setUp, PhotosTests.photos, PhotosTests.fails  # helpers only, not its tests

    def refused(self, items, code="shape", n=1):
        exc = self.fails(fake := FakeTransport(meta=_meta(*items), files={}), code, n=n)
        self.assertEqual(len(fake.calls), 1)  # metadata only: nothing downloaded
        return exc

    def test_guid_over_200_chars_is_shape_and_200_downloads(self):
        self.refused([{"guid": "a" * 201}])
        guid = "a" * 200
        fake = FakeTransport(meta=_meta({"guid": guid}), files={guid: (200, JPG)})
        self.assertEqual(self.photos(fake).fetch("msg-1", 1), [JPG])
        self.assertEqual(len(fake.calls), 2)

    def test_guid_with_control_char_is_shape(self):
        for ch in ("\n", "\x00", "\x1f", "\x7f", "\x85", "\x9f"):
            with self.subTest(ch=repr(ch)):
                self.refused([{"guid": f"att{ch}1"}])

    def test_guid_with_printable_non_ascii_downloads(self):
        guid = "att-\xa0é-1"  # 160 and above are not control characters
        fake = FakeTransport(meta=_meta({"guid": guid}), files={guid: (200, JPG)})
        self.assertEqual(self.photos(fake).fetch("msg-1", 1), [JPG])

    def test_repeated_guid_in_first_n_is_shape(self):
        self.refused([{"guid": "att-1"}, {"guid": "att-1"}], n=2)
        self.refused([{"guid": "att-1"}, {"guid": "att-2"}, {"guid": "att-1"}], n=3)

    def test_repeated_guid_after_first_n_is_never_used(self):
        items = [{"guid": "att-1"}, {"guid": "att-2"}, {"guid": "att-1"}]
        fake = FakeTransport(meta=_meta(*items), files={"att-1": (200, JPG), "att-2": (200, JPG + b"2")})
        self.assertEqual(self.photos(fake).fetch("msg-1", 2), [JPG, JPG + b"2"])
        self.assertEqual(len(fake.calls), 3)

    def test_bad_guid_after_first_n_is_never_checked(self):
        items = [{"guid": "att-1"}, {"guid": "x" * 201}, {"guid": "a\nb", "totalBytes": "1"}]
        fake = FakeTransport(meta=_meta(*items))
        self.assertEqual(self.photos(fake).fetch("msg-1", 1), [JPG])

    def test_non_int_or_negative_total_bytes_is_shape(self):
        for size in ("30000000", "1", 1.5, float(media.MAX_BYTES + 1), True, False, -1, [1], {"n": 1}):
            with self.subTest(size=size):
                self.refused([{"guid": "att-1", "totalBytes": size}])

    def test_bad_total_bytes_on_second_of_two_is_shape(self):
        self.refused([{"guid": "att-1", "totalBytes": 10}, {"guid": "att-2", "totalBytes": "10"}], n=2)

    def test_total_bytes_none_absent_or_zero_downloads(self):
        for item in ({"guid": "att-1", "totalBytes": None}, {"guid": "att-1"}, {"guid": "att-1", "totalBytes": 0}):
            with self.subTest(item=item):
                fake = FakeTransport(meta=_meta(item))
                self.assertEqual(self.photos(fake).fetch("msg-1", 1), [JPG])
                self.assertEqual(len(fake.calls), 2)

    def test_int_total_bytes_over_cap_is_still_too_large(self):
        self.refused([{"guid": "att-1", "totalBytes": media.MAX_BYTES + 1}], "too-large")

    def test_shape_is_checked_before_too_large(self):
        items = [{"guid": "att-1", "totalBytes": media.MAX_BYTES + 1}, {"guid": "att-2", "totalBytes": "1"}]
        self.refused(items, n=2)

    def test_fewer_than_n_valid_guids_is_still_count_error(self):
        self.refused([{"guid": "att-1"}], "attachment-count", n=2)
        self.refused([{"guid": "att-1"}, {"guid": "att-2"}], "attachment-count", n=3)

    def test_fewer_than_n_with_a_bad_guid_is_shape(self):
        self.refused([{"guid": "att-1"}, {"guid": "att-1"}], n=3)
        self.refused([{"guid": "a" * 201}], n=2)

    def test_error_never_holds_password_or_guid(self):
        guid = "secret-guid-" + "z" * 190
        exc = self.refused([{"guid": guid}])
        for text in (str(exc), repr(exc), repr(exc.args)):
            self.assertNotIn(PASSWORD, text)
            self.assertNotIn(guid[:12], text)
        self.assertIsInstance(exc, BridgeError)


del PhotosTests  # imported for its helpers only; its tests run in their own module

if __name__ == "__main__":
    unittest.main()
