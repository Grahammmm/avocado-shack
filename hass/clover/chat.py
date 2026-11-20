"""HASS-CLOVER-2: the owner's till questions in the chat, answered from the PRIVATE cache only (never a live call, never a model).

Three reads: "how many <item> do we have", "low stock", "is <item> in stock". Answers come from hass/clover/reads.py templates with the
voice rules there: plain words, the count as the till has it; older than 20 minutes says "as of <time>"; when the last pull failed it
starts "I can't reach the till right now"; nothing is quoted from a pull over 24 hours old. There are NO writes: any request to add or
change a till item, a count or a price gets WRITE_REPLY (writes come later, behind a separate approval and a write token).

The desk exists only when host.json has a `clover` block (hass/host.py make_worker). Without one, the conversation never calls it and
nothing changes. A question about something else (a hike, sign-ups, the website, drafts, ...) is not claimed: `parse` returns None and
the message goes on to the usual handling. "how many <x>" / "is <x> in stock" are claimed only when they use stock words or <x> names
a till item.
"""
import json, re, secrets  # noqa: E401
from dataclasses import replace
from decimal import Decimal

from hass import voice
from hass.clover import cache, drafts as d, links as linkmod, reads, reports
from hass.clover.apply import ApplyEngine
from hass.clover.config import from_settings
from hass.clover.mapper import (CATEGORIES, MapError, cents_from_text, format_money, norm_name, parse_item, parse_items,
                                parse_site_product, resolve_exact)

WRITE_REPLY = "I can read the till but I can't change it yet."
# HASS-CLOVER-4: the owner's till changes by fixed words (docs/hass/CLOVER.md section 5), tried only with a write engine attached.
TILL_WRITES = (("received", re.compile(r"(?:we )?received (?P<n>\d+(?:\.\d+)?) (?:of )?(?P<q>.+)", re.I)),
               ("price", re.compile(r"change (?:the )?price (?:of|for) (?P<q>.+?) to (?P<n>\$?[\d,]+(?:\.\d+)?)", re.I)),
               ("set", re.compile(r"set (?!(?:the )?price\b)(?:the count of )?(?P<q>.+?) to (?P<n>\d+(?:\.\d+)?)", re.I)),
               ("sold_out", re.compile(r"(?P<q>.+?) (?:is |are )?(?:now )?sold out", re.I)),
               ("new", re.compile(r"new (?:till )?item ?: ?(?P<q>.+)", re.I)),
               ("hide", re.compile(r"(?P<v>hide|show) (?P<q>.+?) on the till", re.I)))
CODED, SITE_OPS = re.compile(r"(yes|no|undo) ([0-9a-f]{8})"), frozenset({"product.set_availability", "product.clear_availability"})
HOW = "I change the till only with a few fixed sentences, like " + voice.quote("set Sunshine olive oil to 7") + ". Say help to see them all."
NOT_OWNER = "I only change the till for the owner, in his own chat. Nothing was changed."
TILL_DOWN, SITE_UNKNOWN = "I can't reach the till, so nothing was changed.", "I couldn't check the website for that item, so nothing was prepared."
NOT_DONE = {"failed": "I sent that to the till, but when I read it back it did not show the change. I stopped there; nothing else was changed.",
            "uncertain": "I couldn't tell whether the till took that change. I won't send it again; please check that item on the till."}
SITE_NOT_YET = "The till is updated; the website is not yet. Tell me again if the website still needs it."
SITE_MOVED = ("The website word for that item changed after you were shown this change, so I changed nothing on the till or the website and "
              "kept the newer word. Send the change again if it is still needed.")
HELP = "Till (each needs your yes and its code): " + "; ".join(map(voice.quote, (
    "received 12 Sunshine olive oil", "set Sunshine olive oil to 7", "Sunshine olive oil is sold out", "new item: Sunshine olive oil, 12.50, pantry",
    "change price of Sunshine olive oil to 14.00", "hide Sunshine olive oil on the till", "show Sunshine olive oil on the till", "undo <code>"))) + "." \
       + " Website links (owner only): " + "; ".join(map(voice.quote, ("link all <code>", "link Sunshine olive oil to <SKU>", "unlink Sunshine olive oil",
                                                                       "stock yes <code>", "stock no <code>"))) + "."
LINKS = re.compile(r"(?:link all (?P<all>\S+)|link (?P<x>.+) to (?P<sku>\S+)|unlink (?P<u>.+)|stock (?P<w>yes|no) (?P<c>\S+))")
LINK_NO = {"unknown": "I have no waiting link list with that code, so nothing was linked.",
           "stale": "The till or the website changed after that link list was made, so nothing was linked. The list has to be made again."}
STOCK_NO = "That stock code is not waiting for you, so nothing was changed."


class BundleEngine(ApplyEngine):
    """HASS-CLOVER-4: CLOVER-3's engine plus a website word riding on a count (to 0, or up from 0): never a till field, never read back."""

    def offer(self, draft, *, sender, chat):
        if (sender, chat) not in self.owners or ";+;" in chat or any(o.get("op") not in SITE_OPS for o in draft.site_ops):
            raise d.DraftRefused(NOT_OWNER)
        if draft.kind == "set_hidden":   # wording only (not hashed): drafts.build_set_hidden states the 'before' backwards
            w = ("showing", "hidden")
            draft = replace(draft, lines=(draft.lines[0], f"  On the till: {w[draft.before['hidden']]} -> {w[draft.after['hidden']]}", *draft.lines[2:]))
        with self.journal.locked() as db:
            self._gate(db, draft.undo_of)
            code = secrets.token_hex(4)
            db.execute("INSERT INTO changes VALUES(?,?,?,?,?,'draft',NULL,NULL)", (code, json.dumps(draft.to_dict()), sender, chat, self.clock() + 600))
        return code, draft.render(code)

    _matches = staticmethod(lambda entry, raw: ApplyEngine._matches({**entry, "after": {k: v for k, v in entry["after"].items() if k != "site"}}, raw))

    def undo(self, code, *, sender, chat, site=lambda item_id: None):
        with self.journal.locked() as db:   # CLOVER-3's undo, given the linked website product so its word goes back too
            row = db.execute("SELECT result FROM changes WHERE code=? AND status='applied' AND sender=? AND chat=?", (code, sender, chat)).fetchone()
            if not row:
                raise d.DraftRefused("That code is not a till change I made, so there is nothing to undo.")
            e = json.loads(row[0])
            draft = d.build_undo(e, parse_item(self._client().get_item(e["result_item_id"])), self.config, site_product=site(e["result_item_id"]))
        return self.offer(draft, sender=sender, chat=chat)


NEVER_READ = "I haven't been able to read the till yet, so I don't have a count to give you. Ask me again in a little while."
DOWN_NO_DATA = "I can't reach the till right now, so I don't have a count to give you."

OTHER = re.compile(r"\b(?:hikes?|hiking|walks?|trails?|sign(?:ed|ing)?[ -]?ups?|rsvps?|people|guests?|spots?|seats?|messages?|texts?|drafts?|"
                   r"changes?|photos?|pictures?|website|web site|site|pages?|makers?|notes?|codes?|days?|times?|hours?|minutes?)\b")
STOCKISH = re.compile(r"\b(?:do we have|have we got|we got|left|in stock|on hand|in the till|on the till|sold out)\b")
LOW = re.compile(r"(?:(?:what(?:'s| is| are) )?(?:the )?|(?:show|tell|give) (?:me )?(?:the )?|any |anything )?"
                 r"(?:low stock|low-stock|stock (?:is )?low|running low|low on stock)(?: items| list| report| in the till)?"
                 r"|what(?:'s| is) (?:low|running low|sold out)(?: in the till)?"
                 r"|what are we (?:low on|running low on|out of|sold out of)"
                 r"|are we (?:low|running low|out) (?:on|of) anything"
                 r"|(?:is )?anything (?:low|running low|sold out)")
HOW_MANY = re.compile(r"how (?:many|much) (?P<q>.+?)(?: (?:do we have(?: left)?|have we got(?: left)?|are there|are left|is left|left|in stock|"
                      r"on hand|in the till|on the till|we got|have we))?")
COUNT_OF = re.compile(r"(?:what(?:'s| is) (?:the )?)?(?:count|stock count|stock level|stock) (?:of|for|on) (?P<q>.+?)")
IN_STOCK = re.compile(r"(?:is|are) (?:there )?(?:any )?(?P<q>.+?) (?P<pred>in stock|sold out|left)(?: in the till| on the till)?"
                      r"|(?:do we have|have we got|we got) (?:any )?(?P<q2>.+?) (?:in stock|left)(?: in the till| on the till)?")
PRICE_WRITE = re.compile(r"\b(?:change|set|update|raise|lower|increase|decrease|drop|cut|bump|adjust|edit|fix|mark (?:up|down))\b(?: \S+){0,4}? prices?\b"
                         r"|\bprices? (?:of|for|on) .+? (?:to|=) ?\$?\d|\bnew prices?\b")
TILL_WRITE = re.compile(r"\b(?:add|put|create|change|update|set|edit|rename|remove|delete|hide|unhide|mark|enter|ring up)\b.*"
                        r"\b(?:the till|clover|cash register|pos|point of sale)\b")
STOCK_WRITE = re.compile(r"^(?:we )?received \d|^new (?:till )?item ?:|\bgive .+ an? sku\b"
                         r"|\b(?:set|change|update|fix|adjust) (?:the )?(?:count|stock count|stock level|quantity|inventory)\b"
                         r"|\b(?:count|quantity|inventory) (?:of|for) .+ to \d")
SITE_WORDS = re.compile(r"\b(?:description|headline|website|web site|site|page|photo|picture|hikes?|makers?|notice|banner|specials?|post)\b")
VAGUE = frozenset({"is", "are", "was", "were", "it", "its", "that", "this", "they", "them", "does", "do", "did", "you", "we", "can", "will",
                   "would", "should", "much", "many", "more", "time", "long", "far", "cost", "costs", "price", "money"})


def _clean(text):
    t = (text or "").replace("\u2019", "'").replace("\u2018", "'").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return re.sub(r"[\s?.!]+$", "", t)


def _query(q):
    q = re.sub(r"^(?:the|any|some|our|of|of the) ", "", q.strip())
    return q.strip()


class TillDesk:
    """Reads the cache under `state`; holds no token and makes no network call (HASS-CLOVER-4 writes go through `engine` only)."""
    HELP, SITE_NOT_YET, SITE_MOVED = HELP, SITE_NOT_YET, SITE_MOVED

    def __init__(self, state, settings, read=cache.read, engine=None):
        self.state, self.config, self._read, self.engine = state, from_settings(settings), read, engine   # engine: a BundleEngine, or None (read-only)
        self.identity = cache.identity_of(self.config)   # only this till's cache is read (RETURN t_54d7c993)

    def __repr__(self):
        return "TillDesk(read-only)"

    def first(self, text, sender, chat):
        """Till words before the commands: (yes|no|undo, code) of this sender's till change here, or `show <item> on the till`."""
        t = _clean(text) if self.engine is not None else ""
        if t.startswith("show ") and t.endswith(" on the till"):
            return self._till_write(text)
        if m := CODED.fullmatch(t):
            with self.engine.journal.locked() as db:
                return (m[1], m[2]) if db.execute("SELECT 1 FROM changes WHERE code=? AND sender=? AND chat=?", (m[2], sender, chat)).fetchone() else None

    def parse(self, text):
        """("low",), ("how_many", query), ("in_stock", query), ("sold_out", query), ("write",) or None (not a till message).

        "is <x> sold out" is ("sold_out", query), never ("in_stock", query): its yes/no is the opposite of "is <x> in stock"."""
        t = _clean(text)
        if not t or len(t) > 200 or len((text or "").strip().splitlines()) > 1:   # any line boundary (CR, VT, FF, NEL, U+2028...), not just LF
            return None
        if self.engine is not None and (m := LINKS.fullmatch(t)) and (not m["sku"] or any(i.sku and i.sku.casefold() == m["sku"] for i in getattr(self._snapshot()[0], "items", ()))):
            # HASS-LINK: owners only (checked again in answer). `link X to Y` is claimed only when Y is exactly a till SKU: other talk of linking goes on as before
            return ("link", {"all": "all", "sku": "one", "u": "unlink", "c": m["w"]}[m.lastgroup], m["all"] or m["x"] or m["u"] or m["c"], m["sku"])
        if LOW.fullmatch(t):
            return ("low",)
        for pattern, kind in ((HOW_MANY, "how_many"), (COUNT_OF, "how_many"), (IN_STOCK, "in_stock")):
            m = pattern.fullmatch(t)
            if m:
                q = _query(m.group("q") or "") if "q2" not in m.re.groupindex else _query(m.group("q") or m.group("q2") or "")
                if "pred" in m.re.groupindex and m.group("pred") == "sold out":
                    kind = "sold_out"
                return self._claim(t, kind, q)
        if self.engine is not None and (till := self._till_write(text)):
            return till
        if not SITE_WORDS.search(t) and (PRICE_WRITE.search(t) or TILL_WRITE.search(t) or STOCK_WRITE.search(t)):
            return ("write",)
        return None

    def _till_write(self, text):
        """("till", kind, query, value) for a fixed sentence; `X is sold out` only when X is exactly a till item (else the site's words)."""
        o = re.sub(r"\s+", " ", (text or "").replace("\u2019", "'").strip()).rstrip(".!")
        for kind, pattern in TILL_WRITES:
            if m := pattern.fullmatch(o):
                q = _query(m["q"].lower()) if kind != "new" else m["q"].strip()
                if kind == "sold_out" and not ((snap := self._snapshot()[0]) is not None and reads.exact(q, snap)):
                    return None
                return ("till", kind, q, m["v"].lower() if kind == "hide" else m.groupdict().get("n"))

    def _claim(self, text, kind, query):
        if not query:
            return None
        snapshot, _ = self._snapshot()
        if snapshot is not None and reads.exact(query, snapshot):
            return (kind, query)          # an exact till item name wins, even "Trail mix"
        if OTHER.search(text) or all(w in VAGUE for w in query.split()):
            return None
        if STOCKISH.search(text):
            return (kind, query)
        if set(query.split()) & VAGUE or any(len(w) < 3 for w in query.split()):
            return None                   # "how much is it": a 'did you mean' on short or vague words is not a till question
        return (kind, query) if snapshot is not None and reads.names_something(query, snapshot) else None

    def _snapshot(self):
        """(snapshot or None, reachable) for the configured till only. A cache of another environment or merchant, or one with no
        identity, is refused by cache.read as (None, True), so the answer is NEVER_READ ("I haven't been able to read the till yet")."""
        try:
            return self._read(self.state, self.identity)
        except Exception:  # noqa: BLE001 - an unreadable cache is "can't reach the till", never a crash of the conversation
            return None, False

    def report(self, now, worktree):
        """G-only caller; freshly computed headline, never a file's arbitrary text."""
        from hass.clover import reports
        snapshot, reachable = self._snapshot()
        if snapshot is None:
            return NEVER_READ if reachable else DOWN_NO_DATA
        state, label = reads.freshness(snapshot, now, reachable)
        if state == "too-old":
            return label
        try:
            content, links = reports.read_inputs(self.state, worktree)
            return reports.headline(snapshot, content, links, now, self.config.low_stock_threshold, reachable)
        except Exception:  # no names, prices, paths or input exceptions in the reply
            return "I couldn't compare the till with the website. Nothing changed."

    def answer(self, intent, now, *, sender=None, chat=None, worktree=None):
        """The reply text for a parsed intent at `now` (timezone-aware). Till names and SKUs are quoted (shown as the till has them)."""
        if intent[0] == "write":
            return WRITE_REPLY if self.engine is None else HOW
        if intent[0] == "link":
            return voice.till(self._link(intent[1:], sender, chat, worktree))
        if intent[0] in ("till", "no", "undo", "yes"):
            return voice.till(self._change(intent, sender, chat, worktree))
        snapshot, reachable = self._snapshot()
        if snapshot is None:
            return NEVER_READ if reachable else DOWN_NO_DATA
        if intent[0] == "low":
            return reads.low_stock(snapshot, now, self.config.low_stock_threshold, reachable, show=voice.quote)
        if intent[0] == "in_stock":
            return reads.in_stock(intent[1], snapshot, now, reachable, show=voice.quote)
        if intent[0] == "sold_out":
            return reads.in_stock(intent[1], snapshot, now, reachable, show=voice.quote, sold_out=True)
        return reads.how_many(intent[1], snapshot, now, reachable, show=voice.quote)

    def _link(self, intent, sender, chat, worktree):
        """`link all <code>`, `link X to <SKU>`, `unlink X`, `stock yes|no <code>`: Mike only. Links never set a website word."""
        kind, a, b = intent
        if (sender, chat) not in self.engine.owners or ";+;" in chat:
            return NOT_OWNER
        if kind in ("yes", "no"):
            return self._stock(kind == "yes", a)
        try:
            snapshot, _ = self._snapshot()
            content, links = reports.read_inputs(self.state, worktree())
        except Exception:  # noqa: BLE001 - no worktree, or the website or the links cannot be read: nothing is linked
            return "I couldn't read the website items or the links, so nothing was changed."
        if snapshot is None:
            return NEVER_READ
        if kind == "all":
            status, n = linkmod.apply(self.state, a, snapshot, content, links)
            return f"Linked {n} website items to till items. No website word was changed." if status == "ok" else LINK_NO[status]
        pids = [p["id"] for p in content["products"] if p.get("status") == "active" and a in (p["id"].casefold(), norm_name(p["name"]))]
        if len(pids) != 1:
            return f"I couldn't find exactly one website item called {voice.quote(a)}, so nothing was changed."
        if kind == "unlink":
            if pids[0] not in links:
                return f"{voice.quote(a)} is not linked, so nothing was changed."
            linkmod.write(linkmod.table(self.state), {p: v for p, v in links.items() if p != pids[0]})
            return f"Unlinked {voice.quote(a)}. No website word was changed."
        items = [i for i in snapshot.items if i.sku and i.sku.casefold() == b.casefold()]
        if len(items) != 1 or pids[0] in links or items[0].id in linkmod.reserved(snapshot.items, links):
            return "That needs one website item and one till SKU, both not linked yet, so nothing was changed. Say unlink first to move a link."
        linkmod.write(linkmod.table(self.state), {**links, pids[0]: {"cloverId": items[0].id, "sku": items[0].sku}})
        return f"Linked {voice.quote(a)} to SKU {items[0].sku}. No website word was changed."

    def _stock(self, yes, code):
        """The website stock words waiting for his yes (STOCK-SITE): one approve or decline call, only for a code that is open now."""
        from hass import stock_site   # lazy: it pulls in the editor and the live policy
        try:
            waiting = stock_site.StockSite(self.state, None, None).load()["sets"].get(code)
        except Exception:  # noqa: BLE001 - an unreadable stock file is never guessed at
            return "I couldn't read the website stock list, so nothing was changed."
        if not waiting or waiting["state"] != "open" or (yes and waiting["approved_by"]):
            return STOCK_NO
        if not (stock_site.approve if yes else stock_site.decline)(self.state, code, "owner"):
            return "I couldn't record that just now, so nothing was changed. Please try again in a minute."
        return "Okay, those website stock words will go up with the next till reads." if yes else "Okay, I've dropped those website stock words. Nothing was changed on the website."

    def _change(self, intent, sender, chat, worktree):
        if intent[0] == "yes":   # only while paused; the real yes is `approve`
            return f"Changes are paused, so I haven't changed the till. Say resume changes, then reply yes {intent[1]}."
        if intent[0] == "no":
            self.drop(intent[1], sender, chat)
            return "Okay, I've cancelled that. Nothing changed on the till."
        try:
            if intent[0] == "undo":
                return self.engine.undo(intent[1], sender=sender, chat=chat, site=lambda iid: self._site(iid, worktree))[1]
            return self.engine.offer(self._draft(*intent[1:], worktree), sender=sender, chat=chat)[1]
        except MapError as exc:   # DraftRefused, NotExact, a bad price and SITE_UNKNOWN are plain sentences for the owner
            return str(exc)
        except Exception:  # noqa: BLE001 - the till could not be read or the token is not usable: nothing is drafted
            return TILL_DOWN

    def _draft(self, kind, query, value, worktree):
        """The drafts.py draft for one fixed sentence, from the till as it is now (a live read, never the cache)."""
        client, cfg = self.engine._client(), self.config
        items = parse_items(client.list_items())[0]
        if kind == "new":
            parts = [p.strip() for p in query.split(",")]
            category = parts.pop().lower() if len(parts) > 2 and parts[-1].lower() in CATEGORIES else None
            if len(parts) < 2: raise MapError("Send a new item like this: new item: Sunshine olive oil, 12.50, pantry")  # noqa: E701
            cents, cats = cents_from_text(parts.pop(), cfg.max_price_cents), [(c.get("id"), c.get("name")) for c in client.list_categories()]
            return d.build_create_item(", ".join(parts), cents, category, items, cfg, categories=cats)
        hidden = [i for i in items if i.hidden and norm_name(i.name) == norm_name(query)]
        item = hidden[0] if value == "show" and len(hidden) == 1 else resolve_exact(query, items)
        if kind in ("price", "hide"):
            return d.build_set_price(item, cents_from_text(value, cfg.max_price_cents), cfg) if kind == "price" else d.build_set_hidden(item, value == "hide", cfg)
        site = self._site(item.id, worktree)
        return (d.build_received(item, Decimal(value), cfg, site_product=site) if kind == "received" else
                d.build_set_stock(item, Decimal(value) if kind == "set" else 0, cfg, site_product=site))

    def _site(self, item_id, worktree):
        """The website product explicitly linked to this till item (the private links table), or None."""
        try:
            content, links = reports.read_inputs(self.state, worktree()) if worktree else ({"products": []}, {})
            pid = next((p for p, link in links.items() if isinstance(link, dict) and link.get("cloverId") == item_id), None)
            record = next((r for r in content["products"] if r.get("id") == pid), None) if pid else None
            return parse_site_product(record) if record else None
        except Exception as exc:  # noqa: BLE001 - unreadable: no draft rather than a till change without its website word
            raise MapError(SITE_UNKNOWN) from exc

    def drop(self, code, sender, chat):
        with self.engine.journal.locked() as db: db.execute("UPDATE changes SET status='dropped' WHERE code=? AND sender=? AND chat=? AND status='draft'", (code, sender, chat))  # noqa: E701

    def bundle(self, code, sender, chat):
        """(website ops, the website word they were drafted against) of this sender's waiting till draft, or ((), None)."""
        with self.engine.journal.locked() as db:
            row = db.execute("SELECT draft FROM changes WHERE code=? AND sender=? AND chat=? AND status='draft'", (code, sender, chat)).fetchone()
        draft = json.loads(row[0]) if row else {}
        return tuple(draft.get("site_ops") or ()), (draft.get("before") or {}).get("site")

    def site_moved(self, base, worktree, draft=None):
        """True unless the website product still shows exactly the word the draft (or undo) was made against: a newer change wins.
        FIX-2: with a prepared site ``draft``, the product as that draft found it (its own base), so nothing can land in between."""
        try:
            record = next((r["before"] for r in draft["records"] if (r["collection"], r["key"]) == ("products", base["id"])), None) if draft \
                else next((r for r in reports.read_inputs(self.state, worktree())[0]["products"] if r.get("id") == base["id"]), None)
            product = parse_site_product(record)
            return product.status != "active" or product.availability != base["available"]
        except Exception:  # noqa: BLE001 - no base, or the website cannot be read: never write over what we cannot see
            return True

    def approve(self, code, *, sender, chat):
        """`yes <code>`: (reply, website ops to publish now under that yes). The engine re-checks owner, chat, code, expiry, cap, item."""
        try:
            status = self.engine.handle("yes " + code, sender=sender, chat=chat, group=";+;" in chat)
        except MapError as exc:
            return voice.till(str(exc)), ()
        except Exception:  # noqa: BLE001 - no token, no till: nothing was sent
            return TILL_DOWN, ()
        if status != "applied":
            return NOT_DONE[status], ()
        with self.engine.journal.locked() as db: e = json.loads(db.execute("SELECT result FROM changes WHERE code=?", (code,)).fetchone()[0])  # noqa: E701
        now = {"set_price": lambda a: f"now costs {format_money(a['price'])}", "set_stock": lambda a: f"now shows {a['stock']}",
               "create_item": lambda a: f"is in it, SKU {a['sku']}", "set_hidden": lambda a: "is hidden" if a["hidden"] else "is showing"}[e["kind"]](e["after"])
        return voice.till(f"Done, and I read the till back: {e['label']} {now}. To put it back, say undo {code}."), tuple(e["site_ops"])
