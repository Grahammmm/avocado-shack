"""RF2030-6 tests: hass/retention.py --days/--now bounds. Any period gets a report or one usage error (exit 2).

--days above 36500, or a --now/--days pair reaching before year 1, is bad usage (exit 2) before anything opens,
never a traceback and never exit 1 (that means a store is unavailable). Temp dirs only, never the real state.
Run: python3 -B -m unittest hass.tests.test_retention_bounds -v
"""
import contextlib, io, json, shutil, sqlite3, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

from hass import conversation, inbox, retention

EARLY = "0005-06-01T00:00:00+00:00"
OVERFLOW = "retention: unsafe: --days reaches before year 1 from --now\n"


class RetentionBoundsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir()
        for name, schema in (("inbox.sqlite3", inbox.SCHEMA), ("conversation.sqlite3", conversation.SCHEMA)):
            with contextlib.closing(sqlite3.connect(self.state / name)) as db, db:
                db.executescript(schema)  # empty real-schema stores: a report that runs exits 0

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = retention.main(["report", *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_upper_bound_36500_is_accepted_with_the_default_clock(self):
        code, out, err = self.run_main("--state", str(self.state), "--days", "36500")
        doc = json.loads(out)
        self.assertEqual((code, doc["days"], doc["deletes"]), (0, 36500, 0), err)
        self.assertEqual(doc["inbox"], {"done": 0, "history": 0, "pending": 0, "oldest": None})
        self.assertEqual(retention.MAX_DAYS, 36500)

    def test_days_above_36500_is_usage_error_naming_the_range(self):
        for raw in ("36501", "1000000", "1000000000", "9" * 5000):
            code, out, err = self.run_main("--state", str(self.state), "--days", raw)
            self.assertEqual((code, out), (2, ""), raw[:12])
            self.assertIn("--days must be a whole number from 1 to 36500", err)
            self.assertIn("usage:", err)
            self.assertNotIn("Traceback", err)

    def test_cli_script_huge_days_has_no_traceback(self):
        script = str(Path(retention.__file__))
        proc = subprocess.run([sys.executable, "-B", script, "report", "--state", str(self.state),
                               "--days", "1000000000"], capture_output=True, text=True, timeout=60)
        self.assertEqual((proc.returncode, proc.stdout), (2, ""))
        self.assertIn("from 1 to 36500", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_now_and_days_reaching_before_year_1_is_unsafe_exit_2(self):
        code, out, err = self.run_main("--state", str(self.state), "--now", EARLY, "--days", "3650")
        self.assertEqual((code, out, err), (2, "", OVERFLOW))
        code, out, err = self.run_main("--state", str(self.state), "--now", "0001-01-01T00:00:00+00:00", "--days", "1")
        self.assertEqual((code, out, err), (2, "", OVERFLOW))
        code, out, _ = self.run_main("--state", str(self.state), "--now", EARLY, "--days", "1500")
        self.assertEqual((code, json.loads(out)["cutoff"][:4]), (0, "0001"))  # still after year 1: a report

    def test_overflow_is_checked_before_the_state_dir(self):
        missing = self.tmp / "missing"
        for extra in ([], ["--media", str(missing), "--backups", str(missing)]):
            code, out, err = self.run_main("--state", str(missing), "--now", EARLY, "--days", "3650", *extra)
            self.assertEqual((code, out, err), (2, "", OVERFLOW), extra)
        self.assertFalse(missing.exists())

    def test_report_function_raises_unsafe_for_an_overflowing_timedelta(self):
        with self.assertRaisesRegex(retention.Unsafe, "before year 1"):
            retention.report(str(self.tmp / "missing"), 10 ** 9)

    def test_superscript_is_usage_error_and_arabic_indic_three_is_three(self):
        self.assertTrue("\u00b2".isdigit())
        code, out, err = self.run_main("--state", str(self.state), "--days", "\u00b2")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("from 1 to 36500", err)
        self.assertNotIn("Traceback", err)
        code, out, err = self.run_main("--state", str(self.state), "--days", "\u0663")
        self.assertEqual((code, json.loads(out)["days"]), (0, 3), err)

    def test_existing_bad_values_still_exit_2(self):
        for args in (["--days", "0"], ["--days", "-1"], ["--days", "x"], ["--days", "1.5"], ["--days", ""],
                     ["--days", " 30"], []):
            code, out, err = self.run_main("--state", str(self.state), *args)
            self.assertEqual((code, out), (2, ""), args)
            self.assertIn("usage:", err)
            self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
