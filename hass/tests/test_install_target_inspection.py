"""Target inspection must record a named failure before touching the site."""
import os
import unittest
from pathlib import Path
from unittest import mock

from hass.tests import test_install_preread as preread


class TargetInspectionTest(unittest.TestCase):
    site: Path
    setUp, set_site, applied, install, snapshot, status, record, assert_recorded_failure = (
        getattr(preread.PreReadTest, name) for name in (
            "setUp", "set_site", "applied", "install", "snapshot", "status", "record", "assert_recorded_failure"))

    def test_second_lookup_failure_is_recorded_before_any_site_write(self):
        # After lexists sees the file, the next lookup can lose it or be denied.
        cid, _commit = self.applied()
        before = self.snapshot()
        target, real_lstat = self.site / "index.html", os.lstat
        for error in (FileNotFoundError, PermissionError):
            with self.subTest(error=error.__name__):
                lookups = 0

                def lstat(path, *args, **kwargs):
                    nonlocal lookups
                    if Path(path) == target:
                        lookups += 1
                        if lookups == 2:
                            raise error(preread.SECRET)
                    return real_lstat(path, *args, **kwargs)

                with mock.patch.object(os, "lstat", lstat):
                    out = self.install(cid)
                self.assert_recorded_failure(cid, out, "site file cannot be read: index.html")
                self.assertNotIn(preread.SECRET, repr(out))
                self.assertEqual(self.snapshot(), before, "every site file unchanged")
        self.assertEqual(self.install(cid)["result"], "installed", "a clean retry installs normally")
        self.assertEqual(self.record(cid)["install"]["state"], "installed")
