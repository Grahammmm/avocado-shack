"""R4-AV-07: released SQLite table/column names are an append-only contract.

The floor below records the schema at 4922224ef13fdef7b24bf5f919613d2f81372a0f.
Keep existing entries when extending it for a new persisted field/table; never
rename/remove an entry to make a destructive release pass. Additional tables and
columns are allowed. This guards schema names, not every rollback compatibility
issue (types, constraints and data semantics still need review).

Only empty synthetic databases in a temporary private directory are opened. No
Git history, live config, service, network or participant records are needed.
"""
import contextlib
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import conversation, inbox, memory, relay
from hass.skills import backlog, openreq


# Independent of the production CREATE statements: a rename there must fail here.
# Group by database because identically named tables may have different columns.
FLOOR = {
    "conversation.sqlite3": {
        "messages": "provider_id disposition received_at",
        "message_chats": "provider_id chat",
        "drafts": "row_id change_id code state reason replaced_by draft_hash base ops_json summary sender chat "
                  "created_at expires_at commit screenshot checked_at proposed_at missing_json",
        "approvals": "id sender chat provider_id change_id draft_hash base expires_at approved_at",
        "outbox": "id chat text attachments created_at sent_at reply_to",
        "control": "name value set_at provider_id",
        "usage": "day calls",
        "interpreter_audit": "provider_id at backend fallback primary_error error seconds",
        "preview_retry": "row_id change_id chat due_at",
        "memory": "id key value kind source approved_change created_at superseded_at forgotten_at",
        "backlog": "id received_at reason summary text state",
        "open_requests": "request_id provider_id owner state skill slots_json calls_json texts_json asked_slot "
                         "question ask_json attachments_json draft_code pending_json asks created_at updated_at "
                         "expires_at closed_at",
    },
    "inbox.sqlite3": {
        "meta": "name value",
        "inbound": "provider_id received_at payload state disposition enqueued_at done_at tries next_try_at",
        "nonces": "nonce seen_at",
    },
    "relay.sqlite3": {
        "relay": "id chat text pictures created_at handed_at acked_at",
        "meta": "name value",
        "picture": "relay_id idx sha256 size data",
    },
    "community.sqlite3": {
        "subscriptions": "email newsletter hikes created_at updated_at consent_version",
        "rsvps": "id event_id email name party_size created_at",
    },
}
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def schema(db):
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {table: {row[1] for row in db.execute('PRAGMA table_info("' + table.replace('"', '""') + '")')}
            for table in tables if not table.startswith("sqlite_")}


class AdditiveStateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hass-additive-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"settings": {
            "ownerSenders": ["schema@example.invalid"], "ownerChat": "schema-fixture",
            "approvalTtlSeconds": 600,
        }}), encoding="utf-8")

    def assert_preserved(self, name, actual, expected=None):
        expected = expected if expected is not None else {
            table: set(columns.split()) for table, columns in FLOOR[name].items()}
        for table, columns in expected.items():
            with self.subTest(database=name, table=table):
                self.assertIn(table, actual, f"{name}: dropped or renamed table {table}")
                missing = columns - actual[table]
                self.assertFalse(missing, f"{name}.{table}: dropped or renamed columns {sorted(missing)}")

    def open_conversation(self):
        conv = conversation.Conversation(self.state, None, None, lambda: NOW)
        self.addCleanup(conv.db.close)
        # Lazy tables are part of saved state too, even if this owner has never
        # used the feature. Execute the same DDL used by their production paths.
        for sql in (conversation.CONTROL, conversation.USAGE, conversation.AUDIT,
                    conversation.Conversation.PREVIEW_RETRY):
            conv.db.execute(sql)
        memory.Memory.on_connection(conv.db, lambda: NOW, self.state)
        backlog.Backlog(conv.db, lambda: NOW)
        openreq.OpenRequests(conv.db).ensure("schema-fixture")
        return conv.db

    def test_conversation_fresh_and_reopen_are_additive(self):
        db = self.open_conversation()
        self.assert_preserved("conversation.sqlite3", schema(db))
        before = schema(db)
        db.close()
        self.assert_preserved("conversation.sqlite3", schema(self.open_conversation()), before)

    def test_inbox_fresh_and_reopen_are_additive(self):
        for _ in range(2):
            store = inbox.Inbox(self.state, start_at=NOW.isoformat(), clock=lambda: NOW)
            with contextlib.closing(store.db) as db:
                self.assert_preserved("inbox.sqlite3", schema(db))

    def test_relay_fresh_and_reopen_are_additive(self):
        for _ in range(2):
            with contextlib.closing(relay.RelayStore(self.state).db) as db:
                self.assert_preserved("relay.sqlite3", schema(db))

    def test_community_fresh_and_reopen_are_additive(self):
        path = Path(__file__).resolve().parents[2] / "storefront-mockup" / "community-server.py"
        spec = importlib.util.spec_from_file_location("additive_community", path)
        assert spec is not None and spec.loader is not None
        community = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(community)
        setattr(community, "DB", self.root / "community.sqlite3")  # set before the first connect; never use its runtime default
        for _ in range(2):
            with contextlib.closing(community.connect()) as db:
                self.assert_preserved("community.sqlite3", schema(db))


if __name__ == "__main__":
    unittest.main()
