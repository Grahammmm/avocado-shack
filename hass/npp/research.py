"""S4: locate one official maker site, return typed evidence, never public prose.

Call outside the state transaction with independently resolved public fields,
not Work.request or an owner message. NPP-G owns scheduling and receipt storage;
NPP-E owns rendering and the existing publication gates.
"""
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from itertools import islice
import json
import re
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

from hass import claims, cloud_codex, maker_site

ASSETS = "hass-maker-research/"
STORY = frozenset({"makes", "founded", "nature"})
BASE = re.compile(r"\b(?:based|located|headquartered) in ([^.!?;]+)", re.I)
THIRD_PARTY = re.compile(r"\b(?:vendors?|directory|marketplace|stockists?|resellers?|retailers?|reviews?)\b", re.I)
# Words that make the owner of a page a seller or a directory rather than the maker. The owner entity may
# be the maker's name plus descriptors ("Miners Orchards"), never plus one of these ("Miners Shop").
SELLER = re.compile(
    r"\b(?:shops?|stores?|markets?|marts?|outlets?|emporiums?|depots?|boutiques?|malls?|retail\w*|resell\w*|dealers?|"
    r"distribut\w+|wholesal\w+|trading|suppl(?:y|ies|iers?)|sellers?|merchants?|traders?|importers?|brokers?|agency|"
    r"agents?|affiliates?|fans?|unofficial|vendors?|directory|marketplace|stockists?)\b")
# Page text that says the page is not the maker's own. Checked on folded text; {name} is the folded maker name.
CONTRARY = (
    r"\b(?:un)?affiliated\b",
    r"\bnot (?:\w+ )?(?:affiliated|associated|endorsed|sponsored|owned|operated|run|connected|official)\b",
    r"\b(?:no|without) (?:\w+ )?(?:affiliation|association|connection|endorsement)\b",
    r"\bunofficial\b|\bfan[- ]?(?:site|page|made|run)\b",
    r"\b(?:independent(?:ly)?|third[- ]party|authori[sz]ed|licensed) (?:\w+ ){0,2}"
    r"(?:shops?|stores?|retail\w*|resell\w*|dealers?|sellers?|stockists?|distribut\w+|merchants?|marketplace|"
    r"directory|reviews?|blog|website|site)\b",
    r"\b(?:shop|store|retailer|reseller|dealer|stockist|distributor|merchant|marketplace|directory) "
    r"(?:for|of|selling|that sells|which sells|specializ\w+)\b",
    r"\b(?:sells?|selling|sold|stocks?|stocking|carr(?:y|ies|ying)|resell\w*|retail\w*|offers?|offering|"
    r"distribut\w+|supplies|supplying) [^.!?]{0,60}(?<![\w-]){name}(?![\w-])",
    r"(?<![\w-]){name}(?![\w-])(?: \w+){0,3} (?:products?|goods|brands?) (?:are |is )?(?:available|sold|stocked)\b",
)
ABOUT = re.compile(r"(?:^|/)(?:about(?:-us)?|(?:our|the)-story|who-we-are)/?$", re.I)
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())


@dataclass
class Page:
    url: str
    retrieved: str
    titles: list = field(default_factory=list)
    ownership: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    about: list = field(default_factory=list)


class _Visible(HTMLParser):
    """Read static semantic text, never JS, description metadata or hidden subtrees."""
    def __init__(self, page):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if len(self.stack) >= 128:
            raise ValueError("page nesting limit")
        attrs = dict(attrs)
        parent = self.stack[-1][1] if self.stack else "body"
        style = re.sub(r"\s+", "", attrs.get("style") or "").lower()
        classes = set((attrs.get("class") or "").lower().split())
        if (parent == "hidden" or "hidden" in attrs or "inert" in attrs
                or (attrs.get("aria-hidden") or "").lower() == "true"
                or classes & {"hidden", "d-none", "sr-only", "visually-hidden"}
                or any(word in style for word in ("display:none", "visibility:hidden", "opacity:0"))
                or tag in (maker_site.SKIP_TAGS - {"header", "footer", "nav"}) | {"dialog", "details", "iframe"}):
            region = "hidden"
        elif tag in {"head", "footer", "nav"} and parent == "body":
            region = tag
        else:
            region = parent
        if region == "head" and tag == "meta" and attrs.get("property") == "og:site_name":
            self.page.titles.append(attrs.get("content") or "")
        if region in {"nav", "body"} and tag == "a" and (href := attrs.get("href")) and len(href) <= 200:
            if ABOUT.search(href):
                self.page.about.append(href)
        if tag not in VOID:
            self.stack.append((tag, region, []))

    def handle_startendtag(self, tag, attrs):
        # In HTML a slash does not close a non-void element. In particular,
        # <div hidden/> must not make its following contents evidence.
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if not self.stack or self.stack[-1][1] == "hidden":
            return
        region = self.stack[-1][1]
        for tag, ancestor_region, text in reversed(self.stack):
            if region != ancestor_region:
                break
            if tag == "footer":
                text.append(data)
                break
            if tag in maker_site.BLOCK_TAGS | {"title"}:
                text.append(data)
                break

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                _, region, text = self.stack[i]
                del self.stack[i:]
                break
        else:
            return
        if not (value := " ".join("".join(text).split())):
            return
        if region == "head" and tag == "title" or region == "body" and tag == "h1":
            self.page.titles.append(value)
        if region == "body":
            self.page.blocks.append(value)
        elif region == "footer" and tag == "footer":
            self.page.ownership.append(value)


def parse_page(url, retrieved, markup):
    page = Page(url, retrieved)
    parser = _Visible(page)
    parser.feed(markup[:maker_site.MAX_BYTES])
    parser.close()
    return page


def _url(raw):
    if (not isinstance(raw, str) or not raw.lower().startswith("https://")
            or "\\" in raw or any(ch.isspace() or ord(ch) < 32 for ch in raw)):
        return None
    try:
        url = maker_site.check_address(raw)
        parts = urlsplit(url)
        if not parts.query and len(url) <= 200:
            return url
    except maker_site.PageError:
        pass
    return None


def _site(url):
    # Exact host (with only a www alias), deliberately narrower than a registrable-domain guess.
    return urlsplit(url).hostname.removeprefix("www.")


def _about_links(page, domain):
    for href in page.about:
        try:
            url = _url(urljoin(page.url, href))
        except ValueError:
            continue
        if url and _site(url) == domain:
            yield url


def _has(text, value):
    return bool(re.search(r"(?<![\w-])" + re.escape(claims.fold(value)) + r"(?![\w-])", claims.fold(text)))


def _identity_field(value):
    # The caller supplies a dedicated provenance-bearing slot, never a whole caption.
    return (isinstance(value, str) and 0 < len(value) <= 80 and len(value.split()) <= 8
            and all(ch.isalpha() or ch in " .&'-’" for ch in value) and bool(claims.fold(value))
            and not cloud_codex.till_like(value))


def _owner(entity, name):
    """True when the claimed owner entity is the maker: its name plus, at most, non-seller descriptors."""
    return _has(entity, name) and not SELLER.search(re.sub(re.escape(claims.fold(name)), " ", claims.fold(entity)))


def _contrary(page, name):
    # The page's own words can contradict its identity: a shop, directory or fan page says so in visible text.
    patterns = [re.compile(p.replace("{name}", re.escape(claims.fold(name)))) for p in CONTRARY]
    return any(p.search(claims.fold(text)) for text in (*page.blocks, *page.ownership) for p in patterns)


def _own_site(page, name, town, markers):
    if not any(_has(title, name) for title in page.titles):
        return "name-mismatch"
    if THIRD_PARTY.search(urlsplit(page.url).path.replace("-", " ")) or any(THIRD_PARTY.search(t) for t in page.titles):
        return "not-the-makers-own-site"
    # A name mentioned in a copyright line is insufficient: the owner of the copyright must be the maker
    # itself (not a shop that merely contains its name), corroborated by the site's own identity and
    # uncontradicted by anything the page says about itself.
    for footer in page.ownership:
        match = re.search(r"(?:©|\bcopyright\b)\s*(?:\d{4}(?:\s*[-–]\s*\d{4})?\s*)?([^.!?©|]+)", footer, re.I)
        if match and _owner(match[1], name) and any(claims.fold(match[1]) == claims.fold(t) for t in page.titles):
            break
    else:
        if page.ownership or not ABOUT.search(urlsplit(page.url).path) or not any(
            (match := re.fullmatch(r"(?:We are|This is) ([^.?!]+)[.]", block, re.I))
            and _owner(match[1], name) and any(claims.fold(match[1]) == claims.fold(t) for t in page.titles)
            for block in page.blocks
        ):
            return "not-the-makers-own-site"
    if _contrary(page, name):
        return "not-the-makers-own-site"
    if not any(_has(block, name) for block in page.blocks):
        return "name-mismatch"
    if town:
        current = [s for b in page.blocks for s in maker_site._split(b) if not markers.search(s)]
        bases = [m[1].strip() for s in current if (m := BASE.search(s))]
        # Also recognize the simple geography used on small producers' home pages.
        # Match capitalized place names only, not a phrase such as 'in copper pots'.
        for sentence in current:
            if _has(sentence, name) and (match := re.search(r"\bin ([A-Z][a-z]+(?: [A-Z][a-z]+)*)(?=[,.!?]|$)", sentence)):
                bases.append(match[1])
        if any(claims.fold(b.split(',')[0]) != claims.fold(town) for b in bases):
            return "different-base-town"
        if not any(_has(s, town) for s in current):
            return "town-unconfirmed"
    return "official"


def _markers(schema):
    words = set(schema["negation_hedge_markers"]) | maker_site.NOT_SAID | {"ignore", "instructions", "prompt", "pretend"}
    # 'about' alone is a normal heading. Ambiguous uses still need entailment.
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, sorted(words - {"about"}))) + r")(?!\w)", re.I)


def _check(row, pages, name, town, schema, markers):
    page = pages.get(row["url"])
    slot, value, quote = row["slot"], row["value"], row["quote"]
    if not page:
        return "unverified-url"
    blocks = [block for block in page.blocks if quote in block]
    if not blocks:
        return "quote-not-in-visible-body-text"
    if markers.search(quote) or any(markers.search(block) for block in blocks):
        return "negation-past-or-hedge-marker"
    if not all(_has(block, name) for block in blocks):
        return "quote-does-not-name-maker"
    if not any(quote.rstrip(".") == sentence.rstrip(".") for block in blocks for sentence in maker_site._split(block)):
        return "fragment-without-context"
    if not claims.fold(value) or not _has(quote, value):
        return "value-not-in-quote"
    if slot == "name" and not (any(claims.fold(value) == claims.fold(t) for t in page.titles) and _has(value, name)):
        return "invalid-name"
    if slot == "town" and town and claims.fold(town) != claims.fold(value):
        return "invalid-town"
    if slot == "founded" and not (re.fullmatch(r"[0-9]{4}", value) and 1800 <= int(value) <= date.fromisoformat(page.retrieved).year):
        return "invalid-year"
    if slot == "nature" and value not in schema["nature_enum"]:
        return "invalid-nature"
    if slot == "makes" and (len(value.split()) > 6 or not maker_site._exact_things(value.lower())):
        return "invalid-product-type"
    if slot in {"name", "town"} and not _identity_field(value):
        return "invalid-identity-value"
    return None


def _rows(result, schema):
    props = schema["properties"]["facts"]
    fields = props["items"]["properties"]
    if not isinstance(result, dict) or set(result) != {"facts"} or not isinstance(result["facts"], list):
        return None
    rows = result["facts"]
    if len(rows) > props["maxItems"] or not all(
        isinstance(row, dict) and set(row) == set(fields) and all(
            isinstance(row[k], str) and spec.get("minLength", 1) <= len(row[k]) <= spec.get("maxLength", 80)
            and ("enum" not in spec or row[k] in spec["enum"]) for k, spec in fields.items()
        ) for row in rows
    ):
        return None
    return rows


@dataclass(frozen=True)
class Result:
    facts: tuple
    receipt: dict

    @property
    def story_facts(self):
        return tuple(fact for fact in self.facts if fact["slot"] in STORY)


def research(pinned, *, search, fetch, extract, verify, owner_maker="", owner_town="", owner_url="",
             label_brand="", label_confidence=0.0, known=False, clock=time.monotonic, budget=None):
    """Search(query, limit, seconds) -> URLs; fetch(url, seconds) -> Page.

    Extract(name, {url: visible blocks}, seconds) -> {'facts': [...]};
    verify(name, slot, value, quote, seconds) -> verdict. Ports honor timeout.
    'known' is the caller's exact local catalog resolution, not a fuzzy hint.
    Owner fields already said and confirmed are used by the caller directly;
    this result only supplies verified official-site evidence, never a public URL.
    """
    pins, files, _ = pinned
    sources = json.loads(files[ASSETS + "sources.json"])
    schema = json.loads(files[ASSETS + "facts.schema.json"])
    markers = _markers(schema)
    locate = sources["discovery"]["search"]
    limits = pins["steps"]
    seconds = sources["fetch"]["stage_budget_seconds"]
    end = clock() + min(seconds, seconds if budget is None else budget)
    receipt: dict[str, Any] = {"queries": [], "identity": [], "pages": [], "facts": []}

    def finish(reason, facts=()):
        receipt["outcome"] = reason
        return Result(tuple(facts), receipt)

    def left(cap):
        return max(0, min(end - clock(), cap))

    def read(url):
        if not (remaining := left(maker_site.DEADLINE)):
            return None
        try:
            page = fetch(url, remaining)
        except (OSError, ValueError, maker_site.PageError):
            return None
        if page and _url(page.url) == page.url and _site(page.url) == _site(url) and clock() < end:
            receipt["pages"].append({"url": page.url, "retrieved": page.retrieved})
            return page
        return None

    if known:
        return finish("known-maker")
    if not (pins["research"]["locate_official_site"] and pins["research"]["search_only_to_locate"]):
        return finish("research-disabled")
    label = label_brand if label_confidence >= sources["discovery"]["seed"]["label_brand_min_confidence"] else ""
    if owner_maker and label and set(claims.fold(owner_maker).split()).isdisjoint(claims.fold(label).split()):
        return finish("label-mismatch")
    name, town = owner_maker or label, owner_town
    if not _identity_field(name) or (town and not _identity_field(town)):
        return finish("no-safe-identity-seed")
    receipt["seed"] = {"name": name, "source": "owner" if owner_maker else "label", "town": town}
    candidates = {}

    def candidate(raw):
        if not (url := _url(raw)):
            return
        domain = _site(url)
        if any(domain == d or domain.endswith("." + d) for d in sources["deny_domains"]):
            receipt["identity"].append({"url": url, "passed": False, "reason": "denied-domain"})
        else:
            candidates.setdefault(domain, url)

    if owner_url:
        candidate(owner_url)
    elif locate["enabled"]:
        for entry in sources["allowlist"]:
            if entry["maker"] == claims.fold(name) and entry["added_by"] == "G" and entry["reviewed_in"]:
                candidate("https://" + entry["domain"] + "/")
        for query in dict.fromkeys(" ".join(form.format(maker=name, town=town).split())
                                   for form in locate["query_forms"][:locate["max_queries"]]):
            if not (remaining := left(5)):
                return finish("deadline")
            receipt["queries"].append(query)
            try:
                for url in islice(search(query, locate["max_results_per_query"], remaining), locate["max_results_per_query"]):
                    candidate(url)
            except (OSError, ValueError, maker_site.PageError):
                return finish("search-unavailable")
    passing = []
    for domain, url in islice(candidates.items(), locate["max_candidates_checked"]):
        page = read(url)
        reason = _own_site(page, name, town, markers) if page else "page-unavailable"
        receipt["identity"].append({"url": url, "passed": reason == "official", "reason": reason})
        if reason == "official":
            passing.append((domain, page))
    if len(passing) != 1 or not left(seconds):
        return finish("two-passing-domains" if len(passing) > 1 else "no-confirmed-site")
    domain, page = passing[0]
    receipt["chosen_domain"] = domain
    pages = {page.url: page}
    # Do not try more pages if the candidate checks already consumed the read budget.
    extras = max(0, sources["fetch"]["pages_max"] - min(len(candidates), locate["max_candidates_checked"]))
    for url in islice((u for u in dict.fromkeys(_about_links(page, domain)) if u not in pages), extras):
        also = read(url)
        if also and _own_site(also, name, town, markers) == "official":
            pages[also.url] = also
    inputs = {u: tuple(p.blocks) for u, p in pages.items()}
    try:
        rows = _rows(extract(name, inputs, left(limits["research_extract"]["timeout_s"])), schema) if left(seconds) else None
    except (OSError, ValueError):
        rows = None
    if rows is None:
        return finish("extraction-unavailable")
    supported = {}
    # Verify story slots first so incidental identity suggestions cannot exhaust the budget first.
    for row in sorted(rows, key=lambda fact: fact["slot"] not in STORY):
        audit: dict[str, Any] = dict(row, verifier=None, kept=False)
        receipt["facts"].append(audit)
        if (reason := _check(row, pages, name, town, schema, markers)) is not None:
            audit["reason"] = reason
            continue
        if not (remaining := left(limits["research_verify"]["timeout_s"])):
            audit["reason"] = "deadline"
            continue
        try:
            verdict = verify(name, row["slot"], row["value"], row["quote"], remaining)
        except (OSError, ValueError):
            verdict = None
        audit["verifier"] = verdict if verdict in schema["verdicts"] else None
        if audit["verifier"] != "supports" or not left(seconds):
            audit["reason"] = "not-verified"
            continue
        supported.setdefault(row["slot"], []).append(audit)
    facts = []
    for slot, rows in supported.items():
        if len({claims.fold(row["value"]) for row in rows}) != 1:
            for row in rows:
                row["reason"] = "conflicting-values"
            continue
        for row in rows:
            row.update(kept=True, reason="verified")
        row = rows[0]
        facts.append({**{k: row[k] for k in ("slot", "value", "url", "quote")},
                      "id": f"official-{slot}", "retrieved": pages[row["url"]].retrieved})
    return finish("story-facts" if any(f["slot"] in STORY for f in facts) else "maker story not found", facts)
