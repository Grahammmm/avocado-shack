#!/usr/bin/env python3
"""Check a selected release for explicit reverts and restored pre-merge files."""

import argparse
import os
import re
import subprocess
import sys


HEX = re.compile(r"[0-9a-fA-F]+")
REVERT = re.compile(rb"This reverts commit ([0-9a-fA-F]+)(?![0-9A-Za-z_])")


class ScanError(ValueError):
    """A reason safe to print without Git diagnostics or input values."""


def local_git(repo):
    # Pin the lookup to --repo, not inherited Git object stores, grafts or refs.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_GRAFT_FILE=os.devnull, GIT_OPTIONAL_LOCKS="0",
               GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")

    def git(*args, allowed=(0,)):
        result = subprocess.run(
            ["git", "--no-pager", "--no-replace-objects", "-C", repo, *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env,
        )
        if result.returncode not in allowed:
            raise ScanError("unknown-commit")
        return result

    return git


def commit_sha(git, value, width):
    if len(value) != width or not HEX.fullmatch(value):
        raise ScanError("bad-sha")
    sha = value.lower()
    if git("cat-file", "-t", sha).stdout != b"commit\n":
        raise ScanError("unknown-commit")
    return sha


def tree(git, sha):
    entries = {}
    for entry in git("ls-tree", "--full-tree", "-rz", sha, "--").stdout.split(b"\0")[:-1]:
        metadata, path = entry.split(b"\t", 1)
        _, kind, oid = metadata.split()
        entries[path] = kind, oid
    return entries


def printable_path(path):
    # Preserve ordinary relative paths, but never let control bytes add lines.
    return "".join(
        char if char.isprintable() and char != "\\" else ascii(char)[1:-1]
        for char in path.decode("utf-8", errors="surrogateescape")
    )


def scan_merge(git, target, merge):
    _, *parents = git("rev-list", "--parents", "-1", merge, "--").stdout.decode("ascii").split()
    if len(parents) < 2:
        raise ScanError("not-merge")
    if target is None:
        return []  # The target already has its own finding.
    if git("merge-base", "--is-ancestor", merge, target, allowed=(0, 1)).returncode:
        raise ScanError("not-ancestor")

    first_parent = parents[0]
    introduced = set(git("rev-list", f"{first_parent}..{merge}", "--").stdout.splitlines())
    history = git("log", "--no-notes", "--no-decorate", "--no-color", "--no-show-signature",
                  "--encoding=none", "--format=%H%x00%B", "-z", f"{merge}..{target}", "--").stdout
    fields = history.split(b"\0")[:-1]
    findings = []
    for commit, message in zip(fields[::2], fields[1::2], strict=True):
        if any(sha.lower() in introduced for sha in REVERT.findall(message)):
            findings.append(f"reverted {merge[:12]} by {commit[:12].decode('ascii')}")

    before, merged, selected = (tree(git, sha) for sha in (first_parent, merge, target))
    for path in sorted(before.keys() | merged.keys()):
        old, new = before.get(path), merged.get(path)
        # A submodule entry isn't a blob and must not be confused with absence.
        blob_path = old if old is not None else new
        if old == selected.get(path) and old != new and blob_path and blob_path[0] == b"blob":
            findings.append(f"path-restored {merge[:12]} {printable_path(path)}")
    return findings


def scan(repo, target, merges):
    values = [target, *merges]
    malformed = [len(value) not in (40, 64) or not HEX.fullmatch(value) for value in values]
    git = local_git(repo)
    try:
        if not repo:
            raise ScanError("unknown-commit")
        fmt, shallow = git("rev-parse", "--show-object-format", "--is-shallow-repository").stdout.split()
        width = {b"sha1": 40, b"sha256": 64}[fmt]
        # Older Git can implicitly fetch missing objects from a promisor remote.
        promisor = git("config", "--get-regexp", r"^(extensions\.partialclone|remote\..*\.promisor)$",
                       allowed=(0, 1)).returncode == 0
        if shallow != b"false" or promisor:
            raise ScanError("unknown-commit")
    except (OSError, ValueError, KeyError):
        yield from ("FAIL bad-sha" for bad in malformed if bad)
        yield "FAIL unknown-commit"
        return

    selected = None
    try:
        selected = commit_sha(git, target, width)
    except ScanError as error:
        yield f"FAIL {error}"
    except OSError:
        yield "FAIL unknown-commit"
    for value in merges:
        try:
            merge = commit_sha(git, value, width)
            findings = scan_merge(git, selected, merge)
        except ScanError as error:
            yield f"FAIL {error}"
        except (OSError, ValueError):
            yield "FAIL unknown-commit"
        else:
            if findings:
                yield from (f"FAIL {reason}" for reason in findings)
            elif selected is not None:
                yield f"OK {merge[:12]}"


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Keep argparse's usage and exit status without echoing unknown argv.
        super().error("invalid arguments")


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo", required=True, help="local checkout with full history")
    parser.add_argument("--target", required=True, help="full release commit SHA")
    parser.add_argument("--merge", action="append", required=True, help="full merge SHA (repeatable)")
    args = parser.parse_args(argv)
    passed = True
    for line in scan(args.repo, args.target, args.merge):
        print(line)
        passed &= not line.startswith("FAIL ")
    print(f"{'PASS' if passed else 'FAIL'} install_revert_scan")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
