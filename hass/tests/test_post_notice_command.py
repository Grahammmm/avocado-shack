"""AV1104-07: `post notice` replies social_draft.build_notice's caption draft for the home notice the saved content shows today.
Read-only: nothing is posted, scheduled, stored or drafted; works while paused or out of interpreter calls. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_post_notice_command -v

Each test names the contract it protects and the believable bug that fails it.
"""
import json
import re
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, editor, social_draft
from hass.content_model import load_content
from hass.tests.test_commands_doc import DOC, rows, verb
from hass.tests.test_conversation import CHAT, GROUP, OWNER, SETTINGS, STRANGER, T0, ConversationTestCase
from hass.tests.test_editor import git
from hass.tests.test_status_pause import StoreMixin

PREFIX = "Draft post (not posted; copy it yourself):\n"
NONE = "There is no notice on the website to post."
UNAVAILABLE = "Catalog unavailable right now; nothing changed."
TEXT = "We are closed for Thanksgiving. Happy holidays!"
RANGE = {"text": TEXT, "from": "2026-11-02", "until": "2026-11-04"}  # T0 is Monday 2026-11-02, 09:00 Pacific


class PostNoticeTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.store = self.repo.wt / "hass" / "content" / "store.json"
        self.content = self.repo.wt / "hass" / "content"
        self.set_notice(RANGE)

    def set_notice(self, notice, **store):
        doc = json.loads(self.store.read_text("utf-8"))
        doc.pop("notice", None)
        if notice is not None: doc["notice"] = notice
        doc.update(store)
        self.store.write_text(json.dumps(doc), "utf-8")
        git(self.repo.wt, "commit", "-qam", "fixture notice")  # a clean worktree, so a waiting proposal can exist beside the posts
        self.base = self.count()

    def want(self):
        return social_draft.build_notice(load_content(self.content), self.now)

    def post(self, text, **kw):
        self.assertEqual(self.say(text, **kw), "post")
        [row] = self.conv.db.execute("SELECT text, attachments FROM outbox ORDER BY id DESC LIMIT 1").fetchall()
        self.assertEqual(len(self.replies()), 1)
        return row["text"], json.loads(row["attachments"] or "[]")

    def untouched(self):
        return (self.drafts(), self.tables(), self.commits(), self.approvals(), self.editor.applies, self.store.read_bytes())

    def test_post_notice_equals_builder_without_photo(self):
        """The reply is the builder's caption verbatim after the draft line, text only, and nothing is changed.
        Bug caught: a reworded or truncated caption, an attached photo, a draft or commit created by a read."""
        want = self.want()
        self.assertEqual(want["caption"].splitlines()[1], "from Monday, November 2 through Wednesday, November 4")
        before = self.untouched()
        with mock.patch("socket.socket", side_effect=AssertionError("network")), mock.patch("os.system", side_effect=AssertionError("shell")):
            self.assertEqual(self.post("post notice"), (PREFIX + want["caption"], []))
            for send in ("Post Notice", "POST NOTICE!", "  post notice. ", "post notice?"):
                with self.subTest(send=send):
                    self.assertEqual(self.post(send), (PREFIX + want["caption"], []))
        self.assertEqual(self.untouched(), before)
        self.set_notice({"text": TEXT, "until": "2026-11-04"})
        self.assertEqual(self.post("post notice")[0].splitlines()[2], "through Wednesday, November 4")

    def test_no_notice_not_yet_or_ended_and_other_reasons(self):
        """No notice, a notice before its first day or after its last gets the one plain line; a tagged notice is refused, never rewritten;
        an unreadable shape says nothing changed. Bug caught: an expired holiday notice offered for posting, '#' leaking into a caption."""
        for notice in (None, {**RANGE, "from": "2026-11-03"}, {"text": TEXT, "until": "2026-11-01"}):
            with self.subTest(notice=notice):
                self.set_notice(notice)
                self.assertEqual(self.post("post notice"), (NONE, []))
        self.set_notice({"text": "Closed #holiday", "until": "2026-11-04"})
        self.assertEqual(self.post("post notice"), ("Cannot draft a notice post: free text has a hashtag or account name.", []))
        self.set_notice({"text": TEXT, "until": "2026-11-04"}, streetAddress="")
        self.assertEqual(self.post("post notice"), ("Cannot draft a notice post: store record incomplete.", []))
        self.set_notice({"text": "x" * 2300, "until": "2026-11-04"}, streetAddress="2190 Main Street")
        self.assertEqual(self.post("post notice"), ("Cannot draft a notice post: caption too long.", []))
        self.set_notice({"text": TEXT, "until": "2026-13-45"})
        self.assertEqual(self.post("post notice"), (UNAVAILABLE, []))
        self.store.write_text("{not json", "utf-8")
        self.assertEqual(self.post("post notice"), (UNAVAILABLE, []))
        with mock.patch.object(editor, "_load", side_effect=editor.UnsafeState("/private/state/path")):
            self.assertEqual(self.post("post notice"), (UNAVAILABLE, []))
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_follows_the_clock_across_the_last_day(self):
        """The same content drafts on the last Pacific day and gets the no-notice line the next morning. Bug caught: a UTC date or a cached answer."""
        self.now = T0 + timedelta(days=2, hours=14)  # Wednesday 23:00 Pacific
        self.assertTrue(self.post("post notice")[0].startswith(PREFIX))
        self.now = T0 + timedelta(days=2, hours=16)  # Thursday 01:00 Pacific
        self.assertEqual(self.post("post notice"), (NONE, []))

    def test_lookalikes_and_other_post_modes_unchanged(self):
        """Only the whole argument `notice` is this command; other words keep their old meaning. Bug caught: `post notice extra` or `post notices` dispatching."""
        calls = []
        with mock.patch.object(self.interp, "interpret", side_effect=lambda *a, **k: calls.append(a)):
            self.assertEqual(self.post("post notices")[0], "I don't know a product called notices. Try find and a word from its name.")
            self.assertNotEqual(self.say("post notice for the holiday closing"), "post")
            self.assertFalse(any(PREFIX in r for r in self.replies()))
        self.assertEqual(self.post("post hike nope")[0], "I don't know a hike called nope. Try find and a word from its name.")
        self.assertEqual(self.post("post maker zz")[0], "No maker zz; send find <words> for keys.")

    def test_paused_lapsed_and_capped_read_only(self):
        """While paused, with a lapsed proposal waiting, or with the interpreter cap used up, the reply still comes and no row, usage count or
        expiry changes. Bug caught: a read-only post sweeping a waiting draft, spending a call, or being refused while paused."""
        want = PREFIX + self.want()["caption"]
        draft, _ = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(seconds=601)  # the proposal has lapsed but no other message has swept it
        before = self.untouched()
        with mock.patch.object(self.interp, "interpret", side_effect=AssertionError("interpreter")):
            self.assertEqual(self.post("post notice"), (want, []))
            self.set_notice(None)
            before = self.untouched()
            self.assertEqual(self.post("post notice"), (NONE, []))
        self.assertEqual(self.untouched(), before)
        self.assertEqual(self.drafts()[0]["state"], "proposed")  # not swept to expired
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_exhausted_cap_is_unchanged(self):
        self.set_settings({**SETTINGS, "interpreterDailyCap": 1})
        self.conv = self.open()
        self.assertEqual(self.say("when?"), "question")
        self.replies()
        self.assertEqual(self.say("hours"), "daily-limit")
        self.replies()
        usage = self.conv.db.execute("SELECT day, calls FROM usage").fetchall()
        self.assertEqual(self.post("post notice"), (PREFIX + self.want()["caption"], []))
        self.assertEqual(self.conv.db.execute("SELECT day, calls FROM usage").fetchall(), usage)

    def test_duplicate_echo_stranger_group_and_attachment(self):
        """Guards stay as for every command: a duplicate, a stranger, a group, an echo and a photo get no caption. Bug caught: a notice caption sent to the wrong person."""
        self.assertEqual(self.say("post notice", pid="m-dup"), "post")
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual((self.say("post notice", pid="m-dup"), self.replies()), ("duplicate", []))
        self.assertEqual(self.say("post notice", sender=STRANGER), "ignored")
        self.assertEqual(self.say("post notice", chat=GROUP), "ignored")
        self.assertEqual(self.say("post notice", from_me=True), "echo")
        self.assertEqual(self.replies(), [])
        for kind in ("edited", "reaction"):
            self.assertEqual(self.say("post notice", kind=kind), "not-read")
        self.assertEqual(self.replies(), [conversation.NOT_READ_REPLY] * 2)
        photo = conversation.Inbound("m-photo", CHAT, OWNER, "post notice", received_at=self.now.isoformat(), attachments=1)
        self.assertNotEqual(self.conv.handle(photo), "post")  # a photo's caption is never a command
        self.assertFalse(any(PREFIX in r for r in self.replies()))

    def test_help_and_commands_row(self):
        """Help and COMMANDS.md carry one parsable example. Bug caught: a command nobody can find, or an example that does not parse."""
        plain = conversation.help_detail("post")
        self.assertIn("post notice", plain)
        [(send, example, row)] = [r for r in rows(DOC.read_text("utf-8")) if r[0].startswith("`post notice")]
        self.assertEqual(verb(re.findall(r"`([^`]+)`", example)[0]), "post")
        self.assertEqual(conversation.parse_command("post notice"), ("post", "notice"))
        for phrase in ("Draft post (not posted; copy it yourself):", "Nothing is posted, scheduled or saved", "works while paused", "There is no notice on the website to post."):
            self.assertIn(phrase, " ".join(row.split()))


if __name__ == "__main__":
    unittest.main()
