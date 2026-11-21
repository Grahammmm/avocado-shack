"""Offline tests of the message-level photo receipt report."""

from contextlib import closing, redirect_stderr, redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from hass.relay_photos import RelayPhotos


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_photo_receipts.py"
SPEC = spec_from_file_location("pilot_photo_receipts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
GUID = "synthetic-target-guid"
OTHER = "synthetic-other-guid"
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

    def seed(self, rows):
        with closing(sqlite3.connect(self.path)) as db, db:
            # Seed receipts directly to represent inconsistent rows the writer rejects.
            db.executemany("INSERT INTO photo_receipt VALUES (?, ?, ?, ?, ?, ?)", rows)
            db.execute("INSERT INTO photo_in VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (GUID, 0, 2, FIRST, BLOB, None, 10))

    def invoke(self, *extra, guid=GUID):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = REPORT.main(["--photos-db", str(self.path), "--guid", guid, *extra])
        output = stdout.getvalue() + stderr.getvalue()
        for private in (GUID, OTHER, REFUSAL, BLOB.decode(), self.path.name, OTHER_DIGEST[:12]):
            self.assertNotIn(private, output)
        return status, stdout.getvalue().splitlines(), stderr.getvalue()

    def seed_complete(self):
        self.seed([(GUID, 1, 2, SECOND, None, 11), (GUID, 0, 2, FIRST, None, 10),
                   (OTHER, 1, 4, OTHER_DIGEST, None, 12)])

    def test_complete_metadata_only_in_index_order(self):
        # A photo_in query, SELECT *, writable open, or an unscoped query fails this control.
        self.seed_complete()
        connect = sqlite3.connect
        reads = []

        def authorize(action, table, column, _schema, _trigger):
            if action == sqlite3.SQLITE_READ:
                reads.append((table, column))
                if table != "photo_receipt" or column not in {"guid", "idx", "count", "sha256", "received_at"}:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        def guarded_connect(*args, **kwargs):
            db = connect(*args, **kwargs)
            with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                db.execute("CREATE TABLE must_not_write (x)")
            db.set_authorizer(authorize)
            return db

        with patch.object(REPORT.sqlite3, "connect", side_effect=guarded_connect):
            self.assertEqual(self.invoke(), (0, [f"0/2 {FIRST[:12]} 10", f"1/2 {SECOND[:12]} 11", "COMPLETE"], ""))
        self.assertTrue(reads)

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
                status, lines, stderr = self.invoke()
                self.assertEqual((status, lines[-1], stderr), (1, f"INCOMPLETE {reason}", ""))
                self.assertEqual(len(lines), len(pairs) + 1)
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute("DELETE FROM photo_receipt")
                    db.execute("DELETE FROM photo_in")

    def test_full_output_and_expected_digest(self):
        # A match can occur after the first index; a prefix or another message is not a match.
        self.seed_complete()
        self.assertEqual(self.invoke("--full", "--expect-sha256", SECOND.upper()),
                         (0, [f"0/2 {FIRST} 10", f"1/2 {SECOND} 11", "COMPLETE"], ""))
        for digest in (OTHER_DIGEST, FIRST[:12] + SECOND[12:]):
            with self.subTest(digest=digest[:12]):
                status, lines, stderr = self.invoke("--expect-sha256", digest)
                self.assertEqual((status, lines[-2:], stderr), (1, ["COMPLETE", "EXPECTED-DIGEST-NOT-FOUND"], ""))
                self.assertNotIn(digest, "\n".join(lines))

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
