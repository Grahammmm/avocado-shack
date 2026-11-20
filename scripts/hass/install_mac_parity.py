#!/usr/bin/env python3
"""Compare a supplied Mac forwarder copy with a selected Git commit, offline."""

import argparse
import errno
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


FORWARDER = "mac/hass_forwarder.py"


def release_digest(repo: Path, commit: str) -> str:
    if not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", commit):
        raise ValueError("--commit must be a full hexadecimal commit SHA")

    # Do not inherit Git overrides that could redirect object lookup to another
    # repo. Deny all transports even on Git versions that lazily fetch blobs.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_ALLOW_PROTOCOL="", GIT_NO_LAZY_FETCH="1")

    def git(*args: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git", "--no-replace-objects", *args], cwd=repo, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except OSError:
            raise ValueError("cannot run Git in the supplied checkout") from None

    resolved = git("rev-parse", "--verify", f"{commit}^{{commit}}")
    if resolved.returncode or resolved.stdout.strip() != commit.lower().encode("ascii"):
        raise ValueError("selected SHA does not identify a locally available commit")
    blob = git("cat-file", "blob", f"{commit.lower()}:{FORWARDER}")
    if blob.returncode:
        raise ValueError(f"cannot read the {FORWARDER} blob from the selected commit")
    return hashlib.sha256(blob.stdout).hexdigest()


def deployed_digest(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("deployed copy is a symlink")
        if not stat.S_ISREG(mode):
            raise ValueError("deployed copy is not a regular file")
        # Also guard the open against a leaf replacement after lstat. NONBLOCK
        # prevents a replacement FIFO from hanging before the descriptor check.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as copy:
            if not stat.S_ISREG(os.fstat(copy.fileno()).st_mode):
                raise ValueError("deployed copy is not a regular file")
            digest = hashlib.sha256()
            for chunk in iter(lambda: copy.read(65536), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except FileNotFoundError:
        raise ValueError("deployed copy is missing") from None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("deployed copy is a symlink or has a symlink loop") from None
        raise ValueError("cannot read the deployed copy") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--commit", required=True, help="full SHA of the selected release commit")
    parser.add_argument("--deployed", required=True, type=Path, help="path to a supplied local file")
    args = parser.parse_args()

    try:
        release = release_digest(args.repo, args.commit)
        deployed = deployed_digest(args.deployed)
    except ValueError as exc:
        print(f"Byte parity not checked: {exc}.", file=sys.stderr)
        return 2

    matches = release == deployed
    verdict = "match" if matches else "mismatch"
    print(f"Byte parity {verdict}: SHA-256 release={release[:12]} deployed={deployed[:12]}.")
    print("File bytes only; process status and delivery were not checked.")
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
