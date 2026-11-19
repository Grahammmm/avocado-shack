"""AV1052-09 (H17): a whole one-word message one letter off a command word gets `Did you mean status? Send status.`

A guess only: the command is never run, and there is no interpreter call, daily count, draft, approval or commit. Same
H06 setup as test_near_approval (temp Git repo, private state dir, injected clock, fixture interpreter); nothing is sent.
Run: python3 -B -m unittest hass.tests.test_command_typo -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import GROUP, SETTINGS, STRANGER
from hass.tests.test_near_approval import TextInterpreter
from hass.tests.test_undo import H06TestCase

CODE = "a1b2"


def guess(*names):
    joined = " or ".join(names)
    return f"Did you mean {joined}? Send {joined}."


class CommandTypoTests(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp = TextInterpreter(self.interp.mapping)
        self.conv = self.open()

    def usage(self):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'usage'").fetchone(): return []
        return [tuple(r) for r in self.conv.db.execute("SELECT day, calls FROM usage ORDER BY day")]

    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def last(self):
        return self.conv.db.execute("SELECT disposition FROM messages ORDER BY rowid DESC LIMIT 1").fetchone()[0]

    def typo(self, text, *names, **kw):
        """The one reply is the guess; nothing ran, nothing was counted or changed."""
        before = (self.drafts(), self.usage(), self.commits(), self.sent_count())
        self.assertEqual(self.say(text, **kw), "command-typo", text)
        self.assertEqual(self.replies(), [guess(*names)], text)
        self.assertEqual(self.last(), "command-typo")
        self.assertEqual((self.drafts(), self.usage(), self.commits(), self.interp.texts, self.approvals()),
                         (before[0], before[1], before[2], [], 0), text)

    def sent_count(self):
        return len(self.out.sent)

    def ordinary(self, text):
        """Today's handling: not a guess, and the reader is asked once."""
        self.interp.texts.clear()
        self.assertNotEqual(self.say(text), "command-typo", text)
        self.replies()
        self.assertEqual(self.interp.texts, [text], text)

    # Contract: one inserted, dropped or changed letter, or one swap, of a command word names that word. Bug caught: a typo
    # that is not understood (today's "Sorry, I can't do that yet."), a swap read as two edits, or a case/space/dot mismatch.
    def test_one_edit_and_adjacent_swap_examples(self):
        for text, name in (("histroy", "history"), ("staus", "status"), ("reprot", "report"), ("memroy", "memory"), ("undp", "undo"),
                           ("statuss", "status"), ("hlep", "help"), ("rejec", "reject"), ("cancle", "cancel"), ("shelv", "shelf"),
                           ("  Staus! ", "status"), ("REPROT.", "report")):
            with self.subTest(text=text): self.typo(text, name)
        self.assertEqual(self.say("status"), "status")  # the real word still runs
        self.assertEqual(self.say("stauts"), "command-typo")  # ... and a typo ran nothing before it

    # Contract: when two command words fit, both are named in sorted order and neither is run. Bug caught: an arbitrary winner.
    def test_multiple_candidates_sorted_and_not_executed(self):
        self.typo("stow", "show", "stop")
        self.typo("approv", "approve")  # approved is two edits away
        self.assertEqual(conversation.command_typo("abcd", ("abce", "abcf", "abcd")), [])  # an exact word is never guessed
        self.assertEqual(conversation.command_typo("abcd", ("zbcd", "abce", "abcz", "abcdx")), ["abce", "abcdx", "abcz", "zbcd"])

    # Contract: exact commands and approval words keep their own handling and a typo of one never approves. Bug caught: the
    # guess placed ahead of an exact parser, or a typo of `approve` acting on the waiting proposal.
    def test_exact_commands_and_approval_words_win(self):
        draft = self.propose("hours")[0]
        for text, want in (("status", "status"), ("help", "help"), ("memory", "memory-none"), ("undo", "no-target"),
                           (f"cancel {draft['code']}", "rejected")):
            with self.subTest(text=text): self.assertEqual(self.say(text), want); self.replies()
        draft = self.propose("hours")[0]
        self.typo("aprove", "approve")
        self.typo("rejct", "reject")
        self.assertEqual((self.drafts()[-1]["state"], self.approvals()), ("proposed", 0))
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")

    # Contract: real words, the near approvals and thanks keep today's handling, as do longer or odd messages. Bug caught: a
    # real word (shop, past) turned into a guess, a casual yes or thanks answered with a command, or a phrase mangled.
    def test_real_words_near_approvals_thanks_and_long_requests_unchanged(self):
        self.proposal = self.propose("hours")[0]
        for text in ("fine", "shop", "past", "most", "hold", "Shop!", "yes", "no", "yeh", "ok"):
            with self.subTest(text=text):
                self.assertNotEqual(self.say(text, pid=f"w-{text}"), "command-typo")
                self.replies()
        for text in ("okay", "yeah", "sure", "Yep", "ok " + self.proposal["code"]):
            with self.subTest(text=text): self.assertEqual(self.say(text), "near-approval"); self.replies()
        self.assertEqual(self.say("thanks"), "social")
        self.replies()
        for text in ("thankyou", "cheers", "thx", "what is staus", "staus please", "history staus", "photos to tak", "stat", "statu s",
                     "sta-tus", "sta tus", "staus2", "status1", "stuats?", "stauts now", "mömory", "memorry!!x",
                     "stuatss", "statuses", "xxxx", "cncl"):
            with self.subTest(text=text): self.ordinary(text)
        self.assertEqual(self.approvals(), 0)

    # Contract: a guess needs no interpreter budget, works while paused, is answered once per delivery and only for the owner's
    # plain new text. Bug caught: a guess counted against the cap, lost while paused, repeated for a redelivery, or sent to a
    # stranger, a group, an echo, an edit, a reaction or a photo caption.
    def test_paused_cap_duplicate_and_untrusted_gates(self):
        self.set_settings({**SETTINGS, "interpreterDailyCap": 1})
        self.conv = self.open()
        self.assertEqual(self.say("desc"), "proposed")  # uses the whole daily count
        self.replies()
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.typo("histroy", "history", pid="t1")
        self.assertEqual(self.say("histroy", pid="t1"), "duplicate")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.say("reprot"), "command-typo")
        self.replies()
        self.assertEqual(self.say("resume changes"), "resume")
        self.replies()
        self.assertEqual(self.say("hours"), "daily-limit")  # the cap still holds for real requests
        self.replies()
        self.assertEqual(self.usage()[0][1], 1)
        for label, kw, want in (("stranger", dict(sender=STRANGER), "ignored"), ("group", dict(chat=GROUP), "ignored"),
                                ("echo", dict(from_me=True), "echo"), ("edit", dict(kind="edited"), "not-read"),
                                ("reaction", dict(kind="reaction"), "not-read")):
            with self.subTest(label):
                self.assertEqual(self.say("staus", **kw), want)
                self.assertNotIn("Did you mean", " ".join(self.replies()))
        self.n += 1
        photo = conversation.Inbound(f"m{self.n}", self.conv.settings["ownerChat"], self.conv.settings["ownerSenders"][0], "staus",
                                     received_at=self.now.isoformat(), attachments=1)
        self.assertEqual(self.conv.handle(photo), "attachment-unsupported")
        self.assertEqual(self.replies(), [conversation.ATTACHMENT_REPLY])

    # Contract: a lapsed proposal still moves to expired as before (the guess is not a read-only command). Bug caught: the guess
    # silently keeping an expired draft waiting.
    def test_expiry_is_unchanged(self):
        self.propose("hours")
        self.now += timedelta(seconds=601)  # SETTINGS approvalTtlSeconds is 600
        self.typo("staus", "status")
        self.assertEqual(self.drafts()[-1]["state"], "expired")


if __name__ == "__main__":
    unittest.main()
