"""HASS-CLOVER-1: the Clover API token, read from ONE private file and never shown anywhere.

CREDENTIAL RULE (docs/hass/CLOVER.md): G creates the token and puts it in one file on the host. Only the Hass service program
reads it. This module is the only code that ever holds the value. It never logs, formats, pickles or copies it, and every
error it raises carries a fixed reason word, never the value, the file's bytes or the path.

The file must be a regular file (no symlink), owned by the user running the service, mode exactly 0600, in a folder that only
that user can write to. The check is done on the open descriptor, so the file cannot be swapped between the check and the read.
"""
import os
import re
import stat

MAX_TOKEN_FILE_BYTES = 512
TOKEN_RE = re.compile(r"[A-Za-z0-9._~+/=-]{8,256}")
REDACTED = "[redacted]"
BEARER_RE = re.compile(r"(?i)bearer\s+\S+")

# Fixed reason words. The CLI/health output shows these and nothing else.
REASONS = {
    "missing": "the token file is not there",
    "unreadable": "the token file could not be opened",
    "not-regular": "the token file is not a plain file",
    "owner": "the token file is not owned by the service user",
    "mode": "the token file mode is not 600",
    "folder": "the token file's folder is not private to the service user",
    "size": "the token file is empty or too large",
    "format": "the token file does not hold one token",
}


class CredentialError(Exception):
    """The token file is unusable. `reason` is one of REASONS; the message never carries a path or a value."""

    def __init__(self, reason):
        super().__init__(f"clover token file refused: {reason}")
        self.reason = reason


class Token:
    """Holds the secret and refuses every way of printing, copying or serialising it."""

    __slots__ = ("_value",)

    def __init__(self, value):
        object.__setattr__(self, "_value", value)

    def __setattr__(self, name, value):
        raise AttributeError("Token is read-only")

    def __repr__(self):
        return "Token(<redacted>)"

    __str__ = __repr__

    def __format__(self, spec):
        return "Token(<redacted>)"

    def __reduce__(self):
        raise TypeError("Token cannot be serialised")

    def __copy__(self):
        raise TypeError("Token cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("Token cannot be copied")

    def authorization(self):
        """The one place the value leaves this object: the Authorization header value, for the transport only."""
        return "Bearer " + self._value

    def redact(self, text):
        """`text` with the token (and any bearer string) replaced. For error paths that must carry some foreign text."""
        text = str(text)
        if self._value:
            text = text.replace(self._value, REDACTED)
        return BEARER_RE.sub("Bearer " + REDACTED, text)


def redact(text):
    """Token-free redaction for code that does not hold the token: only bearer-shaped strings can be removed."""
    return BEARER_RE.sub("Bearer " + REDACTED, str(text))


def load_token(path, uid=None):
    """Read the token file after checking owner, mode and folder on the open descriptor. Raises CredentialError(reason)."""
    uid = os.getuid() if uid is None else uid
    reason, value = _read(path, uid)
    if reason:
        raise CredentialError(reason)  # raised outside the except block: no OSError (which names the path) is chained
    return Token(value)


def inspect(path, uid=None):
    """HASS-CLOVER-2: the problem word for the token file, or None when it looks usable, WITHOUT opening it (lstat and access only).
    `hass/host.py check` and `hass/health.py` use this: they never hold the token. The answer is one REASONS key; never the path."""
    uid = os.getuid() if uid is None else uid
    try:
        folder = os.lstat(os.path.dirname(os.path.abspath(path)))
        st = os.lstat(path)
    except FileNotFoundError:
        return "missing"
    except (OSError, ValueError):   # ValueError: an embedded NUL
        return "unreadable"
    if not stat.S_ISDIR(folder.st_mode) or folder.st_uid != uid or folder.st_mode & 0o022:
        return "folder"
    if not stat.S_ISREG(st.st_mode):
        return "not-regular"
    if st.st_uid != uid:
        return "owner"
    if stat.S_IMODE(st.st_mode) != 0o600:
        return "mode"
    if not 0 < st.st_size <= MAX_TOKEN_FILE_BYTES:
        return "size"
    if not os.access(path, os.R_OK, follow_symlinks=False):
        return "unreadable"
    return None


def _read(path, uid):
    try:
        folder = os.lstat(os.path.dirname(os.path.abspath(path)))
    except FileNotFoundError:
        return "missing", None
    except (OSError, ValueError):
        return "unreadable", None
    if not stat.S_ISDIR(folder.st_mode) or folder.st_uid != uid or folder.st_mode & 0o022:
        return "folder", None
    # Anchor the folder: the leaf is opened relative to this descriptor, never by resolving the full pathname again.
    cloexec = getattr(os, "O_CLOEXEC", 0)
    # O_PATH anchors a searchable directory without requiring permission to list it (Linux service host).
    # On platforms without O_PATH retain the previous directory-open behaviour.
    dir_access = getattr(os, "O_PATH", os.O_RDONLY)
    try:
        dfd = os.open(os.path.dirname(os.path.abspath(path)), dir_access | os.O_DIRECTORY | os.O_NOFOLLOW | cloexec)
    except FileNotFoundError:
        return "missing", None
    except (OSError, ValueError):
        return "folder", None
    try:
        return _read_in(dfd, folder, os.path.basename(os.path.abspath(path)), uid, cloexec)
    finally:
        os.close(dfd)


def _read_in(dfd, folder, name, uid, cloexec):
    try:
        anchored = os.fstat(dfd)
    except OSError:
        return "folder", None
    if (not stat.S_ISDIR(anchored.st_mode) or anchored.st_uid != uid or anchored.st_mode & 0o022
            or (anchored.st_dev, anchored.st_ino) != (folder.st_dev, folder.st_ino)):
        return "folder", None
    try:
        # O_NONBLOCK: a FIFO with no writer must not hang the open; the descriptor check below then refuses it as not-regular
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | cloexec, dir_fd=dfd)
    except FileNotFoundError:
        return "missing", None
    except (OSError, ValueError):
        return "unreadable", None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return "not-regular", None
        if st.st_uid != uid:
            return "owner", None
        if stat.S_IMODE(st.st_mode) != 0o600:
            return "mode", None
        if not 0 < st.st_size <= MAX_TOKEN_FILE_BYTES:
            return "size", None
        raw = os.read(fd, MAX_TOKEN_FILE_BYTES + 1)
    except OSError:
        return "unreadable", None
    finally:
        os.close(fd)
    if len(raw) > MAX_TOKEN_FILE_BYTES:
        return "size", None
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return "format", None
    text = text[:-2] if text.endswith("\r\n") else text[:-1] if text.endswith("\n") else text
    if not TOKEN_RE.fullmatch(text):
        return "format", None
    return None, text


def load_write_token(config):
    """Service-only: the separate write file obeys exactly the read file's private-file rules."""
    if not config.writes_allowed or os.path.realpath(config.write_token_file) == os.path.realpath(config.token_file):
        raise CredentialError("missing")
    if os.path.exists(config.token_file) and os.path.exists(config.write_token_file) and os.path.samefile(config.token_file, config.write_token_file):
        raise CredentialError("not-regular")
    return load_token(config.write_token_file)
