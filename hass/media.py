"""Hass private photo original store (H10 part 1): type check, size cap, sha256 name, no duplicates.

store_original(root, data, received_at=..., source=...) keeps accepted JPEG/PNG bytes once under
root/originals/<sha[:2]>/<sha>.<ext> (0600 files, 0700 dirs) with a <sha>.json sidecar; received_at must be a
timezone-aware ISO-8601 time (else ValueError before the root is opened). The kind comes from the
bytes only; a sender's mimeType or file name is never trusted. The caller passes a media root that is NOT the Hass
state dir (statebackup refuses unknown state entries) and lies outside the repository. Stdlib only; no network,
no wiring into the bridge. Refusals carry a fixed short owner reply with no path or hash in it. The one CLI is
`python3 hass/media.py verify --root DIR` (verify_store: read-only re-hash of the store, one JSON line, exit 0/1/2).

web_copy(root, sha256) (H10 part 2) writes root/web/<sha[:2]>/<sha>.<ext>: the stored original with every metadata
block that can carry location, device or time removed by JPEG segment / PNG chunk filtering (pixels byte-identical,
no image library). Pixels are never rotated or re-encoded: a JPEG whose EXIF Orientation is 2-8 keeps that one value in a
fresh EXIF segment holding nothing else (ORIENT_APP1); a PNG with an eXIf rotation tag is refused.
"""
import argparse, hashlib, json, os, re, stat, sys, tempfile, zlib  # noqa: E401
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hass import editor  # noqa: E402

MAX_BYTES = 20 * 1024 * 1024
KINDS = {"jpeg": b"\xff\xd8\xff", "png": b"\x89PNG\r\n\x1a\n"}
EXT = {"jpeg": "jpg", "png": "png"}
PNG_END = b"\x00\x00\x00\x00IEND\xaeB`\x82"  # zero-length IEND chunk with its fixed CRC32 (0xAE426082)
SOURCE_RE = re.compile(r"[a-z0-9-]{1,32}")
REPLIES = {
    "empty": "That photo arrived empty. Please send it again.",
    "too-large": "That photo is too large for me (20 MB limit). Please send a smaller copy or a screenshot of it.",
    "unsupported-type": "I can't use that file (JPEG or PNG only), so nothing was saved. On iPhone: Settings > Camera > "
                        "Formats > Most Compatible, or send a screenshot of the photo.",
    "truncated": "That photo arrived incomplete. Please send it again.",
    "corrupt-store": "I could not save that photo safely, so nothing was changed. The operator needs to check the photo store.",
    "not-found": "I could not find that photo any more, so nothing was changed. Please send it again.",
    "unreadable": "I could not read that photo safely, so nothing was changed. Please send it again as a screenshot "
                  "(JPEG or PNG, up to 20 MB).",
    "needs-rotation": "This photo is stored sideways, and it has to be stored the right way up, so nothing was changed. "
                      "Please send it again as a screenshot.",
    "many": "Please send one photo at a time (one per message); nothing was saved.",  # NB-AV-10 (H12)
    "audio": "That looks like a voice note or audio file. I can't understand voice notes yet, so nothing was saved. "
             "Please type the change as a text message.",  # AV2022-05 (H11/H12)
}
AUDIO_BRANDS = (b"M4A ", b"M4B ")
SHA_RE = re.compile(r"[0-9a-f]{64}")
JPEG_KEEP = {*range(0xC0, 0xD0), 0xDB, 0xDD}  # SOFn plus DHT C4, JPG C8, DAC CC; DQT; DRI
JPEG_TAGGED = {0xE0: b"JFIF\0", 0xE2: b"ICC_PROFILE\0", 0xEE: b"Adobe"}  # colour/format only, no location
PNG_KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"pHYs", b"bKGD"}

class Refused(Exception):
    """A photo we will not store; .code is one of REPLIES and .reply is the fixed owner text for it."""
    def __init__(self, code: str):
        super().__init__(code)
        self.code, self.reply = code, REPLIES[code]

def _prefix(data: bytes):
    return next((kind for kind, magic in KINDS.items() if data.startswith(magic)), None)

def is_audio(data: bytes) -> bool:
    """True for CAF (iPhone voice note), AMR / AMR-WB, or an ISO-BMFF M4A/M4B; from the bytes only."""
    return data.startswith((b"caff", b"#!AMR")) or (data[4:8] == b"ftyp" and data[8:12] in AUDIO_BRANDS)

def _unknown(data: bytes) -> str:
    return "truncated" if _prefix(data) else "audio" if is_audio(data) else "unsupported-type"

def sniff(data: bytes):
    """'jpeg' | 'png' from the magic bytes, or None (unknown type or a truncated upload)."""
    kind, end = _prefix(data), data.rstrip(b"\x00")  # trailing NUL padding is tolerated for both kinds
    if kind == "jpeg" and end.endswith(b"\xff\xd9"): return "jpeg"
    if kind == "png" and len(end) >= len(KINDS["png"]) + len(PNG_END) and end.endswith(PNG_END): return "png"
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

def _aware(value) -> str:
    """value unchanged if it is a timezone-aware ISO-8601 time (inbox.parse_aware's rule); else ValueError."""
    msg = "received_at must be a timezone-aware ISO-8601 time"
    if not isinstance(value, str) or not value: raise ValueError(msg)
    try: dt = datetime.fromisoformat(value)
    except ValueError: raise ValueError(msg) from None
    if dt.tzinfo is None or dt.utcoffset() is None: raise ValueError(msg)
    return value

def store_original(root, data: bytes, *, received_at: str, source: str) -> dict:
    """Keep data once under its sha256; a repeat returns the existing entry with duplicate=True."""
    if not isinstance(source, str) or not SOURCE_RE.fullmatch(source):
        raise ValueError("source must match ^[a-z0-9-]{1,32}$")
    _aware(received_at)  # before _open_root: a refused time creates nothing
    if not isinstance(data, (bytes, bytearray)): raise TypeError("data must be bytes")
    data = bytes(data)
    base = _open_root(root)
    if not data: raise Refused("empty")
    if len(data) > MAX_BYTES: raise Refused("too-large")
    kind = sniff(data)
    if kind is None: raise Refused(_unknown(data))
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

def check_photo(data: bytes) -> str:
    """NB-AV-10 (H12): the kind, after every store_original and web_copy check on the bytes in memory; writes nothing."""
    if not isinstance(data, (bytes, bytearray)): raise TypeError("data must be bytes")
    data = bytes(data)
    if not data: raise Refused("empty")
    if len(data) > MAX_BYTES: raise Refused("too-large")
    kind = sniff(data)
    if kind is None: raise Refused(_unknown(data))
    (_jpeg_copy if kind == "jpeg" else _png_copy)(data)  # the web-copy filter; its result is discarded
    return kind

def ORIENT_APP1(value: int) -> bytes:  # noqa: N802 - the built segment named in the spec
    """The only EXIF a web copy may carry: little-endian TIFF, one IFD0 entry (Orientation SHORT = value), no next IFD."""
    return b"\xff\xe1\x00\x22Exif\0\0II*\0\x08\0\0\0\x01\0\x12\x01\x03\0\x01\0\0\0" + value.to_bytes(2, "little") + bytes(6)

def _check_orientation(tiff: bytes) -> int:
    """EXIF IFD0 Orientation (0x0112) value 1-8 (1 when absent); malformed EXIF or two differing values -> unreadable."""
    order = {b"II*\0": "little", b"MM\0*": "big"}.get(bytes(tiff[:4]))
    if order is None: raise Refused("unreadable")
    def num(at, size):
        if at + size > len(tiff): raise Refused("unreadable")
        return int.from_bytes(tiff[at:at + size], order)
    ifd, found = num(4, 4), set()
    for entry in range(ifd + 2, ifd + 2 + 12 * num(ifd, 2), 12):
        if num(entry, 2) != 0x0112: continue
        value = num(entry + 8, 2)  # a SHORT sits left-justified in the 4-byte value field for both byte orders
        if num(entry + 2, 2) != 3 or num(entry + 4, 4) != 1 or not 1 <= value <= 8: raise Refused("unreadable")
        found.add(value)
    if len(found) > 1: raise Refused("unreadable")
    return found.pop() if found else 1

def _jpeg_kept(marker: int, seg: bytes) -> bool:
    return marker in JPEG_KEEP or (marker in JPEG_TAGGED and seg[4:].startswith(JPEG_TAGGED[marker]))

def _jpeg_name(marker: int) -> str:
    return "COM" if marker == 0xFE else f"APP{marker - 0xE0}" if 0xE0 <= marker <= 0xEF else f"FF{marker:02X}"

def _jpeg_fill(data: bytes, i: int) -> int:
    """Index of the marker's own FF: any marker may be preceded by fill bytes (repeated FF), which are skipped."""
    while data[i:i + 2] == b"\xff\xff": i += 1
    return i

def _jpeg_segment(data: bytes, i: int):
    """(start, marker, end) of the length-prefixed segment at i after any fill; unreadable if there is none."""
    i = _jpeg_fill(data, i)
    if i + 4 > len(data) or data[i] != 0xFF: raise Refused("unreadable")
    marker, end = data[i + 1], i + 2 + int.from_bytes(data[i + 2:i + 4], "big")
    if marker in (0x00, 0x01, 0xD8, 0xD9, 0xFF) or 0xD0 <= marker <= 0xD7 or end < i + 4 or end > len(data):
        raise Refused("unreadable")
    return i, marker, end

def _jpeg_split(data: bytes):
    """Header segments [(marker, bytes)] before the first SOS (header fill dropped), and the SOS..end tail
    (copied byte-for-byte, including any fill in front of the SOS marker)."""
    if not data.startswith(b"\xff\xd8"): raise Refused("unreadable")
    segs, i = [], 2
    while True:
        start, marker, end = _jpeg_segment(data, i)
        if marker == 0xDA: return segs, data[i:]
        segs.append((marker, data[start:end]))
        i = end

def _jpeg_check_tail(tail: bytes) -> None:
    """The tail is copied unchanged, so it may hold only scans and kept tables up to one EOI, then NUL padding:
    a COM/APPn between progressive scans or a second image appended after EOI (which can carry its own EXIF)
    is refused as unreadable rather than published. Fill bytes before any marker (EOI and RSTn too) are legal."""
    i = 0
    while tail[(i := _jpeg_fill(tail, i)):i + 2] != b"\xff\xd9":
        start, marker, end = _jpeg_segment(tail, i)
        if marker not in (0xDA, 0xDC) and not _jpeg_kept(marker, tail[start:end]): raise Refused("unreadable")
        i = end
        while marker == 0xDA and (i := tail.find(b"\xff", i)) >= 0:
            j = _jpeg_fill(tail, i)  # entropy-coded data: FF00 is a stuffed byte, FFD0-FFD7 a restart marker
            if j == i and tail[i + 1:i + 2] == b"\0": i += 2
            elif b"\xd0" <= tail[j + 1:j + 2] <= b"\xd7": i = j + 2
            else: break
        if i < 0: raise Refused("unreadable")
    if tail[i + 2:].strip(b"\0"): raise Refused("unreadable")

def _jpeg_copy(data: bytes):
    segs, tail = _jpeg_split(data)
    _jpeg_check_tail(tail)
    found = {_check_orientation(seg[10:]) for marker, seg in segs if marker == 0xE1 and seg[4:].startswith(b"Exif\0\0")}
    if len(found) > 1: raise Refused("unreadable")  # two EXIF blocks that disagree on the rotation
    turn = ORIENT_APP1(next(iter(found))) if found - {1} else b""
    out = b"\xff\xd8" + turn + b"".join(seg for marker, seg in segs if _jpeg_kept(marker, seg)) + tail
    again, again_tail = _jpeg_split(out)  # invariant self-check before anything is written
    if turn and again[:1] != [(0xE1, turn)]: raise Refused("unreadable")  # the built segment, exactly, at index 0
    if again_tail != tail or not all(_jpeg_kept(marker, seg) for marker, seg in again[bool(turn):]): raise Refused("unreadable")
    return out, {_jpeg_name(marker) for marker, seg in segs if not _jpeg_kept(marker, seg)}

def _png_chunks(data: bytes):
    """[(type, chunk bytes)] up to the first IEND; unreadable on a bad length or CRC, or anything but NULs after IEND."""
    if not data.startswith(KINDS["png"]): raise Refused("unreadable")
    chunks, i = [], len(KINDS["png"])
    while not chunks or chunks[-1][0] != b"IEND":
        end = i + 12 + int.from_bytes(data[i:i + 4], "big")
        if i + 12 > len(data) or end > len(data) or zlib.crc32(data[i + 4:end - 4]) != int.from_bytes(data[end - 4:end], "big"):
            raise Refused("unreadable")
        chunks.append((data[i + 4:i + 8], data[i:end]))
        i = end
    if data[i:].strip(b"\0"): raise Refused("unreadable")
    return chunks

def _png_idat(chunks) -> bytes:
    return b"".join(chunk[8:-4] for kind, chunk in chunks if kind == b"IDAT")

def _png_copy(data: bytes):
    chunks = _png_chunks(data)
    for kind, chunk in chunks:
        if kind == b"eXIf" and _check_orientation(chunk[8:-4]) != 1: raise Refused("needs-rotation")
    out = KINDS["png"] + b"".join(chunk for kind, chunk in chunks if kind in PNG_KEEP)
    again = _png_chunks(out)  # invariant self-check before anything is written
    if any(kind not in PNG_KEEP for kind, _ in again) or _png_idat(again) != _png_idat(chunks): raise Refused("unreadable")
    return out, {kind.decode("latin-1") for kind, _ in chunks if kind not in PNG_KEEP}

def web_copy(root, sha256: str) -> dict:
    """Write the metadata-free copy of a stored original once; a repeat returns it with duplicate=True."""
    if not isinstance(sha256, str) or not SHA_RE.fullmatch(sha256): raise ValueError("sha256 must be 64 lowercase hex")
    base = _open_root(root)
    folder = base / "originals" / sha256[:2]
    for d in (folder.parent, folder):
        try:
            if not stat.S_ISDIR(os.lstat(d).st_mode): raise Refused("corrupt-store")
        except FileNotFoundError: raise Refused("not-found") from None
    found = [d for d in (_existing(folder / f"{sha256}.{ext}") for ext in ("jpg", "png")) if d is not None]
    if not found: raise Refused("not-found")
    if len(found) > 1 or hashlib.sha256(found[0]).hexdigest() != sha256: raise Refused("corrupt-store")
    data, kind = found[0], sniff(found[0])
    if kind is None: raise Refused("unreadable")
    out, removed = (_jpeg_copy if kind == "jpeg" else _png_copy)(data)
    _private_dir(base / "web")
    _private_dir(base / "web" / sha256[:2])
    final = base / "web" / sha256[:2] / f"{sha256}.{EXT[kind]}"
    have = _existing(final)
    if have is not None and have != out: raise Refused("corrupt-store")
    if have is None: _write_new(final, out)
    return {"sha256": sha256, "web_sha256": hashlib.sha256(out).hexdigest(), "kind": kind, "bytes": len(out),
            "removed": sorted(removed), "path": str(final), "duplicate": have is not None}

def _verify_unsafe(root):  # checked before anything is opened, so a missing root is never created
    """(reason, None) when unsafe, else (None, path): the normalized, unresolved root that is checked AND walked.

    abspath drops a trailing '/' or '/.' (with which lstat would follow a symlink root) and collapses '..'
    lexically, so the entry lstat sees is exactly the one walk scans."""
    if root is None or str(root) == "": return "a media root is required", None
    path = os.path.abspath(os.fspath(root))
    try: st = os.lstat(path)
    except FileNotFoundError: return "media root does not exist", None
    except OSError: return "media root cannot be read", None
    if not stat.S_ISDIR(st.st_mode): return "media root must be a real directory, not a symlink", None
    repo = editor.REPO_ROOT.resolve()
    if repo in (p := Path(path).resolve(), *p.parents): return "media root must lie outside the repository", None
    return None, path

def _valid_time(meta: dict) -> bool:
    """True when the sidecar has no received_at (older stores) or a zoned one; retention dates photos by it."""
    try: return "received_at" not in meta or bool(_aware(meta["received_at"]))
    except ValueError: return False

def _valid_source(meta: dict) -> bool:
    return "source" not in meta or (isinstance(meta["source"], str) and SOURCE_RE.fullmatch(meta["source"]) is not None)

def verify_store(root) -> dict:
    """Read-only re-hash of the store with sidecar, mode, temp and web-copy checks; a sha is shown as 12 hex only."""
    bad, root = _verify_unsafe(root)
    if bad is not None: return {"result": "unsafe", "problems": [bad]}
    problems, found, short = set(), {"originals": {}, "web": {}}, lambda rel: SHA_RE.sub(lambda m: m[0][:12], rel)
    def walk(path, rel, depth):  # depth 0 root, 1 originals|web, 2 <aa> (files live here only); links never followed
        try:  # an access error is a redacted one-line problem (relative name only), never a crash or a path
            st = os.lstat(path)
            if not stat.S_ISDIR(st.st_mode): return problems.add(f"symlink: {short(rel)}")  # swapped since checked
            if stat.S_IMODE(st.st_mode) != 0o700: problems.add(f"mode: {short(rel)}")
            entries = list(os.scandir(path))  # list() exhausts the iterator, which closes it
        except OSError: return problems.add(f"unreadable: {short(rel)}")
        for e in entries:
            sub, m = e.name if depth == 0 else f"{rel}/{e.name}", depth == 2 and re.fullmatch(r"([0-9a-f]{64})\.(jpg|png|json)", e.name)
            try:
                if e.is_symlink(): problems.add(f"symlink: {short(sub)}")
                elif depth < 2 and e.is_dir(follow_symlinks=False) and re.fullmatch(("originals|web", "[0-9a-f]{2}")[depth], e.name):
                    walk(Path(e.path), sub, depth + 1)
                elif depth == 2 and e.name.startswith(".tmp-") and e.is_file(follow_symlinks=False):
                    problems.add(f"leftover temp: {path.name}")
                elif m and e.is_file(follow_symlinks=False) and m[1][:2] == path.name and not (rel[:3] == "web" and m[2] == "json"):
                    if stat.S_IMODE(e.stat(follow_symlinks=False).st_mode) != 0o600: problems.add(f"mode: {short(sub)}")
                    found[rel.split("/")[0]].setdefault(m[1], {})[m[2]] = e.path
                else: problems.add(f"unknown entry: {short(sub)}")
            except OSError: problems.add(f"unreadable: {short(sub)}")
    def read(path, sha):
        try: return _existing(Path(path))  # lstat + O_NOFOLLOW: a link swapped in now is refused, never opened
        except (OSError, Refused): problems.add(f"unreadable: {sha[:12]}")
    walk(Path(str(root)), ".", 0)
    for sha, files in found["originals"].items():
        if not (images := {ext: path for ext, path in files.items() if ext != "json"}): problems.add(f"orphan sidecar: {sha[:12]}")
        for ext, path in images.items():
            if (data := read(path, sha)) is not None and hashlib.sha256(data).hexdigest() != sha:
                problems.add(f"content mismatch: {sha[:12]}")
            if "json" not in files: problems.add(f"sidecar missing: {sha[:12]}")
            elif data is not None and (raw := read(files["json"], sha)) is not None:
                try: meta = json.loads(raw)
                except ValueError: meta = None
                want = {"sha256": sha, "kind": "jpeg" if ext == "jpg" else "png", "bytes": len(data)}
                if not (isinstance(meta, dict) and want.items() <= meta.items() and type(meta["bytes"]) is int  # 1234.0 == 1234
                        and _valid_time(meta) and _valid_source(meta)): problems.add(f"sidecar invalid: {sha[:12]}")
    for sha, files in found["web"].items():
        have = set(found["originals"].get(sha, {})) - {"json"}
        problems.update(f"web {'kind' if have else 'orphan'}: {sha[:12]}" for ext in files if ext not in have)
    return {"result": "problems" if problems else "ok", "problems": sorted(problems), "web": sum(map(len, found["web"].values())),
            "originals": sum(len(f) - ("json" in f) for f in found["originals"].values())}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/media.py", description="Read-only check of the private photo store.")
    parser.add_subparsers(dest="cmd", required=True).add_parser("verify").add_argument("--root", required=True)
    print(json.dumps(out := verify_store(parser.parse_args(argv).root), ensure_ascii=False, sort_keys=True))
    return {"ok": 0, "problems": 1}.get(out["result"], 2)

if __name__ == "__main__":
    sys.exit(main())
