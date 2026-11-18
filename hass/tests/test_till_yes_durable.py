"""M2: real child-process exits, private synthetic till/journal, no credential reads."""
import json
import os
import re
from pathlib import Path
from unittest import mock

from hass import conversation
from hass.clover import approvals, chat
from hass.clover.client import CloverWriteClient
from hass.clover.config import from_settings
from hass.clover.credential import Token
from hass.tests import test_clover_apply as apply_tests, test_clover_chat as chat_tests
from hass.tests import test_clover_client as client_tests, test_conversation as conv_tests


class DurableYes(client_tests.NoNetwork, conv_tests.ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.state = Path(self.repo.state)
        chat_tests.seed(self.state)
        self.block = {**chat_tests.BLOCK, "writes": True, "liveApproved": True,
                      "writeTokenFile": str(self.state / "never-opened-fake-token")}
        self.remote = self.state / "synthetic-till.json"
        self.remote.write_text(json.dumps({"items": apply_tests.Till().items, "writes": 0}))
        self.conv.db.close()
        self.conv = self.start()
        self.assertEqual(self.say("set Hass avocado to 7"), "till-draft")
        self.code = re.search(r"Reply yes ([0-9a-f]{8})", self.replies()[0])[1]
        self.pid = "synthetic-durable-yes"

    def start(self, crash=None, attach=True):
        conv = self.open(conversation.Editor(str(self.state)))
        self.addCleanup(conv.db.close)
        till = apply_tests.Till()

        def transport(req):
            data = json.loads(self.remote.read_text())
            till.items = data["items"]
            result = till(req)
            if req.method != "GET":
                self.remote.write_text(json.dumps({"items": till.items, "writes": data["writes"] + 1}))
                if crash == "accepted": os._exit(73)
            return result

        client = CloverWriteClient("FAKEMERCH0001", Token(client_tests.FAKE_TOKEN), transport, min_interval=0)
        engine = chat.BundleEngine(self.state, from_settings(self.block), lambda _: None,
                                   mike=(conv_tests.OWNER, conv_tests.CHAT))
        engine._client = lambda: client  # fake in-memory token only; no token file is read
        if crash == "intent": client.get_item = lambda _: os._exit(73)
        desk = chat.TillDesk(str(self.state), self.block, engine=engine)
        if attach: conv.till = desk
        else: conv._till = desk  # exercise redelivery independently of the startup hook
        return conv

    def status(self):
        with self.conv.till.engine.journal.locked() as db:
            return db.execute("SELECT status FROM changes WHERE code=?", (self.code,)).fetchone()[0]

    def writes(self):
        return json.loads(self.remote.read_text())["writes"]

    def kill(self, boundary):
        self.conv.db.close()
        child = os.fork()
        if child == 0:
            try:
                self.conv = self.start(boundary)
                if boundary == "before-job": approvals.save = lambda *a: os._exit(73)
                if boundary == "after-job": self.conv._till_apply = lambda *a: os._exit(73)
                if boundary == "outcome-tx": approvals.finish = lambda *a: os._exit(73)
                if boundary == "after-outcome":
                    real = self.conv._till_apply
                    def done(*args):
                        real(*args)
                        os._exit(73)
                    self.conv._till_apply = done
                self.say("yes " + self.code, pid=self.pid)
            except BaseException:
                os._exit(74)
            os._exit(75)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 73)

    def check_restart(self, boundary, uncertain=False):
        self.kill(boundary)
        self.conv = self.start()
        self.assertEqual(self.say("yes " + self.code, pid=self.pid),
                         "till-approved" if boundary == "before-job" else "duplicate")
        self.assertEqual(self.writes(), 1 if boundary != "intent" else 0)
        self.assertEqual(self.status(), "uncertain" if uncertain else "applied")
        stock = json.loads(self.remote.read_text())["items"]["FAKEITEM00002"]["itemStock"]["quantity"]
        self.assertEqual(stock, 40 if boundary == "intent" else 7)
        rows = self.conv.db.execute("SELECT * FROM outbox WHERE sent_at IS NULL").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["chat"], conv_tests.CHAT)
        self.assertIn("check that item" if uncertain else "read", rows[0]["text"])
        self.assertEqual(self.conv.db.execute("SELECT done FROM till_jobs").fetchall()[0][0], 1)
        self.assertEqual(len(self.replies()), 1)
        self.conv.db.close()
        self.conv = self.start()
        self.say("yes " + self.code, pid=self.pid)
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.writes(), 1 if boundary != "intent" else 0)

    def test_death_before_job_rolls_back_message_and_redelivery_runs_once(self):
        self.check_restart("before-job")

    def test_death_after_durable_job_startup_runs_once(self):
        self.check_restart("after-job")

    def test_death_after_intent_holds_durably_and_notifies_owner(self):
        self.check_restart("intent", uncertain=True)

    def test_death_after_accepted_write_before_readback_never_resends(self):
        self.check_restart("accepted", uncertain=True)

    def test_death_in_outcome_transaction_rolls_back_reply_then_only_delivers_result(self):
        self.check_restart("outcome-tx")

    def test_death_after_outcome_commit_never_enqueues_a_second_outcome(self):
        self.check_restart("after-outcome")

    def test_same_provider_redelivery_reconciles_without_startup(self):
        with mock.patch.object(self.conv, "_till_apply", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.say("yes " + self.code, pid=self.pid)
        self.assertEqual(self.status(), "draft")
        self.assertEqual(self.say("yes " + self.code, pid=self.pid), "duplicate")
        self.assertEqual((self.writes(), len(self.replies())), (1, 1))
        self.assertEqual(self.say("yes " + self.code, pid="another-provider"), "till-approved")
        self.assertEqual((self.writes(), self.replies()), (1, [approvals.SAVED]))

    def test_pending_same_code_gets_an_explicit_pending_outcome(self):
        with mock.patch.object(self.conv, "_till_apply", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.say("yes " + self.code, pid=self.pid)
        with mock.patch.object(approvals, "recover"):
            self.assertEqual(self.say("yes " + self.code, pid="second-pending"), "till-approved")
        self.assertEqual((self.writes(), self.status(), self.replies()), (0, "draft", [approvals.PENDING]))
        approvals.recover(self.conv)
        self.assertEqual((self.writes(), self.status(), len(self.replies())), (1, "applied", 1))
        self.assertEqual(self.say("yes " + self.code, pid="second-pending"), "duplicate")
        self.assertEqual((self.writes(), self.replies()), (1, []))

    def test_recovery_refuses_expired_drafts_without_writing(self):
        self.kill("after-job")
        self.conv = self.start(attach=False)
        self.conv.till.engine.clock = lambda: float("inf")
        approvals.recover(self.conv)
        self.assertEqual((self.writes(), len(self.replies())), (0, 1))
        self.say("yes " + self.code, pid=self.pid)
        self.assertEqual(self.replies(), [])

    def test_recovery_rechecks_stale_draft_before_any_write(self):
        self.kill("after-job")
        data = json.loads(self.remote.read_text())
        data["items"]["FAKEITEM00002"]["modifiedTime"] += 1
        self.remote.write_text(json.dumps(data))
        self.conv = self.start()
        self.assertEqual((self.writes(), self.status(), len(self.replies())), (0, "failed", 1))

    def test_concurrent_startups_share_one_execution_and_outcome(self):
        self.kill("after-job")
        children = []
        for _ in range(2):
            child = os.fork()
            if child == 0:
                try:
                    self.start().db.close()
                except BaseException:
                    os._exit(74)
                os._exit(0)
            children.append(child)
        for child in children:
            self.assertEqual(os.waitstatus_to_exitcode(os.waitpid(child, 0)[1]), 0)
        self.conv = self.start()
        self.assertEqual((self.writes(), len(self.replies())), (1, 1))

    def test_pause_and_disconnected_engine_hold_without_writing(self):
        self.kill("after-job")
        self.conv = self.start(attach=False)
        with mock.patch.object(self.conv, "_paused", return_value=True): approvals.recover(self.conv)
        self.assertEqual((self.writes(), len(self.replies())), (0, 1))
        with self.conv._tx(): self.conv.db.execute("UPDATE till_jobs SET done=0")
        self.conv.till = chat.TillDesk(str(self.state), self.block)
        self.assertIsNone(self.conv.till.engine)
        self.assertEqual((self.writes(), len(self.replies())), (0, 1))

    def test_fresh_approval_after_paused_recovery_is_not_silently_lost(self):
        self.kill("after-job")
        self.conv = self.start(attach=False)
        with mock.patch.object(self.conv, "_paused", return_value=True): approvals.recover(self.conv)
        self.assertEqual((self.writes(), self.status(), self.replies()), (0, "draft", [approvals.HELD]))
        self.assertEqual(self.say("yes " + self.code, pid="fresh-approval"), "till-approved")
        self.assertEqual((self.writes(), self.status()), (1, "applied"))
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual(self.say("yes " + self.code, pid="fresh-approval"), "duplicate")
        self.assertEqual((self.writes(), self.replies()), (1, []))

    def test_apply_false_is_durable_held_and_never_upgrades_on_restart(self):
        msg = conversation.Inbound(self.pid, conv_tests.CHAT, conv_tests.OWNER, "yes " + self.code)
        self.conv.handle(msg, apply=False)
        self.assertEqual((self.writes(), len(self.replies())), (0, 1))
        self.conv.db.close()
        self.conv = self.start()
        self.conv.handle(msg)
        self.assertEqual((self.writes(), self.replies()), (0, []))

    def test_wrong_provider_replay_cannot_redirect_the_outcome(self):
        self.kill("after-job")
        self.conv = self.start(attach=False)
        self.say("yes " + self.code, pid=self.pid, sender=conv_tests.STRANGER, chat="wrong-chat")
        rows = self.conv.db.execute("SELECT chat FROM outbox WHERE sent_at IS NULL").fetchall()
        self.assertEqual([r[0] for r in rows], [conv_tests.CHAT])
        self.assertEqual(self.writes(), 1)

    def test_pending_cap_backpressures_atomically_and_completed_rows_can_prune(self):
        with mock.patch.object(self.conv, "_till_apply", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.say("yes " + self.code, pid=self.pid)
        with mock.patch.object(approvals, "MAX_JOBS", 1):
            with self.assertRaisesRegex(RuntimeError, "queue full"):
                self.say("yes " + self.code, pid="not-acknowledged")
            self.assertIsNone(self.conv.db.execute("SELECT 1 FROM messages WHERE provider_id='not-acknowledged'").fetchone())
            approvals.recover(self.conv)
            self.replies()
            self.say("yes " + self.code, pid="after-prune")
            self.assertEqual(self.conv.db.execute("SELECT count(*) FROM till_jobs").fetchone()[0], 1)
        self.assertEqual(self.writes(), 1)
