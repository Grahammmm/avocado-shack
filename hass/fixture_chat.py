"""Fixture conversation adapter (H05). A fixture is not iMessage: messages come from a JSONL file and sends are
only recorded in memory.

    python3 hass/fixture_chat.py --state DIR --fixture FILE --interpreter FILE [--preview]

Runs every fixture message through a Conversation (production op registry, FixtureInterpreter from the JSON
mapping FILE), flushes the outbox into memory and prints it as JSON lines. It sends nothing anywhere.
--preview adds the writer worktree's Previewer (private proposal/result screenshots, verify-before-reply;
PLAYWRIGHT_MODULE and CHROMIUM_PATH are read from the environment).
Exit codes: 0 done, 2 unsafe state dir, missing settings or unreadable input.
"""
import argparse, json, sys  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.conversation import ConfigError, Conversation, Editor, FixtureInterpreter, Inbound  # noqa: E402
from hass.editor import UnsafeState  # noqa: E402
from hass import editor as editor_mod  # noqa: E402
from hass.preview import Previewer  # noqa: E402


class FixtureAdapter:
    """Reads inbound JSONL (`id, chat, sender, text, fromMe, kind, at`); records sends; `fail_sends=N` raises N times."""

    def __init__(self, path=None, fail_sends=0):
        self.path, self.fail_sends, self.sent = path, fail_sends, []

    def inbound(self) -> list:
        rows = [json.loads(line) for line in Path(self.path).read_text("utf-8").splitlines() if line.strip()]
        return [Inbound(provider_id=str(r["id"]), chat=r["chat"], sender=r["sender"], text=r["text"],
                        from_me=bool(r.get("fromMe", False)), kind=r.get("kind", "new"), received_at=r["at"])
                for r in rows]

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
    args = parser.parse_args(argv)
    try:
        adapter = FixtureAdapter(args.fixture)
        interpreter = FixtureInterpreter(json.loads(Path(args.interpreter).read_text("utf-8")))
        editor = Editor(args.state)
        previewer = Previewer(editor_mod._load(args.state)[2]) if args.preview else None
        conversation = Conversation(args.state, editor, interpreter, lambda: datetime.now(timezone.utc), previewer)
        for message in adapter.inbound(): conversation.handle(message)
        conversation.flush(adapter)
    except (ConfigError, UnsafeState, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"fixture_chat: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    for row in adapter.sent: print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
