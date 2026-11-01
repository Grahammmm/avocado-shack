"""RF1650-2 (H15): an `owner-approved:<change id>` memory source must name a change whose record in the same state dir
is applied and not undone. Any other id is the same "unverified source" and writes nothing. Temp state dirs only.
Run: python3 -B -m unittest hass.tests.test_memory_source -v
"""

import contextlib, json, os, sqlite3, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import memory
from hass.tests.test_memory import Clock

APPLIED, FAILED, UNDONE, OTHER = "chg-0000000000a1", "chg-0000000000f1", "chg-0000000000d1", "chg-0000000000a2"


class SourceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.mem = memory.Memory(str(self.state), Clock())
        self.addCleanup(self.mem.close)
        self.changes = self.state / "changes"
        self.changes.mkdir(mode=0o700)
        for cid, rec in ((APPLIED, {"state": "applied"}), (OTHER, {"state": "applied"}), (FAILED, {"state": "failed"}),
                         (UNDONE, {"state": "applied", "revertedBy": "chg-0000000000e1"})):
            self.record(cid, json.dumps(rec))

    def record(self, cid, text):
        (self.changes / f"{cid}.json").write_text(text, "utf-8")

    def rows(self):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM memory ORDER BY id")]

    def refused(self, cid, problem, mem=None):
        mem = mem or self.mem
        before = self.rows()
        self.assertEqual(mem._approved_problem(cid), problem)
        with self.assertRaisesRegex(ValueError, "^unverified source$"):
            mem.remember("pickup.day", "Saturday", "fact", f"owner-approved:{cid}")
        self.assertEqual(self.rows(), before)

    def test_applied_change_is_accepted_and_recorded(self):
        self.mem.remember("pickup.day", "Saturday", "fact", f"owner-approved:{APPLIED}")
        row, = self.rows()
        self.assertEqual((row["source"], row["approved_change"]), (f"owner-approved:{APPLIED}", APPLIED))
        self.assertIsNone(self.mem._approved_problem(APPLIED))

    def test_unknown_failed_and_undone_changes_are_refused(self):
        self.refused("chg-0123456789ab", "no such change")
        self.refused(FAILED, "not applied")
        self.refused(UNDONE, "undone")
        self.assertEqual(self.mem.list(), [])

    def test_malformed_id_is_refused_before_any_file_read(self):
        with mock.patch.object(Path, "lstat", side_effect=AssertionError("path read")), \
                mock.patch.object(memory.os, "open", side_effect=AssertionError("file opened")):
            for cid in ("chg-xyz", "../changes/x", f"../changes/{APPLIED}", APPLIED.upper(), APPLIED + "0",
                        f" {APPLIED}", "chg-1", "c-1"):
                with self.subTest(cid=cid):
                    self.refused(cid, "malformed id")

    def test_symlink_unreadable_and_odd_records_are_refused(self):
        (self.changes / "chg-00000000005e.json").symlink_to(self.changes / f"{APPLIED}.json")
        self.refused("chg-00000000005e", "no such change")
        (self.changes / "chg-0000000000d0.json").mkdir()
        self.refused("chg-0000000000d0", "no such change")
        for cid, text in (("chg-0000000000b1", "{not json"), ("chg-0000000000b2", "[]"),
                          ("chg-0000000000b3", '"applied"'), ("chg-0000000000b4", "[" * 100000)):
            with self.subTest(cid=cid):
                self.record(cid, text)
                self.refused(cid, "unreadable change")
        (self.changes / "chg-0000000000b5.json").write_bytes(b'{"state": "applied", "x": "\xff"}')
        self.refused("chg-0000000000b5", "unreadable change")
        self.record("chg-0000000000b6", json.dumps({"state": "applied"}))
        os.chmod(self.changes / "chg-0000000000b6.json", 0)
        if os.access(self.changes / "chg-0000000000b6.json", os.R_OK): self.skipTest("running as root")
        self.refused("chg-0000000000b6", "unreadable change")

    def test_symlinked_changes_dir_is_refused(self):
        other = self.state.parent / "elsewhere"
        self.changes.rename(other)
        self.changes.symlink_to(other)
        self.refused(APPLIED, "no such change")

    def test_shared_connection_needs_a_state_dir_for_approved_sources(self):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3", isolation_level=None)) as db:
            db.row_factory = sqlite3.Row
            bare = memory.Memory.on_connection(db, Clock())
            self.refused(APPLIED, "no state dir", bare)
            bare.remember("tone", "short", "preference", "owner-stated:msg-1")
            bare.remember("hours", "9-5", "fact", "operator:onboarding")
            with self.assertRaisesRegex(ValueError, "unverified source"):
                bare.correct("tone", "warm", f"owner-approved:{APPLIED}")
            self.assertEqual(bare.get("tone"), "short")
            scoped = memory.Memory.on_connection(db, Clock(), str(self.state))
            scoped.remember("pickup.day", "Saturday", "fact", f"owner-approved:{APPLIED}")
            self.assertEqual(scoped.get("pickup.day"), "Saturday")

    def test_correct_with_approved_source_records_the_id_and_keeps_history(self):
        self.mem.remember("pickup.day", "Saturday", "fact", "owner-stated:msg-1")
        for cid in ("chg-0123456789ab", FAILED, UNDONE, "chg-xyz"):
            with self.subTest(cid=cid), self.assertRaisesRegex(ValueError, "^unverified source$"):
                self.mem.correct("pickup.day", "Sunday", f"owner-approved:{cid}")
        self.assertEqual([(r["value"], r["superseded_at"]) for r in self.rows()], [("Saturday", None)])
        self.mem.correct("pickup.day", "Sunday", f"owner-approved:{APPLIED}")
        self.mem.correct("pickup.day", "Monday", "operator:typo")
        old, mid, new = self.rows()
        self.assertEqual([(r["value"], r["approved_change"]) for r in (old, mid, new)],
                         [("Saturday", None), ("Sunday", APPLIED), ("Monday", None)])
        self.assertTrue(old["superseded_at"] and mid["superseded_at"] and new["superseded_at"] is None)

    def test_explicit_approved_change_must_match_the_source(self):
        for other in (OTHER, "chg-1", f"{APPLIED} "):
            with self.subTest(other=other), self.assertRaisesRegex(ValueError, "approved_change does not match"):
                self.mem.remember("pickup.day", "Saturday", "fact", f"owner-approved:{APPLIED}", approved_change=other)
        self.assertEqual(self.rows(), [])
        self.mem.remember("pickup.day", "Saturday", "fact", f"owner-approved:{APPLIED}", approved_change=APPLIED)
        self.assertEqual(self.rows()[0]["approved_change"], APPLIED)

    def test_key_errors_come_before_the_approval_check(self):
        self.mem.remember("pickup.day", "Saturday", "fact", "operator:n")
        with self.assertRaisesRegex(ValueError, "use correct"):  # names no record, but the key is already stored
            self.mem.remember("pickup.day", "Sunday", "fact", "owner-approved:chg-0123456789ab")
        with self.assertRaises(KeyError):
            self.mem.correct("missing", "x", "owner-approved:chg-0123456789ab")
        self.assertEqual(len(self.rows()), 1)


if __name__ == "__main__":
    unittest.main()
