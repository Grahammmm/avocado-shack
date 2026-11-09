"""Scratch-only rehearsal (HASS-OWNERS-2, STORE-TEST-1 P-0 method): two synthetic owners, each in their own one-to-one chat.

A temporary writer repo + state (hass.tests.test_editor.WriterRepo), the real Conversation, the A2 fixture ops plus the real
history.revert, an exact-text fixture interpreter (no model) and a fake previewer (no browser). No live state, no network, no phone,
nothing sent. Every message and every reply is printed with the chat it travelled in. Each step names what it expects; the script
exits 1 if any step differs.  Usage: python3 -B reports/hass/rehearse_owners_two.py <checkout>
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHECKOUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]).resolve()
sys.path.insert(0, str(CHECKOUT))
import os  # noqa: E402

os.environ.setdefault("HASS_VOICE_STRICT", "1")  # a reply that breaks a voice rule raises, as in CI

from hass import conversation as conv, editor  # noqa: E402
from hass.fixture_chat import FixtureAdapter  # noqa: E402
from hass.ops import load_registry  # noqa: E402
from hass.tests import fixture_ops  # noqa: E402
from hass.tests.test_conversation import _ops  # noqa: E402
from hass.tests.test_editor import DESC, HOURS, NEW_HOURS, WriterRepo  # noqa: E402
from hass.tests.test_undo import FakePreviewer  # noqa: E402

MIKE, GEE = "mike@example.invalid", "g@example.invalid"  # synthetic: no real number or address
MCHAT, GCHAT = f"iMessage;-;{MIKE}", f"iMessage;-;{GEE}"
NAME = {MCHAT: "Mike", GCHAT: "G"}
repo = WriterRepo()
settings = {"ownerSenders": [MIKE, GEE], "ownerChat": MCHAT, "ownerChats": [MCHAT, GCHAT], "ownerNames": NAME, "approvalTtlSeconds": 600}
cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
editor._write_json(repo.state / "config.json", {**cfg, "settings": settings})
interp = conv.FixtureInterpreter({"set the hours": _ops((HOURS, {"hours": NEW_HOURS})),
                                  "better description": _ops((DESC, {"id": "photo-product-001", "description": "Ripe and creamy."}))})
ed = conv.Editor(repo.state, {**fixture_ops.registry(), "history.revert": load_registry()["history.revert"]})
now = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)  # 9 am Pacific
c = conv.Conversation(str(repo.state), ed, interp, lambda: now, FakePreviewer())
out, n, bad = FixtureAdapter(), 0, []


def say(who, text, expect, *, chat=None, sender=None, reply_in=None, has=(), lacks=(), pictures=None):
    """Send `text` as owner `who` (Mike or G) in their own chat, or as `sender` in `chat`; check the disposition and the replies."""
    global n
    n += 1
    chat, sender = chat or (MCHAT if who == "Mike" else GCHAT), sender or (MIKE if who == "Mike" else GEE)
    got = c.handle(conv.Inbound(f"p{n}", chat, sender, text, False, "new", now.isoformat()))
    rows = [(r["chat"], r["text"], json.loads(r["attachments"])) for r in c.outbox.unsent()]
    c.flush(out)
    print(f"\n> {who:5s} [{NAME[chat]}'s chat] {text!r}  ->  {got}")
    for rchat, rtext, pics in rows:
        print(f"    reply to {NAME.get(rchat, rchat)}'s chat{' + ' + str(len(pics)) + ' picture' if pics else ''}: " + rtext.replace("\n", "\n        "))
    if not rows: print("    (no reply)")
    problems = []
    if got != expect: problems.append(f"disposition {got!r}, expected {expect!r}")
    if reply_in is not None and any(r[0] != reply_in for r in rows): problems.append(f"a reply went to the wrong chat (expected {NAME.get(reply_in)}'s)")
    if reply_in is not None and not rows: problems.append("no reply")
    for word in has:
        if not any(word in r[1] for r in rows): problems.append(f"no reply says {word!r}")
    for word in lacks:
        if any(word in r[1] for r in rows): problems.append(f"a reply says {word!r}")
    if pictures is not None and any(bool(r[2]) != pictures for r in rows if r[0] == reply_in) : problems.append(f"pictures expected {pictures}")
    if problems:
        bad.append((text, problems))
        print("    MISMATCH: " + "; ".join(problems))
    return rows


def last_code(): return [dict(r) for r in c.db.execute("SELECT * FROM drafts ORDER BY row_id")][-1]["code"]


print("rehearsal: two synthetic owners, checkout", CHECKOUT.name, "- owner chats:", ", ".join(NAME.values()))
say("Mike", "status", "status", reply_in=MCHAT)
say("G", "status", "status", reply_in=GCHAT)
say("Mike", "set the hours", "proposed", reply_in=MCHAT, has=("yes",), pictures=True)
mcode = last_code()
say("G", "set the hours", "writer-busy", reply_in=GCHAT, has=("Mike has a change waiting",))
say("G", f"yes {mcode}", "no-target", reply_in=GCHAT, has=("belongs to Mike",), lacks=("opening hours",))
say("G", f"no {mcode}", "no-target", reply_in=GCHAT, has=("belongs to Mike",))
say("G", "yes", "no-target", reply_in=GCHAT)
say("G", "set the hours", "ignored", chat=MCHAT, sender=GEE)  # G's number typed into Mike's chat
say("Mike", "set the hours", "ignored", chat=GCHAT, sender=MIKE)  # Mike's number typed into G's chat
say("Mike", f"yes {mcode}", "approved", reply_in=MCHAT)
say("G", "better description", "proposed", reply_in=GCHAT, has=("yes",), pictures=True)
gcode = last_code()
say("Mike", f"yes {gcode}", "no-target", reply_in=MCHAT, has=("belongs to G",))
say("Mike", "undo", "writer-busy", reply_in=MCHAT, has=("G has a change waiting",))  # one writer: G's draft is waiting
say("G", "yes", "approved", reply_in=GCHAT)
say("Mike", "undo", "undo-other", reply_in=MCHAT, has=("G's change", "I haven't undone anything"), lacks=("To undo",))  # the site's last change is G's
say("Mike", "history", "history", reply_in=MCHAT, has=("G's change,", "Your change,"))
say("G", "status", "status", reply_in=GCHAT, has=("Last change",))
say("G", "undo", "proposed", reply_in=GCHAT, has=("To undo that",))  # G's own last change
say("G", "no", "rejected", reply_in=GCHAT)
say("Mike", f"undo {mcode}", "proposed", reply_in=MCHAT, has=("To undo that",))  # Mike's own older change, by its code
say("Mike", "no", "rejected", reply_in=MCHAT)
say("G", f"undo {mcode}", "proposed", reply_in=GCHAT, has=("To undo Mike's change",))  # another owner's work, only by its code, still needs G's own yes
say("Mike", f"yes {last_code()}", "no-target", reply_in=MCHAT, has=("belongs to G",))
say("G", "no", "rejected", reply_in=GCHAT)
print("\nrows out of line:", "none" if not bad else len(bad))
sys.exit(1 if bad else 0)
