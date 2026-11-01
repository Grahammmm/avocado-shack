"""RF1710-6 (H10/H19): `health.py --media DIR` reports a damaged photo store as `media-store` (count only).

Temp 0700 state and store dirs built with media.store_original, a fixed clock, never the real state or store.
"""
import contextlib, hashlib, io, json, os, tempfile, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import health, media
from hass.content_model import REPO_ROOT

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "media"
JPEG, PNG = (FIX / "pixel.jpg").read_bytes(), (FIX / "pixel.png").read_bytes()
J, P = hashlib.sha256(JPEG).hexdigest(), hashlib.sha256(PNG).hexdigest()
SETTINGS = {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid", "approvalTtlSeconds": 600}
UNSAFE = {"check": "media-store", "detail": "media store unsafe"}


class HealthMediaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.state, self.store, self.seen = self.tmp / "state", self.tmp / "media", self.tmp / "fp-health"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": SETTINGS}))
        for data in (JPEG, PNG): media.store_original(self.store, data, received_at=NOW.isoformat(), source="fixture")
        media.web_copy(self.store, J)

    def run_health(self, *extra, media_dir=None):
        args = ["--state", str(self.state), *extra, *([] if media_dir is None else ["--media", str(media_dir)])]
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = health.main(args, now=NOW)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        for leak in (str(self.tmp), J[:12], P[:12], "content mismatch", "symlink", "unknown entry"):
            self.assertNotIn(leak, lines[0])  # never a path, sha prefix or verify_store problem text
        return code, json.loads(lines[0]), lines[0]

    def media_problems(self, doc):
        return [p for p in doc["problems"] if p["check"] == "media-store"]

    def damage(self):  # same length, so the sidecar byte count still matches: exactly one store problem
        path = self.store / "originals" / J[:2] / f"{J}.jpg"
        path.write_bytes(JPEG[:-1] + bytes([JPEG[-1] ^ 1]))

    def test_healthy_store_is_ok(self):
        self.assertEqual(media.verify_store(self.store)["result"], "ok")
        code, doc, _ = self.run_health(media_dir=self.store)
        self.assertEqual((code, doc["ok"], self.media_problems(doc)), (0, True, []))

    def test_changed_original_is_one_problem(self):
        self.damage()
        code, doc, _ = self.run_health(media_dir=self.store)
        self.assertEqual((code, doc["problems"]), (1, [{"check": "media-store", "detail": "1 problem(s)"}]))

    def test_several_problems_are_counted_not_named(self):
        self.damage()
        (self.store / "originals" / P[:2] / f"{P}.json").unlink()
        os.symlink(self.tmp, self.store / "originals" / "zz")
        code, doc, _ = self.run_health(media_dir=self.store)
        n = len(media.verify_store(self.store)["problems"])
        self.assertGreaterEqual(n, 3)
        self.assertEqual((code, self.media_problems(doc)), (1, [{"check": "media-store", "detail": f"{n} problem(s)"}]))

    def test_missing_dir_is_unsafe_and_not_created(self):
        missing = self.tmp / "nope"
        code, doc, _ = self.run_health(media_dir=missing)
        self.assertEqual((code, doc["problems"]), (1, [UNSAFE]))
        self.assertFalse(os.path.lexists(missing))

    def test_symlink_and_repository_roots_are_unsafe(self):
        os.symlink(self.store, link := self.tmp / "link")
        for root in (link, REPO_ROOT, REPO_ROOT / "hass"):
            with self.subTest(root=root.name):
                self.assertEqual(self.run_health(media_dir=root)[1]["problems"], [UNSAFE])

    def test_state_dir_or_inside_it_is_unsafe_and_never_verified(self):
        inside = self.state / "media"
        media.store_original(inside, JPEG, received_at=NOW.isoformat(), source="fixture")
        os.symlink(self.state, link := self.tmp / "state-link")
        with mock.patch("hass.health.verify_store") as verify:
            for root in (self.state, inside, f"{self.state}/", f"{self.state}/.", self.tmp / "x" / ".." / "state", link):
                with self.subTest(root=str(root)):
                    code, doc, _ = self.run_health(media_dir=root)
                    self.assertEqual((code, self.media_problems(doc)), (1, [UNSAFE]))
        verify.assert_not_called()

    def test_unreadable_store(self):
        with mock.patch("hass.health.verify_store", side_effect=PermissionError(13, "denied", str(self.store))):
            code, doc, _ = self.run_health(media_dir=self.store)
        self.assertEqual((code, doc["problems"]), (1, [{"check": "media-store", "detail": "media store unreadable"}]))

    def test_without_media_output_is_unchanged(self):
        self.damage()
        with mock.patch("hass.health.verify_store") as verify:
            plain = self.run_health()
            self.assertEqual(health.check(self.state, now=NOW), health.check(self.state, now=NOW, media=None))
        verify.assert_not_called()
        self.assertEqual(plain[:2], (0, {"ok": True, "problems": [], "info": plain[1]["info"],
                                         "fingerprint": health.fingerprint([]), "notify": False}))
        self.assertNotIn("media", plain[2])
        self.store = self.tmp / "store2"  # a healthy store adds nothing: the line is byte-identical
        media.store_original(self.store, PNG, received_at=NOW.isoformat(), source="fixture")
        self.assertEqual(self.run_health(media_dir=self.store), plain)

    def test_seen_notifies_once_per_change(self):
        seen = ("--seen", str(self.seen))
        first = self.run_health(*seen, media_dir=self.store)[1]
        self.assertEqual((first["ok"], first["notify"]), (True, True))
        self.assertFalse(self.run_health(*seen, media_dir=self.store)[1]["notify"])
        self.damage()
        changed = self.run_health(*seen, media_dir=self.store)[1]
        self.assertEqual((changed["notify"], changed["fingerprint"] != first["fingerprint"]), (True, True))
        again = self.run_health(*seen, media_dir=self.store)[1]
        self.assertEqual((again["notify"], again["fingerprint"]), (False, changed["fingerprint"]))
        self.assertEqual(self.seen.read_text("utf-8").strip(), changed["fingerprint"])


if __name__ == "__main__":
    unittest.main()
