"""RF1500-12 (H10/H19) tests: `media.py verify` calls a sidecar invalid when a present received_at is not zoned,
a present source is not a source name, or bytes is not an int; an absent received_at/source stays acceptable."""

import hashlib, json, os, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import media
from hass.content_model import REPO_ROOT

FIX = REPO_ROOT / "hass" / "tests" / "fixtures" / "media"
JPEG = (FIX / "pixel.jpg").read_bytes()
J = hashlib.sha256(JPEG).hexdigest()
AT = "2026-11-02T18:00:00+00:00"

class SidecarFieldsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        os.chmod(self.tmp, 0o700)

    def build(self, name):
        root = self.tmp / name
        media.store_original(root, JPEG, received_at=AT, source="fixture")
        return root

    def edit(self, name, **changes):
        """A store made by store_original whose sidecar has `changes` applied (a value of ... drops the key)."""
        root = self.build(name)
        side = root / "originals" / J[:2] / f"{J}.json"
        meta = json.loads(side.read_bytes())
        self.assertEqual(set(meta), {"sha256", "kind", "bytes", "received_at", "source"})
        for key, value in changes.items():
            if value is ...: meta.pop(key)
            else: meta[key] = value
        os.chmod(side, 0o600)
        side.write_text(json.dumps(meta))
        return root

    def assertInvalid(self, root):
        self.assertEqual(media.verify_store(root),
                         {"result": "problems", "problems": [f"sidecar invalid: {J[:12]}"], "originals": 1, "web": 0})

    def test_clean_store_is_ok(self):
        self.assertEqual(media.verify_store(self.build("clean")), {"result": "ok", "problems": [], "originals": 1, "web": 0})

    def test_received_at_present_but_not_zoned(self):
        for i, value in enumerate(("yesterday", "2026-11-01T10:00:00", 5, None, "", ["2026-11-01T10:00:00+00:00"])):
            with self.subTest(value=value): self.assertInvalid(self.edit(f"t{i}", received_at=value))

    def test_other_zoned_times_stay_ok(self):
        for i, value in enumerate(("2026-11-01T10:00:00-08:00", "2026-11-01T18:00:00Z")):
            with self.subTest(value=value):
                self.assertEqual(media.verify_store(self.edit(f"z{i}", received_at=value))["result"], "ok")

    def test_source_present_but_not_a_source_name(self):
        for i, value in enumerate(("../x", "UPPER", "", "a" * 33, 7, None, "fixture\n", ["fixture"])):
            with self.subTest(value=value): self.assertInvalid(self.edit(f"s{i}", source=value))
        self.assertEqual(media.verify_store(self.edit("s32", source="a" * 32))["result"], "ok")

    def test_bytes_must_be_an_int(self):
        for i, value in enumerate((len(JPEG) + 0.0, str(len(JPEG)))):
            with self.subTest(value=value): self.assertInvalid(self.edit(f"b{i}", bytes=value))

    def test_absent_received_at_and_source_stay_ok(self):
        for i, drop in enumerate(({"received_at": ...}, {"source": ...}, {"received_at": ..., "source": ...})):
            with self.subTest(drop=sorted(drop)):
                self.assertEqual(media.verify_store(self.edit(f"a{i}", **drop))["result"], "ok")

    def test_cli_exits_1_with_the_existing_problem(self):
        root = self.edit("cli", received_at="yesterday")
        run = subprocess.run([sys.executable, "hass/media.py", "verify", "--root", str(root)], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual((run.returncode, run.stderr), (1, ""))
        self.assertEqual(json.loads(run.stdout)["problems"], [f"sidecar invalid: {J[:12]}"])

if __name__ == "__main__":
    unittest.main()
