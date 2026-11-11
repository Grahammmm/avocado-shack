"""RF2100-13: a guest-limit alternative whose description would exceed the website limit is refused before asking for yes.
Run: python3 -B -m unittest hass.tests.test_hike_chat_offer_limit -q
"""

import copy
import unittest

from hass import hike_chat, voice

SENT = hike_chat.limit_sentence(10)
BASE = 800 - len(SENT) - 1  # plain description length that makes the result exactly 800
EXPLAIN = ("The website can't take sign-ups yet, and the description is too full to add the guest limit. Nothing changed. "
           "Send a shorter description with the guest limit, and I can try again.")


def update(**extra):
    return [{"op": "hike.update", "args": {"id": "h1", "capacity": 10, **extra}}]


def events(desc):
    return {"h1": {"title": "Cass Hill hike", "description": desc}}


class OfferLimitTests(unittest.TestCase):
    def test_exact_limit_allowed_one_over_refused(self):
        for ch in ("a", "é"):  # code points, not UTF-8 bytes
            ok = hike_chat.shape(update(), events=events(ch * BASE))
            self.assertTrue(ok.ask["ops"])
            self.assertEqual(len(ok.ask["ops"][0]["args"]["description"]), 800)
            self.assertIn("Reply yes or no", ok.ask["question"])
            over = hike_chat.shape(update(), events=events(ch * (BASE + 1)))
            self.assertIsNone(over.ask["ops"])
            self.assertEqual(over.ask["kind"], "offer")
            self.assertEqual(over.ask["question"], EXPLAIN)
            self.assertNotIn("yes", over.ask["question"].lower())
            self.assertEqual(voice.check(over.ask["question"]), [])

    def test_supplied_description_wins_even_when_empty(self):
        full = "a" * 790
        self.assertTrue(hike_chat.shape(update(description="short"), events=events(full)).ask["ops"])
        self.assertIsNone(hike_chat.shape(update(description="b" * 790), events=events("short")).ask["ops"])
        empty = hike_chat.shape(update(description=""), events=events(full))
        self.assertEqual(empty.ask["ops"][0]["args"]["description"], SENT)

    def test_old_limit_sentence_is_replaced_before_measuring(self):
        old = hike_chat.limit_sentence(1)
        fits = hike_chat.shape(update(), events=events("a" * BASE + " " + old))
        self.assertEqual(fits.ask["ops"][0]["args"]["description"].count("Limited to"), 1)
        self.assertEqual(len(fits.ask["ops"][0]["args"]["description"]), 800)
        self.assertIsNone(hike_chat.shape(update(), events=events("a" * (BASE + 1) + " " + old)).ask["ops"])

    def test_refusal_preserves_inputs_and_drops_whole_update(self):
        ops, evs = update(location="Cass Hill"), events("a" * (BASE + 1))
        before = copy.deepcopy((ops, evs))
        over = hike_chat.shape(ops, events=evs)
        self.assertEqual((ops, evs), before)
        self.assertIsNone(over.ask["ops"])
        self.assertEqual(over.ops, ops)
        self.assertNotIn("a" * 20, over.ask["question"])


if __name__ == "__main__":
    unittest.main()
