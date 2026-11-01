"""RF1650-5 (H10): store_original keeps only a timezone-aware ISO-8601 received_at; refusals write nothing."""

import json, os, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import media
from hass.content_model import REPO_ROOT

FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "media"
JPEG, PNG = (FIX / "pixel.jpg").read_bytes(), (FIX / "pixel.png").read_bytes()
MSG = "received_at must be a timezone-aware ISO-8601 time"
GOOD = ("2026-11-02T18:00:00+00:00", "2026-11-02T10:00:00-08:00", "2026-11-02T18:00:00.123456+00:00")
BAD = ("2026-11-02T18:00:00", "2026-11-02", "yesterday", "", None, 1730570400, "2026-13-02T18:00:00+00:00")


class MediaTimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"

    def store(self, data, at, root=None):
        return media.store_original(self.root if root is None else root, data, received_at=at, source="fixture")

    def sidecar(self, out):
        return json.loads(Path(out["path"]).with_suffix(".json").read_text("utf-8"))

    def test_aware_times_are_stored_verbatim(self):
        for i, at in enumerate(GOOD):
            with self.subTest(at=at):
                out = self.store(JPEG + b"\x00" * i, at)  # distinct bytes, so each call writes its own sidecar
                self.assertFalse(out["duplicate"])
                self.assertEqual(self.sidecar(out)["received_at"], at)

    def test_bad_times_refused_with_fixed_message(self):
        for at in BAD:
            with self.subTest(at=at):
                with self.assertRaises(ValueError) as cm:  # an int is a ValueError too, never a TypeError
                    self.store(JPEG, at)
                self.assertEqual(str(cm.exception), MSG)

    def test_refusal_on_missing_root_creates_nothing(self):
        for at in BAD:
            with self.subTest(at=at):
                with self.assertRaises(ValueError): self.store(PNG, at)
                self.assertFalse(os.path.lexists(self.root))
                self.assertEqual(os.listdir(self.tmp), [])

    def test_refusal_on_existing_root_writes_no_original(self):
        first = self.store(JPEG, GOOD[0])
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        for at in BAD:
            with self.subTest(at=at):
                with self.assertRaises(ValueError): self.store(PNG, at)
                self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")), before)
        self.assertFalse(any(p.suffix == ".png" for p in (self.root / "originals").rglob("*")))
        self.assertEqual(self.sidecar(first)["received_at"], GOOD[0])

    def test_duplicate_keeps_first_sidecar(self):
        first = self.store(PNG, GOOD[0])
        side = Path(first["path"]).with_suffix(".json")
        raw = side.read_bytes()
        again = self.store(PNG, GOOD[1])
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["path"], first["path"])
        self.assertEqual(side.read_bytes(), raw)
        self.assertEqual(self.sidecar(again)["received_at"], GOOD[0])

    def test_bad_time_on_duplicate_still_refused(self):
        first = self.store(PNG, GOOD[0])
        raw = Path(first["path"]).with_suffix(".json").read_bytes()
        with self.assertRaises(ValueError) as cm: self.store(PNG, "2026-11-02T18:00:00")
        self.assertEqual(str(cm.exception), MSG)
        self.assertEqual(Path(first["path"]).with_suffix(".json").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
