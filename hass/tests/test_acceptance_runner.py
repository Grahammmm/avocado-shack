"""AVB-20 tests: drive acceptance.run(map, loader) with tiny temp modules.

Covers the frozen edge paths: pass/fail exit codes, reason strings, the
exit-2 bad-map cases (nothing run, proven by a counter module), import errors,
the --only subset, and test stdout never leaking into the runner output.
"""
import contextlib, importlib, io, json, os, shutil, sys, tempfile, textwrap, unittest

from hass import acceptance

_SEQ = [0]
OK = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        def test_a(self): self.assertTrue(True)
        def test_b(self): self.assertTrue(True)
""")
BAD = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        def test_a(self): self.assertTrue(True)
        def test_b(self): self.assertTrue(False)
""")
RAISES = "raise ImportError('boom at import')\n"
PRINTS = textwrap.dedent("""
    import unittest
    print('LEAK-MARKER')
    class T(unittest.TestCase):
        def test_a(self):
            print('LEAK-MARKER')
            self.assertTrue(True)
""")
COUNTER = textwrap.dedent("""
    import unittest
    RAN = []
    class T(unittest.TestCase):
        def test_a(self): RAN.append(1)
""")


@contextlib.contextmanager
def temp_pkg(files):
    """Create a uniquely named throwaway package on sys.path; yield (name, dir)."""
    _SEQ[0] += 1
    parent = tempfile.mkdtemp(prefix="acc_parent_")
    name = "accpkg%d_%d" % (os.getpid(), _SEQ[0])
    pkgdir = os.path.join(parent, name)
    os.makedirs(pkgdir)
    for fn, src in dict(files, **{"__init__.py": ""}).items():
        with open(os.path.join(pkgdir, fn), "w") as fh:
            fh.write(src)
    sys.path.insert(0, parent)
    try:
        yield name, pkgdir
    finally:
        sys.path.remove(parent)
        shutil.rmtree(parent, ignore_errors=True)


def _full_map():
    return {i: ("test_ok",) for i in acceptance.ALL_IDS}


def _main(argv, name, pkgdir):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = acceptance.main(argv, map_=_full_map(), tests_pkg=name, tests_dir=pkgdir)
    return code, [ln for ln in buf.getvalue().splitlines() if ln.strip()]


class RunnerTest(unittest.TestCase):
    def _run(self, name, pkgdir, map_, ids=None):
        return acceptance.run(map_, unittest.TestLoader(), tests_pkg=name,
                              tests_dir=pkgdir, expected_ids=ids or tuple(map_))

    def test_pass_exit_zero_and_fail_exit_one(self):
        with temp_pkg({"test_ok.py": OK, "test_bad.py": BAD}) as (n, d):
            rows, code, probs = self._run(n, d, {"H01": ("test_ok",)})
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rows, [{"id": "H01", "result": "pass", "tests": 2,
                                     "failures": 0, "note": ""}])
            rows, code, _ = self._run(n, d, {"H01": ("test_bad",)})
            self.assertEqual(code, 1)
            self.assertEqual((rows[0]["result"], rows[0]["failures"]), ("fail", 1))

    def test_reason_string_is_not_covered_never_pass(self):
        with temp_pkg({"test_ok.py": OK}) as (n, d):
            rows, code, _ = self._run(n, d, {"H07": "needs Michael's devices"})
            self.assertEqual(code, 0)
            self.assertEqual(rows, [{"id": "H07", "result": "not covered", "tests": 0,
                                     "failures": 0, "note": "needs Michael's devices"}])

    def test_bad_map_exit_two_and_nothing_runs(self):
        with temp_pkg({"test_counter.py": COUNTER, "test_ok.py": OK}) as (n, d):
            cases = [({"H01": ("test_counter",), "H02": ("test_ghost",)},
                      ("H01", "H02"), "missing module: test_ghost"),
                     (dict(_full_map(), H26=("test_counter",)), acceptance.ALL_IDS,
                      "map: H26"),
                     ({i: ("test_counter",) for i in acceptance.ALL_IDS[1:]},
                      acceptance.ALL_IDS, "map: H01")]
            for map_, ids, problem in cases:
                rows, code, probs = self._run(n, d, map_, ids)
                self.assertEqual((code, rows), (2, []), problem)
                self.assertIn(problem, probs)
            # the counter module was never run (nor even imported)
            self.assertNotIn(n + ".test_counter", sys.modules)
            self.assertEqual(importlib.import_module(n + ".test_counter").RAN, [])

    def test_import_error_names_module_others_still_run(self):
        with temp_pkg({"test_ok.py": OK, "test_raises.py": RAISES}) as (n, d):
            rows, code, _ = self._run(n, d, {"H01": ("test_ok",), "H02": ("test_raises",),
                                             "H03": ("test_ok",)})
            by = {r["id"]: r for r in rows}
            self.assertEqual(code, 1)
            self.assertEqual((by["H02"]["result"], by["H02"]["note"]),
                             ("fail", "import error: test_raises"))
            for ok in ("H01", "H03"):
                self.assertEqual((by[ok]["result"], by[ok]["tests"]), ("pass", 2))

    def test_only_subset_and_unknown_id(self):
        with temp_pkg({"test_ok.py": OK}) as (n, d):
            self.assertEqual(_main(["--only", "H99"], n, d), (2, ["map: H99"]))
            self.assertEqual(_main(["--only", "H02,H99"], n, d)[0], 2)
            code, lines = _main(["--only", "H02"], n, d)
            self.assertEqual((code, len(lines)), (0, 2))
            self.assertEqual(json.loads(lines[0])["id"], "H02")
            self.assertEqual(json.loads(lines[1])["summary"]["ids"], 1)

    def test_test_stdout_does_not_leak(self):
        with temp_pkg({"test_prints.py": PRINTS}) as (n, d):
            outer = io.StringIO()
            with contextlib.redirect_stdout(outer):
                rows, code, _ = self._run(n, d, {"H01": ("test_prints",)})
            self.assertEqual((code, rows[0]["result"]), (0, "pass"))
            self.assertNotIn("LEAK-MARKER", outer.getvalue())

    def test_real_map_is_valid_on_disk(self):
        self.assertEqual(acceptance._validate(acceptance.MAP, acceptance._TESTS_DIR,
                                              acceptance.ALL_IDS), [])
        self.assertEqual({acceptance.MAP[i] for i in ("H07", "H18", "H25")},
                         {"needs Michael's devices", "release step"})
        self.assertEqual((acceptance.MAP["H23"], acceptance.MAP["H24"][0]),
                         (("test_auto_policy",), "test_design_check"))


if __name__ == "__main__":
    unittest.main()
