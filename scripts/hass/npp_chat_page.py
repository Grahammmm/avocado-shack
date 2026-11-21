#!/usr/bin/env python3
"""Render a Hass JSONL export and an attachment copy as a private offline page."""

import argparse
import base64
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


SHA = re.compile(r"[0-9a-f]{64}")
YES = re.compile(r"\byes\s+[0-9a-f]{4,12}-[1-9][0-9]{0,8}\b", re.I | re.ASCII)
TEXT_FIELDS = ("utc", "chat", "sender", "direction", "kind", "text")
# Transcript export primary key and NOT NULL columns:
# (id, utc, chat, sender, direction, kind, text, attachments, disposition)
REQUIRED_FIELDS = ("id", *TEXT_FIELDS, "attachments", "disposition")
HEAD = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>Private Hass conversation</title>
<style>
body { margin: 1rem auto; padding: 0 .75rem; max-width: 45rem;
       font: 1rem/1.5 system-ui, sans-serif; background: #f5f6f7; color: #18222c; }
h1 { font-size: 1.35rem; }
.bubble { box-sizing: border-box; max-width: 88%; width: fit-content;
          margin: .65rem 0; padding: .65rem .85rem; border-radius: .9rem;
          overflow-wrap: anywhere; }
.in { margin-right: auto; background: #fff; }
.out { margin-left: auto; background: #dceeff; }
.meta, .missing { font-size: .85rem; color: #415264; }
.message { white-space: pre-wrap; }
.marker { font-weight: bold; border-left: .2rem solid #345675; padding-left: .4rem; }
img { display: block; max-width: 100%; height: auto; margin-top: .4rem; }
</style>
<header><h1>Private Hass conversation</h1>
"""


class PageError(Exception):
    """An operator-safe diagnostic; never include input data or paths."""


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can echo an unrecognized private argument.
        self.print_usage(sys.stderr)
        self.exit(2, "npp_chat_page: error: invalid arguments\n")


def read_events(path, chat):
    events = []
    try:
        with path.open(encoding="utf-8") as source:
            for number, line in enumerate(source, start=1):
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise PageError("invalid event")
                for field in REQUIRED_FIELDS:
                    if field not in event:
                        raise PageError(f"missing-field {field} line {number}")
                if (type(event["id"]) is not int
                        or any(not isinstance(event[key], str) for key in TEXT_FIELDS)
                        or event["direction"] not in ("in", "out")
                        or not isinstance(event["attachments"], list)
                        or any(not isinstance(sha, str) or not SHA.fullmatch(sha)
                               for sha in event["attachments"])):
                    raise PageError("invalid event")
                if chat is None or event["chat"] == chat:
                    events.append(event)
    except ValueError:
        raise PageError("invalid export JSON") from None
    except OSError:
        raise PageError("export unavailable") from None
    return sorted(events, key=lambda event: event["id"])


def picture(sha, directory):
    for candidate in (directory / sha, directory / f"card-{sha}.png",
                      *sorted(directory.glob(f"{sha}.*"))):
        try:
            # The operator supplies copies, not symlinks back to the live store.
            if not stat.S_ISREG(candidate.lstat().st_mode):
                continue
            raw = candidate.read_bytes()
        except OSError:
            continue
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif raw.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        else:
            continue
        if hashlib.sha256(raw).hexdigest() == sha:
            return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    return None


def render(events, directory):
    body, pictures, missing = [], {}, set()
    messages_in = count = 0
    for event in events:
        inbound = event["direction"] == "in"
        messages_in += inbound
        sender, utc = escape(event["sender"]), escape(event["utc"])
        body.append(f'<article class="bubble {event["direction"]}">'
                    f'<div class="meta">{sender} · {utc}</div>')
        for line in event["text"].split("\n"):
            marker = ""
            if not inbound:
                if line.startswith("Posted:"):
                    marker = " marker posted"
                elif YES.search(line):
                    marker = " marker approval"
            body.append(f'<div class="message{marker}">{escape(line) or "<br>"}</div>')
        for sha in event["attachments"]:
            if sha not in pictures:
                pictures[sha] = picture(sha, directory)
            uri = pictures[sha]
            if uri is None:
                missing.add(sha)
                body.append(f'<div class="missing">picture {sha[:8]} not in copy</div>')
            else:
                count += 1
                body.append(f'<img src="{uri}" alt="Chat picture">')
        body.append("</article>")
    counts = (f"<p>{messages_in} messages in · {len(events) - messages_in} messages out"
              f" · {count} pictures</p></header>\n<main>")
    return "\n".join([HEAD, counts, *body, "</main></html>\n"]), sorted(missing)


def output_path(path, source, directory, force):
    parent = path.parent.resolve()
    for start in (path.absolute().parent, parent):
        for ancestor in (start, *start.parents):
            if os.path.lexists(ancestor / ".git"):
                raise PageError("output inside git worktree")
    destination = parent / path.name
    input_roots = (source.parent.resolve(), directory)
    if (destination == source.resolve()
            or any(os.path.commonpath((destination, root)) == os.fspath(root) for root in input_roots)):
        raise PageError("out-inside-input")
    if os.path.lexists(destination):
        if not force:
            raise PageError("output exists (use --force)")
        if not stat.S_ISREG(destination.lstat().st_mode):
            raise PageError("output must be a regular file")
    return destination


def write_page(path, html, force):
    # Prepare the complete page privately, then install it without following or
    # truncating an existing inode. link() also guards against a late collision.
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".npp-chat-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(html)
        if force:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = PrivateParser(prog="npp_chat_page", description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--attachments", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chat", help="only show events from this chat ID")
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    args = parser.parse_args(argv)
    try:
        events = read_events(args.export, args.chat)
        directory = args.attachments.resolve()
        if not directory.is_dir():
            raise PageError("attachment copy unavailable")
        destination = output_path(args.out, args.export, directory, args.force)
        page, missing = render(events, directory)
        write_page(destination, page, args.force)
    except PageError as error:
        print(f"FAIL {error}")
    except (OSError, RuntimeError, ValueError):
        print("FAIL could not create page")
    else:
        for sha in missing:
            print(f"NOTE missing-attachment {sha[:8]}")
        print(f"PASS npp_chat_page {len(events)} events")
        return 0
    print("FAIL npp_chat_page")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
