"""RF1501-11: verify_store reports a hash-valid original whose bytes do not sniff as its extension's kind."""

import contextlib, hashlib, io, json, os, subprocess, sys, tempfile, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import health, media
from hass.content_model import REPO_ROOT

FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "media"
JPEG, PNG = (FIX / "pixel.jpg").read_bytes(), (FIX / "pixel.png").read_bytes()
AT = "2026-11-02T18:00:00+00:00"
NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)

def snap(root):
    out = {}
    for d, dirs, names in os.walk(root):
        for n in dirs + names:
            p = Path(d, n)
            st = os.lstat(p)
            out[str(p.relative_to(root))] = (p.read_bytes() if p.is_file() else None, st.st_mtime_ns, st.st_mode)
    return out

class OriginalKindTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"
        media.store_original(self.root, JPEG, received_at=AT, source="fixture")
        sha = hashlib.sha256(JPEG).hexdigest()
        self.template = json.loads((self.root / "originals" / sha[:2] / f"{sha}.json").read_text())

    def plant(self, data, ext, sidecar=True, kind=None):
        """Hash-valid original under its own sha name at `ext`, with an extension-consistent sidecar."""
        sha = hashlib.sha256(data).hexdigest()
        d = self.root / "originals" / sha[:2]
        d.mkdir(mode=0o700, exist_ok=True)
        (d / f"{sha}.{ext}").write_bytes(data)
        os.chmod(d / f"{sha}.{ext}", 0o600)
        if sidecar:
            meta = dict(self.template, sha256=sha, kind=kind or ("jpeg" if ext == "jpg" else "png"), bytes=len(data))
            (d / f"{sha}.json").write_text(json.dumps(meta))
            os.chmod(d / f"{sha}.json", 0o600)
        return sha

    def clean(self):  # drop the setUp original so each test sees only what it plants
        for p in list(self.root.rglob("*")):
            if p.is_file(): p.unlink()

    def run_cli(self):
        before = snap(self.root)
        run = subprocess.run([sys.executable, "hass/media.py", "verify", "--root", str(self.root)], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual((run.stderr, run.stdout.count("\n")), ("", 1))
        self.assertEqual(snap(self.root), before)
        return run.returncode, json.loads(run.stdout), run.stdout

    def test_hash_valid_opposite_kind_original_is_a_problem(self):
        self.clean()
        a, b = self.plant(JPEG, "png"), self.plant(PNG, "jpg")
        out = media.verify_store(self.root)
        self.assertEqual(out["problems"], sorted([f"original kind: {a[:12]}", f"original kind: {b[:12]}"]))
        self.assertEqual(out["result"], "problems")

    def test_hash_valid_unsniffable_original_is_a_problem(self):
        self.clean()
        shas = [self.plant(d, e) for d, e in ((b"not an image", "jpg"), (JPEG[:6], "jpg"), (PNG[:12], "png"))]
        self.assertEqual(media.verify_store(self.root)["problems"], sorted(f"original kind: {s[:12]}" for s in shas))

    def test_cli_kind_failure_is_redacted_and_read_only(self):
        self.clean()
        sha = self.plant(JPEG, "png")
        code, out, text = self.run_cli()
        self.assertEqual((code, out), (1, media.verify_store(self.root)))
        self.assertEqual((out["originals"], out["web"], out["problems"]), (1, 0, [f"original kind: {sha[:12]}"]))
        for leak in (sha, str(self.tmp), str(REPO_ROOT)): self.assertNotIn(leak, text)
        self.assertFalse((self.root / "web").exists())

    def test_invalid_original_kind_does_not_trigger_derivative_checks(self):
        self.clean()
        sha = self.plant(JPEG, "png")
        w = self.root / "web" / sha[:2]
        w.mkdir(parents=True, mode=0o700)
        (w / f"{sha}.png").write_bytes(b"whatever")
        os.chmod(w / f"{sha}.png", 0o600)
        self.assertEqual(media.verify_store(self.root)["problems"], [f"original kind: {sha[:12]}"])

    def test_kind_checks_preserve_hash_and_sidecar_precedence(self):
        self.clean()
        sha = self.plant(JPEG, "png")
        (self.root / "originals" / sha[:2] / f"{sha}.json").write_text("{}")
        self.assertEqual(media.verify_store(self.root)["problems"], sorted([f"original kind: {sha[:12]}", f"sidecar invalid: {sha[:12]}"]))
        self.clean()
        bad = self.plant(b"x" * 8, "jpg")
        (self.root / "originals" / bad[:2] / f"{bad}.jpg").write_bytes(b"y" * 8)  # hash mismatch, not a kind problem
        self.assertEqual(media.verify_store(self.root)["problems"], [f"content mismatch: {bad[:12]}"])
        self.clean()
        sha = self.plant(JPEG, "png")
        with mock.patch.object(media, "_existing", side_effect=OSError("x")):
            self.assertEqual(media.verify_store(self.root)["problems"], [f"unreadable: {sha[:12]}"])

    def test_healthy_original_only_and_derivative_controls(self):
        self.assertEqual(media.verify_store(self.root)["result"], "ok")
        media.store_original(self.root, PNG, received_at=AT, source="fixture")
        media.web_copy(self.root, hashlib.sha256(JPEG).hexdigest())
        self.assertEqual(media.verify_store(self.root), {"result": "ok", "originals": 2, "web": 1, "problems": []})
        self.clean()
        self.plant(JPEG + b"\0\0", "jpg")  # trailing NUL padding is still sniffed as a JPEG
        self.assertEqual(media.verify_store(self.root)["problems"], [])

    def test_health_kind_failure_is_count_only(self):
        self.clean()
        sha = self.plant(JPEG, "png")
        state = self.tmp / "state"
        state.mkdir(mode=0o700)
        settings = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}
        (state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": settings}))
        before, boom = snap(self.root), mock.Mock(side_effect=AssertionError("writer called"))
        out = io.StringIO()
        with mock.patch.multiple(media, web_copy=boom, _write_new=boom, _private_dir=boom, _open_root=boom), \
                contextlib.redirect_stdout(out):
            code = health.main(["--state", str(state), "--media", str(self.root)], now=NOW)
        doc = json.loads(out.getvalue().splitlines()[0])
        self.assertEqual(code, 1)
        self.assertEqual([p for p in doc["problems"] if p["check"] == "media-store"], [{"check": "media-store", "detail": "1 problem(s)"}])
        for leak in (str(self.tmp), sha[:12]): self.assertNotIn(leak, out.getvalue())
        self.assertEqual(snap(self.root), before)
        boom.assert_not_called()

if __name__ == "__main__":
    unittest.main()
