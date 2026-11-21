"""Rehearse an approved Clover change with real reads and a local request receipt."""
import json
import re

from hass.clover import chat, credential, drafts
from hass.clover.client import ID, CloverClient, CloverRefused, CloverWriteClient
from hass.clover.mapper import parse_item
from hass.clover.transport import UrllibTransport


class DryRunWriteClient:
    """Delegate reads; validate and record writes without building an HTTP request."""

    def __init__(self, read_client):
        self._read_client = read_client
        self.requests = []
        self._created = 0

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._read_client, name)

    def write(self, method, path, payload):
        # Match CloverWriteClient.write's method/path and JSON checks. Neither
        # building a credential-bearing request nor invoking its sender is needed.
        allowed = (method == "POST" and re.fullmatch(rf"/items(?:/{ID})?|/category_items", path)
                   or method == "PUT" and re.fullmatch(rf"/item_stocks/{ID}", path))
        if not allowed:
            raise CloverRefused("write path not allowed")
        body = json.loads(json.dumps(payload, allow_nan=False))
        self.requests.append({"method": method, "path": path, "json": body})
        if path == "/items":
            self._created = self._created % 999_999 + 1
            return {"id": f"DRYRUN{self._created:06d}"}
        return {}


def make_client_factory(config, read_loader, *, dry_run=True):
    """Build a rehearsal client by default, or an explicitly enabled live factory.

    The dry factory can load the read token via ``read_loader(path)`` when
    used directly; an engine may supply the token it has already loaded.
    The live factory takes the write token supplied by BundleEngine.
    """
    if dry_run:
        def factory(token=None):
            if token is None:
                token = read_loader(config.token_file)
            return DryRunWriteClient(CloverClient(config.merchant_id, token, UrllibTransport(), config.environment))
        return factory
    if not config.writes_allowed:
        raise drafts.DraftRefused(chat.WRITE_REPLY)
    return lambda token: CloverWriteClient(config.merchant_id, token, UrllibTransport(), config.environment)


class DryRunEngine(chat.BundleEngine):
    """Use the normal preview and journal; an approval records rather than applies."""

    def __init__(self, state, config, client_factory, *, read_loader=None, **owners_and_clock):
        super().__init__(state, config, client_factory, **owners_and_clock)
        self.read_loader = credential.load_token if read_loader is None else read_loader

    def _client(self):
        client = self.factory(self.read_loader(self.config.token_file))
        if not isinstance(client, DryRunWriteClient):
            raise drafts.DraftRefused(chat.WRITE_REPLY)
        return client

    def _gate(self, db, undo):
        # Same pause and Pacific-day budget as ApplyEngine._gate, without the
        # live credential condition. Rehearsal rows never receive a budget day.
        if db.execute("SELECT 1 FROM meta WHERE k='paused'").fetchone():
            raise drafts.DraftRefused("Till changes are paused.")
        if not undo:
            used = db.execute("SELECT count(*) FROM changes WHERE day=? AND json_extract(draft,'$.undo_of') IS NULL",
                              (self._day(),)).fetchone()[0]
            drafts._gate(self.config, used)

    def handle(self, text, *, sender, chat, edited=False, reaction=False, group=False):
        group = group or ";+;" in chat
        if text == "stop changes":
            return super().handle(text, sender=sender, chat=chat, edited=edited, reaction=reaction, group=group)
        # ApplyEngine.handle has no execution hook: it always makes a durable
        # live intent and reads back a mutation. A rehearsal does neither.
        if (sender, chat) not in self.owners or edited or reaction or group:
            raise drafts.DraftRefused("Only an owner's original private message can approve a till change.")
        with self.journal.locked() as db:
            code = text.removeprefix("yes ")
            row = db.execute("SELECT draft, expires, status FROM changes WHERE code=? AND sender=? AND chat=?",
                             (code, sender, chat)).fetchone()
            if not text.startswith("yes ") or row is None or row["status"] != "draft" or row["expires"] <= self.clock():
                raise drafts.DraftRefused("That is not a current till approval code.")
            entry = json.loads(row["draft"])
            draft = drafts.Draft(**{field: entry[field] for field in drafts.Draft.__dataclass_fields__})
            self._gate(db, draft.undo_of)
            client = self._client()
            start = len(client.requests)
            try:
                self._record(draft, client)
            except (drafts.DraftRefused, CloverRefused):
                self.journal.settle(db, code, "failed")
                raise
            except Exception:
                self.journal.settle(db, code, "uncertain")
                return "uncertain"
            self.journal.settle(db, code, "dry-run", client.requests[start:])
            return "dry-run"

    @staticmethod
    def _record(draft, client):
        item_id = draft.item_id
        if item_id:
            fresh = parse_item(client.get_item(item_id))
            if fresh.id != item_id or drafts.is_stale(draft, fresh):
                raise drafts.DraftRefused("The till changed; ask for a fresh draft and approve its new code.")
        sku = draft.after.get("sku")
        if sku and (draft.kind == "set_sku" or not item_id):
            if any(i.get("id") != item_id and any(
                    (i.get(field) or "").casefold() == sku.casefold() for field in ("sku", "code"))
                   for i in client.list_items()):
                raise drafts.DraftRefused("That SKU is now taken; ask for a fresh draft.")
        for request in draft.requests:
            path = request["path"]
            body = json.loads(json.dumps(request["json"]).replace("{newItemId}", item_id or "{newItemId}"))
            result = client.write(request["method"], path, body)
            if path == "/items":
                item_id = result["id"]
