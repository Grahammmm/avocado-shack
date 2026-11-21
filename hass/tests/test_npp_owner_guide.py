"""Offline checks for the owner guide against the shipped reply and command copy."""

import json
from pathlib import Path
import re
import unittest

from hass.chat.commands import parse_command, parse_keyword

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/hass/NPP-OWNER-GUIDE.md"
TEMPLATES = ROOT / "hass/npp/assets/hass-npp-reply/reply-templates.json"
MARKER = re.compile(rb"<!-- hass-line: (/[^\s]+) -->")
EXAMPLE = re.compile(
    r"^Example only: card code `(?P<code>4ed1)`, first tag `(?P=code)-(?P<first>1)`, "
    r"next tag `(?P=code)-(?P<next>2)`, price `(?P<price>\$[0-9]+\.[0-9]{2})`, "
    r"item link `(?P<url>https://example\.com/\?item=[a-z0-9-]+#market)`\.$",
    re.MULTILINE,
)


class NPPOwnerGuideTests(unittest.TestCase):
    def setUp(self):
        self.raw = GUIDE.read_bytes()
        self.guide = self.raw.decode("utf-8")

    def example(self):
        examples = list(EXAMPLE.finditer(self.guide))
        self.assertEqual(len(examples), 1, "Declare one set of examples in the guide")
        return examples[0].groupdict()

    def quotes(self):
        # Keep the quote bytes as written, including any stray spaces or CRs.
        lines = self.raw.split(b"\n")
        for index, line in enumerate(lines):
            if b"hass-line:" in line:
                marker = MARKER.fullmatch(line)
                if marker is None:
                    self.fail(f"Bad marker at line {index + 1}")
                self.assertLess(index + 1, len(lines), "Missing quote after marker")
                self.assertTrue(lines[index + 1].startswith(b"> "), "Put the quote directly after its marker")
                yield marker[1].decode("utf-8"), lines[index + 1][2:]
            elif line.lstrip().startswith(b">"):
                self.assertGreater(index, 0, "Unmarked quote")
                self.assertIsNotNone(MARKER.fullmatch(lines[index - 1]), f"Unmarked quote at line {index + 1}")

    def test_c1_quotes_match_templates(self):
        # C1: a changed template or a retyped quote must not silently drift.
        quotes = list(self.quotes())
        self.assertTrue(quotes)
        templates = json.loads(TEMPLATES.read_bytes())
        example = self.example()
        versions = iter((example["first"], example["next"]))
        for pointer, quote in quotes:
            with self.subTest(pointer=pointer, quote=quote):
                template = templates
                for token in pointer[1:].split("/"):
                    template = template[token.replace("~1", "/").replace("~0", "~")]
                values = {"code": example["code"], "url": example["url"]}
                if "{n}" in template:
                    values["n"] = next(versions)
                self.assertEqual(quote, template.format(**values).encode("utf-8"))

    def test_c2_required_lines_present(self):
        # C2: dropping a key reply must fail even if all surviving quotes match.
        templates = json.loads(TEMPLATES.read_bytes())
        pointers = {pointer for pointer, _ in self.quotes()}
        self.assertLessEqual({
            "/prompts/ready", "/guards/replaced", "/guards/which_card",
            "/guards/not_ready", "/confirm/posted",
        }, pointers)
        self.assertTrue(pointers.intersection(
            f"/questions/{name}" for name in templates["questions"] if not name.startswith("ask_edit_")
        ), "Quote at least one missing-info question")

    def test_c3_phrases_accepted(self):
        # C3: check the typed examples, not a separate copy of the commands.
        # The parsers accept the canonical words as well as the phrase aliases.
        for heading, parse, verb in (
            ("Undo", parse_command, "undo"),
            ("Cancel a card", parse_keyword, "reject"),
        ):
            with self.subTest(heading=heading):
                section = self.guide.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
                phrases = re.findall(r"`([^`\n]+)`", section)
                self.assertTrue(phrases, f"No command shown under {heading}")
                for phrase in phrases:
                    self.assertEqual(parse(phrase), (verb, None), phrase)

    def test_c4_plain_and_short(self):
        # C4: catch a growing handout, stray numbers or pasted contact details.
        self.assertLessEqual(len(self.guide.splitlines()), 60)
        self.assertLessEqual(len(self.guide), 4500)
        self.assertNotIn("@", self.guide)
        example = self.example()
        code = example["code"]
        allowed = (f"{code}-{example['first']}", f"{code}-{example['next']}",
                   code, example["price"], example["url"])
        tokens = "|".join(map(re.escape, allowed))
        remaining = re.sub(rf"(?<!\w)(?:{tokens})(?!\w)", "", self.guide)
        # A phone number would leave digits too; no separate format list needed.
        self.assertFalse(any(char.isdigit() for char in remaining), "Use only the declared example numbers")
