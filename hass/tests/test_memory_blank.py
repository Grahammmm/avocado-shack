"""RF0200-9 (H15): the memory store refuses a whitespace-only value and a source with no detail after its prefix.
Nothing is trimmed or normalised; a refusal writes, supersedes and dates nothing. Temp state dirs only.
Run: python3 -B -m unittest hass.tests.test_memory_blank -v
"""

import contextlib, sqlite3, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import memory
from hass.tests.test_memory import Clock

BLANKS = (" ", "   ", "\u00a0", "\u3000", " \u00a0\u3000 ", "\u2003\u2009", "\u1680\u202f\u205f")
VALUE_REFUSAL, SOURCE_REFUSAL = "^value must be 1-500 plain characters$", "^unverified source$"


class BlankTests(unittest.TestCase):
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

    def test_remember_rejects_blank_values_without_clock_or_rows(self):
        for value in BLANKS:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, VALUE_REFUSAL):
                self.mem.remember("hours", value, "fact", "operator:ok")
        self.assertEqual((self.rows(), self.clock.calls), ([], 0))

    def test_correct_blank_keeps_active_and_history(self):
        self.mem.remember("hours", "Closed Mondays", "fact", "operator:ok")
        self.mem.correct("hours", "Closed Tuesdays", "owner-stated:msg-2")
        before, calls = self.rows(), self.clock.calls
        for value in BLANKS:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, VALUE_REFUSAL):
                self.mem.correct("hours", value, "owner-stated:msg-3")
        self.assertEqual((self.rows(), self.clock.calls, self.mem.get("hours")), (before, calls, "Closed Tuesdays"))
        self.assertFalse(self.mem.db.in_transaction)
        self.mem.correct("hours", "Closed Wednesdays", "owner-stated:msg-4")  # the store still works afterwards
        self.assertEqual(self.mem.get("hours"), "Closed Wednesdays")

    def test_source_detail_requires_nonblank_text(self):
        self.mem.remember("hours", "Closed Mondays", "fact", "operator:ok")
        before, calls = self.rows(), self.clock.calls
        for prefix in ("owner-stated:", "operator:", "owner-approved:"):
            for detail in ("",) + BLANKS:
                source = prefix + detail
                with self.subTest(source=source):
                    with self.assertRaisesRegex(ValueError, SOURCE_REFUSAL):  # exact text: the source is not echoed
                        self.mem.remember("tone", "short", "preference", source)
                    with self.assertRaisesRegex(ValueError, SOURCE_REFUSAL):
                        self.mem.correct("hours", "Closed Tuesdays", source)
        self.assertEqual((self.rows(), self.clock.calls), (before, calls))

    def test_substantive_padding_and_unicode_are_preserved(self):
        values = {"padded": "  Saturday  ", "persian": "می\u200cخواهم", "emoji": "\U0001F468\u200d\U0001F469\u200d\U0001F467",
                  "punct": "...", "max": "x" * 500, "nbsp": "\u00a0open\u3000"}
        for key, value in values.items():
            self.mem.remember(key, value, "fact", "operator:  padded note  ")
        self.assertEqual({r["key"]: r["value"] for r in self.rows()}, values)
        self.assertEqual({r["source"] for r in self.rows()}, {"operator:  padded note  "})
        self.mem.correct("padded", "\u3000Sunday ", "owner-stated:\u00a0msg-1\u00a0")
        self.assertEqual(self.mem.get("padded"), "\u3000Sunday ")
        self.assertEqual(self.rows()[-1]["source"], "owner-stated:\u00a0msg-1\u00a0")
        with self.assertRaisesRegex(ValueError, VALUE_REFUSAL):
            self.mem.remember("long", "x" * 501, "fact", "operator:ok")
        with self.assertRaisesRegex(ValueError, SOURCE_REFUSAL):
            self.mem.remember("long", "x", "fact", "operator:" + "y" * 500)

    def test_shared_connection_refusal_preserves_outer_transaction(self):
        db = sqlite3.connect(self.state / "conversation.sqlite3", isolation_level=None)
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        shared = memory.Memory.on_connection(db, self.clock)
        shared.remember("hours", "Closed Mondays", "fact", "operator:ok")
        db.execute("CREATE TABLE pending(x TEXT)")
        db.execute("BEGIN")
        db.execute("INSERT INTO pending VALUES ('kept')")
        before, calls = self.rows(), self.clock.calls
        for value in BLANKS:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, VALUE_REFUSAL):
                shared.remember("tone", value, "preference", "operator:ok")
            with self.assertRaisesRegex(ValueError, VALUE_REFUSAL):
                shared.correct("hours", value, "operator:ok")
        for source in ("operator:", "owner-stated:\u3000", "owner-approved: "):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, SOURCE_REFUSAL):
                shared.remember("tone", "short", "preference", source)
            with self.assertRaisesRegex(ValueError, SOURCE_REFUSAL):
                shared.correct("hours", "Closed Tuesdays", source)
        self.assertTrue(db.in_transaction)
        self.assertEqual((self.clock.calls, db.execute("SELECT x FROM pending").fetchall()[0]["x"]), (calls, "kept"))
        shared.remember("tone", "short", "preference", "operator:ok")  # caller continues in its own transaction
        db.execute("COMMIT")
        self.assertEqual([(r["key"], r["value"]) for r in self.rows()], [(r["key"], r["value"]) for r in before]
                         + [("tone", "short")])
        self.assertEqual(shared.get("hours"), "Closed Mondays")
        self.assertEqual(shared.get("tone"), "short")


if __name__ == "__main__":
    unittest.main()
