"""H10 part 1 tests: private photo original store (type, size, sha256, no duplicates). Temp 0700 roots only."""

import hashlib, json, os, stat, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import editor, media
from hass.content_model import REPO_ROOT

FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "media"
JPEG, PNG = (FIX / "pixel.jpg").read_bytes(), (FIX / "pixel.png").read_bytes()
AT = "2026-11-02T18:00:00+00:00"

def files(root):
    """Sorted relpaths of every non-dir entry under root (symlinks not followed)."""
    out = []
    for dirpath, dirs, names in os.walk(root):
        out += [str(Path(dirpath, n).relative_to(root)) for n in names]
        out += [str(Path(dirpath, d).relative_to(root)) for d in dirs if Path(dirpath, d).is_symlink()]
    return sorted(out)

def mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)

class MediaTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"

    def store(self, data, root=None, source="fixture"):
        return media.store_original(self.root if root is None else root, data, received_at=AT, source=source)

    def target(self, data, ext, make=False):
        sha = hashlib.sha256(data).hexdigest()
        path = self.root / "originals" / sha[:2] / f"{sha}.{ext}"
        for d in (self.root, path.parent.parent, path.parent) if make else (): d.mkdir(mode=0o700, exist_ok=True)
        return path, sha

    def test_accept_layout_and_sidecar(self):
        for data, kind, ext in ((JPEG, "jpeg", "jpg"), (PNG, "png", "png")):
            rec = self.store(data)
            path, sha = self.target(data, ext)
            self.assertEqual(rec, {"sha256": sha, "kind": kind, "bytes": len(data), "path": str(path), "duplicate": False})
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(mode(path), 0o600)
            for d in (self.root, self.root / "originals", path.parent): self.assertEqual(mode(d), 0o700)
            side = path.with_suffix(".json")
            self.assertEqual(mode(side), 0o600)
            self.assertEqual(json.loads(side.read_text("utf-8")), {
                "sha256": sha, "kind": kind, "bytes": len(data), "received_at": AT, "source": "fixture"})
        self.assertEqual(len(files(self.root)), 4)  # two originals + two sidecars, no temp files left

    def test_duplicate_returns_existing_entry(self):
        first = self.store(JPEG)
        side = Path(first["path"]).with_suffix(".json")
        before = side.read_bytes()
        again = media.store_original(self.root, JPEG, received_at="2026-11-03T09:00:00+00:00", source="other")
        self.assertTrue(again["duplicate"])
        self.assertEqual({**again, "duplicate": False}, first)
        self.assertEqual(side.read_bytes(), before)  # the first sighting's sidecar is kept
        self.assertEqual(len(files(self.root)), 2)  # one original + one sidecar

    def test_lost_sidecar_is_restored_on_repeat(self):
        side = Path(self.store(PNG)["path"]).with_suffix(".json")
        side.unlink()
        self.assertTrue(self.store(PNG)["duplicate"])
        self.assertEqual(json.loads(side.read_text("utf-8"))["kind"], "png")

    def test_mime_and_name_lies_are_ignored(self):
        self.assertEqual(media.sniff(PNG), "png")
        rec = self.store(PNG)  # a sender claiming image/jpeg + fixture.jpg changes nothing: the API takes no name
        self.assertEqual(rec["kind"], "png")
        self.assertTrue(rec["path"].endswith(".png"))
        with self.assertRaises(TypeError): media.store_original(self.root, PNG, received_at=AT, source="fixture",
                                                                 mime_type="image/jpeg")

    def assertRefused(self, data, code, root=None):
        with self.assertRaises(media.Refused) as cm: self.store(data, root)
        self.assertEqual(cm.exception.code, code)
        reply = cm.exception.reply
        self.assertTrue(reply)
        for leak in (str(self.tmp), hashlib.sha256(data).hexdigest()[:8], "/"): self.assertNotIn(leak, reply)
        return cm.exception

    def test_refusals_have_replies_and_write_nothing(self):
        cases = [(b"", "empty"), (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64, "unsupported-type"),
                 (b"GIF89a\x01\x00\x01\x00" + b"\x00" * 32, "unsupported-type"), (b"plain text", "unsupported-type"),
                 (JPEG[:-2], "truncated"), (JPEG[:-2] + b"\x00\x00", "truncated"),
                 (PNG[:PNG.index(b"IEND")], "truncated"), (media.KINDS["png"] + b"IEND", "truncated"),
                 (media.KINDS["png"] + media.PNG_END[:-1], "truncated"),
                 (PNG[:-4] + b"\x00\x00\x00\x00", "truncated"), (PNG[:-4] + b"\xae\x42\x60\x83", "truncated")]
        cases += [(PNG[:-n], "truncated") for n in (1, 2, 3, 4)]  # IEND CRC partly or wholly missing
        for data, code in cases:
            with self.subTest(code=code, head=data[:12]):
                self.assertRefused(data, code)
                self.assertEqual(files(self.root), [])
        with mock.patch.object(media, "MAX_BYTES", len(JPEG) - 1):
            self.assertRefused(JPEG, "too-large")
        self.assertEqual(files(self.root), [])
        self.assertEqual(self.store(JPEG + b"\x00\x00")["kind"], "jpeg")  # trailing NUL padding after EOI is fine
        self.assertEqual(self.store(PNG + b"\x00\x00")["kind"], "png")  # and after a complete IEND chunk

    def test_unsafe_roots_write_nothing(self):
        fake_repo = self.tmp / "repo"
        fake_repo.mkdir(mode=0o700)
        with mock.patch.object(editor, "REPO_ROOT", fake_repo):
            with self.assertRaises(editor.UnsafeState): self.store(JPEG, fake_repo / "media")
        self.assertFalse((fake_repo / "media").exists())
        with self.assertRaises(editor.UnsafeState): self.store(JPEG, REPO_ROOT / "hass" / "media-store-test")
        self.assertFalse((REPO_ROOT / "hass" / "media-store-test").exists())
        open_root = self.tmp / "open"
        open_root.mkdir()
        os.chmod(open_root, 0o755)
        with self.assertRaises(editor.UnsafeState): self.store(JPEG, open_root)
        self.assertEqual(files(open_root), [])
        real = self.tmp / "real"
        real.mkdir(mode=0o700)
        (self.tmp / "link").symlink_to(real)
        with self.assertRaises(editor.UnsafeState): self.store(JPEG, self.tmp / "link")
        self.assertEqual(files(real), [])
        for empty in ("", None):
            with self.assertRaises(editor.UnsafeState): media.store_original(empty, JPEG, received_at=AT, source="x")

    def test_corrupt_store_is_left_unchanged(self):
        path, _ = self.target(JPEG, "jpg", make=True)
        path.write_bytes(b"other bytes")
        self.assertRefused(JPEG, "corrupt-store")
        self.assertEqual(path.read_bytes(), b"other bytes")
        self.assertEqual(files(self.root), [str(path.relative_to(self.root))])

    def test_planted_symlinks_are_refused_and_not_followed(self):
        victim = self.tmp / "victim"
        victim.write_bytes(b"keep me")
        path, sha = self.target(PNG, "png", make=True)
        for planted in (path, path.with_suffix(".json")):
            with self.subTest(planted=planted.name):
                planted.symlink_to(victim)
                self.assertRefused(PNG, "corrupt-store")
                self.assertEqual(victim.read_bytes(), b"keep me")
                self.assertTrue(planted.is_symlink())
                planted.unlink()
                path.unlink(missing_ok=True)
        self.root.joinpath("originals", sha[:2]).rmdir()
        self.root.joinpath("originals", sha[:2]).symlink_to(self.tmp, target_is_directory=True)
        self.assertRefused(PNG, "corrupt-store")
        self.assertEqual(sorted(os.listdir(self.tmp)), ["media", "victim"])

    def test_bad_source_label_writes_nothing(self):
        for bad in ("Owner Phone", "", "a" * 33, "fixture\n", None):
            with self.subTest(source=bad):
                with self.assertRaises(ValueError): self.store(JPEG, source=bad)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.store(JPEG, source="a" * 32)["kind"], "jpeg")
