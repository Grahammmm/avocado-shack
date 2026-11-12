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
import re

from hass import voice
from hass.clover import cache, reads
from hass.clover.config import from_settings

WRITE_REPLY = "I can read the till but I can't change it yet."
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
IN_STOCK = re.compile(r"(?:is|are) (?:there )?(?:any )?(?P<q>.+?) (?:in stock|sold out|left)(?: in the till| on the till)?"
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
    """Reads the cache under `state`; holds no token and makes no network call."""

    def __init__(self, state, settings, read=cache.read):
        self.state, self.config, self._read = state, from_settings(settings), read

    def __repr__(self):
        return "TillDesk(read-only)"

    def parse(self, text):
        """("low",), ("how_many", query), ("in_stock", query), ("write",) or None (not a till message)."""
        t = _clean(text)
        if not t or len(t) > 200 or "\n" in (text or "").strip():
            return None
        if LOW.fullmatch(t):
            return ("low",)
        for pattern, kind in ((HOW_MANY, "how_many"), (COUNT_OF, "how_many"), (IN_STOCK, "in_stock")):
            m = pattern.fullmatch(t)
            if m:
                q = _query(m.group("q") or "") if "q2" not in m.re.groupindex else _query(m.group("q") or m.group("q2") or "")
                return self._claim(t, kind, q)
        if not SITE_WORDS.search(t) and (PRICE_WRITE.search(t) or TILL_WRITE.search(t) or STOCK_WRITE.search(t)):
            return ("write",)
        return None

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
        try:
            return self._read(self.state)
        except Exception:  # noqa: BLE001 - an unreadable cache is "can't reach the till", never a crash of the conversation
            return None, False

    def answer(self, intent, now):
        """The reply text for a parsed intent at `now` (timezone-aware). Till names and SKUs are quoted (shown as the till has them)."""
        if intent[0] == "write":
            return WRITE_REPLY
        snapshot, reachable = self._snapshot()
        if snapshot is None:
            return NEVER_READ if reachable else DOWN_NO_DATA
        if intent[0] == "low":
            return reads.low_stock(snapshot, now, self.config.low_stock_threshold, reachable, show=voice.quote)
        if intent[0] == "in_stock":
            return reads.in_stock(intent[1], snapshot, now, reachable, show=voice.quote)
        return reads.how_many(intent[1], snapshot, now, reachable, show=voice.quote)
