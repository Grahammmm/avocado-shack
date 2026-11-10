"""Catch-all backlog (SKILLS-FW-1): the 'I can't do that yet' store and the skills that use it.

One row per request Hass could not do, in a ``backlog`` table inside the private conversation.sqlite3 (so the state
backup already covers it). The owner's text is private: capped at MAX_TEXT characters, never written to git, a report,
a log or the interpreter, and never leaves the box. Rows are removed after RETENTION_DAYS (D7), or one by one by
``forget``. Nothing here changes site content, so there is no approval and no editor call.

    python3 hass/skills/backlog.py list  --state DIR [--text] [--all]   (--text prints the stored message: operator only)
    python3 hass/skills/backlog.py purge --state DIR                    (drops rows older than RETENTION_DAYS)
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import editor as editor_mod  # noqa: E402
from hass import memory as memory_mod  # noqa: E402
from hass.skills.model import Slot, Skill, Trigger, Undo  # noqa: E402

REASONS = ("unknown-skill", "policy", "unsupported-page", "stuck", "price", "other")
STATES = ("open", "closed")
MAX_TEXT = 4000  # the owner-message cap (conversation.MAX_OWNER_TEXT; a test pins the two together)
MAX_SUMMARY = 160
RETENTION_DAYS = 90  # D7
LIST_MAX = 10  # the owner's 'backlog' command shows the last ten
HIDDEN = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b\u200e\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")

TABLE = """CREATE TABLE IF NOT EXISTS backlog(id INTEGER PRIMARY KEY AUTOINCREMENT, received_at TEXT NOT NULL,
  reason TEXT NOT NULL CHECK(reason IN ('unknown-skill','policy','unsupported-page','stuck','price','other')),
  summary TEXT NOT NULL, text TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open' CHECK(state IN ('open','closed')))"""

CANT_DO = "I can't do that yet. I wrote it down so it can be built. Nothing on the site changed."
NO_FAQ = ("The site has no FAQ page, and adding a page is a design change I can't make by message yet. "
          "I wrote it down so it can be built. Nothing on the site changed.")
EMPTY_LIST = "Nothing is written down right now."
FORGOTTEN = "Done. I took that one off the list."
NOT_THERE = "I don't have that one on the list."


def _clean(text, cap) -> str:
    return HIDDEN.sub(" ", str(text or ""))[:cap]


def _summary(summary, text) -> str:
    """One line, at most MAX_SUMMARY characters: the given summary, else the start of the owner's message."""
    return " ".join(_clean(summary or text, MAX_SUMMARY * 2).split())[:MAX_SUMMARY] or "(no text)"


class Backlog:
    def __init__(self, db, clock):
        """``db`` is an open sqlite3 connection (the Conversation's, or open()'s); ``clock()`` returns an aware datetime."""
        self.db, self.clock = db, clock
        db.execute("PRAGMA secure_delete = ON")  # forgotten text is zeroed in the file, not left in free space
        db.execute(TABLE)

    @classmethod
    def open(cls, state_dir, clock=lambda: datetime.now(timezone.utc)):
        sdir = editor_mod.open_state(state_dir)
        db = sqlite3.connect(memory_mod.private_db(sdir, "conversation.sqlite3"), isolation_level=None)
        db.row_factory = sqlite3.Row
        return cls(db, clock)

    def close(self) -> None:
        self.db.close()

    def record(self, reason, summary="", text="") -> int:
        """Write one open row and return its number. Text over MAX_TEXT is cut, never refused: the request is still logged."""
        if reason not in REASONS:
            raise ValueError("unknown reason")
        row = (self.clock().isoformat(), reason, _summary(summary, text), _clean(text, MAX_TEXT))
        cur = self.db.execute("INSERT INTO backlog(received_at, reason, summary, text) VALUES (?,?,?,?)", row)
        return cur.lastrowid

    def rows(self, limit=LIST_MAX, *, state: str | None = "open", text=False) -> list:
        """Newest first. Summaries only unless ``text`` (operator-only)."""
        cols = "id, received_at, reason, summary, state" + (", text" if text else "")
        where, args = ("WHERE state = ?", (state,)) if state else ("", ())
        cur = self.db.execute(f"SELECT {cols} FROM backlog {where} ORDER BY id DESC LIMIT ?", (*args, limit))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def forget(self, number) -> bool:
        """Remove one row by its number (numbers are never reused, so a stale forget cannot hit a newer row). True when a row was removed."""
        if isinstance(number, bool) or not isinstance(number, int):
            return False
        return self.db.execute("DELETE FROM backlog WHERE id = ?", (number,)).rowcount == 1

    def purge(self, days=RETENTION_DAYS) -> int:
        """Remove rows received more than ``days`` days ago (D7). Returns how many."""
        now = self.clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("backlog clock must be timezone-aware")
        cutoff = now.astimezone(timezone.utc) - timedelta(days=days)  # elapsed days, not local calendar days
        removed = 0
        for row_id, stamp in self.db.execute("SELECT id, received_at FROM backlog").fetchall():
            # A stored stamp that does not parse, or has no offset, has unknown age: keep it rather than guess a zone.
            try:
                at = datetime.fromisoformat(stamp)
            except (TypeError, ValueError):
                continue
            if at.utcoffset() is None or at.astimezone(timezone.utc) >= cutoff:
                continue
            removed += self.db.execute("DELETE FROM backlog WHERE id = ? AND received_at = ?", (row_id, stamp)).rowcount
        return removed

    def owner_list(self) -> str:
        """The 'backlog' command reply: the last ten, each as 'number. day - what was asked'. No stored text."""
        rows = self.rows()
        if not rows:
            return EMPTY_LIST
        lines = [f"{r['id']}. {r['received_at'][:10]} - {r['summary']}" for r in rows]
        return "Written down so far, newest first:\n" + "\n".join(lines) + "\nSay 'forget backlog.<number>' to remove one."


def _plan(slots, ctx) -> list:
    return []  # these skills change no content; the caller records the backlog row and sends the fixed reply


_CASES = "hass/tests/fixtures/skills/catch-all/{}.jsonl"

BACKLOG_LOG = Skill(
    name="backlog.log", label="write it down for later",
    summary="Nothing fits: write the request down, say I can't do that yet, change nothing.",
    triggers=(
        Trigger("can you order more eggs from the farm"),
        Trigger("text the hiking club about Saturday"),
        Trigger("post to faceboook", "typo"),
        Trigger("do the thing we talked about", "vague"),
        Trigger("add a gift card option"),
        Trigger("change the logo and add a blog", "multi"),
        Trigger("what's our POS balance"),
        Trigger("make the site faster"),
        Trigger("forget everything"),
        Trigger("delete the backlog"),
    ),
    slots=(Slot("summary", "text", True, ask="What did you want me to do?"),
           Slot("reason", "enum", False, default="other")),
    rules=("backlog-text-cap", "backlog-no-bulk-delete"),
    plan=_plan, edits=(), side_effects=("backlog-row",), preview="none", approval="none", live_class="read-only",
    undo=Undo("forget", "none"),
    refuse=(("the owner asks to delete the whole list", "I can only take one off at a time. Say 'forget backlog.' and its number."),),
    cases=_CASES.format("backlog.log"), version=1)

PAGE_FAQ = Skill(
    name="page.faq", label="add a questions page",
    summary="The site has no FAQ page and a new page is a design change: say so and write it down.",
    triggers=(
        Trigger("add an FAQ"),
        Trigger("put a page for common questions"),
        Trigger("add a faq sectoin to the home page", "typo"),
        Trigger("people keep asking about parking, put it somewhere", "vague"),
        Trigger("FAQ: do you deliver? no"),
        Trigger("add FAQ and an About page and a gift page", "multi"),
        Trigger("make an about page"),
        Trigger("where do I put our return policy"),
        Trigger("add a question to the FAQ about allergens"),
        Trigger("new page for the hiking club rules"),
    ),
    slots=(), rules=("no-new-page",), plan=_plan, edits=(), side_effects=("backlog-row",), preview="none",
    approval="none", live_class="read-only", undo=Undo("forget", "none"),
    refuse=(("a new page is asked for", NO_FAQ),), cases=_CASES.format("page.faq"), version=1)

SKILLS = (BACKLOG_LOG, PAGE_FAQ)


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="backlog.py", description="Operator view of the 'can't do that yet' backlog.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("list", "purge"):
        p = sub.add_parser(name)
        p.add_argument("--state", required=True)
    sub.choices["list"].add_argument("--text", action="store_true", help="print the stored message (operator only)")
    sub.choices["list"].add_argument("--all", action="store_true", help="include closed rows")
    args = parser.parse_args(argv)
    try:
        store = Backlog.open(args.state)
    except editor_mod.UnsafeState as exc:
        print(f"backlog: unsafe: {exc}", file=sys.stderr)
        return 2
    try:
        if args.cmd == "purge":
            print(f"removed {store.purge()} rows older than {RETENTION_DAYS} days")
            return 0
        for r in store.rows(1000, state=None if args.all else "open", text=args.text):
            print(f"{r['id']}\t{r['received_at'][:10]}\t{r['reason']}\t{r['state']}\t{r['summary']}")
            if args.text:
                print("  " + r["text"].replace("\n", "\n  "))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
