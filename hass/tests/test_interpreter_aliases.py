"""AV0007-06 (H15/H05) tests: owner aliases reach the interpreter as identifier hints, never as claims.

Conversation side: which alias rows are sent (live records only, newest 50). Adapter side: the request bytes.
Claim side: an alias is no proof for claims.unstated. Offline: a recording interpreter double and a fake transport.
Run: python3 -m unittest hass.tests.test_interpreter_aliases -v
"""

import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation, interpreter_prompt, memory
from hass.interpreter_local import LocalInterpreter
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS

AVO = "photo-product-001"
CLOCK = lambda: datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)  # noqa: E731
PENDING = [{"code": "beef", "state": "proposed", "summary": "Hours → Daily 8am–7pm"}]


class Recorder(conversation.FixtureInterpreter):
    def __init__(self, mapping):
        super().__init__(mapping)
        self.seen = []

    def interpret(self, text, pending, **kw):
        self.seen.append(((text, pending), kw))
        return super().interpret(text, pending)


class AliasCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.interp = Recorder(self.interp.mapping)
        self.conv = self.open()
        self.tick = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)

    def mem(self):
        return memory.Memory.on_connection(self.conv.db, lambda: self.tick)

    def save(self, key, value, minutes=1):
        self.tick += timedelta(minutes=minutes)
        self.mem().remember(key, value, "fact", "owner-stated:test")

    def sent(self, text="hours"):
        self.interp.seen.clear()
        self.say(text)
        [call] = self.interp.seen
        return call


class SentAliasesTests(AliasCase):
    def test_live_aliases_newest_50_after_filtering(self):
        for i in range(55): self.save(f"alias.jam-{i:02d}", f"product:{AVO}")
        self.save("alias.gone", "product:no-such-product")  # newer, dangling
        self.save("alias.bad", "nonsense")
        self.save("alias.", f"product:{AVO}")
        self.save("note-x", f"product:{AVO}")
        self.save("alias.same", "maker:Etto")
        (_args, kw) = self.sent()
        names = [a["name"] for a in kw["aliases"]]
        self.assertEqual(names, ["same"] + [f"jam {i:02d}" for i in range(54, 5, -1)])
        self.assertEqual(len(names), conversation.MAX_INTERPRETER_ALIASES)
        self.assertEqual(list(kw["aliases"][0]), ["name", "kind", "id"])
        self.assertEqual(kw["aliases"][0], {"name": "same", "kind": "maker", "id": "Etto"})
        self.assertEqual(list(kw), ["notes", "aliases"])

    def test_equal_time_ties_break_newest_id_first(self):
        for name in ("a", "b"): self.save(f"alias.{name}", f"product:{AVO}", minutes=0)
        self.assertEqual([a["name"] for a in self.sent()[1]["aliases"]], ["b", "a"])

    def test_forget_and_correction_take_effect_next_request(self):
        self.save("alias.green-jam", f"product:{AVO}")
        self.assertEqual(self.sent()[1]["aliases"], [{"name": "green jam", "kind": "product", "id": AVO}])
        self.tick += timedelta(minutes=1)
        self.mem().correct("alias.green-jam", "product:photo-product-016", "owner-stated:test")
        self.assertEqual(self.sent()[1]["aliases"], [{"name": "green jam", "kind": "product", "id": "photo-product-016"}])
        self.tick += timedelta(minutes=1)
        self.mem().forget("alias.green-jam")
        self.assertEqual(self.sent()[1], {})

    def test_notes_and_aliases_coexist(self):
        self.save("tone", "short")
        self.save("alias.jam", f"product:{AVO}")
        kw = self.sent()[1]
        self.assertEqual(sorted(kw), ["aliases", "notes"])
        self.assertEqual(kw["notes"], [{"key": "tone", "text": "short"}])

    def test_missing_memory_and_unreadable_catalog_omit_context(self):
        self.assertIsNone(self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory'").fetchone())
        self.assertEqual(self.sent("nothing"), (("nothing", []), {}))
        self.assertIsNone(self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory'").fetchone(), "no table made")
        self.mem()
        self.assertEqual(self.sent("nothing"), (("nothing", []), {}))
        self.save("alias.jam", f"product:{AVO}")
        (self.repo.wt / "hass" / "content" / "products.json").write_text("{damaged", "utf-8")
        self.assertEqual(self.sent("nothing"), (("nothing", []), {}))

    def test_a_memory_read_error_goes_on_without_aliases(self):
        self.conv.db.execute("CREATE TABLE memory(id INTEGER PRIMARY KEY, key TEXT)")
        self.assertEqual(self.say("hours"), "proposed")
        self.assertEqual(self.interp.seen[-1][1], {})

    def test_two_parameter_double_still_works_with_aliases_absent(self):
        class Old(conversation.FixtureInterpreter):
            def interpret(self, text, pending):
                return super().interpret(text, pending)
        self.interp = Old(self.interp.mapping)
        self.conv = self.open()
        self.assertEqual(self.say("hours"), "proposed")


class AliasIsNotProofTests(AliasCase):
    ADD = {"name": "Hass avocados", "brand": "Hass", "category": "fruit", "image": "assets/products/photo-product-001.webp",
           "displayBrand": "Hass", "description": "Grown in Watsonville"}

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.interp.mapping["add Hass avocados"] = _ops(("product.add", self.ADD))
        self.conv = self.open()

    def test_alias_claim_is_not_evidence(self):
        self.save("alias.grown-in-watsonville", f"product:{AVO}")
        self.assertEqual(self.say("add Hass avocados"), "claim-question")
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.interp.seen[-1][0][0], "add Hass avocados")
        self.assertEqual(self.interp.seen[-1][1]["aliases"][0]["name"], "grown in watsonville")

    def test_the_owner_saying_it_in_the_message_proposes(self):
        self.save("alias.grown-in-watsonville", f"product:{AVO}")
        self.interp.mapping["add Hass avocados, grown in Watsonville"] = _ops(("product.add", self.ADD))
        self.assertEqual(self.say("add Hass avocados, grown in Watsonville"), "proposed")


class RequestBytesTests(unittest.TestCase):
    class Fake:
        def __init__(self): self.calls = []

        def __call__(self, url, body, headers, timeout):
            self.calls.append(body)
            return 200, json.dumps({"message": {"content": json.dumps(_ops((HOURS, {"hours": NEW_HOURS})))},
                                    "done": True}).encode()

    def make(self):
        fake = self.Fake()
        return fake, LocalInterpreter("http://127.0.0.1:11434", "m", "SYSTEM", transport=fake, clock=CLOCK)

    def body(self, **kw):
        fake, interp = self.make()
        interp.interpret("hi", PENDING, **kw)
        [body] = fake.calls
        return body

    def user(self, **kw):
        return json.loads(json.loads(self.body(**kw))["messages"][1]["content"])

    def test_none_and_empty_are_byte_identical_to_no_context(self):
        base = self.body()
        for kw in ({"aliases": None}, {"aliases": []}, {"notes": None, "aliases": []}):
            with self.subTest(kw=kw): self.assertEqual(self.body(**kw), base)

    def test_alias_json_roundtrip_and_member_order(self):
        data = [{"name": 'say "hi" é', "kind": "product", "id": AVO}]
        notes = [{"key": "tone", "text": "short"}]
        user = self.user(notes=notes, aliases=data)
        self.assertEqual(list(user), ["message", "pending", "today", "weekday", "notes", "aliases"])
        self.assertEqual(user["aliases"], data)
        self.assertEqual(list(self.user(aliases=data))[-1], "aliases")

    def test_an_unencodable_alias_payload_fails_as_a_request(self):
        fake, interp = self.make()
        result = interp.interpret("hi", PENDING, aliases=[{"name": "\ud800", "kind": "product", "id": AVO}])
        self.assertEqual((interp.last_error, fake.calls), ("request", []))
        self.assertIn("unsupported", result)


class PromptRuleTests(unittest.TestCase):
    RULE = ('The user message may give "aliases": owner-saved names for a product or maker. An alias names exactly its '
            "listed kind and id; use it only to identify that record. An alias never supplies a claim, a maker "
            "relationship, or text to copy into a change. Claims must come from the owner's message, not alias names "
            "or saved notes.")

    def test_rule_once(self):
        self.assertEqual(interpreter_prompt.RULES.count(self.RULE), 1)


if __name__ == "__main__":
    unittest.main()
