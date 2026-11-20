"""Exercise the byte-only install check against an offline Git fixture."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_mac_parity.py"
RELEASE = b"# synthetic released forwarder\r\n"
STALE = RELEASE.replace(b"\r\n", b"\n")


class InstallMacParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.root = Path(temp.name)
        cls.repo = cls.root / "fixture checkout"
        cls.repo.mkdir()
        cls.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        cls.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        cls.git("init", "--quiet", "--template=")
        cls.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--quiet", "--allow-empty", "-m", "No forwarder yet")
        cls.without_forwarder = cls.git("rev-parse", "HEAD").strip().decode("ascii")
        source = cls.repo / "mac/hass_forwarder.py"
        source.parent.mkdir()
        source.write_bytes(RELEASE)
        cls.git("-c", "core.autocrlf=false", "add", "mac/hass_forwarder.py")
        cls.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--quiet", "-m", "Selected release")
        cls.commit = cls.git("rev-parse", "HEAD").strip().decode("ascii")
        source.write_bytes(STALE)
        cls.git("add", "mac/hass_forwarder.py")
        cls.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--quiet", "-m", "Different checkout HEAD")
        cls.match = cls.root / "match.py"
        cls.match.write_bytes(RELEASE)
        cls.stale = cls.root / "stale.py"
        cls.stale.write_bytes(STALE)

    @classmethod
    def git(cls, *args):
        return subprocess.run(["git", *args], cwd=cls.repo, env=cls.env, check=True,
                              capture_output=True, timeout=10).stdout

    def check_copy(self, copy, commit=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo),
             "--commit", self.commit if commit is None else commit, "--deployed", str(copy)],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10,
        )

    def test_matches_commit_blob_not_working_tree(self):
        # Hashing the modified working tree would fail this positive control.
        result = self.check_copy(self.match)
        self.assertEqual(result.returncode, 0, result.stderr)
        digest = hashlib.sha256(RELEASE).hexdigest()
        self.assertIn(f"Byte parity match: SHA-256 release={digest[:12]} deployed={digest[:12]}.",
                      result.stdout)
        self.assertIn("process status and delivery were not checked", result.stdout)
        self.assertNotIn(digest, result.stdout + result.stderr)
        self.assertNotIn(RELEASE.decode().strip(), result.stdout + result.stderr)

    def test_rejects_stale_copy_even_when_working_tree_matches_it(self):
        # A text-mode read could normalize away the only byte difference (CRLF).
        result = self.check_copy(self.stale)
        self.assertNotEqual(result.returncode, 0)
        release = hashlib.sha256(RELEASE).hexdigest()
        deployed = hashlib.sha256(STALE).hexdigest()
        self.assertIn(f"Byte parity mismatch: SHA-256 release={release[:12]} deployed={deployed[:12]}.",
                      result.stdout)
        for digest in (release, deployed):
            self.assertNotIn(digest, result.stdout + result.stderr)

    def test_rejects_missing_non_regular_and_symlinked_copies(self):
        # A good-target symlink could falsely pass; a FIFO could block on open.
        missing = self.root / "missing.py"
        link = self.root / "linked.py"
        link.symlink_to(self.match)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for copy, reason in ((missing, "missing"), (self.repo, "not a regular file"),
                             (link, "symlink"), (fifo, "not a regular file")):
            with self.subTest(copy=copy.name):
                result = self.check_copy(copy)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)
                self.assertFalse(result.stdout)

    def test_refuses_unpinned_or_unavailable_source(self):
        # Never fall back to HEAD/the checkout when the requested source is invalid.
        for commit, reason in (("HEAD", "full hexadecimal commit SHA"),
                               (self.commit[:12], "full hexadecimal commit SHA"),
                               ("0" * len(self.commit), "locally available commit"),
                               (self.without_forwarder, "cannot read the mac/hass_forwarder.py blob")):
            with self.subTest(reason=reason):
                result = self.check_copy(self.match, commit)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)
                self.assertFalse(result.stdout)
