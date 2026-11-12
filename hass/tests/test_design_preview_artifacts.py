"""RF0825-11 tests: design_preview binds each returned artifact to its planned output path."""

import contextlib, io, json, os, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import design_preview as dp
from hass.tests import test_design_preview as base

CHECKS = {name: True for name in ("pageLoaded", "noHorizontalOverflow", "noPageErrors", "noPosts",
                                  "desktop:pageLoaded", "desktop:noHorizontalOverflow",
                                  "desktop:noPageErrors", "desktop:noPosts")}


def private(path, mode=0o600):
    Path(path).write_bytes(base.PNG)
    os.chmod(path, mode)
    return str(path)


class Fake:
    """Returns whatever ``reply(index, out_png)`` gives; records calls."""
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def capture(self, files, target, out_png):
        self.calls.append(Path(out_png))
        return self.reply(len(self.calls) - 1, Path(out_png))


def desk(out_png):
    return out_png.with_name(out_png.stem + "-desktop.png")


def healthy(i, out_png):
    return {"ok": True, "png": private(out_png), "desktopPng": private(desk(out_png)), "checks": dict(CHECKS)}


class ArtifactIdentityTests(base.RepoCase):
    def setUp(self):
        super().setUp()
        self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})
        self.stray = self.tmp / "stray.png"
        private(self.stray)

    def test_unrelated_private_file_cannot_fill_all_slots(self):
        fake = Fake(lambda i, p: {"ok": True, "png": str(self.stray), "desktopPng": str(self.stray), "checks": dict(CHECKS)})
        code, doc = self.run_fake(fake)
        self.assertEqual((code, doc["result"], len(fake.calls)), (1, "preview-failed", 4))
        for c in doc["captures"]:
            self.assertEqual((c["png"], c["desktopPng"], c["error"]), (None, None, "missing png"))
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertNotIn("stray", json.dumps(doc))

    def test_cross_page_side_and_viewport_paths_are_refused(self):
        made = {}

        def reply(i, p):
            made[i] = p
            other = made.get(0)
            if i == 0:
                return healthy(i, p)
            if i == 1:  # another slot's real phone file
                return {"ok": True, "png": str(made[0]), "desktopPng": private(desk(p)), "checks": dict(CHECKS)}
            if i == 2:  # swapped phone/desktop
                return {"ok": True, "png": private(desk(p)), "desktopPng": private(p), "checks": dict(CHECKS)}
            return {"ok": True, "png": private(p), "desktopPng": str(desk(other)), "checks": dict(CHECKS)}
        code, doc = self.run_fake(Fake(reply))
        self.assertEqual([c["error"] for c in doc["captures"]],
                         [None, "missing png", "missing png", "missing desktop png"])
        self.assertIsNone(doc["captures"][3]["desktopPng"])
        self.assertIsNotNone(doc["captures"][3]["png"])

    def test_identity_check_precedes_filesystem_access(self):
        expected = self.tmp / "want.png"
        private(expected)
        for bad in ("\0x", "", "want.png", None, 7, ["x"], str(expected) + "/", str(self.tmp) + "/./want.png"):
            with self.subTest(bad=bad), mock.patch.object(dp.os, "lstat", side_effect=AssertionError("lstat")):
                self.assertIsNone(dp._private_png(bad, expected))
        with mock.patch.object(dp.os, "lstat", wraps=os.lstat) as spy:
            self.assertEqual(dp._private_png(str(expected), expected), str(expected))
            spy.assert_called_once()
        entry = dp._entry("base", "home", {"ok": True, "png": "\0evil", "desktopPng": "", "checks": dict(CHECKS)}, expected)
        self.assertEqual((entry["png"], entry["desktopPng"], entry["error"]), (None, None, "missing png"))
        self.assertNotIn("evil", json.dumps(entry))

    def test_matching_paths_still_require_private_regular_files(self):
        count = [0]

        def go(prepare):
            count[0] += 1

            def reply(i, p):
                prepare(i, p)
                return {"ok": True, "png": str(p), "desktopPng": str(desk(p)), "checks": dict(CHECKS)}
            return self.run_fake(Fake(reply), out=self.tmp / f"o{count[0]}")[1]["captures"][0]
        self.assertEqual(go(lambda i, p: None)["error"], "missing png")  # missing leaf
        self.assertEqual(go(lambda i, p: (private(p, 0o644), private(desk(p))))["error"], "missing png")  # not 0600
        self.assertEqual(go(lambda i, p: (private(p), desk(p).mkdir()))["error"], "missing desktop png")  # directory

        def link(i, p):
            private(p)
            if i == 0:
                os.symlink(self.stray, desk(p))
        self.assertEqual(go(link)["error"], "missing desktop png")  # symlink leaf
        self.assertIsNone(go(lambda i, p: (private(p), private(desk(p))))["error"])

    def test_partial_capture_preserved_and_later_calls_continue(self):
        def reply(i, p):
            if i == 0:
                return {"ok": True, "png": private(p), "desktopPng": str(self.stray), "checks": dict(CHECKS)}
            if i == 1:
                return {"ok": False, "png": private(p), "desktopPng": private(desk(p)),
                        "checks": {**CHECKS, "noPosts": False}}
            return healthy(i, p)
        fake = Fake(reply)
        code, doc = self.run_fake(fake)
        first, second, *rest = doc["captures"]
        self.assertEqual((code, len(fake.calls)), (1, 4))
        self.assertEqual((first["png"], first["desktopPng"], first["error"]), (str(fake.calls[0]), None, "missing desktop png"))
        self.assertEqual(second["error"], "check failed: noPosts")
        self.assertEqual(second["png"], str(fake.calls[1]))
        self.assertEqual([c["error"] for c in rest], [None, None])

    def test_main_json_lists_exact_eight_paths_on_success(self):
        os.chdir(self.repo)
        stdout = io.StringIO()
        with mock.patch.object(dp, "Previewer", lambda top: Fake(healthy)), contextlib.redirect_stdout(stdout):
            code = dp.main(["--base", "main", "--head", "feature", "--out", str(self.out)])
        lines = stdout.getvalue().splitlines()
        self.assertEqual((code, len(lines)), (0, 1))
        doc = json.loads(lines[0])
        names = [name for c in doc["captures"] for name in (c["png"], c["desktopPng"])]
        want = [str(self.out / f"{s}-{pg}-phone{suf}.png") for s in ("base", "head") for pg in ("home", "hike")
                for suf in ("", "-desktop")]
        self.assertEqual(names, want)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), sorted(Path(w).name for w in want))
        self.assertEqual(set(doc["captures"][0]), {"side", "page", "png", "desktopPng", "checks", "error"})


if __name__ == "__main__":
    unittest.main()
