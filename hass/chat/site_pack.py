"""Site pack: read-only catalog commands `find`, `listing`, `hidden` and `photos to take` (Conversation mixin).

AVB-12: moved verbatim out of hass/conversation.py, which imports every name back (hass.conversation.<name> is
unchanged). The methods run on the Conversation (self is the conversation): they use its store, replies and
settings exactly as before. Command routing stays in Conversation._command.
"""
from datetime import datetime

from hass import editor as editor_mod, sitegen, voice
from hass.chat.shared import CANT_READ, load_content, LOCAL_TZ, q, STATUS_PLAIN
from hass.content_model import _text as checked_text, ContentError, HOME_IMAGE_RE, iso_day, load_and_validate, SHELF_LABELS, shop_today, validate
from hass.ops import catalog

SHELF_MAX = 60  # AV1052-05: products listed by `shelf <name>`, then "... and N more"
SHELF_NEW_DAYS = 14  # AV0222-09 / shop.js NEW_BADGE_DAYS: a product added 0..13 Pacific days ago shows New and comes first
PHOTOS_TO_TAKE_MAX = 5  # AV0222-04, HASS-VOICE-1: names listed by `photos to take` (a short list, then ask again)

HIDDEN_MAX = 20  # AV1222-13: lines of the hidden list
LISTING_DESC_MAX = 120  # AV1622-09: characters of a product description in `listing`

LISTING_USAGE = "Which one? Say it like " + q("listing Etto") + "."
LISTING_NONE = "I don't know that one. Try " + q("find") + " and a word from its name."
LISTING_MANY = "That fits more than one thing. Could you say a bit more of its name?"

FIND_MAX, FIND_USAGE = 10, "Tell me a word or two to look for, like " + q("find lion's mane") + "."  # AV1537-04


class SitePack:
    """Site pack commands, mixed into Conversation."""

    def _listing_names_something(self, text) -> bool:
        """Like post, a multiword listing needs a known name; unreadable content gets the usual read error."""
        try:
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            return True
        return any(self._pick(kind, text, content) != text for kind in ("product", "maker")) \
            or self._pick_hike(content, text) != text or self._pick_hike(content, text, "routeIdeas") != text \
            or self._title_matches(content, text)

    @staticmethod
    def _title_matches(content, text) -> bool:
        """True when some hike or route idea title holds every word, even if several do (the listing then says it is not sure)."""
        words = catalog._fold(text).split()
        if not words or not isinstance(content.community, dict): return False
        return any(isinstance(e, dict) and isinstance(e.get("title"), str) and all(w in catalog._fold(e["title"]) for w in words)
                   for key in ("events", "routeIdeas") for e in (content.community.get(key) if isinstance(content.community.get(key), list) else []))

    def _find(self, query) -> str:
        """AV1537-04: read-only lookup, products then makers; id/name/status only, never a draft or a memory table."""
        try:  # the current catalog, read from the writer worktree as _hike_lines does
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            try:  # AV1322-04: a malformed event/route idea is worded or skipped below; any other problem is unavailable
                validate(content, wt / "storefront-mockup")
            except ContentError as exc:
                if any(not p.startswith(("events[", "routeIdeas[")) for p in exc.problems): raise
            shown = []  # the fields a reply line repeats get the validator's text checks: no line break/markup injection
            for key in ("events", "routeIdeas"):
                for i, r in enumerate(content.community[key] if isinstance(content.community[key], list) else []):
                    for field in ("id", "title", "status") if isinstance(r, dict) else ():
                        if r.get(field) is not None and (field != "title" or isinstance(r[field], str)):
                            checked_text(shown, f"{key}[{i}].{field}", r[field])
            if shown: raise ContentError(shown)
            has_memory = self.db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory'").fetchone()
            aliases, lines, capped = self.aliases() if has_memory else {}, [], False
            records = {"product": {p["id"]: (p["name"], p["status"]) for p in content.products},
                       "maker": {k: (m["name"], "hidden" if m.get("hidden") else "visible") for k, m in content.makers.items()}}
            for kind in ("product", "maker"):
                found = catalog.lookup(content, kind, query, aliases=aliases)
                ids = [found["match"]] if "match" in found else [c["id"] for c in found["candidates"]]
                capped |= len(ids) >= catalog.MAX_CANDIDATES
                lines += [f"{q(records[kind][i][0])} ({STATUS_PLAIN.get(records[kind][i][1], 'not sure')}"
                          + (", your nickname" if found.get("via") else "") + ")" for i in ids]
            words = catalog._fold(query).split()  # AV1322-04: hikes by start, then route ideas by title
            def hits(recs): return [r for r in recs if isinstance(r, dict) and isinstance(r.get("title"), str)
                                    and words and all(w in catalog._fold(r["title"]) for w in words)]
            def when(event):  # Pacific start, or None when startsAt does not parse (never raises)
                try:
                    at = datetime.fromisoformat(event["startsAt"].replace("Z", "+00:00"))
                    return at.astimezone(LOCAL_TZ) if at.tzinfo else None
                except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
                    return None
            dated = sorted(((e, when(e)) for e in hits(content.community["events"])),
                           key=lambda pair: (pair[1] is None, pair[1].timestamp() if pair[1] else 0))
            lines += [f"{q(e['title'])} (hike, " + (voice.natural(at, self._now()) if at else "no date I can read")
                      + f", {STATUS_PLAIN.get(e.get('status'), 'not sure')})" for e, at in dated]
            lines += [f"{q(r['title'])} (route idea, {STATUS_PLAIN.get(r.get('status'), 'not sure')})"
                      for r in sorted(hits(content.community["routeIdeas"]), key=lambda r: catalog._fold(r["title"]))]
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "find"
        more = len(lines) - FIND_MAX
        tail = ["There are more. Add a word to narrow it down."] if more > 0 or capped else []
        self._reply("\n".join(lines[:FIND_MAX] + tail) if lines
                    else f"I couldn't find anything called {q(query)}.", long_ok=True)
        return "find"

    def _listing(self, ident) -> str:
        """AV1622-09 (H17): read-only view of one saved product, maker, hike or route idea by exact id, from the writer
        worktree content (strictly validated). Nothing is drafted or stored; works while paused."""
        if not ident:
            self._reply(LISTING_USAGE)
            return "listing"
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_content(wt / "hass" / "content")
            validate(content, wt / "storefront-mockup")
            def collect(i):
                f = [("product", p) for p in content.products if p.get("id") == i]
                f += [("maker", m) for k, m in content.makers.items() if k == i]
                return f + [(kind, r) for kind, key in (("hike", "events"), ("route idea", "routeIdeas"))
                            for r in content.community[key] if r.get("id") == i]
            found = collect(ident)  # an exact id/key of any kind beats every name/title fallback
            if not found:
                typed, ident = ident, self._pick("product", ident, content)
                if not any(p.get("id") == ident for p in content.products): ident = self._pick("maker", typed, content)
                if ident == typed: ident = self._pick_hike(content, typed)
                if ident == typed: ident = self._pick_hike(content, typed, "routeIdeas")
                found = collect(ident)
            if len(found) != 1: text = LISTING_NONE if not found else LISTING_MANY
            else:
                kind, rec = found[0]
                nope = "nothing yet"
                if kind == "product":
                    maker = content.makers.get(rec.get("producerKey"))
                    desc = rec.get("description")
                    if isinstance(desc, str) and desc:  # held records skip validate_products' description check
                        bad = []
                        checked_text(bad, "description", desc)
                        if bad: raise ValueError(bad[0])
                    desc = nope if not isinstance(desc, str) or not desc else desc[:LISTING_DESC_MAX] + ("…" if len(desc) > LISTING_DESC_MAX else "")
                    avail = (sitegen.availability_label(rec, content.store, shop_today(self._now())) or "not confirmed") \
                        if rec["status"] == "active" else "not showing"
                    fields = [("Name", rec["name"]), ("Maker", (maker or {}).get("name") or rec.get("brand") or nope),
                              ("Shelf", SHELF_LABELS.get(rec.get("category"), rec.get("category")) or nope), ("Description", desc),
                              ("Availability", avail), ("Status", STATUS_PLAIN.get(rec["status"], "not sure"))]
                elif kind == "maker":
                    fields = [("Name", rec["name"]), ("Place", rec.get("place") or nope),
                              ("Products showing", sum(1 for p in content.products if p["status"] == "active" and p.get("producerKey") == ident)),
                              ("Status", "hidden" if rec.get("hidden") else "on the website")]
                elif kind == "hike":
                    fields = [("Title", rec["title"]), ("Starts", voice.natural_iso(rec["startsAt"], self._now())),
                              ("Status", STATUS_PLAIN.get(rec["status"], "not sure")),
                              ("Meeting place", rec.get("meetingPoint") or nope), ("Guest limit", rec.get("capacity", nope))]
                else:
                    fields = [("Title", rec["title"]), ("Place", rec.get("place") or nope), ("Status", STATUS_PLAIN.get(rec["status"], "not sure"))]
                text = "\n".join(["This is from my saved copy, not a live look at the website:"] + [f"{k}: {q(v)}" for k, v in fields])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            text = CANT_READ
        self._reply(text, long_ok=True)
        return "listing"

    def _photos_to_take(self) -> str:
        """AV0222-04 (H10/H17): active products whose image is not an installed photo-<16 hex> file, by shelf in site order;
        saved content only, read-only, works while paused. A filename convention, not proof of where a picture came from."""
        try:
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            order = tuple(SHELF_LABELS)
            todo = sorted((p for p in content.active_products() if not HOME_IMAGE_RE.fullmatch(p["image"])),
                          key=lambda p: (order.index(p["category"]), p["name"].casefold(), p["id"]))
            lines, shelf = [], None
            for p in todo[:PHOTOS_TO_TAKE_MAX]:
                lines.append(f"- {q(' '.join(str(p['name']).split()))} ({SHELF_LABELS[p['category']]})")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "photos"
        if not todo:
            self._reply("Every product on the website has your own photo.")
            return "photos"
        more = ["When you've sent those, ask again and I'll show the next few."] if len(todo) > PHOTOS_TO_TAKE_MAX else []
        self._reply("\n".join(["Some products still show a stock picture instead of your own photo. The first few:"] + [
            l if l.startswith("- ") else f"{l}" for l in lines] + more
            + ["To replace one, send a photo with the product's name as the caption."]), long_ok=True)
        return "photos"

    def _shelf(self, rest, now) -> str:
        """AV1052-05 (H17/SHOP-1): one shelf's active products in site order, each with the word the site shows for it.
        Read-only: the saved writer worktree, never the live site; hidden and held products are left out; works while paused."""
        wanted = " ".join(str(rest or "").split()).lower()
        key = next((k for k, label in SHELF_LABELS.items() if wanted in (k, label.lower())), None)
        if key is None:
            self._reply("Choose a shelf: " + ", ".join(SHELF_LABELS.values()) + ".", long_ok=True)
            return "shelf"
        try:  # the current catalog from the writer worktree, as report; never a default or partial list
            wt = editor_mod._load(str(self.sdir))[2]
            content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
            today = shop_today(now)
            records = [p for p in content.active_products() if p.get("category") == key]
            day = today.toordinal()

            def age(p):  # the site's New rule (shop.js isNew): added 0..13 Pacific days ago
                added = iso_day(p.get("addedOn"))
                return day - added.toordinal() if added is not None and 0 <= day - added.toordinal() < SHELF_NEW_DAYS else None
            fresh = sorted((p for p in records if age(p) is not None), key=lambda p: -iso_day(p["addedOn"]).toordinal())
            records = fresh + [p for p in records if age(p) is None]  # sorted() is stable: ties keep site order
            one = lambda name: " ".join(str(name).split())
            lines = []
            for p in records[:SHELF_MAX]:
                word = sitegen.availability_label(p, content.store, today)
                lines.append(f"- {one(p['name'])}" + (f" - {word}" if word else ""))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shelf-unreadable")
            self._reply(CANT_READ)  # the spec's wording names the catalog, which voice.check refuses; nothing changed is said
            return "shelf"
        more = [f"... and {len(records) - SHELF_MAX} more"] if len(records) > SHELF_MAX else []
        self._reply("\n".join([f"Shelf: {SHELF_LABELS[key]}"] + (lines + more if lines else ["No products on this shelf."])), long_ok=True)
        return "shelf"

    def _hidden(self) -> str:
        """AV1222-13 (H03): read-only list of hidden products then hidden makers; held products and visible makers never."""
        try:  # the current catalog from the writer worktree, as _find
            content = load_content(editor_mod._load(str(self.sdir))[2] / "hass" / "content")
            one = lambda name: " ".join(str(name).split())  # stored text on one line
            lines = [f"- {q(one(p['name']))}" for p in sorted(content.products, key=lambda p: p["id"])
                     if p["status"] == "hidden"]
            first = next((one(p["name"]) for p in sorted(content.products, key=lambda p: p["id"]) if p["status"] == "hidden"), None)
            lines += [f"- {q(one(m['name']))} (maker)" for k, m in sorted(content.makers.items()) if m.get("hidden") is True]
            first = first or next((one(m["name"]) for k, m in sorted(content.makers.items()) if m.get("hidden") is True), "")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, editor_mod.UnsafeState, ContentError):
            self._problem("error", "shop-list-unreadable")
            self._reply(CANT_READ)
            return "hidden"
        more = ["And a few more."] if len(lines) > HIDDEN_MAX else []
        self._reply("\n".join(["These are hidden right now:"] + lines[:HIDDEN_MAX] + more
                               + ["To bring one back, tell me, like " + q(f"Bring back {first}") + "."])
                    if lines else "Nothing is hidden right now.", long_ok=True)
        return "hidden"
