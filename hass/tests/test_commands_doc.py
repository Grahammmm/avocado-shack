"""RF1005-6 (H17/H25): docs/hass/COMMANDS.md lists exactly the commands hass/conversation.py parses (stdlib, offline)."""
import re
import unittest
from pathlib import Path

from hass import conversation as conv

DOC = Path(__file__).resolve().parents[2] / "docs" / "hass" / "COMMANDS.md"
PARSERS = (conv.parse_command, conv.parse_memory, conv.parse_keyword)  # the order Conversation._handle tries them


def verb(text):
    """The verb a whole message parses to (command, memory or approval keyword), or None."""
    return next((r[0] for p in PARSERS if (r := p(text))), None)


def parser_verbs() -> set:
    """Verbs found by calling the parsers on the words in their own regexes (bare and with a code), never a copied list."""
    words = set(re.findall(r"[a-z]{2,}", conv.COMMAND_RE.pattern + conv.MEMORY_RE.pattern + conv.KEYWORD_RE.pattern))
    return {v for w in words for text in (w, f"{w} a1b2", "photos to take") if (v := verb(text))}  # AV0222-04: the compound command


def rows(doc: str) -> list:
    """(send, example, line) for each table row below the `| Send | What happens | Example |` header."""
    lines = [ln.strip() for ln in doc.splitlines() if ln.strip().startswith("|")]
    return [(cells[0], cells[2], ln) for ln in lines
            if (cells := [c.strip() for c in ln.strip("|").split("|")])[0] != "Send" and not set(ln) <= set("|- ")]


def problems(table, verbs, words) -> list:
    out, documented = [], set()
    for send, example, line in table:
        spans = re.findall(r"`([^`]+)`", example)
        got = verb(spans[0]) if len(spans) == 1 else None
        if got is None:
            out.append(f"example does not parse: {line}")
        elif not re.search(rf"\b{got}\b", send.lower()):
            out.append(f"example parses as {got}, not this row's command: {line}")
        documented.add(got)
    sends = " ".join(send.lower() for send, _, _ in table)
    out += [f"no Send cell names: {w}" for w in sorted(verbs | set(words)) if not re.search(rf"\b{w}\b", sends)]
    out += [f"no example for parser verb: {v}" for v in sorted(verbs - documented)]
    out += [f"example verb the parser never returns: {v}" for v in sorted(documented - verbs - {None})]
    return out


class CommandsDocTest(unittest.TestCase):
    def setUp(self):
        self.table, self.verbs, self.words = rows(DOC.read_text("utf-8")), parser_verbs(), conv.APPROVE + conv.REJECT
        self.examples = [re.findall(r"`([^`]+)`", ex)[0] for _, ex, _ in self.table]

    def test_doc_and_parser_agree(self):
        self.assertTrue(self.verbs, "no verbs derived from the parser regexes")
        self.assertLessEqual({"undo", "history", "status", "pause", "resume", "approve", "reject"}, self.verbs)
        self.assertEqual(problems(self.table, self.verbs, self.words), [])

    def test_unparsed_row_fails_with_its_text(self):
        bad = "| `status` | Shows status. | `please status` |"
        self.assertIn(f"example does not parse: {bad}", problems(self.table + rows(bad), self.verbs, self.words))
        two = "| `status` | Shows status. | `status` or `history` |"
        self.assertIn(f"example does not parse: {two}", problems(self.table + rows(two), self.verbs, self.words))

    def test_new_parser_verb_without_a_row_fails(self):
        self.assertEqual(problems(self.table, self.verbs | {"refund"}, self.words),
                         ["no Send cell names: refund", "no example for parser verb: refund"])

    def test_dropped_row_fails(self):
        table = [r for r in self.table if r[0] != "`memory`"]
        self.assertEqual(problems(table, self.verbs, self.words),
                         ["no Send cell names: memory", "no example for parser verb: memory"])
        table = [r for r in self.table if "cancel" not in r[0]]
        self.assertIn("no Send cell names: cancel", problems(table, self.verbs, self.words))

    def test_example_under_the_wrong_row_fails(self):
        swapped = "| `history` | Lists changes. | `status` |"
        self.assertIn(f"example parses as status, not this row's command: {swapped}",
                      problems(self.table + rows(swapped), self.verbs, self.words))

    def test_trailing_punctuation_case_and_undo_forms(self):
        self.assertIn("Status.", self.examples)
        self.assertIn("undo A1B2!", self.examples)
        self.assertEqual(conv.parse_command("undo A1B2!"), ("undo", "a1b2"))
        self.assertIn("YES A1B2", self.examples)
        self.assertEqual(conv.parse_keyword("YES A1B2"), ("approve", "a1b2"))
        undo = {conv.parse_command(ex) for ex in self.examples if verb(ex) == "undo"}
        self.assertEqual(undo, {("undo", None), ("undo", "a1b2")})

    def test_note_command_punctuation_exceptions(self):
        """The intro's remember/forget exceptions match parse_memory (t_527e1533 RETURN item 1)."""
        doc = " ".join(DOC.read_text("utf-8").split())
        self.assertIn("except `remember` and `forget`", doc)
        self.assertIn("`Memory.`", doc)
        self.assertEqual(conv.parse_memory("Memory."), ("memory", None, None))
        self.assertIn("`forget parking.` looks for a note called `parking.`", doc)
        self.assertEqual(conv.parse_memory("forget parking."), ("forget", "parking.", None))
        self.assertEqual(conv.parse_memory("forget parking!"), ("forget", "parking", None))
        self.assertEqual(conv.parse_memory("remember Parking: Use the back lot!"),
                         ("remember", "parking", "Use the back lot!"))

    def test_again_row_contract(self):
        """AV2152-03: `again <code>` is a parser verb with one row whose example parses back to it and names its rules."""
        self.assertIn("again", self.verbs)
        [(send, example, line)] = [r for r in self.table if r[0].startswith("`again")]
        self.assertEqual((send, verb(re.findall(r"`([^`]+)`", example)[0])), ("`again <code>`", "again"))
        self.assertEqual(conv.parse_command(re.findall(r"`([^`]+)`", example)[0]), ("again", "a1b2"))
        cell = " ".join(line.split())
        for phrase in ("at most 7 days ago", "exactly 7 days still counts", "fresh expiry", "never calls the interpreter",
                       "the site changed since <code>; send the change again", "any photo draft", "works while paused", "needs `yes <new code>`"):
            self.assertIn(phrase, cell)

    def test_commands_note_section(self):
        """AV2152-07: the prose after the table describes the optional hike.cancel note (it adds no parser verb)."""
        doc = " ".join(DOC.read_text("utf-8").split())
        for phrase in ("`hike.cancel` takes the hike id and an optional `note`", "`Rained out - we will pick a new date soon`",
                       "one line of plain text, at most 160 characters", "public site copy", "above \"This hike is cancelled.\"",
                       "Cancelling notifies nobody", "removes the note", "not the `cancel <code>` command"):
            self.assertIn(phrase, doc)


if __name__ == "__main__":
    unittest.main()
