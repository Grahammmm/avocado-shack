"""RF1100-20 (H10/H19) tests: verify checks existing web copies against the safe derivative, read-only. All synthetic."""

import contextlib, hashlib, io, json, os, subprocess, sys, tempfile, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import health, media
from hass.content_model import REPO_ROOT
from hass.tests.test_media_verify import snapshot
from hass.tests.test_media_web import XMP, chunk, exif, jpeg, png

AT = "2026-11-02T18:00:00+00:00"
NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
def seg_xmp():
    return bytes([0xFF, 0xE1]) + (len(XMP) + 2).to_bytes(2, "big") + XMP

GPS_PNG = chunk(b"tEXt", b"Comment\0GPS 0 0 0")

class VerifyWebTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"

    def put(self, data, web=True):
        sha = media.store_original(self.root, data, received_at=AT, source="fixture")["sha256"]
        if web: media.web_copy(self.root, sha)
        return sha

    def web(self, sha, ext):
        return self.root / "web" / sha[:2] / f"{sha}.{ext}"

    def replace(self, path, data):
        os.chmod(path, 0o600)
        path.write_bytes(data)

    def plant(self, sha, ext, data):  # a web file with no writer involved (the writer refuses such originals)
        for d in (self.root / "web", self.root / "web" / sha[:2]): d.mkdir(mode=0o700, exist_ok=True)
        self.web(sha, ext).write_bytes(data)
        os.chmod(self.web(sha, ext), 0o600)

    def problems(self, code=1):
        before = snapshot(self.root)
        run = subprocess.run([sys.executable, "hass/media.py", "verify", "--root", str(self.root)], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual((run.returncode, run.stderr, run.stdout.count("\n")), (code, "", 1))
        out = json.loads(run.stdout)
        self.assertEqual(out, media.verify_store(self.root))
        self.assertEqual(snapshot(self.root), before)
        return out["problems"]

    def test_clean_jpeg_and_png_with_removed_metadata_pass(self):
        for data in (jpeg(exif(), seg_xmp()), png(GPS_PNG), jpeg(exif(orientation=6))):
            self.put(data)
        out = media.verify_store(self.root)
        self.assertEqual((out["result"], out["problems"], out["originals"], out["web"]), ("ok", [], 3, 3))
        self.assertNotEqual(self.web(hashlib.sha256(png(GPS_PNG)).hexdigest(), "png").read_bytes(), png(GPS_PNG))

    def test_changed_web_bytes_are_one_mismatch(self):
        sha = self.put(jpeg(exif()))
        good = self.web(sha, "jpg").read_bytes()
        for bad in (good[:-3] + bytes([good[-3] ^ 1]) + good[-2:], b"", good[:len(good) // 2]):
            self.replace(self.web(sha, "jpg"), bad)
            self.assertEqual(self.problems(), [f"web content mismatch: {sha[:12]}"])
        self.assertEqual(media.verify_store(self.root)["web"], 1)

    def test_restored_exif_or_png_text_is_mismatch(self):
        original = jpeg(exif())
        sha = self.put(original)
        self.replace(self.web(sha, "jpg"), original)
        self.assertEqual(self.problems(), [f"web content mismatch: {sha[:12]}"])
        original = png(GPS_PNG)
        sha = self.put(original)
        self.replace(self.web(sha, "png"), original)
        self.assertIn(f"web content mismatch: {sha[:12]}", self.problems())

    def test_missing_web_is_not_generated(self):
        self.put(jpeg(exif()), web=False)
        self.assertEqual(media.verify_store(self.root), {"result": "ok", "problems": [], "web": 0, "originals": 1})
        self.assertFalse((self.root / "web").exists())

    def test_bad_original_does_not_cascade(self):
        sha = self.put(jpeg(exif()))
        path = self.root / "originals" / sha[:2] / f"{sha}.jpg"
        self.replace(path, path.read_bytes()[:-3] + b"\x00\x00\x00")  # still sniffs as a JPEG, hash differs
        self.replace(self.web(sha, "jpg"), b"junk")
        self.assertNotIn(f"web content mismatch: {sha[:12]}", self.problems())
        self.assertIn(f"content mismatch: {sha[:12]}", self.problems())
        orphan = "ab" * 32
        self.plant(orphan, "jpg", b"x")
        self.assertIn(f"web orphan: {orphan[:12]}", self.problems())
        other = self.put(png(GPS_PNG))
        self.plant(other, "jpg", b"x")  # original is a png: wrong kind, never byte-compared
        probs = self.problems()
        self.assertIn(f"web kind: {other[:12]}", probs)
        self.assertNotIn(f"web content mismatch: {other[:12]}", probs)

    def test_unconvertible_original_is_web_unverifiable(self):
        bad = jpeg(exif(orientation=3), exif("MM", 6))  # two EXIF blocks that disagree: the sanitizer refuses
        sha = self.put(bad, web=False)
        self.plant(sha, "jpg", b"anything")
        out = media.verify_store(self.root)
        self.assertEqual(out["problems"], [f"web unverifiable: {sha[:12]}"])
        self.assertEqual(self.problems(), [f"web unverifiable: {sha[:12]}"])

    def test_web_read_failure_is_redacted(self):
        sha = self.put(jpeg(exif()))
        with mock.patch.object(media, "_existing", side_effect=lambda p: (_ for _ in ()).throw(OSError(str(p)))):
            out = media.verify_store(self.root)
        self.assertNotIn(str(self.tmp), json.dumps(out))
        self.assertTrue(all(p.startswith("unreadable: ") for p in out["problems"]))
        # a planted symlink and a swapped FIFO are reported, never followed or blocked on
        target = self.tmp / "target.jpg"
        target.write_bytes(b"secret target")
        web = self.web(sha, "jpg")
        web.unlink()
        web.symlink_to(target)
        self.assertIn(f"symlink: web/{sha[:2]}/{sha[:12]}.jpg", self.problems())
        web.unlink()
        os.mkfifo(web, 0o600)
        probs = self.problems()
        self.assertTrue(any(p.startswith("unknown entry") or p.startswith("unreadable") for p in probs), probs)
        self.assertEqual(target.read_bytes(), b"secret target")

    def test_cli_and_health_report_damage_read_only(self):
        state = self.tmp / "state"
        state.mkdir(mode=0o700)
        settings = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}
        (state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": settings}))
        original = jpeg(exif())
        sha = self.put(original)
        self.replace(self.web(sha, "jpg"), original)
        before = snapshot(self.root)
        boom = mock.Mock(side_effect=AssertionError("writer called"))
        with mock.patch.multiple(media, web_copy=boom, _write_new=boom, _private_dir=boom, _open_root=boom):
            self.assertEqual(self.problems(), [f"web content mismatch: {sha[:12]}"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out): code = health.main(["--state", str(state), "--media", str(self.root)], now=NOW)
        lines = out.getvalue().splitlines()
        self.assertEqual((code, len(lines)), (1, 1))
        doc = json.loads(lines[0])
        self.assertEqual([p for p in doc["problems"] if p["check"] == "media-store"], [{"check": "media-store", "detail": "1 problem(s)"}])
        for leak in (str(self.tmp), sha[:12], "web content", "GPS"): self.assertNotIn(leak, lines[0])
        self.assertEqual(snapshot(self.root), before)
        boom.assert_not_called()

if __name__ == "__main__":
    unittest.main()
