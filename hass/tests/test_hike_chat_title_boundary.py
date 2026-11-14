"""RF1045-11: a hike title expands from its meeting place only when the place equals the name or extends it after a space.

Pure offline shaper tests with synthetic ops. Run: python3 -B -m unittest hass.tests.test_hike_chat_title_boundary -q
"""

import copy
import unittest

from hass import hike_chat


def create(title, meeting, **extra):
    args = {"title": title, "date": "2026-11-08", "time": "10:00", "meetingPoint": meeting, "rsvpEnabled": False}
    args.update(extra)
    return {"op": "hike.create", "args": args}


class TitleBoundaryTests(unittest.TestCase):
    def test_character_prefix_does_not_replace_supplied_title(self):
        for title, meeting, want in (("Pine", "Pineapple trail", "Pine hike"), ("Cedar", "Cedarwood loop", "Cedar hike"),
                                     ("Oak", "Oakley ridge", "Oak hike")):
            with self.subTest(title=title):
                self.assertEqual(hike_chat.build_title(title, meeting), want)
                ops = [create(title, meeting)]
                before = copy.deepcopy(ops)
                shaped = hike_chat.shape(ops, {})
                self.assertEqual(shaped.ops[0]["args"]["title"], want)
                self.assertEqual(shaped.ops[0]["args"]["meetingPoint"], meeting)
                self.assertEqual(ops, before)  # input untouched

    def test_exact_and_space_bounded_longer_names_still_expand(self):
        self.assertEqual(hike_chat.build_title("Pine", "Pine"), "Pine hike")
        self.assertEqual(hike_chat.build_title("Pine", "Pine ridge trail"), "Pine ridge trail hike")
        self.assertEqual(hike_chat.build_title("Fiscalini Ranch", "Fiscalini Ranch bluff trail"), "Fiscalini Ranch bluff trail hike")
        self.assertEqual(hike_chat.shape([create("Fiscalini Ranch", "Fiscalini Ranch bluff trail")], {}).ops[0]["args"]["title"],
                         "Fiscalini Ranch bluff trail hike")
        # no infix or reverse-prefix matching
        self.assertEqual(hike_chat.build_title("Ridge", "Pine ridge trail"), "Ridge hike")
        self.assertEqual(hike_chat.build_title("Pine ridge trail", "Pine"), "Pine ridge trail hike")

    def test_nfkc_casefold_and_whitespace_do_not_defeat_boundary(self):
        self.assertEqual(hike_chat.build_title("PINE", "pine  ridge\u00a0trail"), "pine ridge trail hike")
        self.assertEqual(hike_chat.build_title("\uff30\uff49\uff4e\uff45", "Pine\u3000ridge trail"), "Pine ridge trail hike")
        # character-only continuation refuses; the selected display spelling is kept
        self.assertEqual(hike_chat.build_title("\uff30\uff49\uff4e\uff45", "Pineapple trail"), "\uff30\uff49\uff4e\uff45 hike")
        self.assertEqual(hike_chat.build_title("PINE", "Pineapple trail"), "PINE hike")

    def test_punctuation_is_not_a_new_expansion_separator(self):
        for meeting in ("Pine-ridge", "Pine's loop", "Pine, ridge", "Pine2 loop", "Pine_ridge"):
            with self.subTest(meeting=meeting):
                self.assertEqual(hike_chat.build_title("Pine", meeting), "Pine hike")

    def test_existing_title_hike_meeting_spot_and_length_rules_remain(self):
        self.assertEqual(hike_chat.build_title("Pine walk", "Pine walk loop"), "Pine walk")
        self.assertEqual(hike_chat.build_title("Pine", "Pine ridge parking lot"), "Pine hike")  # MEET_WORD place is not a name
        self.assertEqual(hike_chat.build_title("Pine", "Pine gate"), "Pine hike")
        self.assertEqual(hike_chat.build_title("the Pine", "the Pine ridge"), "Pine ridge hike")
        self.assertEqual(hike_chat.build_title("", "Pine ridge"), "Pine ridge hike")
        self.assertEqual(hike_chat.build_title("  ", None), None)
        self.assertEqual(hike_chat.build_title(None, "x" * 100), None)
        self.assertEqual(hike_chat.build_title(5, 7), None)
        self.assertEqual(hike_chat.build_title("Pine", "Pine " + "x" * 80), "Pine")  # overlong expansion falls back to the title

    def test_shape_preserves_unrelated_calls_and_off_live_values(self):
        other = {"op": "hike.cancel", "args": {"id": "e1"}}
        ops = [other, create("Pine", "Pineapple trail"), create("Pine", "Pine ridge trail")]
        shaped = hike_chat.shape(ops, {})
        self.assertEqual(shaped.ops[0], other)
        self.assertEqual([c["args"]["title"] for c in shaped.ops[1:]], ["Pine hike", "Pine ridge trail hike"])
        self.assertEqual([c["args"]["meetingPoint"] for c in shaped.ops[1:]], ["Pineapple trail", "Pine ridge trail"])
        off = hike_chat.shape(ops, {}, live=False)
        self.assertEqual(off.ops, ops)  # off the live site nothing changes
        self.assertIsNone(off.ask)


if __name__ == "__main__":
    unittest.main()
