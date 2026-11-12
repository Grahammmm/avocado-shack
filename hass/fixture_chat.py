"""Fixture conversation adapter (H05). A fixture is not iMessage: messages come from a JSONL file and sends are
only recorded in memory.

    python3 hass/fixture_chat.py --state DIR --fixture FILE --interpreter FILE [--preview] [--queue START_AT]

Runs every fixture message through a Conversation (production op registry, FixtureInterpreter from the JSON
mapping FILE), flushes the outbox into memory and prints it as JSON lines. It sends nothing anywhere.
--preview adds the writer worktree's Previewer (private proposal/result screenshots, verify-before-reply;
PLAYWRIGHT_MODULE and CHROMIUM_PATH are read from the environment).
--queue START_AT stores every message in <state>/inbox.sqlite3 first, then drains it once (H16): messages before the
start point and repeats never become commands; stderr gets one counts-only summary line.
--photos DIR (NB-AV-13): a row's `photos: [name]` become its attachments, read from regular files directly in DIR
(settings need mediaRoot); without it the field is ignored.
--labels URL --label-model NAME (H10) give the Conversation a LabelReader (loopback vision model, read on a photo
only: needs --photos and both flags); without them nothing changes. No model is called while building the reader.
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
from hass.label_reader import LabelReader  # noqa: E402
from hass.preview import Previewer  # noqa: E402


def _row(n, line, photos=None, names=None) -> Inbound:  # every check names line n and the field, never the value
    def bad(what): raise ValueError(f"fixture line {n}: {what}")
    try: r = json.loads(line)
    except (ValueError, RecursionError): bad("not JSON")
    if not isinstance(r, dict): bad("row must be a JSON object")
    if type(r.get("id")) not in (int, str) or r.get("id") == "": bad("id must be a non-empty string or an integer")
    for field in ("chat", "sender", "text"):
        if not isinstance(r.get(field), str): bad(f"{field} must be a string")
    if not isinstance(r.get("fromMe", False), bool): bad("fromMe must be true or false")
    if not (isinstance(kind := r.get("kind", "new"), str) and kind): bad("kind must be a non-empty string")
    try: at = datetime.fromisoformat(r.get("at"))
    except (TypeError, ValueError): at = None
    if at is None or at.utcoffset() is None: bad("at must be an ISO time with a UTC offset")
    try: at.astimezone(timezone.utc)  # RF0010-12: replay converts later; check it here, before any row runs
    except (OverflowError, ValueError): bad("at must be representable in UTC")
    files = r.get("photos", []) if photos is not None else []  # NB-AV-13: plain names of regular files in --photos
    if not isinstance(files, list) or not all(isinstance(f, str) and f not in ("", ".", "..") and Path(f).name == f and
                                              not (q := Path(photos) / f).is_symlink() and q.is_file() for f in files):
        bad("photos must name regular files directly inside --photos")
    if names is not None: names.setdefault(str(r["id"]), files)  # a repeated id keeps its first row's photos
    return Inbound(provider_id=str(r["id"]), chat=r["chat"], sender=r["sender"], text=r["text"],
                   from_me=r.get("fromMe", False), kind=kind, received_at=r["at"], attachments=len(files))


class FixtureAdapter:
    """Reads inbound JSONL (`id, chat, sender, text, fromMe, kind, at`, with `photos=DIR` also `photos: [name]`);
    records sends; `fail_sends=N` raises N times. With `photos` it is also the Conversation's photo source."""

    def __init__(self, path=None, fail_sends=0, photos=None):
        self.path, self.fail_sends, self.sent, self.photos, self.names = path, fail_sends, [], photos, {}

    def inbound(self) -> list:
        lines = Path(self.path).read_text("utf-8").splitlines()
        return [_row(n, s, self.photos, self.names) for n, s in enumerate(lines, 1) if s.strip()]  # n: physical lines

    def fetch(self, provider_id, count) -> list:  # NB-AV-13 photo source: that row's files, as checked by _row
        return [(Path(self.photos) / name).read_bytes() for name in self.names[provider_id][:count]]

    def send(self, chat, text, attachments):
        if self.fail_sends > 0:
            self.fail_sends -= 1
            raise ConnectionError("fixture send failure")
        self.sent.append({"chat": chat, "text": text, "attachments": list(attachments)})


class FixtureConversation(Conversation):
    """Replay at each row's validated time, in direct or inbox processing order.

    Only this offline adapter trusts fixture timestamps as its processing clock;
    live conversations still use their injected clock and the H05 approval guard.
    With `sink` (an adapter), each row's replies are sent at that row's own time, as a live run sends them when they
    are written, so the AVB-07 "(Delayed reply, ...)" prefix is not added just because the transcript is long.
    A failed per-row send leaves the reply in the outbox; the caller's final flush retries it (and raises).
    """

    def __init__(self, *args, sink=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sink = sink

    def handle(self, msg: Inbound, last_try=False, apply=True) -> str:
        at = datetime.fromisoformat(msg.received_at).astimezone(timezone.utc)
        # A delayed row cannot turn processing time back before a proposal.
        self._fixture_at = max(at, getattr(self, "_fixture_at", at))
        self.clock = lambda: self._fixture_at
        disposition = super().handle(msg, last_try=last_try, apply=apply)
        if self.sink is not None:
            try: self.flush(self.sink)
            except OSError: pass  # still unsent; the final flush retries it at the last row's time
        return disposition


def _load_interpreter(path) -> FixtureInterpreter:  # H09: a failure names the flag, never the file
    try: text = Path(path).read_text("utf-8")
    except (OSError, UnicodeDecodeError): raise ValueError("--interpreter: unreadable") from None
    try: mapping = json.loads(text)
    except (ValueError, RecursionError): raise ValueError("--interpreter: not JSON") from None
    if not isinstance(mapping, dict): raise ValueError("--interpreter: not a JSON object")
    return FixtureInterpreter(mapping)


def _load_labels(url, model, photos):  # H10: a failure names the flag, never the URL or the model
    if url is None and model is None: return None
    if url is None or model is None: raise ValueError("--labels and --label-model go together")
    if photos is None: raise ValueError("--labels: needs --photos")
    try: LabelReader(url, "label-check")  # a known-good model: a failure here is the URL
    except ValueError: raise ValueError("--labels: not a loopback http URL") from None
    try: return LabelReader(url, model)
    except ValueError as exc: raise ValueError(f"--label-model: {exc}") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/fixture_chat.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("--state", "--fixture", "--interpreter"): parser.add_argument(name, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--queue", metavar="START_AT")
    parser.add_argument("--photos", metavar="DIR")
    parser.add_argument("--labels", metavar="URL")
    parser.add_argument("--label-model", metavar="NAME")
    args = parser.parse_args(argv)
    try:
        adapter = FixtureAdapter(args.fixture, photos=args.photos)
        interpreter = _load_interpreter(args.interpreter)
        labels = _load_labels(args.labels, args.label_model, args.photos)
        editor = Editor(args.state)
        previewer = Previewer(editor_mod._load(args.state)[2]) if args.preview else None
        conversation = FixtureConversation(args.state, editor, interpreter, lambda: datetime.now(timezone.utc), previewer,
                                           photos=adapter if args.photos is not None else None, labels=labels,
                                           sink=adapter)
        inbox = None if args.queue is None else Inbox(args.state, start_at=args.queue)
        counts = {"queued": 0, "duplicate": 0, "history": 0}
        try:  # the fixture is read once, before any message is handled or stored (H16)
            try: messages = adapter.inbound()
            except (OSError, UnicodeDecodeError): raise ValueError("--fixture: unreadable") from None
            if inbox is None:
                for message in messages: conversation.handle(message)
            else:
                for message in messages: counts[inbox.enqueue(message)] += 1
                counts["handled"] = len(inbox.drain(conversation))
        finally:
            if inbox is not None: inbox.close()
        if inbox is not None:
            print("fixture_chat: " + " ".join(f"{k}={v}" for k, v in counts.items()), file=sys.stderr)
        conversation.flush(adapter)
    except (ConfigError, UnsafeState, OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, OSError): detail = f"{type(exc).__name__}: {exc.strerror or 'error'}"  # never the path
        elif str(exc).startswith(("fixture line ", "--")): detail = str(exc)
        else: detail = f"{type(exc).__name__}: {exc}"
        print(f"fixture_chat: {detail}", file=sys.stderr)
        return 2
    for row in adapter.sent: print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
