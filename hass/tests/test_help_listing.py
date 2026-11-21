"""HRM-13 (M5): `help listing` tells Mike how to list a new product by photo, in Hass's own words, and `help` points to it.
The wording follows the owner guide (docs/hass/NPP-OWNER-GUIDE.md); the example tag has the form of reply-templates.json
prompts.ready. Fixtures only, no network. Run: python3 -B -m unittest hass.tests.test_help_listing hass.tests.test_help -v
"""

import json
import re
import unittest
from pathlib import Path

from hass import conversation, voice
from hass.chat import commands

TEMPLATES = Path(__file__).resolve().parents[1] / "npp" / "assets" / "hass-npp-reply" / "reply-templates.json"
DETAIL = voice.plain(commands.help_detail("listing")).splitlines()
LINES = voice.plain(conversation.HELP_TEXT).splitlines()


class HelpListingTests(unittest.TestCase):
    def test_c1_detail_text(self):
        """C1: photo with the selling price (each or per lb), website card and a code, plain-word changes, `yes <code>-<n>`
        from the latest card posts it, `undo` takes it down; at most 5 short lines, the photo flow first."""
        self.assertEqual(conversation.parse_command("help listing"), ("help", "listing"))
        self.assertEqual(conversation.help_detail("listing"), commands.help_detail("listing"))
        self.assertLessEqual(len(DETAIL), 5)
        for line in DETAIL: self.assertLessEqual(len(line), 70, line)
        flow = " ".join(DETAIL[:3])
        steps = ("send a photo", "selling price", "each or per lb", "website card", "a code", "change it in your own words",
                 "yes 4ed1-2", "latest card", "posts it", "undo takes it down")
        at = [flow.find(step) for step in steps]
        self.assertNotIn(-1, at, dict(zip(steps, at)))
        self.assertEqual(at, sorted(at))  # in the order Mike does them
        self.assertEqual(DETAIL[3:], ["listing Etto - what's shown for one thing", "listing store - the hours and home page words"])
        for word in ("cost", "paid", "quantity", "stock"): self.assertNotIn(word, flow)  # never_say: nothing private is asked for

    def test_c2_help_mentions(self):
        """C2: HELP_TEXT names `help listing` in exactly one line and keeps within the help length limits (14 lines of 70)."""
        self.assertEqual([ln for ln in LINES if "help listing" in ln], ["To list a new product by photo: help listing"])
        self.assertLessEqual(len(LINES), 14)
        for line in LINES: self.assertLessEqual(len(line), 70, line)
        self.assertEqual(LINES[-1], "Send help <command> for an example: help undo")
        unknown = voice.plain(commands.help_detail("a1b2")).splitlines()
        self.assertEqual(unknown[1:], LINES[1:-1])  # the unknown-name reply lists the same lines, so it points there too

    def test_c3_matches_template(self):
        """C3: the example tag is prompts.ready's `yes {code}-{n}` form, and every yes in the photo lines uses that form."""
        ready = json.loads(TEMPLATES.read_text("utf-8"))["prompts"]["ready"]
        [form] = re.findall(r"yes \{code\}-\{n\}", ready)
        self.assertIn(form.format(code="4ed1", n=2), " ".join(DETAIL[:3]))
        shape = re.escape(form).replace(r"\{code\}", "[0-9a-f]{4,12}").replace(r"\{n\}", "[1-9][0-9]*")
        yeses = re.findall(r"\byes \S+", " ".join(DETAIL[:3]))
        self.assertTrue(yeses)
        for found in yeses: self.assertRegex(found, "^" + shape + "$")


if __name__ == "__main__":
    unittest.main()
