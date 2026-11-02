"""RF1920-2 tests: hass/retention.py reads a photo sidecar once, at most 64 KiB, never following a link or waiting on a
FIFO. A too-deep, oversize, non-UTF-8, non-object or swapped sidecar leaves its original undated; the report still prints.

Temp state and media dirs built as test_retention.py builds them; an injected clock. Never the real private state.
Run: python3 -B -m unittest hass.tests.test_retention_sidecar_read -v
"""
import contextlib, io, json, os, shutil, sqlite3, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import conversation, inbox, retention
from hass.tests.test_retention import NOW, OLD, NEW, SHA_OLD, SHA_NEW, SHA_UNDATED, iso, tree

DATED_OLD = {"originals": 1, "bytes": 5, "web": 0, "oldest": OLD.date().isoformat(), "undated": 1}


def padded(size: int) -> bytes:
    """A valid OLD-dated sidecar of exactly size bytes."""
    head = json.dumps({"received_at": iso(OLD), "pad": ""}).encode()
    return head[:-2] + b"x" * (size - len(head)) + head[-2:]


class SidecarReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.media = self.tmp / "state", self.tmp / "media"
        for d in (self.state, self.media): d.mkdir(mode=0o700)
        for name, schema in (("inbox.sqlite3", inbox.SCHEMA), ("conversation.sqlite3", conversation.SCHEMA)):
            with contextlib.closing(sqlite3.connect(self.state / name)) as db, db: db.executescript(schema)

    def original(self, sha, sidecar: bytes, size=5):
        folder = self.media / "originals" / sha[:2]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{sha}.jpg").write_bytes(b"j" * size)
        (folder / f"{sha}.json").write_bytes(sidecar)
        return folder / f"{sha}.json"

    def report(self):
        """(exit code, stdout, stderr) of one in-process run; asserts nothing under tmp was created or changed."""
        before, out, err = tree(self.tmp), io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = retention.main(["report", "--state", str(self.state), "--days", "30", "--now", iso(NOW),
                                   "--media", str(self.media)])
        self.assertEqual(tree(self.tmp), before)
        return code, out.getvalue(), err.getvalue()

    def media_with_bad(self, sidecar: bytes):
        """The media doc for one good OLD original beside one original whose sidecar is sidecar."""
        self.original(SHA_OLD, json.dumps({"received_at": iso(OLD)}).encode())
        self.original(SHA_UNDATED, sidecar, size=17)
        code, out, err = self.report()
        self.assertEqual((code, err), (0, ""))
        return json.loads(out)["media"]

    def test_too_deep_sidecar_is_undated_not_a_recursion_traceback(self):
        for depth in (100_000, 30_000):  # 200 000 bytes (over the cap), and 60 000 bytes (under it: parser recursion)
            with self.subTest(depth=depth):
                self.assertEqual(self.media_with_bad(b"[" * depth + b"]" * depth), DATED_OLD)
        deep = b'{"received_at": ' + b"[" * 30_000 + b"]" * 30_000 + b"}"
        self.assertEqual(self.media_with_bad(deep), DATED_OLD)

    def test_size_cap_is_64_kib(self):
        self.assertEqual(retention.SIDECAR_MAX, 64 * 1024)
        self.assertEqual(len(padded(64 * 1024 + 1)), 64 * 1024 + 1)
        self.assertEqual(self.media_with_bad(padded(64 * 1024 + 1)), DATED_OLD)
        self.assertEqual(self.media_with_bad(padded(10 * 64 * 1024)), DATED_OLD)
        self.original(SHA_UNDATED, padded(64 * 1024), size=17)  # exactly the cap: dated as today
        code, out, err = self.report()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["media"], {"originals": 2, "bytes": 22, "web": 0,
                                                     "oldest": OLD.date().isoformat(), "undated": 0})

    def test_non_object_or_non_utf8_sidecar_is_undated(self):
        for raw in (b"[]", b'"x"', b"7", b"null", b'["received_at"]', b"\xff\xfe{}", b"", b'{"received_at": '):
            with self.subTest(raw=raw):
                self.assertEqual(self.media_with_bad(raw), DATED_OLD)

    def test_sidecar_swapped_for_a_link_or_dir_is_undated(self):
        good = self.tmp / "good.json"
        good.write_bytes(json.dumps({"received_at": iso(OLD)}).encode())
        (link := self.original(SHA_NEW, b"{}")).unlink()
        link.symlink_to(good)  # a link to a valid OLD sidecar: never followed
        (folder := self.original(SHA_UNDATED, b"{}", size=17)).unlink()
        folder.mkdir()
        code, out, err = self.report()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["media"], {"originals": 0, "bytes": 0, "web": 0, "oldest": None,
                                                    "undated": 2})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no os.mkfifo")
    def test_sidecar_swapped_for_a_fifo_is_undated_within_5_s(self):
        self.original(SHA_OLD, json.dumps({"received_at": iso(OLD)}).encode())
        (sidecar := self.original(SHA_UNDATED, b"{}", size=17)).unlink()
        os.mkfifo(sidecar)  # no writer: a blocking open would hang the report
        names = sorted(os.path.join(d, n) for d, ds, fs in os.walk(self.tmp) for n in ds + fs)
        proc = subprocess.run([sys.executable, "-B", str(Path(retention.__file__)), "report", "--state", str(self.state),
                               "--days", "30", "--now", iso(NOW), "--media", str(self.media)],
                              capture_output=True, text=True, timeout=5)
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        self.assertEqual(json.loads(proc.stdout)["media"], DATED_OLD)
        self.assertEqual(sorted(os.path.join(d, n) for d, ds, fs in os.walk(self.tmp) for n in ds + fs), names)

    def test_normal_media_tree_report_is_byte_identical(self):
        self.original(SHA_OLD, json.dumps({"received_at": iso(OLD)}).encode(), size=11)
        self.original(SHA_NEW, json.dumps({"received_at": iso(NEW), "kind": "jpeg"}).encode(), size=13)
        self.original(SHA_UNDATED, json.dumps({"kind": "jpeg"}).encode(), size=17)
        (web := self.media / "web" / SHA_OLD[:2]).mkdir(parents=True)
        (web / f"{SHA_OLD}.jpg").write_bytes(b"w")
        code, out, err = self.report()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, (  # produced by origin/main a8879cb for this tree and --now
            '{"days": 30, "cutoff": "2026-10-03T17:00:00+00:00", "inbox": {"done": 0, "history": 0, "pending": 0, '
            '"oldest": null}, "messages": {"rows": 0, "oldest": null}, "outbox": {"sent": 0, "unsent": 0, '
            '"oldest": null}, "drafts": {"closed": 0, "open": 0}, "approvals": {"rows": 0, "oldest": null}, '
            '"memory": {"forgotten": 0, "superseded": 0, "oldest": null}, "screenshots": {"files": 0, "bytes": 0}, '
            '"media": {"originals": 1, "bytes": 11, "web": 1, "oldest": "2026-10-02", "undated": 1}, "backups": null, '
            '"deletes": 0}\n'))


if __name__ == "__main__":
    unittest.main()
