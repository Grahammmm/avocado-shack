"""AV1104-10 tests: hass/design_preview.py, the H24 private base/head design capture.

Pure CLI/orchestration cases use synthetic Git repositories and a fake Previewer (no browser). The real-Chromium cases are
skipped unless PLAYWRIGHT_MODULE is set, like test_preview."""

import contextlib, io, json, os, struct, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import design_preview as dp
from hass.design_check import DESIGN, Usage

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "hass" / "design_preview.py"
SHELL = ("<html><head><link rel=stylesheet href=/style.css><link rel=stylesheet href=/hiking.css>"
         "<link rel=stylesheet href=/trail-explorer.css></head>"
         "<body><section class=hero><h1>Hello</h1></section><main><h1>Trail</h1></main></body></html>")
FILES = {"hass/templates/index.html": SHELL, "hass/templates/hike/index.html": SHELL,
         "storefront-mockup/index.html": SHELL, "storefront-mockup/hike/index.html": SHELL,
         "storefront-mockup/style.css": "body{color:black}", "storefront-mockup/hiking.css": "h1{color:black}",
         "storefront-mockup/trail-explorer.css": "p{color:black}"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
OK_CHECKS = {"pageLoaded": True, "noHorizontalOverflow": True, "noPageErrors": True, "noPosts": True,
             "desktop:pageLoaded": True}
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def git(repo, *args, data=None):
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=GIT_ENV, input=data, check=True)
    return out.stdout.decode("utf-8", "replace").strip()


def write(repo, rel, content):
    path = Path(repo, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())


def save(repo, files, message="c"):
    for rel, content in files.items():
        write(repo, rel, content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class RepoCase(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory(prefix="design-preview-")
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.root = save(self.repo, FILES, "root")
        self.out = self.tmp / "out"
        self.addCleanup(os.chdir, os.getcwd())

    def branch(self, name, files, start="main"):
        git(self.repo, "checkout", "-q", "-B", name, start)
        return save(self.repo, files, name)

    def cli(self, *args, cwd=None):
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True,
                              cwd=cwd or self.repo, env={**GIT_ENV, "PYTHONDONTWRITEBYTECODE": "1"})
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout + proc.stderr)
        return proc.returncode, json.loads(lines[0]), proc.stderr

    def run_fake(self, previewer, base="main", head="feature", out=None):
        os.chdir(self.repo)
        return dp.run(base, head, str(out or self.out), previewer)

    def snapshot(self):
        return (git(self.repo, "status", "--porcelain=v1", "-uall"), git(self.repo, "rev-parse", "HEAD"),
                git(self.repo, "symbolic-ref", "HEAD"), (self.repo / ".git" / "index").read_bytes(),
                (self.repo / ".git" / "config").read_bytes())


class FakePreviewer:
    """Records each capture call; ``plan`` maps (page, call index) -> result override."""
    def __init__(self, plan=None):
        self.calls, self.plan = [], plan or {}

    def capture(self, files, target, out_png):
        self.calls.append((dict(files), dict(target), Path(out_png)))
        override = self.plan.get(len(self.calls) - 1, "ok")
        if override == "ok" or override == "desktop-missing" or override == "ghost":
            if override != "ghost":
                Path(out_png).write_bytes(PNG)
                os.chmod(out_png, 0o600)
            desktop = Path(out_png).with_name(Path(out_png).stem + "-desktop.png")
            if override == "ok":
                desktop.write_bytes(PNG)
                os.chmod(desktop, 0o600)
            return {"ok": override == "ok", "png": str(out_png), "checks": dict(OK_CHECKS),
                    "desktopPng": str(desktop), "error": None}
        if override == "phone-fail":
            return {"ok": False, "png": None, "checks": {}, "error": "raw node stderr SECRET"}
        if override == "check-fail":
            Path(out_png).write_bytes(PNG)
            os.chmod(out_png, 0o600)
            return {"ok": False, "png": str(out_png), "checks": {**OK_CHECKS, "noHorizontalOverflow": False}}
        if override == "bad-checks":
            Path(out_png).write_bytes(PNG)
            os.chmod(out_png, 0o600)
            return {"ok": True, "png": str(out_png), "checks": {"pageLoaded": "yes"}}
        raise AssertionError(override)


class ScopeAndRefTests(RepoCase):
    def test_scope_gate_precedes_out_and_capture(self):
        self.branch("feature", {"hass/evil.py": "x=1", "storefront-mockup/style.css": "body{color:red}"})
        self.branch("html", {"storefront-mockup/index.html": SHELL + "<!-- x -->"})  # page without its template
        fake = FakePreviewer()
        for head, expect in (("feature", "A hass/evil.py"), ("html", "unpaired storefront-mockup/index.html")):
            code, doc = self.run_fake(fake, head=head)
            self.assertEqual((code, doc["result"], doc["captures"]), (1, "outside", []))
            self.assertIn(expect, doc["outside"])
        self.assertEqual(fake.calls, [])
        self.assertFalse(self.out.exists())
        git(self.repo, "checkout", "-q", "feature")
        code, doc, _ = self.cli("--base", "main", "--head", "feature", "--out", str(self.out))
        self.assertEqual((code, doc["result"], doc["captures"]), (1, "outside", []))
        self.assertFalse(self.out.exists())

    def test_deletion_symlink_and_executable_are_outside(self):
        self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})
        git(self.repo, "rm", "-q", "storefront-mockup/hiking.css")
        git(self.repo, "commit", "-q", "-m", "del")
        self.assertEqual(self.run_fake(FakePreviewer())[1]["result"], "outside")
        self.branch("link", {})
        (self.repo / "storefront-mockup" / "style.css").unlink()
        os.symlink("hiking.css", self.repo / "storefront-mockup" / "style.css")
        save(self.repo, {})
        self.assertEqual(self.run_fake(FakePreviewer(), head="link")[1]["result"], "outside")

    def test_bad_refs_are_usage_and_make_nothing(self):
        self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})
        git(self.repo, "checkout", "-q", "--orphan", "other")
        save(self.repo, {"readme": "x"}, "unrelated")
        for base, head in (("--help", "feature"), ("main", "nope"), ("main", "feature^{tree}"), ("main", "other"), ("", "feature")):
            code, doc, err = self.cli("--base", base, "--head", head, "--out", str(self.out))
            self.assertEqual((code, doc), (2, {"result": "usage"}), (base, head))
            self.assertIn("design_preview:", err)
        self.assertFalse(self.out.exists())
        code, doc, _ = self.cli("--base", "main", "--head", "feature", "--out", str(self.out), cwd=self.tmp)
        self.assertEqual((code, doc), (2, {"result": "usage"}))  # not inside a work tree

    def test_resolved_refs_and_merge_base_are_not_confused(self):
        head_sha = self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})
        side_sha = self.branch("side", {"storefront-mockup/hiking.css": "h1{color:green}"})
        # diverged: only the head-side change counts, yet each side's own bytes are captured
        fake = FakePreviewer()
        code, doc = self.run_fake(fake, base="side", head="feature")
        self.assertEqual((code, doc["result"], doc["changed"], doc["head"], doc["base"]), (0, "ok", 1, head_sha, side_sha))
        self.assertEqual(fake.calls[0][0]["storefront-mockup/hiking.css"], b"h1{color:green}")
        self.assertEqual(fake.calls[2][0]["storefront-mockup/hiking.css"], b"h1{color:black}")
        # head already merged into base, and identical refs: nothing changed, still captured
        for base, head in (("feature", "main"), ("feature", "feature")):
            fresh = FakePreviewer()
            out = self.tmp / f"o-{base}-{head}"
            code, doc = self.run_fake(fresh, base=base, head=head, out=out)
            self.assertEqual((code, doc["changed"], len(fresh.calls)), (0, 0, 4))


class OverlayTests(RepoCase):
    def test_complete_design_overlays_not_worktree_or_changed_only(self):
        self.branch("basebr", {"storefront-mockup/hiking.css": b"h1{color:\xff\xfe}", "storefront-mockup/index.html": SHELL + "<!--b-->",
                               "hass/templates/index.html": SHELL + "<!--b-->"})
        self.branch("feature", {"storefront-mockup/style.css": "body{color:red}", "storefront-mockup/trail-explorer.css": "p{color:red}"}, start="main")
        write(self.repo, "storefront-mockup/style.css", "POISON worktree")
        write(self.repo, "storefront-mockup/hiking.css", "POISON worktree")
        fake = FakePreviewer()
        code, doc = self.run_fake(fake, base="basebr", head="feature")
        self.assertEqual(code, 0, doc)
        files = [c[0] for c in fake.calls]
        for one in files:
            self.assertEqual(set(one), {p for p in DESIGN if p.startswith("storefront-mockup/")})
        base_files, head_files = files[0], files[2]
        self.assertEqual(base_files["storefront-mockup/hiking.css"], b"h1{color:\xff\xfe}")  # non-UTF8 bytes survive
        self.assertEqual(base_files["storefront-mockup/style.css"], b"body{color:black}")
        self.assertEqual(head_files["storefront-mockup/hiking.css"], b"h1{color:black}")
        self.assertEqual(head_files["storefront-mockup/style.css"], b"body{color:red}")
        self.assertEqual(head_files["storefront-mockup/trail-explorer.css"], b"p{color:red}")
        self.assertTrue(base_files["storefront-mockup/index.html"].endswith(b"<!--b-->"))
        self.assertEqual(files[0], files[1])  # both pages of a side share one overlay
        self.assertEqual([c[1] for c in fake.calls], [{"kind": "design", "page": p} for p in ("home", "hike") * 2])

    def test_unsafe_or_one_sided_members_fail_before_output(self):
        self.branch("exec", {"storefront-mockup/style.css": "body{}"})
        os.chmod(self.repo / "storefront-mockup" / "style.css", 0o755)
        save(self.repo, {}, "x")
        # a member present in only the base ref
        self.branch("nohiking", {})
        git(self.repo, "rm", "-q", "storefront-mockup/hiking.css")
        git(self.repo, "commit", "-q", "-m", "rm")
        git(self.repo, "checkout", "-q", "main")
        fake = FakePreviewer()
        os.chdir(self.repo)
        self.assertEqual(dp.run("main", "exec", str(self.out), fake)[1]["result"], "outside")  # head side: the scope gate
        for base, head in (("exec", "main"), ("nohiking", "main")):  # base side: the blob check
            with self.assertRaises(Usage, msg=(base, head)):
                dp.run(base, head, str(self.out), fake)
        self.assertEqual(fake.calls, [])
        self.assertFalse(self.out.exists())
        code, doc, _ = self.cli("--base", "exec", "--head", "main", "--out", str(self.out))
        self.assertEqual((code, doc), (2, {"result": "usage"}))

    def test_missing_member_in_both_refs_needs_worktree_without_it(self):
        self.branch("nocss", {})
        git(self.repo, "rm", "-q", "storefront-mockup/trail-explorer.css")
        git(self.repo, "commit", "-q", "-m", "rm")
        fake = FakePreviewer()
        code, doc = self.run_fake(fake, base="nocss", head="nocss")
        self.assertEqual(code, 0)
        self.assertNotIn("storefront-mockup/trail-explorer.css", fake.calls[0][0])
        write(self.repo, "storefront-mockup/trail-explorer.css", "leftover")  # untracked worktree copy would leak in
        with self.assertRaises(Usage):
            self.run_fake(FakePreviewer(), base="nocss", head="nocss", out=self.tmp / "o2")
        git(self.repo, "rm", "-q", "--cached", "storefront-mockup/index.html")
        git(self.repo, "commit", "-q", "-m", "no home")
        os.unlink(self.repo / "storefront-mockup" / "trail-explorer.css")
        os.unlink(self.repo / "storefront-mockup" / "index.html")
        with self.assertRaises(Usage):  # the home page is required
            self.run_fake(FakePreviewer(), base="nocss", head="nocss", out=self.tmp / "o3")


class OutputTests(RepoCase):
    def prepare(self, out):
        os.chdir(self.repo)
        return dp.prepare_out(str(out), str(self.repo))

    def test_output_is_private_and_external(self):
        refused = [self.repo / "shots", self.repo / ".git" / "shots", self.repo]
        outside_file = self.tmp / "file"
        outside_file.write_text("x")
        refused.append(outside_file)
        bad_mode = self.tmp / "open"
        bad_mode.mkdir()
        os.chmod(bad_mode, 0o755)
        refused.append(bad_mode)
        full = self.tmp / "full"
        full.mkdir(mode=0o700)
        (full / "stale.png").write_bytes(PNG)
        refused.append(full)
        real = self.tmp / "real"
        real.mkdir(mode=0o700)
        os.symlink(real, self.tmp / "linkdir")
        os.symlink(self.tmp / "nowhere", self.tmp / "dangling")
        refused += [self.tmp / "linkdir", self.tmp / "linkdir" / "sub", self.tmp / "dangling", self.tmp / "missing" / "deeper", Path("")]
        for path in refused:
            with self.assertRaises(Usage, msg=str(path)):
                self.prepare(path)
        self.assertEqual(list(real.iterdir()), [])
        self.assertFalse((self.tmp / "nowhere").exists())
        self.assertFalse((self.repo / "shots").exists())
        fresh = self.prepare(self.tmp / "fresh")
        self.assertEqual(oct(os.stat(fresh).st_mode & 0o777), "0o700")
        empty = self.tmp / "empty"
        empty.mkdir(mode=0o700)
        self.assertEqual(self.prepare(empty), empty)
        # a linked worktree's metadata folder is guarded too
        linked = self.tmp / "linked"
        git(self.repo, "worktree", "add", "-q", "-b", "wt", str(linked))
        os.chdir(linked)
        with self.assertRaises(Usage):
            dp.prepare_out(str(self.repo / ".git" / "worktrees" / "x"), str(linked))

    def test_capture_order_names_checks_and_partial_failures(self):
        self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})
        fake = FakePreviewer()
        code, doc = self.run_fake(fake)
        self.assertEqual((code, doc["result"]), (0, "ok"))
        self.assertEqual([c[2].name for c in fake.calls], ["base-home-phone.png", "base-hike-phone.png", "head-home-phone.png", "head-hike-phone.png"])
        names = sorted(p.name for p in self.out.iterdir())
        self.assertEqual(names, sorted(f"{s}-{p}-phone{d}.png" for s in ("base", "head") for p in ("home", "hike") for d in ("", "-desktop")))
        self.assertTrue(all(os.stat(p).st_mode & 0o777 == 0o600 for p in self.out.iterdir()))
        self.assertEqual([(c["side"], c["page"], c["error"]) for c in doc["captures"]],
                         [("base", "home", None), ("base", "hike", None), ("head", "home", None), ("head", "hike", None)])
        self.assertTrue(all(c["png"] and c["desktopPng"] for c in doc["captures"]))

    def test_failures_are_reported_honestly_and_later_pages_still_run(self):
        self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})
        plan = {0: "phone-fail", 1: "check-fail", 2: "desktop-missing", 3: "ghost"}
        fake = FakePreviewer(plan)
        code, doc = self.run_fake(fake)
        self.assertEqual((code, doc["result"], len(fake.calls)), (1, "preview-failed", 4))
        base_home, base_hike, head_home, head_hike = doc["captures"]
        self.assertEqual((base_home["png"], base_home["desktopPng"], base_home["error"]), (None, None, "capture failed"))
        self.assertEqual(base_hike["error"], "check failed: noHorizontalOverflow")
        self.assertFalse(base_hike["checks"]["noHorizontalOverflow"])
        self.assertEqual((head_home["error"], head_home["desktopPng"]), ("missing desktop png", None))
        self.assertIsNone(head_hike["png"])  # a path the preview named that does not exist is never listed
        self.assertNotIn("SECRET", json.dumps(doc))
        self.assertTrue(all(type(v) is bool for c in doc["captures"] for v in c["checks"].values()))
        fake = FakePreviewer({0: "bad-checks"})
        code, doc = self.run_fake(fake, out=self.tmp / "again")
        self.assertEqual((code, doc["captures"][0]["error"]), (1, "bad checks"))

    def test_main_prints_exactly_one_json_line_and_leaves_git_alone(self):
        self.branch("feature", {"storefront-mockup/style.css": "body{color:red}"})
        write(self.repo, "storefront-mockup/style.css", "dirty tracked")
        write(self.repo, "untracked.txt", "u")
        before = self.snapshot()
        buf = io.StringIO()
        with mock.patch.object(dp, "Previewer", lambda top: FakePreviewer()), contextlib.redirect_stdout(buf):
            os.chdir(self.repo)
            code = dp.main(["--base", "main", "--head", "feature", "--out", str(self.out)])
        self.assertEqual((code, len(buf.getvalue().splitlines())), (0, 1))
        self.assertEqual(json.loads(buf.getvalue())["result"], "ok")
        self.cli("--base", "main", "--head", "nope", "--out", str(self.tmp / "x"))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.repo / "storefront-mockup" / "style.css").read_text(), "dirty tracked")


def png_width(path):
    data = Path(path).read_bytes()
    return struct.unpack(">I", data[16:20])[0]


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class BrowserTests(RepoCase):
    def setUp(self):
        super().setUp()
        for name in ("community-server.py", "community.json"):  # the real loopback server the Previewer runs
            write(self.repo, f"storefront-mockup/{name}", (ROOT / "storefront-mockup" / name).read_bytes())
        (self.repo / "storefront-mockup" / "assets").mkdir()
        save(self.repo, {}, "server")

    def test_browser_eight_real_pngs_and_distinct_ref_designs(self):
        self.branch("feature", {"storefront-mockup/style.css": "body{background:#0000ff}"})
        git(self.repo, "checkout", "-q", "-B", "basebr", "main")
        save(self.repo, {"storefront-mockup/style.css": "body{background:#ff0000}"}, "red")
        git(self.repo, "checkout", "-q", "main")
        write(self.repo, "storefront-mockup/style.css", "body{background:#00ff00}")  # dirty worktree must not leak
        before = self.snapshot()
        code, doc, _ = self.cli("--base", "basebr", "--head", "feature", "--out", str(self.out))
        self.assertEqual((code, doc["result"]), (0, "ok"), doc)
        self.assertEqual(len(doc["captures"]), 4)
        for cap in doc["captures"]:
            self.assertTrue(all(cap["checks"].values()), cap)
            self.assertEqual((png_width(cap["png"]), png_width(cap["desktopPng"])), (390, 1280))
            for path in (cap["png"], cap["desktopPng"]):
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
                self.assertEqual(Path(path).read_bytes()[:8], PNG[:8])
        by = {(c["side"], c["page"]): Path(c["png"]).read_bytes() for c in doc["captures"]}
        for page in ("home", "hike"):
            self.assertTrue(by[("base", page)] != by[("head", page)], page)  # red vs blue page backgrounds
        self.assertEqual(len(list(self.out.iterdir())), 8)
        self.assertEqual(self.snapshot(), before)

    def test_page_check_failures_and_request_gate(self):
        self.branch("wide", {"storefront-mockup/style.css": "body{width:3000px}"})
        code, doc, _ = self.cli("--base", "main", "--head", "wide", "--out", str(self.out))
        self.assertEqual((code, doc["result"]), (1, "preview-failed"))
        base, head = doc["captures"][0], doc["captures"][2]
        self.assertIsNone(base["error"])
        self.assertEqual(head["error"], "check failed: noHorizontalOverflow")
        self.assertTrue(head["png"] and Path(head["png"]).is_file())  # partial evidence kept
        self.assertTrue(head["checks"]["noPosts"])
        broken = self.branch("broken", {"storefront-mockup/index.html": "<html><body>no heading</body></html>",
                                        "hass/templates/index.html": "<html><body>no heading</body></html>"})
        code, doc, _ = self.cli("--base", "main", "--head", broken, "--out", str(self.tmp / "o2"))
        self.assertEqual((code, doc["captures"][2]["error"]), (1, "check failed: pageLoaded"))

    def test_page_enum_and_routes(self):
        shot = self.tmp / "shot.png"
        script = ROOT / "hass" / "screenshot.cjs"
        env = {**os.environ, "PREVIEW_URL": "http://127.0.0.1:9", "OUT": str(shot), "VIEWPORT": "phone"}
        for page in ("elsewhere", "http://example.com/", "", None):
            target = {"kind": "design", "page": page}
            proc = subprocess.run(["node", str(script)], env={**env, "TARGET": json.dumps(target)}, capture_output=True, text=True)
            self.assertEqual((proc.returncode, proc.stderr.strip()), (1, "bad design page"), page)  # before any navigation
        self.assertFalse(shot.exists())
        from hass.preview import Previewer
        seen = []
        for page, heading in (("home", "Hello"), ("hike", "Trail")):
            write(self.repo, "storefront-mockup/index.html", SHELL)
            result = Previewer(self.repo).capture({}, {"kind": "design", "page": page}, self.tmp / f"{page}.png")
            self.assertTrue(result["ok"], result)
            seen.append(result["checks"])
        self.assertTrue(all(c["pageLoaded"] and c["noHorizontalOverflow"] for c in seen))


if __name__ == "__main__":
    unittest.main()
