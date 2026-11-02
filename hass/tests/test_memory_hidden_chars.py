"""RF0310-4 (H15): owner memory refuses value, source and approved_change text holding C1 controls, line/paragraph
separators, direction controls or zero-width marks, before any transaction. U+200C/U+200D (emoji ZWJ sequences,
Persian/Indic scripts), accents, other scripts and U+00A0 keep working."""

import contextlib, sqlite3, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import memory
from hass.tests.test_memory import Clock

HIDDEN = ("\u0085", "\u2028", "\u2029", "\u202e", "\u2067", "\u200b", "\u2060", "\ufeff")
REST_OF_SET = ("\u0080", "\u009f", "\u200e", "\u200f", "\u202a", "\u2064", "\u2066", "\u2069")
ACCEPTED = ("Señora Pérez", "日本の柚子", "\U0001f468\u200d\U0001f469\u200d\U0001f467 family pack",
            "می\u200cخواهم", "4.99\u00a0USD")


class HiddenCharsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.clock = Clock()
        self.mem = memory.Memory(str(self.state), self.clock)
        self.addCleanup(self.mem.close)

    def rows(self):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM memory ORDER BY id")]

    def test_value_with_hidden_char_is_refused_and_writes_nothing(self):
        for ch in HIDDEN + REST_OF_SET:
            for value in (f"price 4.99{ch}", ch, f"{ch}Saturday"):
                with self.subTest(ch=hex(ord(ch)), value=value), \
                        self.assertRaisesRegex(ValueError, "value must be 1-500 plain characters"):
                    self.mem.remember("pickup.day", value, "fact", "operator:ok")
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.clock.calls, 0)  # refused before any transaction or date

    def test_source_with_hidden_char_is_unverified(self):
        for ch in HIDDEN:
            for source in (f"owner-stated:abc{ch}def", f"operator:{ch}", f"owner-approved:chg-0123456789ab{ch}"):
                with self.subTest(ch=hex(ord(ch)), source=source), self.assertRaisesRegex(ValueError, "unverified source"):
                    self.mem.remember("pickup.day", "Saturday", "fact", source)
        self.assertEqual(self.rows(), [])

    def test_approved_change_with_direction_mark_is_invalid(self):
        for ch in ("\u200e", "\u202e", "\u2028", "\u0085", "\ufeff"):
            with self.subTest(ch=hex(ord(ch))), self.assertRaisesRegex(ValueError, "invalid approved_change"):
                self.mem.remember("pickup.day", "Saturday", "fact", "operator:ok", approved_change=f"chg-1{ch}")
        self.assertEqual(self.rows(), [])

    def test_correct_with_hidden_char_leaves_active_row_unchanged(self):
        self.mem.remember("pickup.day", "Saturday", "fact", "operator:ok")
        before = self.rows()
        for value, source in (("Sun\u2028day", "owner-stated:msg-9"), ("Sunday", "owner-stated:msg\u202e9"),
                              ("\u2066Sunday\u2069", "operator:ok")):
            with self.subTest(value=value, source=source), self.assertRaises(ValueError):
                self.mem.correct("pickup.day", value, source)
        self.assertEqual(self.rows(), before)
        self.assertIsNone(before[0]["superseded_at"])
        self.assertEqual(self.mem.get("pickup.day"), "Saturday")

    def test_accents_scripts_emoji_zwj_zwnj_and_nbsp_are_kept(self):
        for i, text in enumerate(ACCEPTED):
            key = f"note.{i}"
            self.mem.remember(key, text, "preference", f"owner-stated:{text}", approved_change=text)
            self.assertEqual(self.mem.get(key), text)
        self.mem.correct("note.0", "Señor Pérez\u200d", "operator:fixed")
        self.assertEqual(self.mem.get("note.0"), "Señor Pérez\u200d")
        stored = {r["key"]: (r["value"], r["source"], r["approved_change"]) for r in self.rows() if not r["superseded_at"]}
        for i, text in enumerate(ACCEPTED[1:], 1):
            self.assertEqual(stored[f"note.{i}"], (text, f"owner-stated:{text}", text))

    def test_c0_and_delete_still_refused(self):
        for ch in ("\x00", "\n", "\x1f", "\x7f"):
            with self.subTest(ch=hex(ord(ch))), self.assertRaisesRegex(ValueError, "value must be"):
                self.mem.remember("pickup.day", f"a{ch}b", "fact", "operator:ok")
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
