"""AVB-10: one audit log for every action Hass takes, on the site and on the till.

Where: `<state>/audit/<UTC day>.jsonl` (folder 0700, files 0600, owned by the Hass user). Append-only: a line is added
with O_APPEND under an exclusive lock, flushed to disk, and never edited. It is in the state backup (statebackup.DIRS).

One line per step of an action (HASS-ARCHITECTURE section 5):
  at, seq        UTC time; the line's number in its day file (1, 2, ...)
  action         one id per owner request (`act-` + 12 hex); every step of it shares the id
  step           one of STEPS
  who            the role that asked: `owner`, `owner:<first name>`, `operator`, `timer` (never a number or address)
  msg            12 hex, one way (stagelog.short) of the message that caused this step; for `approved` that is the yes
  skill          `group.verb@version` (several joined with `+`), when a skill made the plan
  pack, target, env   one of PACKS; one of TARGETS; `sandbox` or `live`
  draft          the draft code the owner saw (4-12 hex)
  approval       A0 none, A1 owner yes, A2 owner yes + second yes, A3 a named G exception
  approved_by    the role that said yes
  result         one fixed word from RESULTS
  subjects       at most 10 ids `<collection>:<key>` (record or till ids)
  fields         at most 20 field names that change
  refs           pointers to the detailed records that stay where they are: `change` (chg-<12 hex>, the editor's change
                 record and the release journal), `commit` (40 hex), `till` (the till journal id)
  undo_of        the action this one takes back

Never in a line: message text, owner words, prices, counts, phone numbers, addresses or tokens. Every key is on a closed
list and every value must match its pattern; a digit run over 4 is refused outside the id keys (check()). A line that
fails the check is not written. record() never raises unless strict=True: the chat must keep answering if a disk is
full, but a till write (AVB-15) calls it with strict=True and stops when the line could not be written. record() says True
only when every byte of the line is written and flushed (a short write is finished; no progress or an error raises).

Framing: a record is one line ended by the LF byte, holding exactly the bytes record() writes for a valid row. A line
without its LF (a write that stopped) is never a record: the readers skip it, `check` counts it as bad, and the next
record() puts TORN (`!torn` LF) after it instead of a bare LF, so it stays bad for good and keeps its own number. The LF
says only where a line ends: it does not prove the flush finished, that the caller was told yes, or that a till write ran.

A skill request that makes no draft is an action of its own (`target: local`): `answered` for a read-only skill (A0) and
`refused` for a refusal before any draft (hass/skills/dispatch.py, Conversation._audit_ask).

Command line (on the box; prints ids and codes only):
  python3 hass/audit.py show --state DIR [--days N] [--action ID]   one JSON line per audit line
  python3 hass/audit.py history --state DIR [--limit N]             one plain line per action, newest first
  python3 hass/audit.py check --state DIR                           every line against the rules; exit 1 on a bad one
"""
import argparse, fcntl, json, os, re, stat, sys  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.stagelog import short  # noqa: E402

FOLDER = "audit"
DAY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl")
MAX_LINE = 4096  # bytes, TORN included; a line is ids and codes only, so this is never reached by a valid row
# Written in front of the next line when the file does not end in LF (a write that stopped). It closes the torn line with
# bytes that can never end a JSON object, so that line stays bad for good; nothing on disk is cut, moved or rewritten.
TORN = b"!torn\n"
STEPS = ("asked", "drafted", "refused", "approved", "applied", "published", "verified", "failed", "undone", "answered")
PACKS = ("site", "front", "till", "reports", "core")
TARGETS = ("site", "till", "local")
ENVS = ("sandbox", "live")
APPROVALS = ("A0", "A1", "A2", "A3")
RESULTS = ("ok", "stale", "cap", "policy", "stopped", "unknown", "said-no", "expired", "replaced", "refused", "busy",
           "failed", "not-verified", "interrupted", "backlog")
# the pack of a skill group (HASS-ARCHITECTURE section 3) until AVB-09 puts `pack` on every skill; any other group is `site`
GROUP_PACKS = {"report": "reports", "social": "reports", "answer": "core", "backlog": "core", "page.faq": "front", "till": "till"}
MAX_SUBJECTS, MAX_FIELDS = 10, 20
ROLE_RE = re.compile(r"owner(?::[a-z]{1,20})?|operator|timer")
HEX12 = re.compile(r"[0-9a-f]{12}")
ACTION_RE = re.compile(r"act-[0-9a-f]{12}")
SKILL_RE = re.compile(r"[a-z][a-z_]{0,30}\.[a-z][a-z_]{0,30}(?:@[0-9]{1,4})?(?:\+[a-z][a-z_]{0,30}\.[a-z][a-z_]{0,30}(?:@[0-9]{1,4})?){0,4}")
DRAFT_RE = re.compile(r"[0-9a-f]{4,12}")
SUBJECT_RE = re.compile(r"[a-zA-Z][a-zA-Z_]{0,30}(?::[A-Za-z0-9][A-Za-z0-9_-]{0,63})?")
FIELD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_.]{0,39}")
REFS = {"change": re.compile(r"chg-[0-9a-f]{12}"), "commit": re.compile(r"[0-9a-f]{40}"),
        "till": re.compile(r"[a-z]{1,8}-[0-9a-f]{8,32}")}
AT_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
DIGITS_RE = re.compile(r"\d{5,}")  # any script's digits: five in a row could be a phone number, a price or a count
ID_KEYS = frozenset({"at", "seq", "action", "msg", "draft", "refs", "undo_of"})  # hex and times: the digit rule does not apply
REQUIRED = ("at", "seq", "action", "step", "who", "pack", "target", "env", "result")
ONE_OF = {"step": STEPS, "pack": PACKS, "target": TARGETS, "env": ENVS, "approval": APPROVALS, "result": RESULTS}
PATTERNS = {"action": ACTION_RE, "undo_of": ACTION_RE, "who": ROLE_RE, "approved_by": ROLE_RE, "msg": HEX12, "skill": SKILL_RE,
            "draft": DRAFT_RE, "at": AT_RE}
KEYS = frozenset(REQUIRED) | frozenset(PATTERNS) | frozenset(ONE_OF) | {"subjects", "fields", "refs"}


class AuditError(Exception):
    """A line was not written (strict=True only). The message is a fixed phrase: never a value, a path or a text."""


def new_action(*parts) -> str:
    """A one-way action id from things that identify the request (for example a draft code and its row)."""
    return "act-" + short(":".join(str(p) for p in parts))


def pack_of(names) -> str:
    """The one pack of these skill names (`report.shelf`, ...); skills of different packs together are `core`."""
    packs = {GROUP_PACKS.get(n, GROUP_PACKS.get(n.split(".")[0], "site")) for n in names if isinstance(n, str)}
    return packs.pop() if len(packs) == 1 else "core"


def check(row) -> list:
    """The rule problems of one line as fixed phrases naming only keys; [] when the line may be kept."""
    if type(row) is not dict: return ["not an object"]
    problems = [f"unknown key: {k}" if isinstance(k, str) and re.fullmatch(r"[a-z_]{1,20}", k) else "unknown key"
                for k in row if k not in KEYS]
    problems += [f"missing: {k}" for k in REQUIRED if k not in row]
    for key, value in row.items():
        if key not in KEYS: continue
        if key == "seq": ok = type(value) is int and 1 <= value <= 10 ** 9
        elif key in ONE_OF: ok = isinstance(value, str) and value in ONE_OF[key]
        elif key in PATTERNS: ok = isinstance(value, str) and bool(PATTERNS[key].fullmatch(value)) and (key != "at" or _real_time(value))
        elif key == "subjects": ok = _list_of(value, SUBJECT_RE, MAX_SUBJECTS)
        elif key == "fields": ok = _list_of(value, FIELD_RE, MAX_FIELDS)
        else: ok = type(value) is dict and bool(value) and all(k in REFS and isinstance(v, str) and REFS[k].fullmatch(v) for k, v in value.items())
        if not ok: problems.append(f"bad value: {key}")
        elif key not in ID_KEYS and any(DIGITS_RE.search(v) for v in (value if isinstance(value, list) else [value]) if isinstance(v, str)):
            problems.append(f"digit run: {key}")
    if row.get("step") == "approved" and "approved_by" not in row: problems.append("missing: approved_by")
    return problems


def _real_time(text) -> bool:
    """A width-checked `at` that is a real UTC date and clock time (no leap second, no year 0)."""
    try:
        datetime(int(text[:4]), int(text[5:7]), int(text[8:10]), int(text[11:13]), int(text[14:16]), int(text[17:19]))
        return True
    except ValueError:
        return False


def _list_of(value, pattern, limit) -> bool:
    return type(value) is list and 1 <= len(value) <= limit and len(set(map(str, value))) == len(value) \
        and all(isinstance(v, str) and pattern.fullmatch(v) for v in value)


def subjects_of(records) -> list:
    """`<collection>:<key>` of the touched records, in order, at most MAX_SUBJECTS; an id that breaks the rules is left out."""
    out = []
    for r in records if isinstance(records, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("collection"), str): continue
        key = r.get("key")
        sub = r["collection"] + (f":{key}" if isinstance(key, str) and key and key != r["collection"] else "")
        if SUBJECT_RE.fullmatch(sub) and not DIGITS_RE.search(sub) and sub not in out: out.append(sub)
    return out[:MAX_SUBJECTS]


def fields_of(records) -> list:
    """The names of the fields the records change (a whole record added or removed is `record`), at most MAX_FIELDS."""
    out = []
    for r in records if isinstance(records, list) else []:
        if not isinstance(r, dict): continue
        before, after = r.get("before"), r.get("after")
        names = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)) \
            if isinstance(before, dict) and isinstance(after, dict) else ["record"]
        out += [n for n in names if isinstance(n, str) and FIELD_RE.fullmatch(n) and not DIGITS_RE.search(n) and n not in out]
    return out[:MAX_FIELDS]


def _utc(now) -> datetime:
    return now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _private_dir(sdir) -> Path:
    """The audit folder: created 0700; a link, another owner's folder or a wider mode is refused (OSError)."""
    path = Path(sdir) / FOLDER
    try: os.mkdir(path, 0o700)
    except FileExistsError: pass
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise OSError("audit folder is not a private folder")
    return path


class AuditLog:
    """Append-only writer and reader of one state folder's audit log. `clock` returns an aware datetime."""

    def __init__(self, state_dir, clock):
        self.sdir, self.clock = Path(state_dir), clock

    def record(self, step, *, action, who, pack, target, env, result, strict=False, **extra) -> bool:
        """Append one line; True when it is on disk. Keys left None are not written. Never raises unless strict."""
        try:
            now = _utc(self.clock())
            row = {"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "action": action, "step": step, "who": who, "pack": pack,
                   "target": target, "env": env, "result": result, **extra}
            row = {k: v for k, v in row.items() if v is not None and v != [] and v != {}}
            row["seq"] = 1  # checked with a placeholder; the real number is taken under the lock
            if check(row): raise AuditError("the audit line breaks the rules; nothing was written")
            self._append(now.strftime("%Y-%m-%d") + ".jsonl", row)
            return True
        except Exception as exc:  # noqa: BLE001 - a lost line never costs a reply; strict callers stop instead
            if strict: raise exc if isinstance(exc, AuditError) else AuditError("the audit line could not be written") from None
            return False

    def _append(self, name, row):
        path = _private_dir(self.sdir) / name
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600:
                raise OSError("audit file is not a private file")
            fcntl.flock(fd, fcntl.LOCK_EX)  # one writer at a time: the chat worker and a till run never share a number
            size, lines = os.fstat(fd).st_size, 0
            os.lseek(fd, 0, os.SEEK_SET)
            while chunk := os.read(fd, 1 << 16): lines += chunk.count(b"\n")
            torn = bool(size) and os.pread(fd, 1, size - 1) != b"\n"
            # A torn last line (a write that stopped before its LF) is closed with TORN, never a bare LF: it then ends in
            # bytes that are not JSON, so it stays a bad line for good and keeps its own number.
            row["seq"] = lines + (2 if torn else 1)
            data = (TORN if torn else b"") + _encode(row) + b"\n"
            if len(data) > MAX_LINE: raise AuditError("the audit line is too long")
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)

    # -- reading ---------------------------------------------------------------------------------------------------
    def days(self) -> list:
        """The day files, oldest first; none when the folder is missing or not private."""
        path = self.sdir / FOLDER
        try:
            st = os.lstat(path)
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid(): return []
            return sorted(p for p in path.iterdir() if DAY_RE.fullmatch(p.name) and p.is_file() and not p.is_symlink())
        except OSError:
            return []

    @staticmethod
    def scan_day(path):
        """(the records of one day file in file order, the number of bad lines), or None when it cannot be read.
        Framing is the literal LF byte only: a record is exactly the bytes record() writes for a valid row, ended by LF.
        Anything else is a bad line: a torn or closed-off (TORN) line, a line with other bytes, and an unterminated end."""
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as fh:
                if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode): return None
                data = fh.read()
        except OSError:
            return None
        *ended, tail = data.split(b"\n")  # bytes.split on LF alone: CR, VT, FF or U+2028 never end a line
        out, bad = [], int(bool(tail))  # a nonempty end with no LF is never a record, whatever it holds
        for raw in ended:
            row = _decode(raw)
            if row is None: bad += 1
            else: out.append(row)
        return out, bad

    @classmethod
    def read_day(cls, path) -> list:
        """The records of one day file, in file order; bad lines are skipped (scan_day)."""
        return (cls.scan_day(path) or ([], 0))[0]

    def rows(self, days=None) -> list:
        """Every valid line, oldest first; `days` keeps only the newest N day files."""
        files = self.days()
        return [r for p in (files[-days:] if days else files) for r in self.read_day(p)]

    def approved(self, limit) -> list:
        """Up to `limit` actions with an `approved` step, newest approval first, each as
        {"action", "draft", "target", "env", "at", "last": the newest line of that action, "undone_by": action or None,
         "saved": True when a later line of the action says the write itself went through (applied, published or undone: ok)}.
        Day files are read newest first and reading stops once enough are found, so `history` stays quick."""
        found, later, undone, saved = [], {}, {}, set()
        for path in reversed(self.days()):
            for row in reversed(self.read_day(path)):
                act = row["action"]
                if row["step"] == "undone" and "undo_of" in row and row["result"] == "ok": undone.setdefault(row["undo_of"], act)
                if row["step"] in ("applied", "published", "undone") and row["result"] == "ok": saved.add(act)
                if row["step"] == "approved" and all(f["action"] != act for f in found):
                    found.append({"action": act, "draft": row.get("draft"), "target": row["target"], "env": row["env"],
                                  "at": row["at"], "last": later.get(act, row), "undone_by": undone.get(act),
                                  "saved": act in saved})
                later.setdefault(act, row)
            if len(found) >= limit: break
        return found[:limit]

    def approved_drafts(self) -> set:
        """Every draft code on an `approved` line (history shows older approved drafts that have none)."""
        return {r["draft"] for r in self.rows() if r["step"] == "approved" and "draft" in r}


# -- plain words for the owner's `history` and the command line ---------------------------------------------------------
# results that stop an action before anything is written: only these may say "nothing changed"
NOT_WRITTEN = frozenset({"stale", "cap", "policy", "refused", "said-no", "expired", "replaced"})
UNSURE = "I'm not sure where it stands, so please check it"


def till_state(entry) -> str:
    """Where an approved till action stands, from its newest line, that line's result and whether the write went through.
    Only a check that passed says "checked"; only a failure that stopped it before any write says "nothing changed"; a
    failure after the write, or one that does not say where it stopped, says so plainly instead of guessing."""
    last, saved = entry["last"], entry.get("saved", False)
    step, result = last["step"], last["result"]
    if entry.get("undone_by"): return "undone"
    if step == "approved": return "being saved" if result == "ok" else UNSURE
    if step in ("applied", "published", "undone"):
        return ("saved (an undo)" if step == "undone" else "saved") if result == "ok" else UNSURE
    if step == "verified":
        if result == "ok" and saved: return "saved and checked"
        return "saved, but I couldn't check it, so please look at it" if saved else UNSURE
    if step in ("failed", "refused"):
        if saved: return "something went wrong after it was saved; " + UNSURE
        return "it didn't go through, so nothing changed" if result in NOT_WRITTEN else UNSURE
    return UNSURE


def till_line(entry) -> str:
    """A till change in history. The till journal holds the details; this line says only where it was and where it stands
    (no code: the voice rules keep a bare code out of a reply)."""
    where = "the test till" if entry["env"] == "sandbox" else "the shop till"
    return f"- A change on {where}: {till_state(entry)}."


def _history_text(log, limit) -> str:
    lines = []
    for e in log.approved(limit):
        last = e["last"]
        bits = [e["at"], f"{e['target']} ({e['env']})", last.get("skill") or "-", f"draft {e.get('draft') or '-'}",
                f"{last['step']} {last['result']}"]
        if e.get("undone_by"): bits.append(f"undone by {e['undone_by']}")
        lines.append("  ".join([e["action"], *bits]))
    return "\n".join(lines) if lines else "no approved actions"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Hass audit log (ids and codes only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "history", "check"):
        p = sub.add_parser(name)
        p.add_argument("--state", required=True)
        if name == "show":
            p.add_argument("--days", type=int)
            p.add_argument("--action")
        if name == "history": p.add_argument("--limit", type=int, default=10)
    args = ap.parse_args(argv)
    log = AuditLog(args.state, lambda: datetime.now(timezone.utc))
    if args.cmd == "show":
        for row in log.rows(args.days if args.days and args.days > 0 else None):
            if args.action in (None, row["action"]): print(json.dumps(row, sort_keys=True))
        return 0
    if args.cmd == "history":
        print(_history_text(log, max(1, min(args.limit, 200))))
        return 0
    good = bad = 0
    for path in log.days():
        scanned = log.scan_day(path)
        if scanned is None: bad += 1; continue  # noqa: E702
        good, bad = good + len(scanned[0]), bad + scanned[1]
    print(json.dumps({"result": "ok" if not bad else "bad", "lines": good, "bad": bad, "days": len(log.days())}))
    return 1 if bad else 0


def _encode(row) -> bytes:
    """The one byte form of a record (no LF): sorted keys, no spaces, ASCII."""
    return json.dumps(row, sort_keys=True, separators=(",", ":")).encode("ascii")


def _decode(raw):
    """The record in one LF-ended line, or None: it must pass check() and be byte for byte what _encode writes for it, so
    a line closed off with TORN, a CR before the LF, spaces or any other bytes never count as a record."""
    try:
        row = json.loads(raw.decode("ascii"))
        return row if not check(row) and _encode(row) == raw else None
    except (ValueError, RecursionError, TypeError):
        return None


def _write_all(fd, data) -> None:
    """Write every byte of `data` (a short write goes on from where it stopped). A write that makes no progress or fails
    raises: the line is then not on disk in full and the earlier lines are untouched. The torn end has no LF, so the
    readers skip it and `check` counts it; the next record() closes it with TORN, so it never becomes a record."""
    view = memoryview(data)
    while view:
        done = os.write(fd, view)
        if not isinstance(done, int) or done <= 0 or done > len(view):
            raise AuditError("the audit line could not be written in full")
        view = view[done:]


__all__ = ["AuditLog", "AuditError", "check", "new_action", "pack_of", "subjects_of", "fields_of", "till_line", "till_state",
           "FOLDER"]

if __name__ == "__main__":
    raise SystemExit(main())
