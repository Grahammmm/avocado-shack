"""BL-AV-2: the storefront QA scripts refuse to run without an explicit loopback PREVIEW_URL and never
write into the repository. Every run uses an explicit env; no browser or server is ever started."""
import json, os, shutil, socket, subprocess, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "storefront-mockup"
DRIVER = Path(__file__).resolve().parent / "fixtures" / "qa_env_driver.cjs"
NODE = shutil.which("node")
URL_REFUSAL = "QA refused: set PREVIEW_URL to an isolated loopback server (http://127.0.0.1:<port>)"
DIR_REFUSAL = "QA refused: QA_OUT_DIR must be outside the repository"
SAFE_URL = "http://127.0.0.1:9"  # unused discard port: a guard bug can never reach the service on 3101
SCRIPTS = [[NODE or "node", str(SITE / n)] for n in ("catalog-only-qa.cjs", "section-navigation-qa.cjs", "community-ui-qa.cjs")]
SCRIPTS.append([sys.executable, str(SITE / "community-qa.py")])


def tree():
    cmd = ["git", "status", "--porcelain", "--untracked-files=all", "--ignored"]
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=True).stdout


@unittest.skipUnless(NODE, "node is required for the QA scripts")
class QaEnvTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.other = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp), self.addCleanup(shutil.rmtree, self.other)
        self.before = tree()

    def run_env(self, cmd, **extra):
        env = {"PATH": os.environ.get("PATH", ""), "TMPDIR": self.tmp, "NODE": NODE,
               "PLAYWRIGHT_MODULE": "/nonexistent/playwright", **extra}
        return subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=5)

    def refused(self, cmd, line, **extra):
        r = self.run_env(cmd, **extra)
        self.assertEqual((r.returncode, r.stderr, r.stdout), (2, line + "\n", ""))
        self.assertEqual(tree(), self.before)  # nothing created or changed in the repo
        self.assertEqual(os.listdir(self.tmp), [])  # and no temp output folder either

    def test_preview_url_required(self):
        for cmd in SCRIPTS:
            with self.subTest(script=cmd[1]):
                self.refused(cmd, URL_REFUSAL)

    def test_non_loopback_preview_urls_refused(self):
        for url in ("http://example.com:3101", "https://127.0.0.1:3101", "http://127.0.0.1", "not a url", "",
                    "http://127.0.0.1.example.com:3101", "http://127.0.0.1:3101@example.com:3101",
                    "http://user@127.0.0.1:3101", "http://127.0.0.1:abc"):
            for cmd in SCRIPTS:
                with self.subTest(url=url, script=cmd[1]):
                    self.refused(cmd, URL_REFUSAL, PREVIEW_URL=url)

    def test_out_dir_inside_repo_refused(self):
        os.symlink(REPO, os.path.join(self.other, "link"))
        for out in (str(SITE), str(REPO / "new-subdir"), str(REPO), f"{SITE}/../new-subdir/x",
                    "storefront-mockup/new", os.path.join(self.other, "link", "evidence")):
            for cmd in SCRIPTS:
                with self.subTest(out=out, script=cmd[1]):
                    self.refused(cmd, DIR_REFUSAL, PREVIEW_URL=SAFE_URL, QA_OUT_DIR=out)

    def test_default_out_dir_is_fresh_temp_outside_repo(self):
        seen = set()
        for _ in range(2):
            r = self.run_env(["node", str(DRIVER)], PREVIEW_URL="http://localhost:4173/")
            self.assertEqual(r.returncode, 0, r.stderr)
            got = json.loads(r.stdout)
            self.assertEqual(got["base"], "http://localhost:4173")
            self.assertTrue(os.path.isdir(got["out"]))
            self.assertNotIn(REPO, Path(os.path.realpath(got["out"])).parents)
            self.assertEqual(r.stderr, "QA_OUT_DIR=" + got["out"] + "\n")
            seen.add(got["out"])
        self.assertEqual(len(seen), 2)
        self.assertEqual(tree(), self.before)

    def test_explicit_out_dir_outside_repo_accepted_and_not_created(self):
        for out in (self.other, str(REPO.parent / (REPO.name + "-qa-sibling"))):
            r = self.run_env(["node", str(DRIVER)], PREVIEW_URL="http://127.0.0.1:4173", QA_OUT_DIR=out)
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            self.assertEqual(json.loads(r.stdout), {"out": out, "base": "http://127.0.0.1:4173"})
        self.assertFalse(os.path.exists(REPO.parent / (REPO.name + "-qa-sibling")))

    def test_community_qa_refuses_before_its_server_starts(self):
        for extra in ({}, {"PREVIEW_URL": SAFE_URL, "QA_OUT_DIR": str(SITE)}):
            start = time.monotonic()
            self.refused(SCRIPTS[-1], URL_REFUSAL if not extra else DIR_REFUSAL, **extra)
            self.assertLess(time.monotonic() - start, 5)
            with socket.socket() as s:
                s.settimeout(1)
                self.assertNotEqual(s.connect_ex(("127.0.0.1", 3102)), 0)  # nothing listens on 3102
