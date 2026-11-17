"""RF1201-12: best-effort stage logging never blocks on, or writes to, a FIFO or other non-regular destination."""
import json, os, stat, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass import stagelog  # noqa: E402

CHILD = ("import sys; sys.path.insert(0, sys.argv[1]); from hass.stagelog import StageLog; "
         "StageLog(sys.argv[2], clock=lambda: 1.0)('accepted', 'm1'); print('returned')")


class DestinationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _fifo(self):
        p = self.dir / "stage.log"
        os.mkfifo(p, 0o600)
        return p

    def test_fifo_without_reader_does_not_block(self):
        p = self._fifo()
        before = os.stat(p)
        with tempfile.TemporaryDirectory() as sd:
            script = Path(sd) / "child.py"
            script.write_text(CHILD.replace("; ", "\n"))
            self._run_child(script, p, before)

    def _run_child(self, script, p, before):
        child = subprocess.Popen([sys.executable, "-B", str(script), str(ROOT), str(p)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out, err = child.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            self.fail("StageLog blocked on a FIFO without a reader")
        self.assertEqual((child.returncode, out, err), (0, "returned\n", ""))
        after = os.stat(p)
        self.assertTrue(stat.S_ISFIFO(after.st_mode))
        self.assertEqual((before.st_ino, before.st_mode), (after.st_ino, after.st_mode))
        self.assertEqual(os.listdir(self.dir), ["stage.log"])

    def test_fifo_with_reader_is_not_written(self):
        p = self._fifo()
        rfd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
        try:
            stagelog.StageLog(p, clock=lambda: 1.0)("accepted", "m1")
            self.assertEqual(os.read(rfd, 100), b"")  # no bytes arrived (EOF: no writer remains)
        finally: os.close(rfd)
        self.assertTrue(stat.S_ISFIFO(os.stat(p).st_mode))

    def test_nonregular_open_descriptor_is_closed(self):
        opened, closed, writes = [], [], []
        real_open, real_close = os.open, os.close

        def spy_open(path, *a, **k):
            fd = real_open(path, *a, **k)
            if str(path) == str(self.dir / "stage.log"): opened.append(fd)
            return fd

        def spy_close(fd):
            if fd in opened: closed.append(fd)
            return real_close(fd)

        p = self._fifo()
        rfd = real_open(p, os.O_RDONLY | os.O_NONBLOCK)
        try:
            with mock.patch.object(os, "open", spy_open), mock.patch.object(os, "close", spy_close), \
                    mock.patch.object(os, "write", lambda *a: writes.append(a)):
                stagelog.StageLog(p)("accepted", "m1")
        finally: real_close(rfd)
        self.assertEqual(len(opened), 1)
        self.assertEqual(closed, opened)
        self.assertEqual(writes, [])
        # fstat failure on the acquired descriptor: no raise, fd still closed
        p2 = self.dir / "plain.log"
        opened.clear(); closed.clear()
        real_open_p2 = spy_open
        def spy_open2(path, *a, **k):
            fd = real_open_p2(path, *a, **k)
            if str(path) == str(p2): opened.append(fd)
            return fd
        with mock.patch.object(os, "open", spy_open2), mock.patch.object(os, "close", spy_close), \
                mock.patch.object(os, "fstat", side_effect=OSError("boom")):
            stagelog.StageLog(p2)("accepted", "m1")
        self.assertEqual(len(opened), 1)
        self.assertEqual(closed, opened)
        # directory and symlink destinations stay quietly dropped
        d = self.dir / "adir"; d.mkdir()
        stagelog.StageLog(d)("accepted", "m1")
        target = self.dir / "target.log"; target.write_text("")
        link = self.dir / "link.log"; link.symlink_to(target)
        stagelog.StageLog(link)("accepted", "m1")
        self.assertEqual(target.read_text(), "")

    def test_regular_existing_and_missing_destinations_still_append(self):
        p = self.dir / "new.log"
        t = iter([1.00049, 2.0006])
        log = stagelog.StageLog(p, clock=lambda: next(t))
        log("accepted", "secret-msg-id", extra="x")
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
        log("reply-queued", "secret-rid")
        rows = [json.loads(x) for x in p.read_text().splitlines()]
        self.assertEqual(rows, [{"t": 1.0, "stage": "accepted", "id": stagelog.short("secret-msg-id"), "extra": "x"},
                                {"t": 2.001, "stage": "reply-queued", "id": stagelog.short("secret-rid")}])
        self.assertNotIn("secret", p.read_text())
        stagelog.StageLog(None)("accepted", "m1")
        stagelog.StageLog(self.dir / "nodir" / "x.log")("accepted", "m1")
        stagelog.StageLog(p, clock=lambda: 1 / 0)("accepted", "m1")
        self.assertEqual(len(stagelog.read(p)), 2)


if __name__ == "__main__":
    unittest.main()
