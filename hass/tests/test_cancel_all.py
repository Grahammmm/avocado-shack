"""AV1052-08 (H05/H17): `no all`, `cancel all` and `cancel everything` cancel every waiting draft and question at once;
`yes all` and `approve all` approve nothing. Neither reaches the interpreter, the daily count or the editor.

Same temp-repo setup as the other conversation tests (injected clock, fixture interpreter, PhotoRepo for the photo case); nothing is
downloaded or sent. Run: python3 -B -m unittest hass.tests.test_cancel_all -v
"""

import os
import stat
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation
from hass.conversation import NOTHING, Inbound, TransitionError
from hass.tests import test_photo_draft as photo
from hass.tests.test_conversation import CHAT, GROUP, OWNER, SETTINGS, STRANGER, T0, ConversationTestCase
from hass.tests.test_editor import HOURS, _req
from hass.tests.test_interpreter_cap import CountingInterpreter

TTL = timedelta(seconds=600)  # SETTINGS approvalTtlSeconds
EMPTY = "Nothing is waiting."


class CancelAllTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping["half"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}  # a question: details missing
        self.interp = CountingInterpreter(self.interp.mapping)
        self.conv = self.open()

    def ask(self):
        self.assertEqual(self.say("half"), "needs-details")
        self.replies()
        return self.drafts()[-1]

    def states(self):
        return [(d["code"], d["state"], d["reason"]) for d in self.drafts()]

    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def assert_nothing_applied(self, calls=None):
        self.assertEqual((self.approvals(), self.commits(), self.editor.applies), (0, 0, 0))
        if calls is not None: self.assertEqual(self.interp.calls, calls)

    def test_keywords_are_exact_whole_messages(self):
        # Contract: only the five documented phrases are bulk (case, outer space and a final . or ! ignored). Bug caught: an
        # accidental `approved all` / `no everything` / sentence reading as a bulk action, or `no`/`no <code>` changing meaning.
        for text, want in (("no all", "reject"), ("Cancel ALL!", "reject"), ("  cancel everything. ", "reject"),
                           ("yes all", "approve"), ("Approve all.", "approve")):
            self.assertEqual(conversation.parse_keyword(text), (want, "all"), text)
        for text in ("approved all", "reject all", "no everything", "yes everything", "no all please", "cancel all drafts",
                     "no all?", "cancel every one", "all"):
            self.assertIsNone(conversation.parse_keyword(text), text)
        self.assertEqual((conversation.parse_keyword("no"), conversation.parse_keyword("YES A1B2")), (("reject", None), ("approve", "a1b2")))

    def test_cancel_all_closes_every_waiting_proposal_and_question_in_order(self):
        # Contract: every unexpired waiting row of the owner is rejected (reason owner) and named in row order, an applied
        # change is untouched, and no interpreter call, approval or commit happens. Bug caught: only one row closed, an
        # old applied row rejected, or the text sent on to the interpreter.
        self.propose("hours")
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        base_commits, calls = self.commits(), self.interp.calls
        applied = self.states()
        first, _ = self.propose("desc")
        question = self.ask()
        self.assertEqual(self.say("Cancel ALL!"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {first['code']}, {question['code']}; nothing changed."])
        self.assertEqual(self.states()[:1], applied)
        self.assertEqual([s[1:] for s in self.states()[1:]], [("rejected", "owner")] * 2)
        self.assertEqual((self.commits(), self.editor.applies, self.interp.calls), (base_commits, 1, calls + 2))  # only the two requests above
        self.assertEqual(self.say("no all"), "no-target")  # duplicate cancel: nothing is waiting any more
        self.assertEqual(self.replies(), [EMPTY])
        self.assertEqual(self.say(f"yes {first['code']}"), "no-target")  # a late yes stays cancelled
        self.assertEqual(self.replies(), ["That one was cancelled, so nothing changed."])
        for phrase in ("no all", "cancel everything"):
            with self.subTest(phrase):
                again, _ = self.propose("desc")
                self.assertEqual(self.say(phrase), "rejected")
                self.assertEqual(self.replies(), [f"Cancelled {again['code']}; nothing changed."])

    def test_cancel_all_with_nothing_waiting_or_only_lapsed_rows(self):
        # Contract: an empty store or only expired rows replies "Nothing is waiting." and an expired row is expired, not
        # reported cancelled; the exact expiry boundary counts as expired. Bug caught: a lapsed row listed as cancelled.
        self.assertEqual(self.say("cancel all"), "no-target")
        self.assertEqual(self.replies(), [EMPTY])
        self.propose("hours")
        self.now = T0 + TTL  # exactly at expires_at
        self.assertEqual(self.say("no all"), "no-target")
        self.assertEqual(self.replies(), [EMPTY])
        self.assertEqual([s[1] for s in self.states()], ["expired"])

    def test_delayed_cancel_all_is_judged_now_but_a_delayed_single_yes_keeps_its_send_time(self):
        # Contract: bulk cancel describes what waits when it is handled; an individual yes keeps its original cutoff.
        # Bug caught: a delayed `no all` using the message's old send time and reporting an expired draft as cancelled.
        draft, _ = self.propose("hours")
        self.now = T0 + TTL + timedelta(seconds=1)
        sent = (T0 + timedelta(seconds=30)).isoformat()
        self.assertEqual(self.conv.handle(Inbound("late-no-all", CHAT, OWNER, "no all", False, "new", sent)), "no-target")
        self.assertEqual(self.replies(), [EMPTY])
        self.assertEqual(self.states(), [(draft["code"], "expired", None)])

    def test_yes_all_approves_nothing_and_names_the_waiting_codes(self):
        # Contract: yes all / approve all approve nothing (not even a single waiting proposal), name every waiting code and
        # qualify questions, call no interpreter and expire nothing. Bug caught: mapped to a bare yes, or sent to the interpreter.
        self.assertEqual(self.say("yes all"), "no-target")
        self.assertEqual(self.replies(), [EMPTY])
        one, _ = self.propose("hours")
        calls, before = self.interp.calls, self.states()
        self.assertEqual(self.say("Approve ALL."), "no-target")
        self.assertEqual(self.replies(), [f"Nothing was changed. Each draft needs its own yes <code>. Waiting codes: {one['code']}."])
        question = self.ask()
        calls += 1
        self.assertEqual(self.say("yes all"), "no-target")
        self.assertEqual(self.replies(), [f"Nothing was changed. Each draft needs its own yes <code>. Waiting codes: {one['code']}, {question['code']}. "
                                          "Questions still need details before approval."])
        self.assertEqual((self.states()[0], self.interp.calls), (before[0], calls))
        self.assert_nothing_applied()
        self.now = T0 + TTL  # both lapsed: not listed, and a yes-all sweep never marks them expired
        self.assertEqual(self.say("yes all"), "no-target")
        self.assertEqual(self.replies(), [EMPTY])
        self.assertEqual([s[1] for s in self.states()], ["proposed", "needs-details"])
        self.assert_nothing_applied()

    def test_works_paused_and_at_the_daily_cap_and_counts_nothing(self):
        # Contract: both phrases work when changes are paused and the daily cap is used up, leaving pause and usage as they
        # were. Bug caught: the cap's DAILY_LIMIT reply or the paused refusal replacing the answer, or a counted call.
        self.set_settings({**SETTINGS, "interpreterDailyCap": 1})
        self.conv = self.open()
        draft, _ = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        paused, usage, calls = self.conv._paused(), self.conv._calls(self.now), self.interp.calls
        self.assertEqual(self.say("yes all"), "no-target")
        self.assertEqual(self.replies(), [f"Nothing was changed. Each draft needs its own yes <code>. Waiting codes: {draft['code']}."])
        self.assertEqual(self.say("no all"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {draft['code']}; nothing changed."])
        self.assertEqual((self.conv._paused(), self.conv._calls(self.now), self.interp.calls), (paused, usage, calls))
        self.assert_nothing_applied()

    def test_strangers_echoes_edits_attachments_and_duplicates_cannot_bulk_act(self):
        # Contract: the existing owner/echo/edit/duplicate guards come first. Bug caught: a stranger, a group chat or a replayed
        # provider id cancelling the owner's drafts or answering twice.
        draft, _ = self.propose("hours")
        before = self.states()
        for disposition, kwargs in (("ignored", dict(sender=STRANGER)), ("ignored", dict(chat=GROUP)), ("echo", dict(from_me=True)),
                                    ("not-read", dict(kind="edited"))):
            with self.subTest(kwargs):
                self.assertEqual(self.say("no all", **kwargs), disposition)
                self.replies()
                self.assertEqual(self.states(), before)
        self.assertEqual(self.say("no all", pid="same"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {draft['code']}; nothing changed."])
        self.assertEqual(self.say("no all", pid="same"), "duplicate")
        self.assertEqual(self.replies(), [])

    def test_cancel_all_is_atomic(self):
        # Contract: all targets are cancelled in the one message transaction. Bug caught: a failure on the second move leaving
        # the first cancelled, or a reply and message record without the whole cancel.
        first, _ = self.propose("hours")
        second, _ = self.propose("desc")
        real, seen = self.conv._move, []

        def flaky(row, state, **fields):
            seen.append(row["code"])
            if len(seen) == 2: raise TransitionError("injected")
            return real(row, state, **fields)

        with mock.patch.object(self.conv, "_move", flaky), self.assertRaises(TransitionError):
            self.say("no all", pid="atomic")
        self.assertEqual([s[1] for s in self.states()], ["proposed", "proposed"])
        self.assertEqual(self.replies(), [])
        self.assertIsNone(self.conv.db.execute("SELECT 1 FROM messages WHERE provider_id = 'atomic'").fetchone())
        self.assertEqual(self.say("no all", pid="atomic"), "rejected")  # the retry succeeds once
        self.assertEqual(self.replies(), [f"Cancelled {first['code']}, {second['code']}; nothing changed."])


class CancelAllPhotoTests(photo.PhotoDraftTests):
    """Reuses the photo harness (PhotoRepo, fake photo source) without re-running its own tests."""

    def snapshot(self):
        root = self.repo.media
        return {str(p.relative_to(root)): (p.read_bytes(), stat.S_IMODE(os.stat(p).st_mode)) for p in sorted(root.rglob("*")) if p.is_file()}

    def test_photo_drafts_are_cancelled_but_every_stored_byte_stays(self):
        # Contract: `no all` closes a photo proposal and a needs-details photo draft like `no <code>` does and the private
        # originals (bytes and mode) stay; a photo caption is never a bulk cancel. Bug caught: media removed on cancel, a
        # photo draft skipped, or a caption "no all" cancelling drafts.
        self.assertEqual(self.say(photo.ANSWER, attachments=1), "proposed")
        self.photos.data = photo.PNG
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        before, product = self.snapshot(), self.repo.product(photo.PID)["image"]
        self.assertEqual(self.say("no all", attachments=1), "photo-duplicate")  # a caption is only a caption: the same photo again
        self.replies()
        self.assertEqual([d["state"] for d in self.drafts()], ["proposed", "needs-details"])
        codes = [d["code"] for d in self.drafts()]
        texts = list(self.interp.texts)
        self.assertEqual(self.say("cancel everything"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {codes[0]}, {codes[1]}; nothing changed."])
        self.assertEqual([(d["state"], d["reason"]) for d in self.drafts()], [("rejected", "owner")] * 2)
        self.assertEqual((self.snapshot() == before, self.repo.product(photo.PID)["image"], self.interp.texts), (True, product, texts))
        self.assertEqual(self.say(f"yes {codes[0]}"), "no-target")  # a late yes stays cancelled
        self.assertEqual(self.replies(), ["That one was cancelled, so nothing changed."])
        self.assertEqual(self.repo.product(photo.PID)["image"], product)


for _name in [n for n in dir(photo.PhotoDraftTests) if n.startswith("test_")]:
    setattr(CancelAllPhotoTests, _name, None)  # inherited tests belong to their own module


if __name__ == "__main__":
    unittest.main()
