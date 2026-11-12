"""HASS-CLOVER-2: the owner's till questions in the chat (hass/clover/chat.py and its hook in hass/conversation.py), answered from the
private cache only, with the voice rules: fresh, 'as of' after 20 minutes, "I can't reach the till right now", nothing after 24 hours,
and no writes ("I can read the till but I can't change it yet"). No network; the cache is filled from recorded fixtures.
Run: python3 -B -m unittest hass.tests.test_clover_chat
"""
import os
import shutil
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import conversation, voice
from hass.clover import cache, chat, sync
from hass.tests.test_clover_cli import T0
from hass.tests.test_clover_client import fixture
from hass.tests.test_conversation import CHAT, OWNER, STRANGER, ConversationTestCase

BLOCK = {"environment": "production", "merchantId": "FAKEMERCH0001", "tokenFile": "/nowhere/production-read.token", "liveApproved": False}


def seed(state, now=T0):
    rows, _ = sync.rows(fixture("items.json")["elements"], fixture("item_stocks.json")["elements"])
    cache.write_items(state, rows, now)


def strict(text):
    """The reply as the outbox would store it, with the voice rules enforced (a broken rule raises)."""
    broken = voice.check(text, long_ok=True)
    if broken:
        raise AssertionError(f"voice rules broken: {broken}: {voice.plain(text)!r}")
    return voice.plain(text)


class DeskCase(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="clover-chat-"))
        self.addCleanup(shutil.rmtree, self.state, True)
        os.chmod(self.state, 0o700)
        self.desk = chat.TillDesk(str(self.state), BLOCK)

    def ask(self, text, now=T0):
        intent = self.desk.parse(text)
        self.assertIsNotNone(intent, text)
        return strict(self.desk.answer(intent, now))


class ParseTests(DeskCase):
    def setUp(self):
        super().setUp()
        seed(self.state)

    def test_the_three_reads(self):
        for text, intent in (("how many Hass avocado do we have?", ("how_many", "hass avocado")),
                             ("How many eggs, dozen do we have", ("how_many", "eggs, dozen")),
                             ("how many tomatoes left", ("how_many", "tomatoes")),
                             ("how much heirloom tomatoes do we have", ("how_many", "heirloom tomatoes")),
                             ("what's the count of sunshine olive oil", ("how_many", "sunshine olive oil")),
                             ("low stock", ("low",)), ("Low stock?", ("low",)), ("what's low", ("low",)), ("what are we running low on?", ("low",)),
                             ("anything sold out?", ("low",)),
                             ("is Hass avocado in stock?", ("in_stock", "hass avocado")), ("are eggs, dozen sold out", ("in_stock", "eggs, dozen")),
                             ("do we have any sunshine olive oil left", ("in_stock", "sunshine olive oil")),
                             ("is the market special (ring up price) in stock", ("in_stock", "market special (ring up price)"))):
            with self.subTest(text=text):
                self.assertEqual(self.desk.parse(text), intent)

    def test_writes_are_claimed_and_refused(self):
        for text in ("change the price of Hass avocado to 2.00", "set the price of eggs, dozen to $8", "raise prices", "price of olive oil to 14",
                     "add olive oil to the till", "new item: olive oil, 12.50, pantry", "received 12 Sunshine olive oil",
                     "set the count of eggs, dozen to 12", "hide the old honey jar on the till", "give eggs a sku", "update clover",
                     "lower the tomato price"):
            with self.subTest(text=text):
                self.assertEqual(self.desk.parse(text), ("write",))
                self.assertEqual(self.desk.answer(("write",), T0), "I can read the till but I can't change it yet.")

    def test_everything_else_goes_on_to_the_usual_handling(self):
        for text in ("how many people signed up for saturday's hike?", "how many hikes are scheduled", "how many drafts are waiting",
                     "how many photos do we have", "how much is it", "how many", "is the website working", "are we open till 6",
                     "change our hours: open till 6 on sunday", "update the description of the olive oil, no price", "add a hike for saturday",
                     "mark the olive oil sold out", "olive oil is in stock again", "hello", "yes a1b2", "status", "do we have a hike on sunday",
                     "is the hike full", "how many can come", "register people for the walk", "line one\nhow many eggs do we have"):
            with self.subTest(text=text):
                self.assertIsNone(self.desk.parse(text))

    def test_an_unknown_item_is_claimed_only_with_stock_words(self):
        self.assertEqual(self.desk.parse("how many kumquats do we have"), ("how_many", "kumquats"))
        self.assertIsNone(self.desk.parse("how many kumquats"))
        self.assertEqual(self.desk.parse("how many tomatoes"), ("how_many", "tomatoes"))     # a 'did you mean' match is enough

    def test_an_exact_till_name_wins_over_the_other_topic_words(self):
        rows, _ = sync.rows([{"id": "FAKEITEM00009", "name": "Trail mix", "price": 500}], [{"item": {"id": "FAKEITEM00009"}, "quantity": 3}])
        cache.write_items(self.state, rows, T0)
        self.assertEqual(self.desk.parse("how many trail mix"), ("how_many", "trail mix"))

    def test_vague_or_short_words_never_ride_on_a_did_you_mean(self):
        rows, _ = sync.rows([{"id": "FAKEITEM00012", "name": "Biscuits", "price": 500}, {"id": "FAKEITEM00013", "name": "Pistachios", "price": 900}],
                            [{"item": {"id": "FAKEITEM00012"}, "quantity": 3}])
        cache.write_items(self.state, rows, T0)
        for text in ("how much is it", "how much does it cost", "how many is that", "how much are pistachios", "is it in stock"):
            with self.subTest(text=text):
                self.assertIsNone(self.desk.parse(text))
        self.assertEqual(self.desk.parse("how many pistachios"), ("how_many", "pistachios"))


class AnswerTests(DeskCase):
    def test_fresh_answers(self):
        seed(self.state)
        self.assertEqual(self.ask("how many hass avocado do we have"), "Hass avocado: 40 in the till.")
        self.assertEqual(self.ask("is sunshine olive oil in stock"), "Yes, Sunshine olive oil: 11 in the till.")
        self.assertEqual(self.ask("are eggs, dozen in stock"), "No, Eggs, dozen is sold out in the till.")
        self.assertEqual(self.ask("is market special (ring up price) in stock"),
                         "The till keeps no count for Market special (ring up price), so I can't tell.")
        self.assertEqual(self.ask("how many sunshine do we have"), "I can't find exactly that. The closest is Sunshine olive oil: 11 in the till.")
        self.assertEqual(self.ask("how many as-pan-sunshine-olive-oil-01 do we have"), "Sunshine olive oil: 11 in the till.")
        self.assertEqual(self.ask("low stock"), "Sold out: Eggs, dozen. 1 item(s) have no count in the till, so I can't tell.")

    def test_older_than_20_minutes_says_as_of(self):
        seed(self.state)
        self.assertEqual(self.ask("how many hass avocado do we have", T0 + timedelta(minutes=19)), "Hass avocado: 40 in the till.")
        self.assertEqual(self.ask("how many hass avocado do we have", T0 + timedelta(minutes=25)),
                         "Hass avocado: 40 in the till. (till count as of 12:00 pm)")

    def test_till_down_says_so_and_nothing_after_24_hours(self):
        seed(self.state)
        cache.record_failure(self.state, "unreachable", T0 + timedelta(minutes=15))
        self.assertTrue(self.ask("how many hass avocado do we have", T0 + timedelta(minutes=16)).startswith(
            "I can't reach the till right now. The last count I have is from 12:00 pm, so treat it as old. Hass avocado: 40 in the till."))
        old = self.ask("how many hass avocado do we have", T0 + timedelta(hours=25))
        self.assertNotIn("40", old)
        self.assertIn("I will not quote a count that old", old)
        self.assertNotIn("Sold out", self.ask("low stock", T0 + timedelta(hours=25)))

    def test_no_pull_yet_a_failing_first_pull_and_an_unsafe_cache(self):
        self.assertEqual(self.desk.answer(("low",), T0), chat.NEVER_READ)
        cache.record_failure(self.state, "refused-key", T0)
        self.assertEqual(self.desk.answer(("low",), T0), "I can't reach the till right now, so I don't have a count to give you.")
        seed(self.state)
        os.chmod(cache.path_for(self.state), 0o644)
        self.assertEqual(self.desk.answer(("how_many", "hass avocado"), T0), chat.DOWN_NO_DATA)
        self.assertIsNone(self.desk.parse("how many hass avocado"))     # an unreadable cache never claims a question without stock words

    def test_hidden_items_and_names_the_voice_rules_would_flag_are_shown_as_the_till_has_them(self):
        rows, _ = sync.rows([{"id": "FAKEITEM00010", "name": "Raw honey (error-free 500g) by api", "sku": "AS-PAN-HONEY-01", "price": 900},
                             {"id": "FAKEITEM00011", "name": "Raw honey (error-free 500g) by api", "sku": "AS-PAN-HONEY-02", "price": 900}],
                            [{"item": {"id": "FAKEITEM00010"}, "quantity": 0}, {"item": {"id": "FAKEITEM00011"}, "quantity": 4}])
        cache.write_items(self.state, rows, T0)
        text = self.ask("how many raw honey (error-free 500g) by api do we have")
        self.assertIn("More than one item is called that: Raw honey (error-free 500g) by api (SKU AS-PAN-HONEY-01): 0 in the till", text)
        self.assertEqual(self.desk.answer(("write",), T0), chat.WRITE_REPLY)

    def test_the_desk_holds_no_token_and_never_touches_the_network(self):
        self.assertEqual(repr(self.desk), "TillDesk(read-only)")
        self.assertFalse(any("token" in k.lower() and not k.startswith("_") for k in vars(self.desk)))
        with mock.patch("socket.create_connection", side_effect=AssertionError("network")), \
                mock.patch("hass.clover.credential.load_token", side_effect=AssertionError("token")):
            seed(self.state)
            self.ask("low stock")
            self.ask("how many hass avocado do we have")


class ConversationTillTests(ConversationTestCase):
    """The hook: an owner till question is answered before the interpreter; nothing is drafted; without a block nothing changes."""

    def setUp(self):
        super().setUp()
        self.now = T0
        strict_box = mock.patch.object(conversation.Outbox, "strict", True)
        strict_box.start()
        self.addCleanup(strict_box.stop)
        self.calls = []
        real = self.interp.interpret
        self.interp.interpret = lambda text, *a, **k: (self.calls.append(text), real(text, *a, **k))[1]
        seed(Path(self.repo.state))

    def attach(self):
        self.conv.till = chat.TillDesk(str(self.repo.state), BLOCK)

    def test_owner_questions_are_answered_from_the_till_with_no_model_and_no_draft(self):
        self.attach()
        self.assertEqual(self.say("how many Hass avocado do we have?"), "till-read")
        self.assertEqual(self.replies(), ["Hass avocado: 40 in the till."])
        self.assertEqual(self.say("low stock"), "till-read")
        self.assertIn("Sold out: Eggs, dozen.", self.replies()[0])
        self.assertEqual(self.say("change the price of Hass avocado to 2.00"), "till-write-refused")
        self.assertEqual(self.replies(), ["I can read the till but I can't change it yet."])
        self.assertEqual((self.calls, self.drafts(), self.commits()), ([], [], 0))

    def test_without_a_clover_block_the_same_words_go_to_the_usual_handling(self):
        self.assertIsNone(self.conv.till)
        self.say("how many Hass avocado do we have?")
        self.assertEqual(self.calls, ["how many Hass avocado do we have?"])
        self.assertNotIn("in the till", " ".join(self.replies()))

    def test_other_messages_and_strangers_are_untouched(self):
        self.attach()
        self.assertEqual(self.say("how many Hass avocado do we have?", sender=STRANGER, chat="chat-stranger"), "ignored")
        self.assertEqual(self.replies(), [])
        self.say("how many people signed up for the hike?")
        self.assertEqual(self.calls, ["how many people signed up for the hike?"])


if __name__ == "__main__":
    unittest.main()
