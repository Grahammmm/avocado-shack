"""RF0250-5 tests: the H21 retention report counts web copies whose original is gone (top-level webOrphans).

Counts only; nothing is dated or deleted and no name prints. Temp trees built like test_retention.
Run: python3 -B -m unittest hass.tests.test_retention_web_orphans -v
"""
import os, unittest  # noqa: E401
from unittest import mock

from hass import retention
from hass.tests import test_retention as base

SHA_GONE, SHA_SIDECAR = "aa" + "4" * 62, "bb" + "5" * 62


class WebOrphansTest(unittest.TestCase):
    setUp, run_main, report, original = (base.RetentionTest.setUp, base.RetentionTest.run_main,
                                         base.RetentionTest.report, base.RetentionTest.original)

    def web(self, sha, root=None):
        (folder := (root or self.media / "web") / sha[:2]).mkdir(parents=True, exist_ok=True)
        (folder / f"{sha}.jpg").write_bytes(b"w")
        return folder

    def media_report(self):
        return self.report("--media", str(self.media))

    def test_no_media_flag_is_null(self):
        code, doc, _ = self.report()
        self.assertEqual((code, doc["webOrphans"], doc["media"]), (0, None, None))

    def test_one_orphan_counted_media_dict_unchanged_and_no_names_print(self):
        self.original(base.SHA_OLD, {"received_at": base.iso(base.OLD)}, 11)
        self.original(base.SHA_NEW, {"received_at": base.iso(base.NEW)}, 13)
        for sha in (base.SHA_OLD, base.SHA_NEW): self.web(sha)
        code, before, _ = self.media_report()
        self.assertEqual((code, before["webOrphans"]), (0, 0))
        self.web(SHA_GONE)
        code, doc, out = self.media_report()
        self.assertEqual((code, doc["webOrphans"], doc["deletes"]), (0, 1, 0))
        self.assertEqual(doc["media"], before["media"])
        self.assertEqual(list(doc)[-2:], ["webOrphans", "deletes"])
        for sha in (SHA_GONE, base.SHA_OLD, base.SHA_NEW): self.assertNotIn(sha[2:18], out)
        self.assertTrue((self.media / "web" / SHA_GONE[:2] / f"{SHA_GONE}.jpg").is_file())  # counted, not deleted

    def test_original_without_sidecar_still_owns_its_web_copy(self):
        (folder := self.media / "originals" / base.SHA_UNDATED[:2]).mkdir(parents=True)
        (folder / f"{base.SHA_UNDATED}.jpg").write_bytes(b"j")
        self.web(base.SHA_UNDATED)
        code, doc, _ = self.media_report()
        self.assertEqual((code, doc["webOrphans"], doc["media"]["undated"]), (0, 0, 1))

    def test_sidecar_alone_is_no_original(self):
        (folder := self.media / "originals" / SHA_SIDECAR[:2]).mkdir(parents=True)
        (folder / f"{SHA_SIDECAR}.json").write_text('{"received_at": "%s"}' % base.iso(base.OLD))
        (folder / f"{SHA_SIDECAR}.tmp").write_bytes(b"t")  # a leftover temp file is no original either
        self.web(SHA_SIDECAR)
        code, doc, out = self.media_report()
        self.assertEqual((code, doc["webOrphans"]), (0, 1))
        self.assertNotIn(SHA_SIDECAR[2:18], out)

    def test_links_folders_and_top_level_web_files_are_not_counted(self):
        folder = self.web(base.SHA_OLD)  # an orphan target for the links below, counted once itself
        (self.media / "web" / f"{SHA_GONE}.jpg").write_bytes(b"w")  # directly in web/, not in a subfolder
        (folder / f"{SHA_GONE}.jpg").symlink_to(folder / f"{base.SHA_OLD}.jpg")
        (folder / f"{SHA_SIDECAR}.jpg").mkdir()
        (self.media / "web" / "zz").symlink_to(folder)  # a linked subfolder is never entered
        code, doc, _ = self.media_report()
        self.assertEqual((code, doc["webOrphans"]), (0, 1))

    def test_missing_or_linked_web_folder_counts_zero(self):
        self.original(base.SHA_OLD, {"received_at": base.iso(base.OLD)}, 11)
        code, doc, _ = self.media_report()
        self.assertEqual((code, doc["webOrphans"]), (0, 0))
        self.web(SHA_GONE, root=self.tmp / "elsewhere")
        (self.media / "web").symlink_to(self.tmp / "elsewhere")
        code, doc, _ = self.media_report()
        self.assertEqual((code, doc["webOrphans"], doc["media"]["web"]), (0, 0, 0))

    def test_unreadable_web_subfolder_is_unavailable_exit_1(self):
        self.original(base.SHA_OLD, {"received_at": base.iso(base.OLD)}, 11)
        sub, real = os.fspath(self.web(SHA_GONE)), os.scandir

        def scandir(path):
            if os.fspath(path) == sub: raise PermissionError(13, "denied")
            return real(path)
        with mock.patch.object(retention.os, "scandir", scandir):
            code, doc, out = self.media_report()
        self.assertEqual((code, doc["webOrphans"], doc["deletes"]), (1, "unavailable", 0))
        self.assertEqual(doc["screenshots"], {"files": 1, "bytes": 7})
        self.assertTrue({"inbox", "messages", "media", "backups", "days", "cutoff"} <= set(doc))
        self.assertNotIn(SHA_GONE[2:18], out)


if __name__ == "__main__":
    unittest.main()
