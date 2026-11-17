"""AV2022-14 (H25): every message docs/hass/PHONE_GUIDE.md tells the owner to send parses as it claims. Stdlib, offline."""
import re
import unittest
from pathlib import Path

from hass.tests.test_commands_doc import verb

DOCS = Path(__file__).resolve().parents[2] / "docs" / "hass"
SECTIONS = ["Add a product", "Add a photo", "Post a hike", "Change opening hours", "Change the home page", "Route ideas", "Undo a change", "Pause and resume"]
SEND_RE = re.compile(r"Send( \(plain words\))?: `([^`]+)`")
NEW_EXAMPLES = {"hide the sample hikes", "bring the sample hikes back", "put the old photo back", "stop showing the eggs as sold out"}  # AV1622-11
LISTING = "listing photo-product-001"
PRIVATE_RE = re.compile(r"[\w.+-]+@[\w-]+\.\w+|\+\d|http://", re.I)


def sends(doc: str) -> list:
    """(plain, text, line) for each quoted message; a line naming Send that breaks the convention gives text None."""
    out = []
    for line in doc.splitlines():
        if not re.match(r"\s*Send\b", line):
            continue
        m = SEND_RE.fullmatch(line.strip())
        out.append((bool(m and m[1]), m[2] if m else None, line.strip()))
    return out


def problems(doc: str) -> list:
    out = []
    for plain, text, line in sends(doc):
        if text is None:
            out.append(f"not a Send line the checker can read: {line}")
        elif plain and verb(text) is not None:
            out.append(f"plain-words line parses as a command ({verb(text)}): {line}")
        elif not plain and verb(text) is None:
            out.append(f"Send line is not a command: {line}")
    headings = re.findall(r"^## (.+)$", doc, re.M)
    if headings != SECTIONS:
        out.append(f"sections are {headings}, not {SECTIONS}")
    out += [f"private text or http link: {ln.strip()}" for ln in doc.splitlines() if PRIVATE_RE.search(ln)]
    return out


class PhoneGuideTest(unittest.TestCase):
    def setUp(self):
        self.doc = (DOCS / "PHONE_GUIDE.md").read_text("utf-8")

    def test_guide_is_clean_and_short(self):
        self.assertEqual(problems(self.doc), [])
        self.assertLessEqual(len(self.doc.splitlines()), 110)

    def test_core_commands_quoted_and_plain_words_present(self):
        commands = {text for plain, text, _ in sends(self.doc) if not plain}
        self.assertLessEqual({"yes a1b2", "undo a1b2", "history", "pause changes", "resume changes", "status"}, commands)
        self.assertTrue(any(plain for plain, _, _ in sends(self.doc)), "no plain-words example")

    def test_new_examples_required_and_classified(self):  # AV1622-11
        found = sends(self.doc)
        plain = {text for p, text, _ in found if p}
        commands = {text for p, text, _ in found if not p}
        self.assertLessEqual(NEW_EXAMPLES, plain)
        self.assertIn(LISTING, commands)
        self.assertEqual(verb(LISTING), "listing")
        for text in NEW_EXAMPLES:
            self.assertIsNone(verb(text), text)
        for text in sorted(NEW_EXAMPLES):  # dropping any one is caught
            self.assertNotIn(text, {t for _p, t, _l in sends(self.doc.replace(f"`{text}`", "`gone`"))})
        self.assertEqual(problems(self.doc.replace("Send: `listing photo-product-001`", "Send (plain words): `listing photo-product-001`"))[0][:36],
                         "plain-words line parses as a command")

    def test_non_command_send_line_fails(self):
        self.assertEqual(problems(self.doc + "Send: `yes please`\n"), ["Send line is not a command: Send: `yes please`"])

    def test_command_as_plain_words_fails(self):
        bad = "Send (plain words): `history`"
        self.assertEqual(problems(self.doc + bad + "\n"), [f"plain-words line parses as a command (history): {bad}"])

    def test_off_convention_send_line_fails(self):
        for bad in ("Send: yes a1b2", "Send `status` now", "Send (plain words) `Add jam`", "Send: `status` and `history`"):
            self.assertEqual(problems(self.doc + bad + "\n"), [f"not a Send line the checker can read: {bad}"], bad)

    def test_sections_missing_extra_or_reordered_fail(self):
        swapped = self.doc.replace("## Undo a change", "## TMP").replace("## Pause and resume", "## Undo a change")
        swapped = swapped.replace("## TMP", "## Pause and resume")
        for doc in (swapped, self.doc.replace("## Post a hike", "## Post hikes"), self.doc + "## Extra\n"):
            self.assertEqual(len(problems(doc)), 1)
            self.assertTrue(problems(doc)[0].startswith("sections are"))

    def test_private_text_fails(self):
        for bad in ("Mail owner@example.com", "Call +15551234567", "See http://example.com"):
            self.assertEqual(problems(self.doc + bad + "\n"), [f"private text or http link: {bad}"], bad)
        self.assertEqual(problems(self.doc + "See [limits](LIMITS.md) or https://example.com\n"), [])

    def test_readme_links_the_guide(self):
        self.assertIn("](PHONE_GUIDE.md)", (DOCS / "README.md").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
