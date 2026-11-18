"""RF1530-1 tests: an OSError from the stored photo's web copy (write or read) is one fixed owner reply, never a crash.

Same temp-repo harness as test_set_photo; the web copy is made to fail with a patched ``media.web_copy``.
"""

import os
import unittest
from unittest import mock

from hass import editor, media
from hass.ops import photos
from hass.tests.test_product_add_photo import _add
from hass.tests.test_set_photo import ALT, PID, SetPhotoTestCase, _photo
from hass.tests.test_store_home_image import _home

SECRET = "/secret/path"
REAL_WEB_COPY = media.web_copy


def _removed_after_copy(root, sha):
    """The real web copy is made, then its file vanishes before the op reads it."""
    out = REAL_WEB_COPY(root, sha)
    os.unlink(out["path"])
    return out


FAILURES = {"write fails": {"side_effect": PermissionError(SECRET)},
            "file gone before read": {"side_effect": _removed_after_copy}}


class StoreOSErrorTests(SetPhotoTestCase):
    def ops(self):
        return {"product.set_photo": _photo(PID, self.jpg), "product.add": _add(photo=self.jpg, imageAlt=ALT),
                "store.set_home_image": _home(self.jpg)}

    def assertFixedReply(self, op):
        products = self.repo.products()
        reason = self.rejected("refused", op)["reason"]
        self.assertEqual(reason, photos.STORE_UNREADABLE)
        for leaked in (SECRET, self.jpg, self.jpg[:12], "Errno", "Permission", "No such file"):
            self.assertNotIn(leaked, reason)
        self.assertEqual(self.repo.products(), products)

    def test_set_photo_web_copy_write_error_is_the_fixed_reply(self):
        with mock.patch.object(media, "web_copy", **FAILURES["write fails"]):
            self.assertFixedReply(_photo(PID, self.jpg))

    def test_set_photo_web_copy_missing_at_read_is_the_fixed_reply(self):
        with mock.patch.object(media, "web_copy", **FAILURES["file gone before read"]):
            self.assertFixedReply(_photo(PID, self.jpg))

    def test_add_and_home_image_get_the_same_reply_for_both_failures(self):
        for name, kwargs in FAILURES.items():
            for op_name, op in self.ops().items():
                if op_name == "product.set_photo":
                    continue
                with self.subTest(failure=name, op=op_name), mock.patch.object(media, "web_copy", **kwargs):
                    self.assertFixedReply(op)

    def test_media_refused_keeps_its_own_reply(self):
        with self.subTest("not-found"):
            self.assertEqual(self.rejected("refused", _photo(PID, "0" * 64))["reason"], media.REPLIES["not-found"])
        self.assertNotEqual(media.REPLIES["not-found"], photos.STORE_UNREADABLE)

    def test_unsafe_state_keeps_its_own_reply(self):
        with mock.patch.object(media, "web_copy", side_effect=editor.UnsafeState("state dir is shared")):
            reason = self.rejected("refused", _photo(PID, self.jpg))["reason"]
        self.assertEqual(reason, "photo store is unusable: state dir is shared")


if __name__ == "__main__":
    unittest.main()
