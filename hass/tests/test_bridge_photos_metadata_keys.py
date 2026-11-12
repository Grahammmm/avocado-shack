"""RF0825-12: repeated consumed metadata keys are a shape refusal; ignored/tail repeats stay compatible. Fake transport only."""
import unittest
from unittest import mock

from hass import media
from hass.bridge import BridgeError
from hass.bridge_photos import BlueBubblesPhotos

ids = BlueBubblesPhotos._attachment_ids
SHAPE = ("shape", [])


def att(body):
    return ('{"data":{"attachments":[%s]}}' % body).encode()


class MetadataKeys(unittest.TestCase):
    def test_repeated_selected_guid_and_size_are_shape(self):
        for body in ('{"guid":"A","guid":"B"}', '{"guid":"A","guid":"A"}', '{"gu\\u0069d":"A","guid":"B"}',
                     '{"guid":"B","guid":"A"}', '{"guid":"P","totalBytes":999999999,"totalBytes":1}',
                     '{"guid":"P","totalBytes":1,"totalBytes":999999999}', '{"guid":"P","totalBytes":1,"totalBytes":1}',
                     '{"guid":"P","totalByte\\u0073":1,"totalBytes":1}'):
            with self.subTest(body=body):
                self.assertEqual(ids(att(body), 1), SHAPE)

    def test_repeated_data_and_attachment_list_are_shape(self):
        for raw in (b'{"data":{"attachments":[]},"data":{"attachments":[{"guid":"A"}]}}',
                    b'{"data":{"attachments":[{"guid":"A"}]},"data":{"attachments":[{"guid":"A"}]}}',
                    b'{"data":{"attachments":[],"attachments":[{"guid":"A"}]}}',
                    b'{"data":{"attachments":[{"guid":"A"}],"attachments":[{"guid":"A"}]}}'):
            with self.subTest(raw=raw):
                self.assertEqual(ids(raw, 1), SHAPE)

    def test_duplicate_after_n_is_not_validated(self):
        dup = '{"guid":"B","totalBytes":5,"totalBytes":6}'
        self.assertEqual(ids(att('{"guid":"A","totalBytes":3},' + dup), 1), (None, [("A", 3)]))
        self.assertEqual(ids(att('{"guid":"A","totalBytes":3},' + dup), 2), SHAPE)

    def test_ignored_duplicates_remain_compatible(self):
        raw = (b'{"x":1,"x":2,"data":{"y":1,"y":2,"attachments":[{"guid":"A","mime":"a","mime":"b","n":{"k":1,"k":2}}]}}')
        self.assertEqual(ids(raw, 1), (None, [("A", None)]))

    def test_existing_error_precedence_and_size_boundary(self):
        self.assertEqual(ids(b'{"data":{"attachments":[{"guid":"A","guid":"B"}', 1), ("not-json", []))
        self.assertEqual(ids(att('{"guid":"A","guid":"B"}'), 3), SHAPE)  # beats attachment-count
        self.assertEqual(ids(att('{"guid":"A","totalBytes":%d,"totalBytes":1}' % (media.MAX_BYTES + 1)), 1), SHAPE)
        self.assertEqual(ids(att('{"guid":"A","totalBytes":-1}'), 1), SHAPE)
        self.assertEqual(ids(att('{"guid":"A","totalBytes":%d}' % media.MAX_BYTES), 1), (None, [("A", media.MAX_BYTES)]))
        self.assertEqual(ids(att('{"guid":"A","totalBytes":%d}' % (media.MAX_BYTES + 1)), 1), ("too-large", []))
        self.assertEqual(ids(att('{"guid":"A"},{"guid":"A"}'), 2), SHAPE)

    def _photos(self, meta):
        p = BlueBubblesPhotos.__new__(BlueBubblesPhotos)
        calls = []

        def get(path, accept, limit):
            calls.append(path)
            return (None, 200, meta) if len(calls) == 1 else (None, 200, b"img")
        p._get, p._password_file = get, "unused"
        return p, calls

    def test_second_selected_duplicate_prevents_first_download_and_is_private(self):
        canary = "CANARY-GUID"
        p, calls = self._photos(att('{"guid":"A","totalBytes":3},{"guid":"%s","guid":"B"}' % canary))
        with mock.patch("hass.bridge_photos._private_file", return_value="x"), \
                mock.patch("hass.bridge_photos.Path.read_text", return_value="pw"):
            with self.assertRaises(BridgeError) as cm:
                p.fetch("m1", 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual((cm.exception.code, cm.exception.status), ("shape", None))
        self.assertIsNone(cm.exception.__cause__)
        self.assertTrue(cm.exception.__suppress_context__ or cm.exception.__context__ is None)
        self.assertNotIn(canary, repr(cm.exception) + str(cm.exception))

    def test_valid_metadata_downloads(self):
        p, calls = self._photos(att('{"guid":"A","totalBytes":3}'))
        with mock.patch("hass.bridge_photos._private_file", return_value="x"), \
                mock.patch("hass.bridge_photos.Path.read_text", return_value="pw"):
            self.assertEqual(p.fetch("m1", 1), [b"img"])
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
