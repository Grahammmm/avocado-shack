"""AV2152-01 (H05/H17): `yes a1b3` / `no a1b3` for a code that matches no draft says `No draft a1b3.` and lists the
proposals actually waiting with their `reply yes <code>`. Nothing is approved, cancelled, replaced or applied.
A code that exists in any state keeps its own state reply. Fixtures only (temp Git repo, injected clock).
Run: python3 -B -m unittest hass.tests.test_unknown_approval_code -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import CHAT, GROUP, OWNER, SETTINGS, STRANGER, T0, ConversationTestCase
from hass.tests.test_editor import HOURS, _req

MISSING = "a1b3"
NO_DRAFT = f"No draft {MISSING}."


class CountingInterpreter(conversation.FixtureInterpreter):
    def __init__(self, mapping):
        super().__init__(mapping)
        self.calls = 0

    def interpret(self, text, pending):
        self.calls += 1
        return super().interpret(text, pending)


class UnknownCodeTestCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping["half"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}
        self.interp = self.conv.interpreter = CountingInterpreter(self.interp.mapping)

    def waiting(self, *drafts):
        return ["Waiting drafts:"] + [f"{d['code']}: {d['summary']}; reply yes {d['code']}." for d in drafts]

    def unknown(self, text=f"yes {MISSING}", **kwargs):
        self.assertEqual(self.say(text, **kwargs), "no-target")
        return self.replies()

    def assert_untouched(self, before, calls=0, applies=0):
        approvals = self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        self.assertEqual((self.drafts(), approvals, self.commits(), self.editor.applies, self.interp.calls),
                         (before, 0, 0, applies, calls))

    def test_unknown_yes_and_no_name_missing_code(self):
        for text in (f"yes {MISSING}", f"no {MISSING}"):
            with self.subTest(text=text):
                self.assertEqual(self.unknown(text), [NO_DRAFT])
        self.assert_untouched([])
        rows = [r[0] for r in self.conv.db.execute("SELECT disposition FROM messages ORDER BY rowid")]
        self.assertEqual(rows, ["no-target", "no-target"])

    def test_unknown_code_lists_every_waiting_proposal(self):
        one, _r = self.propose("hours")
        self.assertNotEqual(one["code"], MISSING)
        self.assertEqual(self.unknown(), ["\n".join([NO_DRAFT] + self.waiting(one))])
        two, _r = self.propose("desc")
        self.assertNotEqual(two["code"], MISSING)
        expected = "\n".join([NO_DRAFT] + self.waiting(one, two))
        self.assertEqual(self.unknown(f"no {MISSING}"), [expected])
        self.assertEqual(expected.splitlines()[2:], [f"{one['code']}: {one['summary']}; reply yes {one['code']}.",
                                                    f"{two['code']}: {two['summary']}; reply yes {two['code']}."])
        self.assert_untouched(self.drafts(), calls=2)

    def test_unknown_code_never_approves_or_cancels(self):
        one, _r = self.propose("hours")
        before, calls = self.drafts(), self.interp.calls
        for text in ("yes", "Yes", "approve", "approved", "no", "cancel", "reject"):
            for variant in (f"{text} {MISSING}", f"{text.upper()} {MISSING.upper()}!", f"{text} {MISSING}."):
                if text in ("yes", "no") and variant == text: continue
                with self.subTest(text=variant):
                    self.assertEqual(self.unknown(variant), ["\n".join([NO_DRAFT] + self.waiting(one))])
        self.assert_untouched(before, calls=calls)

    def test_questions_are_not_yes_alternatives(self):
        self.assertEqual(self.say("half"), "needs-details")
        self.replies()
        q = self.drafts()[-1]
        self.assertEqual(self.unknown(), [NO_DRAFT])
        self.assertEqual(self.unknown(f"no {MISSING}"), [NO_DRAFT])
        draft, _r = self.propose("hours")
        reply = self.unknown()[0]
        self.assertEqual(reply, "\n".join([NO_DRAFT] + self.waiting(draft)))
        self.assertNotIn(q["code"], reply)
        self.assertEqual([d["state"] for d in self.drafts()], ["needs-details", "proposed"])
        self.assertEqual(self.commits(), 0)

    def test_known_closed_code_keeps_its_reply(self):
        expired, _r = self.propose("hours")
        self.now = T0 + timedelta(seconds=600)  # exactly at expires_at: expired
        waiting, _r = self.propose("desc")
        self.assertEqual(self.unknown(f"yes {expired['code']}"), [f"{expired['code']} expired at 2026-11-02 09:10 PST; nothing changed."])
        self.assertEqual(self.say("no"), "rejected")  # cancels the only waiting proposal
        self.replies()
        self.assertEqual(self.unknown(f"yes {waiting['code']}"), [f"{waiting['code']} was cancelled (owner); nothing changed."])
        applied, _r = self.propose("hours")
        self.assertEqual(self.say(f"yes {applied['code']}"), "approved")
        self.replies()
        other, _r = self.propose("desc")
        self.assertEqual(self.unknown(f"yes {applied['code']}"), [f"{applied['code']} is applied."])
        self.assertEqual(self.unknown(f"no {applied['code']}"), [f"{applied['code']} is applied."])
        self.assertEqual((self.commits(), self.editor.applies, self.drafts()[-1]["state"], other["code"] != applied["code"]),
                         (1, 1, "proposed", True))

    def test_replaced_code_keeps_its_reply(self):
        old, _r = self.propose("hours")
        self.interp.mapping["fix"] = {"ops": _req((HOURS, {"hours": ["Daily 8am–7pm"]}))["ops"], "revises": old["code"]}
        new, _r = self.propose("fix")
        other, _r = self.propose("desc")
        self.assertEqual(self.unknown(f"yes {old['code']}"), [f"{old['code']} was replaced by {new['code']}."])
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.drafts()[-1]["state"], "proposed")
        self.assertNotEqual(other["code"], new["code"])

    def test_bare_and_real_code_flows_unchanged(self):
        self.assertEqual(self.unknown("yes"), [conversation.NOTHING])
        self.assertEqual(self.unknown("no"), [conversation.NOTHING])
        one, _r = self.propose("hours")
        two, _r = self.propose("desc")
        [reply] = self.unknown("yes")
        self.assertTrue(reply.startswith("Which draft do you mean?"), reply)
        self.assertEqual(self.say(f"no {one['code']}"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {one['code']}; nothing changed."])
        self.assertEqual(self.say(f"yes {two['code']}"), "approved")
        self.assertTrue(self.replies()[0].startswith(f"Applied {two['code']}"))
        self.assertEqual((self.commits(), self.editor.applies), (1, 1))
        self.assertEqual(self.say("half"), "needs-details")
        self.replies()
        q = self.drafts()[-1]
        self.assertEqual(self.unknown("yes"), [f"{q['code']} still needs details: {q['summary']}"])

    def test_cutoff_pause_and_daily_cap(self):
        old, _r = self.propose("hours")
        self.now = T0 + timedelta(seconds=300)
        young, _r = self.propose("desc")
        self.now = T0 + timedelta(seconds=601)  # `old` has lapsed, `young` has not
        self.assertEqual(self.unknown(), ["\n".join([NO_DRAFT] + self.waiting(young))])
        self.assertEqual(self.drafts()[0]["state"], "expired")
        self.now = T0 + timedelta(seconds=901)  # everything lapsed: no surviving proposal, never NOTHING
        self.assertEqual(self.unknown(), [NO_DRAFT])
        self.assertEqual((self.commits(), self.editor.applies), (0, 0))

    def test_delayed_message_is_judged_at_its_sent_time(self):
        draft, _r = self.propose("hours")
        later = T0 + timedelta(seconds=700)
        self.now, self.n = later, self.n + 1
        msg = conversation.Inbound(f"m{self.n}", CHAT, OWNER, f"yes {MISSING}", False, "new",
                                   (T0 + timedelta(seconds=599)).isoformat())
        self.assertEqual(self.conv.handle(msg), "no-target")
        # judged at its sent time the draft still waits, so it is listed (the sweep uses that cutoff, not the handling clock)
        self.assertTrue(self.replies()[0].endswith("\n".join([NO_DRAFT] + self.waiting(draft))))
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.assertEqual((self.commits(), self.editor.applies), (0, 0))

    def test_paused_and_exhausted_cap_still_answer(self):
        self.set_settings({**SETTINGS, "interpreterDailyCap": 1})
        self.conv = self.open()
        self.conv.interpreter = self.interp
        draft, _r = self.propose("hours")  # uses the one daily call
        calls = self.interp.calls
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.assertEqual(self.unknown(), ["\n".join([NO_DRAFT] + self.waiting(draft))])
        self.assertEqual(self.say("resume changes"), "resume")
        self.replies()
        self.assertEqual(self.unknown(f"no {MISSING}"), ["\n".join([NO_DRAFT] + self.waiting(draft))])
        self.assertEqual(self.say("desc"), "daily-limit")  # the cap really is exhausted
        self.replies()
        self.assertEqual((self.interp.calls, self.commits(), self.drafts()[0]["state"]), (calls, 0, "proposed"))

    def test_duplicate_echo_stranger_group_and_attachment(self):
        self.propose("hours")
        self.assertEqual(self.say(f"yes {MISSING}", pid="dup-1"), "no-target")
        self.assertEqual(len(self.replies()), 1)
        before = self.drafts()
        cases = [("duplicate", dict(pid="dup-1")), ("echo", dict(from_me=True)),
                 ("ignored", dict(sender=STRANGER)), ("ignored", dict(chat=GROUP))]
        for disposition, kwargs in cases:
            with self.subTest(case=kwargs):
                self.assertEqual(self.say(f"yes {MISSING}", **kwargs), disposition)
                self.assertEqual((self.replies(), self.drafts(), self.commits()), ([], before, 0))
        self.n += 1  # a photo caption is never an approval and never gets the draft list
        photo = conversation.Inbound(f"m{self.n}", CHAT, OWNER, f"yes {MISSING}", False, "new", self.now.isoformat(), 1)
        self.assertNotEqual(self.conv.handle(photo), "no-target")
        for reply in self.replies():
            self.assertNotIn(NO_DRAFT, reply)
        self.assertEqual((self.drafts(), self.commits()), (before, 0))


if __name__ == "__main__":
    unittest.main()
