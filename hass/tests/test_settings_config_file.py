"""RF1910-2 (H08/H20): conversation.load_settings reads config.json only as a regular, non-link file <= 1 MiB.

A FIFO or link at config.json is refused with one ConfigError naming no path, without blocking the service or
hass/health.py; a missing, malformed, deeply nested or non-UTF-8 file keeps the existing "settings are missing" error.
Temp 0700 state dirs only; nothing is written by the code under test."""
import contextlib, io, json, os, shutil, tempfile, threading, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import conversation, health
from hass.conversation import ConfigError, load_settings
from hass.tests import test_health as base

REFUSED, MISSING = "config.json must be a regular file up to 1 MiB", "config.json settings are missing"
MIB = 1024 * 1024
EXPECTED = {"ownerSenders": ("owner@example.invalid",), "ownerKeys": frozenset({"owner@example.invalid"}),
            "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600, "mediaRoot": None, "guestCountsDb": None,
            "interpreterDailyCap": None}


def in_thread(fn, timeout=5):
    """(finished, outcome): fn's return value or raised exception; a daemon thread so a hang cannot stall the run."""
    box = {}

    def run():
        try: box["out"] = fn()
        except BaseException as exc: box["out"] = exc  # noqa: BLE001 - the test inspects any outcome
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    return not worker.is_alive(), box.get("out")


class SettingsConfigFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        self.cfg = self.state / "config.json"
        self.valid = json.dumps({"worktree": str(self.tmp / "wt"), "settings": base.SETTINGS})

    def listing(self):
        return sorted((p.name, p.stat(follow_symlinks=False).st_size) for p in self.state.iterdir())

    def refused(self, expected):
        before = self.listing()
        with self.assertRaises(ConfigError) as ctx:
            load_settings(self.state)
        self.assertEqual(str(ctx.exception), expected)
        self.assertNotIn(str(self.tmp), str(ctx.exception))
        self.assertEqual(self.listing(), before)  # nothing written

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_fifo_is_refused_without_blocking(self):
        os.mkfifo(self.cfg, 0o600)
        finished, out = in_thread(lambda: load_settings(self.state))
        self.assertTrue(finished, "load_settings blocked on a FIFO")
        self.assertIsInstance(out, ConfigError)
        self.assertEqual(str(out), REFUSED)
        self.refused(REFUSED)

    def test_link_to_valid_config_is_refused(self):
        real = self.tmp / "elsewhere.json"
        real.write_text(self.valid)
        self.cfg.symlink_to(real)
        self.refused(REFUSED)

    def test_folder_is_refused(self):
        self.cfg.mkdir()
        self.refused(REFUSED)

    def test_missing_list_and_non_object_settings_keep_message(self):
        self.refused(MISSING)
        for text in ("[1, 2]", json.dumps({"settings": 1}), "{not json"):
            with self.subTest(text=text):
                self.cfg.write_text(text)
                self.refused(MISSING)

    def test_over_one_mib_is_refused(self):
        self.cfg.write_bytes(b" " * (MIB + 1))
        self.refused(REFUSED)

    def test_exactly_one_mib_valid_config_is_read(self):
        data = self.valid.encode()
        self.cfg.write_bytes(data + b" " * (MIB - len(data)))
        self.assertEqual(load_settings(self.state), EXPECTED)

    def test_growth_past_cap_after_lstat_is_refused(self):
        self.cfg.write_bytes(b" " * (MIB + 1))
        small = self.tmp / "small.json"
        small.write_text("{}")
        real_lstat = os.lstat
        with mock.patch.object(conversation.os, "lstat", lambda p, *a, **k: real_lstat(small)):
            self.refused(REFUSED)

    def test_deep_array_is_missing_not_recursion_error(self):
        self.cfg.write_text("[" * 100000 + "]" * 100000)
        self.refused(MISSING)

    def test_invalid_utf8_is_missing(self):
        self.cfg.write_bytes(b'{"settings": {"ownerChat": "\xff\xfe"}}')
        self.refused(MISSING)

    def test_valid_config_returns_same_dict(self):
        self.cfg.write_text(self.valid)
        self.assertEqual(load_settings(self.state), EXPECTED)

    def test_invalid_settings_messages_unchanged(self):
        self.cfg.write_text(json.dumps({"settings": dict(base.SETTINGS, approvalTtlSeconds=5)}))
        self.refused("approvalTtlSeconds must be an integer >= 60")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_health_with_fifo_config_reports_without_hanging(self):
        os.mkfifo(self.cfg, 0o600)
        out = io.StringIO()

        def run():
            with contextlib.redirect_stdout(out):
                return health.main(["--state", str(self.state)], now=base.NOW)
        finished, code = in_thread(run)
        self.assertTrue(finished, "health blocked on a FIFO config")
        self.assertEqual(code, 1)
        [line] = out.getvalue().splitlines()
        problems = json.loads(line)["problems"]
        self.assertIn({"check": "settings", "detail": REFUSED}, problems)
        self.assertNotIn(str(self.tmp), line)


if __name__ == "__main__":
    unittest.main()
