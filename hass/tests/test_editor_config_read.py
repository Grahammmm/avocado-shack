"""RF1910-1 (H20): editor._load reads the state config.json only as a regular, non-link file <= 1 MiB holding an object
with a non-empty string worktree; anything else is UnsafeState "state config is unreadable", never a traceback.

WriterRepo temp repos only (temp main repo, linked writer worktree, 0700 state dir). Never the real state or worktree.
Run: python3 -m unittest hass.tests.test_editor_config_read -v
"""
import contextlib, io, json, os, threading, unittest  # noqa: E401
from pathlib import Path

from hass import editor, health
from hass.tests.test_editor import EditorTestCase, git
from hass.tests.test_health import NOW

BAD, MISSING = "state config is unreadable", "state dir is not initialised; run init first"


class ConfigReadTestCase(EditorTestCase):
    def setUp(self):
        self.r = self.repo()
        self.cfg_path = self.r.state / "config.json"
        self.good = json.loads(self.cfg_path.read_text("utf-8"))
        self.outside = self.r.state.parent / "outside"
        self.outside.mkdir()

    def snapshot(self):  # every name, type, size and mtime under the state dir, plus the worktree's head and status
        seen = []
        for root, dirs, files in os.walk(self.r.state):
            for name in sorted(dirs + files):
                st = os.lstat(Path(root) / name)
                seen.append((str(Path(root, name).relative_to(self.r.state)), st.st_mode, st.st_size, st.st_mtime_ns))
        return sorted(seen), self.r.head(), self.r.status()

    def replace(self, maker):
        self.cfg_path.unlink()
        maker(self.cfg_path)

    def assertRefused(self, message=BAD):
        before = self.snapshot()
        with self.assertRaises(editor.UnsafeState) as ctx:
            editor._load(str(self.r.state))
        self.assertEqual(str(ctx.exception), message)
        self.assertNotIn(str(self.r.state.parent), str(ctx.exception))
        self.assertEqual(self.snapshot(), before)  # nothing written to the state dir or worktree

    def load_in_thread(self):  # a FIFO must never block: the result comes back within 5 s
        box = {}

        def run():
            try:
                box["out"] = editor._load(str(self.r.state))
            except Exception as exc:  # noqa: BLE001 - reported to the test thread
                box["exc"] = exc
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(5)
        self.assertFalse(worker.is_alive(), "editor._load blocked on a FIFO")
        return box


class LinkAndTypeTests(ConfigReadTestCase):
    def test_link_to_a_valid_config_elsewhere_is_refused(self):
        target = self.outside / "config.json"
        target.write_text(json.dumps(self.good), "utf-8")
        self.replace(lambda p: p.symlink_to(target))
        self.assertRefused()
        self.replace(lambda p: p.symlink_to(self.outside / "dangling.json"))  # dangling link: not "run init first"
        self.assertRefused()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_fifo_or_link_to_fifo_is_refused_without_blocking(self):
        fifo = self.outside / "fifo"
        os.mkfifo(fifo)
        for maker in (os.mkfifo, lambda p: p.symlink_to(fifo)):
            with self.subTest(maker=maker):
                self.replace(maker)
                box = self.load_in_thread()
                self.assertIsInstance(box.get("exc"), editor.UnsafeState)
                self.assertEqual(str(box["exc"]), BAD)

    def test_folder_is_refused_and_missing_still_says_run_init(self):
        self.replace(lambda p: p.symlink_to(self.outside, target_is_directory=True))
        self.assertRefused()
        self.replace(lambda p: p.mkdir())
        self.assertRefused()
        self.cfg_path.rmdir()
        self.assertRefused(MISSING)


class ShapeAndSizeTests(ConfigReadTestCase):
    CASES = {"list": b"[1]", "empty object": b"{}", "number worktree": b'{"worktree": 7}',
             "empty worktree": b'{"worktree": ""}', "null worktree": b'{"worktree": null}', "invalid json": b"{",
             "invalid utf-8": b'{"worktree": "\xff\xfe"}', "deep list": b"[" * 100_000 + b"]" * 100_000}

    def write(self, data: bytes):
        self.cfg_path.write_bytes(data)

    def test_wrong_shape_or_bytes_is_refused(self):
        for name, data in self.CASES.items():
            with self.subTest(name):
                self.write(data)
                self.assertRefused()

    def test_cli_ops_and_history_print_one_unsafe_state_line(self):
        for name, data in self.CASES.items():
            self.write(data)
            for cmd in ("ops", "history"):
                with self.subTest(name, cmd=cmd):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = editor.main([cmd, "--state", str(self.r.state)])
                    self.assertEqual((code, err.getvalue()), (2, ""))
                    self.assertEqual(out.getvalue().count("\n"), 1, out.getvalue())
                    self.assertEqual(json.loads(out.getvalue()), {"result": "unsafe-state", "problems": [BAD]})

    def padded(self, size):  # valid JSON config of exactly `size` bytes
        base = json.dumps({**self.good, "pad": ""}).encode("utf-8")
        data = json.dumps({**self.good, "pad": "x" * (size - len(base))}).encode("utf-8")
        self.assertEqual(len(data), size)
        return data

    def test_over_one_mib_is_refused_and_exactly_one_mib_loads(self):
        self.write(self.padded(editor.MAX_CONFIG + 1))
        self.assertRefused()
        self.write(self.padded(editor.MAX_CONFIG))
        self.assertEqual(editor._load(str(self.r.state))[2], Path(self.good["worktree"]))

    def test_normal_config_loads_as_before(self):
        before = self.snapshot()
        sdir, cfg, wt = editor._load(str(self.r.state))
        self.assertEqual((sdir, cfg, wt), (self.r.state.resolve(), self.good, Path(self.good["worktree"])))
        self.assertEqual(self.good, {"worktree": str(self.r.wt.resolve()), "settings": {}})
        self.assertEqual(self.snapshot(), before)
        self.write(json.dumps({**self.good, "extra": [1, {"k": None}]}).encode("utf-8"))  # other keys untouched
        self.assertEqual(editor._load(str(self.r.state))[1]["extra"], [1, {"k": None}])
        self.assertEqual(git(self.r.wt, "status", "--porcelain"), "")


class HealthTests(ConfigReadTestCase):
    def test_health_writer_names_a_list_config_without_a_traceback(self):
        self.cfg_path.write_text("[]", "utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = health.main(["--state", str(self.r.state), "--writer"], now=NOW)
        doc = json.loads(out.getvalue())
        self.assertEqual((code, err.getvalue()), (1, ""))
        self.assertIn({"check": "writer", "detail": BAD}, [{k: p[k] for k in ("check", "detail")} for p in doc["problems"]])


if __name__ == "__main__":
    unittest.main()
