"""HASS-LIVE-ADD-2: read a maker's OWN public website once, politely, and draft a short maker story from it.

Only used when Mike gives the maker's web address while adding a new item. One plain HTTPS request for the page (and one for
the site's robots.txt), no accounts, no keys, no cookies, no proxy, one request per site every ``MIN_GAP`` seconds. A redirect
is never followed by urllib: ``fetch`` reads the answer and follows it itself, same site only (www. or not), at most
``MAX_REDIRECTS`` times, and every hop gets the same checks as the first request (public address, robots.txt, the gap).
The page's
text is never kept: only the few short sentences the story uses, the address and the retrieval day (``record``).

What the story may say (the rules, each tested in hass/tests/test_maker_site.py):
* every sentence comes from the page, is short (``MIN_LEN``..``MAX_LEN`` characters), is about the maker (it starts with the
  maker's name, with "We" or with "Our", or it names the maker) and at most ``MAX_SENTENCES`` are used (``MAX_CHARS`` in all);
* "We make ..." becomes "<Maker> makes ..." (hass.skills.makers.story_words); a sentence with we/our/us/you/your anywhere
  else is left out, because it cannot be turned into the house voice safely;
* a sentence with a number (a year is fine), ``!``, ``?``, a quotation, a hype word, a price, contact details, or anything the
  live gate calls a claim (where the food comes from, organic, health, awards, endorsements, trail facts) is left out. The page
  is evidence for the sentence; it is never a reason to say something the shop cannot stand behind;
* nothing is copied in bulk: an extract, not a paragraph. Mike reads the draft and may change it before ``yes``.

This module does the network read; the plan (hass/skills/item_add.py) stays pure and only receives the result through
``ctx.maker_page(url)``.
"""
from __future__ import annotations

import html as html_lib
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from hass import claims, house_style as hs, live_policy

USER_AGENT = "AvocadoShackHass/1.0 (+https://theavocadoman.com; reads a maker's own about page once for the shop owner)"
TIMEOUT = 10  # seconds per request
MAX_BYTES = 600_000  # the page is cut here; the text read is only ever its first part
MAX_REDIRECTS = 3
REDIRECTS = frozenset({301, 302, 303, 307, 308})
MIN_GAP = 2.0  # seconds between two requests to the same host (polite rate limit)
CACHE_SECONDS = 1800  # the same address inside one open request is read once
MIN_LEN, MAX_LEN, MAX_SENTENCES, MAX_CHARS = 40, 190, 2, 330
SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer", "header", "form", "aside", "svg", "template", "button"})
BLOCK_TAGS = frozenset({"p", "h1", "h2", "h3", "li"})
FIRST_PERSON = re.compile(r"\b(?:we|we're|we've|we'll|our|ours|ourselves|us|i|i'm|my|myself|you|your|yours)\b", re.IGNORECASE)
YEAR = re.compile(r"\b(?:18|19|20)\d{2}\b")
HYPE = re.compile("|".join(rf"(?<!\w){re.escape(w)}(?!\w)" for w in hs.HYPE_SEED), re.IGNORECASE)

CODES = {  # PageError.code -> what Mike is told (plain words, VOICE.md)
    "address": "That doesn't look like a website address I can read. Could you send it like https://example.com?",
    "unreachable": "I couldn't open that website just now.",
    "refused": "That website asks programs not to read it, so I won't.",
    "unreadable": "I couldn't find anything I can use on that page.",
}


class PageError(Exception):
    """A page that cannot be used. ``code`` is one of CODES; ``reply`` is the plain sentence for Mike."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code, self.reply = code, CODES[code]


# -- the polite read -----------------------------------------------------------------------------------------------------
_LOCK = threading.Lock()
_LAST: dict = {}  # host -> monotonic time of the last request
_CACHE: dict = {}  # address -> (monotonic time, page)


def _wait(host: str, sleep, clock) -> None:
    with _LOCK:
        gap = MIN_GAP - (clock() - _LAST.get(host, -MIN_GAP))
        if gap > 0:
            sleep(gap)
        _LAST[host] = clock()


def check_address(url) -> str:
    """The address as an https URL with no login, odd port or fragment, or PageError("address")."""
    raw = " ".join(str(url or "").split())
    if not raw.lower().startswith("https://"):
        raw = "https://" + raw if re.fullmatch(r"(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?", raw, re.IGNORECASE) else ""
    parts = urlsplit(raw) if raw else None
    host = (parts.hostname or "") if parts else ""
    if (not parts or parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443) or "." not in host
            or host.replace(".", "").isdigit() or len(raw) > 300):
        raise PageError("address")
    return parts._replace(fragment="").geturl()


def _addresses(host: str) -> list:
    """The addresses ``host`` resolves to, or [] unless every one of them is a public (global) address."""
    try:
        found = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]
    except (OSError, ValueError):
        return []
    return found if found and all(ip.is_global for ip in found) else []


def _public(host: str) -> bool:
    return bool(_addresses(host))


class _PinnedHTTPS(http.client.HTTPSConnection):
    """https that connects only to an address that was just checked to be public: the name is resolved once, here, so a
    name that answers differently the second time (DNS rebinding) cannot lead the read inside. TLS still checks the name."""

    def connect(self):
        addresses = _addresses(self.host)
        if not addresses:
            raise OSError("not a public address")
        last = OSError("no address")
        for ip in addresses:
            try:
                sock = socket.create_connection((str(ip), self.port or 443), self.timeout)
            except OSError as exc:
                last = exc
                continue
            self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
            return
        raise last


class _PinnedHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PinnedHTTPS, req)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect inside urllib: ``fetch`` reads the 3xx answer and decides, hop by hop (``_hop``)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_get(url: str, headers: dict, timeout: float):
    """(status, content type, body bytes cut at MAX_BYTES, Location of a redirect or ""). One request, no proxy, no cookies,
    public addresses only, and no redirect followed: that is ``fetch``'s decision, one checked hop at a time."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _PinnedHandler(), _NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read(MAX_BYTES), ""
    except urllib.error.HTTPError as exc:
        return exc.code, "", b"", (exc.headers.get("Location", "") if exc.headers and exc.code in REDIRECTS else "")
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        return 0, "", b"", ""


def _site(host) -> str:
    return (host or "").lower().removeprefix("www.")


def _hop(url: str, location: str) -> str:
    """Where a redirect from ``url`` may go: https on the same site (www. or not), no login or odd port, else PageError."""
    new = urljoin(url, location)
    if _site(urlsplit(new).hostname) != _site(urlsplit(url).hostname):
        raise PageError("unreachable")
    try:
        return check_address(new)
    except PageError as exc:
        raise PageError("unreachable") from exc


def _read(url: str, accept: str, get, live: bool, sleep, clock, rules: dict, *, robots: bool):
    """(status, content type, body) of ``url`` after at most MAX_REDIRECTS same-site redirects. EVERY request, the first and
    each hop, is held to the same rules: a public address (``live``), the site's robots.txt (for pages; ``robots``) and the
    polite gap. An answer that cannot be followed safely is PageError("unreachable")."""
    for hop in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if live and not _public(parts.hostname or ""):
            raise PageError("unreachable")
        if robots and not _allowed(url, get, live, sleep, clock, rules):
            raise PageError("refused")
        _wait(_site(parts.hostname), sleep, clock)
        status, kind, body, *where = get(url, {"User-Agent": USER_AGENT, "Accept": accept}, TIMEOUT)
        if status not in REDIRECTS:
            return status, kind, body
        if not (where and where[0]) or hop == MAX_REDIRECTS:
            raise PageError("unreachable")
        url = _hop(url, where[0])
    raise PageError("unreachable")  # not reached: the loop returns or raises


def _allowed(url: str, get, live: bool, sleep, clock, rules: dict) -> bool:
    parts = urlsplit(url)
    if parts.netloc not in rules:  # one robots.txt per host in one read
        status, _kind, body = _read(f"https://{parts.netloc}/robots.txt", "text/plain", get, live, sleep, clock, rules, robots=False)
        if status in (401, 403):
            rules[parts.netloc] = False
        elif status != 200:  # none, or unreadable: the usual reading is that nothing is forbidden
            rules[parts.netloc] = True
        else:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(body.decode("utf-8", "replace").splitlines())
            rules[parts.netloc] = parser
    rule = rules[parts.netloc]
    return rule if isinstance(rule, bool) else rule.can_fetch(USER_AGENT, url)


def fetch(url, *, get=None, sleep=time.sleep, clock=time.monotonic, today=None, cache=True) -> dict:
    """Read one page: {"url", "retrieved": ISO day, "blocks": [text, ...]}, or raise PageError. ``get(url, headers, timeout)``
    returns (status, content type, bytes[, redirect Location]); tests pass recorded responses, so no test touches the network."""
    url = check_address(url)
    now = clock()
    cached = _CACHE.get(url) if cache else None
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]
    live = get is None
    if live:
        get = _http_get
    status, kind, body = _read(url, "text/html", get, live, sleep, clock, {}, robots=True)
    if status != 200 or not body:
        raise PageError("unreachable")
    if "html" not in kind.lower() and kind:
        raise PageError("unreadable")
    blocks = extract(body.decode("utf-8", "replace"))
    if not blocks:
        raise PageError("unreadable")
    page = {"url": url, "retrieved": (today or date.today()).isoformat(), "blocks": blocks}
    if cache:
        _CACHE[url] = (now, page)
    return page


def reader(*, get=None, today=None):
    """``ctx.maker_page``: ``fn(url) -> page`` (raises PageError). One per request; the cache above spans requests."""
    return lambda url: fetch(url, get=get, today=today)


# -- the page's text -----------------------------------------------------------------------------------------------------
class _Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self._skip, self._open = [], 0, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (a.get("name") or a.get("property") or "").lower() in ("description", "og:description"):
            self.blocks.insert(0, a.get("content") or "")
        elif tag in SKIP_TAGS:
            self._skip += 1
        elif tag in BLOCK_TAGS and not self._skip:
            self._open = []

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in BLOCK_TAGS and self._open is not None:
            self.blocks.append(" ".join("".join(self._open).split()))
            self._open = None

    def handle_data(self, data):
        if self._open is not None and not self._skip:
            self._open.append(data)


def extract(markup: str) -> list:
    """The readable blocks of a page, in page order, the description meta first. Never raises."""
    parser = _Blocks()
    try:
        parser.feed(markup[:MAX_BYTES])
        parser.close()
    except Exception:  # noqa: BLE001 - a page that will not parse is a page with nothing usable
        pass
    return [b for b in (" ".join(html_lib.unescape(b).split()) for b in parser.blocks) if b]


# -- the story ---------------------------------------------------------------------------------------------------------
def _split(block: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.])\s+(?=[A-Z])", block) if s.strip()]


def _fold(text) -> str:
    return claims.fold(text or "")


def usable(sentence: str, name: str):
    """The sentence in the house voice (the maker's name for We / Our), or None when it cannot be used."""
    s = sentence.strip().replace("\u2019", "'")
    if not (MIN_LEN <= len(s) <= MAX_LEN) or not s.endswith(".") or re.search(r"[!?\"\u201c\u201d@:]|https?:|www\.", s):
        return None
    if re.search(r"\d", YEAR.sub("", s)) or HYPE.search(s) or live_policy._protected(s)[1]:
        return None
    named = bool(re.search(r"(?<!\w)" + re.escape(_fold(name)) + r"(?!\w)", _fold(s)))
    head = re.match(r"(We|Our)\b", s)
    if head and named:  # "We started Harbor Lane ..." would read "Harbor Lane started Harbor Lane ...": left out
        return None
    if head:
        s = ("They" if head.group(1) == "We" else "Their") + s[head.end():]
    if FIRST_PERSON.search(s):
        return None
    if not (named or head):
        return None
    return s


def draft_story(name: str, page: dict, *, said: str = "") -> dict | None:
    """{"sentences": [house-voice sentences], "from": [the page sentences they came from]} for the maker, or None when the page
    gives nothing usable. ``said`` is Mike's own words about the maker; a page sentence that only repeats them is skipped."""
    from hass.skills import makers  # noqa: PLC0415 - makers imports the claims gate; keep this module light to import
    out, used, total = [], [], len(" ".join(said.split()))
    seen = _fold(said)
    for block in page.get("blocks", ()):
        for sentence in _split(block):
            fixed = usable(sentence, name)
            if fixed is None or _fold(sentence) in seen:
                continue
            house = makers.story_words(fixed, name)
            if house in out or total + len(house) + 1 > MAX_CHARS - 40:
                continue
            out.append(house), used.append(sentence)
            total += len(house) + 1
            if len(out) == MAX_SENTENCES:
                return {"sentences": out, "from": used}
    return {"sentences": out, "from": used} if out else None


def record(page: dict, story: dict) -> dict:
    """The provenance kept with the story: where it was read, when, and which page sentences it came from."""
    return {"source": page["url"], "retrieved": page["retrieved"], "from": list(story["from"]), "story": " ".join(story["sentences"])}
