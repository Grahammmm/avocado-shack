"""HASS-SITE-LOOK-1b: design.apply lands a LOOK-1 `ok` look/<code> commit on writer HEAD, publishes it through the disposable
bare-repo release fixture and undoes it once; host.json `looks`. Fixtures only (real editor, local bare Git, no network).
Run: python3 -B -m unittest discover -s hass/tests -p 'test_look_engine.py' -v"""
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import editor, host, live_policy
from hass.tests import test_editor, test_publish_live as tpl
from hass.tests.test_editor import _req, git

CSS = "storefront-mockup/style.css"
R = tpl.ReleaseCase  # its fixture helpers are borrowed below (subclassing would run its tests a second time)


def css_edit(work):
    with open(work / CSS, "a", encoding="utf-8") as fh: fh.write("\nbody { letter-spacing: .01em; }\n")


class LookEngine(unittest.TestCase):
    wrapper, fetch, open, wait, settle, entry, draft, apply = R.wrapper, R.fetch, R.open, R.wait, R.settle, R.entry, R.draft, R.apply

    def setUp(self):
        with mock.patch.object(test_editor, "SITE_FILES", test_editor.SITE_FILES + (CSS,)):  # the writer has a real style.css
            tpl.ReleaseCase.setUp(self)
        patcher = mock.patch.dict(live_policy.LIVE, {"design.apply": None})  # the real LIVE row is LOOK-2's (t_9715bee6)
        patcher.start()
        self.addCleanup(patcher.stop)

    extra = {}  # bytes a test adds to the 'new' build only

    def fixture_build(self, commit, today, cid, label, checks=False):
        files = tpl.ReleaseCase.fixture_build(self, commit, today, cid, label)
        files["style.css"] = git(self.repo.wt, "show", f"{commit}:{CSS}").encode()
        return {**files, **(self.extra if label == "new" else {})}

    def look(self, code, edit):
        """A LOOK-1 `ok` result: branch look/<code> at one commit on writer HEAD made by edit(work)."""
        base, work = self.repo.head(), self.root / ("look-" + code)
        git(self.repo.main, "worktree", "add", "-q", "--detach", str(work), base)
        edit(work)
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "look draft " + code)
        head = git(work, "rev-parse", "HEAD")
        git(self.repo.main, "branch", "look/" + code, head)
        git(self.repo.main, "worktree", "remove", str(work))
        return {"result": "ok", "branch": "look/" + code, "base": base, "head": head, "captures": []}

    def design(self, ok, **over):
        args = {**{k: ok[k] for k in ("branch", "base", "head")}, **over}
        return self.repo.prepare({"ops": [{"op": "design.apply", "args": args}]})

    def published(self, rel): return git(self.bare, "show", "main:" + rel)
    def css_at(self, commit): return git(self.repo.wt, "show", f"{commit}:{CSS}")

    def test_look_lands_publishes_and_undoes_once(self):
        ok = self.look("bigger", css_edit)
        made = self.design(ok)
        self.assertEqual(made["result"], "ok")
        d = made["draft"]
        self.assertEqual(self.live.apply(d["change_id"], d["draft_hash"])["result"], "applied")
        self.assertEqual(git(self.repo.wt, "diff", "--name-only", "HEAD~1", "HEAD"), CSS)
        self.assertEqual(git(self.repo.wt, "rev-parse", "HEAD~1"), ok["base"])
        self.assertEqual(git(self.repo.wt, "rev-parse", "HEAD^{tree}"), git(self.repo.wt, "rev-parse", ok["head"] + "^{tree}"))
        self.assertEqual(git(self.repo.wt, "log", "-1", "--format=%s"), "hass content: " + d["change_id"])
        self.assertEqual(self.repo.status(), "")
        rec = editor.show(d["change_id"], state=str(self.repo.state))["change"]
        self.assertEqual((rec["kind"], rec["state"], rec["commit"], rec["records"]), ("design", "applied", self.repo.head(), []))
        self.settle()
        self.assertEqual(self.entry()["state"], "live")
        self.assertEqual(sorted(self.entry()["manifest"]), ["style.css"])
        self.assertEqual(self.published("style.css"), self.css_at(ok["head"]))

        undo = self.live.revert_last()
        self.assertEqual((undo["result"], undo["undid"]), ("ok", d["change_id"]))
        self.assertEqual(git(self.repo.wt, "rev-parse", "HEAD~1"), rec["commit"])  # a new commit: exactly that commit reverted
        self.assertEqual(git(self.repo.wt, "rev-parse", "HEAD^{tree}"), git(self.repo.wt, "rev-parse", ok["base"] + "^{tree}"))
        self.assertEqual(self.published("style.css"), self.css_at(ok["base"]))
        self.assertIn("undo of " + d["change_id"], git(self.bare, "log", "-1", "--format=%s"))
        self.assertEqual(editor.show(undo["change_id"], state=str(self.repo.state))["change"]["kind"], "design")
        self.assertEqual(self.live.revert_last(), {"result": "nothing-to-revert"})
        for cid in (d["change_id"], undo["change_id"]):  # no second undo, and no undo of the undo
            self.assertEqual(self.repo.prepare(_req(("history.revert", {"changeId": cid})))["result"], "refused")

    def test_refusals_leave_writer_and_release_unchanged(self):
        writer, site = self.repo.head(), self.published("style.css")

        def exec_bit(work):
            css_edit(work)
            os.chmod(work / CSS, 0o755)

        def symlink(work):
            (work / CSS).unlink()
            (work / CSS).symlink_to("index.html")
        bad = {"outside": lambda w: (w / "notes.txt").write_text("x\n"), "delete": lambda w: (w / CSS).unlink(),
               "symlink": symlink, "exec": exec_bit}
        for code, edit in bad.items():
            with self.subTest(code):
                out = self.design(self.look(code, edit))
                self.assertEqual(out["result"], "refused")
                self.assertIn("not only design files", out["reason"])
        ok, other = self.look("moved", css_edit), self.look("other", css_edit)
        self.assertEqual(self.design(ok, head=other["head"])["result"], "refused")  # not the branch head
        self.assertEqual(self.design(ok, base=other["head"])["result"], "stale")  # not made on writer HEAD
        d = self.design(ok)["draft"]
        git(self.repo.main, "branch", "-f", "look/moved", other["head"])  # the branch moved after the yes was bound to it
        self.assertEqual(self.live.apply(d["change_id"], d["draft_hash"])["result"], "refused")
        git(self.repo.main, "branch", "-f", "look/moved", ok["head"])
        d2 = self.design(other)["draft"]
        (self.repo.wt / "stray.txt").write_text("x\n")  # a dirty writer
        out = self.live.apply(d2["change_id"], d2["draft_hash"])
        self.assertEqual(out["result"], "refused")
        self.assertIn("writer worktree has uncommitted changes", out["problems"])
        (self.repo.wt / "stray.txt").unlink()
        self.assertEqual((self.repo.head(), self.repo.status(), self.published("style.css")), (writer, "", site))
        self.assertEqual(git(self.bare, "rev-parse", "main"), self.site_before)
        self.assertEqual([j["state"] for j in self.live.books.journals()], ["not-applied", "not-applied"])

    def test_content_change_unchanged_and_design_path_in_it_refused(self):
        css = self.published("style.css")
        self.assertEqual(self.apply()["result"], "applied")
        self.assertEqual(self.entry()["state"], "pushed")
        self.assertEqual(self.published("index.html"), git(self.repo.wt, "show", "HEAD:hass/content/store.json"))
        pushed = git(self.bare, "rev-parse", "main")
        self.now += timedelta(seconds=61)
        self.extra = {"style.css": b"body { color: red; }\n"}  # a design file changed inside a content release
        self.assertEqual(self.apply(self.draft(["Fixture new hours"]))["result"], "applied")
        self.assertEqual((self.entry()["state"], self.entry()["step"]), ("not-published", "checks"))
        self.assertEqual((git(self.bare, "rev-parse", "main"), self.published("style.css")), (pushed, css))


    def crash(self):
        """A tracked unrelated file, then a design apply cut off after the cherry-pick staged the look (journal left behind)."""
        (self.repo.wt / "hass/voice.py").write_text("voice = 1\n")
        git(self.repo.wt, "add", "-A")
        git(self.repo.wt, "commit", "-q", "-m", "voice")
        self.before, self.ok = self.repo.head(), self.look("crash", css_edit)
        self.cut = self.design(self.ok)["draft"]
        with mock.patch.object(editor, "_post_checks", side_effect=RuntimeError("power cut")), self.assertRaises(RuntimeError):
            editor.apply(self.cut["change_id"], self.cut["draft_hash"], state=str(self.repo.state))
        self.assertIn(CSS, self.repo.status())

    def refused_and_kept(self, rel, text):
        (self.repo.wt / rel).write_text(text)
        status, out = self.repo.status(), editor.recover(state=str(self.repo.state))
        self.assertEqual(out["result"], "refused")
        self.assertEqual(((self.repo.wt / rel).read_text(), self.repo.head(), self.repo.status()), (text, self.before, status))
        self.assertTrue((self.repo.state / "journal" / (self.cut["change_id"] + ".json")).is_file())  # left for the attended path

    def test_recovery_keeps_an_unrelated_tracked_edit(self):
        self.crash()
        self.refused_and_kept("hass/voice.py", "voice = 2  # mine\n")

    def test_recovery_keeps_a_post_crash_edit_to_the_design_path(self):
        self.crash()
        self.refused_and_kept(CSS, "body { color: blue; }\n")

    def test_crash_alone_recovers_and_a_later_apply_lands(self):
        self.crash()
        out = editor.recover(state=str(self.repo.state))
        self.assertEqual(out["recovered"], [{"change_id": self.cut["change_id"], "state": "failed"}])
        self.assertEqual((self.repo.head(), self.repo.status()), (self.before, ""))
        again = self.design(self.ok)["draft"]
        self.assertEqual(self.live.apply(again["change_id"], again["draft_hash"])["result"], "applied")
        self.assertEqual(self.css_at("HEAD"), self.css_at(self.ok["head"]))


del R  # no module-level ReleaseCase: unittest discovery would run its tests here again


class LooksKey(unittest.TestCase):
    def test_looks_is_an_optional_bool_passed_to_the_worker(self):
        tmp = Path(tempfile.mkdtemp(prefix="hass-looks-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))

        def load(**over):
            cfg = {"state": str(tmp / "state"), "secretFile": str(tmp / "key"), "listen": "127.0.0.1:8795",
                   "allowedPeers": ["127.0.0.1"], "approvals": "hold", "runtimeCommit": "0" * 40,
                   "interpreter": {"url": "http://127.0.0.1:11434", "model": "m"}, **over}
            path = tmp / "host.json"
            path.write_text(json.dumps(cfg))
            os.chmod(path, 0o600)
            return host.load_host(path)
        self.assertNotIn("looks", load())
        self.assertIs(load(looks=True)["looks"], True)
        for wrong in ({"looks": "yes"}, {"looks": 1}, {"look": True}):
            with self.subTest(wrong), self.assertRaises(host.HostConfigError): load(**wrong)
        built = []

        class FakeConv:
            def __init__(self, *a, **k):
                self.settings, self.editor = {}, None
                built.append(self)
        with mock.patch.object(host, "_worktree", return_value="/nowhere"), mock.patch.object(host.conversation, "Conversation", FakeConv), \
                mock.patch.object(host.receiver, "Receiver"), mock.patch.object(host.inbox_mod, "Inbox"), mock.patch.object(host, "Worker"):
            for cfg in (load(), load(looks=False), load(looks=True)): host.make_worker(cfg, None, build=lambda: None)
        self.assertEqual([c.looks for c in built], [False, False, True])


if __name__ == "__main__":
    unittest.main()
