"""RF1750-2 tests: install refuses by name when its own or another change record is unreadable or the wrong shape.

Reuses the SHOP-2 InstallTest fixtures (H02 WriterRepo + a temp site dir); nothing touches the live site.
Run: python3 -B -m unittest hass.tests.test_install_records
"""
import contextlib
import io
import json
import unittest
from unittest import mock

from hass import editor, install
from hass.tests import test_install
from hass.tests.test_editor import git

PREFIX = "storefront-mockup/"


class InstallRecordsTest(test_install.InstallTest):
    # Inherit only the fixtures (setUp + helpers), not the SHOP-2 test methods themselves.
    locals().update({n: None for n in dir(test_install.InstallTest) if n.startswith("test_")})

    def two_changes(self):
        first, _ = self.applied()
        second, _ = self.applied(["Daily 8am–8pm"], "Buttery.")
        return first, second

    def path(self, cid):
        return self.repo.state / "changes" / f"{cid}.json"

    def assert_refused_untouched(self, cid, reason):
        site, rec = self.snapshot(), self.path(cid).read_bytes()
        self.assertEqual(self.install(cid), {"result": "refused", "reason": reason})
        self.assertEqual(self.snapshot(), site, "the site must not be written")
        self.assertEqual(self.path(cid).read_bytes(), rec, "the change record must be left as is")

    def test_second_change_installs_when_the_first_record_is_valid(self):  # edge 1
        first, second = self.two_changes()
        self.assertEqual(self.install(first)["result"], "installed")
        self.assertEqual(self.install(second)["result"], "installed")
        self.assertEqual((self.status(first), self.status(second)), ("installed", "installed"))

    def test_an_unreadable_or_wrong_shape_other_record_is_refused_by_name(self):  # edges 2 and 3
        first, second = self.two_changes()
        bad = {"not json": b"{not json", "a list": b"[]", "a string": b'"x"',
               "install is a string": json.dumps({**editor._read(self.path(first)), "install": "done"}).encode(),
               "install is a list": json.dumps({**editor._read(self.path(first)), "install": []}).encode(),
               "installed without a commit string": json.dumps(
                   {**editor._read(self.path(first)), "install": {"state": "installed", "commit": 7}}).encode()}
        for name, data in bad.items():
            with self.subTest(name):
                self.path(first).write_bytes(data)
                self.assert_refused_untouched(second, f"another change record is unreadable: {first}")
                self.assertNotIn("install", editor._read(self.path(second)))

    def test_the_first_unreadable_record_in_sorted_order_is_named(self):
        first, second = self.two_changes()
        third, _ = self.applied(["Daily 9am–5pm"], "Nutty.")
        for cid in (first, second): self.path(cid).write_bytes(b"{not json")
        self.assert_refused_untouched(third, f"another change record is unreadable: {min(first, second)}")

    def test_another_record_with_a_failed_or_empty_install_is_ignored(self):  # edge 4
        first, second = self.two_changes()
        rec = editor._read(self.path(first))
        for name, inst in (("failed", {"state": "failed", "reason": "x"}), ("empty", {}), ("null", None)):
            with self.subTest(name):
                editor._write_json(self.path(first), {**rec, "install": inst})
                editor._write_json(self.path(second), {k: v for k, v in editor._read(self.path(second)).items()
                                                       if k != "install"})
                self.assertEqual(self.install(second)["result"], "installed")

    def test_own_record_unreadable_or_not_an_object_is_refused(self):  # edge 5
        cid, _ = self.applied()
        for name, data in (("a string", b'"x"'), ("not json", b"{not json"), ("a list", b"[]"),
                           ("too deep", b"[" * 100000 + b"]" * 100000)):
            with self.subTest(name):
                self.path(cid).write_bytes(data)
                self.assert_refused_untouched(cid, "the change record is unreadable")

    def test_own_damaged_install_entry_is_not_installed_yet(self):  # edge 6
        cid, commit = self.applied()
        rec = editor._read(self.path(cid))
        for name, inst in (("a string", "done"), ("a list", ["installed"])):
            with self.subTest(name):
                editor._write_json(self.path(cid), {**rec, "install": inst})
                self.assertEqual(self.install(cid)["result"], "installed")
                after = editor._read(self.path(cid))["install"]
                self.assertEqual((after["state"], after["commit"]), ("installed", commit))

    def test_cli_install_on_an_unreadable_other_record_is_one_refused_line(self):  # edge 7
        first, second = self.two_changes()
        self.path(first).write_bytes(b"{not json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = editor.main(["install", second, "--state", str(self.repo.state)])
        lines = buf.getvalue().splitlines()
        self.assertEqual((code, len(lines)), (1, 1), lines)
        self.assertEqual(json.loads(lines[0]), {"result": "refused",
                                                "reason": f"another change record is unreadable: {first}"})


class UnreadableCommitIdentityTest(InstallRecordsTest):
    """RF1550-10: an installed record whose commit cannot be established as a commit is unreadable, never 'no later install'."""
    locals().update({n: None for n in dir(InstallRecordsTest) if n.startswith("test_")})

    def damage(self, cid, commit):
        rec = editor._read(self.path(cid))
        editor._write_json(self.path(cid), {**rec, "install": {"state": "installed", "commit": commit}})

    def refused(self, first, second, reason_stem=None):
        self.assert_refused_untouched(second, f"another change record is unreadable: {reason_stem or first}")

    def test_empty_or_malformed_installed_commit_refuses_without_writes(self):
        first, second = self.two_changes()
        self.assertEqual(self.install(first)["result"], "installed")
        good = editor._read(self.path(first))["install"]["commit"]
        for name, bad in (("empty", ""), ("space", " " + good), ("nul", "bad\x00value"), ("nonhex", "z" * 40),
                          ("short", good[:12]), ("head", "HEAD"), ("upper", good.upper()), ("int", 7), ("none", None)):
            with self.subTest(name), mock.patch.object(install, "_put") as put:
                self.damage(first, bad)
                self.refused(first, second)
                put.assert_not_called()

    def test_missing_or_noncommit_object_is_not_a_nonancestor(self):
        first, second = self.two_changes()
        wt = self.repo.wt
        blob = git(wt, "rev-parse", "HEAD:" + PREFIX + "index.html")
        tree = git(wt, "rev-parse", "HEAD^{tree}")
        git(wt, "tag", "-a", "-m", "t", "rf1550tag", "HEAD")
        tag = git(wt, "rev-parse", "rf1550tag")
        for name, bad in (("absent", "1" * 40), ("blob", blob), ("tree", tree), ("tag", tag)):
            with self.subTest(name):
                self.damage(first, bad)
                self.refused(first, second)

    def test_ancestry_error_is_unreadable_but_status_one_is_not(self):
        first, second = self.two_changes()
        self.assertEqual(self.install(first)["result"], "installed")
        real = editor._git
        for name, fake in (("128", mock.Mock(returncode=128, stdout="", stderr="boom")), ("2", mock.Mock(returncode=2, stdout="", stderr=""))):
            def patched(wt, *a, _f=fake): return _f if a[0] == "merge-base" else real(wt, *a)
            with self.subTest(name), mock.patch.object(editor, "_git", patched):
                self.refused(first, second)
        def launch_fails(wt, *a):
            if a[0] == "merge-base": raise OSError("no git")
            return real(wt, *a)
        with self.subTest("oserror"), mock.patch.object(editor, "_git", launch_fails):
            self.refused(first, second)
        # status 1 (established non-descendant) keeps the ordinary install of the next change
        self.assertEqual(self.install(second)["result"], "installed")

    def test_real_descendant_still_blocks_and_equal_commit_is_not_later(self):
        first, second = self.two_changes()
        c2 = editor._read(self.path(second))["commit"]
        c1 = editor._read(self.path(first))["commit"]
        self.assertEqual(self.install(second)["result"], "installed")
        self.assertEqual(self.install(first), {"result": "refused", "reason": f"a later change is already installed: {second}"})
        self.damage(first, c2)  # an existing equal commit is not a later install
        self.assertEqual(install._later_installed(self.repo.state, self.repo.wt, second, c2), (None, None))
        self.damage(first, "0" * 40)  # an absent identity is unreadable even though it is not the requested commit
        self.assertEqual(install._later_installed(self.repo.state, self.repo.wt, second, "0" * 40), (None, first))
        self.assertNotEqual(c1, c2)

    def test_noninstalled_entries_with_garbage_commits_are_ignored(self):
        first, second = self.two_changes()
        for inst in ({"state": "failed", "commit": ""}, {"commit": "HEAD"}, {}, None):
            with self.subTest(inst):
                rec = {k: v for k, v in editor._read(self.path(first)).items() if k != "install"}
                editor._write_json(self.path(first), rec if inst is None else {**rec, "install": inst})
                self.assertEqual(self.install(second)["result"], "installed")
                editor._write_json(self.path(second), {k: v for k, v in editor._read(self.path(second)).items() if k != "install"})

    def test_cli_unreadable_commit_is_one_refused_line(self):
        first, second = self.two_changes()
        self.damage(first, "")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = editor.main(["install", second, "--state", str(self.repo.state)])
        lines = buf.getvalue().splitlines()
        self.assertEqual((code, len(lines)), (1, 1), lines)
        self.assertEqual(json.loads(lines[0]), {"result": "refused", "reason": f"another change record is unreadable: {first}"})


if __name__ == "__main__":
    unittest.main()
