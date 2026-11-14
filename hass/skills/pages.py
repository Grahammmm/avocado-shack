"""Page-text skills (SKILLS-SHOP-1): the home headline and intro, the store story, the home-page photo.

    page.home   the two-line headline and the intro line on the home page (or put the shop's own words back)
    page.about  the "COME ON IN" story, the only About text the site has (a maker's story is the makers skill)
    page.photo  the one photo at the top of the home page (or put the shop's own photo back)

The site is one home page and the hike page. There is no About page and no FAQ page (``page.faq`` is the refusal in
hass/skills/backlog.py). Plans use only existing ops (``store.set_headline``, ``store.set_intro``, ``store.set_story``,
``store.set_home_image``, ``store.clear_home_image``) and raise ``hass.skills.shop.SkillStop`` for a question or a refusal,
exactly as the shop skills do (see that module for what a plan may read). Spec: reports/hass/SKILLS-SPEC.md 3.23 to 3.25.
The home photo keeps today's behaviour in v1 (metadata removed, the owner's pixels): no house render (decision D6).
Owner guide: docs/hass/skills/shop.md.
"""
from __future__ import annotations

import re

from hass import media
from hass.claims import NEGATORS, fold
from hass.content_model import DEFAULT_HEADLINE, DEFAULT_INTRO, DEFAULT_STORY, MAX_HEADLINE_LINE, MAX_INTRO, MAX_STORY
from hass.ops import photos
from hass.ops.store import _line_key, _spaced
from hass.skills.model import Skill, Slot, Trigger, Undo
from hass.skills.shop import SkillStop, letters, price_problem, store_of, texts_of

_CASES = "hass/tests/fixtures/skills/pages/{}.jsonl"
_INDEX = "storefront-mockup/index.html"
STORE_FILE = "hass/content/store.json"

# a word the owner has to have said himself: a superlative, an award, an origin or a certificate (spec 3.23, 3.24)
CLAIM_RE = re.compile(r"\b(?:best|number one|finest|greatest|top[- ]rated|award[- ]winning|world[- ]class|famous|family[- ]owned|"
                      r"since \d{4})\b|#1", re.I)  # origin, organic and health words are the claims gate's (hass/claims.py)

HEADLINE_ASK = "What should the two lines say?"
SECOND_LINE_ASK = "What should the second line say?"
INTRO_ASK = "What should the intro say?"
STORY_ASK = "What should the story say?"
HOME_ASK = "What should the headline or the intro say?"
RESET_WHAT = "Do you want the headline back, or the intro?"
ABOUT_MAXED = f"That is a bit long. Could you shorten it to {MAX_STORY} characters or fewer?"
ONE_PARAGRAPH = "The story is one paragraph. Could you send it as one paragraph?"
ALREADY = "It already says that. Did you mean something else?"
CLAIM_REPLY = "I can only use words like “{word}” if you say them yourself. What should it say?"
PHOTO_ASK = "Send me the photo you want on the home page."
ALT_ASK = "What does the photo show?"
ALT_REPLY = "Tell me what the photo shows, in a few words, like “the shop front on a sunny morning”."
NO_OWN_PHOTO = "There is no photo of yours on the home page, so there is nothing to put back."
PHOTO_DESTINATION = "Is it for the home page or for a product?"
PHOTO_OR_RESET = "Do you want the home page photo changed, or put back the way it was? I can only do one."


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _price_stop(*values):
    for value in values:
        if (problem := price_problem(value)):
            return SkillStop(problem, "refused", "price")
    return None


# a colon does not end a clause: "Don't say: best" and "Remove this word: best" keep the rejection with their word
_CLAUSE = re.compile(r"[.!?;\n]")


def _negator(word: str) -> bool:
    return word in NEGATORS or word.endswith("n't")


# a clause that takes a word away is no support for it: "Remove 'best' from the headline", "leave out best"
_REMOVAL = re.compile(r"\b(?:remove|removing|delete|deleting|drop|dropping|scrap|scrapping|cut|cutting|skip|skipping|avoid|"
                      r"avoiding|without|stop|stopping|instead of|rather than|get rid|take (?:it |that |this |them )?"
                      r"(?:out|off|away)|leave (?:it |that |this |them )?out|no more|no longer|not any)\b")


def _said_affirmed(claim: str, texts) -> bool:
    """True when some text of the owner has ``claim`` as whole words (spacing and hyphens alike) in a clause with no
    negator and no removal word, before or after it: "Do not call us the best", "The best is not what we are",
    "Remove 'best' from the headline" and "Bestow a warm welcome" do not say "best". Fail-closed."""
    words = [re.escape(w) for w in re.split(r"[\s-]+", fold(claim)) if w]
    rx = re.compile(r"(?<!\w)" + r"[\s-]+".join(words) + r"(?!\w)")
    for text in texts:
        for clause in _CLAUSE.split(fold(text)):
            if not rx.search(clause):
                continue
            if any(_negator(w.strip(",\"'()")) for w in clause.replace("-", " ").split()) or _REMOVAL.search(clause):
                continue
            return True
    return False


def _claim_stop(values, texts):
    """claim-in-his-words: a claim word in the text must be a word the owner said (whole words, not negated).
    Skipped without his texts."""
    if not texts:
        return None
    for value in values:
        for m in CLAIM_RE.finditer(value):
            if not _said_affirmed(m.group(0), texts):
                return SkillStop(CLAIM_REPLY.format(word=m.group(0)), "question")
    return None


def _same_lines(a, b) -> bool:
    return [_spaced(x) for x in a] == [_spaced(x) for x in b]


# -- page.home ----------------------------------------------------------------------------------------------------
def check_home_headline(slots, texts, ctx):
    """headline-two-lines: two different lines of at most 40 characters, each with letters."""
    if "headline" not in slots:
        return None
    lines = slots["headline"]
    if len(lines) == 1:
        return SkillStop(SECOND_LINE_ASK, "question")
    if len(lines) != 2:
        return SkillStop("The headline has two lines. What should each say?", "question")
    for line in lines:
        if len(line) > MAX_HEADLINE_LINE:
            return SkillStop(f"Each line of the headline can be {MAX_HEADLINE_LINE} characters at the most. Could you shorten it?", "question")
        if letters(line) < 2:
            return SkillStop("Each line of the headline needs a few letters. What should it say?", "question")
    if _line_key(lines[0]) == _line_key(lines[1]):
        return SkillStop("The two lines say the same thing. What should the second line say?", "question")
    return None


def check_home_intro(slots, texts, ctx):
    """intro-text: at most the intro limit, at least three letters."""
    intro = slots.get("intro")
    if intro is None:
        return None
    if len(intro) > MAX_INTRO:
        return SkillStop(f"That intro is too long. Could you shorten it to {MAX_INTRO} characters or fewer?", "question")
    if letters(intro) < 3:
        return SkillStop("That has too few words to mean anything. What should the intro say?", "question")
    return None


def check_home_price(slots, texts, ctx):
    """no-price: a price or a deal in the headline or the intro."""
    return _price_stop(*slots.get("headline", ()), *([slots["intro"]] if "intro" in slots else []))


def check_home_claims(slots, texts, ctx):
    """claim-in-his-words: \"best\", an award, an origin: only when he said the word."""
    return _claim_stop([*slots.get("headline", ()), *([slots["intro"]] if "intro" in slots else [])], texts)


def check_home_already(slots, texts, ctx):
    """not-already-true: every part asked for is what the site already shows (the shipped words when none was set)."""
    store = store_of(ctx)
    if store is None or not slots:
        return None
    same = ["headline" not in slots or _same_lines(slots["headline"], store.get("headline") or DEFAULT_HEADLINE),
            "intro" not in slots or _spaced(slots["intro"]) == _spaced(store.get("intro") or DEFAULT_INTRO)]
    return SkillStop(ALREADY, "question") if all(same) else None


HOME_CHECKS = {"headline-two-lines": check_home_headline, "intro-text": check_home_intro, "no-price": check_home_price,
               "claim-in-his-words": check_home_claims, "not-already-true": check_home_already}


def plan_home(slots, ctx):
    texts, store = texts_of(ctx), store_of(ctx)
    headline, intro, reset = slots.get("headline"), _clean(slots.get("intro")), slots.get("reset")
    if isinstance(headline, str):
        headline = [headline]
    headline = [_clean(x) for x in headline if isinstance(x, str) and _clean(x)] if isinstance(headline, (list, tuple)) else []
    if reset not in (None, "", "headline", "intro"):
        raise SkillStop(RESET_WHAT, "question")
    if reset and (headline if reset == "headline" else intro):
        raise SkillStop(f"Do you want the {reset} changed, or put back the way it was? I can only do one.", "question")
    if not (headline or intro or reset):
        raise SkillStop(HOME_ASK, "question")
    given = {**({"headline": headline} if headline else {}), **({"intro": intro} if intro else {})}
    for rule in ("headline-two-lines", "intro-text", "no-price", "claim-in-his-words"):
        if (stop := HOME_CHECKS[rule](given, texts, ctx)):
            raise stop
    want = {**given, **({"headline": list(DEFAULT_HEADLINE)} if reset == "headline" else {}),
            **({"intro": DEFAULT_INTRO} if reset == "intro" else {})}  # the shipped words are not his claims: not checked
    if (stop := HOME_CHECKS["not-already-true"](want, texts, ctx)):
        raise stop
    ops = []
    if "headline" in want and not (store is not None and _same_lines(want["headline"], store.get("headline") or DEFAULT_HEADLINE)):
        ops.append({"op": "store.set_headline", "args": {"first": want["headline"][0], "second": want["headline"][1]}})
    if "intro" in want and not (store is not None and _spaced(want["intro"]) == _spaced(store.get("intro") or DEFAULT_INTRO)):
        ops.append({"op": "store.set_intro", "args": {"text": want["intro"]}})
    return ops


# -- page.about ---------------------------------------------------------------------------------------------------
def check_about_story(slots, texts, ctx):
    """story-one-paragraph: one paragraph, 20 letters, at most the story limit."""
    story = slots["story"]
    if story.splitlines() != [story]:
        return SkillStop(ONE_PARAGRAPH, "question")
    if len(story) > MAX_STORY:
        return SkillStop(ABOUT_MAXED, "question")
    if letters(story) < 20:
        return SkillStop("That is a bit short for a story. What should it say?", "question")
    return None


def check_about_price(slots, texts, ctx):
    """no-price: a price or a deal in the story."""
    return _price_stop(slots["story"])


def check_about_claims(slots, texts, ctx):
    """claim-in-his-words: \"certified organic\", \"best\", \"since 2019\": only when he said it."""
    return _claim_stop([slots["story"]], texts)


def check_about_already(slots, texts, ctx):
    """not-already-true: the same story as now (the shipped one when none was set)."""
    store = store_of(ctx)
    if store is not None and _spaced(slots["story"]) == _spaced(store.get("story") or DEFAULT_STORY):
        return SkillStop(ALREADY, "question")
    return None


ABOUT_CHECKS = {"story-one-paragraph": check_about_story, "no-price": check_about_price,
                "claim-in-his-words": check_about_claims, "not-already-true": check_about_already}


def plan_about(slots, ctx):
    reset, story = bool(slots.get("reset")), str(slots.get("story") or "").strip()
    if reset and story:
        raise SkillStop("Do you want the story changed, or put back the way it was? I can only do one.", "question")
    if not (reset or story):
        raise SkillStop(STORY_ASK, "question")
    clean = {"story": DEFAULT_STORY if reset else (" ".join(story.split()) if story.splitlines() == [story] else story)}
    for rule in ABOUT_CHECKS:
        if reset and rule != "not-already-true":
            continue  # the shipped story is not his claim and is not shortened by a limit
        if (stop := ABOUT_CHECKS[rule](clean, texts_of(ctx), ctx)):
            raise stop
    return [{"op": "store.set_story", "args": {"text": clean["story"]}}]


# -- page.photo ---------------------------------------------------------------------------------------------------
def check_photo_alt(slots, texts, ctx):
    """alt-says-what-it-shows: a few words about the photo, never a file or camera name (the photo op's own rule)."""
    alt = slots["image_alt"]
    if len(alt) > photos.MAX_ALT:
        return SkillStop("That description is too long. Could you say what the photo shows in a few words?", "question")
    if photos._alt_problem(alt, slots["photo"]):
        return SkillStop(ALT_REPLY, "question")
    return None


PHOTO_CHECKS = {"alt-says-what-it-shows": check_photo_alt}


_MAIN_PICTURE = re.compile(r"\bmain\s+(?:picture|photo)\b", re.I)
_HOME_PAGE = re.compile(r"\bhome\s*page\b", re.I)
_PRODUCT = re.compile(r"\bproducts?\b", re.I)


_DENIES = re.compile(r"\b(?:no|not|never|without|none|nothing|neither|nor|cannot|skip|except|besides|instead\s+of|rather\s+than|other\s+than"
                     r"|(?:any|every)(?:where|thing)\s+but|(?:dont|doesnt|didnt|wont|isnt|arent|wasnt|cant))\b|n't\b", re.I)
_CLAUSE_END = re.compile(r"[,;:.!?\n\u2013\u2014]|\s-+\s|\b(?:and|then)\b|(?<!anywhere )(?<!anything )(?<!everywhere )(?<!everything )\bbut\b", re.I)


# A refusal AFTER the home-page mention in the same clause ("the home page is not where I want it"). "without"/"except"
# are left out here: "the home page without a caption" is still a home-page choice.
_DENIES_AFTER = re.compile(r"\b(?:no|nope|not|never|nowhere|cannot)\b|n't\b|\b(?:dont|doesnt|didnt|wont|isnt|arent|wasnt|cant)\b", re.I)
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'", "\u2032": "'", "\u00b4": "'", "`": "'", "\uff07": "'"})


def _chose_home(text) -> bool:
    """True when the text names the home page as the destination: affirmatively (not "not the home page", "don't put it on
    the home page", "the home page is not where I want it"), and not a product."""
    text = str(text or "").translate(_APOSTROPHES)  # curly apostrophes spell the same refusal as the straight one
    if _PRODUCT.search(text):
        return False
    for hit in _HOME_PAGE.finditer(text):
        before = _CLAUSE_END.split(text[:hit.start()])[-1]  # a denial only covers its own clause: "no, the home page" still chooses it
        after = _CLAUSE_END.split(text[hit.end():])[0]
        if not _DENIES.search(before) and not _DENIES_AFTER.search(after):
            return True
    return False


def photo_destination_open(texts) -> bool:
    """True when the owner's latest 'main picture' / 'main photo' request has not been given a home-page destination (RF2345-11).

    Only the owner's request texts count, in order: a text that affirmatively names the home page (and not a product)
    answers the question; a later main-picture text without it, or a refusal of the home page, opens it again; yes/no or
    unrelated text never answers it. "not the home page" is a refusal, never a choice."""
    open_, asked = False, False
    for text in texts:
        home = _chose_home(text)
        if _MAIN_PICTURE.search(text):
            open_, asked = not home, True
        elif home:
            open_ = False
        elif asked and _HOME_PAGE.search(text) and not _PRODUCT.search(text):  # he turned the home page down
            open_ = True
    return open_


def plan_photo(slots, ctx):
    store = store_of(ctx)
    photo, alt = slots.get("photo"), _clean(slots.get("image_alt"))
    if slots.get("clear") and (photo or alt):  # a replacement and putting the old one back: ask, never pick one (RF1345-11)
        raise SkillStop(PHOTO_OR_RESET, "question")
    if slots.get("clear"):
        if store is not None and "homeImage" not in store:
            raise SkillStop(NO_OWN_PHOTO)
        return [{"op": "store.clear_home_image", "args": {}}]
    if photo_destination_open(texts_of(ctx)):  # "make this the main picture": home page or a product? Never assume (RF2345-11)
        raise SkillStop(PHOTO_DESTINATION, "question")
    if not photo:
        raise SkillStop(PHOTO_ASK, "question")
    if not alt:
        raise SkillStop(ALT_ASK, "question")
    if (stop := PHOTO_CHECKS["alt-says-what-it-shows"]({"photo": photo, "image_alt": alt}, texts_of(ctx), ctx)):
        raise stop
    return [{"op": "store.set_home_image", "args": {"photo": photo, "imageAlt": alt}}]


# -- the skills ---------------------------------------------------------------------------------------------------
PAGE_HOME = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='preview', logs=('subjects', 'fields'), who='owner',
    name="page.home", label="change the home page headline or intro",
    summary="Change the two-line headline or the intro on the home page, or put the shop's own words back.",
    triggers=(
        Trigger("change the headline to Fresh from the coast. Picked this week."),
        Trigger("intro: Good food brings people together."),
        Trigger("chang the intro to say wlecome neighbors", "typo"),
        Trigger("make the home page friendlier", "vague"),
        Trigger("headline: A small market. Big flavor. and intro: Come by for lunch.", "multi"),
        Trigger("put the old headline back"),
        Trigger("headline: Best produce in California"),
        Trigger("make the headline bigger and red"),
        Trigger("intro: everything is $2"),
    ),
    slots=(Slot("headline", "text_list", False, owner_words=True),
           Slot("intro", "text", False, owner_words=True),
           Slot("reset", "enum", False)),
    rules=tuple(HOME_CHECKS), plan=plan_home,
    edits=((STORE_FILE, "headline"), (STORE_FILE, "intro"), (_INDEX, "the headline and the intro")),
    side_effects=("none",), preview="home", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "Putting the shipped words back writes those words into the store file, so the page looks the same as "
                        "before the first change; undoing the earlier change is the exact way back."),
    refuse=(("the headline asks for a price or a deal", "A price or a deal can't go in there, so nothing changed."),
            ("a claim word he did not say", CLAIM_REPLY.format(word="best")),
            (("a layout or colour change"), "I can't change how the page looks by message yet. I wrote it down so it can be built."),
            (("the same words are already there"), ALREADY)),
    cases=_CASES.format("page.home"), version=1)

PAGE_ABOUT = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='preview', logs=('subjects', 'fields'), who='owner',
    name="page.about", label="change the store story",
    summary="Change the “Come on in” story on the home page, the only About text the site has.",
    triggers=(
        Trigger("change the about text to: Michael has been buying produce for 30 years and knows every grower"),
        Trigger("update our story, we've been open since 2019"),
        Trigger("abuot us: we are a famly market", "typo"),
        Trigger("rewrite the about section", "vague"),
        Trigger("put the original story back"),
        Trigger("story: small shop, big heart. intro: Come say hi.", "multi"),
        Trigger("add an About page"),
        Trigger("our story: certified organic since day one"),
        Trigger("story over 600 characters"),
    ),
    slots=(Slot("story", "text", "unless:reset", ask=STORY_ASK, owner_words=True),
           Slot("reset", "bool", False)),
    rules=tuple(ABOUT_CHECKS), plan=plan_about,
    edits=((STORE_FILE, "story"), (_INDEX, "the “Come on in” paragraph")),
    side_effects=("none",), preview="home", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "Putting the shipped story back writes that story into the store file, so the page looks the same as "
                        "before the first change; undoing the earlier change is the exact way back."),
    refuse=(("the story is more than one paragraph", ONE_PARAGRAPH), ("the story is over 400 characters", ABOUT_MAXED),
            ("a claim word he did not say", CLAIM_REPLY.format(word="certified")), ("a new About page is asked for",
                                                           "The site has no About page, and adding a page is a design change I can't make by message yet. I wrote it down so it can be built.")),
    cases=_CASES.format("page.about"), version=1)

PAGE_PHOTO = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='preview', logs=('subjects', 'fields'), who='owner',
    name="page.photo", label="change the home page photo",
    summary="Use the photo he sent as the home page photo, or put the shop's own photo back.",
    triggers=(
        Trigger("use this for the home page, it's the front of the shop"),
        Trigger("new hompage pic: the stand outside", "typo"),
        Trigger("put the old photo back"),
        Trigger("make this the main picture", "vague"),
        Trigger("home photo is the shop front, and put up a notice that we're closed Thursday", "multi"),
        Trigger("use this for the home page and the lemons"),
        Trigger("home page photo, the shop front on a sunny morning"),
    ),
    slots=(Slot("photo", "attachment", "unless:clear", ask=PHOTO_ASK, from_attachment=True),
           Slot("image_alt", "text", "unless:clear", ask=ALT_ASK, owner_words=True, limit=("product", "imageAlt")),
           Slot("clear", "bool", False)),
    rules=tuple(PHOTO_CHECKS), plan=plan_photo,
    edits=((STORE_FILE, "homeImage"), ("storefront-mockup/assets/products/photo-<sha16>.<jpg|png>", "the new photo file"),
           (_INDEX, "the picture at the top of the page")),
    side_effects=("none",), preview="home", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "The photo file stays in the site folder with nothing pointing at it; the page shows the shop's own photo again."),
    refuse=(("the description is a file or camera name", ALT_REPLY), ("there is no photo of his to put back", NO_OWN_PHOTO),
            ("the photo is sideways (a rotation tag)", media.REPLIES["needs-rotation"])),
    cases=_CASES.format("page.photo"), version=2)

SKILLS = (PAGE_HOME, PAGE_ABOUT, PAGE_PHOTO)
