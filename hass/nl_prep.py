"""HASS-NL-1: pre-processing hints for the interpreter request.

make_hinter(content) returns hinter(text, today, aliases) -> dict: facts the shop's own software works out from the owner's
words, the catalog and the Pacific calendar, so a small model does not have to guess them. The interpreter request carries
them as "hints"; the prompt tells the model to use them and that a hint never supplies a claim, a price or a quantity.

  products   each product phrase the owner wrote, resolved to ONE product ("is") or listed as "ambiguous" candidates
  makers     a maker named on its own, with its products
  shelves    a whole shelf (bread, meat, dairy ...) with its active products, so the model drafts one change each or asks
  hikes      a hike or route idea named in the message, or the scheduled hikes on a weekday the owner named
  dates      today/tomorrow/weekday/"the 29th"/"dec 5" worked out in Pacific time (an unclear day lists both readings)
  times      explicit clock times as HH:MM; numbers   spoken numbers as digits; price   money words and amounts

Pure and deterministic: no clock, no I/O, no network. Anything the matching cannot settle is left out, never guessed; a
hint that is wrong can only make the model ask, because the registry, editor and claim checks still run on every draft.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import date, timedelta

MAX_LIST, MAX_PHRASE_MATCHES, SHELF_DRAFT_MAX = 8, 25, 6
SHELVES = {"fruit": "fruit", "vegetable": "vegetables", "veggie": "vegetables", "dairy": "dairy", "egg": "eggs", "meat": "meat",
           "pantry": "pantry", "drink": "drinks", "bread": "bread", "flower": "flowers"}
NAME_STOP = frozenset("a an and at by de for from in of on or the to with".split())
MSG_STOP = frozenset("""a about actually after again all also am an and any anymore are as at back be because been before being but by
 can cancel change check checked could couldnt did do does dont down for from gave get go going gone got had has have hey hi
 done em hide hiding him her his how i if im in into is it its ive just kill know let lets like limited little look low made make
 lol theyre theres whats
 many me more my need new no not now of off ok okay on one only or other our out over pls please pull put really remove
 removing rn said say see set should show shown site so sold some stop take takes than that thats the their them then
 there these they this those through to today tomorrow tonight too u up us use want was we well went were what when where
 which who why will with would wont ya yeah yes you your youre hike hikes walk walks listing mark marked available
 availability supply stock running shelf shelves shelfs""".split())
WORD_NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
                "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "dozen": 12}
WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3,
            "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
          "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11,
          "november": 11, "dec": 12, "december": 12}
HIKE_WORD_RE = re.compile(r"\b(?:hikes?|walks?|outings?|trails?|routes?|trek|meet(?:ing)?\s?(?:up|point))\b")
RANGE_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*(?:to|-|\u2013|until|till|through)\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?(?!\d)")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
PRICE_CUE_RE = re.compile(r"\$|\b(?:bucks?|dollars?|cents?|prices?|priced|pricing|charg\w*|costs?|mark(?:ed)?\s?down|markdown|discount\w*|sale|each|per\s(?:lb|pound))\b|%\s*off")
MONEY_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)|\b(\d+(?:\.\d{1,2})?)\s*(?:bucks?|dollars?)\b|\b(\d+\.\d{2})\b")
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b\.?|\b([01]?\d|2[0-3]):([0-5]\d)\b|\b(noon|midnight)\b")
ORDINAL_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b")
MONTH_DAY_RE = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b")
DAY_MONTH_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b")
SLASH_RE = re.compile(r"\b(1[0-2]|0?[1-9])/([0-3]?\d)\b")
WEEKDAY_RE = re.compile(r"\b(?:(this|next|last|coming|on)\s+)?(" + "|".join(sorted(WEEKDAYS, key=len, reverse=True)) + r")s?\b")
RELATIVE_RE = re.compile(r"\b(today|tonight|tomorrow|tmrw|tmr|yesterday|day after tomorrow)\b")
IN_RE = re.compile(r"\bin\s+(\d{1,2}|" + "|".join(WORD_NUMBERS) + r")\s+(day|week)s?\b")
PREFIX_MIN, FUZZY_MIN, FUZZY_CUTOFF = 4, 5, 0.8
SLIPS = {"leak": "leek", "egs": "egg", "agg": "egg", "morale": "morel", "chevy": "chevre", "tumeric": "turmeric", "bok": "bok",
         "avacado": "avocado", "guac": "guacamole", "mango": "mango"}  # voice-to-text and phone slips the spelling match cannot reach


def fold(text) -> str:
    text = unicodedata.normalize("NFKD", str(text)).replace("\u2019", "'").replace("\u2018", "'")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def stem(token: str) -> str:
    if "'" in token: token = token.split("'")[0]
    if len(token) > 4 and token.endswith("ies"): return token[:-3] + "y"
    if len(token) > 3 and token.endswith("oes"): return token[:-2]
    if len(token) > 3 and token.endswith(("ches", "shes", "sses", "xes")): return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us")): return token[:-1]
    return token


def tokens(text, stop=NAME_STOP) -> list:
    return [stem(t) for t in TOKEN_RE.findall(fold(text)) if t not in stop and stem(t) not in stop]


class _Index:
    def __init__(self, content):
        self.products = []
        for p in content.products if isinstance(getattr(content, "products", None), list) else []:
            if not isinstance(p, dict) or not isinstance(p.get("id"), str): continue
            name = tokens(p.get("name") or "")
            desc = tokens(p.get("description") or "") if isinstance(p.get("description"), str) else []
            if name: self.products.append({"id": p["id"], "name": str(p.get("name")), "tokens": name, "set": frozenset(name), "head": name[-1],
                                           "desc": frozenset(desc), "status": p.get("status"), "category": p.get("category"), "maker": p.get("producerKey")})
        self.makers = []
        makers = content.makers if isinstance(getattr(content, "makers", None), dict) else {}
        for key, m in makers.items():
            name = tokens(m.get("name") if isinstance(m, dict) and m.get("name") else key)
            if name: self.makers.append({"key": str(key), "name": str(m.get("name") if isinstance(m, dict) and m.get("name") else key), "tokens": name})
        community = getattr(content, "community", None)
        community = community if isinstance(community, dict) else {}
        self.hikes = [e for e in community.get("events") or [] if isinstance(e, dict) and isinstance(e.get("id"), str)]
        self.ideas = [r for r in community.get("routeIdeas") or [] if isinstance(r, dict) and isinstance(r.get("id"), str)]
        store = getattr(content, "store", None)
        hours = store.get("hours") if isinstance(store, dict) else None
        self.hours = [h for h in hours if isinstance(h, str)] if isinstance(hours, list) else []
        self.vocab = {t for p in self.products for t in p["tokens"]} | {t for m in self.makers for t in m["tokens"]} \
            | {t for e in (*self.hikes, *self.ideas) for t in tokens(e.get("title") or "")}
        self.vocab |= set(SHELVES)
        self.vocab_list = sorted(self.vocab)

    def canon(self, token):
        """(vocabulary token, guessed): the token itself, a unique longer word it starts, or a close spelling; else (None, False)."""
        if token in self.vocab: return token, False
        if SLIPS.get(token) in self.vocab: return SLIPS[token], True
        if len(token) >= PREFIX_MIN - 1:
            longer = [v for v in self.vocab_list if v.startswith(token)]
            if len(longer) == 1: return longer[0], True
            if longer: return None, False  # several words start this way (lem: lemon, lemonade): the owner has not chosen, so no hint
        if len(token) >= FUZZY_MIN:
            close = difflib.get_close_matches(token, self.vocab_list, n=1, cutoff=FUZZY_CUTOFF)
            if close: return close[0], True
        return None, False


def _entry(p) -> dict:
    out = {"id": p["id"], "name": p["name"]}
    if p["status"] not in (None, "active"): out["status"] = p["status"]
    return out


def _decide(span, products):
    """('is'|'ambiguous', [products]) for a span of vocabulary tokens, or None when no product contains it."""
    want = frozenset(span)
    contains = [p for p in products if want <= p["set"]]
    exact = [p for p in contains if p["set"] == want]
    kind = [p for p in contains if p["head"] == span[-1] and p not in exact]
    cands = exact + kind
    if not cands:  # only a word inside names (or in none): products whose description uses the word are candidates too (coffee)
        contains = contains + [p for p in products if p not in contains and want <= p["desc"]]
    if not contains: return None
    if len(exact) == 1 and not kind: return "is", exact
    if not cands: return ("is", contains) if len(contains) == 1 else ("ambiguous", contains)
    if len(cands) == 1:  # one product of that kind; a same-shelf, same-maker sibling that merely mentions the word makes it unclear
        lone = cands[0]
        siblings = [p for p in contains if p not in cands and p["maker"] == lone["maker"] and p["category"] == lone["category"]]
        return ("ambiguous", cands + siblings) if siblings else ("is", cands)
    return "ambiguous", cands


def _spans(words, index, alias_seqs):
    """Greedy, longest first: non-overlapping (start, end, kind, data) over the vocabulary tokens of one run of words."""
    found, taken = [], [False] * len(words)
    options = []
    for i in range(len(words)):
        for j in range(len(words), i, -1):
            span = words[i:j]
            if any(w is None for w in span): continue
            options.append((j - i, 0, i, j, span))
    options.sort(key=lambda o: (-o[0], o[1], o[2]))
    for length, _, i, j, span in options:
        if any(taken[i:j]): continue
        raw = tuple(w for w in span)
        alias = next((a for a in alias_seqs if a[0] == raw), None)
        if alias is not None:
            found.append((i, j, "alias", alias[1]))
        elif len(raw) == 1 and raw[0] in SHELVES:
            found.append((i, j, "shelf", None))
        else:
            decision = _decide(list(raw), index.products)
            maker = next((m for m in index.makers if m["tokens"] == list(raw)), None)
            if maker is not None and (decision is None or decision[0] == "ambiguous" or len(raw) < max(len(p["tokens"]) for p in decision[1])):
                found.append((i, j, "maker", maker))
            elif decision is not None and not (len(raw) == 1 and len(decision[1]) > MAX_PHRASE_MATCHES):
                found.append((i, j, decision[0], decision[1]))
            else:
                continue
        for k in range(i, j): taken[k] = True
    return sorted(found)


def _shelf_of(span):
    return SHELVES.get(span[0]) if len(span) == 1 else None


def phrase_hints(text, index, aliases) -> dict:
    """products / makers / shelves for the phrases in ``text``."""
    tokens_ = [stem(t) for t in TOKEN_RE.findall(fold(text))]
    raw = TOKEN_RE.findall(fold(text))
    alias_seqs = []
    for a in aliases or []:
        if isinstance(a, dict) and isinstance(a.get("name"), str):
            seq = tuple(tokens(a["name"], stop=NAME_STOP | {"the"}))
            if seq: alias_seqs.append((seq, a))
    alias_words = {w for seq, _ in alias_seqs for w in seq}  # an alias word is read as written, in the catalog or not
    canon, guessed = [], []
    for original, token in zip(raw, tokens_):
        if original in MSG_STOP or token in MSG_STOP or original in NAME_STOP or token in NAME_STOP:
            canon.append("")
            guessed.append(False)
            continue
        word, guess = (token, False) if token in alias_words else index.canon(token)
        canon.append(word)
        guessed.append(guess)
    products, makers, shelves, said = [], [], [], {}
    run = []
    for k in range(len(canon) + 1):
        if k < len(canon) and canon[k] != "":
            run.append(k)
            continue
        if run:
            words = [canon[x] for x in run]
            for i, j, kind, data in _spans(words, index, alias_seqs):
                phrase = " ".join(raw[x] for x in run[i:j])
                span = words[i:j]
                fuzzy = any(guessed[x] for x in run[i:j])
                if kind == "shelf":
                    shelf = SHELVES[span[0]]
                    members = [p for p in index.products if p["category"] == shelf and p["status"] == "active"]
                    if len(members) == 1: products.append({"said": phrase, "is": _entry(members[0])})
                    elif members: shelves.append({"said": phrase, "shelf": shelf, "count": len(members), "products": [_entry(p) for p in members][:MAX_LIST * 3]})
                    continue
                if kind == "maker":
                    members = [p for p in index.products if p["maker"] == data["key"]]
                    makers.append({"said": phrase, "key": data["key"], "name": data["name"], "products": [_entry(p) for p in members][:MAX_LIST],
                                   **({"more": len(members) - MAX_LIST} if len(members) > MAX_LIST else {})})
                elif kind == "alias":
                    pid_ = data.get("id")
                    hit = next((p for p in index.products if p["id"] == pid_), None) if data.get("kind") == "product" else None
                    if hit: products.append({"said": phrase, "is": _entry(hit), "alias": True})
                    elif data.get("kind") == "maker": makers.append({"said": phrase, "key": data.get("id"), "alias": True})
                elif kind == "is":
                    products.append({"said": phrase, "is": _entry(data[0]), **({"spelling": "guessed"} if fuzzy else {})})
                else:
                    products.append({"said": phrase, "ambiguous": [_entry(p) for p in data][:MAX_LIST], **({"more": len(data) - MAX_LIST} if len(data) > MAX_LIST else {}),
                                     **({"spelling": "guessed"} if fuzzy else {})})
        run = []
    out = {}
    if products: out["products"] = products[:MAX_LIST]
    if makers: out["makers"] = makers[:MAX_LIST]
    if shelves: out["shelves"] = shelves[:3]
    return out


# -- hikes -------------------------------------------------------------------------------------------------------------
def hike_hints(text, index, today: date, weekday_hits) -> dict:
    words = {stem(t) for t in TOKEN_RE.findall(fold(text)) if t not in MSG_STOP and t not in NAME_STOP}
    out = []
    for e in index.hikes:
        title = set(tokens(e.get("title") or "")) - {"walk", "hike"}
        if title and title <= words:
            out.append({"hike": e["id"], "title": e.get("title"), "startsAt": e.get("startsAt"), "status": e.get("status")})
    ideas = [{"routeIdea": r["id"], "title": r.get("title")} for r in index.ideas if (set(tokens(r.get("title") or "")) - {"walk", "hike"}) and set(tokens(r.get("title") or "")) <= words]
    rows = []
    for name, wd in weekday_hits if HIKE_WORD_RE.search(fold(text)) or out or ideas else ():  # a weekday alone is not about hikes
        on = [e for e in index.hikes if e.get("status") == "scheduled" and _weekday_of(e.get("startsAt")) == wd]
        if on: rows.append({"said": name, "scheduled hikes": [{"hike": e["id"], "title": e.get("title"), "startsAt": e.get("startsAt")} for e in on][:MAX_LIST]})
    result = {}
    if out or ideas: result["named"] = (out + ideas)[:MAX_LIST]
    if rows: result["onThatWeekday"] = rows
    return result


def _weekday_of(starts_at):
    try: return date.fromisoformat(str(starts_at)[:10]).weekday()
    except ValueError: return None


# -- dates, times, numbers, prices ---------------------------------------------------------------------------------------
def _next_weekday(today: date, wd: int, include_today=False) -> date:
    delta = (wd - today.weekday()) % 7
    return today + timedelta(days=delta if (delta or include_today) else 7)


def _safe_date(year, month, day):
    try: return date(year, month, day)
    except ValueError: return None


def date_hints(text, today: date):
    """(rows, [(said weekday, weekday number)]): every day the message names, in Pacific time (``today`` is the Pacific day)."""
    t, rows, hits = fold(text), [], []
    day = lambda d: d.isoformat()  # noqa: E731
    for m in RELATIVE_RE.finditer(t):
        word = m.group(1)
        d = {"today": 0, "tonight": 0, "tomorrow": 1, "tmrw": 1, "tmr": 1, "yesterday": -1, "day after tomorrow": 2}[word]
        rows.append({"said": word, "date": day(today + timedelta(days=d)), "weekday": WEEKDAY_NAMES[(today + timedelta(days=d)).weekday()]})
    for m in WEEKDAY_RE.finditer(t):
        mod, name = m.group(1), m.group(2)
        wd = WEEKDAYS[name]
        hits.append((name, wd))
        nxt, last = _next_weekday(today, wd), today - timedelta(days=((today.weekday() - wd) % 7) or 7)
        said = f"{mod} {name}" if mod and mod != "on" else name
        if mod == "next" or wd == today.weekday() and mod != "last":
            options = [nxt, nxt + timedelta(days=7)] if mod == "next" and wd != today.weekday() else [today, today + timedelta(days=7)]
            rows.append({"said": said, "unclear": [day(d) for d in options], "weekday": WEEKDAY_NAMES[wd], "note": "two readings; ask which unless the owner said"})
        elif mod == "last":
            rows.append({"said": said, "date": day(last), "weekday": WEEKDAY_NAMES[wd]})
        else:
            rows.append({"said": said, "next": day(nxt), "last": day(last), "weekday": WEEKDAY_NAMES[wd], "note": "next = the coming one; last = the one just past"})
    for m in ORDINAL_RE.finditer(t):
        n = int(m.group(1))
        if not 1 <= n <= 31: continue
        d = _safe_date(today.year, today.month, n)
        if d is None or d < today:
            nm = (today.month % 12) + 1
            d = _safe_date(today.year + (today.month == 12), nm, n)
        if d is not None and not MONTH_DAY_RE.search(t[max(0, m.start() - 12):m.end()]) and not DAY_MONTH_RE.search(t[m.start():m.end() + 14]):
            rows.append({"said": m.group(0), "date": day(d), "weekday": WEEKDAY_NAMES[d.weekday()]})
    for m in MONTH_DAY_RE.finditer(t):
        d = _safe_date(today.year, MONTHS[m.group(1)], int(m.group(2)))
        if d is not None and d < today: d = _safe_date(today.year + 1, MONTHS[m.group(1)], int(m.group(2)))
        if d is not None: rows.append({"said": m.group(0), "date": day(d), "weekday": WEEKDAY_NAMES[d.weekday()]})
    for m in DAY_MONTH_RE.finditer(t):
        d = _safe_date(today.year, MONTHS[m.group(2)], int(m.group(1)))
        if d is not None and d < today: d = _safe_date(today.year + 1, MONTHS[m.group(2)], int(m.group(1)))
        if d is not None: rows.append({"said": m.group(0), "date": day(d), "weekday": WEEKDAY_NAMES[d.weekday()]})
    for m in SLASH_RE.finditer(t):
        d = _safe_date(today.year, int(m.group(1)), int(m.group(2)))
        if d is not None and d < today: d = _safe_date(today.year + 1, int(m.group(1)), int(m.group(2)))
        if d is not None: rows.append({"said": m.group(0), "date": day(d), "weekday": WEEKDAY_NAMES[d.weekday()]})
    for m in IN_RE.finditer(t):
        n = int(m.group(1)) if m.group(1).isdigit() else WORD_NUMBERS[m.group(1)]
        d = today + timedelta(days=n * (7 if m.group(2) == "week" else 1))
        rows.append({"said": m.group(0), "date": day(d), "weekday": WEEKDAY_NAMES[d.weekday()]})
    if re.search(r"\b(next week|this weekend|next month|couple (?:of )?(?:days|weeks)|few (?:days|weeks)|sometime|soon)\b", t):
        rows.append({"said": "a loose time", "date": None, "note": "not one day: ask which day"})
    return rows[:MAX_LIST], hits


def time_hints(text) -> list:
    out = []
    for m in TIME_RE.finditer(fold(text)):
        if m.group(6):
            out.append({"said": m.group(0), "time": "12:00" if m.group(6) == "noon" else "00:00"})
        elif m.group(3):
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            if 1 <= hour <= 12 and minute < 60:
                out.append({"said": m.group(0).strip(), "time": f"{hour % 12 + (12 if m.group(3) == 'p' else 0):02d}:{minute:02d}"})
        else:
            out.append({"said": m.group(0), "time": f"{int(m.group(4)):02d}:{m.group(5)}"})
    return out[:MAX_LIST]


def number_hints(text) -> list:
    return [{"said": w, "value": WORD_NUMBERS[w]} for w in TOKEN_RE.findall(fold(text)) if w in WORD_NUMBERS and w != "one"][:MAX_LIST]


def price_hints(text):
    t = fold(text)
    if not PRICE_CUE_RE.search(t): return None
    amounts = [next(g for g in m.groups() if g) for m in MONEY_RE.finditer(t)]
    return {"mentioned": True, "amounts": amounts[:MAX_LIST]}


def _clock(hour, minute, mark):
    return f"{hour % 12 or 12}{':' + minute if minute and minute != '00' else ''}{mark}"


def asked_range(text):
    """('9am', '5pm') for "9 to 5", "8:30-4pm" and the like (a bare end before the start is the afternoon); else None."""
    m = RANGE_RE.search(fold(text))
    if not m: return None
    h1, m1, a1, h2, m2, a2 = int(m.group(1)), m.group(2), m.group(3), int(m.group(4)), m.group(5), m.group(6)
    if not (1 <= h1 <= 12 and 1 <= h2 <= 12): return None
    a1, a2 = (a1 or "")[:1], (a2 or "")[:1]
    if not a2 and not a1: a1, a2 = ("a" if h1 >= 6 else "p"), ("p" if h2 <= 8 or h2 < h1 else "a")
    elif not a2: a2 = "p" if a1 == "a" and h2 < h1 else a1
    elif not a1: a1 = "a" if h1 <= h2 or a2 == "p" else "p"
    return _clock(h1, m1, a1 + "m"), _clock(h2, m2, a2 + "m")


def _day_shows(index, wd, asked):
    """The Store line text for weekday ``wd`` when it shows exactly ``asked``, else None."""
    for line in index.hours:
        for part in line.split("\u00b7"):
            m = re.match(r"\s*([A-Za-z]+)(?:\s*[\u2013-]\s*([A-Za-z]+))?\s+(.+?)\s*$", part)
            if not m: continue
            first = next((i for i, n in enumerate(WEEKDAY_NAMES) if n.lower().startswith(m.group(1).lower()[:3])), None)
            last = first if m.group(2) is None else next((i for i, n in enumerate(WEEKDAY_NAMES) if n.lower().startswith(m.group(2).lower()[:3])), None)
            if first is None or last is None or not first <= wd <= last: continue
            shown = re.sub(r"\s*[\u2013-]\s*", "\u2013", m.group(3).lower().replace(" ", ""))
            if shown == f"{asked[0]}\u2013{asked[1]}": return m.group(3)
    return None


def hours_hints(text, index):
    """The Store already shows EVERY day and hours the owner asks for: a fact for "it already says that", never a draft.
    Each day is matched to its own range (the nearest one); any change not already true, or any pairing in doubt, gives no hint."""
    t = fold(text)
    ranges = [(m.start(), m.end(), asked_range(m.group(0))) for m in RANGE_RE.finditer(t)]
    days = [(m.start(), m.end(), WEEKDAYS[m.group(2)]) for m in WEEKDAY_RE.finditer(t)]
    if not (ranges and days and index.hours) or any(r[2] is None for r in ranges): return None
    same, used = [], set()
    for start, end, wd in days:
        dist = sorted((max(r[0] - end, start - r[1], 0), k) for k, r in enumerate(ranges))
        if len(dist) > 1 and dist[0][0] == dist[1][0]: return None  # equally near two ranges: cannot tell which is meant
        k = dist[0][1]
        shown = _day_shows(index, wd, ranges[k][2])
        if shown is None: return None  # this day is asked to change (or is not on the Store)
        used.add(k)
        same.append(f"{WEEKDAY_NAMES[wd]} already {shown}")
    if len(used) != len(ranges): return None  # a requested range no day was matched to
    return list(dict.fromkeys(same)) or None


def make_hinter(content):
    """hinter(text, today: date, aliases=None) -> dict (empty when there is nothing to say; never raises)."""
    index = _Index(content)

    def hinter(text, today: date, aliases=None) -> dict:
        try:
            out = phrase_hints(text, index, aliases)
            dates, weekdays = date_hints(text, today)
            hikes = hike_hints(text, index, today, weekdays)
            if hikes.get("named") and out.get("products"):  # "cass hill" in a hike message is the hike, not the product of that name
                titles = [set(tokens(n.get("title") or "")) for n in hikes["named"]]
                out["products"] = [p for p in out["products"] if not any(set(tokens(p["said"])) <= t for t in titles)]
                if not out["products"]: del out["products"]
            for key, value in (("alreadyTrue", hours_hints(text, index)), ("hikes", hikes), ("dates", dates), ("times", time_hints(text)), ("numbers", number_hints(text)), ("price", price_hints(text))):
                if value: out[key] = value
            return out
        except Exception:  # noqa: BLE001 - a hint is a convenience; the request still goes out without it
            return {}
    return hinter
