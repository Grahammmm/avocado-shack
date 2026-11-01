"""RF1650-5 (H10): store_original keeps only a timezone-aware ISO-8601 received_at; a refused time writes nothing."""

import hashlib, json, os, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import media
from hass.content_model import REPO_ROOT

FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "media"
JPEG, PNG = (FIX / "pixel.jpg").read_bytes(), (FIX / "pixel.png").read_bytes()
MSG = "received_at must be a timezone-aware ISO-8601 time"
GOOD = ("2026-11-02T18:00:00+00:00", "2026-11-02T10:00:00-08:00", "2026-11-02T18:00:00.123456+00:00")
NAIVE = ("2026-11-02T18:00:00", "2026-11-02")
JUNK = ("yesterday", "", None, 1730570400, " 2026-11-02T18:00:00+00:00x")


def files(root):
    return sorted(str(Path(d, n).relative_to(root)) for d, _, names in os.walk(root) for n in names)


class MediaTimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)
        self.root = self.tmp / "media"

    def store(self, at, data=JPEG):
        return media.store_original(self.root, data, received_at=at, source="fixture")

    def sidecar(self, data):
        sha = hashlib.sha256(data).hexdigest()
        return json.loads((self.root / "originals" / sha[:2] / f"{sha}.json").read_text(encoding="utf-8"))

    def test_aware_times_are_stored_verbatim(self):
        for i, at in enumerate(GOOD):
            data = PNG if i == 1 else JPEG + b"\0" * i  # distinct bytes so each call writes its own sidecar
            with self.subTest(at=at):
                self.assertFalse(self.store(at, data)["duplicate"])
                self.assertEqual(self.sidecar(data)["received_at"], at)

    def test_naive_and_junk_times_refused_with_fixed_message(self):
        for at in NAIVE + JUNK:
            with self.subTest(at=at):
                with self.assertRaises(ValueError) as cm: self.store(at)
                self.assertEqual(str(cm.exception), MSG)
                self.assertIsNone(cm.exception.__cause__)

    def test_refusal_creates_no_root(self):
        for at in NAIVE + JUNK:
            with self.subTest(at=at):
                with self.assertRaises(ValueError): self.store(at)
                self.assertFalse(os.path.lexists(self.root))

    def test_refusal_on_existing_root_writes_no_original(self):
        self.store(GOOD[0], PNG)
        before = files(self.root)
        for at in NAIVE + JUNK:
            with self.subTest(at=at):
                with self.assertRaises(ValueError): self.store(at, JPEG)
                self.assertEqual(files(self.root), before)
        sha = hashlib.sha256(JPEG).hexdigest()
        self.assertFalse((self.root / "originals" / sha[:2]).exists())

    def test_time_checked_before_bad_bytes(self):
        with self.assertRaises(ValueError) as cm: self.store("2026-11-02", b"not a photo")
        self.assertEqual(str(cm.exception), MSG)
        self.assertFalse(os.path.lexists(self.root))

    def test_duplicate_keeps_first_sidecar(self):
        self.store(GOOD[0])
        first = self.sidecar(JPEG)
        again = self.store(GOOD[1])
        self.assertTrue(again["duplicate"])
        self.assertEqual(self.sidecar(JPEG), first)
        self.assertEqual(first["received_at"], GOOD[0])

    def test_duplicate_with_bad_time_is_refused_not_reported(self):
        self.store(GOOD[0])
        with self.assertRaises(ValueError): self.store("2026-11-02T18:00:00")
        self.assertEqual(self.sidecar(JPEG)["received_at"], GOOD[0])


if __name__ == "__main__":
    unittest.main()
