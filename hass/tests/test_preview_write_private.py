"""RF0550-1 tests: a preview screenshot is written whole via a private temp file and rename, or not at all.

A link, folder or FIFO at the PNG path is refused with OSError and nothing it points to is touched; through
``Previewer.capture`` that refusal is the usual ok-False result (fake ``node`` from test_preview_viewports)."""

import os, stat, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import preview
from hass.tests import test_preview_viewports as viewports
from hass.tests.test_editor import EditorTestCase

PNG = b"\x89PNG\r\n\x1a\nnew-shot"
REFUSED = "screenshot path is not a regular file"


def mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


class WritePrivateTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory(prefix="hass-write-private-")
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        self.shots = self.root / "state" / "screenshots"
        self.path = self.shots / "c1-proposal.png"
        self.outside = self.root / "outside.png"

    def leftovers(self):
        return [p.name for p in self.shots.iterdir() if p.name.endswith(".tmp")]

    def assertRefused(self):
        with self.assertRaises(OSError) as caught:
            preview._write_private(self.path, PNG)
        self.assertEqual(str(caught.exception), REFUSED)
        self.assertEqual(self.leftovers(), [])

    def test_new_path_in_missing_folder_is_written_private(self):
        preview._write_private(self.path, PNG)
        self.assertEqual(self.path.read_bytes(), PNG)
        self.assertEqual((mode(self.path), mode(self.shots)), (0o600, 0o700))
        self.assertTrue(stat.S_ISREG(os.lstat(self.path).st_mode))
        self.assertEqual(self.leftovers(), [])

    def test_existing_regular_file_is_replaced_whole(self):
        self.shots.mkdir(parents=True)
        self.path.write_bytes(b"old bytes that are longer than the new shot")
        self.path.chmod(0o644)
        preview._write_private(self.path, PNG)
        self.assertEqual((self.path.read_bytes(), mode(self.path)), (PNG, 0o600))
        self.assertEqual(self.leftovers(), [])

    def test_link_to_outside_file_is_refused_untouched(self):
        self.shots.mkdir(parents=True)
        self.outside.write_bytes(b"owner file")
        self.outside.chmod(0o644)
        self.path.symlink_to(self.outside)
        self.assertRefused()
        self.assertEqual((self.outside.read_bytes(), mode(self.outside)), (b"owner file", 0o644))
        self.assertEqual(os.readlink(self.path), str(self.outside))

    def test_dangling_link_is_refused_and_target_not_created(self):
        self.shots.mkdir(parents=True)
        self.path.symlink_to(self.outside)
        self.assertRefused()
        self.assertFalse(os.path.lexists(self.outside))
        self.assertEqual(os.readlink(self.path), str(self.outside))

    def test_folder_or_fifo_at_path_is_refused_unchanged(self):
        self.shots.mkdir(parents=True)
        self.path.mkdir()
        (self.path / "keep").write_bytes(b"k")
        self.assertRefused()
        self.assertEqual([p.name for p in self.path.iterdir()], ["keep"])
        self.path = self.shots / "c2-proposal.png"
        os.mkfifo(self.path)
        self.assertRefused()
        self.assertTrue(stat.S_ISFIFO(os.lstat(self.path).st_mode))

    def test_write_failure_keeps_old_file_and_leaves_no_temp(self):
        self.shots.mkdir(parents=True)
        self.path.write_bytes(b"old shot")
        with mock.patch.object(preview.os, "fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError) as caught:
                preview._write_private(self.path, PNG)
        self.assertEqual(str(caught.exception), "disk full")
        self.assertEqual(self.path.read_bytes(), b"old shot")
        self.assertEqual(self.leftovers(), [])


class CaptureRefusesLinkTests(EditorTestCase):
    setUp = viewports.ViewportTests.setUp
    capture = viewports.ViewportTests.capture

    def test_capture_with_linked_png_path_is_ok_false(self):
        self.out.parent.mkdir()
        outside = self.tmp / "owner.png"
        outside.write_bytes(b"owner file")
        self.out.symlink_to(outside)
        plan = {"phone": {"checks": viewports.PASS}, "desktop": {"checks": viewports.PASS}}
        result, calls, _server = self.capture(plan)
        self.assertEqual((result["ok"], result["png"]), (False, None))
        self.assertTrue(result["error"].startswith("OSError: " + REFUSED), result["error"])
        self.assertEqual(outside.read_bytes(), b"owner file")
        self.assertTrue(self.out.is_symlink())
        self.assertFalse(self.desktop_png.exists())
        self.assertEqual([c["viewport"] for c in calls], ["phone", "desktop"])
