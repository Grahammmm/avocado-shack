"""Staged new-product pipeline. Product stages compose behind this package, not inside chat dispatch."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPLIES = "hass-npp-reply/reply-templates.json"


def assets():
    """Read and check the assets before enabling NPP. Return the same bytes that were checked."""
    pins = json.loads((ROOT / "pins.json").read_bytes())
    files = {}
    for name, digest in pins["assets"].items():
        path = ROOT / "assets" / name
        if not path.is_relative_to(ROOT / "assets") or ".." in path.parts or path.is_symlink():
            raise ValueError("invalid NPP asset path")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("NPP asset digest mismatch")
        files[name] = data
    if pins["segment"]["cap_s"] != 100:
        raise ValueError("invalid NPP segment cap")
    return pins, files, json.loads(files[REPLIES])


def stages_for(conversation, pinned):
    # NPP-G composes C–G here. Before then the job can be exercised with fixture stages, never the legacy writer.
    try:
        from hass.npp.reply import build_stages
    except ModuleNotFoundError as exc:
        if exc.name != "hass.npp.reply":
            raise
        return None
    return build_stages(conversation, pinned)
