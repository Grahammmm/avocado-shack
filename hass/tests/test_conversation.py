"""H05 tests: approval state machine and fixture conversation.

Each test uses the H02 throwaway Git repo (linked writer worktree, private 0700 state dir), the test-only ops in
fixture_ops, a FixtureInterpreter and an injected clock. Writer commits are counted with git rev-list --count HEAD.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import sqlite3
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation, editor
from hass.content_model import REPO_ROOT
from hass.fixture_chat import FixtureAdapter
from hass.tests import fixture_ops
from hass.tests.test_editor import DESC, HOURS, NEW_HOURS, WriterRepo, _req, git

OWNER, STRANGER = "owner@example.invalid", "stranger@example.invalid"
CHAT, GROUP = "chat-fixture-owner", "chat-fixture-group"
SETTINGS = {"ownerSenders": [OWNER], "ownerChat": CHAT, "approvalTtlSeconds": 600}
T0 = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)  # 09:00 PST
FIXTURE = REPO_ROOT / "hass" / "tests" / "fixtures" / "conversation-basic.jsonl"


def _ops(*ops):
    return {"ops": _req(*ops)["ops"], "revises": None}


class CountingEditor(conversation.Editor):
    def __init__(self, state):
        super().__init__(state, fixture_ops.registry())
        self.applies, self.crash = 0, False

    def apply(self, change_id, draft_hash):
        self.applies += 1
        if self.crash: raise RuntimeError("simulated crash before the editor ran")
        return super().apply(change_id, draft_hash)


class ConversationTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = WriterRepo()
        self.addCleanup(self.repo.cleanup)
        self.set_settings(SETTINGS)
        self.now, self.n, self.out = T0, 0, FixtureAdapter()
        self.interp = conversation.FixtureInterpreter({
            "hours": _ops((HOURS, {"hours": NEW_HOURS})),
            "desc": _ops((DESC, {"id": "photo-product-001", "description": "Ripe and creamy."})),
            "when?": {"question": "Which day should change?"}})
        self.editor = CountingEditor(self.repo.state)
        self.conv = self.open()
        self.base = self.count()

    def set_settings(self, settings):
        cfg = json.loads((self.repo.state / "config.json").read_text("utf-8"))
        editor._write_json(self.repo.state / "config.json", {**cfg, "settings": settings})

    def open(self, ed=None):
        return conversation.Conversation(str(self.repo.state), ed or self.editor, self.interp, lambda: self.now)

    def count(self):
        return int(git(self.repo.wt, "rev-list", "--count", "HEAD"))

    def commits(self):
        return self.count() - self.base

    def say(self, text, pid=None, chat=CHAT, sender=OWNER, from_me=False, kind="new"):
        self.n += 1
        msg = conversation.Inbound(pid or f"m{self.n}", chat, sender, text, from_me, kind, self.now.isoformat())
        return self.conv.handle(msg)

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def propose(self, text):
        self.assertEqual(self.say(text), "proposed")
        [reply] = self.replies()
        return self.drafts()[-1], reply


class FlowTests(ConversationTestCase):
    def test_happy_path_rejection_and_question(self):
        draft, reply = self.propose("hours")
        self.assertEqual(draft["state"], "proposed")
        self.assertEqual(draft["code"], draft["draft_hash"][7:11])
        self.assertTrue(reply.startswith(f"Draft {draft['code']}:"), reply)
        self.assertIn("store store: hours", reply)
        self.assertIn("Expires 2026-11-02 09:10 PST.", reply)
        self.assertTrue(reply.endswith("Reply yes to apply, no to cancel, or send a correction."))
        self.assertEqual(self.say("Yes!"), "approved")
        [reply] = self.replies()
        self.assertTrue(reply.startswith(f"Applied {draft['code']}: store store: hours"), reply)
        self.assertEqual(self.commits(), 1)
        self.assertEqual((self.drafts()[0]["state"], self.drafts()[0]["commit"]), ("applied", self.repo.head()))
        second, _reply = self.propose("desc")
        self.assertEqual(self.say("no"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {second['code']}; nothing changed."])
        self.assertEqual((self.drafts()[1]["state"], self.drafts()[1]["reason"]), ("rejected", "owner"))
        self.assertEqual(self.say("when?"), "question")
        self.assertEqual(self.replies(), ["Which day should change?"])
        self.assertEqual((len(self.drafts()), self.commits()), (2, 1))

    def test_duplicates_echoes_edits_and_strangers_change_nothing(self):
        self.propose("hours")
        self.assertEqual(self.say("yes", pid="yes-1"), "approved")
        self.replies()
        self.propose("desc")
        before = self.drafts()
        cases = [("duplicate", dict(pid="yes-1")), ("echo", dict(from_me=True)), ("not-read", dict(kind="edited")),
                 ("ignored", dict(sender=STRANGER)), ("ignored", dict(chat=GROUP))]
        for disposition, kwargs in cases:
            with self.subTest(case=kwargs):
                self.assertEqual(self.say("yes", **kwargs), disposition)
                reply = [conversation.NOT_READ_REPLY] if disposition == "not-read" else []
                self.assertEqual((self.replies(), self.commits(), self.drafts()), (reply, 1, before))
        self.assertEqual(self.say("zqx stranger request", sender=STRANGER), "ignored")
        stored = (self.repo.state / "conversation.sqlite3").read_bytes()
        self.assertNotIn(b"zqx", stored)
        self.assertNotIn(STRANGER.encode(), stored)
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.commits(), 2)

    def test_expired_approval_is_refused(self):
        draft, _reply = self.propose("hours")
        self.now = T0 + timedelta(seconds=600)
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), [f"{draft['code']} expired at 2026-11-02 09:10 PST; nothing changed."])
        self.assertEqual((self.drafts()[0]["state"], self.commits()), ("expired", 0))
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.assertIn("expired", self.replies()[0])
        self.assertEqual(self.commits(), 0)

    def assert_late_approvals_refused(self, old, closed_text):
        """After `old` closed, the same request repeats it: neither `yes <old code>` nor a bare `yes` applies it."""
        new, reply = self.propose("hours")
        self.assertEqual(new["draft_hash"], old["draft_hash"])  # same ops on the same base: the A2 draft repeats
        self.assertNotEqual(new["code"], old["code"])
        self.assertIn(f"Reply yes {new['code']} to apply", reply)
        self.assertEqual(self.say(f"yes {old['code']}"), "no-target")
        self.assertEqual(self.replies(), [closed_text])
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), [f"{new['code']} repeats a draft that was closed; reply yes {new['code']} to apply it."])
        self.assertEqual((self.drafts()[-1]["state"], self.commits(), self.editor.applies), ("proposed", 0, 0))
        self.assertEqual(self.say(f"yes {new['code']}"), "approved")
        self.assertEqual((self.drafts()[-1]["state"], self.commits(), self.editor.applies), ("applied", 1, 1))

    def test_cancelled_code_is_never_reused_by_a_repeat(self):
        old, _reply = self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assert_late_approvals_refused(old, f"{old['code']} was cancelled (owner); nothing changed.")

    def test_expired_code_is_never_reused_by_a_repeat(self):
        old, _reply = self.propose("hours")
        self.now = T0 + timedelta(seconds=601)
        self.assert_late_approvals_refused(old, f"{old['code']} expired at 2026-11-02 09:10 PST; nothing changed.")

    def test_ambiguous_yes_and_revision(self):
        one, _r = self.propose("hours")
        two, _r = self.propose("desc")
        self.assertEqual(self.say("yes"), "no-target")
        [reply] = self.replies()
        self.assertIn(f"{one['code']}: ", reply)
        self.assertIn(f"{two['code']}: ", reply)
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.say(f"yes {two['code']}"), "approved")
        self.assertTrue(self.replies()[0].startswith(f"Applied {two['code']}"))
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.interp.mapping["fix"] = {"ops": _req((HOURS, {"hours": ["Daily 8am–7pm"]}))["ops"], "revises": one["code"]}
        three, _r = self.propose("fix")
        first = self.drafts()[0]
        self.assertEqual((first["state"], first["reason"], first["replaced_by"]), ("rejected", "revised", three["code"]))
        self.assertEqual(self.say(f"yes {one['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{one['code']} was replaced by {three['code']}."])
        self.assertEqual(self.commits(), 1)

    def test_incomplete_correction_supersedes_proposal(self):
        old, _r = self.propose("hours")
        self.interp.mapping["fix"] = {"ops": _req((HOURS, {}))["ops"], "revises": old["code"]}
        self.assertEqual(self.say("fix"), "needs-details")
        self.replies()
        first, pending = self.drafts()
        self.assertEqual((first["state"], first["reason"], first["replaced_by"]), ("rejected", "revised", pending["code"]))
        self.assertEqual(pending["state"], "needs-details")
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), [f"{pending['code']} still needs details: {pending['summary']}"])  # AV1737-05
        self.assertEqual(self.say(f"yes {old['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{old['code']} was replaced by {pending['code']}."])
        self.assertEqual((self.commits(), self.editor.applies), (0, 0))
        # A different value from the superseded draft (an identical one is a repeat that needs `yes <code>`).
        self.interp.mapping["done"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": pending["code"]}
        self.assertEqual(self.say("done"), "proposed")
        self.replies()
        self.assertEqual([d["state"] for d in self.drafts()], ["rejected", "proposed"])
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.replies(), [f"Applied {pending['code']}: store store: hours"])
        self.assertEqual((self.commits(), self.drafts()[1]["state"]), (1, "applied"))

    def test_stale_approval_redrafts_and_never_writes_old_draft(self):
        old, _r = self.propose("hours")
        other = self.repo.prepare(_req((DESC, {"id": "photo-product-001", "description": "Picked this week."})))
        self.assertEqual(self.repo.apply(other["draft"])["result"], "applied")
        self.assertIn("hass/content/products.json", git(self.repo.wt, "show", "--name-only", "--format=", "HEAD"))
        self.base = self.count()
        self.assertEqual(self.say("yes"), "approved")
        [reply] = self.replies()
        stale, new = self.drafts()
        self.assertEqual((stale["state"], stale["reason"], self.commits()), ("rejected", "stale", 0))
        self.assertEqual(new["state"], "proposed")
        self.assertNotEqual(new["draft_hash"], old["draft_hash"])
        self.assertTrue(reply.startswith(f"The site changed since {old['code']}; please approve {new['code']}."))
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual((self.drafts()[1]["state"], self.commits()), ("applied", 1))


class DurabilityTests(ConversationTestCase):
    def test_result_is_stored_before_reply_and_sent_once(self):
        draft, _r = self.propose("hours")
        self.out.fail_sends = 1
        self.assertEqual(self.say("yes"), "approved")
        with self.assertRaises(ConnectionError):
            self.conv.flush(self.out)
        self.assertEqual((self.drafts()[0]["state"], len(self.conv.outbox.unsent()), self.commits()), ("applied", 1, 1))
        self.conv = self.open()
        self.assertEqual(self.replies(), [f"Applied {draft['code']}: {draft['summary']}"])
        self.assertEqual((self.replies(), self.commits(), self.editor.applies), ([], 1, 1))

    def test_recover_fails_interrupted_approval_without_reapplying(self):
        self.propose("hours")
        self.editor.crash = True
        with self.assertRaises(RuntimeError):
            self.say("yes")
        self.assertEqual(self.drafts()[0]["state"], "approved")
        fresh = CountingEditor(self.repo.state)
        self.conv = self.open(fresh)
        row = self.drafts()[0]
        self.assertEqual((row["state"], row["reason"]), ("failed", conversation.INTERRUPTED))
        self.assertEqual((fresh.applies, self.commits()), (0, 0))
        self.assertEqual(self.replies(), [f"{row['code']} was interrupted and not saved. The website is as it was "
                                          "before; send the change again to make a new draft."])  # SHOP-4 wording

    def test_state_file_is_private(self):
        self.assertEqual((self.repo.state / "conversation.sqlite3").stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(self.repo.state / "conversation.sqlite3") as db:
            self.assertEqual({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")},
                             {"messages", "drafts", "approvals", "outbox"})


class ConfigAndCliTests(ConversationTestCase):
    def test_missing_or_invalid_settings_refuse_to_start(self):
        bad = [{k: v for k, v in SETTINGS.items() if k != key} for key in SETTINGS]
        bad += [{**SETTINGS, "ownerSenders": []}, {**SETTINGS, "ownerChat": ""}, {**SETTINGS, "approvalTtlSeconds": 59},
                {**SETTINGS, "approvalTtlSeconds": "600"}]
        for settings in bad:
            with self.subTest(settings=settings):
                self.set_settings(settings)
                with self.assertRaises(conversation.ConfigError):
                    self.open()

    def test_fixture_cli_prints_only_outbox_lines(self):
        mapping = self.repo.state.parent / "interpreter.json"
        mapping.write_text(json.dumps({"Change the Saturday hours": {"question": "Which hours should Saturday have?"}}))
        run = subprocess.run([sys.executable, str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state", str(self.repo.state),
                              "--fixture", str(FIXTURE), "--interpreter", str(mapping)],
                             capture_output=True, text=True, cwd=REPO_ROOT)
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        rows = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual([(r["chat"], r["attachments"]) for r in rows], [(CHAT, [])] * 4)
        self.assertEqual([r["text"] for r in rows], ["Which hours should Saturday have?", conversation.NOT_READ_REPLY,
                                                     conversation.NOTHING, "Sorry, I can't do that yet."])
        self.assertEqual(self.commits(), 0)


if __name__ == "__main__":
    unittest.main()
