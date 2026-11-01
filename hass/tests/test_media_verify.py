"""RF1710-2 (H10) tests: `media.py verify --root DIR` re-hashes the private photo store and never changes it."""

import hashlib, json, os, re, stat, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import media
from hass.content_model import REPO_ROOT

FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "media"
JPEG, PNG = (FIX / "pixel.jpg").read_bytes(), (FIX / "pixel.png").read_bytes()
J, P = hashlib.sha256(JPEG).hexdigest(), hashlib.sha256(PNG).hexdigest()
AT = "2026-11-02T18:00:00+00:00"

def snapshot(root):
    """{rel: (content or link target, mtime_ns, mode)} for every entry under root; links are never followed."""
    out = {}
    for dirpath, dirs, names in os.walk(root):
        for name in dirs + names:
            path = Path(dirpath, name)
            st = os.lstat(path)
            body = os.readlink(path) if stat.S_ISLNK(st.st_mode) else path.read_bytes() if stat.S_ISREG(st.st_mode) else None
            out[str(path.relative_to(root))] = (body, st.st_mtime_ns, stat.S_IMODE(st.st_mode))
    return out

class VerifyStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"

    def build(self, name="media"):
        """One JPEG + one PNG original and a web copy of the JPEG, made by the real writers."""
        self.root = self.tmp / name
        for data in (JPEG, PNG): media.store_original(self.root, data, received_at=AT, source="fixture")
        media.web_copy(self.root, J)
        return self.root

    def orig(self, sha, ext):
        return self.root / "originals" / sha[:2] / f"{sha}.{ext}"

    def verify(self, code=None):
        """verify_store (or the CLI when code is given); asserts read-only and no full sha / absolute path in output."""
        before = snapshot(self.root) if self.root.is_dir() else None
        if code is None: out = media.verify_store(self.root)
        else:
            run = subprocess.run([sys.executable, "hass/media.py", "verify", "--root", str(self.root)], cwd=REPO_ROOT,
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual((run.returncode, run.stderr, run.stdout.count("\n")), (code, "", 1))
            out = json.loads(run.stdout)
        text = json.dumps(out)
        self.assertIsNone(re.search(r"[0-9a-f]{64}", text))
        for leak in (str(self.tmp), str(REPO_ROOT)): self.assertNotIn(leak, text)
        self.assertEqual(snapshot(self.root) if self.root.is_dir() else None, before)
        return out

    def problems(self, code: "int | None" = 1):
        out = self.verify(code)
        self.assertEqual(out["result"], "problems")
        return out["problems"]

    def test_clean_store_is_ok(self):
        self.build()
        self.assertEqual(self.verify(0), {"result": "ok", "originals": 2, "web": 1, "problems": []})
        self.assertEqual(media.verify_store(str(self.root))["result"], "ok")

    def test_empty_root_is_ok_with_zeros(self):
        self.root.mkdir(mode=0o700)
        self.assertEqual(self.verify(0), {"result": "ok", "originals": 0, "web": 0, "problems": []})

    def test_content_mismatch(self):
        self.build()
        path = self.orig(J, "jpg")
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0xFF  # same length, so only the hash disagrees
        os.chmod(path, 0o600)
        path.write_bytes(bytes(data))
        self.assertEqual(self.problems(1), [f"content mismatch: {J[:12]}"])

    def test_sidecar_missing_invalid_and_orphan(self):
        meta = lambda **kw: json.dumps({"sha256": P, "kind": "png", "bytes": len(PNG), **kw}).encode()  # noqa: E731
        cases = {"missing": (None, "sidecar missing"), "bytes": (meta(bytes=len(PNG) + 1), "sidecar invalid"),
                 "kind": (meta(kind="jpeg"), "sidecar invalid"), "sha": (meta(sha256=J), "sidecar invalid"),
                 "not-json": (b"{not json", "sidecar invalid"), "list": (b"[1, 2]", "sidecar invalid")}
        for name, (body, want) in cases.items():
            with self.subTest(name):
                side = self.orig(P, "json").relative_to(self.root)
                side = self.build(name) / side
                side.unlink()
                if body is not None:
                    side.write_bytes(body)
                    os.chmod(side, 0o600)
                self.assertEqual(self.problems(), [f"{want}: {P[:12]}"])
        self.build("orphan")
        self.orig(P, "png").unlink()
        self.assertEqual(self.problems(), [f"orphan sidecar: {P[:12]}"])
        self.assertEqual(self.verify()["originals"], 1)

    def test_leftover_temp(self):
        self.build()
        tmp = self.orig(J, "jpg").parent / ".tmp-xyz"
        tmp.write_bytes(JPEG[:10])
        os.chmod(tmp, 0o600)
        self.assertEqual(self.problems(), [f"leftover temp: {J[:2]}"])

    def test_modes(self):
        self.build()
        os.chmod(self.orig(J, "jpg"), 0o644)
        self.assertEqual(self.problems(), [f"mode: originals/{J[:2]}/{J[:12]}.jpg"])
        os.chmod(self.orig(J, "jpg"), 0o600)
        for path in (self.root, self.root / "web", self.root / "web" / J[:2]): os.chmod(path, 0o755)
        self.assertEqual(self.problems(), ["mode: .", "mode: web", f"mode: web/{J[:2]}"])

    def test_symlinks_are_named_and_never_followed(self):
        self.build()
        secret = self.tmp / "secret.jpg"
        secret.write_bytes(JPEG)
        os.chmod(secret, 0)
        (self.orig(J, "jpg").parent / f"{J[:2]}{'0' * 62}.jpg").symlink_to(secret)
        (self.root / "originals" / "zz").symlink_to(self.tmp, target_is_directory=True)
        with mock.patch.object(media.os, "open", wraps=os.open) as opened, \
                mock.patch.object(media.os, "scandir", wraps=os.scandir) as scanned:
            got = self.problems(None)
        self.assertEqual(got, [f"symlink: originals/{J[:2]}/{J[:2]}0000000000.jpg", "symlink: originals/zz"])
        touched = [str(c.args[0]) for c in opened.call_args_list + scanned.call_args_list]
        self.assertFalse([t for t in touched if "secret" in t or t.endswith(("zz", "0000.jpg"))], touched)
        (self.root / "web").rename(self.tmp / "web-real")
        (self.root / "web").symlink_to(self.tmp / "web-real", target_is_directory=True)
        self.assertEqual(self.verify(1)["problems"][-1], "symlink: web")

    def test_unreadable_directories_are_problems_not_crashes(self):
        self.build()
        shard = self.root / "originals" / J[:2]
        os.chmod(shard, 0)
        self.addCleanup(os.chmod, shard, 0o700)
        got = self.problems(1)  # CLI: exit 1, one JSON line, no absolute path, store unchanged
        self.assertEqual(got, [f"mode: originals/{J[:2]}", f"unreadable: originals/{J[:2]}", f"web orphan: {J[:12]}"])
        os.chmod(shard, 0o600)  # names listable, entries not stat-able
        got = media.verify_store(self.root)["problems"]
        self.assertIn(f"unreadable: originals/{J[:2]}/{J[:12]}.jpg", got)
        self.assertFalse([p for p in got if str(self.tmp) in p], got)
        os.chmod(shard, 0o700)
        os.chmod(self.root, 0)
        self.addCleanup(os.chmod, self.root, 0o700)
        self.assertEqual(self.problems(1), ["mode: .", "unreadable: ."])
        os.chmod(self.root, 0o700)
        self.assertEqual(self.verify(0)["result"], "ok")

    def test_unknown_entries(self):
        self.build()
        wrong = self.root / "originals" / ("00" if P[:2] != "00" else "01")
        wrong.mkdir(mode=0o700)
        os.rename(self.orig(P, "png"), wrong / f"{P}.png")
        rel = f"originals/{wrong.name}/{P[:12]}.png"
        self.assertEqual(self.problems(), [f"orphan sidecar: {P[:12]}", f"unknown entry: {rel}"])
        os.rename(wrong / f"{P}.png", self.orig(P, "png"))
        (self.root / "originals" / "AB").mkdir(mode=0o700)
        for path in (self.root / "notes.txt", self.root / "web" / J[:2] / f"{J}.json"):
            path.write_bytes(b"x")
            os.chmod(path, 0o600)
        self.assertEqual(self.problems(), ["unknown entry: notes.txt", "unknown entry: originals/AB",
                                           f"unknown entry: web/{J[:2]}/{J[:12]}.json"])

    def test_web_orphan_and_web_kind(self):
        self.build()
        web = self.root / "web" / J[:2] / f"{J}.jpg"
        os.rename(web, web.with_suffix(".png"))
        self.assertEqual(self.problems(), [f"web kind: {J[:12]}"])
        os.rename(web.with_suffix(".png"), web)
        for ext in ("jpg", "json"): self.orig(J, ext).unlink()
        out = self.verify(1)
        self.assertEqual((out["problems"], out["originals"], out["web"]), ([f"web orphan: {J[:12]}"], 1, 1))

    def test_unsafe_roots_create_nothing(self):
        self.assertEqual(self.verify(2), {"result": "unsafe", "problems": ["media root does not exist"]})
        self.assertFalse(self.root.exists())
        real = self.build("real")
        self.root = self.tmp / "link"
        self.root.symlink_to(real, target_is_directory=True)
        self.assertEqual(self.verify(2)["result"], "unsafe")
        link = self.root
        for spelling in ("/", "/.", "/./", "//", "/./."):  # lstat would follow the link for these spellings
            with self.subTest(spelling=spelling), \
                    mock.patch.object(media.os, "scandir", wraps=os.scandir) as scanned:
                self.assertEqual(media.verify_store(str(link) + spelling),
                                 {"result": "unsafe", "problems": ["media root must be a real directory, not a symlink"]})
                self.assertEqual(scanned.call_count, 0)
                run = subprocess.run([sys.executable, "hass/media.py", "verify", "--root", str(link) + spelling],
                                     cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
                self.assertEqual((run.returncode, json.loads(run.stdout)["result"]), (2, "unsafe"))
            with self.subTest(real=spelling):
                self.assertEqual(media.verify_store(str(real) + spelling)["result"], "ok")
        for root in (REPO_ROOT, REPO_ROOT / "hass", REPO_ROOT / "hass" / ".." / "hass", FIX / "pixel.jpg"):
            with self.subTest(root=str(root)):
                self.assertEqual(media.verify_store(root)["result"], "unsafe")
        for root in (None, ""): self.assertEqual(media.verify_store(root)["result"], "unsafe")
        run = subprocess.run([sys.executable, "hass/media.py", "verify"], cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stdout), (2, ""))

if __name__ == "__main__":
    unittest.main()
