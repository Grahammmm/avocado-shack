"""RF0250-1 tests: a pre-write read problem with the site tree is recorded as `install: failed` naming the path.

Reuses the SHOP-2 fixture (temp writer repo + temp site dir). Nothing touches the checkout or the live site.
Run: python3 -B -m unittest hass.tests.test_install_preread
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import editor, install
from hass.tests import test_install as base  # module import: its InstallTest tests are not collected twice

SECRET = "denied-detail-7f3a"  # exception text that must never be stored or printed
PREFIX = base.PREFIX


class PreReadTest(unittest.TestCase):
    setUp, set_site, applied, site_paths, install, snapshot, status = (getattr(base.InstallTest, n) for n in (
        "setUp", "set_site", "applied", "site_paths", "install", "snapshot", "status"))

    def hashes(self):
        return {k: hashlib.sha256(v).hexdigest() for k, v in self.snapshot().items()}

    def record(self, cid):
        return editor._read(self.repo.state / "changes" / f"{cid}.json")

    def assert_recorded_failure(self, cid, out, reason):
        self.assertEqual((out["result"], out["reason"]), ("failed", reason), out)
        inst = self.record(cid)["install"]
        self.assertEqual((inst["state"], inst["reason"], inst["commit"]), ("failed", reason, out["commit"]))
        self.assertNotIn(SECRET, json.dumps(self.record(cid)))
        self.assertEqual(self.status(cid), f"committed, not installed (install failed: {reason})")
        self.assertEqual([p.name for p in self.site.rglob(install.TMP_PREFIX + "*")], [])

    def deny_read(self, sub):
        real = install._current

        def current(target):
            if Path(target) == self.site / sub: raise PermissionError(SECRET)
            return real(target)
        return mock.patch.object(install, "_current", current)

    def test_linked_folder_on_the_way_is_a_recorded_not_regular_failure(self):
        cid, _commit = self.applied()
        (self.repo.wt / PREFIX / "hike" / "index.html").write_bytes(b"<p>hike edit</p>\n")  # the commit also edits
        base.git(self.repo.wt, "commit", "-q", "-a", "--amend", "--no-edit")  # hike/index.html (same subject)
        path = self.repo.state / "changes" / f"{cid}.json"
        editor._write_json(path, {**editor._read(path), "commit": self.repo.head()})
        self.assertIn("hike/index.html", self.site_paths(self.repo.head()))
        other = tempfile.TemporaryDirectory(prefix="hass-outside-")
        self.addCleanup(other.cleanup)
        outside = Path(other.name) / "hike"
        (self.site / "hike").rename(outside)
        (self.site / "hike").symlink_to(outside, target_is_directory=True)
        outside_before = {p.name: p.read_bytes() for p in outside.iterdir()}
        before = self.hashes()
        out = self.install(cid)
        self.assert_recorded_failure(cid, out, "site path is not a regular file: hike/index.html")
        self.assertEqual({p.name: p.read_bytes() for p in outside.iterdir()}, outside_before, "link target untouched")
        self.assertEqual(self.hashes(), before)
        (self.site / "hike").unlink()
        outside.rename(self.site / "hike")
        self.assertEqual(self.install(cid)["result"], "installed", "installs once the link is gone")
        self.assertEqual(self.record(cid)["install"]["state"], "installed")

    def test_unreadable_site_file_is_recorded_and_nothing_is_written(self):
        cid, _commit = self.applied()
        before = self.hashes()
        with self.deny_read("index.html"):
            out = self.install(cid)
        self.assert_recorded_failure(cid, out, "site file cannot be read: index.html")
        self.assertEqual(self.hashes(), before, "every site file unchanged")
        self.assertEqual(self.install(cid)["result"], "installed", "a clean retry installs normally")
        self.assertEqual(self.status(cid), "installed")

    def test_mode_read_error_is_recorded_and_nothing_is_written(self):
        cid, commit = self.applied()
        sub = self.site_paths(commit)[0]
        target, real_stat, real_current, armed = self.site / sub, Path.stat, install._current, []

        def current(path):
            data = real_current(path)
            if Path(path) == target: armed.append(True)  # the next stat of this target is the mode read
            return data

        def stat(path, *args, **kwargs):
            if armed and path == target: raise OSError(SECRET)
            return real_stat(path, *args, **kwargs)
        before = self.hashes()
        with mock.patch.object(install, "_current", current), mock.patch.object(Path, "stat", stat):
            out = self.install(cid)
        self.assertTrue(armed, "the target was read before its mode")
        self.assert_recorded_failure(cid, out, f"site file cannot be read: {sub}")
        self.assertEqual(self.hashes(), before)
        self.assertEqual(self.install(cid)["result"], "installed")

    def test_folder_check_error_is_recorded_not_raised(self):
        cid, _commit = self.applied()
        before, real = self.hashes(), install.sitegen._check_folders

        def check(root, rel):
            if Path(root) == self.site: raise OSError(40, SECRET)  # ELOOP below site_dir only
            return real(root, rel)
        with mock.patch.object(install.sitegen, "_check_folders", check):
            out = self.install(cid)
        first = self.site_paths(out["commit"])[0]
        self.assert_recorded_failure(cid, out, f"site file cannot be read: {first}")
        self.assertEqual(self.hashes(), before)

    def test_cli_prints_failed_not_io_error_and_exits_1(self):
        cid, _commit = self.applied()
        buf = io.StringIO()
        with self.deny_read("index.html"), contextlib.redirect_stdout(buf):
            code = editor.main(["install", cid, "--state", str(self.repo.state)])
        lines = buf.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        out = json.loads(lines[0])
        self.assertEqual((code, out["result"], out["reason"]), (1, "failed", "site file cannot be read: index.html"))
        self.assertNotIn(SECRET, buf.getvalue())
        self.assertNotIn(SECRET, json.dumps(self.record(cid)))


if __name__ == "__main__":
    unittest.main()
