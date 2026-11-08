"""AV1102-09 (H15) tests: the owner's saved notes reach the interpreter as preferences, never as claims.

Conversation side: which memory rows are sent (newest 20, no aliases, active values only) and when the call stays the
plain two-argument call. Adapter side: the request bytes. Claim side: a note is not proof for claims.unstated.
Offline: a recording interpreter double and a fake transport only. Run: python3 -m unittest hass.tests.test_interpreter_notes -v
"""

import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation, interpreter_prompt, memory
from hass.interpreter_local import LocalInterpreter
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS

SOURCE = "owner-stated:test"
CLOCK = lambda: datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)  # noqa: E731
PENDING = [{"code": "beef", "state": "proposed", "summary": "Hours → Daily 8am–7pm"}]


class Recorder(conversation.FixtureInterpreter):
    """Records each call as ((text, pending), keywords); notes arrive only as the `notes` keyword."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.seen = []

    def interpret(self, text, pending, **kw):
        self.seen.append(((text, pending), kw))
        return super().interpret(text, pending)


class NotesTestCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.interp = Recorder(self.interp.mapping)
        self.conv = self.open()
        self.tick = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)

    def mem(self):
        return memory.Memory.on_connection(self.conv.db, lambda: self.tick)

    def save(self, key, value, kind="preference"):
        self.tick += timedelta(minutes=1)
        self.mem().remember(key, value, kind, SOURCE)

    def sent(self, text="hours"):
        self.interp.seen.clear()
        self.say(text)
        [call] = self.interp.seen
        return call


class SentNotesTests(NotesTestCase):
    def test_newest_20_without_aliases_newest_first(self):
        for i in range(25): self.save(f"note-{i:02d}", f"text {i}")
        for i in range(3): self.save(f"alias.jam-{i}", f"product:no-such-00{i}")
        (args, kw) = self.sent()
        self.assertEqual(args, ("hours", []))
        self.assertEqual(kw, {"notes": [{"key": f"note-{i:02d}", "text": f"text {i}"} for i in range(24, 4, -1)], "sent_at": self.now})
        self.assertEqual(len(kw["notes"]), conversation.MAX_NOTES)
        self.assertFalse([n for n in kw["notes"] if n["key"].startswith("alias.")])

    def test_no_table_or_no_rows_is_the_plain_two_argument_call(self):
        self.assertIsNone(self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory'").fetchone())
        self.assertEqual(self.sent("nothing"), (("nothing", []), {"sent_at": self.now}))
        self.mem()  # creates the empty table
        self.assertEqual(self.sent("nothing"), (("nothing", []), {"sent_at": self.now}))
        self.save("alias.only", "maker:Nobody")  # aliases alone are still no notes (and this one points at no record)
        self.assertEqual(self.sent("nothing"), (("nothing", []), {"sent_at": self.now}))

    def test_two_parameter_double_still_works_with_notes_absent(self):
        class Old(conversation.FixtureInterpreter):
            def interpret(self, text, pending, **kw):
                return super().interpret(text, pending)
        self.interp = Old(self.interp.mapping)
        self.conv = self.open()
        self.assertEqual(self.say("hours"), "proposed")

    def test_forgotten_and_superseded_values_are_never_sent(self):
        self.save("tone", "short and friendly")
        self.save("greeting", "Hi neighbour")
        self.save("sign-off", "Thanks")
        self.tick += timedelta(minutes=1)
        self.mem().correct("tone", "formal", SOURCE)
        self.tick += timedelta(minutes=1)
        self.mem().forget("greeting")
        (_args, kw) = self.sent()
        self.assertEqual(kw["notes"], [{"key": "tone", "text": "formal"}, {"key": "sign-off", "text": "Thanks"}])
        self.assertNotIn("short and friendly", json.dumps(kw, default=str))

    def test_a_memory_read_error_goes_on_without_notes(self):
        self.conv.db.execute("CREATE TABLE memory(id INTEGER PRIMARY KEY, key TEXT)")  # no value column: OperationalError
        with self.assertRaises(sqlite3.OperationalError): self.conv.db.execute("SELECT value FROM memory")
        self.assertEqual(self.say("hours"), "proposed")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Here's the change I'd make:"), reply)
        self.assertEqual(self.interp.seen[-1][1], {"sent_at": self.now})


class NoteIsNotProofTests(NotesTestCase):
    ADD = {"name": "Hass avocados", "brand": "Hass", "category": "fruit", "image": "assets/products/photo-product-001.webp",
           "displayBrand": "Hass", "description": "Grown in Watsonville"}

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.interp.mapping["add Hass avocados"] = _ops(("product.add", self.ADD))
        self.conv = self.open()

    def test_a_claim_copied_from_a_note_still_asks(self):
        self.save("origin", "all from Watsonville")
        self.assertEqual(self.say("add Hass avocados"), "claim-question")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("You didn't say "), reply)
        self.assertIn('"grown in"', reply)
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.interp.seen[-1][1]["notes"], [{"key": "origin", "text": "all from Watsonville"}])

    def test_the_owner_saying_it_in_the_message_proposes(self):
        self.save("origin", "all from Watsonville")
        self.interp.mapping["add Hass avocados, grown in Watsonville"] = _ops(("product.add", self.ADD))
        self.assertEqual(self.say("add Hass avocados, grown in Watsonville"), "proposed")


class RequestBytesTests(unittest.TestCase):
    class Fake:
        def __init__(self): self.calls = []

        def __call__(self, url, body, headers, timeout):
            self.calls.append(body)
            return 200, json.dumps({"message": {"content": json.dumps(_ops((HOURS, {"hours": NEW_HOURS})))},
                                    "done": True}).encode()

    def body(self, **kw):
        fake = self.Fake()
        LocalInterpreter("http://127.0.0.1:11434", "m", "SYSTEM", transport=fake, clock=CLOCK).interpret("hi", PENDING, **kw)
        [body] = fake.calls
        return body

    def main_bytes(self):
        user = json.dumps({"message": "hi", "pending": PENDING, "today": "2026-11-07", "weekday": "Saturday"},
                          ensure_ascii=False)
        return json.dumps({"model": "m", "messages": [{"role": "system", "content": "SYSTEM"},
                                                      {"role": "user", "content": user}],
                           "stream": False, "format": "json", "options": {"temperature": 0}},
                          ensure_ascii=False).encode("utf-8")

    def test_no_notes_or_an_empty_list_keep_main_bytes(self):
        for kw in ({}, {"notes": None}, {"notes": []}):
            with self.subTest(kw=kw): self.assertEqual(self.body(**kw), self.main_bytes())

    def test_a_note_survives_quote_newline_and_line_separator(self):
        text = 'say "hi"\nthen\u2028bye'
        sent = json.loads(self.body(notes=[{"key": "tone", "text": text}]))
        user = json.loads(sent["messages"][1]["content"])
        self.assertEqual(user["notes"], [{"key": "tone", "text": text}])
        self.assertEqual((user["message"], user["pending"]), ("hi", PENDING))

    def test_the_rule_is_the_last_prompt_rule(self):
        [rule] = [rule for rule in interpreter_prompt.RULES if '"notes"' in rule]
        self.assertIn('"notes"', rule)
        self.assertIn("never supplies a claim", rule)


if __name__ == "__main__":
    unittest.main()
