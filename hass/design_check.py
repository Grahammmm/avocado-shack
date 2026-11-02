"""H24 design-change scope checker (read-only).

    python3 hass/design_check.py --base REF --head REF

Prints one JSON line {"result": "ok"|"outside", "changed": n, "outside": [...]}
naming each change the head made since its merge base with --base (none when
--head is already merged into --base) that is not an isolated visual change: a path off the design
surface, a deletion, a symlink, submodule or non-plain (e.g. executable) file,
or a template changed without its generated page (or the reverse). Paths only,
never contents. Exit 0 ok,
1 outside, 2 usage (bad refs, or no common history). Read-only git in the current directory; nothing is written.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

DESIGN = ("hass/templates/index.html", "hass/templates/hike/index.html", "storefront-mockup/index.html",
          "storefront-mockup/hike/index.html", "storefront-mockup/style.css", "storefront-mockup/hiking.css",
          "storefront-mockup/trail-explorer.css")
PAIRS = (("hass/templates/index.html", "storefront-mockup/index.html"),
         ("hass/templates/hike/index.html", "storefront-mockup/hike/index.html"))
PLAIN_MODE = "100644"  # anything else (symlink, submodule, executable) is outside


class Usage(Exception):
    """Bad arguments or refs (exit 2)."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise Usage(message)


def git(*args: str, empty_ok: bool = False) -> str:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    out = subprocess.run(["git", "--literal-pathspecs", *args], capture_output=True, env=env)
    if out.returncode and not (empty_ok and out.returncode == 1 and not out.stdout.strip()):
        raise Usage(f"git {args[0]} failed")
    return out.stdout.decode("utf-8", "surrogateescape")


def commit(ref: str) -> str:
    if not ref or ref.startswith("-"):
        raise Usage(f"bad ref {ref!r}")
    return git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()


def merge_base(base: str, head: str) -> str:
    found = git("merge-base", base, head, empty_ok=True).strip()  # exit 1, no output: unrelated
    if not found:
        raise Usage("no common history between --base and --head")
    return found


def check(base: str, head: str) -> tuple[int, list[str]]:
    parts = git("diff", "--name-status", "-z", "--no-renames", merge_base(base, head), head, "--").split("\0")[:-1]
    changes = list(zip(parts[0::2], parts[1::2]))  # (status, path)
    modes = {e.split("\t", 1)[1]: e.split(" ", 1)[0]
             for e in git("ls-tree", "-r", "-z", "--full-tree", head).split("\0") if "\t" in e}
    changed = {p for _, p in changes}
    outside = {f"{s} {p}" for s, p in changes if p not in DESIGN or s == "D" or modes.get(p) != PLAIN_MODE}
    for x, y in PAIRS + tuple(pair[::-1] for pair in PAIRS):
        if x in changed and y not in changed:
            outside.add(f"unpaired {x}")
    return len(changes), sorted(outside)


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description="List changes outside the design surface.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    try:
        args = parser.parse_args(argv)
        changed, outside = check(commit(args.base), commit(args.head))
    except Usage as exc:
        print(json.dumps({"result": "usage"}))
        print(f"design_check: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"result": "outside" if outside else "ok", "changed": changed, "outside": outside}))
    return 1 if outside else 0


if __name__ == "__main__":
    sys.exit(main())
