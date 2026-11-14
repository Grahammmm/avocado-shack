"""Reports pack: `report`, `margin`, `cost` and `post` (Conversation mixin).

AVB-12: moved verbatim out of hass/conversation.py, which imports every name back (hass.conversation.<name> is
unchanged). The methods run on the Conversation (self is the conversation): they use its store, replies and
settings exactly as before. Command routing stays in Conversation._command.
"""
import os, re, stat  # noqa: E401
from datetime import datetime

from hass import editor as editor_mod, margins, memory as memory_mod, morning_report, social_draft, voice
from hass.chat.shared import CANT_READ, CONTROL, COST_USAGE, _iso, load_content, LOCAL_TZ, q, SHELF_ASK
from hass.content_model import ContentError, load_and_validate, shop_today
from hass.ops import catalog

POST_USAGE = "Which product is the post for? Say it like " + q("post Hass avocado") + "."  # AV1322-07
HIKE_USAGE = "Which hike is the post for? Say it like " + q("post hike Point Buchon") + "."  # AV1222-11
HIKE_REFUSALS = {"no such hike": "I don't know a hike called {id}. Try " + q("find") + " and a word from its name.",
                 "hike is cancelled": "{id} is cancelled, so there is nothing to announce.",
                 "hike already happened": "{id} has already happened.", "not scheduled": "{id} isn't scheduled yet."}  # other reasons: POST_CANT
POST_REFUSALS = {"no such product": "I don't know a product called {id}. Try " + q("find") + " and a word from its name.",
                 "not on the site": "{id} isn't on the website right now.",
                 "no photo on the site": "{id} has no photo on the website yet, so I can't make a post for it."}  # other reasons: POST_CANT
POST_CANT = "I can't make a post for {id} right now. Nothing was posted."
_NUM = r"[-+]?[0-9.][0-9.,_]*(?:e[-+]?[0-9]+)?"  # AV1102-12: looks like a number; margins.compute is the only validator
MARGIN_RE = re.compile(rf"\$?({_NUM})\s+for\s+({_NUM})\s+at\s+({_NUM})\s*%(?:\s+shrink\s+({_NUM})\s*%)?")
MARGIN_ID_RE = re.compile(rf"(?!\$?{_NUM}\s+for\s)(\S.*?)\s+at\s+({_NUM})\s*%(?:\s+shrink\s+({_NUM})\s*%)?")  # AV1222-10: saved cost
COST_RE = re.compile(r"\$?(\S+)\s+for\s+(\S+)", re.IGNORECASE)  # AV1222-10: margins.compute is the only number validator

MARGIN_USAGE = "Tell me what you pay for a pack, how many are in it and the margin you want, like " + q("margin 24 for 12 at 35%") + "."


class ReportsPack:
    """Reports pack commands, mixed into Conversation."""

    def _report(self, msg, now) -> str:
        """AV1322-05 (F04): the morning shelf report from the writer worktree content, Pacific today; read-only for the site.
        HASS-SHELFCHECK-FLOW-1: when today's shelf check is missing, the first report of the day also asks the owner
        SHELF_ASK (a yes then drafts the check; nothing is written by asking)."""
        ask = False
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            facts = morning_report.facts(content, shop_today(now))
            text = morning_report.render(facts)
            ask = facts["checked_on"] != shop_today(now).isoformat() and not facts["future"] and self._report_asked(msg, now)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "report-unreadable")
            text = "I can't read the shelf report right now, so I can't tell you what's on the shelves. Nothing has changed."
        waiting = self._waiting_lines(now) + [l for l in self._photo_lines(now) if "waiting for details" in l]
        self._reply(f"{text}\n\n" + "\n".join(["Waiting for you:"] + waiting if waiting else ["Nothing is waiting for you."])
                    + (f"\n\n{SHELF_ASK}" if ask else ""), long_ok=True)
        return "report"

    def _report_asked(self, msg, now) -> bool:
        """HASS-SHELFCHECK-FLOW-1: True the first time today that the report asks SHELF_ASK (and keeps it open); once a day."""
        day = shop_today(now).isoformat()
        self.db.execute(CONTROL)
        if (row := self.db.execute("SELECT value FROM control WHERE name = 'shelf-asked'").fetchone()) and row["value"] == day: return False
        self.db.execute("INSERT INTO control(name, value, set_at, provider_id) VALUES ('shelf-asked', ?, ?, ?)"
                        " ON CONFLICT(name) DO UPDATE SET value = excluded.value, set_at = excluded.set_at,"
                        " provider_id = excluded.provider_id", (day, _iso(now), msg.provider_id))
        self._open_ask(msg, now, [], {"ops": [], "revises": None})
        return True

    def _margin(self, rest) -> str:
        """AV1102-12 (F03): margins.render for one purchase line, text in and text out. Read-only: nothing is stored or
        drafted, no interpreter call or usage count; works while paused."""
        found = MARGIN_RE.fullmatch(rest)
        by_id = None if found else MARGIN_ID_RE.fullmatch(rest.strip())  # AV1222-10: the saved cost of a product (by name or id)
        try:
            text = margins.say(margins.compute(found[1], found[2], found[4] or "0", found[3])) if found else \
                self._margin_saved(*by_id.groups()) if by_id else MARGIN_USAGE
        except margins.InputError as exc:
            self._problem("did-not-understand", "margin-numbers")
            text = "I couldn't work that out. " + margins.plain_input_error(exc)
        self._reply(text)
        return "margin"

    def _margin_saved(self, ident, margin, shrink) -> str:
        """AV1222-10: margins for the saved cost.<id> (read-only; the memory table is not created for a read)."""
        has_table = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
        if self.memory is None and has_table: self.memory = memory_mod.Memory.on_connection(self.db, self.clock)
        typed, ident = ident, self._pick("product", ident)
        row = next((r for r in self.memory.list() if r["key"] == f"cost.{ident}"), None) if has_table else None
        if row is None: return f"I don't have a cost saved for {q(typed)}. Tell me first, like " + q(f"cost {typed}: 24 for 12") + "."
        pack, _, units = row["value"].partition(" for ")
        since = datetime.fromisoformat(row["created_at"]).astimezone(LOCAL_TZ)
        return f"Using the cost you gave me {voice.natural(since, self._now())}.\n" + margins.say(margins.compute(pack, units, shrink or "0", margin))

    def _post_names_something(self, text) -> bool:
        """HASS-VOICE-1: post takes a name, so several words only count as the post command when they point at one product
        or hike; anything else keeps going to the interpreter as before. Unreadable content counts as a name so the usual
        'can't read' answer follows."""
        try:
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return True
        words = text.split()
        if words[0].lower() == "hike" and len(words) == 2: return True  # one id after 'hike': the usual 'I don't know a hike' answer
        if words[0].lower() == "hike": return self._pick_hike(content, text[4:].strip()) != text[4:].strip()
        return self._pick("product", text, content) != text

    def _post(self, pid) -> str:
        """AV1322-07 (F07 prepare half): social_draft's caption for one active product plus its site photo, from the
        writer worktree content. Read-only: nothing is posted, scheduled, written or drafted; works while paused."""
        photo = None
        if pid.lower().split(None, 1)[:1] == ["hike"]: return self._post_hike(pid[4:].strip())
        try:
            if not pid: raise LookupError
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            out = social_draft.build(content, self._pick("product", pid, content), wt / "storefront-mockup")
            if out["draft"] and stat.S_ISREG(os.lstat(photo := wt / "storefront-mockup" / out["image"]).st_mode):
                text = f"Here's a post you can copy. I haven't posted anything.\n{q(out['caption'])}\nWhat the photo shows: {q(out['alt'])}"
            else:  # a refusal, or a photo that is itself a link: never attached
                reason = out.get("reason", "no photo on the site")
                text = POST_REFUSALS[reason].format(id=q(pid)) if reason in POST_REFUSALS else POST_CANT.format(id=q(pid))
                if reason not in POST_REFUSALS: self._problem("could-not-do", "post-refused")
                photo = None
                if reason == "cannot read content": raise OSError
        except LookupError:
            text = POST_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text, photo = CANT_READ, None
        self._reply(text, [str(photo)] if photo else [], long_ok=True)
        return "post"

    def _post_hike(self, hid) -> str:
        """AV1222-11 (F07): social_draft.build_hike's caption for one scheduled upcoming hike. Read-only, nothing is stored."""
        try:
            if not hid: raise LookupError
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            out = social_draft.build_hike(content, self._pick_hike(content, hid), self._now())
            if out["draft"]: text = f"Here's a post you can copy. I haven't posted anything.\n{q(out['caption'])}"
            elif out["reason"] == "cannot read content": raise OSError
            else:
                text = HIKE_REFUSALS[out["reason"]].format(id=q(hid)) if out["reason"] in HIKE_REFUSALS else POST_CANT.format(id=q(hid))
                if out["reason"] not in HIKE_REFUSALS: self._problem("could-not-do", "post-refused")
        except LookupError: text = HIKE_USAGE
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text = CANT_READ
        self._reply(text, long_ok=True)
        return "post"

    def _pick(self, kind, text, content=None) -> str:
        """The id for what Mike typed: an exact id or maker key as before, else the one record whose name or nickname fits
        (catalog.lookup); anything else comes back unchanged so the usual 'I don't know that one' answer follows."""
        try:
            content = content or load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            ids = {p["id"] for p in content.products} if kind == "product" else set(content.makers)
            if text in ids: return text
            has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            found = catalog.lookup(content, kind, text, aliases=self.aliases() if has_memory else None)
            matched = found.get("match")
            # Maker keys keep their exact case; only names and nicknames are folded.
            if kind == "maker" and isinstance(matched, str) and not found.get("via") \
                    and catalog._fold(text) not in catalog._fold(content.makers[matched]["name"]):
                return text
            return matched if isinstance(matched, str) else text
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return text

    def _pick_hike(self, content, text, key="events") -> str:
        """A hike's (or, with key="routeIdeas", a route idea's) id from what Mike typed: an exact id, else the one whose
        title holds every word."""
        events = content.community.get(key) if isinstance(content.community, dict) else None
        events = [e for e in events if isinstance(e, dict)] if isinstance(events, list) else []
        if any(e.get("id") == text for e in events): return text
        words = catalog._fold(text).split()
        hits = [e for e in events if words and isinstance(e.get("title"), str) and all(w in catalog._fold(e["title"]) for w in words)]
        return hits[0]["id"] if len(hits) == 1 and isinstance(hits[0].get("id"), str) else text

    def _cost(self, msg, ident, rest) -> str:
        """AV1222-10 (F03): `cost <id>: <pack> for <units>` saves memory cost.<id> = "<pack> for <units>" (the dated,
        owner-stated, private purchase cost for an existing product, any status). Never the site or the interpreter."""
        typed, product, problem, value = ident, None, None, ""
        found = COST_RE.fullmatch(rest)
        try:
            if not found or not ident: problem = COST_USAGE
            else:
                shown = margins.compute(found[1], found[2], "0", "0")["inputs"]  # validates and normalises both numbers
                value = f"{shown['pack_cost']} for {shown['units']}"
                content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
                ident = self._pick("product", ident, content)
                product = next((p for p in content.products if p["id"] == ident), None)
                problem = None if product else f"I don't know a product called {q(typed)}. Try {q('find')} and a word from its name."
        except margins.InputError as exc:
            problem = "I couldn't read those numbers. " + margins.plain_input_error(exc)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            problem = CANT_READ
        key, old, source = f"cost.{ident}", None, f"owner-stated:{msg.provider_id}"
        try:
            old = self.memory.get(key) if product else None
            if product and old == value:
                self._reply(f"I already have that cost for {q(product['name'])}, so nothing changed.")
                return "memory-unchanged"
            if product: self.memory.remember(key, value, "fact", source) if old is None else self.memory.correct(key, value, source)
        except ValueError:  # e.g. an id too long for a memory key
            problem = "I couldn't keep that one. Could you say it another way?"
        if problem:
            self._problem("could-not-do", "cost-refused")
            self._reply(f"I couldn't save that. {problem}" if not problem.startswith(("Tell me", "I ")) else problem)
            return "memory-invalid"
        pack, _, units = value.partition(" for ")
        self._reply((f"Saved. {q(product['name'])} costs you {pack} for {units}." if old is None else
                     f"Updated. {q(product['name'])} now costs you {pack} for {units}.")
                    + f" That stays private and is never on the website. Say {q('forget cost.' + ident)} to remove it.")
        return "memory-saved" if old is None else "memory-updated"
