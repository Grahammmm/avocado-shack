"""SHOP-2 tests: install one applied change from its commit into a synthetic running-site dir.

Each test uses the H02 WriterRepo (temp repo + linked writer worktree + 0700 state dir) and a temp site dir
seeded with the base site files. Nothing touches the checkout, the live site or its service.
Run: python3 -B -m unittest hass.tests.test_install
"""
import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import editor, install
from hass.tests.test_editor import DESC, HOURS, NEW_HOURS, SITE_FILES, WriterRepo, _req, git

PREFIX = "storefront-mockup/"


class Killed(BaseException):
    """Stands in for the process dying between two files (no except clause runs)."""


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.repo = WriterRepo()
        self.addCleanup(self.repo._tmp.cleanup)
        tmp = tempfile.TemporaryDirectory(prefix="hass-site-")
        self.addCleanup(tmp.cleanup)
        self.site = Path(tmp.name).resolve() / "site"
        for rel in SITE_FILES:
            (self.site / rel[len(PREFIX):]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.repo.main / rel, self.site / rel[len(PREFIX):])
        (self.site / "style.css").write_bytes(b"/* untouched */\n")
        self.set_site(str(self.site))

    def set_site(self, value):
        cfg = editor._read(self.repo.state / "config.json")
        editor._write_json(self.repo.state / "config.json", {**cfg, "settings": {"site_dir": value}})

    def applied(self, hours=NEW_HOURS, description="Ripe and creamy."):
        draft = self.repo.prepare(_req((HOURS, {"hours": hours}),
                                       (DESC, {"id": "photo-product-001", "description": description})))["draft"]
        out = self.repo.apply(draft)
        self.assertEqual(out["result"], "applied", out)
        return out["change_id"], out["commit"]

    def site_paths(self, commit):
        names = git(self.repo.wt, "diff-tree", "-r", "--no-commit-id", "--name-only", f"{commit}^", commit, "--", PREFIX)
        return sorted(n[len(PREFIX):] for n in names.splitlines())

    def install(self, cid):
        return install.install(cid, state=str(self.repo.state))

    def snapshot(self):
        return {str(p.relative_to(self.site)): p.read_bytes() for p in sorted(self.site.rglob("*")) if p.is_file()}

    def status(self, cid):
        shown = editor.show(cid, state=str(self.repo.state))["install"]
        listed = {e["change_id"]: e["install"] for e in editor.history(state=str(self.repo.state))["history"]}
        self.assertEqual(shown, listed[cid])
        return shown

    def blob_hash(self, commit, rel):
        data = install._blob(self.repo.wt, f"{commit}:{rel}")
        return hashlib.sha256(data).hexdigest()

    def test_applied_change_installs_commit_blobs_and_nothing_else(self):
        before = self.snapshot()
        cid, commit = self.applied()
        self.assertEqual(self.status(cid), "committed, not installed")
        self.assertEqual(self.snapshot(), before, "apply alone must not install")
        out = self.install(cid)
        paths = self.site_paths(commit)
        self.assertIn("catalog-products.js", paths)
        self.assertIn("index.html", paths)
        self.assertEqual((out["result"], out["commit"], out["files"]), ("installed", commit, len(paths)), out)
        after = self.snapshot()
        for rel in paths:
            self.assertEqual(hashlib.sha256(after[rel]).hexdigest(), self.blob_hash(commit, PREFIX + rel))
            self.assertNotEqual(after[rel], before[rel])
        changed = {k for k in after if after[k] != before.get(k)}
        self.assertEqual(changed, set(paths))
        self.assertEqual(after["style.css"], b"/* untouched */\n")
        self.assertEqual(self.status(cid), "installed")
        rec = editor._read(self.repo.state / "changes" / f"{cid}.json")
        self.assertEqual((rec["state"], rec["install"]["state"], rec["install"]["files"]),
                         ("applied", "installed", len(paths)))
        self.assertEqual(self.repo.status(), "", "install must not edit the worktree")

    def test_unknown_unapplied_failed_and_reverted_changes_are_refused(self):
        before = self.snapshot()
        draft = self.repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        self.assertEqual(self.install(draft["change_id"])["reason"], "the change is not applied")
        self.assertEqual(self.install("chg-000000000000")["reason"], "unknown change id")
        self.assertEqual(self.install("../etc")["result"], "invalid")
        cid, _commit = self.applied()
        path = self.repo.state / "changes" / f"{cid}.json"
        rec = editor._read(path)
        editor._write_json(path, {**rec, "revertedBy": "chg-111111111111"})
        self.assertEqual(self.install(cid), {"result": "refused", "reason": "the change was reverted by chg-111111111111"})
        editor._write_json(path, {"state": "failed", "change_id": cid, "problems": ["x"]})
        self.assertEqual(self.install(cid)["reason"], "the change is not applied")
        self.assertIsNone(self.status(cid))
        editor._write_json(path, {**rec, "commit": git(self.repo.wt, "rev-parse", "HEAD~1")})
        self.assertEqual(self.install(cid)["reason"], "the change commit is not in the writer worktree")
        self.assertEqual(self.snapshot(), before)

    def test_readback_mismatch_rolls_back_every_file(self):
        before = self.snapshot()
        cid, _commit = self.applied()
        real, calls = install._swap, []

        def corrupt_first(tmp, target):
            real(tmp, target)
            calls.append(target)
            if len(calls) == 1: Path(target).write_bytes(b"corrupt")
        with mock.patch.object(install, "_swap", corrupt_first):
            out = self.install(cid)
        self.assertEqual(out["result"], "failed", out)
        self.assertTrue(out["reason"].startswith("readback mismatch: "), out)
        self.assertEqual(self.snapshot(), before, "every file must be restored")
        self.assertTrue(self.status(cid).startswith("committed, not installed (install failed: readback mismatch"))

    def test_write_error_on_second_file_rolls_back_the_first(self):
        before = self.snapshot()
        cid, _commit = self.applied()
        real, calls = install._swap, []

        def fail_second(tmp, target):
            calls.append(target)
            if len(calls) == 2: raise PermissionError("denied")
            real(tmp, target)
        with mock.patch.object(install, "_swap", fail_second):
            out = self.install(cid)
        self.assertEqual((out["result"], out["reason"]), ("failed", "write failed: PermissionError"))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual([p.name for p in self.site.rglob(install.TMP_PREFIX + "*")], [])
        self.assertEqual(self.install(cid)["result"], "installed", "a failed install can be retried")

    def test_bad_site_dir_is_refused_before_any_write(self):
        cid, _commit = self.applied()
        link = self.site.parent / "link"
        link.symlink_to(self.site, target_is_directory=True)
        (self.repo.state / "pub").mkdir()
        cases = {
            None: "settings.site_dir is not set",
            "site": "site_dir must be an absolute path",
            str(self.site.parent / "missing"): "site_dir does not exist",
            str(link): "site_dir must not be a symlink",
            str(link / "hike"): "site_dir must not be a symlink",
            str(self.repo.wt.resolve() / "storefront-mockup"): "site_dir must lie outside the writer worktree",
            str(self.repo.wt.resolve()): "site_dir must lie outside the writer worktree",
            str(self.repo.main.resolve() / ".git"): "site_dir must lie outside the Git directory",
            str(self.repo.main.resolve()): "site_dir must lie outside the Git directory",
            str(self.repo.state.resolve() / "pub"): "site_dir must lie outside the state dir",
            str(self.repo.state.resolve().parent): "site_dir must lie outside the writer worktree",
        }
        wt_before = (self.repo.wt / PREFIX / "index.html").read_bytes()
        before = self.snapshot()
        for value, reason in cases.items():
            with self.subTest(site_dir=value):
                self.set_site(value)
                self.assertEqual(self.install(cid), {"result": "refused", "reason": reason})
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.repo.wt / PREFIX / "index.html").read_bytes(), wt_before)
        self.assertEqual(sorted(p.name for p in (self.repo.state / "pub").iterdir()), [])
        self.assertEqual(self.status(cid), "committed, not installed")

    def test_later_worktree_edits_do_not_change_what_installs(self):
        cid, commit = self.applied()
        (self.repo.wt / PREFIX / "index.html").write_bytes(b"uncommitted edit\n")
        self.assertEqual(self.install(cid)["result"], "installed")
        self.assertEqual(hashlib.sha256((self.site / "index.html").read_bytes()).hexdigest(),
                         self.blob_hash(commit, PREFIX + "index.html"))

    def test_second_install_is_already_installed_and_bytes_unchanged(self):
        cid, commit = self.applied()
        self.assertEqual(self.install(cid)["result"], "installed")
        first = self.snapshot()
        stamps = {p: p.stat().st_mtime_ns for p in self.site.rglob("*") if p.is_file()}
        self.assertEqual(self.install(cid), {"result": "already_installed", "change_id": cid, "commit": commit,
                                             "files": len(self.site_paths(commit))})
        self.assertEqual(self.snapshot(), first)
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.site.rglob("*") if p.is_file()}, stamps)

    def test_interrupted_install_converges_on_retry(self):
        cid, commit = self.applied()
        real = install._swap

        def killed(tmp, target):
            real(tmp, target)
            raise Killed()
        with mock.patch.object(install, "_swap", killed), self.assertRaises(Killed):
            self.install(cid)
        (self.site / (install.TMP_PREFIX + "left.tmp")).write_bytes(b"half")
        self.assertEqual(self.status(cid), "committed, not installed")
        self.assertEqual(self.install(cid)["result"], "installed")
        for rel in self.site_paths(commit):
            self.assertEqual(hashlib.sha256((self.site / rel).read_bytes()).hexdigest(),
                             self.blob_hash(commit, PREFIX + rel))
        self.assertEqual([p.name for p in self.site.rglob(install.TMP_PREFIX + "*")], [])
        self.assertEqual(self.install(cid)["result"], "already_installed")

    def test_out_of_order_install_of_an_older_change_is_refused(self):
        old, _ = self.applied()
        new, _ = self.applied(["Daily 8am–8pm"], "Buttery.")
        self.assertEqual(self.install(new)["result"], "installed")
        installed = self.snapshot()
        self.assertEqual(self.install(old), {"result": "refused", "reason": f"a later change is already installed: {new}"})
        self.assertEqual(self.snapshot(), installed)
        self.assertEqual((self.status(old), self.status(new)), ("committed, not installed", "installed"))

    def test_held_writer_lock_is_busy(self):
        cid, _commit = self.applied()
        with editor._writer_lock(self.repo.state) as held:
            self.assertTrue(held)
            self.assertEqual(self.install(cid), {"result": "busy"})
        self.assertEqual(self.status(cid), "committed, not installed")

    def test_cli_install_verb_exit_codes(self):
        cid, _commit = self.applied()
        runs = []
        for change in (cid, cid, "chg-000000000000"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = editor.main(["install", change, "--state", str(self.repo.state)])
            runs.append((code, json.loads(buf.getvalue())["result"]))
        self.assertEqual(runs, [(0, "installed"), (0, "already_installed"), (1, "refused")])


if __name__ == "__main__":
    unittest.main()
