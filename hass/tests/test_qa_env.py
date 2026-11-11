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
        os.symlink(SITE, os.path.join(self.other, "site"))  # other/site/.. is the repo on disk, not other
        for out in (str(SITE), str(REPO / "new-subdir"), str(REPO), f"{SITE}/../new-subdir/x", "storefront-mockup/new",
                    os.path.join(self.other, "link", "evidence"), f"{self.other}/site/..", f"{self.other}/site/../new/x"):
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
            self.assertTrue(os.path.isdir(got["out"]) and REPO not in Path(os.path.realpath(got["out"])).parents)
            self.assertEqual(r.stderr, "QA_OUT_DIR=" + got["out"] + "\n")
            seen.add(got["out"])
        self.assertEqual(len(seen), 2)
        self.assertEqual(tree(), self.before)

    def test_explicit_out_dir_outside_repo_accepted_canonical_and_not_created(self):
        os.mkdir(os.path.join(self.tmp, "in")), os.symlink(os.path.join(self.tmp, "in"), os.path.join(self.other, "ext"))
        sib, real, u = str(REPO.parent / (REPO.name + "-qa-sibling")), os.path.realpath, "http://127.0.0.1:4173"
        for out, want, url, base in ((self.other, real(self.other), u, u), (sib, sib, "http://localhost:80/", "http://localhost"),
                                     (f"{self.other}/ext/..", real(self.tmp), u, u)):  # ext/.. is the link target's parent
            r = self.run_env(["node", str(DRIVER)], PREVIEW_URL=url, QA_OUT_DIR=out)
            self.assertEqual((r.returncode, r.stderr, json.loads(r.stdout or "null")), (0, "", {"out": want, "base": base}))
        self.assertFalse(os.path.exists(sib))

    def synthetic(self):
        """Byte-identical copies of the real guard and driver in a disposable checkout-shaped tree, so TMPDIR
        can point into "the repository" without ever touching the real clone. Returns (root, box)."""
        box = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, box)
        root, src = os.path.join(box, "repo"), DRIVER.read_text()
        self.assertIn("preview:true", src)
        fixtures = os.path.join(root, "hass", "tests", "fixtures")
        os.makedirs(fixtures), os.makedirs(os.path.join(root, "storefront-mockup"))
        shutil.copyfile(SITE / "qa-env.cjs", os.path.join(root, "storefront-mockup", "qa-env.cjs"))
        shutil.copyfile(DRIVER, os.path.join(fixtures, "qa_env_driver.cjs"))
        Path(fixtures, "qa_env_nopreview.cjs").write_text(src.replace("preview:true", "preview:false"))
        return root, box

    def drive(self, root, tmpdir, preview, **extra):
        url = {"PREVIEW_URL": "http://127.0.0.1:4173"} if preview else {}
        env = {"PATH": os.environ.get("PATH", ""), "TMPDIR": tmpdir, **url, **extra}
        name = "qa_env_driver.cjs" if preview else "qa_env_nopreview.cjs"
        cmd = [NODE, os.path.join(root, "hass", "tests", "fixtures", name)]
        return subprocess.run(cmd, cwd=os.path.dirname(root), env=env, capture_output=True, text=True, timeout=5)

    @staticmethod
    def snapshot(root):  # every path in the synthetic tree, with file bytes
        snap = {}
        for d, dirs, files in os.walk(root):
            snap.update({os.path.join(d, n): None for n in dirs})
            snap.update({os.path.join(d, n): Path(d, n).read_bytes() for n in files})
        return snap

    def syn_refused(self, root, tmpdir):
        for preview in (True, False):
            with self.subTest(tmpdir=tmpdir, preview=preview):
                before = self.snapshot(root)
                r = self.drive(root, tmpdir, preview)
                self.assertEqual((r.returncode, r.stderr, r.stdout), (2, DIR_REFUSAL + "\n", ""))
                self.assertEqual(self.snapshot(root), before)  # no temp child, no evidence, sources unchanged

    def test_default_tmpdir_in_repository_refused_before_creation(self):
        root, _ = self.synthetic()
        for tmpdir in (root, os.path.join(root, "hass", "tests"), root + "/storefront-mockup/"):
            self.syn_refused(root, tmpdir)

    def test_default_tmpdir_symlink_into_repository_refused(self):
        root, _ = self.synthetic()
        Path(self.other, "canary").write_text("unrelated")
        os.symlink(root, os.path.join(self.other, "to-root"))
        os.symlink(os.path.join(root, "hass"), os.path.join(self.other, "to-hass"))
        outside_before = sorted(os.listdir(self.other))
        for tmpdir in ("to-root", "to-hass", "to-hass/.."):  # to-hass/.. is the repository root on disk
            self.syn_refused(root, os.path.join(self.other, tmpdir))
        self.assertEqual(sorted(os.listdir(self.other)), outside_before)
        self.assertEqual(Path(self.other, "canary").read_text(), "unrelated")

    def test_default_tmpdir_outside_repository_stays_fresh(self):
        root, box = self.synthetic()
        os.mkdir(os.path.join(box, "sibling"))
        for tmpdir in (os.path.join(box, "sibling"), box, self.tmp):  # sibling, ancestor, ordinary temp base
            for preview in (True, False):
                with self.subTest(tmpdir=tmpdir, preview=preview):
                    before, seen = self.snapshot(root), set()
                    for _ in range(2):
                        r = self.drive(root, tmpdir, preview)
                        self.assertEqual(r.returncode, 0, r.stderr)
                        got = json.loads(r.stdout)
                        self.assertEqual(r.stderr, "QA_OUT_DIR=" + got["out"] + "\n")
                        self.assertEqual(got.get("base"), "http://127.0.0.1:4173" if preview else None)
                        self.assertTrue(os.path.isdir(got["out"]))
                        self.assertEqual(os.path.dirname(got["out"]), os.path.realpath(tmpdir))
                        self.assertTrue(os.path.basename(got["out"]).startswith("avoshack-qa-"))
                        seen.add(got["out"])
                    self.assertEqual(len(seen), 2)
                    self.assertEqual(self.snapshot(root), before)

    def test_explicit_safe_output_ignores_unsafe_default_tmpdir(self):
        root, _ = self.synthetic()
        os.symlink(root, os.path.join(self.other, "to-root"))
        for tmpdir in (root, os.path.join(root, "hass"), os.path.join(self.other, "to-root")):
            for preview in (True, False):
                with self.subTest(tmpdir=tmpdir, preview=preview):
                    before = self.snapshot(root)
                    r = self.drive(root, tmpdir, preview, QA_OUT_DIR=self.tmp)
                    want = {"out": os.path.realpath(self.tmp), **({"base": "http://127.0.0.1:4173"} if preview else {})}
                    self.assertEqual((r.returncode, r.stderr, json.loads(r.stdout or "null")), (0, "", want))
                    self.assertEqual(self.snapshot(root), before)
                    self.assertEqual(os.listdir(self.tmp), [])

    def test_community_qa_refuses_before_its_server_starts(self):  # :80 passes its URL check, then the dir is refused
        for extra in ({}, {"PREVIEW_URL": "http://localhost:80", "QA_OUT_DIR": str(SITE)}):
            start = time.monotonic()
            self.refused(SCRIPTS[-1], URL_REFUSAL if not extra else DIR_REFUSAL, **extra)
            self.assertLess(time.monotonic() - start, 5)
            with socket.socket() as s:
                self.assertNotEqual(s.connect_ex(("127.0.0.1", 3102)), 0)  # nothing listens on 3102
