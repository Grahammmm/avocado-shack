"""RF1920-9 (H19): health --seen reads the stored fingerprint with one O_NOFOLLOW|O_NONBLOCK open of at most 128 bytes.

A link, FIFO or oversize file swapped in after _seen_path counts as changed (notify) and is replaced; never a hang or a
followed link. Temp 0700 state dirs and seen folders outside the repo, as test_health_seen.py. Never the real state.
"""
import contextlib, io, json, os, shutil, stat, tempfile, threading, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

from hass import health

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}
DIGEST = health.fingerprint([])


class HealthSeenReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.folder, self.other = self.tmp / "state", self.tmp / "seendir", self.tmp / "other"
        for d in (self.state, self.folder, self.other): d.mkdir(mode=0o700)
        self.seen = self.folder / "fp-health"
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))

    def remember(self, digest=DIGEST):  # _seen_path ran on the earlier entry; _remember must return within 5 s
        result, done = [], threading.Event()
        def run():
            with contextlib.suppress(BaseException): result.append(health._remember(self.seen, digest))
            done.set()
        threading.Thread(target=run, daemon=True).start()
        if not done.wait(5):
            with contextlib.suppress(OSError): os.close(os.open(self.seen, os.O_WRONLY | os.O_NONBLOCK))  # unhang it
            self.fail("_remember did not return within 5 s")
        self.assertEqual(len(result), 1, "_remember raised")
        return result[0]

    def checked(self):  # the swap happens after the start-of-run checks accepted a regular file
        self.seen.write_text("0" * 64 + "\n")
        self.assertEqual(health._seen_path(str(self.seen), str(self.state)), self.seen.resolve())
        self.seen.unlink()

    def assert_record(self):
        st = os.lstat(self.seen)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        self.assertEqual(self.seen.read_bytes(), (DIGEST + "\n").encode())
        self.assertEqual(os.listdir(self.folder), [self.seen.name])  # no temp left, nothing else written

    def test_symlink_swapped_in_is_a_change_and_never_followed(self):
        self.checked()
        target = self.other / "target"
        target.write_text(DIGEST + "\n")
        os.utime(target, ns=(1_000_000_000, 1_000_000_000))
        before = (target.read_bytes(), os.stat(target).st_mtime_ns)
        self.seen.symlink_to(target)
        self.assertIs(self.remember(), True)
        self.assertEqual((target.read_bytes(), os.stat(target).st_mtime_ns), before)
        self.assertEqual(os.listdir(self.other), ["target"])
        self.assert_record()

    def test_dangling_symlink_is_a_change_and_never_followed(self):
        self.checked()
        self.seen.symlink_to(self.other / "missing")
        self.assertIs(self.remember(), True)
        self.assertEqual(os.listdir(self.other), [])
        self.assert_record()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_fifo_swapped_in_is_a_change_never_a_hang(self):
        self.checked()
        os.mkfifo(self.seen, 0o600)
        self.assertIs(self.remember(), True)
        self.assert_record()

    def test_huge_file_is_a_change(self):
        with open(self.seen, "wb") as fh:
            fh.write((DIGEST + "\n").encode())
            fh.truncate(10 * 2**20)  # 10 MB whose first line is the digest
        self.assertIs(self.remember(), True)
        self.assert_record()

    def test_128_bytes_is_read_129_is_a_change(self):
        self.seen.write_bytes((DIGEST + "\n").encode().ljust(128, b" "))
        os.utime(self.seen, ns=(1_000_000_000, 1_000_000_000))
        self.assertIs(self.remember(), False)
        self.assertEqual(os.stat(self.seen).st_mtime_ns, 1_000_000_000)
        self.seen.write_bytes((DIGEST + "\n").encode().ljust(129, b" "))
        self.assertIs(self.remember(), True)
        self.assert_record()

    def test_same_digest_untouched_different_digest_rewritten(self):
        self.seen.write_text(DIGEST + "\n")
        os.chmod(self.seen, 0o600)
        os.utime(self.seen, ns=(1_000_000_000, 1_000_000_000))
        self.assertIs(self.remember(), False)
        self.assertEqual(os.stat(self.seen).st_mtime_ns, 1_000_000_000)
        self.assertIs(self.remember("1" * 64), True)
        self.assertEqual(self.seen.read_text(), "1" * 64 + "\n")
        self.assertIs(self.remember(), True)
        self.assert_record()

    def test_missing_and_non_utf8_are_a_change(self):
        self.assertIs(self.remember(), True)
        self.assert_record()
        self.seen.write_bytes(b"\xff" * 64)
        self.assertIs(self.remember(), True)
        self.assert_record()

    def run_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state), "--seen", str(self.seen)], now=NOW)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        return code, lines[0]

    def test_cli_clean_state_two_runs_as_before(self):
        doc = {"fingerprint": DIGEST, "info": [{"check": "conversation", "detail": "no conversation yet"}], "ok": True,
               "problems": []}  # main's clean-state line
        first, second = self.run_cli(), self.run_cli()
        self.assertEqual(first, (0, json.dumps({**doc, "notify": True}, sort_keys=True)))
        self.assertEqual(second, (0, json.dumps({**doc, "notify": False}, sort_keys=True)))
        self.assert_record()


if __name__ == "__main__":
    unittest.main()
