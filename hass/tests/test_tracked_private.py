"""H21: fail, naming the path, if a private runtime file is tracked by Git (force-added or Hass-state-shaped).
Reads `git ls-files` only. Outside a checkout the repo test skips, except with GITHUB_ACTIONS=true, where it fails."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
STATE_NAMES = frozenset({"conversation.sqlite3", "inbox.sqlite3", "writer.lock"})
BACKUP_RE = re.compile(r"hass-state-\d{8}T\d{6}Z")


class NotACheckout(Exception):
    """git is missing, failed, or the folder is not the top of a checkout."""


def private_reasons(paths):
    """`<path>: <reason>` for every path that looks like Hass private state (first matching reason only)."""
    out = []
    for path in paths:
        parts = PurePosixPath(path).parts
        name = parts[-1] if parts else ""
        if name in STATE_NAMES:
            reason = f"Hass state file {name}"
        elif name.endswith((".sqlite3", ".db")) or ".sqlite3-" in name:
            reason = "database file"
        elif name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            reason = "environment file"
        elif any(BACKUP_RE.fullmatch(p) for p in parts):
            reason = "hass-state backup"
        elif ".runtime" in parts:
            reason = ".runtime folder"
        else:
            continue
        out.append(f"{path}: {reason}")
    return out


def git(repo, *args):
    try:
        run = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                             encoding="utf-8", errors="surrogateescape")
    except OSError as exc:
        raise NotACheckout(type(exc).__name__) from exc
    if run.returncode != 0:
        raise NotACheckout(f"git exit {run.returncode}")
    return run.stdout


def tracked_problems(repo):
    """Ignored-but-tracked paths first, then private-looking tracked paths (`-z`: names kept intact)."""
    if Path(git(repo, "rev-parse", "--show-toplevel").strip()).resolve() != Path(repo).resolve():
        raise NotACheckout("not the top of a checkout")
    ignored = [p for p in git(repo, "ls-files", "-ci", "--exclude-standard", "-z").split("\0") if p]
    tracked = [p for p in git(repo, "ls-files", "-z").split("\0") if p]
    return [f"{p}: tracked but ignored by .gitignore" for p in ignored] + private_reasons(tracked)


def scan(repo):
    try:
        return tracked_problems(repo)
    except NotACheckout:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            raise AssertionError("not a git checkout (CI must not skip this check)") from None
        raise unittest.SkipTest("not a git checkout") from None


class TrackedPrivateTests(unittest.TestCase):
    def test_repo_tracks_no_private_runtime_file(self):
        problems = scan(REPO)
        self.assertEqual(problems, [], "private runtime files are tracked:\n" + "\n".join(problems))

    def test_matcher_flags_private_paths_with_reason(self):
        self.assertEqual(private_reasons([
            "x/conversation.sqlite3", "a/inbox.sqlite3-wal", "state/writer.lock", "b.db", ".env", "commerce/.env.local",
            "backups/hass-state-20261031T120000Z/MANIFEST.json", "site/.runtime/x"]), [
            "x/conversation.sqlite3: Hass state file conversation.sqlite3", "a/inbox.sqlite3-wal: database file",
            "state/writer.lock: Hass state file writer.lock", "b.db: database file", ".env: environment file",
            "commerce/.env.local: environment file", "backups/hass-state-20261031T120000Z/MANIFEST.json: hass-state backup",
            "site/.runtime/x: .runtime folder"])

    def test_matcher_passes_lookalikes(self):
        self.assertEqual(private_reasons(["commerce/.env.example", "docs/hass-state-notes.md", "hass/statebackup.py",
                                          "dbtools/readme.md", "x.sqlite3.md", "hass-state-2026T1Z/a"]), [])

    def test_force_added_ignored_file_and_unicode_path_are_reported_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q")
            (Path(tmp) / ".gitignore").write_text("*.secret\n")
            (Path(tmp) / "a.secret").write_text("synthetic\n")
            (Path(tmp) / "dir é").mkdir()
            (Path(tmp) / "dir é" / "writer.lock").write_text("")
            git(tmp, "add", ".gitignore", "dir é/writer.lock")
            self.assertEqual(tracked_problems(tmp), ["dir é/writer.lock: Hass state file writer.lock"])
            git(tmp, "add", "-f", "a.secret")
            self.assertEqual(tracked_problems(tmp), [
                "a.secret: tracked but ignored by .gitignore", "dir é/writer.lock: Hass state file writer.lock"])

    def test_not_a_checkout_skips_locally_and_fails_in_ci(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
                self.assertRaisesRegex(unittest.SkipTest, "^not a git checkout$", scan, tmp)
            with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                self.assertRaisesRegex(AssertionError, "not a git checkout", scan, tmp)
                with mock.patch("subprocess.run", side_effect=FileNotFoundError("git")):
                    self.assertRaises(AssertionError, scan, REPO)
