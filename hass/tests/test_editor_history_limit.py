"""RF1500-9 tests: editor.py history --limit is 1..500; anything else is a usage error, never an empty history.

Run: python3 -m unittest hass.tests.test_editor_history_limit -v
"""

import contextlib
import io
import json

from hass import editor
from hass.tests.test_editor import EditorTestCase


def _rec(n):
    return {"state": "applied", "change_id": f"chg-{n:012x}", "applied_at": f"2026-10-0{n}T12:00:00+00:00",
            "commit": f"c{n}", "base": "b", "records": [], "generated": []}


class HistoryLimitTests(EditorTestCase):
    def setUp(self):
        self.r = self.repo()
        for n in (1, 2, 3):
            editor._write_json(self.r.state / "changes" / f"chg-{n:012x}.json", _rec(n))

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = editor.main(["history", *argv, "--state", str(self.r.state)])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def ids(self, out):
        return [json.loads(line)["change_id"] for line in out.splitlines()]

    def test_out_of_range_or_non_number_is_a_usage_error(self):
        before = sorted(p.name for p in self.r.state.rglob("*"))
        for bad in ("0", "-1", "501", "abc", "1.5", ""):
            code, out, err = self.cli("--limit", bad)
            self.assertEqual((code, out), (2, ""), bad)
            self.assertIn("--limit", err)
            self.assertIn("1 to 500", err)
        self.assertEqual(sorted(p.name for p in self.r.state.rglob("*")), before)

    def test_bounds_and_default(self):
        newest_first = ["chg-000000000003", "chg-000000000002", "chg-000000000001"]
        self.assertEqual(self.ids(self.cli("--limit", "1")[1]), newest_first[:1])
        self.assertEqual(self.ids(self.cli("--limit", "500")[1]), newest_first)
        code, out, _err = self.cli()
        self.assertEqual((code, self.ids(out)), (0, newest_first))

    def test_python_call_outside_range_raises(self):
        for bad in (0, -1, 501, True, "5", 2.0, None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                editor.history(bad, state=str(self.r.state))
        self.assertEqual(len(editor.history(500, state=str(self.r.state))["history"]), 3)
