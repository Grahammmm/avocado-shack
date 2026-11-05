"""SHOP-4: plain answers to the owner's questions after a change ("Did my change work?", "Are changes stopped?").

Pure functions over dictionaries the caller has already read (a conversation draft row, the editor change record's
`install` entry from SHOP-2, the pause time, waiting counts). No I/O and no clock read other than the `now` argument.
Never a change hash, draft hash, file path or commit: the owner only sees what changed and where it is now.
"""
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
FUTURE_SLACK = timedelta(minutes=5)  # RF1300-20: clock-skew allowance for an install time after now
PENDING = ("proposed", "needs-details")  # not applied yet: never described as applied (approval gate)
UNDER_WAY = "You said yes; it is still being saved, so nothing has changed on the website yet."  # approved, not saved
SAVED = ("applied", "verified")
KNOWN = PENDING + ("approved", "reverted", "rejected", "expired", "failed") + SAVED  # = conversation.TRANSITIONS states
UNKNOWN_STATE = "I can't read where this change is, so I can't say whether the website changed. Please ask for help."
INSTALL_REASONS = (  # SHOP-2 install failure reasons -> plain words (the file name that follows is dropped)
    ("write failed", "The website files could not be written"),
    ("readback mismatch", "The website files did not read back as written"),
    ("site path is not a regular file", "Something unexpected is in the website folder"))
PREVIEW_REASONS = (  # preview/result-check diagnostics -> plain words; the raw text (paths, records) stays stored
    ("generated file out of date", "the website pages were not rebuilt for it"),
    ("preview server did not start", "the preview could not be started"),
    ("check failed:", "the preview did not show the change as expected"),
    ("no change record", "the saved change could not be found"))
CHECK_WORDS = {  # AV1222-03: result-check key -> plain words (an unknown key is never shown)
    "productShown": "the product card", "description": "the product description", "availabilityShown": "the availability word",
    "imageShown": "the product photo", "hoursShown": "the opening hours", "addressShown": "the address",
    "headlineShown": "the home-page headline", "storyShown": "the shop story", "introShown": "the home-page intro",
    "selectionShown": "the selection checked line", "eventShown": "the hike", "pastShown": "the past hike",
    "recapShown": "the hike recap", "rsvpGone": "the sign-up button", "makerName": "the maker's name",
    "makerPlace": "the maker's place", "makerHidden": "the hidden maker",
    "phoneShown": "the phone number"}
RECORD_RE = re.compile(r"([a-z][a-z0-9_-]{0,40}) ([A-Za-z0-9][A-Za-z0-9._-]{0,80}): (.*)", re.S)  # no path characters
NOT_COPIED = "Copying it to the website has not been done, or did not finish"
PARTIAL = ("If copying it was started and stopped part way, some pages may already show it; ask for help to copy it "
           "to the website again, which puts every page in place")
NOT_LIVE = "Saved, but not on the website yet: copying it there is a separate step. Ask for help to put it on the website."
UNCHANGED = "The website is as it was before"
ROLLBACK_FAILED_WORDS = "install failed, some website files not put back - ask for help"  # RF1230-19


def _when(iso, now) -> str:
    """`today 09:05` on now's local day, otherwise `Mon Nov 2 09:05`; an unreadable time, or a time without a zone, is
    `at an unknown time` (never read in the host's zone)."""
    try:
        at = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "at an unknown time"
    if at.utcoffset() is None: return "at an unknown time"
    now = now if now.utcoffset() is not None else now.replace(tzinfo=timezone.utc)
    if at > now.astimezone(timezone.utc) + FUTURE_SLACK:  # RF1300-20: in UTC, so a DST fall-back never widens the slack
        return "at an unknown time"  # never a check time that has not happened
    at = at.astimezone(LOCAL_TZ)
    if at.date() == now.astimezone(LOCAL_TZ).date(): return f"today {at:%H:%M}"
    return f"{at:%a %b} {at.day} {at:%H:%M}"


def _summary(value) -> str:  # RF1300-19: one readable line of text, stripped, else "the change"
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > 200 or any(unicodedata.category(c) == "Cc" or c in "\u2028\u2029" for c in text):
        return "the change"
    return text


def _install_reason(reason) -> str:
    text = str(reason or "")
    return next((plain for prefix, plain in INSTALL_REASONS if text.startswith(prefix)), "The copy did not finish")


def _rollback_failed(install) -> bool:  # SHOP-2 install failed and could not put every file back
    return isinstance(install, dict) and install.get("state") == "failed" and "rollback failed" in str(install.get("reason"))


def did_it_work(change, install, now) -> str:
    """change: a conversation draft row as a dict (state, summary, reason); install: the editor change record's
    `install` entry (SHOP-2) or None. Returns one plain answer."""
    state, summary = change.get("state"), _summary(change.get("summary"))
    if state in PENDING or state is None: return "Waiting for your OK - nothing has changed yet."
    if state not in KNOWN: return UNKNOWN_STATE  # RF0910-5: a damaged/unknown state is never called unchanged or done
    if state == "approved": return UNDER_WAY  # an install entry never upgrades an unsaved approval to "Done"
    if state == "reverted": return "That change was undone."
    if state in ("rejected", "expired"): return "That draft was closed, so nothing changed."
    if state not in SAVED:  # failed before it was saved: the website was never touched
        return "This was not saved, and the website is unchanged; send the change again to retry."
    install = install if isinstance(install, dict) else {}
    if install.get("state") == "installed":
        return f"Done. {summary} is on the website now (checked {_when(install.get('installed_at'), now)})."
    if install.get("state") == "failed":
        if _rollback_failed(install):  # SHOP-2 could not put every file back
            return (f"This did not reach the website, and some website files could not be put back. "
                    f"{_install_reason(install.get('reason'))}. Please ask for help before more changes.")
        return f"This did not reach the website, and the website is unchanged. {_install_reason(install.get('reason'))}."
    # No install result: never run, or stopped before it could record one (install.py may already have replaced
    # some files), so the website is unconfirmed, never called intact.
    reason = str(change.get("reason") or "")
    why = f"The preview check failed: {preview_reason(reason[len('not verified: '):])}" \
        if reason.startswith("not verified: ") else NOT_COPIED
    return f"Saved, but not confirmed on the website. {why}. {PARTIAL}."


def preview_reason(error) -> str:
    """A stored preview/result-check diagnostic in plain words; never the raw text (file paths, exception text).
    The record the check failed on (AV1737-08: `<collection> <key>: <error>`) stays named, in brackets."""
    text = str(error or "")
    found = RECORD_RE.fullmatch(text)
    rest, which = (found[3], f" ({found[1]} {found[2]})") if found else (text, "")
    plain = next((plain for marker, plain in PREVIEW_REASONS if marker in rest), "the preview could not be checked")
    if "check failed:" in rest:  # name the checks that failed (diagnostic order), known ones only
        keys = [k.strip().removeprefix("desktop:") for k in rest.split("check failed:", 1)[1].split(",")]
        names = list(dict.fromkeys(CHECK_WORDS[k] for k in keys if k in CHECK_WORDS))
        plain += f": {', '.join(names)}" if names else ""
    return plain + which


def applied_text(code, summary, checked=False, error=None) -> str:
    """The reply when an approved change is saved (the apply/approve reply point): applying never copies it to the
    website, so the reply says so instead of only 'Applied'."""
    if error is not None: return f"Applied {code}, but the preview check failed: {preview_reason(error)}.\n{NOT_LIVE}"
    return f"Applied{' and checked' if checked else ''} {code}: {_summary(summary)}\n{NOT_LIVE}"


def _requests(n) -> str:
    return "No requests are waiting." if n == 0 else "1 request is waiting." if n == 1 else f"{n} requests are waiting."


def stopped_state(paused, queue) -> str:
    """paused: when changes were stopped (ISO time) or None; queue: {"waiting": requests not applied yet (drafts
    waiting for an OK plus messages not read yet), "applying": codes of approvals already under way}."""
    if not paused: return "Changes are on."
    queue = queue if isinstance(queue, dict) else {}  # RF2320-10: a damaged queue reads as unknown, never crashes
    waiting, applying = queue.get("waiting"), queue.get("applying")
    lines = ["Changes are stopped. Nothing new will be applied until you say 'resume'.",
             _requests(waiting) if type(waiting) is int and waiting >= 0 else "Waiting requests: unknown."]
    skipped = 0
    for code in applying if isinstance(applying, (list, tuple)) else ():
        if not (isinstance(code, str) and len(code) <= 40 and "/" not in code and code.split() == [code]):
            skipped += 1
            continue
        lines.append(f"{code} had already started: {UNCHANGED.lower()}, and nothing is copied to it by itself.")
    if skipped: lines.append(f"{skipped} more change(s) had already started.")
    lines.append("Changes already on the website stay there.")
    return " ".join(lines)


def recovered_text(code) -> str:
    """An approval interrupted before it was saved (editor recovery found no saved change)."""
    return f"{code} was interrupted and not saved. {UNCHANGED}; send the change again to make a new draft."


def history_words(change, install) -> str:
    """A short where-is-it phrase for one history line."""
    state = change.get("state")
    if state not in KNOWN and state is not None: return "state unknown - ask for help"  # RF0910-5
    if state in SAVED:
        if _rollback_failed(install): return ROLLBACK_FAILED_WORDS  # RF1230-19: asks for help, as did_it_work does
        state = (install if isinstance(install, dict) else {}).get("state")  # same rule as did_it_work
        return "on the website" if state == "installed" else "not on the website yet" if state == "failed" \
            else "not confirmed on the website"
    return {"approved": "approved, not saved yet", "reverted": "undone", "failed": "not saved; website unchanged",
            "rejected": "nothing changed", "expired": "nothing changed"}.get(state, "waiting for your OK")
