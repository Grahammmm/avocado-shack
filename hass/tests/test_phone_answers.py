"""AV1352-04 (H05): a coded yes/no survives phone decoration; a ? is never an answer.

Run: python3 -m unittest hass.tests.test_phone_answers -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_editor import HOURS, _req
from hass.tests.test_near_approval import TextInterpreter
from hass.tests.test_undo import H06TestCase


class PhoneAnswerTests(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp = TextInterpreter({**self.interp.mapping, "half": {"ops": _req((HOURS, {}))["ops"], "revises": None}})
        self.conv = self.open()

    def proposal(self, text="hours"):
        draft, _reply = self.propose(text)
        self.interp.texts.clear()
        return draft

    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def hint(self, text, reply, drafts=None):
        drafts = drafts or self.drafts()
        self.assertEqual(self.say(text), "near-approval", text)
        self.assertEqual(self.replies(), [reply])
        self.assertEqual((self.drafts(), self.approvals(), self.commits(), self.interp.texts), (drafts, 0, 0, []))

    def one(self, code):
        return f"Nothing was changed. To apply {code}, reply yes {code}; to cancel it, no {code}."

    def test_decorated_yes_applies_exactly_the_named_draft(self):
        a, b = self.proposal("hours"), self.proposal("desc")
        self.assertEqual(self.say(f"{a['code'].upper()}, approve please 👍"), "approved")
        self.replies()
        states = {d["code"]: d["state"] for d in self.drafts()}
        self.assertNotEqual(states[a["code"]], "proposed")
        self.assertEqual((states[b["code"]], self.approvals(), self.interp.texts), ("proposed", 1, []))

    def test_each_decorated_yes_form_approves(self):
        for text, proposal in (("Yes, {}", "hours"), ("{} yes", "desc"), ("yes {} thanks 🙏", "desc2")):
            with self.subTest(text=text):
                code = self.proposal(proposal)["code"]
                self.assertEqual(self.say(text.format(code)), "approved")
                self.replies()
                self.assertEqual(self.interp.texts, [])

    def test_classifier_reads_only_whole_message_forms(self):
        for text, want in (("Yes, a1b2", ("approve", "a1b2", False)), ("yes a1b2 thanks", ("approve", "a1b2", False)),
                           ("A1B2 yes", ("approve", "a1b2", False)), ("no a1b2 please", ("reject", "a1b2", False)),
                           ("ok, approve a1b2 thank you!", ("approve", "a1b2", False)), ("cancel 👍 a1b2", ("reject", "a1b2", False)),
                           ("yes a1b2?", ("approve", "a1b2", True)), ("a1b2 yes?", ("approve", "a1b2", True)),
                           ("yes?", ("approve", None, True)), ("no?", ("reject", None, True)), ("a1b2", (None, "a1b2", False)),
                           ("a1b2?", (None, "a1b2", True)), ("yes please", None), ("yes", None), ("ok", None),
                           ("yes but a1b2", None), ("yes a1b2 a1b3", None), ("yes no a1b2", None), ("yes a1b", None),
                           ("yes a1b2c3d4e5f6a", None), ("yes a1b2 不要", None), ("不要 yes a1b2", None), ("no a1b2 谢谢", None), ("yes a1b2 não", None), ("yes a1b2é", None), ("yes a1b2 нет?", None), ("yes a1 b2", None), ("yes a1b2g", None), ("", None), ("👍", None)):
            with self.subTest(text=text):
                self.assertEqual(conversation.parse_phone(text), want)
        self.assertEqual(conversation.parse_phone("yes a1b2c3d4e5f6")[1], "a1b2c3d4e5f6")  # 12 characters

    def test_decorated_no_cancels_exactly_the_named_draft(self):
        a, b = self.proposal("hours"), self.proposal("desc")
        self.assertEqual(self.say(f"no {a['code']} please"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {a['code']}; nothing changed."])
        states = {d["code"]: d["state"] for d in self.drafts()}
        self.assertEqual((states[a["code"]], states[b["code"]], self.approvals(), self.interp.texts),
                         ("rejected", "proposed", 0, []))
        self.assertEqual(self.say(f"{b['code']}, cancel!"), "rejected")

    def test_question_forms_change_nothing(self):
        a, b = self.proposal("hours"), self.proposal("desc")
        a_hint = self.one(a["code"])
        for text in (f"yes {a['code']}?", f"no {a['code']}?", f"Yes, {a['code']}?", f"{a['code']} yes?", f"{a['code']}?",
                     f"{a['code']}", f"?yes {a['code']}", f"approve? {a['code']}", f"{a['code']} cancel thanks?"):
            with self.subTest(text=text):
                self.hint(text, a_hint)
        many = f"Nothing was changed. Reply yes <code> or no <code> with one of: {a['code']}, {b['code']}."
        for text in ("yes?", "no?", "approve?", "yes 0000?"):
            with self.subTest(text=text):
                self.hint(text, many)

    def test_single_waiting_draft_bare_question_names_it(self):
        a = self.proposal()
        self.hint("yes?", self.one(a["code"]))
        self.hint("no?", self.one(a["code"]))

    def test_nothing_waiting_gets_nothing(self):
        self.hint("yes?", conversation.NOTHING)
        self.hint("no?", conversation.NOTHING)

    def test_expired_or_closed_draft_is_not_offered_or_applied(self):
        a = self.proposal()
        self.now += timedelta(seconds=601)
        self.assertEqual(self.say(f"yes {a['code']}?"), "near-approval")  # housekeeping expires it; nothing else changes
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.assertEqual((self.drafts()[-1]["state"], self.approvals(), self.commits(), self.interp.texts), ("expired", 0, 0, []))
        self.assertEqual(self.say(f"yes {a['code']} thanks"), "no-target")
        self.assertEqual((self.approvals(), self.commits()), (0, 0))
        self.replies()
        b = self.proposal("desc")
        self.assertEqual(self.say(f"no {b['code']}"), "rejected")
        self.replies()
        self.say(f"{b['code']}?")
        self.replies()
        self.assertEqual(self.interp.texts[-1:], [f"{b['code']}?"])  # no longer waiting: a plain request

    def test_hex_word_that_is_no_waiting_code_stays_a_request(self):
        self.proposal()
        for text in ("cafe", "beef", "cafe?"):
            with self.subTest(text=text):
                self.say(text)
                self.replies()
                self.assertEqual(self.interp.texts[-1], text)
        self.assertEqual(self.approvals(), 0)

    def test_other_words_keep_todays_reading(self):
        self.proposal()
        for text in ("yes but make it 10am", "no, 5pm", "yes {} but later", "yes yes {}", "yes {} {}", "yes no {}",
                     "yes abc", "yes {}x", "{} {}", "yes {} 不要", "不要 yes {}", "no {} 谢谢", "yes {} não", "yes {}é", "yes {} нет?"):
            with self.subTest(text=text):
                code = self.drafts()[-1]["code"]
                text = text.format(code, code) if "{}" in text else text
                self.say(text)
                self.replies()
                self.assertEqual(self.interp.texts[-1], text)
        self.assertEqual(self.approvals(), 0)
        self.assertEqual(self.drafts()[-1]["state"], "proposed")

    def test_yes_please_stays_the_near_approval(self):
        code = self.proposal()["code"]
        self.assertEqual(self.say("yes please"), "near-approval")
        self.assertEqual(self.replies(), [f"Nothing was applied. To apply {code}, reply yes {code}."])
        self.assertEqual((self.approvals(), self.interp.texts), (0, []))

    def test_delayed_decorated_yes_is_judged_at_the_time_it_was_sent(self):
        code = self.proposal()["code"]
        sent = self.now
        self.now += timedelta(seconds=700)  # after the draft expired, but the yes was sent in time
        self.n += 1
        late = conversation.Inbound(f"m{self.n}", self.conv.settings["ownerChat"], self.conv.settings["ownerSenders"][0],
                                    f"Yes, {code}", received_at=sent.isoformat())
        self.assertEqual(self.conv.handle(late), "approved")


if __name__ == "__main__":
    unittest.main()
