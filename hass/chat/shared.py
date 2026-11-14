"""Wording and small helpers the chat dispatcher (hass/conversation.py) and more than one pack module read.

AVB-12: moved verbatim out of hass/conversation.py, which imports every name back (hass.conversation.<name> is
unchanged). load_content here looks hass.conversation.load_content up at call time, so the packs read the catalog through
the same name as the dispatcher.
"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from hass import voice

LOCAL_TZ = ZoneInfo("America/Los_Angeles")

q = voice.quote  # HASS-VOICE-1: words Mike typed himself, or commands he types, are shown as they are and never judged

FIND_TEXT_MAX, ALIAS_NAME_MAX = 60, 60  # AV0022-15: docs/hass/LIMITS.md states these (test_limits_doc)

STATUS_PLAIN = {"active": "on the website", "hidden": "hidden", "held": "on hold", "visible": "on the website",
                "scheduled": "coming up", "cancelled": "cancelled", "completed": "done", "idea": "just an idea", "draft": "not finished"}

COST_USAGE = "Tell me the product, what you pay for a pack and how many are in it, like " + q("cost Hass avocado: 24 for 12") + "."

# H17 pause flag. Created by the first `pause` (not in SCHEMA) so the H05 store keeps its four tables until then.
CONTROL = """CREATE TABLE IF NOT EXISTS control(name TEXT PRIMARY KEY, value TEXT NOT NULL, set_at TEXT NOT NULL,
  provider_id TEXT NOT NULL)"""

NOTHING = "Nothing is waiting for your yes."

CANT_READ = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"

SHELF_ASK = "Is the shelf list right for today? Reply yes if it is, or tell me what is different."


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _is_undo(row) -> bool:
    """AV0022-07 (H06): the draft's ops are a non-empty list of only history.revert calls; unparsable is not an undo."""
    try: ops = json.loads(row["ops_json"])
    except (TypeError, ValueError, RecursionError): return False
    return isinstance(ops, list) and bool(ops) and all(isinstance(c, dict) and c.get("op") == "history.revert" for c in ops)


def load_content(path):
    """hass.content_model.load_content as hass.conversation names it, looked up when called (tests patch that name)."""
    from hass import conversation  # at call time: hass.conversation imports this module
    return conversation.load_content(path)
