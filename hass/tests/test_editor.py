"""H02 tests: typed editing service, drafts, single writer, recovery.

Each test builds a throwaway Git repo (copied hass/ and site files, images linked
read-only) with a linked writer worktree on branch hass/content and a private
temp state dir. Nothing touches the checkout, the live service or its database.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import contextlib
import fcntl
import http.client
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from hass import editor, migration_check
from hass.content_model import REPO_ROOT, SITE_DIR
from hass.tests import fixture_ops

HOURS, DESC = "test.set_store_hours", "test.set_product_description"
NEW_HOURS = ["Monday–Saturday 9am–6pm", "Closed Sunday"]
SITE_FILES = editor.GENERATED_PATHS + tuple("storefront-mockup/" + n for n in (
    "held-products.json", "hiking-preview.json", "community-server.py"))


def _req(*ops):
    return {"ops": [{"op": name, "args": args} for name, args in ops]}


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout.strip()


class WriterRepo:
    """Temp repo on main plus a linked writer worktree and an initialised 0700 state dir."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="hass-h02-")
        tmp = Path(self._tmp.name)
        self.main, self.wt, self.state = tmp / "main", tmp / "writer", tmp / "state"
        shutil.copytree(REPO_ROOT / "hass", self.main / "hass", ignore=shutil.ignore_patterns("__pycache__"))
        (self.main / "storefront-mockup" / "hike").mkdir(parents=True)
        for rel in SITE_FILES:
            shutil.copyfile(REPO_ROOT / rel, self.main / rel)
        (self.main / "storefront-mockup" / "assets").symlink_to(SITE_DIR / "assets", target_is_directory=True)
        git(tmp, "init", "-q", "-b", "main", str(self.main))
        git(self.main, "config", "user.name", "hass-test")
        git(self.main, "config", "user.email", "hass-test@example.invalid")
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "base")
        git(self.main, "worktree", "add", "-q", "-b", "hass/content", str(self.wt))
        self.state.mkdir(mode=0o700)
        assert editor.init(str(self.state), str(self.wt))["result"] == "ok"

    def prepare(self, request):
        return editor.prepare(request, state=str(self.state), registry=fixture_ops.registry())

    def apply(self, draft):
        return editor.apply(draft["change_id"], draft["draft_hash"], state=str(self.state),
                            registry=fixture_ops.registry())

    def head(self):
        return git(self.wt, "rev-parse", "HEAD")

    def status(self):
        return git(self.wt, "status", "--porcelain")

    def drafts(self):
        d = self.state / "drafts"
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def cleanup(self):
        self._tmp.cleanup()


class EditorTestCase(unittest.TestCase):
    def repo(self):
        repo = WriterRepo()
        self.addCleanup(repo.cleanup)
        return repo


class TypedInputTests(EditorTestCase):
    def test_invalid_requests_write_no_draft(self):
        repo = self.repo()
        good = {"op": HOURS, "args": {"hours": NEW_HOURS}}
        cases = {
            "unknown op": _req(("test.delete_everything", {})),
            "unknown arg": _req((HOURS, {"hours": NEW_HOURS, "path": "/etc/passwd"})),
            "wrong kind": _req((HOURS, {"hours": "9am-6pm"})),
            "wrong kind id": _req((DESC, {"id": ["photo-product-001"], "description": "Fresh."})),
            "script text": _req((DESC, {"id": "photo-product-001", "description": "Nice <script>x</script>"})),
            "dollar text": _req((DESC, {"id": "photo-product-001", "description": "Only $3 today."})),
            "over 64 KiB": _req((HOURS, {"hours": ["9am " * 17000]})),
            "extra top-level key": {"ops": [good], "sql": "select 1"},
            "NUL character": _req((HOURS, {"hours": ["9am\x00"]})),
        }
        for name, request in cases.items():
            with self.subTest(case=name):
                result = repo.prepare(request)
                self.assertEqual(result["result"], "invalid", result)
                self.assertTrue(result["problems"])
                self.assertEqual(repo.drafts(), [])
        self.assertEqual(repo.status(), "")

    def test_missing_required_arg_needs_details(self):
        repo = self.repo()
        result = repo.prepare(_req((DESC, {"id": "photo-product-001"})))
        self.assertEqual(result["result"], "needs-details", result)
        self.assertEqual(result["missing"], ["description"])
        self.assertEqual(repo.drafts(), [])


class DraftTests(EditorTestCase):
    def test_prepare_store_hours_draft_is_bound_and_idempotent(self):
        repo = self.repo()
        before = json.loads((repo.wt / "hass" / "content" / "store.json").read_text("utf-8"))
        result = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))
        self.assertEqual(result["result"], "ok", result)
        draft = result["draft"]
        self.assertEqual(draft["base"], editor.content_revision(repo.wt))
        self.assertEqual(draft["records"], [{"collection": "store", "key": "store", "before": before,
                                             "after": {**before, "hours": NEW_HOURS}}])
        # Only index.html shows the hours; hike/index.html carries the address slot alone, so it is unchanged.
        self.assertEqual(draft["generated"], ["storefront-mockup/index.html"])
        self.assertRegex(draft["change_id"], r"^chg-[0-9a-f]{12}$")
        self.assertEqual(draft["change_id"], "chg-" + draft["draft_hash"][7:19])
        again = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        self.assertEqual((again["change_id"], again["draft_hash"]), (draft["change_id"], draft["draft_hash"]))
        self.assertEqual(repo.drafts(), [draft["change_id"] + ".json"])
        self.assertEqual(os.stat(repo.state / "drafts" / repo.drafts()[0]).st_mode & 0o777, 0o600)
        self.assertEqual(repo.status(), "")


class ApplyTests(EditorTestCase):
    def test_apply_once_makes_one_signed_content_only_commit(self):
        repo = self.repo()
        draft = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        start = repo.head()
        result = repo.apply(draft)
        self.assertEqual(result["result"], "applied", result)
        self.assertEqual(git(repo.wt, "rev-list", "--count", f"{start}..HEAD"), "1")
        self.assertEqual(result["commit"], repo.head())
        names = git(repo.wt, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertTrue(set(names) <= set(editor.OWNED_PATHS), names)
        self.assertEqual(sorted(names), sorted(["hass/content/store.json"] + draft["generated"]))
        self.assertEqual(git(repo.wt, "log", "-1", "--format=%s"), f"hass content: {draft['change_id']}")
        self.assertIn("Signed-off-by: hass-test <hass-test@example.invalid>", git(repo.wt, "log", "-1", "--format=%B"))
        shown = editor.show(draft["change_id"], state=str(repo.state))
        self.assertEqual((shown["change"]["state"], shown["change"]["commit"]), ("applied", repo.head()))
        again = repo.apply(draft)
        self.assertEqual((again["result"], again["commit"]), ("already-applied", result["commit"]))
        self.assertEqual(git(repo.wt, "rev-list", "--count", f"{start}..HEAD"), "1")
        self.assertEqual(migration_check.run_checks(repo.wt)[0], [])
        self.assertEqual(repo.status(), "")


class FailClosedTests(EditorTestCase):
    def assertUnchanged(self, repo, head, status):
        self.assertEqual((repo.head(), repo.status()), (head, status))

    def test_older_draft_is_stale_after_products_change(self):
        repo = self.repo()
        old = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        other = repo.prepare(_req((DESC, {"id": "photo-product-001", "description": "Ripe and creamy."})))["draft"]
        self.assertEqual(repo.apply(other)["result"], "applied")
        self.assertIn("hass/content/products.json", git(repo.wt, "show", "--name-only", "--format=", "HEAD"))
        head = repo.head()
        result = repo.apply(old)
        self.assertEqual(result["result"], "stale", result)
        self.assertUnchanged(repo, head, "")

    def test_lock_held_gives_busy(self):
        repo = self.repo()
        draft = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        head = repo.head()
        with open(repo.state / "writer.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(repo.apply(draft)["result"], "busy")
        self.assertUnchanged(repo, head, "")

    def test_unsafe_worktrees_are_refused(self):
        def dirty(repo):
            (repo.wt / "hass" / "content" / "store.json").write_text("{}\n", encoding="utf-8")

        def main_checkout(repo):
            config = repo.state / "config.json"
            config.write_text(json.dumps({"worktree": str(repo.main), "settings": {}}), encoding="utf-8")

        def detached(repo):
            git(repo.wt, "checkout", "-q", "--detach")

        def branch_main(repo):
            git(repo.main, "checkout", "-q", "--detach")
            git(repo.wt, "checkout", "-q", "main")

        for name, setup in {"dirty": dirty, "main checkout": main_checkout, "detached": detached,
                            "branch main": branch_main}.items():
            with self.subTest(case=name):
                repo = self.repo()
                draft = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
                setup(repo)
                target = repo.main if name == "main checkout" else repo.wt
                head, status = git(target, "rev-parse", "HEAD"), git(target, "status", "--porcelain")
                result = repo.apply(draft)
                self.assertEqual(result["result"], "refused", result)
                self.assertEqual((git(target, "rev-parse", "HEAD"), git(target, "status", "--porcelain")),
                                 (head, status))
                self.assertFalse((repo.state / "changes").exists())

    def test_group_readable_state_dir_makes_cli_exit_2(self):
        repo = self.repo()
        draft = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        head = repo.head()
        os.chmod(repo.state, 0o755)
        for argv in (["show", draft["change_id"]], ["apply", draft["change_id"], "--hash", draft["draft_hash"]]):
            with self.subTest(argv=argv[0]):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = editor.main(argv + ["--state", str(repo.state)])
                self.assertEqual(code, 2, out.getvalue())
                self.assertEqual(json.loads(out.getvalue())["result"], "unsafe-state")
        self.assertUnchanged(repo, head, "")


class RecoveryTests(EditorTestCase):
    def journal(self, repo, draft, base_commit):
        editor._write_json(repo.state / "journal" / f"{draft['change_id']}.json",
                           {"phase": "writing", "change_id": draft["change_id"], "base_commit": base_commit,
                            "paths": ["hass/content/store.json"]})

    def test_interrupted_write_is_restored_and_failed(self):
        repo = self.repo()
        draft = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        head = repo.head()
        self.journal(repo, draft, head)
        (repo.wt / "hass" / "content" / "store.json").write_text("{}\n", encoding="utf-8")
        result = editor.recover(state=str(repo.state))
        self.assertEqual(result["recovered"], [{"change_id": draft["change_id"], "state": "failed"}])
        self.assertEqual((repo.head(), repo.status()), (head, ""))
        change = editor.show(draft["change_id"], state=str(repo.state))["change"]
        self.assertEqual(change["state"], "failed")
        self.assertEqual(list((repo.state / "journal").iterdir()), [])

    def test_committed_change_is_recorded_applied(self):
        repo = self.repo()
        draft = repo.prepare(_req((HOURS, {"hours": NEW_HOURS})))["draft"]
        commit = repo.apply(draft)["commit"]
        (repo.state / "changes" / f"{draft['change_id']}.json").unlink()
        self.journal(repo, draft, git(repo.wt, "rev-parse", "HEAD~1"))
        result = editor.recover(state=str(repo.state))
        self.assertEqual(result["recovered"], [{"change_id": draft["change_id"], "state": "applied"}])
        change = editor.show(draft["change_id"], state=str(repo.state))["change"]
        self.assertEqual((change["state"], change["commit"]), ("applied", commit))
        self.assertEqual(repo.head(), commit)


class NoPublicWriteRouteTests(EditorTestCase):
    def test_community_server_has_no_apply_route(self):
        repo = self.repo()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {**os.environ, "AVOSHACK_COMMUNITY_DB": str(Path(repo._tmp.name) / "community.sqlite3")}
        server = subprocess.Popen([sys.executable, str(repo.main / "storefront-mockup" / "community-server.py"),
                                   "--port", str(port)], env=env, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        self.addCleanup(server.wait)
        self.addCleanup(server.terminate)
        before = (editor.content_revision(repo.main), editor.content_revision(repo.wt))
        body = json.dumps(_req((HOURS, {"hours": NEW_HOURS}))).encode()
        for _ in range(100):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("POST", "/api/hass/apply", body=body,
                             headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
                status = conn.getresponse().status
                conn.close()
                break
            except ConnectionRefusedError:
                time.sleep(0.1)
        else:
            self.fail("community server did not start")
        self.assertEqual(status, 404)
        self.assertEqual((editor.content_revision(repo.main), editor.content_revision(repo.wt)), before)


if __name__ == "__main__":
    unittest.main()
