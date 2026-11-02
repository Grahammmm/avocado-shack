"""RF0310-3 (H10): photos.install refuses with a fixed reply when the existing site photo cannot be read.

Same PhotoRepo harness as test_set_photo (temp Git repo + linked writer worktree with a real assets/products folder and
a private media root outside the repo). Unreadable files are simulated with mocks (CI may run as root). No network.
"""

import os
import unittest
from pathlib import Path
from unittest import mock

from hass import media
from hass.tests.test_catalog_ops import _req
from hass.tests.test_editor import git
from hass.tests.test_product_add_photo import _add
from hass.tests.test_set_photo import OTHER, PID, SetPhotoTestCase, _photo

UNREADABLE = "the website photo file cannot be read"
DIFFERENT = "a different photo already uses that name"


class SiteReadTests(SetPhotoTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.repo.wt / self.target(self.jpg)
        self.web = Path(media.web_copy(self.repo.media, self.jpg)["path"]).read_bytes()

    def commit_at_target(self, data=b"", link=None):
        if link:
            self.path.symlink_to(link)
        else:
            self.path.write_bytes(data)
        git(self.repo.wt, "add", "--", self.target(self.jpg))
        git(self.repo.wt, "commit", "-q", "-s", "-m", "existing site photo")

    def refused(self, reply, op=None):
        before = self.repo.products()
        reason = self.rejected("refused", op or _photo(PID, self.jpg))["reason"]
        self.assertEqual(reason, reply)
        self.assertEqual(self.repo.products(), before)
        return reason

    def test_permission_error_is_the_fixed_reply_without_path_or_error_text(self):
        self.commit_at_target(self.web)
        real = Path.read_bytes

        def read(path):
            if Path(path).name == self.path.name:
                raise PermissionError(13, "Permission denied", str(path))
            return real(path)
        for name, op in (("set_photo", _photo(PID, self.jpg)), ("add", _add(photo=self.jpg, imageAlt="Ripe avocados"))):
            with self.subTest(op=name), mock.patch.object(Path, "read_bytes", autospec=True, side_effect=read):
                reason = self.refused(UNREADABLE, op)
                for leak in (self.path.name, "assets/", "Permission", "Errno", "denied"):
                    self.assertNotIn(leak, reason)
        self.assertEqual(self.path.read_bytes(), self.web)

    def test_other_os_error_from_lstat_is_the_fixed_reply(self):
        real = os.lstat

        def lstat(path, *args, **kwargs):
            if Path(path).name == self.path.name:
                raise OSError(5, "Input/output error")
            return real(path, *args, **kwargs)
        with mock.patch("hass.ops.photos.os.lstat", side_effect=lstat):
            self.refused(UNREADABLE)

    def test_folder_at_the_name_is_the_fixed_reply(self):
        self.path.mkdir()
        self.refused(UNREADABLE)
        self.assertTrue(self.path.is_dir())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFOs on this platform")
    def test_fifo_at_the_name_is_the_fixed_reply_and_never_opened(self):
        os.mkfifo(self.path)
        real = Path.read_bytes

        def read(path):  # opening a FIFO with no writer would block; fail instead
            if Path(path).name == self.path.name:
                raise AssertionError("FIFO opened")
            return real(path)
        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=read):
            self.refused(UNREADABLE)

    def test_symlink_at_the_name_keeps_the_different_photo_reply(self):
        self.commit_at_target(link=self.repo.wt / "README.md")
        self.refused(DIFFERENT)

    def test_same_bytes_are_reused_and_different_bytes_keep_the_reply(self):
        self.commit_at_target(self.web)
        self.repo.run(_photo(PID, self.jpg))
        self.assertNotIn(self.target(self.jpg), self.repo.committed())
        self.assertEqual(self.repo.product(PID)["image"], f"assets/products/{self.path.name}")
        self.path.write_bytes(b"\xff\xd8 not the same photo")
        git(self.repo.wt, "commit", "-q", "-s", "-am", "clash")
        self.refused(DIFFERENT, _photo(OTHER, self.jpg, "Another crate"))

    def test_second_use_in_one_draft_takes_the_queued_bytes_not_the_disk(self):
        reads, real_read = [], Path.read_bytes

        def read(path):
            reads.append(Path(path).name)
            return real_read(path)
        with mock.patch("hass.ops.photos.os", wraps=os) as photos_os, \
                mock.patch.object(Path, "read_bytes", autospec=True, side_effect=read):
            result = self.repo.prepare(_req(_photo(PID, self.jpg), _photo(OTHER, self.jpg, "Another crate")))
        self.assertEqual(result["result"], "ok", result)
        looked = [Path(c.args[0]).name for c in photos_os.lstat.call_args_list]
        self.assertEqual(looked, [self.path.name])  # first use only: absent, so queued; second takes ctx.assets
        self.assertNotIn(self.path.name, reads)


if __name__ == "__main__":
    unittest.main()
