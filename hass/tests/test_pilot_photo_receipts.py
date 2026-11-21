"""Offline tests of the pilot photo receipt report."""

from contextlib import closing, redirect_stderr, redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hass.npp.job import SCHEMA as NPP_SCHEMA
from hass.relay_photos import RelayPhotos


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_photo_receipts.py"
SPEC = spec_from_file_location("pilot_photo_receipts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
GUID = "synthetic-target-guid"
OTHER = "synthetic-other-guid"
RETAKE = "synthetic-z-retake-guid"
TEXT_TURN = "synthetic-text-guid"
CODE = "synthetic-pilot-code"
OTHER_CODE = "synthetic-other-code"
TURN_MARKER = "synthetic-turn-metadata"
REFUSAL = "synthetic-refusal-marker"
BLOB = b"synthetic-unprinted-photo"
FIRST = "a" * 64
SECOND = "b" * 64
OTHER_DIGEST = "c" * 64


class PilotPhotoReceiptsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "synthetic ?# host"
        root.mkdir()
        RelayPhotos(root)
        self.path = root / "photos.sqlite3"
        self.conversation = root / "conversation.sqlite3"
        with closing(sqlite3.connect(self.conversation)) as db:
            db.executescript(NPP_SCHEMA)

    def seed_turns(self, *turns):
        with closing(sqlite3.connect(self.conversation)) as db, db:
            db.executemany("INSERT INTO npp_turns (provider_id, job_id, kind, accepted_at, receipt_refs) "
                           "VALUES (?, ?, 'fixture', '2000-01-01', ?)",
                           [(guid, code, TURN_MARKER) for guid, code in turns])

    def seed(self, rows):
        with closing(sqlite3.connect(self.path)) as db, db:
            # Seed receipts directly to represent inconsistent rows the writer rejects.
            db.executemany("INSERT INTO photo_receipt VALUES (?, ?, ?, ?, ?, ?)", rows)
            db.execute("INSERT INTO photo_in VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (GUID, 0, 2, FIRST, BLOB, None, 10))

    def invoke(self, *extra, code=None):
        target = (["--guid", GUID] if code is None else
                  ["--code", code, "--conversation-db", str(self.conversation)])
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = REPORT.main(["--photos-db", str(self.path), *target, *extra])
        output = stdout.getvalue() + stderr.getvalue()
        for private in (GUID, OTHER, RETAKE, TEXT_TURN, CODE, OTHER_CODE, REFUSAL, TURN_MARKER,
                        BLOB.decode(), self.path.name, self.conversation.name, OTHER_DIGEST[:12]):
            self.assertNotIn(private, output)
        return status, stdout.getvalue().splitlines(), stderr.getvalue()

    def seed_complete(self):
        self.seed([(GUID, 1, 2, SECOND, None, 11), (GUID, 0, 2, FIRST, None, 10),
                   (OTHER, 1, 4, OTHER_DIGEST, None, 12)])
        self.seed_turns((GUID, CODE), (TEXT_TURN, CODE), (OTHER, OTHER_CODE))

    def test_complete_metadata_only_in_index_order(self):
        # A query for private columns, a writable open, or an unscoped lookup fails this control.
        self.seed_complete()
        connect = sqlite3.connect
        reads = []

        def authorize(action, table, column, _schema, _trigger):
            if action == sqlite3.SQLITE_READ:
                reads.append((table, column))
                allowed = {"photo_receipt": {"guid", "idx", "count", "sha256", "received_at"},
                           "npp_turns": {"job_id", "provider_id"}}
                if column not in allowed.get(table, ()):
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        def guarded_connect(*args, **kwargs):
            db = connect(*args, **kwargs)
            with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                db.execute("CREATE TABLE must_not_write (x)")
            db.set_authorizer(authorize)
            return db

        with patch.object(REPORT.sqlite3, "connect", side_effect=guarded_connect):
            self.assertEqual(self.invoke(code=CODE),
                             (0, [f"0/2 {FIRST[:12]} 10", f"1/2 {SECOND[:12]} 11", "COMPLETE"], ""))
        self.assertIn(("npp_turns", "provider_id"), reads)
        self.assertIn(("photo_receipt", "sha256"), reads)

    def test_incomplete_reasons(self):
        # Length-only validation misses shifted indexes; other messages cannot fill gaps.
        for pairs, reason in (
            ([], "no-rows"),
            ([(0, 2)], "missing-index"),
            ([(0, 3), (2, 3)], "missing-index"),
            ([(1, 2), (2, 2)], "missing-index"),
            ([(0, 2), (1, 3)], "count-disagrees"),
        ):
            with self.subTest(pairs=pairs):
                self.seed([(GUID, i, n, FIRST, None, 10) for i, n in pairs]
                          + [(OTHER, 1, 2, OTHER_DIGEST, None, 11)])
                self.seed_turns((GUID, CODE), (OTHER, OTHER_CODE))
                status, lines, stderr = self.invoke(code=CODE)
                self.assertEqual((status, lines[-1], stderr), (1, f"INCOMPLETE {reason}", ""))
                self.assertEqual(len(lines), len(pairs) + 1)
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute("DELETE FROM photo_receipt")
                    db.execute("DELETE FROM photo_in")
                with closing(sqlite3.connect(self.conversation)) as db, db:
                    db.execute("DELETE FROM npp_turns")

    def test_full_output_and_expected_digest(self):
        # A match can occur after the first index; a prefix or another message is not a match.
        self.seed_complete()
        self.assertEqual(self.invoke("--full", "--expect-sha256", SECOND.upper(), code=CODE),
                         (0, [f"0/2 {FIRST} 10", f"1/2 {SECOND} 11", "COMPLETE"], ""))
        for digest in (OTHER_DIGEST, FIRST[:12] + SECOND[12:]):
            with self.subTest(digest=digest[:12]):
                status, lines, stderr = self.invoke("--expect-sha256", digest, code=CODE)
                self.assertEqual((status, lines[-2:], stderr), (1, ["COMPLETE", "EXPECTED-DIGEST-NOT-FOUND"], ""))
                self.assertNotIn(digest, "\n".join(lines))

    def test_unknown_code_is_not_a_photo_guid_or_a_receipt_code(self):
        # A shortcut via either photo column would falsely find this unknown job.
        self.seed([(CODE, 0, 1, FIRST, CODE, 10)])
        self.seed_turns((GUID, OTHER_CODE))
        self.assertEqual(self.invoke(code=CODE), (1, ["INCOMPLETE unknown-code"], ""))

    def test_messages_cannot_fill_each_others_missing_indexes(self):
        # Pooling two turns produces a falsely complete 0..1 set, even with the expected digest.
        self.seed([(GUID, 0, 2, FIRST, None, 10), (RETAKE, 1, 2, SECOND, None, 11)])
        self.seed_turns((RETAKE, CODE), (GUID, CODE))
        self.assertEqual(self.invoke("--expect-sha256", SECOND, code=CODE),
                         (1, ["Message 1: INCOMPLETE missing-index", f"0/2 {FIRST[:12]} 10",
                              "Message 2: INCOMPLETE missing-index", f"1/2 {SECOND[:12]} 11",
                              "INCOMPLETE missing-index"], ""))

    def test_complete_messages_can_have_different_counts(self):
        # A retake's count belongs to that message, and its digest can satisfy the job-wide expectation.
        self.seed_complete()
        self.seed_turns((RETAKE, CODE))
        retake_digest = "d" * 64
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO photo_receipt VALUES (?, 0, 1, ?, NULL, 13)", (RETAKE, retake_digest))
        self.assertEqual(self.invoke("--expect-sha256", retake_digest, code=CODE),
                         (0, ["Message 1: COMPLETE", f"0/2 {FIRST[:12]} 10", f"1/2 {SECOND[:12]} 11",
                              "Message 2: COMPLETE", f"0/1 {retake_digest[:12]} 13", "COMPLETE"], ""))

    def test_refusal_has_no_digest(self):
        # The receipt index can exist without a photo. Don't print the refusal code.
        self.seed([(GUID, 0, 1, None, REFUSAL, 10)])
        self.assertEqual(self.invoke("--expect-sha256", FIRST),
                         (1, ["0/1 - 10", "COMPLETE", "EXPECTED-DIGEST-NOT-FOUND"], ""))

    def test_missing_store_stays_missing(self):
        # A default sqlite3 connection could create a store or report its private path.
        self.path = self.path.with_name("missing.sqlite3")
        self.assertEqual(self.invoke(), (1, [], "error: could not read photo receipts\n"))
        self.assertFalse(self.path.exists())
        self.conversation = self.conversation.with_name("missing-conversation.sqlite3")
        self.assertEqual(self.invoke(code=CODE), (1, [], "error: could not read conversation turns\n"))
        self.assertFalse(self.conversation.exists())
