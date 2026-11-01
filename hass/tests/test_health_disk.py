"""AV1737-14 (H19): `health.py --min-free-mb MB` reports `disk-low` (temp dirs, a fake os.statvfs keyed by dir)."""
import contextlib, io, json, os, tempfile, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import health

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}
MB = 2**20


def low(label, n): return {"check": "disk-low", "detail": f"{label}: {n} MB free"}  # noqa: E704


class HealthDiskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.state, self.backups, self.seen = self.tmp / "state", self.tmp / "backups", self.tmp / "fp-health"
        for d in (self.state, self.backups): d.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))
        self.free, self.calls = {"state": 10_000, "backups": 10_000}, []  # MB available per dir; or an exception

    def fake_statvfs(self, path):
        label = {self.state.resolve(): "state", self.backups.resolve(): "backups"}[Path(path).resolve()]
        self.calls.append(label)
        if isinstance(value := self.free[label], Exception): raise value
        return SimpleNamespace(f_frsize=4096, f_bavail=(value * MB + 1000) // 4096)  # a little over n MB

    def run_health(self, *extra, fake=True):
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            if fake: stack.enter_context(mock.patch("os.statvfs", self.fake_statvfs))
            stack.enter_context(contextlib.redirect_stdout(out))
            code = health.main(["--state", str(self.state), *extra], now=NOW)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertNotIn(str(self.tmp), lines[0])  # never a path
        return code, json.loads(lines[0]), lines[0]

    def disk(self, doc): return [p for p in doc["problems"] if p["check"] == "disk-low"]  # noqa: E704

    def test_state_low_is_one_problem_without_path(self):
        self.free["state"] = 120
        code, doc, _ = self.run_health("--min-free-mb", "500")
        self.assertEqual((code, doc["ok"], doc["problems"]), (1, False, [low("state", 100)]))

    def test_backups_low_alone_and_both_low(self):
        backups = ("--backups", str(self.backups), "--min-free-mb", "500")
        self.free["backups"] = 260
        code, doc, _ = self.run_health(*backups)
        self.assertEqual((code, self.disk(doc)), (1, [low("backups", 250)]))
        self.free["state"] = 75
        first = self.run_health(*backups)[1]
        self.assertEqual(sorted(map(str, self.disk(first))), sorted(map(str, [low("state", 50), low("backups", 250)])))
        self.assertEqual(first["fingerprint"], health.fingerprint(list(reversed(first["problems"]))))
        self.assertEqual(self.run_health(*backups)[1]["fingerprint"], first["fingerprint"])

    def test_boundary_is_strictly_under_the_floor(self):
        for free, floor, want in ((500, "500", []), (501, "500", []), (499, "500", [low("state", 450)]),
                                  (0, "1", [low("state", 0)]), (1, "1", [])):
            with self.subTest(free=free, floor=floor):
                self.free["state"] = free
                code, doc, _ = self.run_health("--min-free-mb", floor)
                self.assertEqual((code, doc["problems"]), (1 if want else 0, want))

    def test_seen_notifies_only_when_the_50_mb_bucket_changes(self):
        args = ("--min-free-mb", "500", "--seen", str(self.seen))
        self.free["state"] = 120
        first = self.run_health(*args)[1]
        self.assertTrue(first["notify"])
        self.free["state"] = 140  # same bucket: same detail, no new alert
        same = self.run_health(*args)[1]
        self.assertEqual((same["notify"], same["fingerprint"]), (False, first["fingerprint"]))
        self.free["state"] = 60
        lower = self.run_health(*args)[1]
        self.assertEqual((lower["notify"], self.disk(lower)), (True, [low("state", 50)]))
        self.assertNotEqual(lower["fingerprint"], first["fingerprint"])
        self.assertEqual(self.seen.read_text("utf-8").strip(), lower["fingerprint"])

    def test_unreadable_free_space_is_a_problem_not_a_traceback(self):
        self.free["state"] = PermissionError(13, "denied", str(self.state))
        self.free["backups"] = OSError(5, "io error", str(self.backups))
        code, doc, _ = self.run_health("--min-free-mb", "500", "--backups", str(self.backups))
        want = [{"check": "disk-low", "detail": f"{s}: free space unreadable"} for s in ("state", "backups")]
        self.assertEqual((code, self.disk(doc)), (1, want))

    def test_real_statvfs_reports_counted_mb(self):
        code, doc, _ = self.run_health("--min-free-mb", str(10**12), fake=False)
        self.assertEqual(code, 1)
        self.assertRegex(self.disk(doc)[0]["detail"], r"^state: (\d*[05]0|0) MB free$")  # a 50-MB bucket

    def test_without_flag_output_is_unchanged_and_statvfs_unused(self):
        self.free["state"] = self.free["backups"] = 1
        plain = self.run_health("--backups", str(self.backups))
        self.assertEqual(self.calls, [])
        with mock.patch("os.statvfs", self.fake_statvfs):
            self.assertEqual(health.check(self.state, now=NOW), health.check(self.state, now=NOW, min_free_mb=None))
        self.free["state"] = self.free["backups"] = 10_000  # ample space: the line is byte-identical
        self.assertEqual(self.run_health("--backups", str(self.backups), "--min-free-mb", "500"), plain)
        self.assertEqual(sorted(self.calls), ["backups", "state"])

    def test_floor_below_one_or_not_a_number_is_a_usage_error(self):
        for bad in ("0", "-5", "lots", "1.5"):
            with self.subTest(bad=bad), mock.patch("os.statvfs", self.fake_statvfs):
                out, err, argv = io.StringIO(), io.StringIO(), ["--state", str(self.state), "--min-free-mb", bad]
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    with self.assertRaises(SystemExit) as cm: health.main(argv, now=NOW)
                self.assertEqual((cm.exception.code, out.getvalue(), self.calls), (2, "", []))
                self.assertIn("--min-free-mb", err.getvalue())

    def test_unsafe_state_never_reads_free_space(self):
        os.symlink(self.state, link := self.tmp / "state-link")
        self.free["state"], self.state = 1, link
        code, doc, _ = self.run_health("--min-free-mb", "500", "--backups", str(self.backups))
        self.assertEqual((code, [p["check"] for p in doc["problems"]], self.calls), (2, ["state"], []))

    def test_missing_or_non_dir_backups_get_no_disk_problem(self):
        self.free["backups"] = 1
        (afile := self.tmp / "afile").write_text("x")
        for target in (self.tmp / "nope", afile):
            with self.subTest(target=target.name):
                code, doc, _ = self.run_health("--min-free-mb", "500", "--backups", str(target))
                self.assertEqual((code, self.disk(doc)), (1, []))
                self.assertIn("backup-age", [p["check"] for p in doc["problems"]])
        self.assertNotIn("backups", self.calls)
        self.assertFalse(os.path.lexists(self.tmp / "nope"))
