"""RF0835-5 (H12 part 1) tests: an owner photo/file gets one "not supported yet" reply and changes nothing.

Synthetic BlueBubbles fixtures only (example.invalid); nothing is downloaded or sent.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import unittest
from unittest import mock

from hass import inbox as inbox_mod
from hass.bridge import Drop, EnvelopeError, normalize, seal, unseal
from hass.conversation import ATTACHMENT_REPLY, Inbound
from hass.tests.test_bridge import KEY, NONCE, NOW, OWNER_CHAT, event
from hass.tests.test_conversation import SETTINGS, STRANGER, T0, ConversationTestCase

PHOTO = {"guid": "FAKE-ATTACHMENT-0001", "mimeType": "image/jpeg", "transferName": "fixture.jpg"}


def photo_event(pid="photo-1", text="", n=1, **data):
    ev = event("attachment")
    ev["data"].update(guid=pid, text=text, attachments=[dict(PHOTO) for _ in range(n)])
    ev["data"].update(data)
    return ev


class NormalizeAttachmentTests(unittest.TestCase):
    def test_count_text_and_object_replacement(self):
        msg = normalize(photo_event())
        self.assertEqual((msg.attachments, msg.text, msg.sender, msg.kind), (1, "", "owner@example.invalid", "new"))
        self.assertEqual(normalize(photo_event(text="\ufffc")).text, "")
        self.assertEqual(normalize(photo_event(text="\ufffcadd this mug")).text, "add this mug")
        self.assertEqual(normalize(photo_event(text=None)).text, "")
        self.assertEqual(normalize(photo_event(n=3)).attachments, 3)
        text_only = normalize(event("new-message"))
        self.assertEqual((text_only.attachments, text_only.text), (0, "desc"))

    def test_group_and_malformed_events_are_still_dropped(self):
        group = event("group-chat")
        group["data"]["attachments"] = [dict(PHOTO)]
        cases = {"group chat": (group, "group-or-unknown-chat"),
                 "attachments not a list": (photo_event(attachments="fixture.jpg"), "malformed"),
                 "missing handle": (photo_event(handle=None), "malformed"),
                 "lone surrogate caption": (photo_event(text=json.loads('"mug\\ud800"')), "malformed")}
        for name, (ev, reason) in cases.items():
            with self.subTest(name):
                self.assertEqual(normalize(ev), Drop(reason))
        no_text = event("new-message")
        no_text["data"]["text"] = None
        self.assertEqual(normalize(no_text), Drop("malformed"))  # without attachments null text stays malformed

    def test_envelope_round_trips_the_count_and_refuses_bad_shapes(self):
        msg = normalize(photo_event(n=2))
        env = seal(msg, KEY, nonce=NONCE, now=NOW)
        self.assertEqual(unseal(json.loads(json.dumps(env)), KEY, now=NOW, seen=set()), msg)
        missing = {**env, "body": {k: v for k, v in env["body"].items() if k != "attachments"}}
        bad = [missing] + [{**env, "body": {**env["body"], "attachments": v}} for v in (True, -1, "1", 1.0)]
        for envelope in bad:
            with self.subTest(body=envelope["body"].get("attachments", "missing")):
                seen = set()
                with self.assertRaises(EnvelopeError) as ctx:
                    unseal(envelope, KEY, now=NOW, seen=seen)
                self.assertEqual((ctx.exception.code, seen), ("shape", set()))


class AttachmentReplyTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "ownerChat": OWNER_CHAT})
        self.conv.db.close()
        self.conv = self.open()
        self.interpret = self.enterContext(mock.patch.object(self.interp, "interpret", wraps=self.interp.interpret))
        self.prepare = self.enterContext(mock.patch.object(self.editor, "prepare", wraps=self.editor.prepare))

    def say(self, text, pid=None, chat=OWNER_CHAT, **kwargs):
        return super().say(text, pid, chat, **kwargs)

    def send_photo(self, **kwargs):
        return self.conv.handle(normalize(photo_event(**kwargs)))

    def disposition(self, pid):
        return self.conv.db.execute("SELECT disposition FROM messages WHERE provider_id = ?", (pid,)).fetchone()[0]

    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def test_photo_without_caption_gets_one_reply_and_nothing_else(self):
        self.assertEqual(self.send_photo(), "attachment-unsupported")
        self.assertEqual(self.replies(), [ATTACHMENT_REPLY])
        self.assertEqual(self.disposition("photo-1"), "attachment-unsupported")
        self.assertEqual((self.interpret.call_count, self.prepare.call_count, self.editor.applies), (0, 0, 0))
        self.assertEqual((self.drafts(), self.commits(), self.approvals()), ([], 0, 0))
        self.assertEqual(self.send_photo(pid="photo-3", n=3), "attachment-unsupported")
        self.assertEqual(self.replies(), [ATTACHMENT_REPLY])

    def test_caption_is_never_interpreted_or_approved(self):
        draft, _reply = self.propose("hours")
        calls, before = self.interpret.call_count, self.drafts()
        for i, caption in enumerate(["add this mug", f"yes {draft['code']}", "yes", "no", "hours", "pause changes",
                                     "remember mugs are blue"]):
            with self.subTest(caption):
                self.assertEqual(self.send_photo(pid=f"cap-{i}", text=caption), "attachment-unsupported")
                self.assertEqual(self.replies(), [ATTACHMENT_REPLY])
        self.assertEqual((self.drafts(), self.drafts()[0]["state"]), (before, "proposed"))
        self.assertEqual((self.interpret.call_count, self.editor.applies, self.approvals(), self.commits()),
                         (calls, 0, 0, 0))
        self.assertEqual(self.say("yes"), "approved")  # the draft is still approvable by a text reply

    def test_duplicates_direct_and_through_the_inbox_reply_once(self):
        box = inbox_mod.Inbox(str(self.repo.state), T0.isoformat(), clock=lambda: self.now)
        self.addCleanup(box.close)
        msg = normalize(photo_event())
        self.assertEqual([self.conv.handle(msg), self.conv.handle(msg)], ["attachment-unsupported", "duplicate"])
        self.assertEqual([box.enqueue(msg), box.enqueue(msg)], ["queued", "duplicate"])
        self.assertEqual(box.drain(self.conv), [("photo-1", "duplicate")])
        self.assertEqual(box.enqueue(normalize(photo_event(pid="photo-2"))), "queued")
        self.assertEqual(box.drain(self.conv), [("photo-2", "attachment-unsupported")])  # the count survives the queue
        self.assertEqual(self.replies(), [ATTACHMENT_REPLY, ATTACHMENT_REPLY])

    def test_old_inbox_payload_without_attachments_is_handled_as_text(self):
        box = inbox_mod.Inbox(str(self.repo.state), T0.isoformat(), clock=lambda: self.now)
        self.addCleanup(box.close)
        self.assertEqual(box.enqueue(normalize(event("new-message"))), "queued")
        payload = json.loads(box.db.execute("SELECT payload FROM inbound").fetchone()[0])
        del payload["attachments"]  # stored before this field existed
        box.db.execute("UPDATE inbound SET payload = ?", (json.dumps(payload, sort_keys=True),))
        self.assertEqual(Inbound(**payload).attachments, 0)
        self.assertEqual(box.drain(self.conv), [("FAKE-0000-0000-0000-000000000001", "proposed")])
        self.assertEqual(self.interpret.call_count, 1)

    def test_strangers_echoes_and_edits_behave_as_before(self):
        cases = [("ignored", dict(pid="s1", handle={"address": STRANGER})), ("echo", dict(pid="e1", isFromMe=True)),
                 ("edited-ignored", dict(pid="u1"))]
        for disposition, kwargs in cases:
            with self.subTest(disposition):
                ev = photo_event(**kwargs)
                if disposition == "edited-ignored": ev["type"] = "updated-message"
                self.assertEqual(self.conv.handle(normalize(ev)), disposition)
                self.assertEqual(self.replies(), [])
        self.assertEqual(self.interpret.call_count, 0)

    def test_paused_photo_still_gets_the_reply(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.assertEqual(self.send_photo(), "attachment-unsupported")
        self.assertEqual(self.replies(), [ATTACHMENT_REPLY])
        self.assertEqual((self.drafts(), self.commits()), ([], 0))
