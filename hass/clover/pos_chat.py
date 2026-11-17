"""HASS-POS-2 (build-ahead): the till-view commands for Mike and G, as pure functions. No model, runner, interpreter, network or token:
only the private cache through a TillDesk (docs/hass/POS.md). Not wired into chat/conversation yet (rebase round)."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from hass import voice
from hass.clover import cache, pos, reads, reports

INTENTS = ("till_summary", "price_of", "sold_today", "sold_week", "website_vs_till")
FIXED = {"till summary": "till_summary", "what sold today": "sold_today", "what sold this week": "sold_week",
         "website vs till": "website_vs_till", "website versus till": "website_vs_till"}
PRICE = re.compile(r"(?:what(?:'s| is) )?(?:the )?price of (?P<q>.+)")
COMPARE_FAILED = "I couldn't compare the till with the website. Nothing changed."


def parse(text):
    """(intent, query or None), or None when this is not a POS read. Fixed patterns only; one line, 200 characters at most."""
    if not isinstance(text, str) or len(text) > 200 or "\n" in text.strip():
        return None
    t = re.sub(r"[\s?.!]+$", "", re.sub(r"\s+", " ", text.replace("\u2019", "'").strip().lower()))
    if t in FIXED:
        return (FIXED[t], None)
    m = PRICE.fullmatch(t)
    q = re.sub(r"^(?:the|our|some) ", "", m["q"]).strip() if m else ""
    return ("price_of", q) if q else None


def allowed(msg, settings, owner_chats, *, role):
    """role 'owner': an owner sender in an owner chat. role 'g': a G sender in G's own chat (never an owner chat). Both: a new,
    private, text-only message that is not our own. Anything else gets no reply."""
    from hass.conversation import sender_key   # lazy: conversation imports the till chat that will import this module
    chat, key = getattr(msg, "chat", None), sender_key(getattr(msg, "sender", None))
    if not isinstance(chat, str) or ";+;" in chat or key is None or msg.from_me or msg.kind != "new" or msg.attachments != 0:
        return False
    if role == "owner":
        return chat in owner_chats and key in settings.get("chatKeys", {}).get(chat, settings.get("ownerKeys", ()))
    return role == "g" and chat == settings.get("gChat") and chat not in owner_chats and key in settings.get("gKeys", ())


def answer(intent, *, desk, now, worktree):
    """The reply for a parsed intent, from the private cache only. Till names are quoted (voice.quote)."""
    from hass.clover import chat   # lazy: chat will import this module
    snapshot, reachable = desk._snapshot()
    if snapshot is None:
        return chat.NEVER_READ if reachable else chat.DOWN_NO_DATA
    kind, query = intent
    if kind == "price_of":
        return pos.price_of(query, snapshot, now, reachable, voice.quote)
    snaps = cache.history(desk.state, desk.identity)
    deltas = pos.journal_deltas(desk.state, desk.identity)
    if kind in ("sold_today", "sold_week"):
        return pos.drops(snapshot, snaps, deltas, now, reachable, 1 if kind == "sold_today" else 7, voice.quote)
    try:
        content, links = reports.read_inputs(desk.state, worktree)
        if kind == "website_vs_till":
            return pos.website_vs_till(snapshot, content, links, now, reachable, voice.quote)
        return pos.summary(snapshot, snaps, deltas, now, content, links, reachable, desk.config.low_stock_threshold)
    except Exception:  # noqa: BLE001 - no names, paths or input errors in the reply
        return COMPARE_FAILED


def waiting_line(state):
    """'N stock words waiting for the website since H:MM pm (reason)' from site-stock-totals.json (hass/stock_site.py), else None."""
    path = Path(state) / "clover" / "reports" / "site-stock-totals.json"
    try:
        data = json.loads(path.read_text("utf-8"))
        pending, age, reason = data["pending"], data["oldestPendingAge"], data.get("lastReason") or ""
        if type(pending) is not int or pending <= 0 or isinstance(age, bool) or not isinstance(age, (int, float)) or not isinstance(reason, str):
            return None
        first = datetime.fromtimestamp(path.stat().st_mtime - age, timezone.utc)
        since = reads.when(first, first)
        return f"{pending} stock words waiting for the website since {since}" + (f" ({reason})" if reason else "")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return None
