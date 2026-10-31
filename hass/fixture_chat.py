"""Fixture conversation adapter (H05). A fixture is not iMessage: messages come from a JSONL file and sends are
only recorded in memory.

    python3 hass/fixture_chat.py --state DIR --fixture FILE --interpreter FILE [--preview] [--queue START_AT]

Runs every fixture message through a Conversation (production op registry, FixtureInterpreter from the JSON
mapping FILE), flushes the outbox into memory and prints it as JSON lines. It sends nothing anywhere.
--preview adds the writer worktree's Previewer (private proposal/result screenshots, verify-before-reply;
PLAYWRIGHT_MODULE and CHROMIUM_PATH are read from the environment).
--queue START_AT stores every message in <state>/inbox.sqlite3 first, then drains it once (H16): messages before the
start point and repeats never become commands; stderr gets one counts-only summary line.
Exit codes: 0 done, 2 unsafe state dir, missing settings or unreadable input.
"""
import argparse, json, sys  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.conversation import ConfigError, Conversation, Editor, FixtureInterpreter, Inbound  # noqa: E402
from hass.editor import UnsafeState  # noqa: E402
from hass import editor as editor_mod  # noqa: E402
from hass.inbox import Inbox  # noqa: E402
from hass.preview import Previewer  # noqa: E402


def _row(n, line) -> Inbound:  # every check names line n and the field, never the value
    def bad(what): raise ValueError(f"fixture line {n}: {what}")
    try: r = json.loads(line)
    except ValueError: bad("not JSON")
    if not isinstance(r, dict): bad("row must be a JSON object")
    if type(r.get("id")) not in (int, str) or r.get("id") == "": bad("id must be a non-empty string or an integer")
    for field in ("chat", "sender", "text"):
        if not isinstance(r.get(field), str): bad(f"{field} must be a string")
    if not isinstance(r.get("fromMe", False), bool): bad("fromMe must be true or false")
    if not (isinstance(kind := r.get("kind", "new"), str) and kind): bad("kind must be a non-empty string")
    try: at = datetime.fromisoformat(r.get("at"))
    except (TypeError, ValueError): at = None
    if at is None or at.utcoffset() is None: bad("at must be an ISO time with a UTC offset")
    return Inbound(provider_id=str(r["id"]), chat=r["chat"], sender=r["sender"], text=r["text"],
                   from_me=r.get("fromMe", False), kind=kind, received_at=r["at"])


class FixtureAdapter:
    """Reads inbound JSONL (`id, chat, sender, text, fromMe, kind, at`); records sends; `fail_sends=N` raises N times."""

    def __init__(self, path=None, fail_sends=0):
        self.path, self.fail_sends, self.sent = path, fail_sends, []

    def inbound(self) -> list:
        lines = Path(self.path).read_text("utf-8").splitlines()
        return [_row(n, s) for n, s in enumerate(lines, 1) if s.strip()]  # n counts physical lines, blanks included

    def send(self, chat, text, attachments):
        if self.fail_sends > 0:
            self.fail_sends -= 1
            raise ConnectionError("fixture send failure")
        self.sent.append({"chat": chat, "text": text, "attachments": list(attachments)})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/fixture_chat.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("--state", "--fixture", "--interpreter"): parser.add_argument(name, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--queue", metavar="START_AT")
    args = parser.parse_args(argv)
    try:
        adapter = FixtureAdapter(args.fixture)
        interpreter = FixtureInterpreter(json.loads(Path(args.interpreter).read_text("utf-8")))
        editor = Editor(args.state)
        previewer = Previewer(editor_mod._load(args.state)[2]) if args.preview else None
        conversation = Conversation(args.state, editor, interpreter, lambda: datetime.now(timezone.utc), previewer)
        if args.queue is None:
            for message in adapter.inbound(): conversation.handle(message)
        else:
            inbox, counts = Inbox(args.state, start_at=args.queue), {"queued": 0, "duplicate": 0, "history": 0}
            try:  # store every message before handling any (H16)
                for message in adapter.inbound(): counts[inbox.enqueue(message)] += 1
                counts["handled"] = len(inbox.drain(conversation))
            finally:
                inbox.close()
            print("fixture_chat: " + " ".join(f"{k}={v}" for k, v in counts.items()), file=sys.stderr)
        conversation.flush(adapter)
    except (ConfigError, UnsafeState, OSError, ValueError, KeyError, TypeError) as exc:
        detail = str(exc) if str(exc).startswith("fixture line ") else f"{type(exc).__name__}: {exc}"
        print(f"fixture_chat: {detail}", file=sys.stderr)
        return 2
    for row in adapter.sent: print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
