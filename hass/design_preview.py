"""H24 design visual check (AV1104-10): private base/head page captures for a design change.

    python3 -B hass/design_preview.py --base REF --head REF --out DIR

Runs the design_check scope gate first (outside: exit 1, nothing read for capture, no folder made, no browser). Then
lays each ref's seven design files (read with ``git show`` from the ref's commit, never the worktree) over the current
worktree's other site files and captures the home page and /hike at phone and desktop width with the H06 Previewer:
base-home, base-hike, head-home, head-hike, as DIR/<side>-<page>-phone.png and <side>-<page>-phone-desktop.png (0600).
The common background (content, community.js, assets) is the current worktree, not either ref: this compares design
surfaces, not whole historic sites. Prints ONE JSON line {result, base, head, changed, outside, captures}. Exit 0 ok,
1 outside or preview-failed, 2 usage (bad refs, unsafe design member or output folder). Git is read-only; nothing is
sent, merged or published. A page check passing is not design approval: the operator looks at the PNGs.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hass import design_check  # noqa: E402
from hass.design_check import DESIGN, PLAIN_MODE, Parser, Usage  # noqa: E402
from hass.preview import Previewer  # noqa: E402

PAGES = ("home", "hike")
REQUIRED = ("storefront-mockup/index.html", "storefront-mockup/hike/index.html")
SITE_PREFIX = "storefront-mockup/"  # templates (hass/templates) are validated, never served or overlaid
NAME_OK = re.compile(r"[A-Za-z0-9:]+")
REQUIRED_CHECKS = frozenset(n for b in ("pageLoaded", "noHorizontalOverflow", "noPageErrors", "noPosts") for n in (b, "desktop:" + b))


def _read_blob(sha: str, path: str, top: str) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    out = subprocess.run(["git", "--literal-pathspecs", "show", f"{sha}:{path}"], capture_output=True, env=env, cwd=top)
    if out.returncode:
        raise Usage("git show failed")
    return out.stdout


def design_files(sha: str, top: str) -> dict:
    """path -> bytes of every design member present at ``sha``; each must be a plain 100644 blob."""
    listed = design_check.git("ls-tree", "-z", "--full-tree", sha, "--", *DESIGN, cwd=top)
    found = {}
    for entry in filter(None, listed.split("\0")):
        meta, _, path = entry.partition("\t")
        mode, kind = meta.split(" ")[:2]
        if path not in DESIGN or kind != "blob" or mode != PLAIN_MODE:
            raise Usage(f"unsafe design member {path}")
        found[path] = _read_blob(sha, path, top)
    return found


def side_overlays(base_sha: str, head_sha: str, top: str) -> dict:
    """{'base': files, 'head': files} of storefront-mockup bytes; refuses a member one side lacks (an overlay cannot
    delete a copied file) or a missing home/hike page."""
    sides = {"base": design_files(base_sha, top), "head": design_files(head_sha, top)}
    for path in DESIGN:
        present = [path in sides[name] for name in sides]
        if any(present) and not all(present):
            raise Usage(f"design member {path} exists in only one ref")
        if not any(present) and os.path.lexists(os.path.join(top, path)):
            raise Usage(f"design member {path} missing from both refs but present in the worktree")
        if not any(present) and path in REQUIRED:
            raise Usage(f"required page {path} missing")
    return {name: {p: b for p, b in files.items() if p.startswith(SITE_PREFIX)} for name, files in sides.items()}


def _git_dirs(top: str) -> list[Path]:
    dirs = design_check.git("rev-parse", "--git-dir", "--git-common-dir", cwd=top).split("\n")
    return [Path(top, d).resolve() for d in dirs if d]


def prepare_out(out: str, top: str) -> Path:
    """The private output folder: outside the repository and its Git folders, no link anywhere on the way, new (0700)
    or an existing real empty 0700 folder. Raises Usage; a filesystem error becomes a fixed path-free Usage."""
    try:
        return _prepare_out(out, top)
    except OSError:
        raise Usage("--out is not usable") from None


def _walk_out(out: str) -> Path:
    """Normalized absolute --out, after lstat of every component of the ORIGINAL spelling (cwd ancestry included), so a
    link hidden by ``link/..`` is refused, not cancelled. A missing last component is allowed; a missing or non-folder
    intermediate one is not. Static check only."""
    parts = Path(out).parts
    if not os.path.isabs(out):
        parts = Path(os.getcwd()).parts + parts
    cur, last = Path(parts[0]), len(parts) - 1
    for index, name in enumerate(parts[1:], 1):
        if name == "..":
            cur = cur.parent
            continue
        cur = cur / name
        try:
            info = os.lstat(cur)
        except FileNotFoundError:
            if index == last:
                break
            raise Usage("--out is not usable") from None
        if stat.S_ISLNK(info.st_mode):
            raise Usage("--out has a symlink on its path")
        if index != last and not stat.S_ISDIR(info.st_mode):
            raise Usage("--out is not usable")
    return cur


def _prepare_out(out: str, top: str) -> Path:
    if not out or "\0" in out:
        raise Usage("bad --out")
    path = _walk_out(out)
    resolved = path.resolve()
    for guarded in [Path(top).resolve(), *_git_dirs(top)]:
        if resolved == guarded or guarded in resolved.parents:
            raise Usage("--out is inside the repository")
    if os.path.lexists(path):
        info = os.lstat(path)
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
            raise Usage("--out exists and is not a private real folder")
        if any(path.iterdir()):
            raise Usage("--out is not empty")
    else:
        if not path.parent.is_dir():
            raise Usage("--out parent folder does not exist")
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
    return path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _private_png(value, expected: Path | None) -> str | None:
    """The expected path when value names it exactly and it is a regular 0600 file; else None."""
    if expected is None or not isinstance(value, str) or value != str(expected):
        return None
    try:
        info = os.lstat(value)
        if not (stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600):
            return None
        fd = os.open(value, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            opened = os.fstat(fd)
            if not (stat.S_ISREG(opened.st_mode) and stat.S_IMODE(opened.st_mode) == 0o600):
                return None
            # Format identification only: the eight-byte signature, not CRC, size or pixel validity.
            return value if os.read(fd, 8) == PNG_SIGNATURE else None
        finally:
            os.close(fd)
    except OSError:
        return None


def _entry(side: str, page: str, result: dict, expected: Path | None = None) -> dict:
    """run() always passes the planned phone path; without it only the result's own png names the pair."""
    if expected is None:
        own = result.get("png")
        expected = Path(own) if isinstance(own, str) and own and "\0" not in own else None
    raw = result.get("checks")
    raw = raw if isinstance(raw, dict) else {}
    checks = {k: v for k, v in raw.items() if isinstance(k, str) and type(v) is bool}
    desktop_path = expected and expected.with_name(expected.stem + "-desktop.png")
    png, desktop = _private_png(result.get("png"), expected), _private_png(result.get("desktopPng"), desktop_path)
    failed = sorted(k for k, v in checks.items() if not v)
    if not checks or len(checks) != len(raw):
        error = "capture failed" if png is None else "bad checks"
    elif failed:
        error = "check failed: " + ", ".join(k for k in failed if NAME_OK.fullmatch(k))
    elif png is None:
        error = "missing png"
    elif desktop is None:
        error = "missing desktop png"
    elif not REQUIRED_CHECKS <= checks.keys():
        error = "bad checks"
    elif result.get("ok") is not True:
        error = "capture failed"
    else:
        error = None
    return {"side": side, "page": page, "png": png, "desktopPng": desktop, "checks": checks, "error": error}


def run(base: str, head: str, out: str, previewer=None) -> tuple[int, dict]:
    top = design_check.toplevel()
    base_sha, head_sha = design_check.commit(base, top), design_check.commit(head, top)
    if not base_sha or not head_sha:
        raise Usage("unknown ref")
    changed, outside = design_check.check(base_sha, head_sha, top)
    doc = {"result": "outside" if outside else "ok", "base": base_sha, "head": head_sha, "changed": changed,
           "outside": outside, "captures": []}
    if outside:
        return 1, {**doc, "result": "outside"}
    overlays = side_overlays(base_sha, head_sha, top)
    folder = prepare_out(out, top)
    previewer = previewer or Previewer(top)
    for side in ("base", "head"):
        for page in PAGES:
            expected = folder / f"{side}-{page}-phone.png"
            result = previewer.capture(overlays[side], {"kind": "design", "page": page}, expected)
            doc["captures"].append(_entry(side, page, result if isinstance(result, dict) else {}, expected))
    good = all(c["error"] is None for c in doc["captures"])
    doc["result"] = "ok" if good else "preview-failed"
    return (0 if good else 1), doc


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description="Capture base and head design pages privately.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--out", required=True)
    try:
        args = parser.parse_args(argv)
        code, doc = run(args.base, args.head, args.out)
    except Usage as exc:
        print(json.dumps({"result": "usage"}))
        print(f"design_preview: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(doc))
    return code


if __name__ == "__main__":
    sys.exit(main())
