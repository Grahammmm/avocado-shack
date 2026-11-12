"""HASS-LIVE-ADD-2: read a maker's OWN public website once, politely, and offer the owner a short story written from it.

Only used when Mike gives the maker's web address while adding a new item. One plain HTTPS request for the page (and one for
the site's robots.txt), no accounts, no keys, no cookies, no proxy, one request per site every ``MIN_GAP`` seconds. A redirect
is never followed by urllib: ``fetch`` reads the answer and follows it itself, same site only (www. or not), at most
``MAX_REDIRECTS`` times, and every hop gets the same checks as the first request (public address, robots.txt, the gap).
The page's text is never kept: only the page sentences the facts came from, the address and the retrieval day (``record``).

HASS-SEC-3 (reports/hass/SEC-1.md M2, L1): the whole read has limits, not each request.
* ONE wall-clock deadline (``DEADLINE``, 8 s) for robots.txt, every hop, the polite gaps between them and the page: a request
  may only take what is left (``TIMEOUT`` at most), a gap that would run past the deadline is not waited, the body is read in
  ``CHUNK`` pieces with the clock checked between them, the name lookup runs with the time left, and a watchdog shuts the
  socket at the deadline, so a server that trickles one byte at a time cannot hold the read open;
* one byte allowance (``TOTAL_BYTES``) and one request count (``MAX_REQUESTS``) for everything the read asks for;
* the address must be a plain public name (no IP literal in any spelling, no trailing dot, no non-ASCII, a real top-level
  name), and every address it resolves to must be public: not IPv4-mapped, NAT64, 6to4, Teredo or IPv4-compatible. Every
  connection resolves the name again and connects only to what it just checked (DNS rebinding).
* The read happens BEFORE the conversation opens its write transaction (``prefetch``, called by hass/conversation.py); inside
  the transaction the plan only sees that result (``prefetched``) and never touches the network.

What may be taken from the page (HASS-SEC-3 H2 / L2; each rule tested in hass/tests/test_maker_site_sec3.py):
* never a page sentence. Three facts only, each from a page sentence that passes every rule (``source_ok``): what the maker
  makes ("<Maker> makes <things>."), since which year ("<Maker> started in <year>.") and the town, only when it is the town the
  owner already confirmed ("<Maker> is based in <town>."); at most ``MAX_SENTENCES`` of them, written by code in the house
  voice. The "things" are plain lower-case words cut before any place, purpose or manner ("in", "for", "with", ...);
* a page sentence is left out whole when it has a number (a year is fine), ``!``, ``?``, a quotation, a link or an address,
  a hype word, anything the live gate calls a claim (``live_policy._protected``), a claim, contact, price, third-party or
  instruction word (``DROP_WORDS``), a capitalised name other than the maker and the confirmed town, first-person talk past
  a leading We / Our, or anything that is not plain ASCII;
* Mike sees it in the preview as "The maker's own site says: ..." with the address and the day (hass/skills/item_add.py),
  and it goes live only with his yes to that exact draft. A coincidence where a page sentence already has the exact shape of
  a fact sentence is not copying: every public sentence is one of the three shapes above, built from the fact.

This module does the network read; the plan (hass/skills/item_add.py) stays pure and only receives the result through
``ctx.maker_page(url)``.
"""
from __future__ import annotations

import functools
import html as html_lib
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from hass import claims, house_style as hs, live_policy

USER_AGENT = "AvocadoShackHass/1.0 (+https://theavocadoman.com; reads a maker's own about page once for the shop owner)"
DEADLINE = 8.0  # seconds for the WHOLE read: robots.txt, every redirect hop, the gaps between them and the page (SEC-3 M2)
TIMEOUT = 5  # seconds one request may take at most; never more than what is left of DEADLINE
MAX_BYTES = 600_000  # the page is cut here; the text read is only ever its first part
ROBOTS_BYTES = 64_000  # a robots.txt is cut here
TOTAL_BYTES = 640_000  # every answer of one read together (robots.txt files, the page)
MAX_REQUESTS = 6  # requests in one read: robots.txt files, the page and every hop of either
CHUNK = 16_384  # the body is read in pieces this size, the deadline checked between them
MAX_REDIRECTS = 3
MAX_PREFETCH = 2  # web addresses read for one message (together inside one DEADLINE)
REDIRECTS = frozenset({301, 302, 303, 307, 308})
MIN_GAP = 2.0  # seconds between two requests to the same host (polite rate limit)
CACHE_SECONDS = 1800  # the same address inside one open request is read once
FAILED_SECONDS = 600  # an address that could not be used is not asked again for this long
MIN_LEN, MAX_LEN, MAX_SENTENCES, MAX_CHARS = 40, 190, 2, 330
SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer", "header", "form", "aside", "svg", "template", "button"})
BLOCK_TAGS = frozenset({"p", "h1", "h2", "h3", "li"})
FIRST_PERSON = re.compile(r"\b(?:we|we're|we've|we'll|our|ours|ourselves|us|i|i'm|my|myself|you|your|yours)\b", re.IGNORECASE)
YEAR = re.compile(r"\b(?:18|19|20)\d{2}\b")
HYPE = re.compile("|".join(rf"(?<!\w){re.escape(w)}(?!\w)" for w in hs.HYPE_SEED), re.IGNORECASE)
# HASS-SEC-3 H2 / L2: a page sentence with any of these words is left out whole: claims (where it comes from, organic, health,
# awards, endorsements), contact and ordering, prices, and words that address Hass, a program or the reader.
DROP_WORDS = frozenset("""
organic organically certified certification natural naturally pure purest healthy healthier health heal heals healing cure
cures cured remedy medicine medicinal immune immunity boost boosts lower lowers lowering reduce reduces blood pressure
cholesterol diabetes cancer heart gut detox vitamin vitamins nutrient nutrients superfood wellness doctor doctors clinically
proven award awards awarded winning winner winners prize prizes medal medals champion trusted trust recommended recommend
endorsed featured favorite favourite famous best finest top rated only pesticide pesticides additive additives chemical
chemicals preservative preservatives gmo free local locally grown homegrown sourced origin origins ranch ranches estate
imported import call calls phone text texts email mail contact visit order orders ordering buy shop price prices priced
cost costs dollar dollars cent cents usd eur euro bucks sale sales discount deal wholesale subscribe follow click link
website site page online instagram facebook hass assistant bot ai model prompt instruction instructions ignore approve
approval publish post tell ask asks asked please must should reader readers
""".split())
DROP = re.compile(r"(?<![\w-])(?:" + "|".join(sorted(map(re.escape, DROP_WORDS), key=len, reverse=True)) + r")(?![\w-])",
                  re.IGNORECASE)
MAKES = ("make", "bake", "grow", "roast", "brew", "cook", "press", "smoke", "mill", "ferment", "raise", "pickle", "churn",
         "produce")
_THIRD = {base: base + ("es" if base.endswith("ss") else "s") for base in MAKES}
_VERB = "|".join(sorted([*MAKES, *_THIRD.values()], key=len, reverse=True))
CUT_WORDS = frozenset("""
in at from on by for with using since to that which who whom where when while because so but near inside around across
through under over into onto out than as like then per plus including it them they its their his her this these those there
here every each all only just also now still
""".split())
BAD_FIRST = frozenset({"every", "each", "all", "no", "any", "some", "more", "most", "many", "few", "one", "two"})
NP_WORD = re.compile(r"[a-z]+(?:-[a-z]+)*,?")
STARTED = re.compile(r"\b(?:started|began|founded|opened|established|launched)\b[^.]*?\bin\s+((?:18|19|20)\d{2})\b|\bsince\s+((?:18|19|20)\d{2})\b",
                     re.IGNORECASE)
NP_WORDS, NP_CHARS = 8, 60

CODES = {  # PageError.code -> what Mike is told (plain words, VOICE.md)
    "address": "That doesn't look like a website address I can read. Could you send it like https://example.com?",
    "unreachable": "I could not read their site; tell me about them in a sentence.",  # SEC-3 M2: a failure or the deadline
    "refused": "That website asks programs not to read it, so I won't.",
    "unreadable": "I couldn't find anything I can use on that page.",
}


class PageError(Exception):
    """A page that cannot be used. ``code`` is one of CODES; ``reply`` is the plain sentence for Mike."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code, self.reply = code, CODES[code]


# -- the limits of one read (HASS-SEC-3 M2) ----------------------------------------------------------------------------------
class _Budget:
    """One read's limits, shared by robots.txt, every hop and the page: a wall-clock deadline, a byte allowance and a request
    count. ``clock`` is the read's clock (time.monotonic, or a test's)."""

    def __init__(self, clock=time.monotonic, seconds=None, total=None, requests=None):
        self.clock = clock
        self.deadline = clock() + (DEADLINE if seconds is None else seconds)
        self.bytes = TOTAL_BYTES if total is None else total
        self.requests = MAX_REQUESTS if requests is None else requests
        self._timers: list = []

    def left(self) -> float:
        return self.deadline - self.clock()

    def request(self) -> float:
        """Count one request: the seconds it may take (never past the deadline), or PageError("unreachable")."""
        left = self.left()
        if self.requests <= 0 or left <= 0:
            raise PageError("unreachable")
        self.requests -= 1
        return min(TIMEOUT, left)

    def take(self, body: bytes, cap: int) -> bytes:
        """``body`` cut at ``cap`` and at what is left of the byte allowance, which it then uses up."""
        body = bytes(body or b"")[:max(0, min(cap, self.bytes))]
        self.bytes -= len(body)
        return body

    def watch(self, sock) -> None:
        """At the deadline, shut ``sock`` so a read blocked on it ends (a server that answers one byte at a time)."""
        timer = threading.Timer(max(0.0, self.left()), _cut, (sock,))
        timer.daemon = True
        self._timers.append(timer)
        timer.start()

    def release(self) -> None:
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()


def _cut(sock) -> None:
    try:
        socket.socket.shutdown(sock, socket.SHUT_RDWR)  # the plain socket call: an SSL socket's own shutdown unwraps it first
    except (OSError, ValueError, TypeError):
        pass


def _guard(sock, budget) -> None:
    budget.watch(sock)


# -- the polite read -----------------------------------------------------------------------------------------------------
_LOCK = threading.Lock()
_LAST: dict = {}  # host -> monotonic time of the last request
_CACHE: dict = {}  # address -> (monotonic time, page or PageError)


def _wait(host: str, sleep, clock, budget=None) -> None:
    with _LOCK:
        gap = MIN_GAP - (clock() - _LAST.get(host, -MIN_GAP))
        if gap > 0:
            if budget is not None and gap >= budget.left():  # SEC-3 M2: never wait past the deadline
                raise PageError("unreachable")
            sleep(gap)
        _LAST[host] = clock()


_LABEL = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)")
_TOP = re.compile(r"[a-z]{2,63}|xn--[a-z0-9-]{1,59}")
LOCAL_NAMES = frozenset({"localhost", "local", "localdomain", "internal", "intranet", "lan", "home", "corp", "arpa", "onion",
                         "invalid"})


def _plain_host(host: str) -> bool:
    """A plain public DNS name: ASCII labels, at least two, no empty label (so no trailing dot), a top-level name that is
    letters (or IDNA), not a local name, and not an IPv4 or IPv6 address in any spelling (0x7f.1, 0177.0.0.1, 127.1 ...)."""
    labels = host.split(".")
    if len(labels) < 2 or len(host) > 253 or not all(_LABEL.fullmatch(label) for label in labels):
        return False
    if not _TOP.fullmatch(labels[-1]) or labels[-1] in LOCAL_NAMES:
        return False
    try:
        socket.inet_aton(host)
        return False
    except OSError:
        pass
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return True


def check_address(url) -> str:
    """The address as an https URL with no login, odd port or fragment, on a plain public name, or PageError("address")."""
    raw = " ".join(str(url or "").split())
    if not raw.lower().startswith("https://"):
        raw = "https://" + raw if re.fullmatch(r"(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?", raw, re.IGNORECASE) else ""
    if not raw or len(raw) > 300 or not raw.isascii():
        raise PageError("address")
    try:  # urlsplit itself raises ValueError on a broken bracket ("https://[broken/about"); .port on a bad port
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise PageError("address") from None
    host = parts.hostname or ""
    if (parts.scheme != "https" or parts.username or parts.password or port not in (None, 443) or "[" in parts.netloc
            or not _plain_host(host)):
        raise PageError("address")
    return parts._replace(fragment="", path=parts.path or "/").geturl()


_NOT_PUBLIC_V6 = tuple(ipaddress.ip_network(n) for n in (
    "::ffff:0:0/96",  # IPv4-mapped
    "::/96",  # IPv4-compatible (deprecated)
    "64:ff9b::/96", "64:ff9b:1::/48",  # NAT64: the gateway reaches the IPv4 address inside
    "2002::/16",  # 6to4
    "2001::/32",  # Teredo
    "100::/64", "2001:db8::/32", "fc00::/7", "fe80::/10"))


def _public_ip(ip) -> bool:
    """True for a global unicast address that does not carry (or lead to) an IPv4 address through a translator."""
    if not ip.is_global or ip.is_multicast:
        return False
    if ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour or ip.teredo or any(ip in net for net in _NOT_PUBLIC_V6)):
        return False
    return True


def _resolve(host: str, seconds=None) -> list:
    """getaddrinfo for ``host``; with ``seconds`` the lookup is given only that long (a slow resolver is not waited for)."""
    if seconds is None:
        try:
            return socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        except (OSError, ValueError):
            return []
    if seconds <= 0:
        return []
    box: dict = {}

    def run():
        try:
            box["infos"] = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        except BaseException as exc:  # noqa: BLE001 - handed to the caller below
            box["error"] = exc

    worker = threading.Thread(target=run, name="maker-site-lookup", daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        return []
    error = box.get("error")
    if error is not None:
        if isinstance(error, (OSError, ValueError)):
            return []
        raise error
    return box.get("infos") or []


def _addresses(host: str, seconds=None) -> list:
    """The addresses ``host`` resolves to, or [] unless every one of them is a public address (``_public_ip``)."""
    try:
        found = [ipaddress.ip_address(info[4][0]) for info in _resolve(host, seconds)]
    except (ValueError, IndexError, TypeError):
        return []
    return found if found and all(_public_ip(ip) for ip in found) else []


def _public(host: str, seconds=None) -> bool:
    return bool(_addresses(host, seconds))


class _PinnedHTTPS(http.client.HTTPSConnection):
    """https that connects only to an address that was just checked to be public: the name is resolved again here, for every
    connection (every hop), so a name that answers differently the second time (DNS rebinding) cannot lead the read inside.
    TLS still checks the name. With a ``budget`` nothing here outlasts the read's deadline."""

    def __init__(self, *args, budget=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.budget = budget

    def _time(self):
        base = self.timeout if isinstance(self.timeout, (int, float)) else TIMEOUT
        if self.budget is None:
            return base
        left = self.budget.left()
        if left <= 0:
            raise TimeoutError("the read's deadline has passed")
        return min(base, left)

    def connect(self):
        addresses = _addresses(self.host, None if self.budget is None else max(0.0, self.budget.left()))
        if not addresses:
            raise OSError("not a public address")
        last = OSError("no address")
        for ip in addresses:
            try:
                sock = socket.create_connection((str(ip), self.port or 443), self._time())
            except OSError as exc:
                last = exc
                continue
            if self.budget is not None:
                self.budget.watch(sock)  # the TLS handshake
            try:
                self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
            except BaseException:
                sock.close()
                raise
            if self.budget is not None:
                self.budget.watch(self.sock)  # the request and the answer
            return
        raise last


class _PinnedHandler(urllib.request.HTTPSHandler):
    def __init__(self, budget=None):
        super().__init__()
        self.budget = budget

    def https_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPS, budget=self.budget), req)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect inside urllib: ``fetch`` reads the 3xx answer and decides, hop by hop (``_hop``)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _body(resp, cap: int, budget) -> bytes:
    """The answer's body, at most ``cap`` bytes. With a budget it is read in CHUNK pieces and stops at the deadline."""
    if budget is None:
        return resp.read(cap)
    out = bytearray()
    while len(out) < cap:
        if budget.left() <= 0:
            raise TimeoutError("the read's deadline has passed")
        piece = resp.read(min(CHUNK, cap - len(out)))
        if not piece:
            break
        out += piece
    return bytes(out)


def _http_get(url: str, headers: dict, timeout: float, budget=None, cap: int = MAX_BYTES):
    """(status, content type, body bytes cut at ``cap``, Location of a redirect or ""). One request, no proxy, no cookies,
    public addresses only, and no redirect followed: that is ``fetch``'s decision, one checked hop at a time. With a
    ``budget`` (every real read has one) the connection, the handshake and the body all end at its deadline."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _PinnedHandler(budget), _NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), _body(resp, cap, budget), ""
    except urllib.error.HTTPError as exc:
        return exc.code, "", b"", (exc.headers.get("Location", "") if exc.headers and exc.code in REDIRECTS else "")
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        return 0, "", b"", ""
    finally:
        if budget is not None:
            budget.release()


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


def _read(url: str, accept: str, get, live: bool, sleep, clock, rules: dict, *, robots: bool, budget: _Budget):
    """(status, content type, body) of ``url`` after at most MAX_REDIRECTS same-site redirects. EVERY request, the first and
    each hop, is held to the same rules: a public address (``live``), the site's robots.txt (for pages; ``robots``), the
    polite gap, and the read's one budget (deadline, bytes, requests). An answer that cannot be followed safely, or that
    comes after the deadline, is PageError("unreachable")."""
    cap = MAX_BYTES if robots else ROBOTS_BYTES
    for hop in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if live and not _public(parts.hostname or "", max(0.0, budget.left())):
            raise PageError("unreachable")
        if robots and not _allowed(url, get, live, sleep, clock, rules, budget):
            raise PageError("refused")
        _wait(_site(parts.hostname), sleep, clock, budget)
        timeout = budget.request()
        call = functools.partial(get, budget=budget, cap=min(cap, max(0, budget.bytes))) if live else get
        status, kind, body, *where = call(url, {"User-Agent": USER_AGENT, "Accept": accept}, timeout)
        if budget.left() <= 0:
            raise PageError("unreachable")  # an answer after the deadline is not used
        if status not in REDIRECTS:
            return status, kind, budget.take(body, cap)
        if not (where and where[0]) or hop == MAX_REDIRECTS:
            raise PageError("unreachable")
        url = _hop(url, where[0])
    raise PageError("unreachable")  # not reached: the loop returns or raises


def _allowed(url: str, get, live: bool, sleep, clock, rules: dict, budget: _Budget) -> bool:
    parts = urlsplit(url)
    if parts.netloc not in rules:  # one robots.txt per host in one read
        status, _kind, body = _read(f"https://{parts.netloc}/robots.txt", "text/plain", get, live, sleep, clock, rules,
                                    robots=False, budget=budget)
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


def fetch(url, *, get=None, sleep=time.sleep, clock=time.monotonic, today=None, cache=True, deadline=None) -> dict:
    """Read one page: {"url", "retrieved": ISO day, "blocks": [text, ...]}, or raise PageError. ``get(url, headers, timeout)``
    returns (status, content type, bytes[, redirect Location]); tests pass recorded responses, so no test touches the network.
    The whole read (robots.txt, hops, gaps, page) ends within ``deadline`` seconds (DEADLINE, never more)."""
    url = check_address(url)
    now = clock()
    cached = _CACHE.get(url) if cache else None
    if cached and now - cached[0] < (FAILED_SECONDS if isinstance(cached[1], PageError) else CACHE_SECONDS):
        if isinstance(cached[1], PageError):
            raise PageError(cached[1].code)
        return cached[1]
    live = get is None
    if live:
        get = _http_get
    budget = _Budget(clock, min(DEADLINE, DEADLINE if deadline is None else deadline))
    try:
        status, kind, body = _read(url, "text/html", get, live, sleep, clock, {}, robots=True, budget=budget)
        if status != 200 or not body:
            raise PageError("unreachable")
        if "html" not in kind.lower() and kind:
            raise PageError("unreadable")
        blocks = extract(body.decode("utf-8", "replace"))
        if not blocks:
            raise PageError("unreadable")
    except PageError as exc:
        if cache:
            _CACHE[url] = (now, exc)
        raise
    finally:
        budget.release()
    page = {"url": url, "retrieved": (today or date.today()).isoformat(), "blocks": blocks}
    if cache:
        _CACHE[url] = (now, page)
    return page


def reader(*, get=None, today=None):
    """``fn(url) -> page`` (raises PageError) that reads the network: only for use OUTSIDE a write transaction."""
    return lambda url: fetch(url, get=get, today=today)


# -- the read before the transaction (HASS-SEC-3 M2) -------------------------------------------------------------------------
_IN_TEXT = re.compile(r"(?<![\w@.:/-])(?:https://[^\s<>\"'()]+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24}(?:/[^\s<>\"'()]*)?)",
                      re.IGNORECASE)
_SITE_WORDS = re.compile(r"\b(?:site|website|web\s*site|web\s*page|webpage|page|online|url|link|www)\b", re.IGNORECASE)


def addresses_in(texts) -> list:
    """The website addresses the owner typed in ``texts`` (checked, in order, each once, at most MAX_PREFETCH). A bare name
    (harborlane.com) counts only with a path, a www. or a word like "site" in the same text, so a typo is not read."""
    out = []
    for text in texts or ():
        if not isinstance(text, str):
            continue
        cue = bool(_SITE_WORDS.search(text))
        for hit in _IN_TEXT.finditer(text):
            raw = hit.group(0).rstrip(".,;:!?)")
            if not (raw.lower().startswith(("https://", "www.")) or "/" in raw or cue):
                continue
            try:
                url = check_address(raw)
            except PageError:
                continue
            if url not in out:
                out.append(url)
    return out[:MAX_PREFETCH]


def prefetch(texts, *, today=None, clock=time.monotonic) -> dict:
    """Read every address ``addresses_in(texts)`` finds, all of them inside one DEADLINE: {address: page or PageError}.
    Called by the conversation BEFORE it opens its write transaction; never raises."""
    out: dict = {}
    start = clock()
    for url in addresses_in(texts):
        left = DEADLINE - (clock() - start)
        if left <= 0:
            out[url] = PageError("unreachable")
            continue
        try:
            out[url] = fetch(url, today=today, deadline=left)
        except PageError as exc:
            out[url] = exc
        except Exception:  # noqa: BLE001 - whatever went wrong, the owner gets the plain reply, never a crash or a hang
            out[url] = PageError("unreachable")
    return out


def prefetched(pages):
    """``ctx.maker_page`` inside the write transaction: only what ``prefetch`` read before it, never the network. An address
    that was not read before the transaction is PageError("unreachable") (the plain reply)."""
    pages = dict(pages or {})

    def read(url):
        got = pages.get(check_address(url))
        if got is None:
            raise PageError("unreachable")
        if isinstance(got, PageError):
            raise PageError(got.code)
        return got
    return read


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


# -- the facts and the story (HASS-SEC-3 H2 / L2) ------------------------------------------------------------------------
def _split(block: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"\u201c])", block) if s.strip()]


def _fold(text) -> str:
    return claims.fold(text or "")


def _name_re(name: str) -> str:
    return r"(?<![\w-])" + re.escape(name.strip()) + r"(?![\w-])"


def _without(text: str, *names) -> str:
    for name in names:
        if name and name.strip():
            text = re.sub(_name_re(name), " ", text, flags=re.IGNORECASE)
    return text


def source_ok(sentence: str, name: str, town: str = ""):
    """The page sentence, normalised, when a fact may be taken from it; None when it must be left out whole."""
    s = unicodedata.normalize("NFKC", sentence or "").strip().replace("\u2019", "'")
    if not (MIN_LEN <= len(s) <= MAX_LEN) or not s.endswith(".") or re.search(r"[!?;\"\u201c\u201d@:]|https?:|www\.", s):
        return None
    if not _without(s, name).isascii():  # a look-alike letter or an invisible character: nothing is guessed
        return None
    if re.search(r"\d", YEAR.sub("", s)) or HYPE.search(s) or live_policy._protected(s)[1]:
        return None
    rest = _without(s, name, town)
    if DROP.search(rest):  # a claim, contact, a price or words addressed to Hass or the reader
        return None
    head = re.match(r"(We|Our)\b", s)
    if FIRST_PERSON.search(s[head.end():] if head else s):
        return None
    if not (head or re.search(_name_re(name), s, re.IGNORECASE)):
        return None
    words = rest.split()
    if any(w[:1].isupper() for w in words[1:]) or (not head and words and words[0][:1].isupper()
                                                    and not re.match(_name_re(name), s, re.IGNORECASE)):
        return None  # a name of someone or somewhere else (a shop, a store, a place he did not confirm)
    return s


def _things(rest: str):
    """The plain things a maker makes, from the words after the verb: cut before a place, purpose or manner word; None
    when what is left is not a short run of plain lower-case words."""
    words = []
    for word in rest.rstrip(".").split():
        if word.rstrip(",").lower() in CUT_WORDS:
            break
        words.append(word)
    while words and words[-1].rstrip(",") in ("and", "or"):
        words.pop()
    if words:
        words[-1] = words[-1].rstrip(",")
    text = " ".join(words)
    if (not words or len(words) > NP_WORDS or len(text) > NP_CHARS or words[0] in BAD_FIRST
            or not all(NP_WORD.fullmatch(w) for w in words) or DROP.search(text)):
        return None
    return text


def facts(name: str, page: dict, *, town: str = "", today=None) -> dict:
    """{"makes": (verb, things, source), "since": (year, source), "town": (town, source)} found on the page, each from the
    first page sentence that passes ``source_ok`` and has that fact; a fact not found is missing."""
    year_now = (today or date.today()).year
    head = r"^(?:" + _name_re(name) + r"|We)\s+(?:also\s+|now\s+|still\s+)?(" + _VERB + r")\s+(.+)$"
    found: dict = {}
    for block in page.get("blocks", ()):
        for sentence in _split(block):
            s = source_ok(sentence, name, town)
            if s is None:
                continue
            if "makes" not in found and (m := re.match(head, s, re.IGNORECASE)):
                verb = m.group(1).lower()
                things = _things(m.group(2))
                if things:
                    found["makes"] = (_THIRD.get(verb, verb), things, sentence)
            if "since" not in found and re.match(r"(?:" + _name_re(name) + r"|We|Our)\b", s, re.IGNORECASE):
                hit = STARTED.search(s)
                year = int(hit.group(1) or hit.group(2)) if hit else 0
                if 1800 <= year <= year_now:
                    found["since"] = (year, sentence)
            if town and "town" not in found and re.search(_name_re(town), s, re.IGNORECASE):
                found["town"] = (town, sentence)
    return found


def draft_story(name: str, page: dict, *, said: str = "", town: str = "", today=None) -> dict | None:
    """{"sentences": [house-voice sentences written from the facts], "from": [the page sentences the facts came from]} for
    the maker, or None when the page gives nothing usable (it must say what they make). ``said`` is Mike's own words about
    the maker; a fact sentence they already carry is not said twice. ``town`` is the town he confirmed."""
    name = " ".join((name or "").split())
    if not name:
        return None
    found = facts(name, page, town=" ".join((town or "").split()), today=today)
    if "makes" not in found:
        return None
    verb, things, source = found["makes"]
    candidates = [(f"{name} {verb} {things}.", source)]
    if "since" in found:
        candidates.append((f"{name} started in {found['since'][0]}.", found["since"][1]))
    elif "town" in found:
        candidates.append((f"{name} is based in {found['town'][0]}.", found["town"][1]))
    seen, out, used = _fold(said), [], []
    for sentence, source in candidates:
        if _fold(sentence).rstrip(".") in seen or len(sentence) > MAX_LEN or HYPE.search(sentence) \
                or live_policy._protected(sentence)[1]:
            continue
        if len(" ".join([*out, sentence])) > MAX_CHARS or len(out) == MAX_SENTENCES:
            break
        out.append(sentence)
        if source not in used:
            used.append(source)
    return {"sentences": out, "from": used} if out else None


def record(page: dict, story: dict) -> dict:
    """The provenance kept privately with the story: where it was read, when, which page sentences the facts came from."""
    return {"source": page["url"], "retrieved": page["retrieved"], "from": list(story["from"]), "story": " ".join(story["sentences"])}
