"""SHOP-4: plain answers to the owner's questions after a change ("Did my change work?", "Are changes stopped?").

Pure functions over dictionaries the caller has already read (a conversation draft row, the editor change record's
`install` entry from SHOP-2, the pause time, waiting counts). No I/O and no clock read other than the `now` argument.
Never a change hash, draft hash, file path or commit: the owner only sees what changed and where it is now.
"""
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from hass import voice

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
FUTURE_SLACK = timedelta(minutes=5)  # RF1300-20: clock-skew allowance for an install time after now
PENDING = ("proposed", "needs-details")  # not applied yet: never described as applied (approval gate)
UNDER_WAY = "You said yes, but it isn't saved yet, so nothing has changed on the website."  # approved, not saved
SAVED = ("applied", "verified")
KNOWN = PENDING + ("approved", "reverted", "rejected", "expired", "failed") + SAVED  # = conversation.TRANSITIONS states
UNKNOWN_STATE = "I don't know where this change stands, so I can't say whether the website changed. Say status in a few minutes and I'll look again."
INSTALL_REASONS = (  # SHOP-2 install failure reasons -> plain words (the file name that follows is dropped)
    ("write failed", "I couldn't update the website pages"),
    ("readback mismatch", "The website pages didn't come out the way I wrote them"),
    ("site path is not a regular file", "Something unexpected is in the way on the website"))
PREVIEW_REASONS = (  # preview/result-check diagnostics -> plain words; the raw text (paths, records) stays stored
    ("generated file out of date", "the website pages were not rebuilt for it"),
    ("preview server did not start", "I couldn't make a preview"),
    ("check failed:", "the preview didn't show the change the way it should"),
    ("no change record", "I couldn't find the saved change"))
CHECK_WORDS = {  # AV1222-03: result-check key -> plain words (an unknown key is never shown)
    "productShown": "the product card", "description": "the product description", "availabilityShown": "the availability word",
    "imageShown": "the product photo", "hoursShown": "the opening hours", "addressShown": "the address",
    "headlineShown": "the home-page headline", "storyShown": "the shop story", "introShown": "the home-page intro",
    "selectionShown": "the shelf check line", "eventShown": "the hike", "pastShown": "the past hike",
    "recapShown": "the hike recap", "rsvpGone": "the sign-up button", "makerName": "the maker's name",
    "makerPlace": "the maker's place", "makerHidden": "the hidden maker",
    "phoneShown": "the phone number"}
RECORD_RE = re.compile(r"([a-z][a-z0-9_-]{0,40}) ([A-Za-z0-9][A-Za-z0-9._-]{0,80}): (.*)", re.S)  # no path characters
NOT_COPIED = "Copying it to the website hasn't been done, or didn't finish"
PARTIAL = ("If copying it started and stopped partway, some pages may already show it. "
           "Copying it to the website again, by hand, puts every page in place")
NOT_LIVE = "It's saved, but not on the website yet. Copying it there is a separate step, done by hand."
LIVE_SHOWN = "Your change is on the website now."
LIVE_PICTURE = "The picture is Hass's own view of the published page."
LIVE_NO_PICTURE = "No picture this time."
LIVE_TAKEN_BACK = "Graham took your last change off the website. The website is back as it was before that change."
LIVE_NOT_PUBLISHED = "That change is saved on my side but did not go on the website: {reason}. The website is unchanged. Graham has been told."
LIVE_REASONS = {"the release was interrupted": "it was interrupted"}  # the only reason text the release books write today


def live_reason(reason) -> str:
    return LIVE_REASONS.get(reason, "something went wrong while copying it")
# HASS-LIVE-PLAN-1: why the release engine would not even start (publish_live.refuse reasons), in the owner's words. The website is
# unchanged in every case. A reason with no entry here gets the generic "couldn't save" line, never the raw text.
LIVE_REFUSED = (
    ("another change is going live", "Another change is going on the website right now. Please send this again in a few minutes."),
    ("live changes are stopped", "Changes to the website are paused right now. Graham will say when they are back."),
    ("not settled yet", "The last change is still being checked, so I can't send another one yet. Graham has been told."),
    ("limit of", "I've reached today's limit for website changes. Please send it again tomorrow."),
    ("someone else changed the website", "The website was changed by someone else, so I'm holding off. Graham has been told."),
    ("differ", "The website and my copy don't match, so I'm holding off. Graham has been told."),
    ("needs g to check", "Graham needs to check something before I can change the website. He has been told."),
    ("already has a release record", "That change was already sent."),
    ("draft no longer matches", "That change was out of date. Please ask me again."),
)


def live_refused(reason) -> str | None:
    """The owner's-words reply for a release refused before it started, or None for a reason we have no words for."""
    text = str(reason or "")
    return next((f"{words} Nothing changed on the website." for key, words in LIVE_REFUSED if key in text), None)


LIVE_UNKNOWN = "I sent that change to the website, but I can't tell whether it arrived. It may or may not show. Graham has been told, and no other change will go on the website until this is sorted."
LIVE_UNCONFIRMED = "I sent that change to the website, but I can't see it there yet. Graham has been told."
UNCHANGED = "The website is as it was before"
ROUTE_UNSHOWN = "The route idea isn't shown on the website right now, so there was nothing to check."  # AV1222-06
ROLLBACK_FAILED_WORDS = "it didn't finish, and some website files could not be put back - please hold off on more changes"  # RF1230-19


def _when(iso, now) -> str:
    """`today at 9:05 am` on now's local day, otherwise `Monday, Nov 2 at 9:05 am`; an unreadable time, or a time without a zone, is
    `at a time I can't read` (never read in the host's zone)."""
    try:
        at = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "at a time I can't read"
    if at.utcoffset() is None: return "at a time I can't read"
    now = now if now.utcoffset() is not None else now.replace(tzinfo=timezone.utc)
    if at > now.astimezone(timezone.utc) + FUTURE_SLACK:  # RF1300-20: in UTC, so a DST fall-back never widens the slack
        return "at a time I can't read"  # never a check time that has not happened
    return voice.natural(at, now)


def _summary(value) -> str:  # RF1300-19: one readable line of text, stripped, else "the change" (names in it are Mike's own words)
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > 200 or any(unicodedata.category(c) == "Cc" or c in "\u2028\u2029" for c in text):
        return "the change"
    return voice.quote(text)


def _install_reason(reason) -> str:
    text = str(reason or "")
    return next((plain for prefix, plain in INSTALL_REASONS if text.startswith(prefix)), "It didn't finish")


def _rollback_failed(install) -> bool:  # SHOP-2 install failed and could not put every file back
    return isinstance(install, dict) and install.get("state") == "failed" and "rollback failed" in str(install.get("reason"))


def did_it_work(change, install, now) -> str:
    """change: a conversation draft row as a dict (state, summary, reason); install: the editor change record's
    `install` entry (SHOP-2) or None. Returns one plain answer."""
    state, summary = change.get("state"), _summary(change.get("summary"))
    if state in PENDING or state is None: return "It's waiting for your yes. Nothing has changed yet."
    if state not in KNOWN: return UNKNOWN_STATE  # RF0910-5: a damaged/unknown state is never called unchanged or done
    if state == "approved": return UNDER_WAY  # an install entry never upgrades an unsaved approval to "Done"
    if state == "reverted": return "That change was undone."
    if state in ("rejected", "expired"): return "That change was cancelled, so nothing changed."
    if state not in SAVED:  # failed before it was saved: the website was never touched
        return "I couldn't save that, and the website is unchanged. Please send the change again."
    install = install if isinstance(install, dict) else {}
    if install.get("state") == "installed":
        return f"Done. {summary} is on the website now (I checked {_when(install.get('installed_at'), now)})."
    if install.get("state") == "failed":
        if _rollback_failed(install):  # SHOP-2 could not put every file back
            return (f"That didn't reach the website, and some website files could not be put back. "
                    f"{_install_reason(install.get('reason'))}. Please hold off on more changes until those files are put back by hand.")
        return f"That didn't reach the website, and the website is unchanged. {_install_reason(install.get('reason'))}."
    # No install result: never run, or stopped before it could record one (install.py may already have replaced
    # some files), so the website is unconfirmed, never called intact.
    reason = str(change.get("reason") or "")
    why = f"The preview check didn't pass: {preview_reason(reason[len('not verified: '):])}" \
        if reason.startswith("not verified: ") else NOT_COPIED
    return f"It's saved, but I'm not sure it's on the website. {why}. {PARTIAL}."


def preview_reason(error) -> str:
    """A stored preview/result-check diagnostic in plain words; never the raw text (file paths, exception text).
    The kind of record the check failed on stays named (the record's id is dropped)."""
    text = str(error or "")
    found = RECORD_RE.fullmatch(text)
    rest = found[3] if found else text
    plain = next((plain for marker, plain in PREVIEW_REASONS if marker in rest), "I couldn't check the preview")
    if "check failed:" in rest:  # name the checks that failed (diagnostic order), known ones only
        keys = [k.strip().removeprefix("desktop:") for k in rest.split("check failed:", 1)[1].split(",")]
        names = list(dict.fromkeys(CHECK_WORDS[k] for k in keys if k in CHECK_WORDS))
        plain += f": {', '.join(names)}" if names else ""
    return plain


def applied_text(code, summary, checked=False, error=None, live_site=None) -> str:
    """The reply when an approved change is saved (the apply/approve reply point): applying never copies it to the
    website, so the reply says so instead of only 'Saved'."""
    if live_site: return f"Saved: {_summary(summary)}. I'll send a separate message about the website."
    if error is not None: return f"I saved it, but the preview check didn't pass: {preview_reason(error)}.\n{NOT_LIVE}"
    return f"Saved{' and checked' if checked else ''}: {_summary(summary)}\n{NOT_LIVE}"


def _requests(n) -> str:
    return "No requests are waiting." if n == 0 else "1 request is waiting." if n == 1 else f"{n} requests are waiting."


def stopped_state(paused, queue) -> str:
    """paused: when changes were stopped (ISO time) or None; queue: {"waiting": requests not applied yet (drafts
    waiting for an OK plus messages not read yet), "applying": codes of approvals already under way}."""
    if not paused: return "Changes are on."
    queue = queue if isinstance(queue, dict) else {}  # RF2320-10: a damaged queue reads as unknown, never crashes
    waiting, applying = queue.get("waiting"), queue.get("applying")
    lines = ["Changes are stopped. I won't save anything new until you say 'resume changes'.",
             _requests(waiting) if type(waiting) is int and waiting >= 0 else "I don't know how many requests are waiting."]
    started = sum(1 for code in (applying if isinstance(applying, (list, tuple)) else ())
                  if isinstance(code, str) and len(code) <= 40 and "/" not in code and code.split() == [code])
    skipped = len(applying) - started if isinstance(applying, (list, tuple)) else 0
    if started: lines.append(f"{started} change{'s' if started != 1 else ''} had already started. {UNCHANGED}, and nothing is copied to it by itself.")
    if skipped: lines.append(f"{skipped} more had already started.")
    lines.append("Changes already on the website stay there.")
    return " ".join(lines)


def recovered_text(code, live_site=None) -> str:
    """An approval interrupted before it was saved (editor recovery found no saved change)."""
    if live_site: return "That change was interrupted and not saved. Please send it again."
    return f"That change was interrupted and not saved. {UNCHANGED}. Please send it again."


def history_words(change, install) -> str:
    """A short where-is-it phrase for one history line."""
    state = change.get("state")
    if state not in KNOWN and state is not None: return "I'm not sure where this one stands yet"  # RF0910-5
    if state in SAVED:
        if _rollback_failed(install): return ROLLBACK_FAILED_WORDS  # RF1230-19: asks for help, as did_it_work does
        state = (install if isinstance(install, dict) else {}).get("state")  # same rule as did_it_work
        return "on the website" if state == "installed" else "saved, but it didn't reach the website" if state == "failed" \
            else "saved, but I'm not sure it's on the website"
    return {"approved": "you said yes, but it isn't saved yet", "reverted": "undone", "failed": "I couldn't save it, so nothing changed",
            "rejected": "cancelled, nothing changed", "expired": "timed out, nothing changed"}.get(state, "waiting for your yes")
