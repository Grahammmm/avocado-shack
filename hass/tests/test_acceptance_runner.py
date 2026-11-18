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
EMPTY = "# no cases here\n"
HOOK_EMPTY = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        def test_a(self): self.assertTrue(True)
    def load_tests(loader, tests, pattern):
        return unittest.TestSuite()
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

    def test_empty_covering_entry_is_bad_map_before_import(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            for empty in ((), []):
                rows, code, probs = self._run(n, d, {"H01": ("test_counter",), "H02": empty},
                                              ("H01", "H02"))
                self.assertEqual((rows, code, probs), ([], 2, ["map: H02"]))
            # the counter module was never run (nor even imported)
            self.assertNotIn(n + ".test_counter", sys.modules)
            self.assertEqual(importlib.import_module(n + ".test_counter").RAN, [])

    def test_importable_empty_module_fails_with_zero_tests(self):
        with temp_pkg({"test_empty.py": EMPTY}) as (n, d):
            rows, code, probs = self._run(n, d, {"H01": ("test_empty",)})
            self.assertEqual((code, probs), (1, []))
            self.assertEqual(rows, [{"id": "H01", "result": "fail", "tests": 0,
                                     "failures": 1, "note": "no tests: test_empty"}])

    def test_empty_load_tests_hook_is_not_evidence(self):
        with temp_pkg({"test_hook.py": HOOK_EMPTY}) as (n, d):
            rows, code, _ = self._run(n, d, {"H01": ("test_hook",)})
            self.assertEqual(code, 1)
            self.assertEqual(rows, [{"id": "H01", "result": "fail", "tests": 0,
                                     "failures": 1, "note": "no tests: test_hook"}])

    def test_empty_module_is_not_masked_by_passing_sibling(self):
        files = {"test_empty.py": EMPTY, "test_counter.py": COUNTER, "test_ok.py": OK}
        for order in (("test_empty", "test_ok"), ("test_ok", "test_empty")):
            with temp_pkg(files) as (n, d):
                rows, code, _ = self._run(n, d, {"H01": order, "H02": ("test_counter",)})
                self.assertEqual(code, 1)
                self.assertEqual(rows[0], {"id": "H01", "result": "fail", "tests": 2,
                                           "failures": 1, "note": "no tests: test_empty"})
                self.assertEqual((rows[1]["result"], rows[1]["tests"]), ("pass", 1))
                self.assertEqual(importlib.import_module(n + ".test_counter").RAN, [1])

    def test_multiple_empty_modules_and_import_error_accounting(self):
        files = {"test_empty.py": EMPTY, "test_hook.py": HOOK_EMPTY, "test_bad.py": BAD,
                 "test_raises.py": RAISES, "test_ok.py": OK}
        with temp_pkg(files) as (n, d):
            rows, code, _ = self._run(n, d, {
                "H01": ("test_ok", "test_hook", "test_empty"),
                "H02": ("test_empty", "test_raises", "test_bad", "test_hook")})
            self.assertEqual(code, 1)
            self.assertEqual(rows[0], {"id": "H01", "result": "fail", "tests": 2,
                                       "failures": 2, "note": "no tests: test_hook"})
            # import-error note wins; 1 import error + 2 empty + 1 failed case
            self.assertEqual(rows[1], {"id": "H02", "result": "fail", "tests": 2,
                                       "failures": 4, "note": "import error: test_raises"})

    def test_reason_rows_and_nonempty_suites_preserve_contract(self):
        with temp_pkg({"test_ok.py": OK, "test_bad.py": BAD, "test_prints.py": PRINTS}) as (n, d):
            map_ = {"H07": "needs Michael's devices", "H18": "needs Michael's devices",
                    "H25": "release step", "H01": ("test_ok", "test_prints"),
                    "H02": ("test_bad",)}
            outer = io.StringIO()
            with contextlib.redirect_stdout(outer):
                rows, code, _ = self._run(n, d, map_)
            self.assertEqual(code, 1)
            self.assertNotIn("LEAK-MARKER", outer.getvalue())
            by = {r["id"]: r for r in rows}
            for id_, reason in (("H07", "needs Michael's devices"),
                                ("H18", "needs Michael's devices"), ("H25", "release step")):
                self.assertEqual(by[id_], {"id": id_, "result": "not covered", "tests": 0,
                                           "failures": 0, "note": reason})
            self.assertEqual(by["H01"], {"id": "H01", "result": "pass", "tests": 3,
                                         "failures": 0, "note": ""})
            self.assertEqual((by["H02"]["result"], by["H02"]["failures"], by["H02"]["note"]),
                             ("fail", 1, ""))

    def test_real_map_is_valid_on_disk(self):
        self.assertEqual(acceptance._validate(acceptance.MAP, acceptance._TESTS_DIR,
                                              acceptance.ALL_IDS), [])
        self.assertEqual({acceptance.MAP[i] for i in ("H07", "H18", "H25")},
                         {"needs Michael's devices", "release step"})
        self.assertEqual((acceptance.MAP["H23"], acceptance.MAP["H24"][0]),
                         (("test_auto_policy",), "test_design_check"))
        self.assertEqual(acceptance.MAP["H01"], ("test_content", "test_content_read_errors",
                         "test_browser_freshness", "test_publish"))
        self.assertEqual(acceptance.MAP["H02"], ("test_editor", "test_maker_product_batch"))
        self.assertEqual(acceptance.MAP["H03"], ("test_catalog_ops", "test_clear_availability",
                         "test_product_new", "test_maker_hide_products", "test_maker_optional_url",
                         "test_product_default_brand"))
        self.assertEqual(acceptance.MAP["H12"], ("test_attachment_reply", "test_photo_draft",
                         "test_photo_on_product", "test_photo_new_product", "test_photo_home_image",
                         "test_photo_batch", "test_media_batch"))
        self.assertEqual(acceptance.MAP["H22"], ("test_interpreter_cap", "test_interpreter_prompt"))
        self.assertEqual(acceptance.MAP["H17"], ("test_status_pause", "test_help",
                         "test_status_photos", "test_listing_command", "test_status_notice",
                         "test_social_draft_maker", "test_post_maker_command"))
        self.assertEqual(acceptance.MAP["H25"], "release step")
        self.assertEqual(acceptance.MAP["H04"], ("test_hike_ops", "test_route_add",
                         "test_route_edit", "test_route_hide", "test_hike_samples",
                         "test_hike_repeat", "test_hike_ics", "test_hike_cancel_note",
                         "test_preview_cancel_note"))
        self.assertEqual(acceptance.MAP["H05"], ("test_conversation", "test_near_approval",
                         "test_unknown_approval_code", "test_again", "test_interpreter_prompt_shelf_maker",
                         "test_interpreter_prompt_descriptions", "test_claims_health_awards",
                         "test_interpreter_no_undo", "test_field_words", "test_question_missing_fields",
                         "test_named_records", "test_interpreter_aliases", "test_social_message"))
        self.assertEqual(acceptance.MAP["H06"], ("test_preview", "test_undo", "test_history_search",
                         "test_store_field_undo"))
        self.assertEqual(acceptance.MAP["H13"], ("test_store_ops", "test_store_intro",
                         "test_store_headline", "test_store_story",
                         "test_store_home_image", "test_store_clear_home_image", "test_notice_start",
                         "test_club_intro"))
        for id_ in ("H04", "H05", "H06", "H12", "H13"):
            self.assertEqual(len(acceptance.MAP[id_]), len(set(acceptance.MAP[id_])))

    def test_av1622_modules_selected_once(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H01": ("test_browser_freshness", "test_publish"),
                "H03": ("test_clear_availability", "test_product_new"),
                "H17": ("test_listing_command",)}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(len(rec.names), len(set(rec.names)))
            for m in mods:
                self.assertEqual(rec.names.count("hass.tests." + m), 1)
        rows, code, _ = acceptance.run({"H25": acceptance.MAP["H25"]}, Recorder(), expected_ids=("H25",))
        self.assertEqual((code, rows[0]["result"], rows[0]["note"]),
                         (0, "not covered", "release step"))

    def test_av1937_modules_selected_once_in_order(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H02": ("test_maker_product_batch",),
                "H03": ("test_maker_hide_products", "test_maker_optional_url"),
                "H04": ("test_hike_repeat", "test_hike_ics"),
                "H12": ("test_photo_home_image",), "H22": ("test_interpreter_prompt",),
                "H17": ("test_status_notice", "test_social_draft_maker", "test_post_maker_command")}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rec.names, ["hass.tests." + m for m in acceptance.MAP[id_]])
            self.assertEqual(len(rec.names), len(set(rec.names)))
            self.assertEqual([n for n in rec.names if n[len("hass.tests."):] in mods],
                             ["hass.tests." + m for m in mods])
        rows, code, _ = acceptance.run({"H25": acceptance.MAP["H25"]}, Recorder(), expected_ids=("H25",))
        self.assertEqual((code, rows[0]["result"], rows[0]["tests"], rows[0]["note"]),
                         (0, "not covered", 0, "release step"))

    def test_av2152_modules_selected_once_in_order(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H04": ("test_hike_cancel_note", "test_preview_cancel_note"),
                "H05": ("test_unknown_approval_code", "test_again", "test_interpreter_prompt_shelf_maker",
                        "test_interpreter_prompt_descriptions", "test_claims_health_awards"),
                "H06": ("test_history_search", "test_store_field_undo"),
                "H12": ("test_photo_batch", "test_media_batch"),
                "H13": ("test_notice_start", "test_club_intro")}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rec.names, ["hass.tests." + m for m in acceptance.MAP[id_]])
            self.assertEqual(len(rec.names), len(set(rec.names)))
            self.assertEqual([n for n in rec.names if n[len("hass.tests."):] in mods],
                             ["hass.tests." + m for m in mods])

    def test_av0007_modules_selected_once_in_order(self):
        class Recorder(unittest.TestLoader):
            def __init__(self):
                super().__init__()
                self.names = []

            def loadTestsFromName(self, name, module=None):
                self.names.append(name)
                return unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])

        want = {"H03": ("test_product_default_brand",),
                "H05": ("test_interpreter_no_undo", "test_field_words", "test_question_missing_fields",
                        "test_named_records", "test_interpreter_aliases", "test_social_message")}
        for id_, mods in want.items():
            rec = Recorder()
            rows, code, probs = acceptance.run({id_: acceptance.MAP[id_]}, rec, expected_ids=(id_,))
            self.assertEqual((code, probs), (0, []))
            self.assertEqual(rec.names, ["hass.tests." + m for m in acceptance.MAP[id_]])
            self.assertEqual(len(rec.names), len(set(rec.names)))
            self.assertEqual([n for n in rec.names if n[len("hass.tests."):] in mods],
                             ["hass.tests." + m for m in mods])

    def test_h25_stays_release_step(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = acceptance.main(["--only", "H25"])
        lines = out.getvalue().splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(lines[0]), {"id": "H25", "result": "not covered", "tests": 0,
                                                "failures": 0, "note": "release step"})
        self.assertEqual(json.loads(lines[1]), {"summary": {"ids": 1, "pass": 0, "fail": 0, "not covered": 1}})


UNEXP = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        @unittest.expectedFailure
        def test_a(self): self.assertTrue(True)
""")
UNEXP2 = textwrap.dedent("""
    import unittest
    print('LEAK-MARKER')
    class T(unittest.TestCase):
        @unittest.expectedFailure
        def test_a(self): print('LEAK-MARKER')
        @unittest.expectedFailure
        def test_b(self): pass
        def test_c(self): self.assertTrue(True)
""")
EXPECTED = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        @unittest.expectedFailure
        def test_a(self): self.assertTrue(False)
        @unittest.skip("x")
        def test_b(self): pass
        def test_c(self): self.assertTrue(True)
""")
ERRS = textwrap.dedent("""
    import unittest
    class T(unittest.TestCase):
        def test_a(self): raise RuntimeError('x')
""")


class UnexpectedSuccessTest(unittest.TestCase):
    _run = RunnerTest._run

    def test_unexpected_success_fails_acceptance(self):
        with temp_pkg({"test_unexp.py": UNEXP}) as (n, d):
            rows, code, probs = self._run(n, d, {"H01": ("test_unexp",)})
            self.assertEqual((code, probs), (1, []))
            self.assertEqual(rows, [{"id": "H01", "result": "fail", "tests": 1,
                                     "failures": 1, "note": ""}])
            res = unittest.TextTestRunner(stream=io.StringIO()).run(
                unittest.TestLoader().loadTestsFromName(n + ".test_unexp"))
            self.assertFalse(res.wasSuccessful())

    def test_multiple_unexpected_successes_counted_each(self):
        with temp_pkg({"test_unexp2.py": UNEXP2, "test_ok.py": OK}) as (n, d):
            for order in (("test_unexp2", "test_ok"), ("test_ok", "test_unexp2")):
                rows, code, _ = self._run(n, d, {"H01": order})
                self.assertEqual(code, 1)
                self.assertEqual(rows[0], {"id": "H01", "result": "fail", "tests": 5,
                                           "failures": 2, "note": ""})

    def test_unexpected_success_adds_to_assertion_error_and_import_counts(self):
        files = {"test_unexp.py": UNEXP, "test_bad.py": BAD, "test_errs.py": ERRS,
                 "test_raises.py": RAISES}
        with temp_pkg(files) as (n, d):
            rows, _, _ = self._run(n, d, {
                "H01": ("test_unexp", "test_bad"), "H02": ("test_unexp", "test_errs"),
                "H03": ("test_unexp", "test_raises"),
                "H04": ("test_unexp", "test_bad", "test_raises")})
            self.assertEqual([(r["tests"], r["failures"], r["note"]) for r in rows],
                             [(3, 2, ""), (2, 2, ""),
                              (1, 2, "import error: test_raises"),
                              (3, 3, "import error: test_raises")])

    def test_expected_failures_and_skips_keep_existing_outcomes(self):
        with temp_pkg({"test_expected.py": EXPECTED}) as (n, d):
            rows, code, _ = self._run(n, d, {"H01": ("test_expected",)})
            self.assertEqual(code, 0)
            self.assertEqual(rows, [{"id": "H01", "result": "pass", "tests": 3,
                                     "failures": 0, "note": ""}])

    def test_unexpected_success_does_not_stop_later_rows(self):
        with temp_pkg({"test_unexp.py": UNEXP, "test_ok.py": OK}) as (n, d):
            rows, code, _ = self._run(n, d, {"H01": ("test_unexp",), "H02": ("test_ok",),
                                             "H25": "release step"})
            self.assertEqual(code, 1)
            self.assertEqual([(r["id"], r["result"]) for r in rows],
                             [("H01", "fail"), ("H02", "pass"), ("H25", "not covered")])

    def test_cli_unexpected_success_summary_and_output_isolation(self):
        with temp_pkg({"test_ok.py": UNEXP2}) as (n, d):
            code, lines = _main(["--only", "H01"], n, d)
            self.assertEqual(code, 1)
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0]), {"id": "H01", "result": "fail",
                             "tests": 3, "failures": 2, "note": ""})
            self.assertEqual(json.loads(lines[1])["summary"],
                             {"ids": 1, "pass": 0, "fail": 1, "not covered": 0})
            self.assertNotIn("LEAK-MARKER", "".join(lines))


class SelectedMissingTest(unittest.TestCase):
    def _main_map(self, argv, map_, n, d):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = acceptance.main(argv, map_=map_, tests_pkg=n, tests_dir=d)
        return code, out.getvalue(), err.getvalue()

    def test_selected_missing_id_returns_bad_map_not_keyerror(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            m = {"H02": ("test_counter",)}
            self.assertEqual(self._main_map(["--only", "H01"], m, n, d),
                             (2, "map: H01\n", ""))
            self.assertEqual(m, {"H02": ("test_counter",)})
            self.assertNotIn(n + ".test_counter", sys.modules)

    def test_missing_selected_id_blocks_valid_counter_prefix(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            m = {"H02": ("test_counter",)}
            self.assertEqual(self._main_map(["--only", "H02,H01"], m, n, d),
                             (2, "map: H01\n", ""))
            self.assertNotIn(n + ".test_counter", sys.modules)
            self.assertEqual(importlib.import_module(n + ".test_counter").RAN, [])

    def test_multiple_missing_selected_ids_keep_requested_order(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            m = {"H02": ("test_counter",)}
            code, out, err = self._main_map(["--only", "H03,H01,H02"], m, n, d)
            self.assertEqual((code, out, err), (2, "map: H03\nmap: H01\n", ""))
            self.assertNotIn(n + ".test_counter", sys.modules)

    def test_partial_map_with_complete_selection_remains_valid(self):
        with temp_pkg({"test_ok.py": OK}) as (n, d):
            code, out, err = self._main_map(["--only", "H01"], {"H01": ("test_ok",)}, n, d)
            self.assertEqual((code, err), (0, ""))
            lines = out.splitlines()
            self.assertEqual(json.loads(lines[0]), {"id": "H01", "result": "pass",
                             "tests": 2, "failures": 0, "note": ""})
            self.assertEqual(json.loads(lines[1])["summary"],
                             {"ids": 1, "pass": 1, "fail": 0, "not covered": 0})

    def test_unknown_id_precedes_missing_map_validation(self):
        with temp_pkg({"test_counter.py": COUNTER}) as (n, d):
            m = {"H02": ("test_counter",)}
            self.assertEqual(self._main_map(["--only", "H01,H99"], m, n, d),
                             (2, "map: H99\n", ""))
            self.assertNotIn(n + ".test_counter", sys.modules)

    def test_full_map_and_runtime_failure_semantics_unchanged(self):
        with temp_pkg({"test_bad.py": BAD, "test_ok.py": OK}) as (n, d):
            m = {i: ("test_ok",) for i in acceptance.ALL_IDS if i != "H05"}
            code, out, _ = self._main_map([], m, n, d)
            self.assertEqual((code, out), (2, "map: H05\n"))
            m = {"H01": ("test_bad",)}
            code, out, _ = self._main_map(["--only", "H01"], m, n, d)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out.splitlines()[0])["result"], "fail")
            self.assertEqual(m, {"H01": ("test_bad",)})


if __name__ == "__main__":
    unittest.main()
