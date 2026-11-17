"""HASS-SITE-LOOK-1 tests: hass/look_change.py and hass/look_guard.py on a fixture writer repo with a fake Codex runner
(fixed diffs) and a fake previewer. No network, no browser, never the live site checkout (an unreadable LIVE folder)."""
import difflib, json, os, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import look_change, look_guard
from hass.design_check import DESIGN

PAGE = ("<html>\n<head>\n<meta charset=utf-8><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'\">\n"
        "<link rel=stylesheet href=style.css>\n</head>\n<body>\n<h1>Hello</h1>\n<p>Fresh food</p>\n</body>\n</html>\n")
CSS = "body {\n  color: black;\n}\nh1 {\n  margin: 0;\n}\n"
STUB_GEN = ("import pathlib\nt = pathlib.Path('hass/templates')\nm = pathlib.Path('storefront-mockup')\n"
            "pairs = [(t / 'index.html', m / 'index.html'), (t / 'hike/index.html', m / 'hike/index.html')]\n"
            "pairs += [(t / 'info/index.html', m / p / 'index.html') for p in ('about', 'getting-here', 'policies', 'faq')]\n"
            "for src, dst in pairs:\n    if dst.read_text() != src.read_text(): dst.write_text(src.read_text())\n")
FILES = {**{p: CSS if p.endswith(".css") else PAGE for p in DESIGN}, "hass/__init__.py": "", "hass/tests/__init__.py": "",
         "hass/sitegen.py": STUB_GEN, "hass/house_style.py": "print('ok')\n",
         "storefront-mockup/community.js": "x = 1;\n", "hass/content/store.json": "{}\n", "README.md": "readme\n",
         **{f"hass/tests/{t.split('.')[-1]}.py": "import unittest\nclass T(unittest.TestCase):\n    def test(self): pass\n"
            for t in look_change.SITE_TESTS}}
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
CHECKS = {f"{v}{b}": True for v in ("", "desktop:") for b in ("pageLoaded", "noHorizontalOverflow", "noPageErrors", "noPosts")}
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=GIT_ENV, check=True, text=True).stdout


def diff(path, old, new):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "a/" + path, "b/" + path))


def page_add(extra, path="hass/templates/index.html"):
    return diff(path, PAGE, PAGE.replace("<p>Fresh food</p>\n", "<p>Fresh food</p>\n" + extra + "\n"))


GOOD = diff("storefront-mockup/style.css", CSS, CSS.replace("color: black;", "color: #2f5d3a;\n  font-size: 1.1rem;"))
BAD = {  # reason -> model diff
    "tag": [page_add(x) for x in ("<script src=a.js></script>", "<form action=x>", "<input name=q>", "<iframe src=x>",
                                  "<embed src=x>", "<object data=x>", "<SCRIPT>", "&lt;script&gt;")],
    "handler": [page_add("<p onclick=\"x()\">Hi</p>"), page_add("<img src=a.png ONERROR = x>")],
    "javascript": [page_add("<a href=\"java\tscript:x\">Hi</a>"), page_add("<a href=\"&#106;avascript:x\">Hi</a>")],
    "url": [page_add("<img src=\"https://evil.example/a.png\">"), page_add("<a href=\"//evil.example\">Go</a>"),
            diff("storefront-mockup/style.css", CSS, "@import url(https://evil.example/x.css);\n" + CSS),
            diff("storefront-mockup/hiking.css", CSS, CSS.replace("margin: 0;", "background: url('http://x.example/b.png');"))],
    "protected": [diff("hass/templates/index.html", PAGE, PAGE.replace("charset=utf-8", "charset=latin1")),
                  diff("hass/templates/index.html", PAGE, PAGE.replace("<link rel=stylesheet href=style.css>\n", "")),
                  diff("hass/templates/index.html", PAGE, PAGE.replace("<head>", "<head class=x>")),
                  diff("hass/templates/index.html", PAGE, PAGE.replace("default-src 'self'", "default-src *"))],
    "claims": [page_add("<p>All organic</p>"), diff("storefront-mockup/style.css", CSS, CSS + "h1::after {\n  content: \"organic\";\n}\n")],
    "commerce": [page_add("<p>Honey $5</p>"), page_add("<p>See our prices</p>")],
    "path": [diff("storefront-mockup/community.js", "x = 1;\n", "x = 2;\n"), diff("hass/content/store.json", "{}\n", "{\"a\": 1}\n"),
             diff("README.md", "readme\n", "changed\n"), diff("storefront-mockup/index.html", PAGE, PAGE.replace("Hello", "Hi"))],
    "mode": ["--- /dev/null\n+++ b/storefront-mockup/style.css\n@@ -0,0 +1 @@\n+a{}\n",
             "diff --git a/storefront-mockup/style.css b/storefront-mockup/style.css\nold mode 100644\nnew mode 100755\n",
             GOOD + "Hope this helps!\n", GOOD.replace("+1,6 @@", "+1,9 @@")],
    "apply": [GOOD.replace(" body {", " main {")],  # passes the guard, fails in the temporary worktree
}


class FakePreviewer:
    def __init__(self, top):
        self.calls = []

    def capture(self, files, target, out_png):
        self.calls.append(target)
        desktop = Path(out_png).with_name(Path(out_png).stem + "-desktop.png")
        for p in (Path(out_png), desktop):
            p.write_bytes(PNG)
            os.chmod(p, 0o600)
        return {"ok": True, "png": str(out_png), "desktopPng": str(desktop), "checks": dict(CHECKS)}


class LookChangeTest(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory(prefix="look-change-")
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.repo, self.live, self.n = self.tmp / "writer", self.tmp / "LIVE", 0
        for rel, text in FILES.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "root")
        self.live.mkdir()
        (self.live / "index.html").write_text(PAGE)
        os.chmod(self.live, 0)  # any open of the live checkout fails, and fails the good draft too
        self.addCleanup(os.chmod, self.live, 0o700)
        self.calls = []
        real = subprocess.run
        patcher = mock.patch("subprocess.run", side_effect=lambda *a, **k: self.calls.append((a, k)) or real(*a, **k))
        patcher.start()
        self.addCleanup(patcher.stop)

    def snapshot(self):
        return (git(self.repo, "status", "--porcelain=v1", "-uall", "--ignored"), git(self.repo, "symbolic-ref", "HEAD"),
                git(self.repo, "for-each-ref"), git(self.repo, "worktree", "list", "--porcelain"),
                (self.repo / ".git" / "index").read_bytes())

    def draft(self, model_diff, code="green", request="Make the page text dark green and a bit bigger.", **kw):
        self.n += 1
        runner = mock.Mock(return_value={"ok": True, "text": "```diff\n" + model_diff + "```\n"})
        doc = look_change.draft(self.repo, code, request, self.tmp / "ledger.json", str(self.tmp / f"out{self.n}"),
                                runner=runner, previewer=FakePreviewer(None), today="2026-11-16", **kw)
        self.runner = runner
        return doc

    def assert_live_untouched(self):
        self.assertFalse(any(str(self.live) in json.dumps([a, k], default=str) for a, k in self.calls))
        self.assertTrue(self.calls)

    def test_good_css_change_gives_branch_four_captures_and_ok(self):
        before = self.snapshot()
        doc = self.draft(GOOD)
        self.assertEqual(doc["result"], "ok", doc)
        self.assertEqual(doc["branch"], "look/green")
        self.assertEqual(git(self.repo, "rev-parse", "look/green").strip(), doc["head"])
        self.assertIn("font-size: 1.1rem", git(self.repo, "show", "look/green:storefront-mockup/style.css"))
        self.assertEqual([(c["side"], c["page"], c["error"]) for c in doc["captures"]],
                         [("base", "home", None), ("base", "hike", None), ("head", "home", None), ("head", "hike", None)])
        self.assertTrue(all(Path(c["png"]).is_file() and Path(c["desktopPng"]).is_file() for c in doc["captures"]))
        after = self.snapshot()  # only the new branch: worktree, HEAD, index unchanged; temporary worktree gone
        self.assertEqual(after[:2] + after[3:], before[:2] + before[3:])
        self.assertEqual(after[2].replace(f"{doc['head']} commit\trefs/heads/look/green\n", ""), before[2])
        request = self.runner.call_args.args[0]
        self.assertEqual((request["model"], request["effort"], request["timeout"]), ("gpt-6.1-sol", "medium", 20))
        self.assertIn("Make the page text dark green", request["text"])
        self.assertEqual(sorted(p for p in look_guard.MODEL_FILES if f"=== {p} ===" in request["text"]), sorted(look_guard.MODEL_FILES))
        self.assert_live_untouched()

    def test_template_change_regenerates_its_pages(self):
        doc = self.draft(diff("hass/templates/info/index.html", PAGE, PAGE.replace("<h1>Hello</h1>", "<h1 class=big>Hello</h1>")))
        self.assertEqual(doc["result"], "ok", doc)
        for page in ("about", "getting-here", "policies", "faq"):
            self.assertIn("class=big", git(self.repo, "show", f"look/green:storefront-mockup/{page}/index.html"))

    def test_each_bad_diff_is_refused_and_leaves_repo_exactly_as_before(self):
        for reason, diffs in BAD.items():
            for model_diff in diffs:
                with self.subTest(reason=reason, diff=model_diff[-60:]):
                    (self.tmp / "ledger.json").unlink(missing_ok=True)
                    before = self.snapshot()
                    self.assertEqual(self.draft(model_diff), {"result": f"refused:{reason}"})
                    self.assertEqual(self.snapshot(), before)
        self.assert_live_untouched()

    def test_guard_rejects_multiline_url_and_every_srcset_candidate(self):
        for tag in ('<img src=\n"https://evil.example/a.png">',
                    '<img srcset="/safe.png 1x, https://evil.example/x.png 2x">'):
            with self.subTest(tag=tag):
                self.assertEqual(look_guard.check(page_add(tag), "add a picture"), "url")

        for old, new in (('<img src=\n"/safe.png">', '<img src=\n"https://evil.example/a.png">'),
                         ('<img srcset="/safe.png 1x,\n/safe2.png 2x">',
                          '<img srcset="/safe.png 1x,\nhttps://evil.example/x.png 2x">')):
            with self.subTest(new=new):
                self.assertEqual(look_guard.check(diff("hass/templates/index.html", PAGE + old + "\n", PAGE + new + "\n"),
                                                  "add a picture"), "url")

    def test_guard_checks_url_when_tag_opens_outside_diff_context(self):
        for old in ('<img\n a=1\n b=2\n c=3\n d=4\n src=\n"/safe.png"\n>\n',
                    '<img\n src=\n \n \n \n \n"/safe.png"\n>\n'):
            for replacement, expected in (("https://evil.example/x.png", "url"), ("/other.png", None)):
                patch = diff("hass/templates/index.html", old, old.replace("/safe.png", replacement))
                self.assertNotIn("<img", patch)
                self.assertEqual(look_guard.check(patch, "change the picture"), expected)

    def test_guard_refuses_ambiguous_incomplete_tag(self):
        old = '<img\n a=1\n b=2\n c=3\n d=4\n data-src=\n \n \n \n \n"https://evil.example/x.png"\n>\n'
        patch = diff("hass/templates/index.html", old, old.replace("data-src=", "src="))
        self.assertNotIn("<img", patch)
        self.assertNotIn("https:", patch)
        self.assertEqual(look_guard.check(patch, "change the picture"), "url")

    def test_guard_rejects_unquoted_unstated_visible_claim(self):
        self.assertEqual(look_guard.check(page_add('<img src="/x" alt=organic>'), "add a picture"), "claims")

    def test_guard_allows_owner_said_claim_and_relative_urls(self):
        self.assertIsNone(look_guard.check(page_add("<p>All organic</p>"), "add a line saying All organic"))
        self.assertIsNone(look_guard.check(page_add("<img src=\"/assets/a.png\" alt=\"Shop front\">"), "add a picture"))
        self.assertIsNone(look_guard.check(page_add('<img srcset="/a.png 1x, /b.png 2x" alt=organic>'),
                                           "add an organic picture"))

    def test_daily_cap_refuses_fourth_draft_before_codex(self):
        for code in ("a1", "a2", "a3"):
            self.assertEqual(self.draft(GOOD, code=code)["result"], "ok")
        before = self.snapshot()
        self.assertEqual(self.draft(GOOD, code="a4"), {"result": "refused:cap"})
        self.runner.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_existing_branch_bad_code_and_runner_failure_refused(self):
        git(self.repo, "branch", "look/green")
        self.assertEqual(self.draft(GOOD), {"result": "refused:branch"})
        self.assertEqual(self.draft(GOOD, code="../x"), {"result": "refused:usage"})
        self.runner = mock.Mock(return_value={"ok": False, "code": "timeout"})
        doc = look_change.draft(self.repo, "blue", "make it blue", self.tmp / "l2.json", str(self.tmp / "o"), runner=self.runner,
                                previewer=FakePreviewer(None))
        self.assertEqual(doc, {"result": "refused:codex"})

    def test_failed_preview_after_commit_leaves_repo_as_before(self):
        before = self.snapshot()
        with mock.patch.object(FakePreviewer, "capture", return_value={"ok": False, "png": None, "checks": {}}):
            self.assertEqual(self.draft(GOOD), {"result": "refused:preview"})
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
