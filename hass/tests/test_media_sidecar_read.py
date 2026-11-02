"""RF1920-6 (H10/H19) tests: a too-deep or >64 KiB sidecar is one `sidecar invalid` problem in `media.py verify`
and one counted problem in `health --media`, never a RecursionError; `_existing` never hangs on a swapped-in FIFO.

Temp 0700 stores built with media.store_original (as test_media_verify_sidecar.py builds them); nothing is ever
written to a store by the code under test.
"""
import contextlib, hashlib, io, json, os, subprocess, sys, tempfile, threading, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import health, media
from hass.content_model import REPO_ROOT

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "media"
JPEG, PNG = (FIX / "pixel.jpg").read_bytes(), (FIX / "pixel.png").read_bytes()
J, P = hashlib.sha256(JPEG).hexdigest(), hashlib.sha256(PNG).hexdigest()
DEEP = b"[" * 100_000 + b"]" * 100_000
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}


def snapshot(root: Path) -> dict:
    """Every entry under root with its mode and (for files) bytes, to prove nothing was written."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(dirpath) / name
            st = os.lstat(path)
            out[str(path.relative_to(root))] = (st.st_mode, path.read_bytes() if path.is_file() else None)
    return out


class SidecarReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.store = self.tmp / "media"
        for data in (JPEG, PNG): media.store_original(self.store, data, received_at=NOW.isoformat(), source="fixture")

    def put_sidecar(self, raw: bytes):
        side = self.store / "originals" / J[:2] / f"{J}.json"
        os.chmod(side, 0o600)
        side.write_bytes(raw)
        return snapshot(self.store)

    def assertInvalid(self, before):
        self.assertEqual(media.verify_store(self.store),
                         {"result": "problems", "problems": [f"sidecar invalid: {J[:12]}"], "originals": 2, "web": 0})
        self.assertEqual(snapshot(self.store), before)

    def test_deep_sidecar_is_one_problem_and_other_originals_still_counted(self):
        self.assertInvalid(self.put_sidecar(DEEP))

    def test_recursion_error_from_the_parser_is_sidecar_invalid(self):
        before = self.put_sidecar(b"[" * 30_000 + b"]" * 30_000)  # under 64 KiB, so it reaches json.loads
        real = json.loads  # only the deep sidecar raises; the PNG's normal sidecar parses as usual
        def loads(raw, *a, **k):
            if raw.startswith(b"[["): raise RecursionError("maximum recursion depth exceeded")
            return real(raw, *a, **k)
        with mock.patch.object(media.json, "loads", side_effect=loads):
            self.assertInvalid(before)

    def test_size_boundary(self):
        meta = json.loads((self.store / "originals" / J[:2] / f"{J}.json").read_bytes())
        self.assertLess(len(json.dumps(meta)), 1024)  # a store-written sidecar is far below the cap
        body = json.dumps(meta).encode()
        before = self.put_sidecar(body + b" " * (media.SIDECAR_MAX - len(body)))  # exactly 64 KiB: still parsed
        self.assertEqual(media.verify_store(self.store)["result"], "ok")
        self.assertEqual(snapshot(self.store), before)
        self.assertInvalid(self.put_sidecar(body + b" " * (media.SIDECAR_MAX + 1 - len(body))))  # 64 KiB + 1

    def test_normal_store_is_ok(self):
        before = snapshot(self.store)
        self.assertEqual(media.verify_store(self.store), {"result": "ok", "problems": [], "originals": 2, "web": 0})
        self.assertEqual(snapshot(self.store), before)

    def test_cli_prints_one_json_line_and_exits_1(self):
        before = self.put_sidecar(DEEP)
        run = subprocess.run([sys.executable, "hass/media.py", "verify", "--root", str(self.store)], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual((run.returncode, run.stderr, len(run.stdout.splitlines())), (1, "", 1))
        self.assertEqual(json.loads(run.stdout)["problems"], [f"sidecar invalid: {J[:12]}"])
        self.assertEqual(snapshot(self.store), before)

    def test_health_prints_its_report_with_one_counted_problem(self):
        state = self.tmp / "state"
        state.mkdir(mode=0o700)
        (state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))
        before = self.put_sidecar(DEEP)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(state), "--media", str(self.store)], now=NOW)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertNotIn(J[:12], lines[0])
        self.assertEqual((code, json.loads(lines[0])["problems"]), (1, [{"check": "media-store", "detail": "1 problem(s)"}]))
        self.assertEqual(snapshot(self.store), before)


@unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
class ExistingFifoTest(unittest.TestCase):
    def test_fifo_swapped_in_after_lstat_is_refused_without_hanging(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (regular := tmp / "regular").write_bytes(b"x")
        os.mkfifo(fifo := tmp / "fifo", 0o600)
        real_lstat, outcome = os.lstat, []
        def run():
            try: outcome.append(media._existing(fifo))
            except media.Refused as exc: outcome.append(exc.code)
            except Exception as exc: outcome.append(repr(exc))  # noqa: BLE001
        with mock.patch.object(media.os, "lstat", lambda p: real_lstat(regular if Path(p) == fifo else p)):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            worker.join(5)
        if worker.is_alive():  # old behaviour: open() blocks; give it a writer so the thread can end, then fail
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
            self.fail("_existing blocked on a FIFO")
        self.assertEqual(outcome, ["corrupt-store"])
        self.assertEqual(sorted(os.listdir(tmp)), ["fifo", "regular"])


if __name__ == "__main__":
    unittest.main()
