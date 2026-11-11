"""RF0111-11: an OS-level failure launching ``git show`` for a design blob is the fixed private usage refusal.

A forwarding spy delegates every command to real local Git and raises only at the selected ``git show`` launch, so
_read_blob itself is exercised. Synthetic repositories only; no browser, network or server."""

import contextlib, errno, io, json, os, subprocess, unittest  # noqa: E401
from unittest import mock

from hass import design_preview as dp
from hass.design_check import DESIGN, Usage
from hass.tests.test_design_preview import FILES, FakePreviewer, RepoCase

CANARY = "SYNTHETIC_PRIVATE_CANARY"
PER_SIDE = sum(1 for p in FILES if p in DESIGN)  # blobs read per ref by the synthetic fixture
REAL_RUN = subprocess.run


class LaunchSpy:
    """Counts git-show launches; raises ``error`` at launch number ``fail_at`` (1-based) and records later commands."""
    def __init__(self, fail_at=None, error=None):
        self.fail_at, self.error, self.shows, self.after = fail_at, error, 0, []

    def __call__(self, argv, *args, **kwargs):
        if self.fail_at is not None and self.shows >= self.fail_at:
            self.after.append(list(argv))
        if list(argv[:3]) == ["git", "--literal-pathspecs", "show"]:
            self.shows += 1
            if self.shows == self.fail_at:
                raise self.error
        return REAL_RUN(argv, *args, **kwargs)


class BlobLaunchTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.feature = self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})

    def main(self, spy, out=None):
        os.chdir(self.repo)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(dp.subprocess, "run", spy), mock.patch.object(dp, "Previewer") as ctor, \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = dp.main(["--base", "main", "--head", "feature", "--out", str(out or self.out)])
        return code, stdout.getvalue(), stderr.getvalue(), ctor

    def assert_usage(self, code, stdout, stderr):
        self.assertEqual(code, 2)
        self.assertEqual(stdout.splitlines(), [json.dumps({"result": "usage"})])
        self.assertEqual(stderr, "design_preview: git show failed\n")
        self.assertNotIn(CANARY, stdout + stderr)
        self.assertNotIn("Traceback", stderr)

    def test_blob_launch_oserror_matrix_is_fixed_usage(self):
        for code in (errno.ENOENT, errno.EACCES, errno.ENOTDIR, errno.E2BIG):
            with self.subTest(errno=code):
                spy = LaunchSpy(1, OSError(code, CANARY, CANARY))
                with mock.patch.object(dp.subprocess, "run", spy), self.assertRaises(Usage) as caught:
                    dp._read_blob(self.feature, "storefront-mockup/style.css", str(self.repo))
                self.assertEqual(str(caught.exception), "git show failed")
                self.assertIsNone(caught.exception.__cause__)
                self.assertTrue(caught.exception.__suppress_context__)
                spy = LaunchSpy(1, OSError(code, CANARY, CANARY))
                self.assert_usage(*self.main(spy)[:3])

    def test_main_blob_failure_first_and_late_in_both_sides(self):
        for stage in (1, PER_SIDE + 1, 2 * PER_SIDE):
            with self.subTest(stage=stage):
                spy = LaunchSpy(stage, PermissionError(errno.EACCES, CANARY))
                code, stdout, stderr, ctor = self.main(spy)
                self.assert_usage(code, stdout, stderr)
                self.assertEqual(spy.shows, stage)
                self.assertEqual(spy.after, [])
                ctor.assert_not_called()
                self.assertFalse(os.path.lexists(self.out))

    def test_failed_overlay_keeps_existing_external_directory_empty(self):
        self.out.mkdir(mode=0o700)
        os.chmod(self.out, 0o700)
        before = os.lstat(self.out)
        code, stdout, stderr, ctor = self.main(LaunchSpy(2 * PER_SIDE, FileNotFoundError(errno.ENOENT, CANARY)))
        self.assert_usage(code, stdout, stderr)
        after = os.lstat(self.out)
        self.assertEqual((after.st_mode, after.st_mtime_ns), (before.st_mode, before.st_mtime_ns))
        self.assertEqual(list(self.out.iterdir()), [])
        ctor.assert_not_called()

    def test_nonzero_git_show_retains_existing_refusal(self):
        failed = subprocess.CompletedProcess(["git"], 128, b"", ("fatal: " + CANARY).encode())
        with mock.patch.object(dp.subprocess, "run", return_value=failed) as run, \
                self.assertRaises(Usage) as caught:
            dp._read_blob(self.feature, "storefront-mockup/style.css", str(self.repo))
        self.assertEqual(str(caught.exception), "git show failed")
        argv, kwargs = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(argv, ["git", "--literal-pathspecs", "show", f"{self.feature}:storefront-mockup/style.css"])
        self.assertEqual((kwargs["capture_output"], kwargs["cwd"], kwargs["env"]["GIT_OPTIONAL_LOCKS"]),
                         (True, str(self.repo), "0"))
        self.assertNotIn("text", kwargs)

    def test_binary_blob_and_valid_equal_refs_are_unchanged(self):
        blob = b"\xff\xfe\x00body{}\x80"
        sha = self.branch("binary", {"storefront-mockup/style.css": blob}, start="feature")
        before = self.snapshot()
        self.assertEqual(dp._read_blob(sha, "storefront-mockup/style.css", str(self.repo)), blob)
        fake = FakePreviewer()
        code, doc = self.run_fake(fake, base="binary", head="binary")
        self.assertEqual((code, doc["result"]), (0, "ok"))
        self.assertEqual([(c["side"], c["page"]) for c in doc["captures"]],
                         [("base", "home"), ("base", "hike"), ("head", "home"), ("head", "hike")])
        self.assertEqual([call[0]["storefront-mockup/style.css"] for call in fake.calls], [blob] * 4)
        self.assertEqual(self.snapshot(), before)

    def test_non_os_programming_error_not_swallowed(self):
        with mock.patch.object(dp.subprocess, "run", LaunchSpy(1, RuntimeError(CANARY))), \
                self.assertRaises(RuntimeError):
            dp._read_blob(self.feature, "storefront-mockup/style.css", str(self.repo))


if __name__ == "__main__":
    unittest.main()
