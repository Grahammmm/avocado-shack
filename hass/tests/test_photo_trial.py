"""AV1109-10: the offline photo trial harness (hass/skills/photo_trial.py). Synthetic photos only (hass/newitem_synthetic.py);
every folder and fake repository root is a temporary directory outside the checkout, so nothing here writes into the repo."""
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import house_style, newitem_synthetic, skills
from hass.skills import item_picture, photo_trial

REPO = photo_trial.REPO_ROOT
SCRIPT = REPO / "hass" / "skills" / "photo_trial.py"
EXPECT = {"jar-white-sheet": "pass", "bottle-grey-wall-tilted": "pass", "bag-bench-small": "warn", "jar-phone-rotated": "pass",
          "bottle-bench-png": "pass", "jar-cutout-alpha": "pass", "jar-dark-wood": "warn", "bag-red-cloth": "warn"}
HEAD = "Photo\tResult\tFailing checks\tRetake advice"
_PHOTOS = {}


def _file_name(name, kwargs):
    return name + (".png" if kwargs.get("fmt") == "PNG" else ".jpg")


def setUpModule():
    for name, kwargs in newitem_synthetic.cases():  # Pillow is required here: no skipped success
        _PHOTOS[_file_name(name, kwargs)] = newitem_synthetic.make_photo(**kwargs)


def _tmp(test):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    return Path(tmp.name).resolve()


def _folder(test, photos=None):
    folder = _tmp(test) / "photos"
    folder.mkdir()
    for name, data in (photos or _PHOTOS).items():
        (folder / name).write_bytes(data)
    return folder


def _tree(root):
    return sorted((str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else "-")
                  for p in Path(root).rglob("*"))


def _cli(folder, *extra):
    done = subprocess.run([sys.executable, str(SCRIPT), str(folder), *extra], capture_output=True, text=True, cwd=str(folder.parent))
    return done.returncode, done.stdout, done.stderr


def _run(argv, **kw):
    out, err = io.StringIO(), io.StringIO()
    code = photo_trial.main(argv, stdout=kw.pop("stdout", out), stderr=err)
    return code, out.getvalue(), err.getvalue()


class Eight(unittest.TestCase):
    def test_eight_synthetic_photos_five_pass_three_warn(self):
        folder = _folder(self)
        before = _tree(folder)
        code, out, err = _cli(folder, "--json")
        self.assertEqual((code, err), (1, ""))
        rows = json.loads(out)
        self.assertEqual([list(r) for r in rows], [["file", "status", "failed_checks", "advice"]] * 8)
        self.assertEqual({r["file"].rsplit(".", 1)[0]: r["status"] for r in rows}, EXPECT)
        self.assertEqual(sum(r["status"] == "pass" for r in rows), 5)
        by = {r["file"].rsplit(".", 1)[0]: r for r in rows}
        self.assertEqual(by["bag-bench-small"]["failed_checks"], ["subject size in frame"])
        self.assertEqual(by["jar-dark-wood"]["failed_checks"], ["background even", "clean ivory around the product (no photo background left)"])
        self.assertEqual(by["bag-red-cloth"]["failed_checks"], ["no photo background left inside the product (patterned cloth, planks)"])
        for name, row in by.items():
            self.assertEqual(bool(row["advice"]), EXPECT[name] == "warn", name)
        self.assertEqual([r["file"] for r in rows], sorted(r["file"] for r in rows))
        tcode, text, terr = _cli(folder)
        self.assertEqual((tcode, terr), (1, ""))
        lines = text.splitlines()
        self.assertEqual(lines[0], HEAD)
        self.assertEqual(len(lines), 9)
        self.assertEqual([ln.split("\t")[:2] for ln in lines[1:]], [[r["file"], r["status"]] for r in rows])
        self.assertTrue(all(len(ln.split("\t")) == 4 for ln in lines))
        self.assertEqual(_tree(folder), before)

    def test_all_pass_exits_zero(self):
        folder = _folder(self, {"jar-white-sheet.jpg": _PHOTOS["jar-white-sheet.jpg"]})
        code, out, err = _cli(folder)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, HEAD + "\njar-white-sheet.jpg\tpass\t-\t-\n")

    def test_small_warns_even_when_check_passes(self):
        row = photo_trial.assess_photo("s.jpg", _PHOTOS["bag-bench-small.jpg"])
        self.assertTrue(house_style.check_image(photo_trial._tools()[1].render(_PHOTOS["bag-bench-small.jpg"])["jpeg"])["pass"])
        self.assertEqual(row["status"], "warn")
        self.assertTrue(row["advice"])

    def test_rotated_photo_is_corrected_not_automatically_warned(self):
        row = photo_trial.assess_photo("r.jpg", _PHOTOS["jar-phone-rotated.jpg"])
        self.assertEqual(row, {"file": "r.jpg", "status": "pass", "failed_checks": [], "advice": []})


class Advice(unittest.TestCase):
    def test_item_picture_advice_matches_exactly(self):
        variants = {"busy": _PHOTOS["jar-dark-wood.jpg"], "small": _PHOTOS["bag-bench-small.jpg"],
                    "sideways-small": newitem_synthetic.make_photo(product="bag", background="kitchen-bench", size=(480, 360),
                                                                   phone_orientation=8, seed=3)}
        seen = set()
        for label, data in variants.items():
            _, warn = item_picture.picture_review(data, True)
            row = photo_trial.assess_photo("x.jpg", data)
            if label != "sideways-small":
                self.assertEqual(row["status"], "warn", label)
            self.assertEqual(row["advice"], list(warn), label)
            seen.add(tuple(row["advice"]))
        self.assertGreaterEqual(len(seen), 2)  # busy and small are told apart by the real helper, not by this tool


class Folders(unittest.TestCase):
    def test_folder_policy(self):
        base = _tmp(self)
        fake = base / "repo"
        (fake / "inside").mkdir(parents=True)
        sibling = base / "repo-photos"
        sibling.mkdir()
        a_file = base / "file.jpg"
        a_file.write_bytes(b"x")
        empty = base / "empty"
        empty.mkdir()
        (base / "real").mkdir()
        (base / "link").symlink_to(base / "real")
        (base / "real" / "sub").mkdir()
        with mock.patch.object(photo_trial, "REPO_ROOT", fake):
            for bad in (base / "missing", a_file, fake, fake / "inside", base / "link", base / "link" / "sub", "", fake / ".." / "repo"):
                with self.assertRaises(photo_trial.TrialError, msg=str(bad)):
                    photo_trial.checked_directory(str(bad))
            self.assertEqual(photo_trial.checked_directory(str(sibling)), sibling)  # a name that only shares the repo's prefix
            self.assertEqual(photo_trial.checked_directory(str(base / "real" / ".." / "repo-photos")), sibling)
            code, out, err = _run([str(empty)])  # nothing to try is a refusal, never a vacuous pass
            self.assertEqual((code, out), (2, ""))
            self.assertIn("no JPEG or PNG", err)
        self.assertEqual(_run([str(REPO)])[:2], (2, ""))  # the real checkout and a descendant
        self.assertEqual(_run([str(REPO / "hass")])[:2], (2, ""))

    def test_symlink_candidate_refused_before_reads(self):
        folder = _folder(self, {"a.jpg": _PHOTOS["jar-white-sheet.jpg"]})
        outside = folder.parent / "elsewhere.png"
        outside.write_bytes(_PHOTOS["bottle-bench-png.png"])
        for target in (outside, REPO / "hass" / "skills" / "__init__.py"):
            link = folder / "z-link.PNG"
            link.symlink_to(target)
            with mock.patch.object(photo_trial, "_read_photo") as read, mock.patch.object(photo_trial, "assess_photo") as assess:
                code, out, err = _run([str(folder)])
            self.assertEqual((code, out), (2, ""))
            self.assertFalse(read.called or assess.called)
            self.assertIn("symbolic link", err)
            link.unlink()

    def test_flat_sorted_case_insensitive_candidates(self):
        folder = _tmp(self) / "photos"
        folder.mkdir()
        for name in ("B.JPG", "a.jpeg", "c.PNG", "x\ty\nz.jpg", "skip.webp", "notes.txt"):
            (folder / name).write_bytes(b"not read")
        (folder / "nested").mkdir()
        (folder / "nested" / "deep.jpg").write_bytes(b"deeper")
        (folder / "dir.jpg").mkdir()
        passed = lambda name, data: photo_trial._row(name, "pass", [], [])  # noqa: E731
        with mock.patch.object(photo_trial, "assess_photo", passed):
            code, out, _ = _run([str(folder)])
            jcode, jout, _ = _run([str(folder), "--json"])
        self.assertEqual(code, 0)
        lines = out.split("\n")
        self.assertEqual(lines[:-1], [HEAD, "B.JPG\tpass\t-\t-", "a.jpeg\tpass\t-\t-", "c.PNG\tpass\t-\t-", "x\\ty\\nz.jpg\tpass\t-\t-"])
        self.assertEqual([r["file"] for r in json.loads(jout)], ["B.JPG", "a.jpeg", "c.PNG", "x\ty\nz.jpg"])


class Output(unittest.TestCase):
    def test_external_stdout_only(self):
        base = _tmp(self)
        fake = base / "repo"
        fake.mkdir()
        folder = _folder(self, {"a.jpg": b"-"})
        passed = lambda name, data: photo_trial._row(name, "pass", [], [])  # noqa: E731
        with mock.patch.object(photo_trial, "REPO_ROOT", fake), mock.patch.object(photo_trial, "assess_photo", passed):
            with open(fake / "out.txt", "w") as sink:
                code, _, err = _run([str(folder)], stdout=sink)
            self.assertEqual(code, 2)
            self.assertIn("inside the repository", err)
            self.assertEqual((fake / "out.txt").read_text(), "")
            with open(base / "outside.txt", "w") as sink:
                with mock.patch.object(photo_trial.os, "readlink", side_effect=OSError):  # cannot be identified: refuse
                    self.assertEqual(_run([str(folder)], stdout=sink)[0], 2)
                self.assertEqual(_run([str(folder)], stdout=sink)[0], 0)
            self.assertIn("a.jpg", (base / "outside.txt").read_text())
            r, w = os.pipe()
            with os.fdopen(w, "w") as pipe:
                self.assertEqual(_run([str(folder)], stdout=pipe)[0], 0)
            os.close(r)
            for flag in ("--output", "--out", "-o"):
                code, out, err = _run([str(folder), flag, str(base / "o.txt")])
                self.assertEqual((code, out), (2, ""))
                self.assertIn("Usage", err)
            self.assertFalse((base / "o.txt").exists())


class Failures(unittest.TestCase):
    def test_corrupt_or_unreadable_photo_warns_and_continues(self):
        folder = _folder(self, {"a-ok.jpg": _PHOTOS["jar-white-sheet.jpg"], "b-bad.jpg": b"this is not an image",
                                "c-gone.png": _PHOTOS["bottle-bench-png.png"], "d-ok.jpg": _PHOTOS["jar-phone-rotated.jpg"]})
        real = photo_trial._read_photo

        def read(path):
            if path.name == "c-gone.png":
                raise OSError("secret path /nope")
            return real(path)
        with mock.patch.object(photo_trial, "_read_photo", read):
            code, out, err = _run([str(folder), "--json"])
        self.assertEqual((code, err), (1, ""))
        rows = json.loads(out)
        self.assertEqual([(r["file"], r["status"]) for r in rows],
                         [("a-ok.jpg", "pass"), ("b-bad.jpg", "warn"), ("c-gone.png", "warn"), ("d-ok.jpg", "pass")])
        say = "I couldn't read this photo. Send it again as a JPEG or PNG."
        self.assertEqual((rows[1]["failed_checks"], rows[1]["advice"]), (["cannot-render"], [say]))
        self.assertEqual((rows[2]["failed_checks"], rows[2]["advice"]), (["unreadable-photo"], [say]))
        self.assertNotIn("secret", out)

    def test_missing_pillow_or_dependency_is_setup_error(self):
        folder = _folder(self, {"a.jpg": _PHOTOS["jar-white-sheet.jpg"], "b.jpg": _PHOTOS["jar-dark-wood.jpg"]})
        render = photo_trial._tools()[1]
        for patcher in (mock.patch.object(render, "render", side_effect=house_style.PillowMissing("no PIL at /secret")),
                        mock.patch.object(photo_trial, "_tools", side_effect=ImportError("no helper at /secret"))):
            with patcher:
                code, out, err = _run([str(folder), "--json"])
            self.assertEqual((code, out), (2, ""))
            self.assertNotIn("Traceback", err)
            self.assertNotIn("secret", err)
            self.assertTrue(err.startswith("photo_trial:"))

    def test_advice_missing_for_a_render_warning_is_a_contract_error(self):
        folder = _folder(self, {"a.jpg": _PHOTOS["bag-bench-small.jpg"]})
        with mock.patch.object(item_picture, "picture_review", return_value=((), ())):
            code, out, err = _run([str(folder)])
        self.assertEqual((code, out), (2, ""))


class Privacy(unittest.TestCase):
    def test_no_metadata_or_writes(self):
        photos = {"phone.jpg": _PHOTOS["jar-phone-rotated.jpg"], "wood.jpg": _PHOTOS["jar-dark-wood.jpg"]}
        folder = _folder(self, photos)
        self.assertTrue(newitem_synthetic.has_exif_location(photos["phone.jpg"]))
        before, repo_before = _tree(folder.parent), _tree(REPO / "hass")
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network")), \
                mock.patch.object(socket, "create_connection", side_effect=AssertionError("network")):
            outputs = [_cli(folder), _cli(folder, "--json")]
        for code, out, err in outputs:
            self.assertEqual((code, err), (1, ""))
            for secret in ("SyntheticCo", "Phone 0", "2026:11:07", "GPS", "35.0", "120.0", "orientation", "Orientation", str(folder.parent)):
                self.assertNotIn(secret, out)
        self.assertEqual(set(json.loads(outputs[1][1])[0]), {"file", "status", "failed_checks", "advice"})
        self.assertEqual(_tree(folder.parent), before)
        self.assertEqual(_tree(REPO / "hass"), repo_before)

    def test_import_is_inert_and_registry_unchanged(self):
        self.assertFalse(hasattr(photo_trial, "SKILLS"))
        names = set(skills.load_skills().skills)
        self.assertNotIn("photo_trial", names)
        self.assertFalse(any("photo" in n and "trial" in n for n in names))
        with mock.patch.object(photo_trial, "_tools", side_effect=AssertionError("tools used at import")), \
                mock.patch.object(os, "scandir", side_effect=AssertionError("scan at import")):
            import importlib
            importlib.reload(photo_trial)  # reloading runs module-level code again: no argv, scan, render or tool import
        self.assertTrue(callable(photo_trial.main))


if __name__ == "__main__":
    unittest.main()
