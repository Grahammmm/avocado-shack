"""AV1537-01 (H16): a needs-details question expires after approvalTtlSeconds like a proposal.

Expired questions vanish from `status` and from the interpreter's `pending`; a later answer naming the old code
is handled as a new request.
Run: python3 -B -m unittest hass.tests.test_needs_details_expiry -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_editor import HOURS, NEW_HOURS, _req

TTL = timedelta(seconds=600)  # SETTINGS approvalTtlSeconds in test_conversation


class SpyInterpreter(conversation.FixtureInterpreter):
    def __init__(self, mapping):
        super().__init__({})
        self.mapping, self.pendings = mapping, []

    def interpret(self, text, pending, **kw):
        self.pendings.append([p["code"] for p in pending])
        return super().interpret(text, pending)


class NeedsDetailsExpiryTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping["half"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}
        self.interp = self.conv.interpreter = SpyInterpreter(self.interp.mapping)

    def ask(self):
        self.assertEqual(self.say("half"), "needs-details")
        self.replies()
        row = self.drafts()[-1]
        self.assertEqual((row["state"], row["expires_at"]), ("needs-details", "2026-11-02T17:10:00+00:00"))
        return row

    def answer(self, name, code, complete=True):
        args = {"hours": NEW_HOURS} if complete else {}
        self.interp.mapping[name] = {"ops": _req((HOURS, args))["ops"], "revises": code}
        return self.say(name)

    def state(self, row):
        return [d for d in self.drafts() if d["row_id"] == row["row_id"]][0]

    def status(self):
        self.assertEqual(self.say("status"), "status")
        [reply] = self.replies()
        return reply

    def test_expired_question_leaves_status_and_pending(self):
        q = self.ask()
        self.assertIn(f"{q['code']} needs details:", self.status())
        self.assertEqual(self.say("hello there"), "unsupported")
        self.assertEqual(self.interp.pendings[-1], [q["code"]])
        self.now = T0 + TTL + timedelta(seconds=1)
        self.assertEqual(self.say("hello there"), "unsupported")
        self.replies()
        self.assertEqual(self.interp.pendings[-1], [])
        self.assertEqual(self.state(q)["state"], "expired")
        self.assertNotIn(q["code"], self.status())
        self.assertEqual((self.commits(), self.editor.applies), (0, 0))

    def test_boundary_uses_the_proposal_rule(self):
        q = self.ask()
        self.now = T0 + TTL - timedelta(seconds=1)
        self.assertEqual(self.answer("done", q["code"]), "proposed")
        self.replies()
        self.assertEqual((len(self.drafts()), self.state(q)["state"]), (1, "proposed"))
        second = self.ask_at(T0 + TTL)
        self.now = second["created"] + TTL  # exactly at expires_at
        self.assertEqual(self.say("hello there"), "unsupported")
        self.replies()
        self.assertEqual(self.state(second["row"])["state"], "expired")

    def ask_at(self, when):
        self.now = when
        self.interp.mapping["half2"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}
        self.assertEqual(self.say("half2"), "needs-details")
        self.replies()
        return {"row": self.drafts()[-1], "created": when}

    def test_status_alone_is_read_only_but_hides_the_lapsed_question(self):
        q = self.ask()
        self.now = T0 + TTL + timedelta(seconds=1)
        reply = self.status()
        self.assertNotIn(q["code"], reply)
        self.assertIn(conversation.NOTHING, reply)
        self.assertEqual(self.state(q)["state"], "needs-details")

    def test_partial_correction_refreshes_expiry(self):
        q = self.ask()
        self.now = T0 + TTL - timedelta(seconds=10)
        self.assertEqual(self.answer("still half", q["code"], complete=False), "needs-details")
        self.replies()
        row = self.state(q)
        self.assertEqual((len(self.drafts()), row["state"]), (1, "needs-details"))
        self.assertEqual(row["expires_at"], conversation._iso(self.now + TTL))
        self.now = T0 + TTL + timedelta(seconds=5)
        self.assertEqual(self.answer("done", q["code"]), "proposed")
        self.replies()
        self.assertEqual((len(self.drafts()), self.state(q)["state"]), (1, "proposed"))

    def test_late_fill_naming_expired_code_starts_a_new_request(self):
        q = self.ask()
        self.now = T0 + TTL + timedelta(seconds=1)
        self.assertEqual(self.answer("done", q["code"]), "proposed")
        [reply] = self.replies()
        old, new = self.drafts()
        self.assertEqual((old["state"], old["replaced_by"]), ("expired", None))
        self.assertEqual(new["state"], "proposed")
        self.assertNotEqual(new["code"], q["code"])
        self.assertTrue(reply.startswith(f"Draft {new['code']}:"), reply)
        self.assertEqual(self.interp.pendings[-1], [])
        # A second late answer still cannot reopen the expired question: it never becomes proposed.
        self.assertEqual(self.say(f"yes {q['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{q['code']} expired at 2026-11-02 09:10 PST; nothing changed."])
        self.assertEqual((self.state(old)["state"], self.commits()), ("expired", 0))

    def make_legacy(self, row):
        self.conv.db.execute("UPDATE drafts SET expires_at = NULL WHERE row_id = ?", (row["row_id"],))

    def test_legacy_row_without_expiry_uses_created_at(self):
        q = self.ask()
        self.make_legacy(q)
        self.now = T0 + TTL - timedelta(seconds=1)
        self.assertIn(f"{q['code']} needs details:", self.status())
        self.assertEqual(self.say("hello there"), "unsupported")
        self.replies()
        self.assertEqual(self.interp.pendings[-1], [q["code"]])
        self.assertEqual(self.state(q)["state"], "needs-details")
        self.now = T0 + TTL + timedelta(seconds=1)
        self.assertNotIn(q["code"], self.status())
        self.assertEqual(self.say(f"yes {q['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{q['code']} expired at 2026-11-02 09:10 PST; nothing changed."])
        self.assertEqual(self.state(q)["state"], "expired")

    def test_yes_to_an_expired_question_changes_nothing(self):
        q = self.ask()
        self.now = T0 + TTL + timedelta(seconds=1)
        self.assertEqual(self.say("yes"), "no-target")  # the lapse is named by the message that expires it
        self.assertEqual(self.replies(), ["That change timed out today at 9:10 am, so nothing changed. Tell me again if you still want it."])
        self.assertEqual(self.say(f"yes {q['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{q['code']} expired at 2026-11-02 09:10 PST; nothing changed."])
        self.assertEqual(self.say(f"no {q['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{q['code']} expired at 2026-11-02 09:10 PST; nothing changed."])
        self.assertEqual((self.state(q)["state"], self.commits(), self.editor.applies), ("expired", 0, 0))


if __name__ == "__main__":
    unittest.main()
