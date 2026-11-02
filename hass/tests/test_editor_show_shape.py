"""H06/H17 tests: `editor.py show` names a change or draft record that is valid JSON but not an object `unreadable`.

Run: python3 -m unittest hass.tests.test_editor_show_shape -v
"""

import json

from hass import editor
from hass.tests.test_editor_cli_io import CliIoTestCase, _rec

ID = "chg-000000000001"
WRONG_SHAPE = (b"[]", b"null", b'"x"', b"5")


class ShowWrongShapeTests(CliIoTestCase):
    def put(self, kind, data):
        (self.r.state / kind).mkdir(mode=0o700, exist_ok=True)
        (self.r.state / kind / f"{ID}.json").write_bytes(data)

    def assertShow(self, code, result, **extra):
        got, out = self.run_cli("show", ID)
        self.assertEqual(got, code, out)
        self.assertEqual(out.count("\n"), 1, out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(json.loads(out)["result"], result, out)
        for key, value in extra.items():
            self.assertEqual(json.loads(out)[key], value, out)
        return out

    def test_change_record_that_is_not_an_object_is_unreadable(self):
        for raw in WRONG_SHAPE:
            with self.subTest(raw=raw):
                self.put("changes", raw)
                out = self.assertShow(1, "unreadable", key=ID, kind="change")
                self.assertEqual(json.loads(out), {"result": "unreadable", "key": ID, "kind": "change"})

    def test_draft_record_that_is_not_an_object_is_unreadable(self):
        for raw in WRONG_SHAPE:
            with self.subTest(raw=raw):
                self.put("drafts", raw)
                out = self.assertShow(1, "unreadable", key=ID, kind="draft")
                self.assertEqual(json.loads(out), {"result": "unreadable", "key": ID, "kind": "draft"})

    def test_wrong_shape_change_wins_over_a_valid_draft(self):
        self.put("changes", b"[]")
        self.put("drafts", json.dumps({"ops": []}).encode())
        self.assertShow(1, "unreadable", kind="change")

    def test_corrupt_json_keeps_the_io_error_line(self):
        self.put("changes", b"{bad")
        self.assertIoError(["show", ID], "JSONDecodeError")

    def test_valid_applied_change_and_draft_print_as_before(self):
        self.put("changes", json.dumps(_rec(1)).encode())
        out = self.assertShow(0, "ok", install="committed, not installed")
        self.assertEqual(json.loads(out)["change"], _rec(1))
        (self.r.state / "changes" / f"{ID}.json").unlink()
        self.put("drafts", json.dumps({"ops": []}).encode())
        out = self.assertShow(0, "ok")
        self.assertEqual(json.loads(out), {"result": "ok", "draft": {"ops": []}})

    def test_invalid_and_unknown_ids_are_unchanged(self):
        self.assertEqual(self.run_cli("show", "nope")[0], 1)
        self.assertEqual(json.loads(self.run_cli("show", "nope")[1])["result"], "invalid")
        code, out = self.run_cli("show", ID)
        self.assertEqual((code, json.loads(out)), (1, {"result": "not-found", "key": ID}))

    def test_library_show_returns_the_unreadable_dict(self):
        self.put("drafts", b"[]")
        self.assertEqual(editor.show(ID, state=str(self.r.state)), {"result": "unreadable", "key": ID, "kind": "draft"})
