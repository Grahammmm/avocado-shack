"""HASS-FAST-1: a read-only stage-time log. One JSON line per stage: {"t": epoch seconds, "stage": name, "id": 12 hex}.
The id is the first 12 hex characters of SHA-256 of a message id (or a reply id), so a line never carries message
text, a sender, a chat, an address, a path or a secret. Writing is best effort and can never raise: a full disk, a
missing directory or a bad path just means no line. The file stops growing at MAX_BYTES (one rollover to `.1`).
`table()` joins the Mac log and the host log into the stage table (offsets from the first stage of each message).
Nothing here reads a clock the callers do not pass in, opens a socket or changes any state.
"""
import hashlib, json, os, time  # noqa: E401
from pathlib import Path

MAX_BYTES = 512 * 1024
ORDER = ("sent", "webhook-in", "accepted", "ack-start", "ack-end", "post-start", "receiver-accepted", "post-end", "worker-pickup",
         "interp-start", "interp-end", "handled", "reply-queued", "reply-pulled", "bb-send-start", "bb-send-end")


def short(value) -> str:
    """The log id of a message or reply id (12 hex characters, one way)."""
    return hashlib.sha256(str(value).encode("utf-8", "surrogatepass")).hexdigest()[:12]


class StageLog:
    """Append-only, size-capped, never raises. `path` None means off. `clock` is a callable returning epoch seconds."""

    def __init__(self, path=None, clock=time.time):
        self.path, self.clock = (os.fspath(path) if path else None), clock

    def __call__(self, stage, ident, **extra):
        if not self.path: return
        try:
            line = json.dumps({"t": round(self.clock(), 3), "stage": stage, "id": short(ident), **extra}, sort_keys=True) + "\n"
            try:
                if os.stat(self.path).st_size > MAX_BYTES: os.replace(self.path, self.path + ".1")
            except FileNotFoundError: pass
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try: os.write(fd, line.encode("utf-8"))
            finally: os.close(fd)
        except Exception:  # noqa: BLE001 - a log line is never worth a crash; nothing is kept about the error
            pass


def off(stage, ident, **extra): return None  # noqa: E704 - the no-op stand-in


def read(path) -> list:
    """The valid lines of one stage log, in file order; unreadable or malformed lines are skipped."""
    out = []
    try: text = Path(path).read_text("utf-8", "replace")
    except OSError: return out
    for raw in text.splitlines():
        try: row = json.loads(raw)
        # Excessive nesting is malformed diagnostic input too; skip only this line.
        except (ValueError, RecursionError): continue
        if type(row) is dict and type(row.get("t")) in (int, float) and type(row.get("stage")) is str and type(row.get("id")) is str:
            out.append(row)
    return out


def table(rows) -> list:
    """[(message id, {stage: seconds after that message's first stage})] from the merged rows of both logs. Reply stages
    (keyed by reply id) join their message through the `reply-queued` line, which carries both `id` and `rid`."""
    by_reply = {r["rid"]: r["id"] for r in rows if r["stage"] == "reply-queued" and type(r.get("rid")) is str}
    first, seen = {}, {}
    for r in sorted(rows, key=lambda r: r["t"]):
        ident = by_reply.get(r["id"], r["id"]) if r["stage"] in ("reply-pulled", "bb-send-start", "bb-send-end") else r["id"]
        seen.setdefault(ident, {}).setdefault(r["stage"], r["t"])
        first[ident] = min(first.get(ident, r["t"]), r["t"])
    return [(i, {s: round(t - first[i], 3) for s, t in sorted(st.items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99)})
            for i, st in seen.items() if "accepted" in st or "webhook-in" in st]


def main(argv=None) -> int:
    """`python3 hass/stagelog.py LOG [LOG ...]`: read-only; prints one line per message, seconds after its first stage, for the
    Mac log (spool dir `stages.jsonl`) and the host log (host dir `stages.jsonl`) together. Both machines' clocks should be in step."""
    import sys
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(main.__doc__)
        return 2
    for ident, stages in table([r for path in args for r in read(path)]):
        print(ident, " ".join(f"{s}={t}" for s, t in stages.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
