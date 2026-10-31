"""RF1105-11 (H19): health still prints its one JSON line when the --seen file cannot be written; notify is forced.

Temp 0700 state dirs and seen folders outside the repo, placeholder rows, an injected clock. Never the real state.
"""
import contextlib, errno, io, json, os, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import conversation, health

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}
SEEN_INFO = {"check": "seen", "detail": "seen file not updated"}


class HealthSeenWriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.folder = self.tmp / "state", self.tmp / "seendir"
        self.state.mkdir(mode=0o700)
        self.folder.mkdir(mode=0o700)
        self.seen = self.folder / "fp-health"
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))

    def stuck_outbox(self):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            db.executescript(conversation.SCHEMA)
            db.execute("INSERT INTO outbox(chat, text, attachments, created_at, sent_at) VALUES ('c', 't', '[]', ?, NULL)",
                       ((NOW - timedelta(minutes=30)).isoformat(timespec="seconds"),))

    def run_health(self, seen=True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state), *(["--seen", str(self.seen)] if seen else [])], now=NOW)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)  # exactly one JSON line
        return code, json.loads(lines[0]), lines[0]

    def assert_forced(self, failing):
        base_code, base, _ = self.run_health(seen=False)
        with failing:
            code, doc, line = self.run_health()
        self.assertEqual(code, base_code)
        self.assertTrue(doc["notify"])
        self.assertIn(SEEN_INFO, doc["info"])
        self.assertEqual([i for i in doc["info"] if i != SEEN_INFO], base["info"])
        self.assertEqual((doc["ok"], doc["problems"], doc["fingerprint"]), (base["ok"], base["problems"], base["fingerprint"]))
        for value in (str(self.seen), str(self.folder), self.seen.name):  # value-free detail
            self.assertNotIn(value, line)
        return code, doc

    def no_temp(self):
        self.assertEqual([n for n in os.listdir(self.folder) if n.startswith(f".{self.seen.name}.")], [])

    def test_mkstemp_fails(self):
        self.assert_forced(mock.patch("hass.health.tempfile.mkstemp", side_effect=OSError(errno.ENOSPC, "full")))
        self.assertFalse(self.seen.exists())

    def test_replace_fails_leaves_no_temp(self):
        self.assert_forced(mock.patch("hass.health.os.replace", side_effect=OSError(errno.ENOSPC, "full")))
        self.no_temp()
        self.assertFalse(self.seen.exists())

    def test_write_fails_leaves_no_temp(self):
        self.assert_forced(mock.patch("hass.health.os.fdopen", side_effect=OSError(errno.EIO, "io")))
        self.no_temp()

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores folder modes")
    def test_read_only_folder(self):
        self.folder.chmod(0o500)
        self.addCleanup(self.folder.chmod, 0o700)
        self.assert_forced(contextlib.nullcontext())
        self.assertEqual(os.listdir(self.folder), [])

    def test_stale_record_and_write_failure_still_alerts(self):
        self.seen.write_text("0" * 64 + "\n")  # a record that differs, folder then unwritable
        self.assert_forced(mock.patch("hass.health.os.replace", side_effect=OSError(errno.EROFS, "ro")))
        self.assertEqual(self.seen.read_text(), "0" * 64 + "\n")

    def test_healthy_state_write_failure(self):
        code, doc = self.assert_forced(mock.patch("hass.health.os.replace", side_effect=OSError(errno.ENOSPC, "full")))
        self.assertEqual((code, doc["ok"], doc["problems"]), (0, True, []))
        self.assertEqual(doc["fingerprint"], health.fingerprint([]))

    def test_problem_state_write_failure(self):
        self.stuck_outbox()
        code, doc = self.assert_forced(mock.patch("hass.health.tempfile.mkstemp", side_effect=OSError(errno.ENOSPC, "x")))
        self.assertEqual((code, doc["ok"], doc["problems"]), (1, False, [{"check": "outbox-stuck", "detail": "1"}]))
        self.assertNotIn(SEEN_INFO, doc["problems"])

    def test_normal_seen_unchanged(self):
        first, second = self.run_health(), self.run_health()
        self.assertEqual(([first[1]["notify"], second[1]["notify"]], first[0], second[0]), ([True, False], 0, 0))
        self.stuck_outbox()
        runs = [self.run_health() for _ in range(2)]
        self.assertEqual([(c, d["notify"]) for c, d, _ in runs], [(1, True), (1, False)])
        for _, doc, _ in (first, second, *runs):
            self.assertNotIn(SEEN_INFO, doc["info"])
        self.assertEqual(self.seen.read_text().strip(), runs[0][1]["fingerprint"])
        self.no_temp()

    def test_other_errors_are_not_swallowed(self):
        with mock.patch("hass.health.os.replace", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.run_health()
        self.no_temp()
