"""RF1750-1 tests: an applied change whose `install` entry is not an object (or whose `install.state` is not a string)
reads "committed, not installed (install record unreadable)"; `editor.py history` and `show` never raise on it.

Run: python3 -m unittest hass.tests.test_install_status_shape -v
"""

import contextlib
import io
import json

from hass import editor
from hass.tests.test_editor import EditorTestCase

UNREADABLE = "committed, not installed (install record unreadable)"
GOOD, BAD = "chg-000000000001", "chg-000000000002"


def _rec(change_id, day, **extra):
    return {"state": "applied", "change_id": change_id, "applied_at": f"2026-10-0{day}T12:00:00+00:00",
            "commit": f"c{day}", "base": "b", "records": [], "generated": [], **extra}


class InstallStatusShapeTests(EditorTestCase):
    def test_install_not_an_object_is_unreadable(self):
        for bad in ("done", ["installed"], 5, True, "", [], 0):
            self.assertEqual(editor.install_status({"state": "applied", "install": bad}), UNREADABLE, repr(bad))

    def test_install_state_not_a_string_is_unreadable(self):
        for bad in (5, [], ["installed"], {"state": "installed"}, True):
            out = editor.install_status({"state": "applied", "install": {"state": bad, "reason": "r"}})
            self.assertEqual(out, UNREADABLE, repr(bad))

    def test_missing_or_null_install_unchanged(self):
        self.assertEqual(editor.install_status({"state": "applied", "install": None}), "committed, not installed")
        self.assertEqual(editor.install_status({"state": "applied"}), "committed, not installed")
        self.assertEqual(editor.install_status({"state": "applied", "install": {}}), "committed, not installed")

    def test_valid_shapes_unchanged(self):
        self.assertEqual(editor.install_status({"state": "applied", "install": {"state": "installed"}}), "installed")
        self.assertEqual(editor.install_status({"state": "applied", "install": {"state": "failed", "reason": "r"}}),
                         "committed, not installed (install failed: r)")
        for bad in ("done", 5, {"state": 5}):  # not applied wins over a bad install entry
            for state in ("failed", "prepared", None):
                self.assertIsNone(editor.install_status({"state": state, "install": bad}), (state, bad))
        self.assertIsNone(editor.install_status({"install": "done"}))


class InstallStatusCommandTests(EditorTestCase):
    def setUp(self):
        self.r = self.repo()
        editor._write_json(self.r.state / "changes" / f"{GOOD}.json", _rec(GOOD, 1, install={"state": "installed"}))
        editor._write_json(self.r.state / "changes" / f"{BAD}.json", _rec(BAD, 2, install="done"))

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = editor.main([*argv, "--state", str(self.r.state)])
        return code, out.getvalue(), err.getvalue()

    def test_history_lists_both_and_names_the_bad_install(self):
        got = editor.history(state=str(self.r.state))
        self.assertEqual(got["result"], "ok")
        self.assertEqual([(e["change_id"], e["install"]) for e in got["history"]],
                         [(BAD, UNREADABLE), (GOOD, "installed")])
        code, out, err = self.cli("history")
        lines = out.splitlines()
        self.assertEqual((code, err, len(lines)), (0, "", 2))
        bad_line = next(line for line in lines if json.loads(line)["change_id"] == BAD)
        self.assertEqual(json.loads(bad_line)["install"], UNREADABLE)
        self.assertNotIn("done", bad_line)  # the stored bad value is never printed

    def test_history_with_a_non_string_install_state(self):
        editor._write_json(self.r.state / "changes" / f"{BAD}.json", _rec(BAD, 2, install={"state": ["x"]}))
        code, out, err = self.cli("history")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual({json.loads(line)["change_id"]: json.loads(line)["install"] for line in out.splitlines()},
                         {BAD: UNREADABLE, GOOD: "installed"})

    def test_show_names_the_bad_install(self):
        got = editor.show(BAD, state=str(self.r.state))
        self.assertEqual((got["result"], got["install"]), ("ok", UNREADABLE))
        code, out, err = self.cli("show", BAD)
        self.assertEqual((code, err), (0, ""))
        printed = json.loads(out)
        self.assertEqual((printed["result"], printed["install"]), ("ok", UNREADABLE))
        self.assertNotIn("done", printed["install"])  # the status line never repeats the stored value
        self.assertEqual(editor.show(GOOD, state=str(self.r.state))["install"], "installed")
