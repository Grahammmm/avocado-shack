"""Hass private photo original store (H10 part 1): type check, size cap, sha256 name, no duplicates.

store_original(root, data, received_at=..., source=...) keeps accepted JPEG/PNG bytes once under
root/originals/<sha[:2]>/<sha>.<ext> (0600 files, 0700 dirs) with a <sha>.json sidecar. The kind comes from the
bytes only; a sender's mimeType or file name is never trusted. The caller passes a media root that is NOT the Hass
state dir (statebackup refuses unknown state entries) and lies outside the repository. Stdlib only; no network,
no CLI, no wiring into the bridge. Refusals carry a fixed short owner reply with no path or hash in it.
"""
import hashlib, json, os, re, stat, tempfile  # noqa: E401
from pathlib import Path

from hass import editor

MAX_BYTES = 20 * 1024 * 1024
KINDS = {"jpeg": b"\xff\xd8\xff", "png": b"\x89PNG\r\n\x1a\n"}
EXT = {"jpeg": "jpg", "png": "png"}
SOURCE_RE = re.compile(r"[a-z0-9-]{1,32}")
REPLIES = {
    "empty": "That photo arrived empty. Please send it again.",
    "too-large": "That photo is too large for me (20 MB limit). Please send a smaller copy or a screenshot of it.",
    "unsupported-type": "I can only use JPEG or PNG photos for now. On iPhone: Settings > Camera > Formats > "
                        "Most Compatible, or send a screenshot of the photo.",
    "truncated": "That photo arrived incomplete. Please send it again.",
    "corrupt-store": "I could not save that photo safely, so nothing was changed. The operator needs to check the photo store.",
}

class Refused(Exception):
    """A photo we will not store; .code is one of REPLIES and .reply is the fixed owner text for it."""
    def __init__(self, code: str):
        super().__init__(code)
        self.code, self.reply = code, REPLIES[code]

def _prefix(data: bytes):
    return next((kind for kind, magic in KINDS.items() if data.startswith(magic)), None)

def sniff(data: bytes):
    """'jpeg' | 'png' from the magic bytes, or None (unknown type or a truncated upload)."""
    kind = _prefix(data)
    if kind == "jpeg" and data.rstrip(b"\x00").endswith(b"\xff\xd9"): return "jpeg"
    if kind == "png" and b"\x00\x00\x00\x00IEND" in data[len(KINDS["png"]):]: return "png"  # zero-length IEND chunk
    return None

def _private_dir(path: Path) -> None:
    try: os.mkdir(path, 0o700)
    except FileExistsError: pass
    if not stat.S_ISDIR(os.lstat(path).st_mode): raise Refused("corrupt-store")

def _existing(path: Path):
    """None if nothing is at path; the bytes of a regular file; Refused for any other entry (symlink included)."""
    try: st = os.lstat(path)
    except FileNotFoundError: return None
    if not stat.S_ISREG(st.st_mode): raise Refused("corrupt-store")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as fh: return fh.read()

def _write_new(final: Path, data: bytes) -> None:
    """Write via a 0600 temp file in the same dir, fsync, then hard-link; never overwrites or follows a symlink."""
    fd, tmp = tempfile.mkstemp(dir=final.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try: os.link(tmp, final, follow_symlinks=False)
        except FileExistsError: raise Refused("corrupt-store") from None
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
    dfd = os.open(final.parent, os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)

def _open_root(root) -> Path:
    if root is None or str(root) == "": raise editor.UnsafeState("a media root is required")
    try:
        if stat.S_ISLNK(os.lstat(root).st_mode): raise editor.UnsafeState("media root must not be a symlink")
    except FileNotFoundError: pass
    path, repo = Path(root).resolve(), editor.REPO_ROOT.resolve()
    if path == repo or repo in path.parents:  # checked before open_state, which would create the dir first
        raise editor.UnsafeState("media root must lie outside the repository")
    return editor.open_state(str(path))

def store_original(root, data: bytes, *, received_at: str, source: str) -> dict:
    """Keep data once under its sha256; a repeat returns the existing entry with duplicate=True."""
    if not isinstance(source, str) or not SOURCE_RE.fullmatch(source):
        raise ValueError("source must match ^[a-z0-9-]{1,32}$")
    if not isinstance(received_at, str) or not received_at: raise ValueError("received_at must be a non-empty string")
    if not isinstance(data, (bytes, bytearray)): raise TypeError("data must be bytes")
    data = bytes(data)
    base = _open_root(root)
    if not data: raise Refused("empty")
    if len(data) > MAX_BYTES: raise Refused("too-large")
    kind = sniff(data)
    if kind is None: raise Refused("truncated" if _prefix(data) else "unsupported-type")
    sha = hashlib.sha256(data).hexdigest()
    _private_dir(base / "originals")
    folder = base / "originals" / sha[:2]
    _private_dir(folder)
    final, sidecar = folder / f"{sha}.{EXT[kind]}", folder / f"{sha}.json"
    have = _existing(final)
    if have is not None and hashlib.sha256(have).hexdigest() != sha: raise Refused("corrupt-store")
    duplicate = have is not None
    if not duplicate: _write_new(final, data)
    if _existing(sidecar) is None:  # also repairs a sidecar lost between the two writes
        meta = {"sha256": sha, "kind": kind, "bytes": len(data), "received_at": received_at, "source": source}
        _write_new(sidecar, json.dumps(meta, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return {"sha256": sha, "kind": kind, "bytes": len(data), "path": str(final), "duplicate": duplicate}
