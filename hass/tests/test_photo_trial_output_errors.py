"""RF1900-12: the photo trial reports a failing output sink (write or flush after admission) as the documented exit 2 with one
fixed, path-free stderr sentence, and no interpreter-shutdown traceback / exit 120. Synthetic photos and external temporary
folders only; nothing here writes inside the checkout."""
import errno
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import newitem_synthetic
from hass.skills import photo_trial

SCRIPT = photo_trial.REPO_ROOT / "hass" / "skills" / "photo_trial.py"
FIXED = "photo_trial: I couldn't write the photo results. The output may be incomplete.\n"
CANARY = "/private/canary/owner-photos"
_GOOD = {}


def setUpModule():
    kwargs = dict(newitem_synthetic.cases())["jar-white-sheet"]
    _GOOD["jar-white-sheet.jpg"] = newitem_synthetic.make_photo(**kwargs)


def _tmp(test):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    return Path(tmp.name).resolve()


def _folder(test, photos):
    folder = _tmp(test) / "photos"
    folder.mkdir()
    for name, data in photos.items():
        (folder / name).write_bytes(data)
    return folder


def _tree(root):
    return sorted((str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest()) for p in Path(root).rglob("*") if p.is_file())


class Sink:
    """An in-memory, caller-owned stream whose write and/or flush fail on purpose after accepting ``accept`` characters."""

    def __init__(self, write_error=None, flush_error=None, accept=0):
        self.write_error, self.flush_error, self.accept = write_error, flush_error, accept
        self.calls, self.data, self.closed = [], "", False

    def write(self, text):
        self.calls.append("write")
        if self.write_error:
            self.data += text[:self.accept]
            raise self.write_error
        self.data += text
        return len(text)

    def flush(self):
        self.calls.append("flush")
        if self.flush_error:
            raise self.flush_error

    def close(self):
        self.closed = True


def _run(folder, *extra, stdout):
    err = io.StringIO()
    return photo_trial.main([str(folder), *extra], stdout=stdout, stderr=err), err.getvalue()


class Emission(unittest.TestCase):
    def setUp(self):
        self.folder = _folder(self, {"a.jpg": b"not a picture"})  # a corrupt photo: the real renderer gives one warn row
        self.before = _tree(self.folder)

    def test_write_oserror_returns_two_and_fixed_private_diagnostic(self):
        for error in (OSError(errno.ENOSPC, CANARY), PermissionError(errno.EACCES, CANARY), BrokenPipeError(errno.EPIPE, CANARY)):
            for extra in ((), ("--json",)):
                with self.subTest(error=type(error).__name__, extra=extra):
                    sink = Sink(write_error=error)
                    code, err = _run(self.folder, *extra, stdout=sink)
                    self.assertEqual((code, err), (2, FIXED))
                    self.assertEqual(sink.calls, ["write"])  # one attempt: no flush, no retry
                    self.assertNotIn(CANARY, err)
                    self.assertNotIn(str(self.folder), err)
                    self.assertNotIn("Traceback", err)
                    self.assertEqual(sink.data, "")
                    self.assertEqual(_tree(self.folder), self.before)

    def test_flush_oserror_is_not_reported_as_a_completed_trial(self):
        for extra, shape in (((), "text"), (("--json",), "json")):
            with self.subTest(shape=shape):
                sink = Sink(flush_error=OSError(errno.EIO, CANARY))
                code, err = _run(self.folder, *extra, stdout=sink)
                self.assertEqual((code, err), (2, FIXED))
                self.assertEqual(sink.calls, ["write", "flush"])  # one report, one flush, nothing retried
                healthy = io.StringIO()
                self.assertEqual(_run(self.folder, *extra, stdout=healthy)[0], 1)
                self.assertEqual(sink.data, healthy.getvalue())  # accepted bytes are left alone, not repeated
                self.assertEqual(sink.data.count("a.jpg"), 1)
                self.assertNotIn(CANARY, err)

    def test_prefix_then_write_failure_does_not_retry_or_claim_atomic_output(self):
        sink = Sink(write_error=OSError(errno.ENOSPC, CANARY), accept=12)
        code, err = _run(self.folder, stdout=sink)
        self.assertEqual((code, err), (2, FIXED))
        self.assertEqual(sink.data, photo_trial.HEADER[:12])  # the accepted prefix stays exactly as written
        self.assertEqual(sink.calls, ["write"])
        self.assertIn("may be incomplete", err)
        self.assertNotIn("a.jpg", sink.data)
        self.assertEqual(_tree(self.folder), self.before)


class RealScript(unittest.TestCase):
    def _run_script(self, folder, sink_path, *extra):
        with open(sink_path, "rb") as readonly:  # a genuine regular file opened read-only: the kernel refuses every write
            done = subprocess.run([sys.executable, "-B", str(SCRIPT), str(folder), *extra], stdout=readonly, stderr=subprocess.PIPE,
                                  text=True, cwd=str(folder.parent))
        return done.returncode, done.stderr

    def test_real_script_readonly_stdout_exits_two_without_shutdown_traceback(self):
        folder = _folder(self, {"a.jpg": b"not a picture"})
        sink = folder.parent / "sentinel.txt"
        sink.write_bytes(b"sentinel\n")
        before, sink_before = _tree(folder), sink.read_bytes()
        for extra in ((), ("--json",)):
            with self.subTest(extra=extra):
                code, err = self._run_script(folder, sink, *extra)
                self.assertEqual((code, err), (2, FIXED))  # not 120, no "Exception ignored", no traceback
                self.assertEqual(sink.read_bytes(), sink_before)
                self.assertEqual(_tree(folder), before)


class Ownership(unittest.TestCase):
    def setUp(self):
        self.folder = _folder(self, {"a.jpg": b"not a picture"})

    def test_caller_owned_output_is_not_closed_or_rebound(self):
        before_stdout, before_fds = sys.stdout, len(os.listdir("/proc/self/fd"))
        sink = Sink(flush_error=OSError(errno.EIO, CANARY))
        self.assertEqual(_run(self.folder, stdout=sink)[0], 2)
        self.assertFalse(sink.closed)
        self.assertIs(sys.stdout, before_stdout)  # a caller-supplied stream never changes the process stdout
        self.assertEqual(len(os.listdir("/proc/self/fd")), before_fds)

    def test_failed_standard_stdout_is_quarantined_and_restored_by_the_test(self):
        failing = Sink(write_error=OSError(errno.ENOSPC, CANARY))
        original = sys.stdout
        err = io.StringIO()
        sys.stdout = failing
        try:
            code = photo_trial.main([str(self.folder)], stderr=err)
            parked = sys.stdout
        finally:
            sys.stdout = original
        self.assertEqual((code, err.getvalue()), (2, FIXED))
        self.assertIsNot(parked, failing)  # shutdown can no longer flush the failed stream
        self.assertIsInstance(parked, io.StringIO)
        self.assertEqual(failing.calls, ["write"])
        self.assertFalse(failing.closed)

    def test_healthy_standard_stdout_is_not_rebound(self):
        original, err, held = sys.stdout, io.StringIO(), io.StringIO()
        sys.stdout = held
        try:
            code = photo_trial.main([str(self.folder)], stderr=err)
            after = sys.stdout
        finally:
            sys.stdout = original
        self.assertEqual((code, err.getvalue()), (1, ""))
        self.assertIs(after, held)
        self.assertTrue(held.getvalue().startswith(photo_trial.HEADER))


class Healthy(unittest.TestCase):
    def test_healthy_pass_warn_and_preflight_paths_keep_their_contract(self):
        good = _folder(self, _GOOD)
        warn = _folder(self, {"a.jpg": b"not a picture"})
        for folder, status, want in ((good, "pass", 0), (warn, "warn", 1)):
            rows = photo_trial.trial_directory(folder)
            self.assertEqual(rows[0]["status"], status)
            for extra, render in (((), photo_trial.format_text), (("--json",), photo_trial.format_json)):
                out = io.StringIO()
                code, err = _run(folder, *extra, stdout=out)
                self.assertEqual((code, err), (want, ""))
                self.assertEqual(out.getvalue(), render(rows))
        json.loads(out.getvalue())
        # refusals stay before emission with their own sentence
        out = io.StringIO()
        code, err = _run(warn.parent / "missing", stdout=out)
        self.assertEqual((code, out.getvalue(), err), (2, "", "photo_trial: That folder does not exist.\n"))

    def test_unrelated_errors_are_not_mislabeled_as_a_sink_failure(self):
        folder = _folder(self, {"a.jpg": b"not a picture"})
        with self.assertRaises(RuntimeError):
            _run(folder, stdout=Sink(write_error=RuntimeError("writer defect")))
        with mock.patch.object(photo_trial, "format_text", side_effect=RuntimeError("formatter defect")):
            with self.assertRaises(RuntimeError):
                _run(folder, stdout=io.StringIO())


if __name__ == "__main__":
    unittest.main()
