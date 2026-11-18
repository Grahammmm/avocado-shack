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
AV1937_PLAIN = (
    "Use this for the home page, a crate of ripe avocados on the counter",
    "Add a new maker called Example Orchard and its first product, pear jam",
    "Add a maker called Example Orchard; it has no website",
    "Stop stocking Example Orchard and hide its products",
    "Repeat hike walk-001 on 2026-12-06 at 09:00",
)  # AV1937-13
AV1937_POST = "post maker Example Orchard"
AV2152_PLAIN = (
    "For draft a1b2, use this on the home page: avocados in a wooden crate",
    "Cancel hike walk-001 with the note: Rained out - we will pick a new date soon.",
    "Set the hiking club opening paragraph to: Walk with us along the coast, share the trail, and leave room for discovery.",
    "Set the home notice to \"Closed Thanksgiving Day\" from 2026-11-26 through 2026-11-26.",
)
AV2152_COMMANDS = {"history notice": "history", "again a1b2": "again"}  # AV2152-14
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
    found = {(plain, text) for plain, text, _ in sends(doc)}
    out += [f"required example missing or misclassified: {t}" for t in AV1937_PLAIN if (True, t) not in found]
    out += [f"required example missing or misclassified: {AV1937_POST}"] if (False, AV1937_POST) not in found else []
    out += [f"required example missing or misclassified: {t}" for t in AV2152_PLAIN if (True, t) not in found]
    out += [f"required example missing or misclassified: {t}" for t in AV2152_COMMANDS if (False, t) not in found]
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

    def test_av1937_examples_required_and_classified(self):  # AV1937-13
        found = sends(self.doc)
        self.assertLessEqual(set(AV1937_PLAIN), {t for p, t, _ in found if p})
        self.assertIn(AV1937_POST, {t for p, t, _ in found if not p})
        for text in AV1937_PLAIN:
            self.assertIsNone(verb(text), text)
        self.assertEqual(verb(AV1937_POST), "post")
        self.assertEqual(problems(self.doc), [])

    def test_missing_or_reclassified_av1937_example_fails(self):  # AV1937-13
        for text in (*AV1937_PLAIN, AV1937_POST):
            missing = f"required example missing or misclassified: {text}"
            plain = text in AV1937_PLAIN
            line = f"Send{' (plain words)' if plain else ''}: `{text}`"
            self.assertIn(line, self.doc)
            self.assertEqual(problems(self.doc.replace(f"`{text}`", "`gone`")), [f"Send line is not a command: Send: `gone`", missing] if not plain else [missing])
            flipped = f"Send{'' if plain else ' (plain words)'}: `{text}`"
            self.assertIn(missing, problems(self.doc.replace(line, flipped)), text)

    def test_photo_reply_is_not_an_approval(self):  # AV1937-13
        photo = AV1937_PLAIN[0]
        self.assertIsNone(verb(photo))
        self.assertEqual(verb("yes a1b2"), "approve")
        self.assertIn(f"Send (plain words): `{photo}`", self.doc)
        self.assertIn("send any `yes` as its own message", self.doc)

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

    def test_av2152_examples_required_and_classified(self):  # AV2152-14
        found = sends(self.doc)
        self.assertLessEqual(set(AV2152_PLAIN), {t for p, t, _ in found if p})
        self.assertLessEqual(set(AV2152_COMMANDS), {t for p, t, _ in found if not p})
        for text in AV2152_PLAIN:
            self.assertIsNone(verb(text), text)
        for text, name in AV2152_COMMANDS.items():
            self.assertEqual(verb(text), name)
        self.assertEqual(problems(self.doc), [])

    def test_av2152_missing_or_reclassified_example_fails(self):  # AV2152-14
        for text in (*AV2152_PLAIN, *AV2152_COMMANDS):
            plain = text in AV2152_PLAIN
            missing = f"required example missing or misclassified: {text}"
            line = f"Send{' (plain words)' if plain else ''}: `{text}`"
            self.assertIn(line, self.doc)
            self.assertIn(missing, problems(self.doc.replace(f"`{text}`", "`gone`")), text)
            flipped = f"Send{'' if plain else ' (plain words)'}: `{text}`"
            self.assertIn(missing, problems(self.doc.replace(line, flipped)), text)

    def test_batch_photo_instructions_and_separate_codes(self):  # AV2152-14
        for text in ("one to four photos in one message", "Each newly accepted photo gets its own draft code",
                     "already waiting, repeated in the same message, or already on a product", "does not get a new draft code",
                     "none is saved", "caption on several photos is ignored", "repeat the answer for each actual code",
                     "separately with its own code", "no text command that sends photos"):
            self.assertIn(text, self.doc)
            self.assertNotIn(text, self.doc.replace(text, ""), text)
        self.assertNotRegex(self.doc, r"(?i)one photo per message")

    def test_again_window_and_named_approval_wording(self):  # AV2152-14
        step = next(l for l in self.doc.splitlines() if "expired within the last seven days" in l)
        for text in ("site still matches", "new code and expiry", "separately with `yes` and the new code",
                     "A photo, a question, a cancelled, replaced or applied draft is not renewed"):
            self.assertIn(text, step)
        self.assertIn("resuming never applies a waiting draft by itself", self.doc)

    def test_store_undo_keeps_other_fields_not_same_field(self):  # AV2152-14
        for text in ("keeping a later shelf check or other detail", "a later edit of the same detail is a conflict and the undo is refused",
                     "with its new code", "Not every older change can be undone"):
            self.assertIn(text, self.doc)
            self.assertNotIn(text, self.doc.replace(text, ""), text)

    def test_notice_and_club_wording_promises_nothing_outbound(self):  # AV2152-14
        for text in ("Before the first day it stays hidden", "Hass sends no message to guests", "guests are not messaged",
                     "club page copy only, still a draft you approve; it is not an announcement or the store intro"):
            self.assertIn(text, self.doc)

    def test_readme_links_the_guide(self):
        self.assertIn("](PHONE_GUIDE.md)", (DOCS / "README.md").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
