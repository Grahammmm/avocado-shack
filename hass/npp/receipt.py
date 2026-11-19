"""Private NPP artifacts and the positive transport receipt boundary."""

import hashlib
import json
import os
import re
import stat
import tempfile
from datetime import datetime
from pathlib import Path

from hass import media

JOB_RE = r"[0-9a-f]{4,12}"
SHA_RE = r"[0-9a-f]{64}"
CARD_RE = rf"card-({SHA_RE})\.png"
RECEIPT_MAX = 256 << 10


def instant(value):
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        return dt if dt.utcoffset() is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def confirmation(source, row_id, png_sha, queued, now):
    """An enqueue, legacy ACK or missing/ambiguous/failed receipt is never evidence of delivery."""
    if source is None:
        return None
    try:
        record = source(row_id)
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("state") != "confirmed" or record.get("png_sha256") != png_sha:
        return None
    at, guid = instant(record.get("confirmed_at")), record.get("provider_guid")
    if at is None or not queued <= at <= now:
        return None
    return at, guid if isinstance(guid, str) and 0 < len(guid) <= 512 else None


def read_artifact(path):
    """Same bound and type check at dispatch and in backup. Never follow an artifact symlink."""
    card = re.fullmatch(CARD_RE, path.name)
    cap = media.MAX_BYTES if card else RECEIPT_MAX
    with os.fdopen(fd := os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as fh:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular NPP artifact")
        data = fh.read(cap + 1)
    if not data or len(data) > cap:
        raise ValueError("invalid NPP artifact size")
    if card:
        if not data.startswith(media.KINDS["png"]) or hashlib.sha256(data).hexdigest() != card[1]:
            raise ValueError("invalid frozen card PNG")
    elif path.name != "receipt.json" or not isinstance(json.loads(data), dict):
        raise ValueError("invalid NPP receipt")
    return data


class Artifacts:
    def __init__(self, media_root):
        self.root = Path(media_root) / "npp"

    def folder(self, job, *, create=False):
        if not re.fullmatch(JOB_RE, job):
            raise ValueError("invalid NPP job id")
        path = self.root / job
        for directory in (self.root.parent, self.root, path):
            if create and directory != self.root.parent:
                directory.mkdir(mode=0o700, exist_ok=True)
            if not directory.is_dir() or directory.is_symlink():
                raise ValueError("unsafe NPP directory")
        return path

    def card(self, job, digest):
        if not re.fullmatch(SHA_RE, digest):
            raise ValueError("invalid NPP card digest")
        return self.folder(job) / f"card-{digest}.png"

    def write_card(self, job, png):
        if not isinstance(png, bytes) or len(png) > media.MAX_BYTES or not png.startswith(media.KINDS["png"]):
            raise ValueError("not a card PNG")
        digest = hashlib.sha256(png).hexdigest()
        path = self.folder(job, create=True) / f"card-{digest}.png"
        if not path.exists():
            media._write_new(path, png)
        read_artifact(path)
        return path, digest

    def write_receipt(self, job, record):
        data = json.dumps(record, sort_keys=True).encode() + b"\n"
        if len(data) > RECEIPT_MAX:
            raise ValueError("NPP receipt too large")
        path = self.folder(job, create=True) / "receipt.json"
        with tempfile.NamedTemporaryFile(dir=self.root, prefix=".receipt-", delete=False) as temp:
            tmp = Path(temp.name)
            try:
                temp.write(data)
                temp.flush()
                os.fsync(temp.fileno())
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
