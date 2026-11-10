"""HASS-ATTACH-1: send one PNG to the owner chat through loopback BlueBubbles. The attachment endpoint, field names and send
method are UNVERIFIED on the real Mac (runbook step 19). Same transport rules as bridge.BlueBubblesSender: loopback only, no
proxy, no redirect, the password read per call, and no error carries the URL, the password, the name or the bytes."""
import re, urllib.parse, uuid  # noqa: E401
from pathlib import Path

from hass import bridge, relay

ATTACH_PATH, ATTACH_TIMEOUT = "/api/v1/message/attachment", 30  # UNVERIFIED
NAME_RE = re.compile(r"hass-[0-9]{1,18}-[01]\.png")


class BlueBubblesAttachmentSender(bridge.BlueBubblesSender):
    """send_png(chat, data, name) -> one multipart POST (built in memory), or BridgeError. Only an owner chat is accepted (HASS-OWNERS-2: `owner_chat` is one chat id or a tuple of them)."""
    def __init__(self, base_url, password_file, owner_chat, transport=None):
        super().__init__(base_url, password_file, transport)
        self._owners = (owner_chat,) if isinstance(owner_chat, str) else tuple(owner_chat)
        self._owner = self._owners[0]

    def send_png(self, chat, data, name):
        code, status = None, None
        if chat not in self._owners or not NAME_RE.fullmatch(name) or not (1 <= len(data) <= relay.MAX_PNG) or not data.startswith(relay.PNG_SIG):
            code = "refused"
        else:
            try: password = Path(bridge._private_file(self._password_file)).read_text("utf-8").strip()
            except (OSError, ValueError, UnicodeDecodeError): password = ""
            if not password: code = "password-unreadable"
        if code is None:
            boundary = uuid.uuid4().hex
            fields = {"chatGuid": chat, "tempGuid": str(uuid.uuid4()), "name": name, "method": "apple-script"}  # UNVERIFIED
            body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8") for k, v in fields.items())
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="attachment"; filename="{name}"\r\n'
                     f'Content-Type: image/png\r\n\r\n').encode() + data + f"\r\n--{boundary}--\r\n".encode()
            url = f"{self._base}{ATTACH_PATH}?{urllib.parse.urlencode({'password': password})}"
            try: status = self._transport(url, body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, ATTACH_TIMEOUT)
            except Exception: code = "transport-error"  # noqa: BLE001 - its text may hold the URL
            if code is None and not (type(status) is int and 200 <= status < 300): code, status = "http-error", status if type(status) is int else None
        if code is not None: raise bridge.BridgeError(code, status)
