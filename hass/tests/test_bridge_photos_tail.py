"""RF0720-5 (H10) tests: BlueBubblesPhotos.fetch(guid, n) shape-checks only the first n attachments it will download;
a later entry that is not an object or has no text guid (a sticker, a link preview) never refuses the photos.
Fake transports only: nothing listens, connects or downloads.
Run: python3 -m unittest hass.tests.test_bridge_photos_tail -v"""

import json
import unittest

from hass.tests.test_bridge_photos import JPG, FakeTransport, PhotosTests, _meta

BAD = ("sticker", {}, {"guid": ""}, {"guid": 5}, {"guid": None}, None, ["att-9"])


class AttachmentTailTests(unittest.TestCase):
    setUp, photos, fails = PhotosTests.setUp, PhotosTests.photos, PhotosTests.fails  # helpers only, not its tests

    def refused(self, items, code="shape", n=1):
        exc = self.fails(fake := FakeTransport(meta=_meta(*items), files={}), code, n=n)
        self.assertEqual(len(fake.calls), 1)  # metadata only: nothing downloaded
        return exc

    def test_null_guid_after_first_n_keeps_the_photo(self):
        fake = FakeTransport(meta=_meta({"guid": "att-1"}, {"guid": None}))
        self.assertEqual(self.photos(fake).fetch("msg-1", 1), [JPG])
        self.assertEqual(len(fake.calls), 2)  # metadata + one download

    def test_each_bad_entry_after_first_n_is_never_read(self):
        for bad in BAD:
            with self.subTest(bad=bad):
                fake = FakeTransport(meta=_meta({"guid": "att-1"}, bad))
                self.assertEqual(self.photos(fake).fetch("msg-1", 1), [JPG])
                self.assertEqual(len(fake.calls), 2)

    def test_all_bad_entries_after_first_two_keep_both_photos(self):
        fake = FakeTransport(meta=_meta({"guid": "att-1"}, {"guid": "att-2"}, *BAD),
                             files={"att-1": (200, JPG), "att-2": (200, JPG + b"2")})
        self.assertEqual(self.photos(fake).fetch("msg-1", 2), [JPG, JPG + b"2"])
        self.assertEqual(len(fake.calls), 3)

    def test_bad_entry_inside_first_n_is_shape(self):
        for bad in BAD:
            with self.subTest(bad=bad, at="second"):
                self.refused([{"guid": "att-1"}, bad], n=2)
            with self.subTest(bad=bad, at="first"):
                self.refused([bad, {"guid": "att-2"}], n=2)
            with self.subTest(bad=bad, at="only"):
                self.refused([bad, {"guid": "att-2"}], n=1)

    def test_bad_entry_inside_first_n_wins_over_attachment_count(self):
        self.refused([{"guid": "att-1"}, {"guid": None}], n=2)
        self.refused([{"guid": "att-1"}, "sticker"], n=3)

    def test_fewer_than_n_good_entries_is_still_count_error(self):
        self.refused([{"guid": "att-1"}], "attachment-count", n=2)

    def test_attachments_not_a_list_is_shape(self):
        for value in ({}, "x", None, 1, {"guid": "att-1"}):
            body = json.dumps({"status": 200, "data": {"attachments": value}}).encode()
            for n in (1, 2):
                with self.subTest(value=value, n=n):
                    self.fails(fake := FakeTransport(meta=(200, body), files={}), "shape", n=n)
                    self.assertEqual(len(fake.calls), 1)


del PhotosTests  # imported for its helpers only; its tests run in their own module

if __name__ == "__main__":
    unittest.main()
