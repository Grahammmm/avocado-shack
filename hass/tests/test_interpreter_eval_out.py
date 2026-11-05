"""RF0250-6 (H09) tests: `--live --out` writes the replies file 0600 and whole, through a private temp file beside it
that is linked into place; a failed write leaves neither the file nor a temp file. Fake transport only, no model."""

import contextlib, errno, os, stat, unittest  # noqa: E401
from unittest import mock

from hass import interpreter_eval as ev
from hass.tests import test_interpreter_eval as base  # module import: its test classes are not collected twice


class OutFileTests(base.EvalTestCase):
    fake = base.LiveTests.fake

    def live(self, out, **patches):
        """Run --live with ``ev.os.<name>`` (or ``ev.tempfile.mkstemp``) replaced by a function or an exception."""
        calls = []
        with contextlib.ExitStack() as stack:
            for name, value in patches.items():
                kw = {"side_effect": value} if isinstance(value, BaseException) else {"new": value}
                stack.enter_context(mock.patch.object(ev.tempfile if name == "mkstemp" else ev.os, name, **kw))
            code, stdout, err = base.run("--live", "--url", base.URL, "--model", "m", "--out", out,
                                         transport=self.fake(calls))
        return code, stdout, err, len(calls)

    def temps(self, folder=None): return sorted((folder or self.tmp).glob(".interpreter-eval-*.tmp"))

    def test_fresh_out_is_0600_whole_and_leaves_no_temp(self):
        out, old = self.tmp / "fresh.jsonl", os.umask(0o022)
        try:
            code, stdout, err, calls = self.live(out)
        finally:
            os.umask(old)
        self.assertEqual((code, err, calls, stat.S_IMODE(out.stat().st_mode)), (0, "", 69, 0o600))
        self.assertEqual(len(out.read_text("utf-8").splitlines()), 69)
        self.assertEqual(list(ev.load_replies(out)), [c["id"] for c in self.cases])
        self.assertEqual((self.temps(), out.stat().st_nlink), ([], 1))

    def test_fsync_failure_leaves_nothing(self):
        out = self.tmp / "full.jsonl"
        code, stdout, err, calls = self.live(out, fsync=OSError(errno.ENOSPC, "No space left on device"))
        self.assertEqual((code, stdout, err, calls), (2, "", "--out could not be created", 69))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_link_lost_race_keeps_other_file_and_removes_temp(self):
        out, real_link = self.tmp / "race.jsonl", os.link

        def other_writer_wins(src, dst, *a, **k):
            with open(dst, "xb") as fh: fh.write(b"theirs\n")
            return real_link(src, dst, *a, **k)  # raises FileExistsError: os.link never replaces
        code, stdout, err, calls = self.live(out, link=other_writer_wins)
        self.assertEqual((code, stdout, err, calls), (2, "", "--out already exists", 69))
        self.assertEqual((out.read_bytes(), self.temps()), (b"theirs\n", []))

    def test_link_unsupported_leaves_nothing(self):
        out = self.tmp / "nolinks.jsonl"
        code, stdout, err, calls = self.live(out, link=PermissionError(errno.EPERM, "Operation not permitted"))
        self.assertEqual((code, stdout, err, calls), (2, "", "--out could not be created", 69))
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_missing_parent_fails_after_the_calls_and_creates_nothing(self):
        code, stdout, err, calls = self.live(self.tmp / "absent" / "r.jsonl")
        self.assertEqual((code, stdout, err, calls), (2, "", "--out could not be created", 69))  # calls come first
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_temp_name_never_printed(self):
        names = []
        real = ev.tempfile.mkstemp

        def spy(*a, **k):
            fd, path = real(*a, **k)
            names.append(os.path.basename(path))
            return fd, path
        code, stdout, err, _ = self.live(self.tmp / "spy.jsonl", mkstemp=spy, fsync=OSError(errno.EIO, "I/O"))
        self.assertEqual((code, len(names)), (2, 1))
        self.assertNotIn(names[0], stdout + err)
        self.assertNotIn(".interpreter-eval-", stdout + err)

    def test_existing_refusals_unchanged_and_before_any_call(self):
        existing, link = self.write("exists.jsonl", ["{}"]), self.tmp / "link.jsonl"
        os.symlink(self.tmp / "nowhere", link)
        for out, why in ((ev.REPO / "replies.jsonl", "--out must be outside the repository"),
                         (existing, "--out already exists"), (link, "--out already exists")):
            self.assertEqual(self.live(out), (2, "", why, 0), out)
        self.assertEqual((existing.read_text("utf-8"), self.temps(), self.temps(ev.REPO)), ("{}\n", [], []))
        self.assertFalse((ev.REPO / "replies.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
