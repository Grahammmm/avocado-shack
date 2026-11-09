"""RF0824-10 tests: the receiver commits the inbound replay nonce and the queue row in ONE SQLite transaction, so a failed
insert cannot leave a nonce that makes an exact retry report `duplicate`. Real SQLite faults (set_authorizer) on
isolated fixtures; nothing is mocked in production code, nothing is sent.
Run: python3 -B -m unittest hass.tests.test_receiver_atomic_intake"""

import json, sqlite3, unittest  # noqa: E401
from datetime import timedelta

from hass import inbox as inbox_mod, receiver
from hass.tests.test_bridge import event
from hass.tests.test_conversation import T0
from hass.tests.test_receiver import NOW, SECRET, ReceiverTestCase


def deny_insert_into(table):
    def authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_INSERT and arg1 == table: return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return authorizer


def deny_commit(action, arg1, arg2, dbname, source):
    if action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT": return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class AtomicIntakeTests(ReceiverTestCase):
    def reopen(self):
        box = inbox_mod.Inbox(str(self.repo.state), None, clock=lambda: self.now)
        self.addCleanup(box.close)
        return box

    def durable(self):
        """(nonce rows, inbound rows) as a freshly opened connection sees them."""
        box = self.reopen()
        nonces = [tuple(r) for r in box.db.execute("SELECT nonce, seen_at FROM nonces ORDER BY nonce")]
        rows = [tuple(r) for r in box.db.execute("SELECT provider_id, state FROM inbound ORDER BY provider_id")]
        box.close()
        return nonces, rows

    def accept(self, raw):
        return self.rx.accept(raw, secret=SECRET, now=NOW)

    def test_insert_failure_rolls_back_nonce_then_exact_retry_queues(self):
        raw = self.seal(event("new-message"))
        self.inbox.db.set_authorizer(deny_insert_into("inbound"))
        with self.assertRaises(sqlite3.DatabaseError): self.accept(raw)
        self.assertFalse(self.inbox.db.in_transaction)
        self.assertEqual(self.durable(), ([], []))
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 0)
        self.inbox.db.set_authorizer(None)
        self.assertEqual(self.accept(raw)["result"], "queued")  # the exact same envelope
        nonces, rows = self.durable()
        self.assertEqual((len(nonces), [r[1] for r in rows]), (1, ["pending"]))
        again = self.accept(raw)
        self.assertEqual((again["result"], again["reason"]), ("duplicate", "this exact envelope was already received"))
        self.assertEqual(self.durable(), (nonces, rows))

    def test_failed_intake_restores_nonce_pruning(self):
        self.now = T0 - timedelta(days=3)
        self.inbox.seen().add("ee" * 16)  # long expired by the time of the intake
        self.now = T0
        before = self.durable()
        self.assertEqual(len(before[0]), 1)
        raw = self.seal(event("new-message"))
        self.inbox.db.set_authorizer(deny_insert_into("inbound"))
        with self.assertRaises(sqlite3.DatabaseError): self.accept(raw)
        self.assertEqual(self.durable(), before)  # the pruned row is back, no new nonce
        self.inbox.db.set_authorizer(None)
        self.assertEqual(self.accept(raw)["result"], "queued")
        nonces, rows = self.durable()
        self.assertEqual(([n for n, _ in nonces], len(rows)), ([f"{self.nonce:032x}"], 1))  # pruned as before

    def test_outer_rollback_undoes_successful_nested_nonce_and_enqueue(self):
        msg = self.inbound_msg()
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with self.inbox._tx():
                self.inbox.seen().add("aa" * 16)
                self.assertEqual(self.inbox.enqueue(msg), "queued")
                self.assertTrue(self.inbox.db.in_transaction)  # inner success released only its savepoint
                raise RuntimeError("boom")
        self.assertFalse(self.inbox.db.in_transaction)
        self.assertEqual(self.durable(), ([], []))

    def test_inner_failure_rolls_back_only_its_savepoint_and_standalone_calls_commit(self):
        msg = self.inbound_msg()
        with self.inbox._tx():
            self.inbox.seen().add("bb" * 16)
            self.inbox.db.set_authorizer(deny_insert_into("inbound"))
            with self.assertRaises(sqlite3.DatabaseError): self.inbox.enqueue(msg)
            self.inbox.db.set_authorizer(None)
            self.assertTrue(self.inbox.db.in_transaction)  # the caller's transaction is intact
        self.assertEqual([n for n, _ in self.durable()[0]], ["bb" * 16])
        self.assertEqual(self.durable()[1], [])
        self.assertEqual(self.inbox.enqueue(msg), "queued")  # standalone: its own BEGIN/COMMIT
        self.inbox.seen().add("cc" * 16)
        self.assertFalse(self.inbox.db.in_transaction)
        nonces, rows = self.durable()
        self.assertEqual(([n for n, _ in nonces], [r[0] for r in rows]), (["bb" * 16, "cc" * 16], [msg.provider_id]))

    def test_commit_failure_rolls_back_and_same_connection_can_retry(self):
        raw = self.seal(event("new-message"))
        self.inbox.db.set_authorizer(deny_commit)
        with self.assertRaises(sqlite3.DatabaseError): self.accept(raw)
        self.assertFalse(self.inbox.db.in_transaction)
        self.assertEqual(self.durable(), ([], []))
        self.inbox.db.set_authorizer(None)
        self.assertEqual(self.accept(raw)["result"], "queued")  # same connection, same bytes
        nonces, rows = self.durable()
        self.assertEqual((len(nonces), len(rows)), (1, 1))

    def inbound_msg(self):
        env = json.loads(self.seal(event("new-message")))
        return inbox_mod.Inbound(**env["body"])

    def test_success_history_duplicate_and_rejections_keep_contract(self):
        stages = []

        def stage(name, provider_id, **extra):  # runs after the commit: a fresh reader already sees the row
            stages.append((name, self.inbox.db.in_transaction, len(self.durable()[1])))
        self.rx.stage = stage
        first = self.seal(event("new-message"))
        self.assertEqual(self.accept(first), {"result": "queued", "draft_id": None, "disposition": None,
                                              "reason": "stored; the next drain handles it"})
        self.assertEqual(stages, [("receiver-accepted", False, 1)])
        replay = self.accept(first)
        self.assertEqual(replay, {"result": "duplicate", "draft_id": None, "disposition": None,
                                  "reason": "this exact envelope was already received"})
        same_id = self.accept(self.seal(event("new-message")))  # new nonce, id already stored
        self.assertEqual((same_id["result"], same_id["reason"]),
                         ("duplicate", "this message id was already received; not queued again"))
        self.assertEqual(len(self.durable()[0]), 2)  # that nonce is recorded with the existing message
        early = self.event_from("new-message", guid="FAKE-EARLY", dateCreated=(NOW - 60) * 1000)
        hist = self.rx.accept(self.seal(early, now=NOW - 60), secret=SECRET, now=NOW - 60)
        self.assertEqual((hist["result"], hist["reason"]),
                         ("history", "sent before the recorded start point; kept as history only"))
        before = self.durable()
        bad_mac = self.accept(self.seal(self.event_from("new-message", guid="FAKE-B"), secret=b"x" * 40))
        stale = self.accept(self.seal(self.event_from("new-message", guid="FAKE-S"), now=NOW - 1000))
        junk = self.accept("{not json")
        self.assertEqual([(r["result"], r["reason"]) for r in (bad_mac, stale, junk)],
                         [("rejected", receiver.REJECTED["mac"]), ("rejected", receiver.REJECTED["stale"]),
                          ("rejected", receiver.REJECTED["shape"])])
        self.assertEqual(self.durable(), before)  # a rejection leaves no nonce and no row
        self.assertEqual(len(stages), 1)  # only the one queued message is staged
        self.assertEqual((self.drafts(), self.reply.calls, self.editor.applies, self.unsent()), ([], [], 0, 0))


if __name__ == "__main__":
    unittest.main()
