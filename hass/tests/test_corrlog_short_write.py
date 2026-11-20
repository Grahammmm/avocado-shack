"""Exercise correspondence-log appends against real files with fixture write faults."""
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from hass import corrlog


class ShortWrites(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        self.now = datetime(2026, 11, 16, 20, tzinfo=timezone.utc)
        self.log = corrlog.CorrLog(state.name, lambda: self.now)
        self.path = self.log.dir / f"{self.now:%Y-%m-%d}.jsonl"

    def reasons(self):
        return [row["reason"] for row in self.log.rows()]

    def test_short_writes_finish_one_row_before_the_next_append(self):
        # Ignoring a partial count loses this row and merges it with the next.
        real_write = corrlog.os.write
        limits = iter((10, 5))

        def short_then_finish(fd, data):
            return real_write(fd, data[:next(limits, None)])

        with mock.patch.object(corrlog.os, "write", side_effect=short_then_finish):
            self.assertTrue(self.log.record("error", "first"))
        self.assertTrue(self.log.record("error", "second"))
        self.assertEqual(self.reasons(), ["first", "second"])
        self.assertTrue(self.path.read_bytes().endswith(b"\n"))

    def test_zero_progress_returns_false_without_retrying(self):
        # A stalled write must neither report success nor retry indefinitely.
        with mock.patch.object(corrlog.os, "write", side_effect=[0, OSError]) as write:
            self.assertFalse(self.log.record("error", "stalled"))
        self.assertEqual(write.call_count, 1)

    def test_write_error_returns_false(self):
        # Errors at the write boundary must remain best effort, not escape.
        with mock.patch.object(corrlog.os, "write", side_effect=OSError):
            self.assertFalse(self.log.record("error", "failed"))
