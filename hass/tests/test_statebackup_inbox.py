"""H20/H16 tests: the state backup covers the inbound queue (`inbox.sqlite3`); fixture setup of test_statebackup."""

import contextlib, hashlib, json, os, random, sqlite3  # noqa: E401
from datetime import timedelta
from unittest import mock

from hass import conversation, inbox as inbox_mod, statebackup
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import CHAT, OWNER, T0
from hass.tests.test_statebackup import BackupTestCase

INBOX = statebackup.INBOX

class InboxBackupTestCase(BackupTestCase):
    def setUp(self):
        super().setUp()
        self.box = self.open_inbox(self.repo.state, T0.isoformat())

    def open_inbox(self, state, start_at=None):
        box = inbox_mod.Inbox(str(state), start_at, clock=lambda: self.now)
        self.addCleanup(box.close)
        return box

    def msg(self, pid, text, seconds):
        return conversation.Inbound(pid, CHAT, OWNER, text, False, "new", (T0 + timedelta(seconds=seconds)).isoformat())

    def fill(self):  # start point T0; one history, one done and one pending row
        self.assertEqual(self.box.enqueue(self.msg("h1", "history", -60)), "history")
        self.assertEqual(self.box.enqueue(self.msg("d1", "history", 1)), "queued")
        self.assertEqual(self.box.drain(self.conv), [("d1", "history")])
        self.assertEqual(self.box.enqueue(self.msg("p1", "history", 2)), "queued")

    def rows(self, path):
        with contextlib.closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as db:
            return {r[0]: r[1:] for r in db.execute("SELECT provider_id, state, payload FROM inbound")}

    def restored(self, new):
        ed = conversation.Editor(new, {**fixture_ops.registry(), **load_registry()})
        return conversation.Conversation(str(new), ed, self.interp, lambda: self.now, self.previewer)

    def rehash(self, backup, data):
        (backup / INBOX).write_bytes(data)
        doc = json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))
        doc["files"][INBOX] = hashlib.sha256(data).hexdigest()
        (backup / statebackup.MANIFEST).write_text(json.dumps(doc), "utf-8")

class RoundTripTests(InboxBackupTestCase):
    def test_restore_keeps_start_point_and_pending_rows(self):
        self.fill()
        backup = self.backup()
        self.assertIn(INBOX, self.files(backup))
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")
        new = self.tmp / "restored"
        self.assertEqual(statebackup.restore(str(backup), str(new), str(self.drill_wt))["result"], "ok")
        self.assertEqual((new / INBOX).stat().st_mode & 0o777, 0o600)
        rows = self.rows(new / INBOX)
        self.assertEqual({pid: row[0] for pid, row in rows.items()}, {"h1": "history", "d1": "done", "p1": "pending"})
        self.assertEqual((rows["h1"][1], rows["d1"][1]), (None, None))
        self.assertEqual(json.loads(rows["p1"][1])["provider_id"], "p1")
        box = self.open_inbox(new)  # start_at=None reuses the restored start point
        self.assertEqual(box.start_at, T0)
        self.assertEqual(box.drain(self.restored(new)), [("p1", "history")])

    def test_no_inbox_backs_up_the_same_file_set(self):
        self.box.close()
        (self.repo.state / INBOX).unlink()
        self.apply("kumquat desc")
        state = self.repo.state
        expected = {"config.json", "conversation.sqlite3"} | {
            f"{d}/{name}" for d in statebackup.DIRS if (state / d).is_dir() for name in os.listdir(state / d)}
        self.assertEqual(set(self.files(self.backup())), expected)

    def test_inbox_is_snapshotted_before_the_conversation_store(self):
        self.fill()
        with mock.patch.object(statebackup, "_snapshot", wraps=statebackup._snapshot) as snap, \
                mock.patch.object(statebackup, "_copy", wraps=statebackup._copy) as copy:
            self.backup()
        self.assertEqual([call.args[0].name for call in snap.call_args_list], [INBOX, statebackup.DB])
        self.assertNotIn(INBOX, [call.args[0].name for call in copy.call_args_list])

    def test_message_handled_between_snapshots_is_a_duplicate_after_restore(self):
        self.fill()
        real = statebackup._snapshot

        def snapshot(src, dst):  # p1 is handled after the inbox snapshot, before the conversation snapshot
            if src.name == statebackup.DB: self.assertEqual(self.box.drain(self.conv), [("p1", "history")])
            real(src, dst)
        with mock.patch.object(statebackup, "_snapshot", snapshot):
            backup = self.backup()
        self.assertEqual(self.rows(backup / INBOX)["p1"][0], "pending")
        new = self.tmp / "restored"
        self.assertEqual(statebackup.restore(str(backup), str(new), str(self.drill_wt))["result"], "ok")
        conv = self.restored(new)
        outbox = conv.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        self.assertEqual(self.open_inbox(new).drain(conv), [("p1", "duplicate")])
        self.assertEqual(conv.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], outbox)  # no second reply

    def test_paused_restore_leaves_the_inbox_bytes_alone(self):
        self.fill()
        backup, new = self.backup(), self.tmp / "restored"
        got = statebackup.restore(str(backup), str(new), str(self.drill_wt), paused=True, now=T0)
        self.assertEqual((got["result"], got["paused"]), ("ok", True))
        self.assertEqual((new / INBOX).read_bytes(), (backup / INBOX).read_bytes())
        self.assertNotEqual((new / statebackup.DB).read_bytes(), (backup / statebackup.DB).read_bytes())

class DamageTests(InboxBackupTestCase):
    def test_corrupt_inbox_fails_verify_and_restore(self):
        self.fill()
        backup = self.backup()
        self.rehash(backup, random.Random(0).randbytes(4096))
        got = statebackup.verify(str(backup))
        self.assertEqual(got, {"result": "corrupt", "problems": [f"integrity check failed: {INBOX}"]})
        into, before = self.tmp / "restored", sorted(os.listdir(self.tmp))
        got = statebackup.restore(str(backup), str(into), str(self.drill_wt))
        self.assertEqual(got["result"], "corrupt")
        self.assertEqual((into.exists(), sorted(os.listdir(self.tmp))), (False, before))

    def test_changed_inbox_byte_is_a_hash_mismatch(self):
        self.fill()
        backup = self.backup()
        data = bytearray((backup / INBOX).read_bytes())
        data[len(data) // 2] ^= 1
        (backup / INBOX).write_bytes(bytes(data))
        got = statebackup.verify(str(backup))
        self.assertEqual(got, {"result": "corrupt", "problems": [f"hash mismatch: {INBOX}"]})

class CreateRefusalTests(InboxBackupTestCase):
    def test_leftover_journal_and_lookalikes_are_refused(self):
        self.fill()
        (self.repo.state / "drafts").mkdir(mode=0o700, exist_ok=True)
        for name in (f"{INBOX}-journal", f"{INBOX}-wal", "inbox.sqlite3.bak", "INBOX.sqlite3", f"drafts/{INBOX}"):
            with self.subTest(name):
                statebackup._write_new(self.repo.state / name, b"x")
                got = statebackup.create(str(self.repo.state), str(self.bk))
                self.assertEqual((got["result"], got["problems"]), ("refused", [f"unknown entry: {name}"]))
                self.assertEqual(os.listdir(self.bk), [])
                (self.repo.state / name).unlink()

    def test_symlinked_inbox_is_refused_and_target_untouched(self):
        self.fill()
        self.box.close()
        aside = self.tmp / "inbox-aside.sqlite3"
        (self.repo.state / INBOX).rename(aside)
        (self.repo.state / INBOX).symlink_to(aside)
        before = aside.read_bytes()
        got = statebackup.create(str(self.repo.state), str(self.bk))
        self.assertEqual((got["result"], got["problems"]), ("refused", [f"symlink: {INBOX}"]))
        self.assertEqual((aside.read_bytes(), os.listdir(self.bk)), (before, []))
