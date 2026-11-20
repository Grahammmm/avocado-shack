"""Core pack: notes, nicknames, history, status, pause/resume, backlog and `show` (Conversation mixin).

AVB-12: moved verbatim out of hass/conversation.py, which imports every name back (hass.conversation.<name> is
unchanged). The methods run on the Conversation (self is the conversation): they use its store, replies and
settings exactly as before. Command routing stays in Conversation._command.
"""
import contextlib, copy, json, os, re, sqlite3, stat  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import owner_answers as answers, audit as audit_mod, editor as editor_mod, margins, memory as memory_mod, morning_report as shelf, voice
from hass.chat.shared import ALIAS_NAME_MAX, CANT_READ, CONTROL, COST_USAGE, LOCAL_TZ, _is_undo, _iso, load_content, NOTHING, q, STATUS_PLAIN
from hass.chat.wording import proposal_text, _record_lines
from hass.content_model import _text as checked_text
from hass.ops import catalog, hikes
from hass.skills import dispatch as dispatch_mod

MEMORY_LIST_MAX, HISTORY_MAX = 20, 5  # AV1537-14: docs/hass/LIMITS.md states these (test_limits_doc)
ALIAS_LIST_MAX = 20  # AV0222-05: `memory` lists this many aliases apart from the notes (LIMITS.md)
COSTS_LIST_MAX = 20  # AV2137-06: `costs` lists this many saved purchase costs; `memory` lists none of them (LIMITS.md)
COSTS_UNAVAILABLE = "I can't read the saved costs right now. Nothing has changed. Could you try again in a little while?"
COSTS_NO_NAMES = "I can't look up the product names right now, so some lines show only the product code."
HISTORY_STATES = ("approved", "applied", "verified", "failed", "reverted")  # AV2022-06: owner-approved changes only

HISTORY_SEARCH_MAX, HISTORY_TEXT_MAX = 10, 60  # AV2152-02 (H06/H17): `history <words>`; docs/hass/COMMANDS.md
TIME_UNKNOWN = "time unknown"  # AV0222-06: a history line whose approval row is missing or unreadable
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")  # fixed English names: no process-locale %a/%b/%p
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
HISTORY_USAGE = "Tell me a word or two to look for, like " + q("history opening hours") + "."

AGAIN_WINDOW_DAYS = 7  # AV2152-03 (H05/H16): `again <code>` works for a proposal that expired at most this long ago; COMMANDS.md
AGAIN_USAGE = "Send " + q("again") + " and an expired draft code, e.g. " + q("again a1b2") + "."
AGAIN_PHOTO_OPS = ("product.set_photo", "store.set_home_image")  # ops that carry a stored photo; any op with args.photo does too
AGAIN_DRIFT = "the site changed since {code}; send the change again"
AGAIN_UNDO = "That code is for an undo. Use again with the original change's code."


class CorePack:
    """Core pack commands, mixed into Conversation."""

    def _history_when(self, r) -> str:
        """AV0222-06: when this change's owner approval was recorded, in Pacific time ("Tue Nov 3 2:14 pm"), from the approval row
        bound to the draft (change id, hash, base, expiry and chat); anything missing or unreadable says "time unknown", never a guess."""
        try:
            bind = tuple(r[k] for k in ("change_id", "draft_hash", "base", "expires_at", "chat"))
            if any(not isinstance(v, str) or not v for v in bind): return TIME_UNKNOWN
            row = self.db.execute("SELECT approved_at FROM approvals WHERE change_id = ? AND draft_hash = ? AND base = ? AND expires_at = ? "
                                  "AND chat = ? ORDER BY id DESC LIMIT 1", bind).fetchone()
            raw = row["approved_at"] if row is not None else None
        except (ValueError, TypeError, OverflowError, OSError, KeyError, IndexError, sqlite3.Error): return TIME_UNKNOWN
        return self._history_time(raw)

    @staticmethod
    def _history_time(raw) -> str:
        try:
            if not isinstance(raw, str): return TIME_UNKNOWN
            at = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw)
            if at.tzinfo is None or at.utcoffset() is None: return TIME_UNKNOWN
            at = at.astimezone(LOCAL_TZ)
            hour = at.hour % 12 or 12
            return f"{_DAYS[at.weekday()]} {_MONTHS[at.month - 1]} {at.day} {hour}:{at.minute:02d} {'am' if at.hour < 12 else 'pm'}"
        except (ValueError, TypeError, OverflowError, OSError): return TIME_UNKNOWN

    def _history_line(self, r) -> str:
        """One `history` line. HASS-OWNERS-2: with several owners it says whose change it was (`Mike's change`, `Your change`)."""
        when = self._history_when(r)
        words = f"{q(r['summary'])}, {when if when == TIME_UNKNOWN else 'approved ' + when}: {answers.history_words(dict(r), self._install(r))}"
        return f"- {self._whose(r['chat'])}, {words}" if self._shared else f"- {words}"

    def _history_lines(self, limit) -> list:
        """AVB-10: `history` reads the audit log: the newest approved actions on the site and the till, newest yes first. A site
        change is told in its own words from its draft row (where it is now); a till change says which till and where it
        stands, since the till journal keeps its details. Changes approved before the audit log existed (no `approved` line)
        follow, newest first, as before."""
        lines = []
        try: entries = self.audit.approved(3 * limit)  # slack for actions whose draft was re-written (stale) and not shown
        except Exception: entries = []  # noqa: BLE001,E701 - an unreadable log still shows the changes below
        for e in entries:
            if e["target"] == "site" and e.get("draft"):
                row = self.db.execute("SELECT * FROM drafts WHERE code = ?", (e["draft"],)).fetchone()
                if row is not None and row["state"] in HISTORY_STATES: lines.append(self._history_line(row))
            elif e["target"] == "till":
                when = self._history_time(e.get("at"))  # the audit entry's approved step, not its later result
                head, sep, state = audit_mod.till_line(e).partition(":")
                lines.append(f"{head}, {when if when == TIME_UNKNOWN else 'approved ' + when}{sep}{state}")
            if len(lines) >= limit: return lines
        try: logged = self.audit.approved_drafts()
        except Exception: logged = set()  # noqa: BLE001,E701
        for r in self.db.execute(f"SELECT * FROM drafts WHERE state IN ({', '.join('?' * len(HISTORY_STATES))}) "
                                 "ORDER BY row_id DESC", HISTORY_STATES):
            if len(lines) >= limit: break
            if r["code"] not in logged: lines.append(self._history_line(r))  # SHOP-4: where it is now instead of the commit
        return lines

    def _history_search(self, query: str) -> str:
        """AV2152-02: up to ten newest owner-approved changes whose summary holds every word; read-only."""
        words = catalog._fold(query).split() if 1 <= len(query) <= HISTORY_TEXT_MAX and query.isprintable() else []
        if not words:
            self._reply(HISTORY_USAGE)
            return "history"
        found = []
        for r in self.db.execute(f"SELECT * FROM drafts WHERE state IN ({', '.join('?' * len(HISTORY_STATES))}) "
                                 "ORDER BY row_id DESC", HISTORY_STATES):
            folded = catalog._fold(r["summary"])
            if all(w in folded for w in words): found.append(r)
            if len(found) >= HISTORY_SEARCH_MAX: break
        self._reply("\n".join(["These match:"] + [self._history_line(r) for r in found]) if found else f"I found no changes that match {q(query)}.", long_ok=True)
        return "history"

    # -- AV2152-03 (H05/H16): `again <code>` ----------------------------------------------------------------------
    @staticmethod
    def _again_final(records):
        """{(collection, key): canonical JSON of the record's LAST `after`} for a well-shaped, non-empty record list; else None.
        Only the end state counts: before, summaries and order of records are ignored; JSON scalar types, null and list order are not."""
        if not isinstance(records, list) or not records: return None
        final = {}
        try:
            for r in records:
                if not (isinstance(r, dict) and isinstance(r.get("collection"), str) and isinstance(r.get("key"), str) and "after" in r): return None
                final[(r["collection"], r["key"])] = json.dumps(r["after"], sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, RecursionError): return None
        return final

    def _again_original(self, row):
        """The stored draft an expired row proposed, copied, when it still matches the row (id, hash, base, ops) and holds
        well-shaped records; else None."""
        try:
            out = self.editor.show(row["change_id"])
            draft, ops = out.get("draft") if out.get("result") == "ok" else None, json.loads(row["ops_json"])
            if draft is None and row["state"] == "reverted": draft = self._again_stored(row["change_id"])  # AV2137-01: show() gives an applied change, not its draft
            if not isinstance(draft, dict) or not isinstance(ops, list) or not ops or draft.get("ops") != ops: return None
            if any(not (isinstance(c, dict) and isinstance(c.get("op"), str) and isinstance(c.get("args"), dict)) for c in ops): return None
            if any(draft.get(k) != row[k] for k in ("change_id", "draft_hash", "base")) or self._again_final(draft.get("records")) is None: return None
            return copy.deepcopy(draft)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, editor_mod.UnsafeState): return None

    def _again_stored(self, change_id):
        """AV2137-01: <state>/drafts/<id>.json of this change when it is a regular file holding an object for that id; else None."""
        try:
            if not editor_mod.CHANGE_ID_RE.fullmatch(str(change_id)): return None
            path = Path(self.sdir) / "drafts" / f"{change_id}.json"
            if not stat.S_ISREG(os.lstat(path).st_mode): return None
            doc = json.loads(path.read_text("utf-8"))
            return doc if isinstance(doc, dict) and doc.get("change_id") == change_id else None
        except (OSError, ValueError, RecursionError): return None

    @staticmethod
    def _has_revert(row) -> bool:
        """AV2137-01: any history.revert call among the draft's ops (a mixed draft too); unparsable counts as none."""
        try: ops = json.loads(row["ops_json"])
        except (TypeError, ValueError, RecursionError): return False
        return isinstance(ops, list) and any(isinstance(c, dict) and c.get("op") == "history.revert" for c in ops)

    def _again_undone_at(self, row):
        """AV2137-01: when the applied undo that reverted `row` was applied (aware datetime), read ONLY from the original's change
        record `revertedBy` -> the undo's change record, whose stored draft must revert this change and whose draft row is in
        this chat; None when any link is missing or inconsistent."""
        try:
            change = self.editor.show(row["change_id"]).get("change")
            undo_id = change.get("revertedBy") if isinstance(change, dict) else None
            if not isinstance(undo_id, str) or not editor_mod.CHANGE_ID_RE.fullmatch(undo_id): return None
            if change.get("state") != "applied" or change.get("change_id") != row["change_id"]: return None
            undo, stored = self.editor.show(undo_id).get("change"), self._again_stored(undo_id)
            if not isinstance(undo, dict) or undo.get("state") != "applied" or undo.get("change_id") != undo_id or stored is None: return None
            if not any(isinstance(c, dict) and c.get("op") == "history.revert" and (c.get("args") or {}).get("changeId") == row["change_id"]
                       for c in stored.get("ops") or []): return None
            if not any(self._mine(r) and _is_undo(r) and r["state"] in ("applied", "verified") for r in self._drafts("change_id = ?", undo_id)): return None
            at = datetime.fromisoformat(undo["applied_at"])
            return at if at.tzinfo is not None else None
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, editor_mod.UnsafeState): return None

    def _again_same(self, row, new) -> bool:
        """True when the draft `new` ends every record it touches with the values the draft of `row` showed (the same records, the
        same whole `after`); an unreadable original is never the same."""
        old = self._again_original(row)
        final = self._again_final(new.get("records")) if isinstance(new, dict) else None
        return old is not None and final is not None and final == self._again_final(old["records"])

    def _again(self, msg, now, arg) -> str:
        """AV2152-03 (H05/H16): re-draft a proposal that expired at most AGAIN_WINDOW_DAYS ago as a NEW proposal (new code, fresh
        expiry), with no interpreter call, only when preparing its stored ops on the site as it is now ends every record it
        touches with the values the expired draft showed. Nothing is revived or applied: the owner still sends `yes <new code>`."""
        if not re.fullmatch(r"[0-9a-f]{4,12}", arg or ""): return self._reply(AGAIN_USAGE) or "again"
        code, row = arg, self._by_code(arg)
        if row is None: return self._reply(f"No draft {q(code)}.") or "again"
        if self._has_revert(row): return self._reply(AGAIN_UNDO) or "again"  # AV2137-01: an undo, or a draft with any undo call
        if row["state"] not in ("expired", "reverted"):  # a live, cancelled, replaced, saved or failed draft is refused with its own state
            self._reply({"proposed": f"{q(code)} is still waiting for your yes, so there is nothing to draft again.",
                         "needs-details": f"{q(code)} is still waiting for details, so there is nothing to draft again."}.get(row["state"]) or self._state_text(row))
            return "again"
        if not row["change_id"] or not row["draft_hash"]: return self._reply(f"{q(code)} expired before it was a proposal; send the change again.") or "again"
        try:  # expired: the age since its expiry; undone (AV2137-01): the age since the linked undo was applied
            since = datetime.fromisoformat(row["expires_at"]) if row["state"] == "expired" else self._again_undone_at(row)
            age = now - since if since is not None and since.tzinfo is not None else None
        except (TypeError, ValueError): age = None
        if age is None or age < timedelta(0): return self._reply(f"{q(code)}: the draft details are not available any more.") or "again"
        if age > timedelta(days=AGAIN_WINDOW_DAYS):
            return self._reply(f"{q(code)} expired more than {AGAIN_WINDOW_DAYS} days ago; send the change again." if row["state"] == "expired" else
                               f"{q(code)} was undone more than {AGAIN_WINDOW_DAYS} days ago; send the change again.") or "again"
        old = self._again_original(row)
        if old is None or (row["state"] == "reverted" and self._again_final((self.editor.show(row["change_id"]).get("change") or {}).get("records")) != self._again_final(old["records"])):
            return self._reply(f"{q(code)}: the draft details are not available any more.") or "again"
        if old.get("assets") or any(c["op"] in AGAIN_PHOTO_OPS or "photo" in c["args"] for c in old["ops"]):
            return self._reply(f"{q(code)} is a photo draft; send the photo again.") or "again"
        if (busy := self._writer_busy(now)) is not None: return self._busy_reply(busy)
        try:  # the stored typed ops, on the site as it is now; never the interpreter, the message history or a claim check
            out = self.editor.prepare(old["ops"], skills=()) if hasattr(self.editor, "gate") else self.editor.prepare(old["ops"])
            new = out.get("draft") if out.get("result") == "ok" else None
        except Exception: new = None  # noqa: BLE001,E701 - any failure to prepare is the same refusal below
        if not self._again_same(row, new): return self._reply(AGAIN_DRIFT.format(code=q(code))) or "again"
        fresh = self._propose(new, msg.sender, now)  # a new row and code, fresh expiry; the expired row stays expired
        self.db.execute("UPDATE drafts SET reason = ? WHERE row_id = ?", (f"again:{code}", fresh["row_id"]))  # a named yes is required
        self._last_draft_code = fresh["code"]
        self._proposal_reply(self._row(fresh["row_id"]), new, f"Again {q(code)}:\n")
        return "proposed"

    def _show(self, code, now) -> tuple:
        """AV0022-08 (H17): (text, attachments) repeating one draft's stored proposal lines and its saved screenshot.
        Read-only: no state move, no expiry sweep, never prepared or rendered again; works while paused."""
        if not code:  # `show` on its own: the newest change that is waiting for a yes
            waiting = [r for r in self._drafts("state = 'proposed'") if self._mine(r) and self._expiry(r) > now]
            if not waiting: return NOTHING, []
            code = waiting[-1]["code"]
        if not re.fullmatch(r"[0-9a-f]{4,12}", code): return "Say " + q("show") + " on its own to see the change that is waiting for you.", []
        if (row := self._by_code(code)) is None: return "I don't have a change with that code.", []
        state = row["state"]
        if state in ("proposed", "needs-details") and self._expiry(row) <= now:  # lapsed, not swept: words it only
            return self._state_text({**dict(row), "state": "expired", "expires_at": _iso(self._expiry(row))}), []
        if state == "needs-details": return "I'm waiting for details: " + row["summary"], []
        if state not in ("proposed", "applied", "verified"): return self._state_text(row), []
        try:
            out = self.editor.show(row["change_id"])
            rec = (out.get("draft") or out.get("change") or {}) if out.get("result") == "ok" else {}
            draft = {"records": rec["records"], "warnings": rec.get("warnings"), "ops": rec.get("ops") or json.loads(row["ops_json"])}  # ops: the live check reads them
            if state == "proposed":
                text = proposal_text(code, draft, row["expires_at"], self._named(row), "Here's the change that is waiting:", undo=_is_undo(row), live_site=self.settings.get("liveSite"), now=now,
                                     reasons=self._live_reasons(draft) if self.settings.get("liveSite") else None)
                shot = self.sdir / "screenshots" / f"{row['change_id']}-proposal.png"
            else:
                text, shot = "\n".join(["Here's what was saved:"] + _record_lines(draft, _is_undo(row), done=True)), row["screenshot"]
            return text, [str(shot)] if shot and Path(shot).is_file() else []
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            return "I can't find the details of that change any more.", []

    # -- H15: remember, forget, memory ---------------------------------------------------------------------------
    def _backlog_table(self) -> bool:
        return self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'backlog'").fetchone() is not None

    def _backlog_list(self) -> str:
        """SKILLS-FW-3 (spec 3.32): the last ten things Hass could not do, newest first, as number, day and one line. Read-only;
        never the stored message. No table made to answer it."""
        from hass.skills.backlog import EMPTY_LIST, Backlog
        rows = Backlog(self.db, self._now).rows() if self._backlog_table() else []
        if not rows:
            self._reply(EMPTY_LIST)
            return "backlog"
        def day(iso):  # "Nov 8": the owner never sees a computer date
            try: return f"{datetime.fromisoformat(iso):%b} {datetime.fromisoformat(iso).day}"
            except (TypeError, ValueError): return "a day I can't read"
        self._reply("Written down so far, newest first:\n" + "\n".join(f"{r['id']}. {day(r['received_at'])} - {r['summary']}" for r in rows)
                    + "\nSay " + voice.quote("forget backlog.3") + " (with that number) to remove one.")
        return "backlog"

    def _backlog_forget(self, number: int) -> str:
        """`forget backlog.<n>`: remove that one row (numbers are never reused). Never more than one row, never the whole list."""
        from hass.skills.backlog import FORGOTTEN, NOT_THERE, Backlog
        done = self._backlog_table() and Backlog(self.db, self._now).forget(number)
        self._reply(FORGOTTEN if done else NOT_THERE)
        return "backlog-forgot" if done else "backlog-none"

    def _memory(self, msg, verb, key, value) -> str:
        """Owner-stated facts on this connection inside the message's transaction; a store ValueError undoes only
        that op's savepoint and the message is still recorded. The interpreter reads notes other than PRIVATE_PREFIXES as preferences (AV1102-09); never facts or claims."""
        if verb == "forget" and re.fullmatch(r"backlog\.[0-9]{1,9}", key): return self._backlog_forget(int(key[8:]))  # SKILLS-FW-3
        if verb == "memory":  # AV0222-05: read-only; no memory table is created to answer it
            has_table = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            if has_table and self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
            every = self.memory.list() if has_table else []
            design = [r for r in every if r["key"].startswith("design.")]  # AV1052-11: kept design requests, listed apart
            rows = [r for r in every if not r["key"].startswith(("alias.", "design.", "cost."))]  # AV2137-06: saved costs are listed by `costs`, never among the notes
            aliases = [r for r in every if r["key"].startswith("alias.")]
            costs = sum(1 for r in every if r["key"].startswith("cost."))  # all of them, well formed or not
            lines = [f"- {q(r['key'])}: {q(r['value'])} (since {voice.natural(datetime.fromisoformat(r['created_at']), self._now())})"
                     for r in rows[:MEMORY_LIST_MAX]]
            more = ["And a few more."] if len(rows) > MEMORY_LIST_MAX else []
            notes = "\n".join(["Notes I'm keeping:"] + lines + more) if rows else "I'm not keeping any notes."
            amore = ["And a few more."] if len(aliases) > ALIAS_LIST_MAX else []
            self._reply("\n".join([notes] + (["Nicknames:"] + self._alias_lines(aliases[:ALIAS_LIST_MAX]) + amore if aliases else
                                            ["I don't have any nicknames."])
                        + ([f"Design notes ({len(design)}):"] + [
                            f"- {r['key']}: {q(r['value'])} (owner, since {voice.natural(datetime.fromisoformat(r['created_at']), self._now())})"
                            for r in design[:MEMORY_LIST_MAX]] + (["And a few more."] if len(design) > MEMORY_LIST_MAX else []) if design else [])
                        + ([f"Costs saved: {costs} (send {q('costs')})"] if costs else [])),
                        long_ok=True)
            return "memory-list"
        if self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        if verb == "alias": return self._alias(msg, key, value)
        if verb == "cost": return self._cost(msg, key, value)
        valid = memory_mod.KEY_RE.fullmatch(key) is not None
        if verb == "forget":
            if value == "spaced" and valid and key.startswith("alias."):  # AV1352-07: `forget alias <name>`: alias or note
                note = "alias-" + key[6:]
                has_alias, has_note = self.memory.get(key) is not None, valid and self.memory.get(note) is not None
                if has_alias and has_note:  # never guess which record to erase
                    self._reply(f"I have both a nickname and a note called {q(key[6:])}, so I forgot neither. "
                                f"Say {q('forget alias ' + key[6:])} for the nickname or {q('forget ' + note)} for the note.")
                    return "memory-ambiguous"
                if has_note: key = note
            if not valid or self.memory.get(key) is None:
                self._reply(f"I don't have a note called {q(key)}.")
                return "memory-none"
            self.memory.forget(key)
            self._reply(f"Okay, I've forgotten {q(key)}.")
            return "memory-forgot"
        problem = "A note's name can only use letters, numbers, dots and dashes, and has to be short." if not valid else None
        if valid and (not memory_mod._clean(value) or len(value) > memory_mod.MAX_VALUE):
            problem = "The note needs to be short, plain text."
        if valid and key.startswith("alias."): problem = "To save a nickname, say it like " + q("alias jam: Linn's blueberry preserves")
        if valid and key.startswith("cost."): problem = COST_USAGE  # AV1222-10
        old, source = (self.memory.get(key) if valid else None), f"owner-stated:{msg.provider_id}"
        if problem is None and old is not None and old == value:  # AVB-15: the same text again changes nothing
            self._reply(f"I already have {q(key)} as {q(value)}, so nothing changed.")
            return "memory-unchanged"
        try:
            if problem is None and old is None: self.memory.remember(key, value, "fact", source)
            elif problem is None: self.memory.correct(key, value, source)
        except ValueError as exc:
            problem = self._memory_words(exc)
        if problem:
            self._problem("could-not-do", "note-refused")
            self._reply(f"I couldn't save that. {problem}" if not problem.startswith("To save") else problem)
            return "memory-invalid"
        self._reply((f"Saved {q(key)}: {q(value)}." if old is None else f"Updated {q(key)}. It was {q(old)}.")
                    + f" Say {q('forget ' + key)} to remove it.")
        return "memory-saved" if old is None else "memory-updated"

    def _memory_words(self, exc) -> str:
        """A note store refusal in plain words (the store's own text is technical)."""
        return "Please keep it short and plain, and try again."

    def _alias(self, msg, name, ident) -> str:
        """`alias <name>: <id>` saves memory alias.<slug> = product:<id> | maker:<key>, only if that record exists now."""
        key, found = "alias." + catalog._fold(name).replace(" ", "-"), []
        problem = ("A nickname needs to be short, with just letters, numbers and spaces." if not memory_mod._clean(name)
                   or len(name) > ALIAS_NAME_MAX or not memory_mod.KEY_RE.fullmatch(key[6:]) or not memory_mod.KEY_RE.fullmatch(key)
                   else "Which product or maker is it for? Say it like " + q("alias jam: Linn's blueberry preserves") + "." if not ident else None)
        typed = ident
        try:  # the current catalog, read from the writer worktree as _hike_lines does
            content = None if problem else load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            if content is not None:
                ident = self._pick("product", ident, content)
                if not any(p["id"] == ident for p in content.products) and ident not in content.makers: ident = self._pick("maker", typed, content)
            found = [] if problem else [("product", p, p["status"]) for p in content.products if p["id"] == ident] + (
                [("maker", m, "hidden" if m.get("hidden") else "visible")] if (m := content.makers.get(ident)) else [])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            problem = CANT_READ
        problem = problem or (f"I don't know a product or maker called {q(typed)}. Try {q('find')} and a word from its name." if not found
                              else f"{q(typed)} fits both a product and a maker. Could you say a bit more of the name?" if len(found) > 1 else None)
        if problem:
            self._problem("could-not-do", "nickname-refused")
            self._reply(f"I couldn't save that. {problem}" if not problem.startswith(("Which", "I ", "A nick")) and CANT_READ not in problem else problem)
            return "memory-invalid"
        old, value, source = self.memory.get(key), f"{found[0][0]}:{ident}", f"owner-stated:{msg.provider_id}"
        try: self.memory.remember(key, value, "fact", source) if old is None else self.memory.correct(key, value, source)
        except ValueError:
            self._problem("could-not-do", "nickname-refused")
            self._reply("I couldn't save that nickname. Could you try a shorter one?")
            return "memory-invalid"
        kind, rec, status = found[0]
        target = f"{q(rec['name'])}" + ("" if status in ("active", "visible") else f" ({STATUS_PLAIN.get(status, status)})")
        self._reply((f"Saved. {q(name)} now means " if old is None else f"Updated. {q(name)} now means ") + f"{target}."
                    + f" Say {q('forget alias ' + name)} to remove it.")
        return "memory-saved" if old is None else "memory-updated"

    def _alias_lines(self, rows) -> list:
        """AV0222-05: one line per alias row: name -> target name (id), [hidden]/[held], or what is wrong with it.
        The catalog is read once, only when there is a line to show; never echoes unsafe stored or catalog text."""
        def safe(text):
            problems = []
            checked_text(problems, "x", text)
            return isinstance(text, str) and not problems
        parsed = []
        for r in rows:
            slug = r["key"][6:]
            kind, colon, ident = str(r["value"]).partition(":")
            ok = bool(colon) and kind in ("product", "maker") and bool(ident) and len(ident) <= 80 and safe(ident)
            parsed.append((slug, kind, ident, ok))
        records = None
        if any(ok for *_, ok in parsed):
            try:
                content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                records = {"product": {p["id"]: (p["name"], p["status"]) for p in content.products},
                           "maker": {k: (m["name"], "hidden" if m.get("hidden") else "visible") for k, m in content.makers.items()}}
            except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
                records = None
        lines = []
        for slug, kind, ident, ok in parsed:
            name = slug.replace("-", " ")
            if not ok:
                lines.append(f"- {q(name)}: I can't read this one. Say {q('forget alias ' + name)} to remove it.")
            elif records is None:
                lines.append(f"- {q(name)}: I can't look up what it means right now.")
            elif (found := records[kind].get(ident)) is None:
                lines.append(f"- {q(name)}: it points to something that is no longer on the website. Say {q('forget alias ' + name)} to remove it.")
            elif not safe(found[0]):
                lines.append(f"- {q(name)}: I can't show what it means right now.")
            else:
                mark = " (hidden)" if found[1] == "hidden" else " (on hold)" if found[1] == "held" else ""
                lines.append(f"- {q(name)} means {q(found[0])}{mark}")
        return lines

    def _costs(self) -> str:
        """AV2137-06 (F03/H15): the saved purchase costs, newest saved first, read-only. Rows are read straight from an existing
        memory table (none is made to answer it); the each figure is margins.compute's unit_cost, never worked out here. A row
        that cannot be read stays in the list, counted and marked, and is never repaired or echoed."""
        try:
            has_table = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            rows = self.db.execute(f"SELECT key, value, created_at FROM memory WHERE {memory_mod.ACTIVE} AND substr(key, 1, 5) = 'cost.'").fetchall() if has_table else []
        except sqlite3.Error:
            self._reply(COSTS_UNAVAILABLE)
            return "costs"
        if not rows:
            self._reply("No purchase costs saved.")
            return "costs"

        def when(raw):  # (the stored instant, its Pacific time), or None for a missing, naive or impossible date
            try:
                at = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw)
                if at.tzinfo is None or at.utcoffset() is None: return None
                return at.astimezone(timezone.utc), at.astimezone(LOCAL_TZ)
            except (ValueError, TypeError, AttributeError, OverflowError, OSError): return None
        dated = [(r, when(r["created_at"])) for r in sorted(rows, key=lambda r: str(r["key"]))]  # by key first: the sort below is stable
        shown = (sorted((d for d in dated if d[1]), key=lambda d: d[1][0], reverse=True) + [d for d in dated if not d[1]])[:COSTS_LIST_MAX]
        records, products = False, {}
        if any(self._cost_parts(d[0]) for d in shown):
            try:
                content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                products, records = {p["id"]: (p["name"], p["status"]) for p in content.products}, True
            except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState): pass
        lines, lookup_failed = [], False
        for row, at in shown:
            parts, ident = self._cost_parts(row), str(row["key"])[5:]
            if parts is None:
                lines.append(f"{q(ident)}: I can't read this saved cost. Send {q('forget cost.' + ident)} to remove it."
                             if self._safe_text(ident) and memory_mod.KEY_RE.fullmatch(str(row["key"])) else "One saved cost has a name I can't show, so I can't read it.")
                continue
            found = products.get(ident)
            if not records or (found is not None and not self._safe_text(found[0])):
                label, lookup_failed = f"Product name unavailable ({q(ident)})", True
            elif found is None: label = f"Product no longer listed ({q(ident)})"
            else: label = f"{q(found[0])} ({q(ident)})" + (" (hidden)" if found[1] == "hidden" else " (held)" if found[1] == "held" else "")
            day = f"saved {_DAYS[at[1].weekday()]} {_MONTHS[at[1].month - 1]} {at[1].day}" if at else "saved date unavailable"
            lines.append(f"{label}: ${parts[0]} for {parts[1]} = ${parts[2]} each, {day}")
        if len(rows) > COSTS_LIST_MAX: lines.append(f"... and {len(rows) - COSTS_LIST_MAX} more")
        if lookup_failed: lines.append(COSTS_NO_NAMES)
        self._reply("\n".join(lines), long_ok=True)
        return "costs"

    @staticmethod
    def _safe_text(text) -> bool:
        problems = []
        checked_text(problems, "x", text)
        return isinstance(text, str) and not problems

    @staticmethod
    def _cost_parts(row):
        """(pack cost, units, each) as margins.compute returns them for the saved `<pack> for <units>`, or None when the row is
        not one: a key memory would not have kept, a value not in that form, or numbers the calculator refuses."""
        try:
            pack, sep, units = str(row["value"]).partition(" for ")
            if not sep or not memory_mod.KEY_RE.fullmatch(str(row["key"])): return None
            out = margins.compute(pack, units, "0", "0")
            return out["inputs"]["pack_cost"], out["inputs"]["units"], out["unit_cost"]
        except (margins.InputError, ArithmeticError, ValueError, TypeError, KeyError, AttributeError): return None

    def aliases(self) -> dict:
        """Read-only H15 aliases {name: (kind, id)} from active memory rows, for catalog.lookup(aliases=…)."""
        if self.memory is None: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        rows = [(r["key"][6:], r["value"].partition(":")) for r in self.memory.list() if r["key"].startswith("alias.")]
        return {slug.replace("-", " "): (kind, ident) for slug, (kind, colon, ident) in rows
                if colon and kind in ("product", "maker")}

    def _control(self, msg, now, verb) -> str:
        since = self._paused()
        if verb == "status":
            self._reply(self._status(now, since), long_ok=True)
        elif verb == "pause" and since:
            self._reply(answers.stopped_state(since, self._queue(msg)))
        elif verb == "pause":
            self.db.execute(CONTROL)
            self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('paused', '1', ?, ?)",
                            (_iso(now), msg.provider_id))
            self._reply(answers.stopped_state(_iso(now), self._queue(msg)))
        elif not since:
            self._reply("Changes are already on.")
        else:  # resume never applies anything by itself
            self.db.execute("DELETE FROM control WHERE name = 'paused'")
            codes = [r["code"] for r in self._drafts("state = 'proposed'") if self._visible(r)]
            self._reply("Changes are back on." + ("\nWaiting for your yes:\n" + self._choices(codes) if len(codes) > 1 else
                                                    f"\nOne change is waiting. Reply {q('yes ' + codes[0])} to save it." if codes else ""), long_ok=True)
        return verb

    def _status(self, now, since) -> str:
        """Read-only: pause state, waiting drafts, the last apply result and confirmed guests of upcoming hikes."""
        reader = self._reader_failed_lines(now)
        lines = [f"Changes are paused since {self._when(since)}. Say {q('resume changes')} when you're ready." if since
                 else "I'm having trouble reading your messages." if reader else "Everything is ready."]
        if (cap := self.settings["interpreterDailyCap"]) is not None and self._calls(now)[1] >= 0.8 * cap:  # H22, only near the cap
            lines.append("I'm close to the number of new requests I can read today.")
        waiting = self._waiting_lines(now)
        lines += waiting or [NOTHING]
        lines += [f"Waiting for your answer: {ask}"] if (ask := self._legacy_question(now)) else []  # AV2007-14
        with contextlib.suppress(OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            f = shelf.facts(load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content"), shelf.shop_today(now))
            lines.append(shelf.check_line(f))  # AV1102-05
            lines += [shelf.count_line(f)] if f["checked_on"] is not None else []  # AV1922-02: the word counts, after the shelf line
        lines += [line] if (line := self._notice_line(now)) else []  # AV1937-07: the home notice, once, after the shelf check
        lines += reader
        if self.skills_mode != dispatch_mod.DEFAULT_MODE:  # SKILLS-FW-3: one plain line per open request
            lines += self.requests.status_lines(self._chat(), now, self.dispatch.registry if self.dispatch else None)
        lines += self._photo_lines(now)  # NB-AV-12: counts only, before Last change
        last = self.db.execute(  # the most recently approved change that has a result
            "SELECT d.* FROM drafts d JOIN approvals a ON a.change_id = d.change_id WHERE d.state IN"
            " ('applied', 'verified', 'failed', 'reverted') ORDER BY a.id DESC, d.row_id DESC LIMIT 1").fetchone()
        if last:  # SHOP-4: did it work, in plain words (whether it is on the website now), never the commit
            whose = " (" + self._whose(last["chat"], False) + ")" if self._shared and not self._mine(last) else ""  # HASS-OWNERS-2
            lines.append(f"Last change{whose}: {q(last['summary'])}. " + answers.did_it_work(dict(last), self._install(last), now))
        return "\n".join(lines + self._hike_lines(now))

    def _reader_failed_lines(self, now) -> list:
        """AV1052-10: the last request was not read because the reader failed; read-only, never raises."""
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'control'").fetchone():
            return []
        row = self.db.execute("SELECT set_at, value FROM control WHERE name = 'reader-failed'").fetchone()
        if not row: return []
        try:
            when = voice.natural(datetime.fromisoformat(row["set_at"]), now)
        except (ValueError, TypeError, OverflowError, OSError):
            when = "a time I can't read"
        draft = row["value"] != "1" and self._by_code(row["value"], ("needs-details",))  # a photo caption
        if draft and self._expiry(draft) > now:  # resending the photo is a duplicate while its draft is open
            return [f"I couldn't read your request from {when}. I'm keeping the photo, so just reply with the product and what the photo shows."]
        if draft:  # the draft lapsed (status does not sweep it): a reply would find nothing, so the photo goes again
            return [f"I couldn't read your request from {when}, and the photo's time ran out. Please send the photo again with its caption."]
        return [f"I couldn't read your request from {when}. Could you send it again?"]

    def _waiting_lines(self, now) -> list:
        """AV1102-11: one line per unexpired draft waiting for yes or for details; `status` and `report` share it."""
        rows = [r for r in self._drafts("state IN ('proposed', 'needs-details')") if self._expiry(r) > now]
        lines = [f"Waiting for your yes: {q(r['summary'])} (reply {q('yes ' + r['code'])})" if r["state"] == "proposed"
                 else "I'm waiting for details: " + r["summary"] for r in rows if self._visible(r)]
        for chat in dict.fromkeys(r["chat"] for r in rows if not self._visible(r)):  # HASS-OWNERS-2: another owner's change: said, never shown
            lines.append(f"{self._who(chat)[0].upper() + self._who(chat)[1:]} has a change waiting.")
        return lines

    def _photo_lines(self, now) -> list:
        """NB-AV-12: waiting photo drafts (every op a photo op: AV1937-01 adds product.add and the home photo, each with a photo)
        and pending inbox messages with tries > 0.
        The inbox is opened read-only (never created); no file or no tries column means no line."""
        def photo_only(raw):
            try: ops = json.loads(raw)
            except (TypeError, ValueError): return False
            return isinstance(ops, list) and bool(ops) and all(
                isinstance(c, dict) and c.get("op") in ("product.set_photo", "product.add", "store.set_home_image")
                and isinstance(c.get("args"), dict) and isinstance(c["args"].get("photo"), str) and c["args"]["photo"] != ""
                for c in ops)
        n = sum(self._expiry(r) > now and photo_only(r["ops_json"]) for r in self._drafts("state = 'needs-details'") if self._visible(r))
        lines, path = [f"{'A photo is' if n == 1 else 'Some photos are'} waiting for details from you."] if n else [], self.sdir / "inbox.sqlite3"
        if not path.is_file(): return lines
        try:
            with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True, timeout=1)) as db:
                if "tries" not in {r[1] for r in db.execute("PRAGMA table_info(inbound)")}: return lines
                m = db.execute("SELECT COUNT(*) FROM inbound WHERE state = 'pending' AND tries > 0").fetchone()[0]
        except sqlite3.Error:
            return lines + ["I can't tell whether any photos are still coming in."]
        return lines + ([f"{'A photo is' if m == 1 else 'Some photos are'} still coming in."] if m else [])

    def _hike_lines(self, now) -> list:
        """Scheduled hikes after now with seat totals only (never names or emails); unknown counts are never guessed.
        AV1537-07: then scheduled hikes whose start has passed (oldest first, at most 5, no guest counts)."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            events = json.loads((wt / "hass" / "content" / "community.json").read_text("utf-8"))["events"]
            scheduled = sorted(((datetime.fromisoformat(e["startsAt"]), e) for e in events
                                if e.get("status") == "scheduled"), key=lambda pair: pair[0])
            upcoming = [e for start, e in scheduled if start > now]
            passed = [e for start, e in scheduled if start <= now]  # the site hides these too (`>` rule)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, editor_mod.UnsafeState):
            return ["I can't read the hike list right now."]
        path, counts = self.settings.get("guestCountsDb"), None
        if any(e.get("rsvpEnabled") for e in upcoming) and isinstance(path, str) and path:  # RSVP-off only: never opened
            try:
                counts = hikes.guest_counts(path)
            except (sqlite3.Error, OSError, ValueError, TypeError):
                counts = None
        lines = []
        for e in upcoming:
            head = f"{q(e.get('title'))}, {voice.natural_iso(e['startsAt'], now)}: "
            limit = e.get("capacity")
            n = counts.get(e.get("id"), 0) if counts is not None else 0
            lines.append(head + ("sign-ups are off" if not e.get("rsvpEnabled") else "I can't see how many guests have signed up" if counts is None
                                 else f"{n} {'guest has' if n == 1 else 'guests have'} signed up" + (f", with room for {limit}" if limit is not None else "")))
        for e in passed[:5]:
            title = e.get("title")
            lines.append(f"{q(title)} was {voice.natural_iso(e['startsAt'], now)} and is still listed as coming up. "
                         "Tell me if it happened or was cancelled.")
        if len(passed) > 5:
            lines.append("A few more past hikes are still listed as coming up.")
        return lines
