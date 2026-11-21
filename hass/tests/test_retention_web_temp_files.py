"""Only finished web images affect the read-only retention report."""
import unittest
from pathlib import Path

from hass.tests import test_retention as base


class WebTempFilesTest(unittest.TestCase):
    media: Path
    tmp: Path
    setUp = base.RetentionTest.setUp
    run_main = base.RetentionTest.run_main
    report = base.RetentionTest.report
    original = base.RetentionTest.original

    def web_folder(self):
        folder = self.media / "web" / base.SHA_OLD[:2]
        folder.mkdir(parents=True)
        return folder

    def test_writer_temp_does_not_add_an_orphan(self):
        # A stem-only scan counts the writer's leftover temporary file as another orphan.
        folder = self.web_folder()
        (folder / f"{base.SHA_OLD}.png").write_bytes(b"web image")
        code, control, _ = self.report("--media", str(self.media))
        self.assertEqual((code, control["webOrphans"]), (0, 1))

        (folder / ".tmp-fixture").write_bytes(b"unfinished")
        before = base.tree(self.tmp)
        code, doc, _ = self.report("--media", str(self.media))
        self.assertEqual(base.tree(self.tmp), before)
        self.assertEqual((code, doc["webOrphans"], doc["deletes"]), (0, 1, 0))

    def test_same_stem_non_image_does_not_add_a_dated_web_copy(self):
        # A stem-only join credits the metadata file with the original's date as well.
        self.original(base.SHA_OLD, {"received_at": base.iso(base.OLD)}, 3)
        folder = self.web_folder()
        (folder / f"{base.SHA_OLD}.jpg").write_bytes(b"web image")
        code, control, _ = self.report("--media", str(self.media))
        self.assertEqual((code, control["media"]["web"], control["webOrphans"]), (0, 1, 0))

        (folder / f"{base.SHA_OLD}.json").write_text("{}", encoding="utf-8")
        before = base.tree(self.tmp)
        code, doc, _ = self.report("--media", str(self.media))
        self.assertEqual(base.tree(self.tmp), before)
        self.assertEqual((code, doc["media"]["web"], doc["webOrphans"], doc["deletes"]), (0, 1, 0, 0))
