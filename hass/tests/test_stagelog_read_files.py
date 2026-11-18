"""RF1911-11: stage-log reading skips FIFOs and other non-regular inputs without blocking."""
import json, os, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import stagelog

ROOT = Path(__file__).resolve().parents[2]


class StageLogReadFiles(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.dir = Path(td.name)

    def test_fifo_without_writer_returns_promptly(self):
        fifo = self.dir / "f.fifo"
        os.mkfifo(fifo)
        r = subprocess.run([sys.executable, "-B", str(ROOT / "hass" / "stagelog.py"), str(fifo)], capture_output=True, cwd=ROOT, timeout=20)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))

    def test_fifo_with_writer_and_directory_are_not_consumed(self):
        fifo = self.dir / "f.fifo"
        os.mkfifo(fifo)
        wfd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        self.addCleanup(os.close, wfd)
        os.write(wfd, (json.dumps({"t": 1.0, "stage": "accepted", "id": "a"}) + "\n").encode())
        self.assertEqual(stagelog.read(fifo), [])
        self.assertEqual(os.read(wfd, 4096)[:1], b"{")  # data still in the pipe: nothing consumed
        self.assertEqual(stagelog.read(self.dir), [])

    def test_regular_and_regular_symlink_preserve_decoding(self):
        good = lambda t, s: json.dumps({"t": t, "stage": s, "id": "x\u2028y"}, ensure_ascii=False)  # noqa: E731
        p = self.dir / "a.jsonl"
        p.write_bytes((good(1, "accepted") + "\r\n" + good(2, "sent") + "\r\xff{bad\n").encode("utf-8") + b"\xff\n")
        link = self.dir / "l.jsonl"
        link.symlink_to(p)
        got = stagelog.read(p)
        self.assertEqual([r["stage"] for r in got], ["accepted", "sent"])
        self.assertEqual(got[0]["id"], "x\u2028y")
        self.assertEqual(stagelog.read(link), got)
        self.assertEqual(stagelog.read(self.dir / "missing"), [])

    def test_descriptor_is_closed_on_refusal_and_fstat_failure(self):
        p = self.dir / "a.jsonl"
        p.write_text(json.dumps({"t": 1, "stage": "accepted", "id": "a"}) + "\n")
        real_close = os.close
        for patch in (None, mock.patch("os.fstat", side_effect=OSError("boom")), mock.patch("os.fstat", return_value=os.stat(self.dir))):
            closed = []
            with mock.patch("os.close", side_effect=lambda fd: (closed.append(fd), real_close(fd))[1]):
                if patch is None:
                    self.assertEqual(len(stagelog.read(p)), 1)
                else:
                    with patch: self.assertEqual(stagelog.read(p), [])
            self.assertEqual(len(closed), 1)


if __name__ == "__main__":
    unittest.main()
