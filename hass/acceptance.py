#!/usr/bin/env python3
"""AVB-20: standing acceptance run per H id (local evidence, not in CI). Maps
each H01-H25 id to covering hass/tests modules (or a fixed "not covered"
reason), runs them in-process and prints one JSON line per id + a summary.
Exit 0/1/2 = no fail / a failure / bad map. Stdlib only.
"""
import argparse, contextlib, importlib, io, json, os, sys, unittest

TESTS_PKG = "hass.tests"
_TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")

MAP = {  # frozen: H id -> covering modules, or a "not covered" reason
    "H01": ("test_content", "test_content_read_errors", "test_browser_freshness", "test_publish"),
    "H02": ("test_editor",), "H03": ("test_catalog_ops", "test_clear_availability", "test_product_new"),
    "H04": ("test_hike_ops", "test_route_add", "test_route_edit", "test_route_hide", "test_hike_samples"),
    "H05": ("test_conversation", "test_near_approval"),
    "H06": ("test_preview", "test_undo"), "H07": "needs Michael's devices",
    "H08": ("test_bridge", "test_owner_sender_match", "test_host", "test_relay"),
    "H09": ("test_demo_transcript", "test_demo_negative", "test_demo_browser", "test_demo_transcript_photo"),
    "H10": ("test_label_reader", "test_label_reader_amounts", "test_label_question_brand"),
    "H11": ("test_media_audio",),
    "H12": ("test_attachment_reply", "test_photo_draft", "test_photo_on_product", "test_photo_new_product"),
    "H13": ("test_store_ops", "test_store_intro", "test_store_headline", "test_store_story",
            "test_store_home_image", "test_store_clear_home_image"),
    "H14": ("test_hike_capacity_ceiling", "test_hike_capacity_rsvp_off"),
    "H15": ("test_memory", "test_memory_source"),
    "H16": ("test_outbox_delayed", "test_late_yes", "test_writer_lock_entry"),
    "H17": ("test_status_pause", "test_help", "test_status_photos", "test_listing_command"), "H18": "needs Michael's devices",
    "H19": ("test_health", "test_health_host"), "H20": ("test_statebackup_drill", "test_statebackup", "test_statebackup_bundle"),
    "H21": ("test_retention",), "H22": ("test_interpreter_cap",),
    "H23": ("test_auto_policy",), "H24": ("test_design_check", "test_design_check_modes",
            "test_design_check_merge_base"), "H25": "release step",
}
ALL_IDS = tuple("H%02d" % i for i in range(1, 26))

def _validate(map_, tests_dir, expected_ids):
    probs = ["map: %s" % i for i in expected_ids if i not in map_]
    probs += ["map: %s" % k for k in map_ if k not in expected_ids]
    for id_, entry in map_.items():
        if id_ not in expected_ids or isinstance(entry, str):
            continue
        if not isinstance(entry, (tuple, list)):
            probs.append("map: %s" % id_)
            continue
        if not entry:  # an empty covering tuple/list is evidence of nothing
            probs.append("map: %s" % id_)
            continue
        probs += ["missing module: %s" % m for m in entry
                  if not os.path.exists(os.path.join(tests_dir, m + ".py"))]
    return probs

def _run_id(modules, loader, tests_pkg):
    # -> (tests_run, failures, note); a failed import names itself, counts as one failure;
    # an imported module that discovers no cases is no evidence: one failure each.
    import_error = first_empty = None
    empty = 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        suite = unittest.TestSuite()
        for m in modules:
            name = tests_pkg + "." + m
            try:
                importlib.import_module(name)
            except Exception:
                import_error = import_error or m
                continue
            mod_suite = loader.loadTestsFromName(name)
            if mod_suite.countTestCases() == 0:
                empty += 1
                first_empty = first_empty or m
                continue
            suite.addTest(mod_suite)
        result = unittest.TextTestRunner(stream=buf, verbosity=0, buffer=True).run(suite)
    failures = (len(result.failures) + len(result.errors)
                + len(result.unexpectedSuccesses)
                + (import_error is not None) + empty)
    note = ("import error: %s" % import_error if import_error
            else "no tests: %s" % first_empty if first_empty else "")
    return (result.testsRun, failures, note)

def run(map_, loader, tests_pkg=TESTS_PKG, tests_dir=None, expected_ids=None):
    # Validate then run in-process; return (rows, code, problems).
    tests_dir = _TESTS_DIR if tests_dir is None else tests_dir
    expected_ids = ALL_IDS if expected_ids is None else expected_ids
    probs = _validate(map_, tests_dir, expected_ids)
    if probs:
        return ([], 2, probs)
    rows, any_fail = [], False
    for id_ in expected_ids:
        entry = map_[id_]
        if isinstance(entry, str):
            rows.append({"id": id_, "result": "not covered", "tests": 0,
                         "failures": 0, "note": entry})
            continue
        tests_run, failures, note = _run_id(entry, loader, tests_pkg)
        any_fail = any_fail or bool(failures)
        rows.append({"id": id_, "result": "fail" if failures else "pass",
                     "tests": tests_run, "failures": failures, "note": note})
    return (rows, (1 if any_fail else 0), [])

def main(argv=None, map_=None, tests_pkg=TESTS_PKG, tests_dir=None):
    argv = sys.argv[1:] if argv is None else argv
    map_ = MAP if map_ is None else map_
    p = argparse.ArgumentParser(description="standing acceptance run per H id")
    p.add_argument("--only", help="comma-separated H ids, e.g. --only H03,H05")
    args = p.parse_args(argv)
    ids = ([s.strip() for s in args.only.split(",") if s.strip()]
           if args.only else list(ALL_IDS))
    unknown = [i for i in ids if i not in ALL_IDS]
    if unknown:
        print("map: %s" % unknown[0])
        return 2
    submap = map_ if not args.only else {i: map_[i] for i in ids if i in map_}  # absent: _validate says map: Hxx
    rows, code, probs = run(submap, unittest.defaultTestLoader,
                            tests_pkg, tests_dir, tuple(ids))
    if code == 2:
        print("\n".join(probs))
        return 2
    counts = {k: 0 for k in ("pass", "fail", "not covered")}
    for row in rows:
        print(json.dumps(row))
        counts[row["result"]] += 1
    print(json.dumps({"summary": {"ids": len(rows), **counts}}))
    return code

if __name__ == "__main__":  # run as a file: import hass.tests from the repo root
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
