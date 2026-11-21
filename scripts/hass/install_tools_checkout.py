#!/usr/bin/env python3
"""Check the reviewed tools checkout offline (origin is a local config check)."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess


NAME = "install_tools_checkout"


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's normal diagnostic may echo a mistyped private value.
        super().error("invalid arguments")


def git(repo, *args):
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
            cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": ""},
            check=True,
        ).stdout
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def normalize_url(url):
    return url.removesuffix(b"/").removesuffix(b".git")


def remote_finding(repo, expected):
    raw = git(repo, "config", "--null", "--get-all", "remote.origin.url")
    if raw in (None, b"", b"\0"):
        return "no-remote"
    # One exact value, not a substring, remote rewrite, or choice among URLs.
    actual = raw.removesuffix(b"\0")
    if (not raw.endswith(b"\0") or not actual.decode("utf-8", "replace").isprintable()
            or not expected.isprintable() or not normalize_url(actual)
            or normalize_url(actual) != normalize_url(os.fsencode(expected))):
        return "wrong-remote"
    return None


def install_digests(repo):
    paths = git(repo, "ls-files", "-z", "--", ":(top,glob)scripts/hass/install_*.py")
    if paths is None or (paths and not paths.endswith(b"\0")):
        raise ValueError
    rows = []
    for raw_path in sorted(paths.split(b"\0")[:-1]):
        path = raw_path.decode("utf-8")
        if not path.isprintable():
            raise ValueError
        source = repo / path
        if not stat.S_ISREG(source.lstat().st_mode):
            raise ValueError
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()[:12]
        rows.append(f"install_tool {path} {digest}")
    return rows


def main(argv=None):
    parser = Parser(prog=NAME, description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="checkout root")
    parser.add_argument("--sha", required=True, help="reviewed 40-character commit SHA")
    parser.add_argument("--remote-url", required=True, help="expected origin URL")
    args = parser.parse_args(argv)

    findings = []
    valid_sha = re.fullmatch(r"[0-9a-f]{40}", args.sha)
    if not valid_sha:
        findings.append("bad-sha")
    rows = []
    if git(args.repo, "rev-parse", "--is-inside-work-tree", "--show-prefix") != b"true\n\n":
        findings.append("not-git")
    else:
        if valid_sha and git(args.repo, "rev-parse", "--verify", "HEAD^{commit}") != (
            args.sha.encode("ascii") + b"\n"
        ):
            findings.append("head-mismatch")
        if git(args.repo, "status", "--porcelain", "--untracked-files=all") != b"":
            findings.append("dirty")
        remote = remote_finding(args.repo, args.remote_url)
        if remote:
            findings.append(remote)
        if not findings:
            try:
                rows = install_digests(args.repo)
            except (OSError, ValueError):
                findings.append("dirty")

    if findings:
        for reason in findings:
            print(f"FAIL {reason}")
        print(f"FAIL {NAME}")
        return 1
    for row in rows:
        print(row)
    print(f"PASS {NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
