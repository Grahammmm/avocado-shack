"""H02/H06 tests: editor.py CLI turns I/O and bad-record errors into one JSON line; history survives a corrupt record.

Reuses the throwaway writer repo from test_editor (temp Git repo, linked worktree, private 0700 state dir).
Run: python3 -m unittest hass.tests.test_editor_cli_io -v
"""

import contextlib
import io
import json
import os

from hass import editor
from hass.tests.test_editor import EditorTestCase

CANARY = b"{bad canary-bytes-71c3"


def _rec(n):
    return {"state": "applied", "change_id": f"chg-{n:012x}", "applied_at": f"2026-10-0{n}T12:00:00+00:00",
            "commit": f"c{n}", "base": "b", "records": [], "generated": []}


class CliIoTestCase(EditorTestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = editor.main([*argv, "--state", str(self.r.state)])
        return code, out.getvalue()

    def setUp(self):
        self.r = self.repo()
        self.changes, self.drafts = self.r.state / "changes", self.r.state / "drafts"

    def assertIoError(self, argv, exc_name):
        code, out = self.run_cli(*argv)
        self.assertEqual(code, 2, out)
        self.assertEqual(out.count("\n"), 1, out)
        self.assertEqual(json.loads(out), {"result": "io-error", "problems": [exc_name]})
        self.assertNotIn(str(self.r.state.parent), out)  # no temp dir path
        self.assertNotIn("canary", out)  # no file bytes
        self.assertNotIn("Traceback", out)
        return out

    def good_records(self):
        for n in (1, 2):
            editor._write_json(self.changes / f"chg-{n:012x}.json", _rec(n))
            editor._write_json(self.drafts / f"chg-{n:012x}.json", {"ops": [{"op": "x.op", "args": {"n": n}}]})


class PrepareRequestIoTests(CliIoTestCase):
    def test_missing_request_file_is_one_io_error_line(self):
        for missing in ("/nonexistent.json", str(self.r.state.parent / "canary-missing.json")):
            self.assertNotIn("nonexistent", self.assertIoError(["prepare", missing], "FileNotFoundError"))
            self.assertEqual(self.r.drafts(), [])

    def test_request_is_a_directory(self):
        self.assertIoError(["prepare", str(self.r.state.parent)], "IsADirectoryError")
        self.assertEqual(self.r.drafts(), [])


class HistoryCorruptRecordTests(CliIoTestCase):
    def history(self):
        code, out = self.run_cli("history")
        self.assertEqual(code, 0, out)
        self.assertNotIn("Traceback", out)
        return [json.loads(line) for line in out.splitlines()]

    def test_corrupt_record_is_listed_unreadable_and_the_rest_unchanged(self):
        self.good_records()
        before = self.history()
        self.assertEqual([e["change_id"] for e in before], ["chg-000000000002", "chg-000000000001"])
        (self.changes / "chg-00000000000a.json").write_bytes(b"{bad")
        after = self.history()
        self.assertEqual(len(after), 3)
        self.assertEqual(after[:2], before)  # good ones unchanged, still newest-first
        self.assertEqual(after[2], {"change_id": "chg-00000000000a", "state": "unreadable", "applied_at": None,
                                    "commit": None, "revertedBy": None, "ops": []})

    def test_non_utf8_and_directory_records_are_unreadable(self):
        self.good_records()
        (self.changes / "chg-00000000000b.json").write_bytes(b"\xff")
        (self.changes / "chg-00000000000c.json").mkdir()
        states = {e["change_id"]: e["state"] for e in self.history()}
        self.assertEqual(states, {"chg-000000000001": "applied", "chg-000000000002": "applied",
                                  "chg-00000000000b": "unreadable", "chg-00000000000c": "unreadable"})

    def test_corrupt_draft_only_lists_record_with_no_ops(self):
        self.good_records()
        (self.drafts / "chg-000000000001.json").write_bytes(CANARY)
        (self.drafts / "chg-000000000002.json").write_bytes(b"\xff")
        entries = self.history()
        self.assertEqual([(e["change_id"], e["state"], e["commit"], e["ops"]) for e in entries],
                         [("chg-000000000002", "applied", "c2", []), ("chg-000000000001", "applied", "c1", [])])

    def test_limit_still_applies_with_unreadable_records(self):
        self.good_records()
        (self.changes / "chg-00000000000a.json").write_bytes(b"{bad")
        code, out = self.run_cli("history", "--limit", "1")
        self.assertEqual((code, [json.loads(x)["change_id"] for x in out.splitlines()]), (0, ["chg-000000000002"]))

    UNREADABLE = {"state": "unreadable", "applied_at": None, "commit": None, "revertedBy": None, "ops": []}

    def test_record_that_is_not_an_object_is_unreadable(self):
        self.good_records()
        before = self.history()
        for i, body in enumerate((b"[]", b"null", b'"x"', b"5", b'["' + CANARY + b'"]')):
            (self.changes / f"chg-00000000001{i}.json").write_bytes(body)
        after = self.history()
        self.assertEqual(after[:2], before)  # good ones unchanged, newest first
        self.assertEqual(sorted(e["change_id"] for e in after[2:]), [f"chg-00000000001{i}" for i in range(5)])
        for e in after[2:]:
            self.assertEqual(e, {"change_id": e["change_id"], **self.UNREADABLE})
        self.assertNotIn("canary", json.dumps(after))

    def test_time_field_of_the_wrong_type_is_unreadable_and_failed_at_string_is_kept(self):
        self.good_records()
        for n, extra in ((10, {"applied_at": 5}), (11, {"applied_at": ["x"]}), (12, {"applied_at": None, "failed_at": 7})):
            editor._write_json(self.changes / f"chg-{n:012x}.json", {**_rec(1), **extra})
        editor._write_json(self.changes / "chg-00000000000f.json",
                           {**_rec(1), "state": "failed", "applied_at": None, "failed_at": "2026-10-03T00:00:00+00:00"})
        entries = self.history()
        self.assertEqual([(e["change_id"], e["state"], e["applied_at"]) for e in entries[:3]],
                         [("chg-00000000000f", "failed", None), ("chg-000000000002", "applied", _rec(2)["applied_at"]),
                          ("chg-000000000001", "applied", _rec(1)["applied_at"])])
        self.assertEqual({e["change_id"]: e["state"] for e in entries[3:]},
                         {f"chg-{n:012x}": "unreadable" for n in (10, 11, 12)})

    def test_draft_of_the_wrong_shape_gives_no_ops(self):
        self.good_records()
        bad = ([], {"ops": {}}, {"ops": None}, {"ops": [{"op": "product.edit"}]}, {"ops": [{"op": 1, "args": {}}]},
               {"ops": [{"op": "x.op", "args": {"n": 1}}, "x"]})
        for draft in bad:
            with self.subTest(draft=draft):
                editor._write_json(self.drafts / "chg-000000000001.json", draft)
                entries = self.history()
                self.assertEqual([(e["change_id"], e["state"], e["commit"], e["ops"]) for e in entries],
                                 [("chg-000000000002", "applied", "c2", ['x.op {"n": 2}']),
                                  ("chg-000000000001", "applied", "c1", [])])

    def test_limit_still_applies_with_wrong_shape_records(self):
        self.good_records()
        (self.changes / "chg-00000000000a.json").write_bytes(b"[]")
        (self.changes / "chg-00000000000b.json").write_bytes(b'{"applied_at": 5}')
        code, out = self.run_cli("history", "--limit", "1")
        self.assertEqual((code, [json.loads(x)["change_id"] for x in out.splitlines()]), (0, ["chg-000000000002"]))


class ShowCorruptRecordTests(CliIoTestCase):
    def test_show_corrupt_record_is_one_io_error_line(self):
        (self.r.state / "changes").mkdir(mode=0o700)
        (self.changes / "chg-00000000000a.json").write_bytes(CANARY)
        self.assertIoError(["show", "chg-00000000000a"], "JSONDecodeError")

    def test_show_corrupt_draft_is_one_io_error_line(self):
        (self.r.state / "drafts").mkdir(mode=0o700)
        (self.drafts / "chg-00000000000a.json").write_bytes(b"\xff canary")
        self.assertIoError(["show", "chg-00000000000a"], "UnicodeDecodeError")

    def test_library_show_still_raises_for_in_process_callers(self):
        (self.r.state / "changes").mkdir(mode=0o700)
        (self.changes / "chg-00000000000a.json").write_bytes(CANARY)
        with self.assertRaises(json.JSONDecodeError):
            editor.show("chg-00000000000a", state=str(self.r.state))


class UnsafeStateStillWinsTests(CliIoTestCase):
    def test_group_readable_state_dir_with_corrupt_record_is_unsafe_state(self):
        self.good_records()
        (self.changes / "chg-00000000000a.json").write_bytes(CANARY)
        os.chmod(self.r.state, 0o750)
        for argv in (["history"], ["show", "chg-00000000000a"]):
            with self.subTest(argv=argv[0]):
                code, out = self.run_cli(*argv)
                self.assertEqual((code, json.loads(out)["result"]), (2, "unsafe-state"), out)
