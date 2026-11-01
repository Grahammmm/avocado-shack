"""SHOP-4: plain answers to the owner's questions after a change ("Did my change work?", "Are changes stopped?").

Pure functions over dictionaries the caller has already read (a conversation draft row, the editor change record's
`install` entry from SHOP-2, the pause time, waiting counts). No I/O and no clock read other than the `now` argument.
Never a change hash, draft hash, file path or commit: the owner only sees what changed and where it is now.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
PENDING = ("proposed", "needs-details", "approved")  # not applied yet: never described as applied (approval gate)
SAVED = ("applied", "verified")
INSTALL_REASONS = (  # SHOP-2 install failure reasons -> plain words (the file name that follows is dropped)
    ("write failed", "The website files could not be written"),
    ("readback mismatch", "The website files did not read back as written"),
    ("site path is not a regular file", "Something unexpected is in the website folder"))
NOT_COPIED = "Copying it to the website has not been done or did not finish"
UNCHANGED = "The website is as it was before"


def _when(iso, now) -> str:
    """`today 09:05` on now's local day, otherwise `Mon Nov 2 09:05`; an unreadable time is `at an unknown time`."""
    try:
        at = datetime.fromisoformat(iso).astimezone(LOCAL_TZ)
    except (TypeError, ValueError):
        return "at an unknown time"
    if at.date() == now.astimezone(LOCAL_TZ).date(): return f"today {at:%H:%M}"
    return f"{at:%a %b} {at.day} {at:%H:%M}"


def _install_reason(reason) -> str:
    text = str(reason or "")
    return next((plain for prefix, plain in INSTALL_REASONS if text.startswith(prefix)), "The copy did not finish")


def did_it_work(change, install, now) -> str:
    """change: a conversation draft row as a dict (state, summary, reason); install: the editor change record's
    `install` entry (SHOP-2) or None. Returns one plain answer."""
    state, summary = change.get("state"), change.get("summary") or "the change"
    if state in PENDING or state is None: return "Waiting for your OK - nothing has changed yet."
    if state == "reverted": return "That change was undone."
    if state in ("rejected", "expired"): return "That draft was closed, so nothing changed."
    if state not in SAVED:  # failed (or interrupted) before it was saved: the website was never touched
        return "This was not saved, and the website is unchanged; send the change again to retry."
    install = install if isinstance(install, dict) else {}
    if install.get("state") == "installed":
        return f"Done. {summary} is on the website now (checked {_when(install.get('installed_at'), now)})."
    if install.get("state") == "failed":
        if "rollback failed" in str(install.get("reason")):  # SHOP-2 could not put every file back
            return (f"This did not reach the website, and some website files could not be put back. "
                    f"{_install_reason(install.get('reason'))}. Please ask for help before more changes.")
        return f"This did not reach the website, and the website is unchanged. {_install_reason(install.get('reason'))}."
    reason = str(change.get("reason") or "")
    why = f"The preview check failed ({reason[len('not verified: '):]})" if reason.startswith("not verified: ") \
        else NOT_COPIED
    return f"Saved, but not on the website yet. {why}. Nothing is broken; ask for help to put it on the website."


def _requests(n) -> str:
    return "No requests are waiting." if n == 0 else "1 request is waiting." if n == 1 else f"{n} requests are waiting."


def stopped_state(paused, queue) -> str:
    """paused: when changes were stopped (ISO time) or None; queue: {"waiting": requests not applied yet (drafts
    waiting for an OK plus messages not read yet), "applying": codes of approvals already under way}."""
    if not paused: return "Changes are on."
    lines = ["Changes are stopped. Nothing new will be applied until you say 'resume'.", _requests(queue.get("waiting", 0))]
    for code in queue.get("applying") or ():
        lines.append(f"{code} had already started: {UNCHANGED.lower()}, and nothing is copied to it by itself.")
    lines.append("Changes already on the website stay there.")
    return " ".join(lines)


def recovered_text(code) -> str:
    """An approval interrupted before it was saved (editor recovery found no saved change)."""
    return f"{code} was interrupted and not saved. {UNCHANGED}; send the change again to make a new draft."


def history_words(change, install) -> str:
    """A short where-is-it phrase for one history line."""
    state = change.get("state")
    if state in SAVED:
        return "on the website" if (install or {}).get("state") == "installed" else "not on the website yet"
    return {"reverted": "undone", "failed": "not saved; website unchanged", "rejected": "nothing changed",
            "expired": "nothing changed"}.get(state, "waiting for your OK")
